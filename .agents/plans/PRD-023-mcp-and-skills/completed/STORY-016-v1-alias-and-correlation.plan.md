---
story: STORY-016
prd: PRD-023
slug: v1-alias-and-correlation
title: "`/v1` alias resolution at step 7c and gateway correlation at M7"
type: NEW_CAPABILITY
complexity: large
epic_branch: epic/PRD-023-mcp-and-skills
created: 2026-11-23
---

# Plan: `/v1` alias resolution and gateway correlation

## Summary

A pure resolver in `action_policy` maps a raw `/v1` name (`harness_postgres-staging__query`) to `(server, bare tool)` using the configured prefixes and the caller's config-only visible set. `evaluate_all` gains a keyword-only `aliases` input; `evaluate` runs with `ToolCall(id, bare, args)` and `McpSurface(server, visible[server])`, then the decision is rewritten to keep the raw name and to carry `mcp_server`. `query_pipeline` step 7c builds `aliases` only when `MCP_ENABLED` and prefixes are non-empty (zero DB reads). `action_audit` stamps `surface='v1'`, `mcp_server` and the canonical hash on the row. At M7 the gateway's pre-forward insert becomes one `INSERT ... SELECT` that claims the newest linkable `/v1` row atomically, replacing `_correlate`.

- Story: `.agents/stories/PRD-023-mcp-and-skills/STORY-016-v1-alias-and-correlation.md` (AC text lives there)
- PRD sections used: 6.8, 6.9, F9, D15, D21, O8 (out of scope), User Story 6, R5
- Systems affected: `action_policy`, `query_pipeline` (7c), `action_audit`, `database`, `mcp_gateway`

## Design Decisions

