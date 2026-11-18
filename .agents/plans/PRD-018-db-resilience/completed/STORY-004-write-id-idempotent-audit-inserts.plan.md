---
story: STORY-004
prd: PRD-018
slug: write-id-idempotent-audit-inserts
title: write_id columns, unique indexes, idempotent insert_audit_log and insert_action_decisions
type: ENHANCEMENT
complexity: MEDIUM
epic_branch: epic/PRD-018-db-resilience        # all stories commit here, no per-story branch
created: 2026-11-17
---

# Plan: Idempotent audit writes by write_id (PRD-018 F3, D4)

## Summary

Give `audit_logs` and `action_decisions` a nullable `write_id TEXT` column with a `UNIQUE` index, added through `_add_missing_columns()` (`action_decisions` becomes the fourth table on that path). `AuditLog` and `ActionDecisionRow` gain a defaulted `write_id: Optional[str] = None`, declared before `id` so the surrogate key stays the trailing field. A row that carries a `write_id` is written with `INSERT ... ON CONFLICT(write_id) DO NOTHING`, and its id is read back with `SELECT id ... WHERE write_id = ?` in the same transaction. A row without one keeps today's plain `INSERT` and `cursor.lastrowid`. The statement kind becomes a per-call expression, `_keyed_kind([...])`: `IDEMPOTENT` only when every row has a `write_id`, `NON_IDEMPOTENT` otherwise. The AST pin accepts that exact expression for these two functions only. `log_query` mints `write_id = uuid.uuid4().hex` next to its single timestamp stamp and still returns `int`. `action_audit.record()` mints one batch hex per call and keys row *i* as `"<batch>:<i>"`. `write_id` is mapped back on both read shapes (`SELECT *` and `_SUMMARY_SQL`'s `json_object`). It is not projected into any API response (`/audit`, `/audit/actions`) or the admin console.

## User Story

As a compliance admin
I want every audit row and action decision to carry a client-minted `write_id` with a unique index
So that a retried or drained write lands exactly once even when the first attempt did commit

## Story Reference

- Story file: `.agents/stories/PRD-018-db-resilience/STORY-004-write-id-idempotent-audit-inserts.md`
- PRD: `.agents/PRDs/PRD-018-db-resilience/PRD.md`, Sections 4 (:58-60), 6.3 rows 6/8/9 + "Why the unit is the whole block" (:172-201), 6.4 (:203-218), 6.8 journal shape (:283-295, consumer of `write_id`), 7 F3 (:351-352), 15 D4 (:552), Assumption (:603)
- Consumers: STORY-008 (journal serializes `write_id` from the dataclasses), STORY-009 (drain = keyed insert + `SELECT id` by `write_id`), STORY-010 (`AuditRef(audit_id, write_id)`, `audit_ref`, `chatcmpl-harness-ref-<write_id>`)
- STORY-003 artefacts reused: `_unit_of_work` (`app/db/database.py:1011-1117`), name→kind table and AST pin (`tests/test_db_resilience_retry.py:614-700`), `Fault`/`FaultScript`/`_FaultyClient` (`tests/db_faults.py:97-200`), `faulty_db` fixture (`tests/conftest.py:753-771`)

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT (story `type: technical`, `complexity: medium`) |
| Complexity | MEDIUM: ~80 lines of app code, one schema migration on two tables, ~10 existing census assertions re-registered, one new `db` test module |
| Systems Affected | `app/db/models.py`, `app/db/database.py`, `app/services/audit_logger.py`, `app/services/action_audit.py`; 7 existing test files; 1 new test file |
| Story | STORY-004 |
| PRD | PRD-018 |
| Epic Branch | `epic/PRD-018-db-resilience` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| (none) | `.agents/skills/` holds only `frontend-design` (UI aesthetics, `.agents/skills/frontend-design/SKILL.md:1-5`). This story has no UI, so it does not apply. Story `skills: []`. | n/a |

Repo rules from `SUBAGENT_BRIEF.md` that bind the tasks: `PYTHONUTF8=1` on every pytest; never two pytest processes at once; no full suite (CI runs it); modified pre-existing assertions carry a comment citing PRD-018 D4; classification and retry stay in `database.py`; `_translated()` untouched (D1); no new dependency (`uuid` is stdlib).

---

## Pre-flight findings (verified by the planner on 2026-11-17)

1. **Live-driver probe (de-risks PRD Assumption :603).** I ran `probe_write_id.py` (scratchpad) against `harness-libsql-dev` on a scratch table `zz_probe_story004_write_id`, then dropped it (confirmed gone). The table shape was a pre-existing row, then `ALTER TABLE ADD COLUMN write_id TEXT`, then `CREATE UNIQUE INDEX IF NOT EXISTS` run twice (the second run was a no-op). Results:
   - First keyed insert: `lastrowid=2 rowcount=1`. `SELECT id ... WHERE write_id='w1'` in the same transaction returns `(2,)`.
   - Replay after commit (`ON CONFLICT(write_id) DO NOTHING`): `lastrowid=0 rowcount=0`. `SELECT` returns `(2,)` and `COUNT(*)` is 1.
   - Conflict inside one transaction: `rowcount=0` and `lastrowid=4`, which is **stale**, left over from the previous insert. **So `lastrowid` must never be read on the keyed path.** The `SELECT` read-back the AC requires is the only correct id.
   - `NULL` write_ids: two inserts with `ON CONFLICT` plus one plain insert all landed (`lastrowid` 6, 7, 8). Four NULL rows coexist under the UNIQUE index.
   - `PRAGMA index_list` reports the index with `unique=1`, origin `c`.
   - Side effect worth knowing: under `AUTOINCREMENT` a conflicting `DO NOTHING` **consumes an id** (ids 3 and 5 were skipped). This is harmless. Nothing orders `audit_logs` or `action_decisions` by id contiguity, and PRD 6.8 already says drained ids are out of order. Tests must not assert contiguous ids.
