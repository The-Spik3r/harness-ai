---
story: STORY-008
prd: PRD-023
slug: audit-columns-and-outcome
title: "Audit: MCP columns on `action_decisions`, `record(..., mcp=)`, `record_outcome`, correlation lookup"
type: NEW_CAPABILITY
complexity: medium
epic_branch: epic/PRD-023-mcp-and-skills
created: 2026-11-22
---

# Plan: Audit columns, `record(mcp=)`, `record_outcome`, correlation lookup

## Summary

Add the eleven section 6.9 columns and `idx_action_decisions_link`; teach `ActionDecisionRow`, the INSERT and the row mapper about them; give `record()` a keyword-only fail-closed `mcp=McpRecord(...)`; add best-effort `record_outcome`, a canonical-JSON hash helper and a read-only correlation query. No caller wiring (STORY-013/016/017).

- Story: `.agents/stories/PRD-023-mcp-and-skills/STORY-008-audit-columns-and-outcome.md`
- PRD sections: 6.9, 6.3 (M7/M9), 6.8, D9, D21, T9, T14
- Systems: `app/db/models.py`, `app/db/database.py`, `app/services/action_audit.py`, tests

## Design Decisions

- **Schema.** The eleven columns exactly as PRD 6.9, in **both** `CREATE_ACTION_DECISIONS_TABLE` (`models.py:~463`, after `write_id`, mapping order) and `ACTION_DECISIONS_ADDED_COLUMNS` (`models.py:480`, now `{"write_id": "TEXT"}`). Both, because `tests/test_db_resilience_write_id.py:300-304` requires every mapping entry `"<name> <ddl>"` to appear in the CREATE, and it keeps a fresh DB free of ALTERs. `surface` has a DEFAULT (NOT NULL rule, `test_db_resilience_write_id.py:307`). New `CREATE_ACTION_DECISIONS_LINK_INDEX` constant, imported at `database.py:44-47` and executed in `init_db()` after the pass (`:1502-1505`). Refresh the "fourth mapping" comment at `models.py:472`.
- **`ActionDecisionRow`** (`models.py:706`): 11 fields after `write_id`, before `id`, all defaulted (`surface="v1"`, rest `None`), so existing constructions (`test_actions_view.py:132-154`, `test_admin_actions.py:74-98`, `test_audit_journal.py:59-66`) work. The journal serializes by `dataclasses.fields` (`audit_journal.py:144`, `:181`): new fields ride along, old journal lines decode with defaults.
- **`McpRecord`**: frozen dataclass in `action_audit.py`: `surface` (only `"mcp"`, else `ValueError` in `__post_init__`), `mcp_server`, `skills: tuple[str, ...]`, `arguments_canonical_hash`, `linked_decision_id: Optional[int]`, `mcp_config_digest`, `jsonrpc_id: Union[str, int]`, plus optional `audit_id: Optional[int] = None` (see risk 1).
- **`record(decisions, identity, audit_ref=None, session_id=None, *, mcp=None)`** returns `list[int]` already (`action_audit.py:~214`), so nothing changes for `/v1` callers. `mcp=None`: code path untouched. `mcp` given: `ValueError` if `audit_ref` or `session_id` is also given, or `len(decisions) != 1`. Build rows with `decision_rows(..., _new_write_id(), None, None)` (`:~193`), then `dataclasses.replace` each: `tool_call_id="mcp:"+str(jsonrpc_id)`, `session_id=None`, `skills=json.dumps(list(skills), separators=(",",":"))`, the surface/server/hash/link/digest fields, `audit_id` from the record. Then `insert_action_decisions(rows)`. **No try/except, no `audit_journal` call**: any `StorageError` (incl. `StorageUnavailableError`) propagates and nothing is journaled (T9, O8; the docstring at `:222-226` already names this path). The minted `write_id` makes the unit IDEMPOTENT (`_keyed_kind`, `database.py:3488`), so an infra retry lands the row once; returns `[row_id]`.
- **`record_outcome(row_id, outcome, duration_ms, result_bytes, result_hash, result_flags, *, user_id)`**. `user_id` is keyword-only and required: after a failed UPDATE nothing can be read back, and STORY-013 holds the identity, so passing it is the only way to name the user in the ERROR line without a second statement. `result_flags: Sequence[str]` (names only; stored as JSON array); no content parameter exists (T14). Body: outcome not in `MCP_OUTCOME_VALUES` -> `logger.error("... user_id=%s row_id=%s outcome=%r")`, return, no write. Else `try: database.update_action_outcome(...) except Exception as exc:` -> `logger.error("... user_id=%s row_id=%s: %s", user_id, row_id, type(exc).__name__)` (class name only, never the message). Returns `None`, never raises.
- **Vocabulary** beside `ACTION_DECISION_VALUES` (`models.py:506`; `app/db` imports nothing from services): `McpOutcome = Literal[...]` and `MCP_OUTCOME_VALUES: tuple[str, ...]`; a test pins them equal via `typing.get_args` (same pairing as `Phase`/`_PHASES`, `database.py:949-953`).
- **`update_action_outcome(row_id, outcome, duration_ms, result_bytes, result_hash, result_flags_json)`** in `database.py`: `_unit_of_work("update_action_outcome", StatementKind.IDEMPOTENT, _op)`, one `UPDATE ... SET outcome, duration_ms, result_bytes, result_hash, result_flags WHERE id = ?` (same values twice is the same row).
- **Canonical hash.** `grep canonical` finds only `audit_journal._canonical` (`:135`, ASCII-escaped, private): not reusable. Add to `action_audit.py` beside `record()`: `canonical_json(obj) -> str` = `json.dumps(obj, ensure_ascii=False, separators=(",",":"), sort_keys=True)` (PRD 6.3) and `arguments_canonical_hash(arguments) -> str` = sha256 hex of its UTF-8 bytes (style of `hash_prompt`, `duplicate_checker.py:24`). STORY-013/016 call these.
- **Correlation** `find_linkable_v1_decision(user_id, server, tool_names, arguments_canonical_hash, window_seconds, *, now=None) -> Optional[ActionDecisionRow]` in `database.py`, `StatementKind.READ`. SQL: `WHERE user_id=? AND surface='v1' AND mcp_server=? AND tool_name IN (?, ...) AND arguments_canonical_hash=? AND decision IN ('allow','flag') AND timestamp >= ? AND NOT EXISTS (SELECT 1 FROM action_decisions l WHERE l.linked_decision_id = action_decisions.id) ORDER BY id DESC LIMIT 1` (the index serves it; `id DESC` not timestamp, ties: `database.py:~3571`). Time: `timestamp` is second-resolution TEXT in `_TIMESTAMP_FORMAT` (`database.py:71`); the existing window read computes `since` in Python and compares `timestamp >= ?` (`find_duplicate_timestamp`, `:1723-1767`; caller `duplicate_checker.py:31`). Mirror it with `now` injectable (no sleeps in tests). **Tool match** (orchestrator decision, overrides the earlier draft): alias rows keep the raw `/v1` `tool_name` the model emitted (audit fidelity). The caller passes `tool_names: Sequence[str]`, the exact candidate names (STORY-016 computes `prefix + server + '__' + tool` for each configured `v1_aliases` prefix), and the query uses `tool_name IN (...)` with one bound placeholder per name; an empty `tool_names` returns None without querying. Read-only here; the **claim race** (two gateway calls matching one `/v1` row) is STORY-016's to close.
- **Audit API readability**: `list_action_decisions` is `SELECT *` (`:3602`); `_row_to_action_decision_row` (`:3540`) maps by name and gets the 11 fields. `admin.py:_action_entry` (`:193`) copies fields explicitly and is left alone: exposing them is STORY-017, so `test_admin_actions.py` is unchanged.