1. **Resolver** `resolve_v1_alias(name, prefixes, visible) -> Optional[tuple[str, str]]` plus a sentinel for ambiguity (return a small frozen `AliasMatch(server, tool)` or raise nothing; ambiguity = `AMBIGUOUS` constant). Pure: no I/O, no settings. A prefix resolves when `name.startswith(prefix)` and `name[len(prefix):].partition("__")` gives non-empty `server in visible` and `tool in visible[server]` (first `__`, O7, same as `mcp_config.split_tool` at `mcp_config.py:178-190`). One match -> resolved; two or more distinct prefixes -> `tool.malformed`; none -> today's path. Note `harness__pg__q` against prefix `harness_` leaves `_pg__q`, server `_pg`, not visible: no false ambiguity for the two confirmed prefixes.
2. **`evaluate_all(calls, identity, policy=None, *, aliases=None)`** (`action_policy.py:415`). `aliases` is a frozen `AliasInput(prefixes: tuple[str,...], visible: Mapping[str, frozenset[str]])`. `None` -> byte-identical loop. Per call: resolve; resolved -> `dataclasses.replace(evaluate(ToolCall(call.id, tool, call.arguments), identity, policy, surface=McpSurface(server, visible[server])), tool_name=<raw name>, mcp_server=server)`. `tool_call_id` is already the raw id. Ambiguous -> build the `tool.malformed` decision through `evaluate`'s own fail-closed route (fixed detail e.g. `"ambiguous alias prefix"`; add a private helper that mirrors the boundary's `except` branch, `action_policy.py:393-411`), `tool_name` raw, `mcp_server` None. The resolver call sits inside the same never-raises guarantee: wrap in the engine's boundary pattern so a bad input still returns `tool.malformed`.
3. **ActionDecision** gets one optional trailing field `mcp_server: Optional[str] = None` (after `arguments`, `action_policy.py:89-125`). **Deviation from the "two fields" suggestion**: the canonical hash is NOT stored on the decision. `action_policy` cannot import `action_audit.canonical_json` (DB-importing, would invert layering), and duplicating canonicalisation risks drift from the gateway. `action_audit._row_of` (`action_audit.py:178`) computes it from `d.arguments` when `d.mcp_server is not None`: `json.loads` -> if a `dict`, `arguments_canonical_hash(obj)` (same function the gateway's hash equals: `mcp_gateway.py:448-460` `canonical_json(arguments)` then sha256), else NULL. `{}` hashes like an absent gateway `arguments` (`"{}"`); `""`, non-JSON, arrays, scalars -> NULL (all denied by `tool.malformed`). Row: `surface='v1'` (default), `mcp_server`, hash, `skills` NULL. `decision_rows` already feeds both `record` and step 8's journal path, so both persist the columns.
4. **Step 7c wiring** (`query_pipeline.py:1622-1646`, the only `evaluate_all` call in `app/`; grep confirmed). Both the buffered path and the PRD-021 real-time path reach it, because streaming holds tool calls until the response is complete and decides them here (no other decision site: `grep -n "evaluate" query_pipeline.py v1.py v1_sse.py` finds only line 1643). Build `aliases` just before the call: `settings.MCP_ENABLED and (cfg := mcp_config.get_config()).v1_prefixes` -> `AliasInput(cfg.v1_prefixes, mcp_config.visible_tools(identity))`; else `None`. `visible_tools` reads config + `authz.holds` only. Called through modules (`action_policy.evaluate_all`, per `query_pipeline.py:21-24`). Add `mcp_config` to the module imports.
5. **Atomic claim** in one statement. New public `database.insert_mcp_decision_linked(row, candidate_names, window_seconds, *, now=None) -> int` (single keyed row, `K.IDEMPOTENT`, one `_unit_of_work`). SQL shape (same column list and `_ON_WRITE_ID_CONFLICT` as `database.py:3426-3437`):
   `INSERT INTO action_decisions (cols...) SELECT ?,..., c.id, COALESCE(c.audit_id, ?) FROM (SELECT 1) one LEFT JOIN (SELECT id, audit_id FROM action_decisions WHERE <find_linkable_v1_decision WHERE, database.py:3698-3711> ORDER BY id DESC LIMIT 1) c WHERE true ON CONFLICT(write_id) DO NOTHING RETURNING id`.
   The LEFT JOIN keeps the row inserted when no candidate matches (plain INSERT...SELECT would insert nothing). `WHERE true` before `ON CONFLICT` avoids the SQLite parsing ambiguity: verify on libSQL in Task 2. The candidate WHERE text is extracted into a module constant shared with `find_linkable_v1_decision`. The `since` window is computed in Python as TEXT exactly as `database.py:3690-3692`. Replay: conflict -> `_keyed_row_id` reads the original id (`database.py:1613`). Serialisation: libSQL serialises write transactions, the NOT EXISTS reads the committed state inside the same write transaction, so two concurrent claims cannot both link one row (proved by the `db` thread test). No unique index, no migration. Keep `find_linkable_v1_decision` read-only and unchanged in behaviour.
6. **Plumbing**. `McpRecord` (`action_audit.py:241-263`) gains trailing optional `link_candidates: tuple[str, ...] = ()`, `link_window_seconds: int = 0`, `link_now: Optional[datetime] = None`; `audit_id`/`linked_decision_id` stay but the gateway now passes None for both when it supplies candidates (the statement fills them). `record(mcp=...)` (`action_audit.py:315-330`): when `mcp.link_candidates` and `mcp.mcp_server` -> `insert_mcp_decision_linked(rows[0], mcp.link_candidates, mcp.link_window_seconds, now=mcp.link_now)`; otherwise `insert_action_decisions(rows)` as today (no extra statement). Still no audit_ref, never journaled (T9).
7. **Gateway** (`mcp_gateway.py:385-395, 448-460, 462-527`). Delete `_correlate`. After the decision: candidates only when `server is not None`, `decision.decision in ('allow','flag')`, and prefixes non-empty: `tuple(p + server + "__" + tool for p in mcp_config.get_config().v1_prefixes)`; window `settings.MCP_LINK_WINDOW_SECONDS`; `now` via a module-level injectable (`_now()` returning UTC datetime; tests monkeypatch it; no new clock read in `action_policy`). Round trips unchanged (the claim rides the existing pre-forward insert). A `MCP_LINK_WINDOW_SECONDS=0` still runs the statement (window is `>= now`).
8. **Census** (brief rule): new public function in `database.py` -> `tests/test_db_resilience_retry.py` `_EXPECTED_KINDS` (+ `"insert_mcp_decision_linked": K.IDEMPOTENT`), count assert 44->45 (`:730`, comment citing STORY-016), caller sets in `test_nothing_opens_a_session_outside_the_unit_and_the_boot_path`; check `tests/test_db.py:1982` signature snapshot and the `find_linkable` module-docstring text in `test_mcp_audit.py`.

## Skills In Use

None apply (`.agents/skills/` holds only `frontend-design`; story `skills: []`).

## Patterns to Follow

| Category | Source | What to mirror |
|----------|--------|----------------|
| Pure engine inputs | `action_policy.py:181-198` `McpSurface` | frozen dataclass; caller computes, engine checks |
| Fail-closed boundary | `action_policy.py:393-411` | `tool.malformed`, fixed detail, class name only in log |
| Keyed insert | `database.py:3426-3492` | `_unit_of_work`, `_ON_WRITE_ID_CONFLICT`, `_keyed_row_id` |
| Link WHERE | `database.py:3666-3716` | share the text; window as TEXT |
| Gateway engine call | `mcp_gateway.py:448-460` | bare tool name, `McpSurface`, `canonical` hash |
| DB tests | `tests/test_mcp_audit.py:255-370` (`temp_db`, `_row`, `_NOW`, `_ts`) | row helpers and injected `now` |
| Gateway tests | `tests/test_mcp_gateway.py:1-45` | `_DEV`, `_PR_SKILL`, fake `mcp_upstream` |

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/action_policy.py` | UPDATE | resolver, `AliasInput`, `evaluate_all(aliases=)`, `ActionDecision.mcp_server` |
| `app/services/query_pipeline.py` | UPDATE | build `aliases` at 7c |
| `app/services/action_audit.py` | UPDATE | `_row_of` alias columns; `McpRecord` link fields; `record` routing |
| `app/db/database.py` | UPDATE | `insert_mcp_decision_linked`; shared candidate WHERE |
| `app/services/mcp_gateway.py` | UPDATE | remove `_correlate`; pass candidates/window/now |
| `tests/test_v1_alias.py` | CREATE | non-db resolver, 7c and row tests |
| `tests/test_mcp_correlation.py` | CREATE | `db` claim tests incl. concurrency |
| `tests/test_db_resilience_retry.py` | UPDATE | census (Design 8) |
| `tests/test_action_policy.py`, `tests/test_mcp_gateway.py` | UPDATE only if a signature/field guard trips | cite STORY-016 in any touched assertion |

## Tasks

### Task 1: Pure resolver and `evaluate_all(aliases=)`
- **File**: `app/services/action_policy.py`. **Implement**: Design 1-3. Update the module docstring (`:66` mentions step 7c). Resolver never reads settings.
- **Mirror**: `action_policy.py:181-198`, `:415-430`. **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_action_policy.py -m "not db"`

### Task 2: Atomic claim in the database layer
- **File**: `app/db/database.py`. **Implement**: Design 5. First prove the `LEFT JOIN ... WHERE true ON CONFLICT` shape parses on libSQL and SQLite (small probe in a scratch script, not committed); if libSQL rejects it, report instead of changing design.
- **Validate**: `tests/test_mcp_audit.py` (`-m "not db"` locally).

### Task 3: Audit plumbing
- **File**: `app/services/action_audit.py`. **Implement**: Design 3 (hash in `_row_of`), 6. `decision_rows` output for a non-alias decision must be unchanged (`test_record_without_mcp_builds_the_same_rows_as_decision_rows`, `tests/test_mcp_audit.py:157`).
- **Validate**: `tests/test_action_audit.py tests/test_mcp_audit.py -m "not db"`

### Task 4: Wire step 7c
- **File**: `app/services/query_pipeline.py:1643`. **Implement**: Design 4. With `MCP_ENABLED=false`, `mcp_config` is not called at all.
- **Validate**: `tests/test_v1_alias.py`, `tests/test_query_pipeline*.py -m "not db"` (grep names first).

### Task 5: Gateway
- **File**: `app/services/mcp_gateway.py`. **Implement**: Design 7. Update the `_correlate` seam comment and the module header if it mentions it.
- **Validate**: `tests/test_mcp_gateway.py -m "not db"`.

### Task 6: Tests and census
- `tests/test_v1_alias.py` (not db): DROP TABLE alias (`harness_postgres-staging__query`, `{"sql":"DROP TABLE t"}` style per the stub mapping) -> `deny`/`sql.ddl`, raw `tool_name` kept; SELECT -> released and `decision_rows` has `surface='v1'`, `mcp_server`, hash equal to the gateway's for the same arguments (key order shuffled, `{}`); two prefixes resolve -> `tool.malformed`; unresolved, invisible (role not holding the skill), Cline hash-truncated name -> `tool.unknown`/unchanged; `MCP_ENABLED=false` -> `aliases` is None (monkeypatch `evaluate_all` to capture kwargs) and decisions equal the no-alias call; unparseable arguments -> hash NULL; **no DB read at 7c** (monkeypatch `database.get_connection`/`_session`/`_unit_of_work` to raise during `evaluate_all(..., aliases=...)` and a `query_pipeline` 7c run).
- `tests/test_mcp_correlation.py` (`db`): match links `linked_decision_id` + `audit_id`; outside window (`now` injected) -> NULL/NULL; different args; deny row not linked; already-linked row not reused (second call -> NULL); unconfigured server / empty candidates -> NULL with one statement (count `_unit_of_work` calls); newest of two candidates wins; replay of the same `write_id` returns the original id; **concurrency**: two `threading.Thread`s each call `record(mcp=...)` for one `/v1` row, assert exactly one row has `linked_decision_id` set to it.
- Census edits per Design 8.
- **Validate** (one pytest call, locally `-m "not db"`): `tests/test_v1_alias.py tests/test_mcp_correlation.py tests/test_action_policy.py tests/test_action_audit.py tests/test_mcp_audit.py tests/test_mcp_gateway.py tests/test_db_resilience_retry.py -k "not slow"`, plus `tests/test_untouched_app.py`.

## End-to-End Tests
- [ ] `TestClient(app)` `/v1/chat/completions` with `MCP_ENABLED=true`, fake upstream tool call `harness_postgres-staging__query` DROP -> denial note, row `surface='v1'`.
- [ ] Gateway `tools/call` with the same arguments right after: row carries `linked_decision_id` and the `/v1` row's `audit_id` (CI, `db`).

## Validation
```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider -m "not db" tests/test_v1_alias.py tests/test_action_policy.py tests/test_action_audit.py tests/test_mcp_audit.py tests/test_mcp_gateway.py tests/test_untouched_app.py
```
`db` tests (correlation, census) run in CI; Docker is down locally.

## Acceptance Criteria -> Tasks -> Tests

| AC | Task(s) | Test that proves it |
|----|---------|---------------------|
| AC1 alias deny/allow + row columns | 1, 3, 4 | `tests/test_v1_alias.py::test_drop_table_alias_is_denied_sql_ddl`, `::test_select_alias_released_and_row_columns` |
| AC2 two prefixes / none / off | 1, 4 | `::test_two_resolving_prefixes_are_malformed`, `::test_unresolved_invisible_and_hashed_names_unchanged`, `::test_mcp_disabled_passes_no_aliases` |
| AC3 correlation, window, reuse | 2, 3, 5 | `tests/test_mcp_correlation.py` (match / window / args / deny / reuse / concurrency, `db`) |
| AC4 no DB read; both paths | 4 | `::test_alias_resolution_adds_no_database_read`; single call site cited in Design 4 |

## Open risks
- libSQL parse of `INSERT ... SELECT ... LEFT JOIN ... WHERE true ON CONFLICT` (Task 2 probe, CI-only locally).
- Alias visibility is config-only; the gateway also withholds over-length tools, so a withheld tool may alias-resolve but still be refused at the gateway (acceptable; same engine verdict).
- Hash stored on the row, not the decision (Design 3 deviation).