2. **Field placement.** `AuditLog` (`app/db/models.py:411-473`) and `ActionDecisionRow` (`:577-605`) both keep `id` last by documented convention: `models.py:437-439` "so id stays the trailing field" and `:584-585` "`id` is last because insert_action_decisions() assigns it". `tests/test_db.py:2240-2267` pins this ("the surrogate key stays the trailing field"). No caller constructs either positionally through `id`. `grep "AuditLog(\""` finds nothing. Every `ActionDecisionRow(` call uses keywords (`app/services/action_audit.py:153`, `app/db/database.py:2922`, `tests/test_db_resilience_faults.py:73`, `tests/test_actions_view.py:154`, `tests/test_admin_actions.py:98`). **So `write_id` goes immediately before `id`.** This is the "trailing defaulted" field in the sense the house uses (see Deviations).
3. **No test mocks `insert_audit_log` / `insert_action_decisions` with an exact-entry equality.** The only references outside `test_db*.py` are `hasattr` guards (`tests/test_admin_state.py:374`, `tests/test_actions_view.py:593`) and real calls. `log_query`'s 12 call sites (`app/routers/query.py:118`, `app/services/query_pipeline.py:288 … 893`) use the int return and are untouched.
4. **`_SUMMARY_SQL`'s `json_object` must gain `'write_id', write_id`** if the mapper reads it. `database.py:1848-1850` states that `_row_to_audit_log` reads every key and a missing one is a `KeyError`. The tuple of `?` parameters is unchanged (no new `?`).
5. **`_Recording(fail_on=…)` in `tests/test_action_audit.py:130-147`** raises `StorageError("injected failure")`, which carries no `Hrana:` text. `_unit_of_work` passes it through unclassified (`database.py:1070-1072`), so a keyed `record()` does not retry it. `test_a_storage_failure_midway_through_record_writes_no_row` keeps passing unchanged. It counts `"INSERT INTO action_decisions"` statements, and the keyed SQL still starts with that text. The read-back `SELECT` does not match it.
6. **`scripts/migrate_to_turso.py`** builds `AuditLog` from source columns only through `denied_permission` (`:456-482`), and its read-back compares against `get_audit_log`. For any legacy source, `write_id` is NULL on both sides, so the script needs no change. Only its census test pins `_ddl_columns(CREATE_AUDIT_LOGS_TABLE)`.
7. **Stale line refs in the story.** Story Technical Notes cite `init_db()` at `:645-745` with reasons at `:673-679` and `:681-692`. STORY-002/003 moved them: `init_db()` is now `database.py:1120-1218`, the dedup-index reason is `:1148-1154`, and the `chat_messages`-pass reason is `:1156-1167`. The audit_logger range `:73-107` and `action_audit.py:174` → `:186-197` (`record`) are still accurate or near.

## Story-text deviations (for the orchestrator; all follow the code)

- **"trailing defaulted `write_id`"** → declared **before `id`**, with `id` still last (finding 2). Every positional construction keeps working, because no caller passes `id` positionally, and the house invariant pinned at `tests/test_db.py:2255-2267` holds.
- **"keeps today's plain insert"**: implemented literally. The unkeyed branch issues today's statement text with `write_id` in the column list and no `ON CONFLICT` suffix, and returns `cursor.lastrowid` exactly as today. The probe shows `ON CONFLICT` would be inert on NULL anyway. The literal form is kept so the AC is visible in the code.
- **`record()`'s batch uuid is fresh per call**, not the audit row's `write_id`. The PRD 6.8 journal example (`"decisions":[{"write_id":"7f3c…:0"}]` under `"write_id":"7f3c…"`) suggests deriving it from the audit ref. But `log_query` returns `int` until STORY-010, so `record()` has no audit `write_id` to derive from, and the AC says "one batch uuid per call". The index is **0-based** to match the PRD example. **Open for STORY-010:** whether `record()` should take the audit `write_id` as its batch prefix once it holds an `AuditRef`.

## write_id convention (one for the whole PRD)

**`uuid.uuid4().hex`**: 32 lowercase hex characters, no hyphens, minted by one helper, `audit_logger._new_write_id()`. Decision rows use `f"{batch}:{index}"` with `batch = _new_write_id()` and a 0-based `index`. Why hex and not `str(uuid4())`:
- It appears verbatim in client-facing strings in STORY-010: `audit_ref`, `X-Harness-Audit-Ref`, and `id: "chatcmpl-harness-ref-<write_id>"` (`CHAT_COMPLETION_ID_PREFIX = "chatcmpl-harness-"`, `app/models/v1_schemas.py:23`). The PRD's own examples are unhyphenated (`"audit_ref":"7f3c2a…"`, PRD :433).
- `"<batch>:<index>"` reads unambiguously with no hyphen inside the batch part.
- The `str(uuid.uuid4())` precedent (`database.py:2445`, `create_chat_session`) is a primary key exposed in `/chat` URLs and `schemas.py:41` documents its version-4 hyphenated form. It is a different identifier with its own contract, and nothing compares the two.
- One helper rather than two `uuid4()` calls is the guard against drift. `action_audit` already imports `_PREVIEW_LENGTH` and `_TIMESTAMP_FORMAT` from `audit_logger` for exactly this reason (`app/services/action_audit.py:52-54`). STORY-008/009/010 import `_new_write_id` from there too.

---

## Design

### D-1. Schema (`app/db/models.py`)

- `CREATE_AUDIT_LOGS_TABLE` (`:4-40`) gains `write_id TEXT` as the **last** column, after `ignored_params`. `AUDIT_LOGS_ADDED_COLUMNS` (`:61-136`) gains `"write_id": "TEXT"` last, with a comment in the house style: PRD-018 D4 (Section 6.4), client-minted idempotency key, nullable with no default and no backfill, every pre-PRD row reads NULL, SQLite `UNIQUE` admits any number of NULLs, indexed by `CREATE_AUDIT_LOGS_WRITE_ID_INDEX`. The header list at `:42-48` gains "PRD-018 STORY-004 adds write_id".
- New `CREATE_AUDIT_LOGS_WRITE_ID_INDEX = "CREATE UNIQUE INDEX IF NOT EXISTS idx_audit_logs_write_id ON audit_logs(write_id)"`, placed beside `CREATE_AUDIT_LOGS_DEDUP_INDEX` (`:138-151`). Its comment says UNIQUE on purpose (unlike the dedup index): the key is the replay's identity and must reject a second row. It must run **after** `_add_missing_columns()`, for the dedup index's reason.
- `CREATE_ACTION_DECISIONS_TABLE` (`:369-390`) gains `write_id TEXT` last, after `policy_digest`, with a trailing `-- "<batch hex>:<index>"; NULL for an unkeyed direct call` comment. The comment at `:368` ("A new table, so it arrives by CREATE alone and has no added-columns mapping") is replaced by the new mapping's rationale.
- New `ACTION_DECISIONS_ADDED_COLUMNS = {"write_id": "TEXT"}`, the fourth mapping. Its comment mirrors `CHAT_MESSAGES_ADDED_COLUMNS`' (`:314-335`): it is also declared in the CREATE, additive only, and NOT NULL would need a default.
- New `CREATE_ACTION_DECISIONS_WRITE_ID_INDEX = "CREATE UNIQUE INDEX IF NOT EXISTS idx_action_decisions_write_id ON action_decisions(write_id)"`, after `CREATE_ACTION_DECISIONS_AUDIT_INDEX` (`:399-403`).
- `AuditLog`: `write_id: Optional[str] = None` between `ignored_params` and `id`. The comment follows the PRD-015 one (`:467-472`): PRD-018 STORY-004 (D4); `insert_audit_log()` writes it and `_row_to_audit_log()` maps it back on both read shapes; `log_query` mints it once per call alongside the timestamp; never exposed on `GET /audit` (STORY-010 exposes `audit_ref`, a response field, not this one); declared after `ignored_params` so `id` stays the trailing field.
- `ActionDecisionRow`: `write_id: Optional[str] = None` between `policy_digest` and `id`. The docstring gains one sentence: `write_id` is `"<batch>:<index>"` from `record()`, and `None` for an unkeyed direct call.