## Skills In Use

None (`.agents/skills/` holds only `frontend-design`; story `skills: []`).

## Patterns to Follow

| Category | Source | What to mirror |
|----------|--------|----------------|
| Added columns | `models.py:463-480` | column in CREATE and mapping; comment cites PRD |
| Insert / mapper | `database.py:3404-3456`, `:3540-3562` | explicit column list; map by name |
| Unit of work | `database.py:3604-3607` | `_unit_of_work("<function name>", StatementKind.X, _op)` |
| Closed vocabulary | `models.py:506`, `usage_limits.py:39` | tuple + Literal, pinned in a test |
| Log fields | `action_audit.py:403-410` | `user_id=%s` style |

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/db/models.py` | UPDATE | CREATE + mapping, index constant, row fields, vocabulary |
| `app/db/database.py` | UPDATE | `init_db` index, INSERT, mapper, `update_action_outcome`, `find_linkable_v1_decision` |
| `app/services/action_audit.py` | UPDATE | `McpRecord`, canonical helpers, `record(mcp=)`, `record_outcome`, docstring |
| `tests/test_mcp_audit.py` | CREATE | new tests |
| `tests/test_action_audit.py`, `tests/test_db_resilience_retry.py`, `tests/test_db_resilience_write_id.py` | UPDATE | census edits (Task 4) |

## Tasks

1. **Schema and row model** (`models.py`): as above. Validate: `.venv/Scripts/python -c "from app.db import models"`.
2. **Database layer** (`database.py`): `init_db()` runs the link index; INSERT grows to 29 columns/placeholders (`:3423-3446`); mapper; the two new functions after `list_action_decisions`. Validate: `.venv/Scripts/python -c "from app.main import app; print('OK')"`.
3. **Service layer** (`action_audit.py`): as above; docstring "What each column holds" gains a gateway-row paragraph.
4. **Census edits** (each changed assertion gets a PRD-023 STORY-008 comment):
   - `test_action_audit.py:75-96` `_COLUMNS`: append the eleven `(name, notnull)` (`surface` 1, rest 0); feeds `:179-183` and `:568`.
   - `test_action_audit.py:239-245` `added` set gains `("index", "idx_action_decisions_link")`; `:262` count `5` becomes `6` (CREATE + PRAGMA + 4 indexes; no ALTER on a fresh DB).
   - `test_db_resilience_write_id.py:228-249`: the legacy table is built without everything from `write_id` on (`_without_write_id`, `:189-195`), so the expected ALTER list gains the eleven `ALTER TABLE action_decisions ADD COLUMN <name> <ddl>` after the `write_id` one. This is also the PRD-022 to PRD-023 upgrade proof.
   - `test_db_resilience_retry.py`: `_EXPECTED_KINDS` (`:675-677`) gains `"update_action_outcome": K.IDEMPOTENT` and `"find_linkable_v1_decision": K.READ`; `:725` `== 42` becomes `== 44`. `_PER_CALL_KIND`, `_EXEMPT` and the `_session`/`get_connection` caller sets (`:766-779`) are unchanged: both functions go through `_unit_of_work`.
   - Checked, no edit: `test_audit_journal.py:186-205` is generic by `dataclasses.fields`; `test_db.py` snapshots (`:1950`, `:2622`) cover other readers; `/audit` field-order guards are `audit_logs`.
5. **New tests** (`tests/test_mcp_audit.py`). Pure, runnable without Docker (no `temp_db`; the repo auto-marks a test `db` by fixture, `tests/conftest.py:25`):
   - `get_args(McpOutcome) == MCP_OUTCOME_VALUES`, six names exactly.
   - `canonical_json`: sorted keys, no whitespace, non-ASCII kept; key order does not change the hash; hash is sha256 hex of the UTF-8 text.
   - `McpRecord` frozen; `surface="v1"` raises; `record(mcp=..., audit_ref=...)` / `session_id=...` / two decisions raise `ValueError`.
   - `record(mcp=)` with `insert_action_decisions` and `audit_journal.append` monkeypatched: a raised `StorageUnavailableError` propagates and `append` is never called (T9); on success the rows carry `tool_call_id == "mcp:7"` (and `"mcp:abc"`), `session_id None`, `skills == '["a@1.0.0","b@2.1.0"]'`, a `write_id`, and the call returns the ids.
   - `mcp=None` rows equal `decision_rows(...)` output field for field.
   - `record_outcome`: `inspect.signature` names are exactly `row_id, outcome, duration_ms, result_bytes, result_hash, result_flags, user_id` (no content parameter, T14); invalid outcome: `update_action_outcome` monkeypatched to fail if called, ERROR logged naming user and row id, no raise; update raising `StorageUnavailableError` then `RuntimeError("secret")`: ERROR names user and row id, no raise, text `secret` absent from the log.
   - `find_linkable_v1_decision` signature check.

   DB tests (cannot run locally, Docker down; CI reads them): index columns `["user_id","arguments_canonical_hash"]`; fresh init has the 11 columns; a legacy table converges and an old row reads `surface='v1'`, others NULL; mcp row round trip via `list_action_decisions`; `record_outcome` sets the five columns on its row only, `result_flags` JSON of names; update of a missing id is silent; correlation returns the newest of two matches and ignores `deny`, other user, server, tool, hash, `surface='mcp'` rows, rows older than the window (injected `now`, boundary included) and a row already named by another row's `linked_decision_id`; `flag` qualifies; `None` when nothing matches.

## End-to-End Tests

- [ ] No route changes; `from app.main import app` is the boot check.
- [ ] DB (CI): second `init_db()` on the new schema issues no ALTER (existing `test_init_db_issues_no_alter_when_schema_is_current`).

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
# No DB needed:
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_mcp_audit.py -k "not db"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_db_resilience_retry.py -k "covers_the_modules or one_unit_of_its_own or keyed_kind"
# With the DB (CI), one call:
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_mcp_audit.py tests/test_action_audit.py tests/test_db_resilience_write_id.py tests/test_db_resilience_retry.py tests/test_audit_journal.py tests/test_admin_actions.py tests/test_actions_view.py tests/test_untouched_app.py
```
`-k "not db"` is a placeholder: use the repo's real selector (`-m "not db"` if the marker is registered, else name the pure tests); check `tests/conftest.py:25`. No test is renamed or removed, so `test_pii_redaction_integration.py` is not needed.