### D-2. `init_db()` (`app/db/database.py:1199-1218`)

```python
conn.execute(CREATE_AUDIT_LOGS_TABLE)
_add_missing_columns(conn, "audit_logs", AUDIT_LOGS_ADDED_COLUMNS)
conn.execute(CREATE_AUDIT_LOGS_DEDUP_INDEX)
conn.execute(CREATE_AUDIT_LOGS_WRITE_ID_INDEX)      # after the pass: the column may be new
...
conn.execute(CREATE_ACTION_DECISIONS_TABLE)
_add_missing_columns(conn, "action_decisions", ACTION_DECISIONS_ADDED_COLUMNS)  # after the CREATE
conn.execute(CREATE_ACTION_DECISIONS_USER_TS_INDEX)
conn.execute(CREATE_ACTION_DECISIONS_AUDIT_INDEX)
conn.execute(CREATE_ACTION_DECISIONS_WRITE_ID_INDEX)
```
Add one docstring paragraph after the PRD-016 paragraph (`:1193-1197`): PRD-018 STORY-004 adds `write_id` to both tables. The `audit_logs` unique index sits after the pass for the dedup index's reason. The `action_decisions` pass sits after its CREATE for the `chat_messages` pass's reason, which makes `action_decisions` the fourth table on this path. In steady state the cost is one more `PRAGMA table_info` and two `CREATE INDEX IF NOT EXISTS` no-ops. Update the `_add_missing_columns` docstring sentence "Two calls rather than one loop" (`:1257-1263`) to name all four passes. Imports at `database.py:36-50` gain the three new constants.

### D-3. Per-call kind (`app/db/database.py`, beside `_retryable`, `:965-980`)

```python
def _keyed_kind(write_ids: Sequence[Optional[str]]) -> StatementKind:
    """The kind of an audit insert, chosen per call (PRD-018 D4, STORY-004).

    `IDEMPOTENT` only when every row carries a `write_id`: then a replay meets
    `ON CONFLICT(write_id) DO NOTHING` and reads the first attempt's id back.
    One row without a key (a test, a script) makes the whole unit
    `NON_IDEMPOTENT`, because a replay after `OUTCOME_UNKNOWN` would land that
    row twice. Pure. Empty input is `NON_IDEMPOTENT` (no caller passes it:
    `insert_action_decisions([])` returns before the unit).
    """
    if write_ids and all(write_id is not None for write_id in write_ids):
        return StatementKind.IDEMPOTENT
    return StatementKind.NON_IDEMPOTENT
```
The call sites are written **exactly** as follows, so the AST pin can match the unparsed text:
- `_unit_of_work("insert_audit_log", _keyed_kind([entry.write_id]), _op)`
- `_unit_of_work("insert_action_decisions", _keyed_kind([row.write_id for row in rows]), _op)`

The `StatementKind` docstring (`:769-780`) gains one line: "Declared per public function at its `_unit_of_work()` call; the two audit inserts choose it per call with `_keyed_kind()` (STORY-004)."

### D-4. Keyed inserts (`app/db/database.py`)

Two private row writers, so STORY-009's drain unit can call both inside one transaction without copying SQL:

```python
_ON_WRITE_ID_CONFLICT = " ON CONFLICT(write_id) DO NOTHING"

def _insert_audit_row(conn: _Connection, entry: AuditLog) -> int:
    """One audit row on `conn`; its id. Keyed by `entry.write_id` when present (D4).

    Keyed: `ON CONFLICT(write_id) DO NOTHING`, then `SELECT id ... WHERE
    write_id = ?` on the same connection, so the id is the row's whichever
    attempt inserted it. `lastrowid` is never read on this path: after a
    conflicting DO NOTHING the driver reports 0 or the previous insert's id
    (STORY-004 plan probe). No `RETURNING`: it returns no row on conflict
    (PRD 6.4). Unkeyed: today's plain INSERT and `lastrowid`.
    """
```
- The column list gains `write_id` last. It becomes 33 `?`. The value tuple gains `entry.write_id`.
- `sql = _INSERT_AUDIT_LOG_SQL + (_ON_WRITE_ID_CONFLICT if entry.write_id is not None else "")`. Hoist the existing triple-quoted INSERT into a module constant `_INSERT_AUDIT_LOG_SQL` beside the function. The text is unchanged apart from `write_id`.
- Keyed read-back: `row = conn.execute("SELECT id FROM audit_logs WHERE write_id = ?", (entry.write_id,)).fetchone()`. If `row is None`, raise `StorageError("audit_logs: no row for its write_id after the insert")`. This cannot happen, and failing closed beats a `TypeError`. It is not driver text, so it passes through `_unit_of_work` unclassified and is not retried. Then `return row["id"]`.
- `_insert_action_decision_rows(conn, rows) -> list[int]` does the same per row: `INSERT INTO action_decisions (… , write_id) VALUES (18 ?)`, plus the suffix and `SELECT id FROM action_decisions WHERE write_id = ?` when `row.write_id is not None`, else `lastrowid`. `ids` is created **inside** the function (the existing "a retry starts the batch over" rule, `database.py:2874-2877`). Per-row read-back keeps input order without depending on multi-row ordering, as `:2865-2869` argues. The cost is 2N statements for a keyed batch of N tool calls (N is small) and one extra round trip per audit row. PRD 6.4 accepts this.
- `insert_audit_log` / `insert_action_decisions` become `def _op(conn): return _insert_…(conn, entry|rows)` plus the D-3 call. Their docstrings replace the "`NON_IDEMPOTENT` until STORY-004" paragraph (`:1280-1282`, `:2874-2877`) with the D4 rule. **Keyed → `IDEMPOTENT`**: retried on every infrastructure class, and a replay of a landed commit returns the same id(s). **Unkeyed → `NON_IDEMPOTENT`** exactly as before. `insert_action_decisions` keeps its "whole block from row 1" sentence (PRD 6.3 :201).

### D-5. Read shapes (`app/db/database.py`)

- `_row_to_audit_log` (`:1409-1456`) gains `write_id=row["write_id"]`.
- `_SUMMARY_SQL` (`:1866-1899`) gains `'write_id', write_id` as the last `json_object` pair. Add a comment line beside the PRD-015 one at `:1848-1850`: a key, not a figure, so there is no `?` and the tuple is unchanged.
- `_row_to_action_decision_row` (`:2920-2941`) gains `write_id=row["write_id"]`.
- **Not exposed:** `app/routers/admin.py:50-91` (`AuditQueryEntry`, explicit projection) and `:153-…` (`_action_entry`), `chat_ui` `to_audit_row` / `to_action_rows` (explicit projections, `chat_ui/chat_ui/admin_formatting.py:14`). Nothing changes there. A new test pins the absence (Task 7).

### D-6. Minting (`app/services/audit_logger.py`, `app/services/action_audit.py`)

- `audit_logger.py`: `import uuid`. Add `def _new_write_id() -> str: return uuid.uuid4().hex`, with a docstring naming it the PRD-wide convention (PRD-018 D4; STORY-008/009/010 reuse it) and saying why it is hex (plan "write_id convention"). In `log_query`, add `write_id=_new_write_id()` to the `AuditLog(...)` with a comment: minted once per call, beside the one `timestamp` stamp, **before** the first attempt, so every retry (and, from STORY-008, the journal entry and the drain) carries the same pair (PRD 6.4 :217). The signature is unchanged and it still returns `int` (STORY-010 changes that).
- `action_audit.py`: import `_new_write_id` beside `_PREVIEW_LENGTH, _TIMESTAMP_FORMAT` (`:52-54`). `_row_of(...)` (`:145-171`) gains a trailing `write_id: Optional[str] = None` parameter passed to `ActionDecisionRow(write_id=write_id)`. The existing positional 5-argument caller `tests/test_action_audit.py:456` keeps working and stays unkeyed. In `record()` (`:174-197`):
  ```python
  batch = _new_write_id()
  rows = [
      _row_of(d, identity, timestamp, audit_id, session_id, f"{batch}:{index}")
      for index, d in enumerate(decisions)
  ]
  ```
  The module docstring's column list (`:9-27`) gains a `write_id` bullet: one batch hex per `record()` call, plus `:<index>` (0-based, input order), the key a replay is recognised by (PRD-018 D4). Mention it in the `record()` docstring too.

### D-7. Pin test: per-call kind for exactly two functions (`tests/test_db_resilience_retry.py:613-700`)

```python
_EXPECTED_KINDS = {
    # IDEMPOTENT when keyed (PRD-018 D4, STORY-004): every row carries a write_id.
    # The kind is chosen per call; _PER_CALL_KIND pins the exact expression.
    "insert_audit_log": K.IDEMPOTENT,  # rows 6, 8
    ...
    "insert_action_decisions": K.IDEMPOTENT,  # row 9
}
# PRD-018 D4 (STORY-004): the only two units whose kind is an expression, not a
# constant. The expression is pinned verbatim, so neither can drift to a constant
# NON_IDEMPOTENT/IDEMPOTENT, and no other function can join without editing this.
_PER_CALL_KIND = {
    "insert_audit_log": "_keyed_kind([entry.write_id])",
    "insert_action_decisions": "_keyed_kind([row.write_id for row in rows])",
}
```
`test_every_public_function_runs_one_unit_of_its_own_name_and_kind` changes one line, with a comment citing PRD-018 D4: `expected = _PER_CALL_KIND.get(name, f"StatementKind.{kind.name}")`, then `assert ast.unparse(second) == expected, name`. Add `assert set(_PER_CALL_KIND) == {"insert_audit_log", "insert_action_decisions"}` and `assert set(_PER_CALL_KIND) <= set(_EXPECTED_KINDS)`. The other 39 still require the literal `StatementKind.X`. `len(_EXPECTED_KINDS) == 41` is unchanged (no new public function: the helpers are private).

New pure tests in the same file:
- `test_keyed_kind_is_idempotent_only_when_every_row_is_keyed`. Parametrized: `["a"]` → IDEMPOTENT; `["a:0","a:1"]` → IDEMPOTENT; `[None]`, `["a:0", None]`, `[]` → NON_IDEMPOTENT.
- `test_the_expected_kind_of_a_keyed_unit_is_what_keyed_kind_returns`: `_keyed_kind(["x"]) is _EXPECTED_KINDS["insert_audit_log"]`. This ties the table's value to the expression.

---

## Census / inventory registrations (every one I found; exact edits)

Each modified assertion gets a `# PRD-018 STORY-004 (D4): …` comment.