## Acceptance Criteria -> Tasks -> Tests

| AC | Tasks | Test that proves it |
|----|-------|---------------------|
| AC1 columns, index, old rows `v1` | 1, 2, 4 | `test_action_audit.py::test_init_db_creates_action_decisions_with_the_prd_columns`, `::test_init_db_adds_action_decisions_to_a_pre_prd_database_and_alters_nothing`, `test_db_resilience_write_id.py::test_init_db_migrates_a_pre_prd018_database`, new legacy-convergence + index tests (db) |
| AC2 `record(mcp=)` fail-closed, row content | 3, 5 | new `test_record_mcp_storage_error_propagates_and_never_journals`, `test_record_mcp_row_fields` (pure) + db round trip |
| AC3 `record_outcome` best effort, closed vocabulary | 1, 3, 5 | new `test_record_outcome_*` (pure) + db update test |
| AC4 correlation helper | 2, 5 | new `test_find_linkable_*` (db) |

## Risks / questions

1. PRD M7 writes `record(..., audit_id=link.audit_id, ...)`, but `record()` has no such parameter after PRD-018. This plan carries the correlated `audit_id` on `McpRecord`; confirm.
2. Alias rows keep the raw `/v1` `tool_name`; STORY-016 passes the exact prefixed candidates to `find_linkable_v1_decision` (orchestrator decision).
3. The claim race belongs to STORY-016.