| # | File:line | What it pins | Exact registration |
|---|---|---|---|
| 1 | `tests/test_audit_characterization.py:116-122` | `{fields(AuditLog)} == PINNED ∪ VOLATILE ∪ FIELDS_ADDED_SINCE` (`:236-238`) | Add `# PRD-018 STORY-004 (D4).` and `"write_id",` to `FIELDS_ADDED_SINCE`. The module rule (`:114-115`, `:34`) is that later stories add here and edit nothing above. `PINNED` stays at 22 and is not touched. |
| 2 | `tests/test_db.py:1048-1095` `test_schema_has_no_ip_or_location_column` | exact `PRAGMA table_info(audit_logs)` set | add `"write_id",` after `"ignored_params"`, commented `# PRD-018 STORY-004 (D4): the idempotency key.` ("write_id" contains no "ip"). |
| 3 | `tests/test_db.py:2255-2267` (in `test_audit_log_carries_session_id_without_breaking_construction`) | `names[-15:]` ends `"ignored_params", "id"` | `names[-16:]` with `"write_id", "id"` at the end; extend the comment list ("…and PRD-018 STORY-004 appended write_id"). The claim (id trails) is unchanged. |
| 4 | `tests/test_db.py:3187-3189` | `names[-10:] == [*_PRD013_COLUMNS, "ignored_params", "id"]` | `names[-11:] == [*_PRD013_COLUMNS, "ignored_params", "write_id", "id"]`; comment. |
| 5 | `tests/test_db.py:2995-3000` `test_the_prd013_columns_are_declared_last_and_in_order` | `[-9:-1]` of mapping and CREATE | `[-10:-2]` for both; docstring/comment: PRD-018 STORY-004 appended write_id after ignored_params. |
| 6 | `tests/test_db.py:3026-3032` `test_init_db_migrates_a_pre_prd013_database` | exact ALTER list | append `"ALTER TABLE audit_logs ADD COLUMN write_id TEXT"` after the ignored_params entry; comment. The fixture (`:656-…`) has no `action_decisions`, so the CREATE builds it with `write_id` and no second ALTER appears. |
| 7 | `tests/test_db.py:3047` | `len(columns) == 33` | `34`; comment. |
| 8 | `tests/test_db.py:3252-3258` `test_audit_logs_declares_ignored_params_in_both_places_last` | `[-1] == "ignored_params"` | `[-2]` for mapping and CREATE (the name is kept so `_DELIBERATELY_SUPERSEDED_TESTS` is not needed); comment: write_id now follows it. |
| 9 | `tests/test_db.py:3278-3280` `test_init_db_migrates_a_pre_prd015_database` | exact ALTER list `["…ignored_params TEXT"]` | append `"ALTER TABLE audit_logs ADD COLUMN write_id TEXT"`; comment. |
| 10 | `tests/test_db.py:3293` | `len(columns) == 33` | `34`; comment. |
| 11 | `tests/test_action_audit.py:67-88` `_COLUMNS` | exact `(name, notnull)` of `PRAGMA table_info(action_decisions)` (`:174`), and the `asdict(row) == raw` round trip (`:553`) | append `("write_id", 0),` with comment `# PRD-018 STORY-004 (D4): "<batch>:<index>", nullable`. `:553` then holds because the mapper maps `write_id` (D-5). |
| 12 | `tests/test_action_audit.py:229-233` `test_init_db_adds_action_decisions_to_a_pre_prd_database_and_alters_nothing` | exact `added` set from `sqlite_master` | add `("index", "idx_action_decisions_write_id")` and `("index", "idx_audit_logs_write_id")`. The legacy audit_logs is built from the current `CREATE_AUDIT_LOGS_TABLE`, so its column is already there and no ALTER happens; only its index is new. Comment. "Alters nothing" and the byte-identical check still hold. |
| 13 | `tests/test_action_audit.py:248` `test_init_db_creates_action_decisions_inside_the_one_bootstrap_session` | `sum("action_decisions" in sql) == 3  # table + 2 indexes` | `== 5  # table + PRAGMA table_info (the added-columns pass) + 3 indexes`; comment. On `uninitialized_db` the CREATE already has `write_id`, so there is no ALTER. |
| 14 | `tests/test_history_off_integration.py:288-291` | `asdict` equality of two rows minus `("id", "timestamp")` | `volatile = ("id", "timestamp", "write_id")`; comment: minted per `log_query` call, so it must differ like the other two (also extend the docstring sentence at `:267-268`). |
| 15 | `tests/test_migrate_to_turso_cli.py:165-180` | `_ddl_columns(CREATE_AUDIT_LOGS_TABLE)` exact list | append `"write_id",` after `"ignored_params"`, and comment line `# write_id: PRD-018 STORY-004 (D4)`. |

Checked and **needing no change**:
- `tests/test_db.py:84-100`, `:231-237`: subset/invariant loops over `AUDIT_LOGS_ADDED_COLUMNS`.
- `:4646-4684` stale-read convergence: the new action_decisions pass also converges through `_is_duplicate_column`. Optionally add an `ACTION_DECISIONS_ADDED_COLUMNS` loop beside the `chat_messages` one.
- `:4700-4720` and `:4805-4840` gated races: each thread now crosses the barrier four times, symmetric. Optionally update the "three" in the `:4816-4818` docstring to "four (`action_decisions` joined in PRD-018 STORY-004)".
- `:1873-1891`: summary statement count is unaffected.
- `tests/test_two_instance_smoke.py:237-251`: instance-vs-instance schema equality, symmetric. `:1891-1898` is chat_messages only.
- `tests/test_audit_logger.py:100-117`: `vars(fetched)`. "write_id" has no "ip"/"location", and a hex value has no "ip address".
- `tests/test_admin_models.py`, `tests/test_admin_formatting.py:516`, `tests/test_actions_view.py:79,208`: `chat_ui` projections, untouched.
- `tests/test_pii_dedup_isolation.py:383-409`: `hash_prompt` census, and no new call site.
- `tests/test_db_resilience_faults.py:207-220`: its rows are unkeyed. It stays `NON_IDEMPOTENT` and is retried on `DEAD_STREAM`@execute exactly as now.
- `tests/test_action_audit.py:455-478`: see finding 5.
- `tests/e2e/_live.py:41-54`: `asdict` dump gains a key, and no exact-key consumer exists.

---

## Patterns to Follow

### Added column with its rationale comment, declared in both places
```python
# SOURCE: app/db/models.py:129-135
    # PRD-015 (Section 7.3, D3): the sorted, comma-joined *names* of the
    # top-level request keys ... Nullable with no default on purpose, like
    # dedup_key: NULL is "nothing ignored", which is true of every `/query`
    # and chat row and of every row written before PRD-015, so it is never backfilled.
    "ignored_params": "TEXT",
```

### Index after the pass that may add its column
```python
# SOURCE: app/db/database.py:1204-1206
        conn.execute(CREATE_AUDIT_LOGS_TABLE)
        _add_missing_columns(conn, "audit_logs", AUDIT_LOGS_ADDED_COLUMNS)
        conn.execute(CREATE_AUDIT_LOGS_DEDUP_INDEX)
```

### Unit body (re-runnable, accumulators inside)
```python
# SOURCE: app/db/database.py:2882-2917
    def _op(conn: _Connection) -> list[int]:
        ids: list[int] = []
        for row in rows:
            cursor = conn.execute(...)
            ids.append(cursor.lastrowid)
        return ids

    return _unit_of_work("insert_action_decisions", StatementKind.NON_IDEMPOTENT, _op)
```

### Value minted before the unit (same on every attempt)
```python
# SOURCE: app/db/database.py:2445 (create_chat_session) and app/services/audit_logger.py:73-75
    session_id = str(uuid.uuid4())
    ...
    entry = AuditLog(
        timestamp=datetime.now(timezone.utc).strftime(_TIMESTAMP_FORMAT),
```

### Fault test, the landed case (commit forwarded, answer lost)
```python
# SOURCE: tests/test_db_resilience_faults.py:223-235
def test_a_session_created_by_a_lost_commit_is_returned_not_raised(faulty_db):
    _seed_user()
    faulty_db.add(Fault(NAMESPACE_SHUTDOWN_503, op="commit", when="after"))
    session_id = create_chat_session("dana", "hello")
    with get_connection() as conn:
        rows = conn.execute("SELECT session_id, user_id FROM chat_sessions").fetchall()
    assert [(r["session_id"], r["user_id"]) for r in rows] == [(session_id, "dana")]
```

### Refused-retry pin (NON_IDEMPOTENT on a landed OUTCOME_UNKNOWN)
```python
# SOURCE: tests/test_db_resilience_faults.py:176-186
    faulty_db.add(Fault(NAMESPACE_SHUTDOWN_503, op="commit", when="after"))
    with pytest.raises(StorageError):
        admit_usage("u-landed")
    assert _usage_row("u-landed")["requests"] == 1
    assert faulty_db.forwarded("INSERT INTO USAGE_DAILY") == 1
    assert not [r for r in _retry_records(caplog) if "retry op=" in r.getMessage()]
```

### Session recorder for init_db ordering (no import from test_db.py)
```python
# SOURCE: tests/test_action_audit.py:130-165 (_Recording + `sessions` fixture)
```

### Error handling: our own StorageError passes through unclassified
```python
# SOURCE: app/db/database.py:1070-1072
        except StorageError as exc:
            if _DRIVER_ERROR not in str(exc):
                raise
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/db/models.py` | UPDATE | `write_id` in both CREATEs, `AUDIT_LOGS_ADDED_COLUMNS`, new `ACTION_DECISIONS_ADDED_COLUMNS`, two UNIQUE index constants, two dataclass fields |
| `app/db/database.py` | UPDATE | imports; `init_db()` passes and indexes; `_keyed_kind`; `_INSERT_AUDIT_LOG_SQL`, `_ON_WRITE_ID_CONFLICT`, `_insert_audit_row`, `_insert_action_decision_rows`; both inserts' kinds and docstrings; both mappers; `_SUMMARY_SQL` key |
| `app/services/audit_logger.py` | UPDATE | `_new_write_id()`; `log_query` mints `write_id` |
| `app/services/action_audit.py` | UPDATE | `_row_of(..., write_id=None)`; `record()` mints one batch; docstrings |
| `tests/test_db_resilience_write_id.py` | CREATE | `db` + pure tests for every AC (Task 7) |
| `tests/test_db_resilience_retry.py` | UPDATE | kinds table, `_PER_CALL_KIND`, pin line, `_keyed_kind` tests (D-7) |
| `tests/test_db.py` | UPDATE | census rows 2-10 |
| `tests/test_action_audit.py` | UPDATE | census rows 11-13 |
| `tests/test_audit_characterization.py` | UPDATE | census row 1 |
| `tests/test_history_off_integration.py` | UPDATE | census row 14 |
| `tests/test_migrate_to_turso_cli.py` | UPDATE | census row 15 |

No renamed or removed test, so `_DELIBERATELY_SUPERSEDED_TESTS` is untouched. No docs in this story: STORY-014 owns docs. No API, router or `chat_ui` change.

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: Schema constants and dataclass fields
- **File**: `app/db/models.py`
- **Action**: UPDATE
- **Implement**: D-1 exactly. `write_id` is last in both CREATEs and last in `AUDIT_LOGS_ADDED_COLUMNS`. New `ACTION_DECISIONS_ADDED_COLUMNS`, `CREATE_AUDIT_LOGS_WRITE_ID_INDEX`, `CREATE_ACTION_DECISIONS_WRITE_ID_INDEX`. Dataclass fields go before `id`.
- **Mirror**: `app/db/models.py:129-151` (column comment and index constant), `:314-335` (a second-table mapping), `:467-473` (dataclass field comment)
- **Validate**: `.venv/Scripts/python -c "from app.db.models import AuditLog, ActionDecisionRow as R; import dataclasses as d; print([f.name for f in d.fields(AuditLog)][-2:], [f.name for f in d.fields(R)][-2:])"` → `['write_id', 'id'] ['write_id', 'id']`

### Task 2: `init_db()` passes and indexes
- **File**: `app/db/database.py`
- **Action**: UPDATE
- **Implement**: D-2 (imports, the block at `:1203-1218`, docstring paragraph, `_add_missing_columns` docstring sentence).
- **Mirror**: `app/db/database.py:1205-1206`, `:1212-1214`
- **Validate**: `.venv/Scripts/python -c "from app.main import app; print('OK')"`

### Task 3: `_keyed_kind` and the keyed inserts
- **File**: `app/db/database.py`
- **Action**: UPDATE
- **Implement**: D-3 and D-4. Write the two `_unit_of_work(...)` calls character-for-character as in D-3. `_translated()` and `_unit_of_work` are untouched.
- **Mirror**: `app/db/database.py:1285-1338`, `:2879-2917`
- **Validate**: import check as Task 2

### Task 4: Read shapes
- **File**: `app/db/database.py`
- **Action**: UPDATE
- **Implement**: D-5 (two mappers, the `_SUMMARY_SQL` key and its comment line).
- **Mirror**: `app/db/database.py:1455`, `:1848-1850`, `:1899`
- **Validate**: import check

### Task 5: Minting
- **Files**: `app/services/audit_logger.py`, `app/services/action_audit.py`
- **Action**: UPDATE
- **Implement**: D-6. `log_query` keeps its signature and its `-> int`.
- **Mirror**: `app/services/action_audit.py:52-54` (cross-import of audit_logger privates)
- **Validate**: import check

### Task 6: Re-register the censuses
- **Files**: `tests/test_db_resilience_retry.py` (D-7), `tests/test_db.py`, `tests/test_action_audit.py`, `tests/test_audit_characterization.py`, `tests/test_history_off_integration.py`, `tests/test_migrate_to_turso_cli.py`
- **Action**: UPDATE
- **Implement**: the census table rows 1-15 and D-7, each with a `PRD-018 STORY-004 (D4)` comment. Optionally make the two docstring/loop touch-ups listed under "needing no change".
- **Validate**: Task 8

### Task 7: `tests/test_db_resilience_write_id.py` (new)
- **File**: `tests/test_db_resilience_write_id.py`
- **Action**: CREATE
- **Implement**: Module header in the `tests/test_db_resilience_faults.py:1-14` style: PRD-018 STORY-004 (D4, Section 6.4), `db` by fixture closure, so there is no `_DB_NODEIDS` entry. Prologue `os.environ.setdefault(...)` as `:16-19`. The tests, by AC:
  - **AC 1 (schema / migration)**:
    - `test_a_fresh_database_has_both_write_id_columns_nullable_text` (`temp_db`): `PRAGMA table_info` type `TEXT`, `notnull 0`, `dflt_value None` on both tables.
    - `test_both_write_id_indexes_are_unique_on_the_one_column` (`temp_db`): `PRAGMA index_list` `unique == 1`, and `PRAGMA index_info` returns `["write_id"]` for `idx_audit_logs_write_id` and `idx_action_decisions_write_id`.
    - `test_init_db_migrates_a_pre_prd018_database` (`uninitialized_db`, `db_connect`): build legacy tables from `CREATE_AUDIT_LOGS_TABLE` / `CREATE_ACTION_DECISIONS_TABLE` with the `write_id` line removed. Assert the removal actually changed the text. Add the other CREATEs and the existing indexes, and seed one row in each. Record statements (a `_Recording`-style proxy over `database.get_connection`, `tests/test_action_audit.py:130-165`). `init_db()`. Then:
      - The ALTERs are exactly `["ALTER TABLE audit_logs ADD COLUMN write_id TEXT", "ALTER TABLE action_decisions ADD COLUMN write_id TEXT"]`, and no `UPDATE`/`INSERT`/`DELETE` was issued.
      - Both seeded rows read `write_id IS NULL`.
      - Both indexes exist.
      - A second `init_db()` issues no `ALTER` (re-run no-op).
    - `test_the_write_id_indexes_follow_their_columns_and_tables`: from the same recording, `CREATE_AUDIT_LOGS_WRITE_ID_INDEX` comes after the audit_logs ALTER. The `PRAGMA table_info(action_decisions)` comes after `CREATE_ACTION_DECISIONS_TABLE` and before `CREATE_ACTION_DECISIONS_WRITE_ID_INDEX`.
    - `test_two_null_write_ids_coexist_in_each_table` (`temp_db`): two unkeyed `insert_audit_log` and one 2-row unkeyed `insert_action_decisions` all land.
    - Pure: `test_action_decisions_added_columns_are_declared_in_the_create`, and the NOT-NULL-needs-DEFAULT twin over `ACTION_DECISIONS_ADDED_COLUMNS`. These mirror `tests/test_db.py:2300-2328`.
  - **AC 2**:
    - `test_existing_constructions_still_work_and_default_write_id_to_none` (pure): `AuditLog(timestamp=…, user_id=…, prompt_hash=…)` and a 17-positional-argument `ActionDecisionRow(...)` both have `.write_id is None`. `id` stays the last field of each.
  - **AC 3**:
    - `test_the_same_keyed_entry_twice_is_one_row_and_one_id` (`temp_db`): `wid = _new_write_id()`. `insert_audit_log(entry)` twice returns equal ids. `SELECT COUNT(*) … WHERE write_id = ?` is 1.
    - `test_a_landed_commit_whose_answer_is_lost_is_replayed_to_the_same_row` (`faulty_db`): `Fault(NAMESPACE_SHUTDOWN_503, op="commit", when="after")`. The keyed insert returns an id, the count is 1, `faulty_db.forwarded("INSERT INTO AUDIT_LOGS") == 2`, and the returned id equals `SELECT id … WHERE write_id = ?`. This is the honest landed `OUTCOME_UNKNOWN` (`tests/db_faults.py:24`).
    - `test_a_lost_execute_answer_is_retried_and_lands_once` (`faulty_db`): `Fault(NAMESPACE_SHUTDOWN_503, sql="INSERT INTO AUDIT_LOGS", when="after")`. This is the AC's literal "after forwarding the first INSERT" case. Exactly one row, the returned id matches, and forwarded is 2.
  - **AC 4**:
    - `test_a_dead_stream_on_row_k_replays_the_keyed_batch_from_row_one` (`faulty_db`), parametrized k ∈ {1, 2, 3}: rows `f"{batch}:{i}"` and `Fault(INVALID_BATON, sql="INSERT INTO ACTION_DECISIONS", nth=k)`. N=3 rows stored, `forwarded("INSERT INTO ACTION_DECISIONS") == (k - 1) + 3`, returned ids == `SELECT id … ORDER BY id` and in input order by `tool_call_id`.
    - `test_a_landed_keyed_batch_replayed_after_a_lost_commit_stays_n_rows` (`faulty_db`): commit/after 503. 3 rows, not 6, and returned ids equal the stored ids in input order.
    - `test_on_conflict_do_nothing_on_this_driver` (`temp_db`, raw `get_connection`): in one transaction, insert the same `write_id` twice into `action_decisions` with `ON CONFLICT(write_id) DO NOTHING`, then `SELECT id … WHERE write_id = ?`. One row, the first id. Repeat after commit. This is the PRD 6.4 Assumption verified as a `db` test, and the docstring cites the planner probe, including that `lastrowid` after a conflict is 0 or stale.
  - **AC 5**:
    - `test_log_query_mints_a_hex_write_id_and_still_returns_int` (`temp_db`): `isinstance(audit_id, int)`, and the raw row's `write_id` matches `^[0-9a-f]{32}$`. Two calls give two distinct ids.
    - `test_log_query_keeps_one_write_id_and_timestamp_across_a_retry` (`faulty_db`): commit/after 503 on `log_query(...)`. Expect `forwarded("INSERT INTO AUDIT_LOGS") == 2`, exactly one row for that user, and the returned id equal to the stored id. A second row would exist if the retry had minted a new key, so the single row proves the key was the same. `FaultScript` does not record parameters, so do not add parameter capture to the harness.
    - `test_record_keys_its_rows_batch_colon_index` (`temp_db`): `record(...)` of 3 decisions (reuse a `_three()`-style helper built from `action_policy`, or construct `ActionDecision`s as `tests/test_action_audit.py` does). The `write_id`s are `f"{b}:0"`, `f"{b}:1"`, `f"{b}:2"`, share one `b` matching `^[0-9a-f]{32}$`, and a second `record()` gets a different `b`.
    - `test_an_unkeyed_audit_row_is_not_replayed_after_a_landed_commit` (`faulty_db`, `caplog`): commit/after 503 raises `StorageError`. The count for that user is 1, forwarded INSERT is 1, and one `retry refused op=insert_audit_log … kind=non_idempotent` WARNING appears.
    - `test_an_unkeyed_batch_is_not_replayed_after_a_landed_commit` (`faulty_db`): the same for `insert_action_decisions`. N rows, not 2N.
  - **Exposure pin (story Technical Notes, default "not exposed")**:
    - `test_write_id_is_not_projected_into_api_responses` (pure): `"write_id" not in AuditQueryEntry.model_fields` and `not in ActionDecisionEntry.model_fields` (`app/models/schemas.py:187`, `:279`). The comment says STORY-010 adds `audit_ref`, a response field, and still not `write_id`.
- **Mirror**: `tests/test_db_resilience_faults.py:1-95` (header, imports, `_decision` helper), `:176-235` (fault tests)
- **Validate**: Task 8

### Task 8: Targeted regression run (one pytest process; never two at once; target under ~10 minutes)
Two runs, **sequential** (the second starts after the first exits):
```bash
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q \
  tests/test_db_resilience_write_id.py tests/test_db_resilience_retry.py tests/test_db_resilience_faults.py \
  tests/test_action_audit.py tests/test_audit_logger.py tests/test_audit_characterization.py \
  tests/test_history_off_integration.py tests/test_migrate_to_turso_cli.py tests/test_admin_actions.py \
  tests/test_untouched_app.py

PYTHONUTF8=1 .venv/Scripts/python -m pytest -q tests/test_db.py \
  -k "init_db or migrat or schema or added_column or declared or carries or audit_log or summary or batched or ignored_params or prd013 or dedup or add_missing or two_init_db"
```
Record exact pass/fail/skip counts for each. If many `db` tests error at fixture setup, `docker restart harness-libsql-dev` and rerun. Full suite: GitHub CI on push (user decision).

---

## End-to-End Tests

- [ ] `.venv/Scripts/python -c "from app.main import app; print('OK')"` prints OK. The lifespan's `init_db()` path is exercised by the `db` tests against the dev server.
- [ ] On the dev server, after `init_db()`: `PRAGMA index_list(audit_logs)` and `PRAGMA index_list(action_decisions)` each show their `*_write_id` index with `unique=1`.
- [ ] A `log_query(...)` row has a 32-hex `write_id`. A `record(...)` batch has `<hex>:0..N-1`.

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q <Task 8 selection>
PYTHONIOENCODING=utf-8 .venv/Scripts/python .agents/scripts/gen_index.py PRD-018   # after frontmatter changes: "errors: none"
```

---

## Risks + mitigations

| Risk | Mitigation |
|---|---|
| A census I missed goes red in CI | The census table was built from a grep over `fields(AuditLog)`, `asdict`, `table_info`, `sqlite_master`, `_ddl_columns`, `[-N:]` slices and exact ALTER lists. CI runs the full suite on push, and any miss is a one-line registration of the same kind. |
| `_SUMMARY_SQL` forgets the key → `KeyError` on the admin summary | D-5 adds it. The existing both-shapes tests (`tests/test_db.py:940-968`, `:3325-3344`) assert `snapshot.rows == list_audit_logs()`, which fails if the key is missing. |
| Using `lastrowid` after a conflict | It is forbidden on the keyed path in code and in the docstring. The probe shows it is 0 or stale, and the replay tests compare returned ids against the stored ids. |
| `AUTOINCREMENT` gaps after a conflicting replay | Harmless (finding 1). Tests compare against `SELECT`ed ids, never against `previous + 1`. |
| One extra round trip per audit row (the read-back `SELECT`) | Accepted by PRD 6.4, which rejects `RETURNING` under DO NOTHING. A `rowcount == 1 → lastrowid` shortcut was rejected: it is unverified across replays, and the AC mandates the read-back. |
| A mixed batch (some rows keyed, some not) | Its kind is `NON_IDEMPOTENT` (safe). Each row takes its own SQL branch, so nothing breaks. No production caller makes one: `record()` keys every row. |
| Later stories reshape the minting | `_new_write_id()` is the single convention point. The `record()` batch prefix question is flagged for STORY-010 (Deviations). |

## Acceptance Criteria

(Copied from story `STORY-004`)

- [ ] AC 1: `init_db()` adds nullable, no-default, no-backfill `write_id TEXT` to `audit_logs` and `action_decisions` through `_add_missing_columns()`, with UNIQUE `idx_audit_logs_write_id` and `idx_action_decisions_write_id`. `action_decisions` is the fourth added-columns table. Pre-PRD rows read NULL, two NULL rows coexist, and a re-run is a no-op. *(Task 1-2, Task 7 AC 1 tests, census rows 6-13)*
- [ ] AC 2: `AuditLog` / `ActionDecisionRow` constructed as today still work, and the defaulted `write_id` is `None`. *(Task 1, Task 7 AC 2 test)*
- [ ] AC 3: a keyed `insert_audit_log` run twice, or replayed after a forwarded INSERT / landed commit with `OUTCOME_UNKNOWN`, gives one row and the same id via `SELECT id … WHERE write_id = ?` in the same transaction, using `ON CONFLICT(write_id) DO NOTHING` and no `RETURNING`. *(Task 3, Task 7 AC 3 tests)*
- [ ] AC 4: a keyed batch hit by `DEAD_STREAM` on row k is replayed from row 1, gives exactly N rows, and returns ids in input order. `ON CONFLICT … DO NOTHING` is verified on this driver by a `db` test. *(Task 3, Task 7 AC 4 tests)*
- [ ] AC 5: `log_query` mints `uuid4().hex` beside the single timestamp and still returns `int`. `record()` mints one batch per call. Unkeyed calls keep the plain insert, run as `NON_IDEMPOTENT`, and are pinned by a test. *(Task 3, 5, D-7, Task 7 AC 5 tests)*
- [ ] All tasks completed
- [ ] Backend imports without error (`from app.main import app`)
- [ ] Follows existing patterns (comments cite PRD-018 D4; `_translated()` untouched; no new dependency)
