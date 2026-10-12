---
story: STORY-002
prd: PRD-013
slug: audit-columns
title: "Eight additive audit columns: convergence, AuditLog, writer and both read shapes"
type: ENHANCEMENT
complexity: MEDIUM
epic_branch: epic/PRD-013-audit-and-usage-limits        # all stories commit here, no per-story branch
created: 2026-10-12
---

# Plan: Eight additive audit columns: convergence, AuditLog, writer and both read shapes

## Summary

This story gives `audit_logs` eight new columns and carries them through storage, and nothing else. No caller sets a non-default value yet: `log_query` is untouched until STORY-005.

- **Schema.** `ingress`, `message_count`, `input_tokens`, `output_tokens`, `streamed`, `has_tool_calls`, `conversation_key` and `limit_exceeded` are declared in both `CREATE_AUDIT_LOGS_TABLE` and `AUDIT_LOGS_ADDED_COLUMNS`, after `profile`. Six are nullable with no default. `streamed` and `has_tool_calls` are `INTEGER NOT NULL DEFAULT 0`.
- **Convergence.** `init_db()` gets no new code. The columns ride the existing `_add_missing_columns(conn, "audit_logs", AUDIT_LOGS_ADDED_COLUMNS)` call. No index.
- **Dataclass.** `AuditLog` gains eight fields after `profile`, so `id` stays last. Defaults are `None` for the six and `False` for the two flags.
- **Writer and both read shapes.** `insert_audit_log` writes all eight. `_row_to_audit_log` maps them back, with `bool(...)` on the two flags. The `json_object(...)` in `_SUMMARY_SQL` lists the eight keys, so the batched read returns the same rows as the `SELECT *` read.
- **Tests.** A new section in `tests/test_db.py` covers the declaration, the fresh schema, convergence of a pre-PRD-013 database, defaults, the round trip and the batched read. `tests/test_audit_characterization.py` gets its eight names in `FIELDS_ADDED_SINCE` and one added test.

**One acceptance criterion cannot be met as written, and the plan says how it is handled (F-2).** AC 5 says every existing test passes "with no assertion changed". Three existing tests pin the full list of audit columns or `AuditLog` fields, and each must gain the eight names. The plan treats those three inventories as the only assertions that change, each with a comment citing PRD-013, which is what PRD-012 STORY-011 did and what PRD Section 11 *Quality indicators* provides for.

**Nothing below was run.** Docker Desktop was not running when this plan was written, so the libSQL dev container was unreachable (F-7). Expected values come from reading the code.

## User Story

As a compliance admin
I want the audit table able to hold the ingress, size, cost and grouping of a request
So that later stories have somewhere to record them and existing databases converge without a migration step

## Story Reference

- Story file: `.agents/stories/PRD-013-audit-and-usage-limits/STORY-002-audit-columns.md`
- PRD: `.agents/PRDs/PRD-013-audit-and-usage-limits/PRD.md` (Sections 4 *Audit columns*, 6.2, 6.12, 7/F2, 11 *Audit* and *Quality indicators*)

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT (story type `technical`) |
| Complexity | MEDIUM |
| Systems Affected | audit schema and convergence (`app/db/models.py`), writer, mapper and summary snapshot (`app/db/database.py`), three test modules |
| Story | STORY-002 |
| PRD | PRD-013 |
| Epic Branch | `epic/PRD-013-audit-and-usage-limits` (commit directly on this branch; it exists and is checked out, HEAD `9aea08f`) |
| Depends on | STORY-001 (done, `126f0da`) |
| Blocks | STORY-005, STORY-011 |

---

## Skills In Use

None. `.agents/skills/` holds one skill, `frontend-design`. The story sets `skills: []` and says "No UI surface changes in this story".

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | — | — |

---

## Findings from Exploration

Read on `epic/PRD-013-audit-and-usage-limits` @ `9aea08f`.

### F-1: Six places carry an audit column, and the story names all six

| # | Place | File:Lines | Today |
|---|---|---|---|
| 1 | `CREATE_AUDIT_LOGS_TABLE` | `app/db/models.py:4-31` | 24 columns, `profile TEXT` last |
| 2 | `AUDIT_LOGS_ADDED_COLUMNS` | `app/db/models.py:49-82` | 10 entries, `profile` last |
| 3 | `AuditLog` | `app/db/models.py:232-275` | 24 fields, `profile` then `id` |
| 4 | `insert_audit_log` | `app/db/database.py:765-804` | 23 columns, 23 placeholders, 23 values |
| 5 | `_row_to_audit_log` | `app/db/database.py:845-883` | 24 named reads |
| 6 | `json_object(...)` in `_SUMMARY_SQL` | `app/db/database.py:1201-1225` | 24 key/value pairs |

`get_audit_log` and `list_audit_logs` use `SELECT *` (`database.py:889`, `:913`, `:921`), so they need no change. `init_db()` (`database.py:696-706`) needs none either.

`json_object` goes from 48 arguments to 64. SQLite's default limit on function arguments is 100 or more, so this fits. The batched-read test in Task 5 proves it against the real server.

### F-2: AC 5 conflicts with three pinned inventories

AC 5: "STORY-001's characterization and every existing test pass with no assertion changed." Three existing assertions enumerate every audit column or field and fail the moment eight are added:

| Test | File:Lines | What it pins |
|---|---|---|
| `test_schema_has_no_ip_or_location_column` | `tests/test_db.py:929-963` | `set(columns) == expected`, the exact 24-column set |
| `test_audit_log_carries_session_id_without_breaking_construction` | `tests/test_db.py:2103-2110` | `names[-6:] == [..., "profile", "id"]` |
| `test_dest_columns_match_the_ddl` | `tests/test_migrate_to_turso_cli.py:165-175` | `_ddl_columns(CREATE_AUDIT_LOGS_TABLE) == [...]`, the exact 24-name list |

There is no way to add a column and leave these untouched. Each prior column story edited the same three: PRD-012 STORY-011's report records "The only existing assertions changed are pinned field, column and key lists". PRD-013 Section 11 expects it too: "Every modified pre-existing test carries a comment citing PRD-013 and its decision".

**Consequence.** These three assertions are extended and nothing else in any existing test changes. Each edit adds the eight names with a PRD-013 comment, in the style already used at those lines. The report states this against AC 5 in the words PRD-012 STORY-011 used. No name contains `ip` or `location`, so the second assertion of the first test (`tests/test_db.py:963`) still holds unchanged.

The four files PRD Section 11 freezes by name (`test_query_outcomes_regression.py`, `test_chat_outcomes_regression.py`, `test_duplicate_scope.py`, `test_pii_characterization.py`) are not touched.

### F-3: The characterization module has one sanctioned extension point

`tests/test_audit_characterization.py:114` is `FIELDS_ADDED_SINCE: frozenset[str] = frozenset()`. The guard at lines 221-230 requires every `AuditLog` field to be pinned, volatile or in that set, so it fails as soon as Task 1 lands. STORY-001's report (line 113) says what to do: "add the eight column names to `FIELDS_ADDED_SINCE` and add assertions for them. … No expected row in `ARM_CASES` is edited."

`ARM_CASES` compares a projection over `PINNED_FIELDS` (line 160), so the 12 arm rows are unaffected by new fields.

**What the added assertions can say.** The module's rule is that a later story may not change an assertion written there. STORY-005 will make every arm write `message_count` and `conversation_key`, so pinning those two as `None` now would force STORY-005 to break the rule. The other six stay at their defaults for rows written through `_drive` for the rest of this PRD:

- `ingress`: `_drive` passes none, and STORY-001's report says its rows "will record `NULL` there".
- `input_tokens`, `output_tokens`: the stub builds `OpenRouterResult` with three fields.
- `streamed`: `_drive` passes none; the default is `False`.
- `has_tool_calls`: `False` until PRD-016.
- `limit_exceeded`: set only by the usage-limit arm, which is a thirteenth arm.

The added test pins those six on every arm and leaves the other two out, with a comment saying why.

### F-4: The migration script reads the schema from the DDL

`scripts/migrate_to_turso.py:112-143` derives the column list and the defaults from `CREATE_AUDIT_LOGS_TABLE`. The eight new declarations have no comma and no parenthesis, so `_ddl_columns` still splits correctly, and `_ddl_defaults` reads `DEFAULT 0` as `0` and the six others as `None`. The script needs no change. Its test's pinned list does (F-2).

`_audit_log_from_source` (`scripts/migrate_to_turso.py:457-483`) builds an `AuditLog` from the first 19 fields only. That already omits `session_id` through `profile`, so a source file carrying non-default values in any later column would fail the read-back check. This predates the story and is not changed here. The report notes it for STORY-018.

### F-5: `tests/test_migrate_to_turso_cli.py::_make_source` iterates the mapping

`_make_source` (lines 96-111) builds a legacy file by running `ALTER TABLE ... ADD COLUMN` for every entry in `AUDIT_LOGS_ADDED_COLUMNS` against stdlib `sqlite3`. The two `NOT NULL DEFAULT 0` entries are valid there for the same reason they are valid in `init_db()`. No edit is needed, and the module's other tests exercise the new entries for free.

### F-6: Existing tests that cover the new entries without being edited

- `test_added_columns_declaring_not_null_also_declare_a_default` (`tests/test_db.py:80-96`) covers the two `NOT NULL` entries.
- `test_every_added_column_is_also_declared_in_the_create` (`tests/test_db.py:2079-2085`) covers the both-places rule.
- `test_init_db_issues_no_alter_when_schema_is_current` (`tests/test_db.py:130-200`) is AC 3 and passes unchanged, because `temp_db` builds the table from the `CREATE` with all 32 columns.
- The six race and convergence tests at `tests/test_db.py:3796-4095` iterate the mapping, so each now converges 18 audit columns.
- `tests/test_history_off_integration.py:275-293` compares two rows with `dataclasses.asdict`, which stays equal.

### F-7: Environment

- Python: the virtual environment at `C:\Users\tobip\.venvs\harness-ai` exists (STORY-001 report, *Environment*). There is none in the repo and `python` on PATH is the Windows Store alias.
- **Docker Desktop was not running** when this plan was written, so `harness-libsql-dev` was unreachable and no test was run.
- The working tree is clean on the epic branch.
- Baseline from STORY-001's report: 3355 passed, 27 skipped, with one failure and one error per run from libSQL flakiness, in different unrelated tests each time, all passing in isolation.

---

## Patterns to Follow

### Naming: an added column, declared in both places, with its reason
```python
# SOURCE: app/db/models.py:74-81
    # PRD-012 (D9): the profile that ran -- the name the call site passed,
    # after default resolution (`chat` for /query and the chat UI). It is what
    # tells a reader that `pii_detected_output = 0` under `code` means "not
    # analyzed" rather than "clean". Nullable with no default on purpose, like
    # dedup_key: rows written before PRD-012 stay NULL and are never
    # backfilled, and so does /query's foreign-session refusal, which writes
    # before any profile exists.
    "profile": "TEXT",
```

### Naming: a dataclass field appended before `id`
```python
# SOURCE: app/db/models.py:269-275
    # PRD-012 STORY-011 (D9). Same pattern as pattern_action: insert_audit_log()
    # writes it and _row_to_audit_log() maps it back on both read shapes. Set
    # on every row run_conversation writes; NULL on rows written before
    # PRD-012 and on /query's foreign-session refusal. Declared after
    # pattern_action to mirror the table, so id stays the trailing field.
    profile: Optional[str] = None
    id: Optional[int] = None
```

### Flags: `int(...)` on the way in, `bool(...)` on the way out
```python
# SOURCE: app/db/database.py:788-793, 869-874
                int(entry.was_duplicate_blocked),
                ...
                int(entry.pii_detected_input),
                int(entry.pii_detected_output),

        was_duplicate_blocked=bool(row["was_duplicate_blocked"]),
        ...
        pii_detected_input=bool(row["pii_detected_input"]),
        pii_detected_output=bool(row["pii_detected_output"]),
```

### Error Handling
This story adds no error path. Convergence keeps `_add_missing_columns`' single tolerated failure:
```python
# SOURCE: app/db/database.py:753-762
    existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    for name, ddl in columns.items():
        if name in existing:
            continue
        try:
            with _translated():
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
        except StorageError as exc:
            if not _is_duplicate_column(exc, name):
                raise
```

### Tests: a pre-migration fixture, then convergence without backfill
```python
# SOURCE: tests/test_db.py:2559-2586
def test_init_db_migrates_a_pre_profile_database(uninitialized_db, db_connect):
    _create_pre_profile_database(db_connect, uninitialized_db)

    init_db()
    init_db()  # the second boot converges without a second ALTER

    with get_connection() as conn:
        columns = _column_names(conn, "audit_logs")
    assert columns.count("profile") == 1

    assert count_audit_logs() == 1
    preserved = get_audit_log(1)
    assert preserved.profile is None
    assert (preserved.pattern_role, preserved.pattern_action) == ("user", "block")
```

### Tests: the batched read, checked on the raw JSON and through the mapper
```python
# SOURCE: tests/test_db.py:1162-1165, 2641-2645
    with get_connection() as conn:
        raw = conn.execute(database._SUMMARY_SQL, (100, 5, 5, 5)).fetchone()
    entries = json.loads(raw["rows"])
    assert all({"pattern_role", "pattern_action"} <= set(entry) for entry in entries)

    snapshot = summary_snapshot()

    assert snapshot.errors == {}
    assert snapshot.rows == list_audit_logs()
    assert [r.profile for r in snapshot.rows] == [None, "code"]
```

### Tests: recording the statements `init_db()` issues
```python
# SOURCE: tests/test_db.py:1588-1596
def _count_statements(monkeypatch) -> list:
    statements: list = []
    real_get_connection = database.get_connection
    monkeypatch.setattr(
        database,
        "get_connection",
        lambda: _RecordingConnection(real_get_connection(), statements),
    )
    return statements
```

---

## Design

### D-1: The eight declarations, in PRD Section 6.2 order

| Column | DDL | `AuditLog` field |
|---|---|---|
| `ingress` | `TEXT` | `Optional[str] = None` |
| `message_count` | `INTEGER` | `Optional[int] = None` |
| `input_tokens` | `INTEGER` | `Optional[int] = None` |
| `output_tokens` | `INTEGER` | `Optional[int] = None` |
| `streamed` | `INTEGER NOT NULL DEFAULT 0` | `bool = False` |
| `has_tool_calls` | `INTEGER NOT NULL DEFAULT 0` | `bool = False` |
| `conversation_key` | `TEXT` | `Optional[str] = None` |
| `limit_exceeded` | `TEXT` | `Optional[str] = None` |

The same order is used in all six places of F-1 and in every test list. The mapping is a `dict`, so its order is the order `init_db()` issues the `ALTER`s in, and Task 5 asserts it.

### D-2: Comment text for the mapping (story Technical Notes, PRD Section 6.2)

One block per column, or per pair where the reason is shared:

- `ingress`: PRD-013. Which door the request came through: `query`, `chat` or `v1`, named by the call site and never by a request field. Nullable with no default on purpose, like `dedup_key`: rows written before PRD-013 stay NULL and are never backfilled, and so does a direct call that passed none.
- `message_count`: `len(messages)` as received, before redaction. Nullable for the same reason: nothing recorded the count for an earlier row, and 0 would claim a request with no messages.
- `input_tokens`, `output_tokens`: `usage.prompt_tokens` and `usage.completion_tokens`. Nullable because NULL has two true meanings that 0 would erase: no upstream call was made, or the provider omitted the split. `tokens_used` is unchanged and stays the reported total.
- `streamed`, `has_tool_calls`: `NOT NULL DEFAULT 0`, unlike the six around them, because 0 is true of every row written before them: neither was possible. Always 0 until PRD-014 and PRD-016 respectively.
- `conversation_key`: the grouping key over the user id and the conversation's opening turns (PRD Section 6.3). Nullable, not backfilled: an earlier row kept only the last turn's hash, so its key cannot be derived. Not indexed (PRD Section 4, *Out of Scope*).
- `limit_exceeded`: `requests` or `tokens` on a usage-limit refusal, NULL on every other row. It is the dedicated verdict column that lets that row be `success=1` (PRD D6). Nullable with no default: NULL is "not a usage-limit row", which is every earlier row.

A line under the last entry: nothing writes a non-default value yet; `log_query` gains the parameters in STORY-005.

### D-3: Test values that expose a transposition

`insert_audit_log` has a hand-counted column list, placeholder list and value tuple. A swap between two adjacent integers or two adjacent flags would survive a test that sets both to the same value. The round-trip rows therefore use a different value in every field and opposite flags across two rows:

| Field | Row A | Row B |
|---|---|---|
| `ingress` | `"v1"` | `"chat"` |
| `message_count` | `7` | `3` |
| `input_tokens` | `2140` | `55` |
| `output_tokens` | `312` | `8` |
| `streamed` | `True` | `False` |
| `has_tool_calls` | `False` | `True` |
| `conversation_key` | `"ck-a"` | `"ck-b"` |
| `limit_exceeded` | `"tokens"` | `"requests"` |

Row A also sets `profile="code"` and `dedup_key="k"`, so the test can show the columns before the new ones did not shift.

### D-4: What is not done

- No index (story Technical Notes; PRD Section 4).
- No change to `log_query`, `query_pipeline.py`, `AuditQueryEntry`, `/audit`, `/stats` or the admin console. STORY-005 and STORY-006 own those.
- No change to `find_duplicate_timestamp`. The `limit_exceeded IS NULL` predicate is STORY-011's.
- No change to `scripts/migrate_to_turso.py` (F-4).
- The stale count in `_Row`'s docstring (`database.py:199`, "20 named reads") is left as it is. It has been out of date since PRD-008 and is not this story's to rewrite.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/db/models.py` | UPDATE | Eight columns in the `CREATE` and the mapping, with comments; eight `AuditLog` fields |
| `app/db/database.py` | UPDATE | `insert_audit_log`, `_row_to_audit_log`, `_SUMMARY_SQL`'s `json_object`; one paragraph in `init_db()`'s docstring |
| `tests/test_db.py` | UPDATE | New PRD-013 STORY-002 section (22 cases); two pinned inventories extended (F-2) |
| `tests/test_migrate_to_turso_cli.py` | UPDATE | One pinned inventory extended (F-2) |
| `tests/test_audit_characterization.py` | UPDATE | Eight names in `FIELDS_ADDED_SINCE`; one added test over the 12 arms (F-3) |
| `.agents/stories/PRD-013-audit-and-usage-limits/STORY-002-audit-columns.md` | UPDATE | Plan link and status (this command). Report and commit later (`/implement`) |
| `.agents/PRDs/PRD-013-audit-and-usage-limits/index.md` | UPDATE | Status and plan link (this command). Commit SHA later (`/implement`) |
| `.agents/reports/PRD-013-audit-and-usage-limits/STORY-002-audit-columns.report.md` | CREATE (by `/implement`) | Task 8 |

---

## Tasks

Execute in order. Each task is atomic and verifiable. `python` below means `C:\Users\tobip\.venvs\harness-ai\Scripts\python.exe`.

### Task 0: Preflight

- **Action**: environment and branch only.
- **Implement**:
  1. Start Docker Desktop, then `docker start harness-libsql-dev`. Check `docker ps`.
  2. Confirm the branch is `epic/PRD-013-audit-and-usage-limits`.
  3. Commit this plan and the Phase 5 story and index updates as `docs(PRD-013): STORY-002 plan`, so the story commit holds code and tests only (precedent: `5224280`).
  4. Run the full suite once and record the counts and any failure names. STORY-001's figure was 3355 passed, 27 skipped.
- **Validate**: `python -m pytest -q`. One or two failures in unrelated tests that pass in isolation are the known libSQL flakiness. On mass fixture errors, restart the container before looking at code (PRD Section 11).

### Task 1: Schema and dataclass

- **File**: `app/db/models.py`
- **Action**: UPDATE
- **Implement**:
  - `CREATE_AUDIT_LOGS_TABLE` (lines 29-30): add a comma after `profile TEXT` and the eight declarations of D-1, one per line, in order. No comma after the last. No comment inside the SQL string: `_ddl_columns` and `tests/test_db.py::_declared_columns` take the first token of each part.
  - Header comment (lines 33-36): extend the list of contributing stories with "PRD-013 STORY-002 adds ingress, message_count, input_tokens, output_tokens, streamed, has_tool_calls, conversation_key and limit_exceeded".
  - `AUDIT_LOGS_ADDED_COLUMNS` (after line 81): the eight entries of D-1 with the comment blocks of D-2.
  - `AuditLog` (after line 274, before `id`): the eight fields of D-1 under one comment block: PRD-013 STORY-002; same pattern as `profile` (the writer writes them and the mapper reads them back on both read shapes); nothing sets a non-default value until STORY-005; the two flags are `bool` like `pii_detected_input`; declared after `profile` to mirror the table, so `id` stays the trailing field.
- **Mirror**: `app/db/models.py:74-81` and `:269-275`
- **Validate**: `python -c "from app.db.models import AuditLog, AUDIT_LOGS_ADDED_COLUMNS as m; a = AuditLog('t','u','h'); print(len(m), a.streamed, a.has_tool_calls, a.ingress)"` prints `18 False False None`.

### Task 2: Writer, mapper and the batched read shape

- **File**: `app/db/database.py`
- **Action**: UPDATE
- **Implement**:
  - `insert_audit_log` (lines 769-802): append the eight names to the column list, grow the placeholders from 23 to 31, and append the eight values in the same order. `int(entry.streamed)` and `int(entry.has_tool_calls)`, like the flags above them. The other six are passed as they are.
  - `_row_to_audit_log` (after line 882): eight named reads, with `bool(row["streamed"])` and `bool(row["has_tool_calls"])`.
  - `_SUMMARY_SQL` (line 1225): move the closing `))` from the `'profile', profile` line to after eight new `'name', name` pairs. This is the change the story warns about: without it `_row_to_audit_log` raises `KeyError` on the batched path only.
  - `init_db()` docstring (after line 690): one paragraph. PRD-013 STORY-002 adds eight `audit_logs` columns on the same path with no new code here; six are nullable with no default and no backfill; `streamed` and `has_tool_calls` are `NOT NULL DEFAULT 0`, which `ADD COLUMN` accepts because the default is non-NULL; none is indexed.
  - Do not touch `init_db()`'s body, `_add_missing_columns`, `find_duplicate_timestamp` or the positional parameter order of `_SUMMARY_SQL` (the new pairs are inside the first subquery and add no `?`).
- **Mirror**: `app/db/database.py:775-801`, `:869-882`, `:1223-1225`
- **Validate**: `python -c "from app.main import app"` imports. Then `python -m pytest tests/test_db.py -q -k "round_trip or batched_read or summary_snapshot or no_alter"` is green.

### Task 3: The three pinned inventories (F-2)

- **Files**: `tests/test_db.py`, `tests/test_migrate_to_turso_cli.py`
- **Action**: UPDATE. These are the only edits to existing assertions in the story.
- **Implement**:
  - `test_schema_has_no_ip_or_location_column` (`tests/test_db.py:959-961`): add the eight names to `expected` under a comment, `# PRD-013 STORY-002 (Section 6.2): ingress, size, token split, delivery flags, conversation key and the usage-limit verdict.` Line 963 is not edited.
  - `test_audit_log_carries_session_id_without_breaking_construction` (`tests/test_db.py:2103-2110`): extend the comment with "and PRD-013 STORY-002 appended eight more after profile", and change the slice to `names[-14:]` with the eight names between `"profile"` and `"id"`. The claim stays the same: `id` is the trailing field.
  - `test_dest_columns_match_the_ddl` (`tests/test_migrate_to_turso_cli.py:165-175`): append the eight names after `"profile"` and add a comment line, `# ingress ... limit_exceeded: PRD-013 STORY-002 (Section 6.2)`. The `defaults[...]` assertions below are not edited.
- **Mirror**: the PRD-012 STORY-011 edits at the same lines (`faaa4be`)
- **Validate**: `python -m pytest tests/test_migrate_to_turso_cli.py -q` and `python -m pytest tests/test_db.py -q -k "ip_or_location or carries_session_id"` are green. `git diff -U0 tests/test_db.py tests/test_migrate_to_turso_cli.py` shows changes at these three places only.

### Task 4: The characterization module's extension point (F-3)

- **File**: `tests/test_audit_characterization.py`
- **Action**: UPDATE
- **Implement**:
  - Line 114: `FIELDS_ADDED_SINCE` becomes a `frozenset` of the eight names, with a comment `# PRD-013 STORY-002.` No other existing line changes. `PINNED_FIELDS`, `_row`, `ARM_CASES` and every existing test stay as they are.
  - Add, after `test_the_upstream_error_row_names_the_requested_model`:
    - `_UNSET_THROUGH_DRIVE`: a dict of the six fields F-3 lists to their defaults (`ingress`, `input_tokens`, `output_tokens` and `limit_exceeded` to `None`; `streamed` and `has_tool_calls` to `False`). Its comment says why `message_count` and `conversation_key` are absent: STORY-005 sets them on every arm, and an assertion written here may not be changed later.
    - `test_no_arm_sets_these_prd013_fields(temp_db, monkeypatch, arm)`, parametrized over the arm names from `ARM_CASES` with the same ids. It records `_last_audit_id()`, calls `_drive`, reads `_audit_rows_since`, asserts at least one row was written, and asserts `{name: getattr(row, name) for name in _UNSET_THROUGH_DRIVE} == _UNSET_THROUGH_DRIVE` for each row.
  - Add one sentence to the module docstring's "How a later story extends this module" paragraph: STORY-002 added eight names and `test_no_arm_sets_these_prd013_fields`.
- **Mirror**: `tests/test_audit_characterization.py:465-486`
- **Validate**: `python -m pytest tests/test_audit_characterization.py -q` is green with 39 cases (27 + 12). `git diff tests/test_audit_characterization.py` shows one changed line (114) and additions only.

### Task 5: The PRD-013 STORY-002 section in `tests/test_db.py`

- **File**: `tests/test_db.py`
- **Action**: UPDATE (additions only)
- **Implement**: a section headed `# PRD-013 STORY-002: eight audit columns (Section 6.2).`, placed after the PRD-012 STORY-011 section (after line 2660), plus one fixture beside the other `_create_pre_*` helpers (after line 603).
  - `_PRD013_COLUMNS`: a dict literal of D-1, name to DDL, in order. `_PRD013_NULLABLE` and `_PRD013_FLAGS` are derived from it as tuples of names.
  - `_create_pre_prd013_database(connect, url)`: the 24-column table as it shipped before this story (the `CREATE` of `_create_pre_profile_database` plus `profile TEXT`), with the dedup index. It seeds two rows: a `chat` success row with `tokens_used=42`, `session_id`, `dedup_key="k-pre013"` and `profile="chat"`, and a duplicate-blocked row. Docstring: the seventh of these fixtures, and the only one where the eight PRD-013 columns are the sole columns in flight.
  - **AC 1** `test_audit_logs_declares_each_prd013_column_in_both_places(name, ddl)`, parametrized ×8: `AUDIT_LOGS_ADDED_COLUMNS[name] == ddl` and `f"{name} {ddl}" in CREATE_AUDIT_LOGS_TABLE`.
  - **AC 1** `test_the_prd013_columns_are_declared_last_and_in_order()`: the last eight keys of `AUDIT_LOGS_ADDED_COLUMNS` and the last eight of `_declared_columns(CREATE_AUDIT_LOGS_TABLE)` both equal `list(_PRD013_COLUMNS)`.
  - **Fresh schema** `test_init_db_creates_each_prd013_column_with_its_shape(temp_db, name)`, parametrized ×8, from `PRAGMA table_info`: the type is `TEXT` or `INTEGER` as declared; the six nullable ones have `notnull == 0` and `dflt_value is None`; the two flags have `notnull == 1` and `str(dflt_value) == "0"`.
  - **AC 2** `test_init_db_migrates_a_pre_prd013_database(uninitialized_db, db_connect, monkeypatch)`:
    1. Build the fixture, then `statements = _count_statements(monkeypatch)` and `init_db()`.
    2. The `ADD COLUMN` statements are exactly `[f"ALTER TABLE audit_logs ADD COLUMN {name} {ddl}" for name, ddl in _PRD013_COLUMNS.items()]`.
    3. No recorded statement starts with `UPDATE`, `INSERT` or `DELETE` (AC 2, "no row is updated").
    4. `statements.clear()`, `init_db()` again, and no statement contains `ALTER`.
    5. `monkeypatch.undo()`. The table has 32 columns and each of the eight appears once.
    6. A raw `SELECT` of the eight columns for both rows returns `None` for the six and the integer `0` for the two flags.
    7. Through `get_audit_log`: the six are `None`, the two flags `is False`, and the seeded `tokens_used`, `session_id`, `dedup_key`, `profile` and `was_duplicate_blocked` are what was seeded. `count_audit_logs() == 2`.
    8. A new row inserted with Row A of D-3 reads back with those values.
  - `test_prd013_fields_default_when_not_supplied(temp_db)`: a bare `AuditLog` is inserted. It reads back `None` ×6 and `False` ×2, and a raw `SELECT streamed, has_tool_calls` returns `0, 0`.
  - **AC 4** `test_prd013_fields_round_trip(temp_db)`: Rows A and B of D-3 are inserted. For each, `get_audit_log(id)` returns the eight values, with `streamed is True` / `has_tool_calls is False` on A and the reverse on B. Row A's `profile`, `dedup_key` and `prompt_hash` are unshifted. `list_audit_logs()` returns the same two objects as `get_audit_log`.
  - **AC 4** `test_prd013_fields_survive_the_batched_read(temp_db)`: Rows A and B plus one bare row.
    - Raw: `json.loads` of `database._SUMMARY_SQL`'s `rows` has all eight keys on every entry, and the flags are the integers `0` and `1` there, which is what makes the mapper's `bool(...)` necessary.
    - `summary_snapshot()`: `errors == {}`, `rows == list_audit_logs()`, each of the eight fields matches `get_audit_log` for the same id, and `type(row.streamed) is bool` and `type(row.has_tool_calls) is bool` on every row.
  - `test_audit_log_carries_the_prd013_fields_without_breaking_construction()`: a bare `AuditLog` has the eight defaults, a keyword construction carries them, and the last nine field names are the eight followed by `"id"`.
- **Mirror**: `tests/test_db.py:546-603`, `:2543-2660`, `:1156-1177`, `:1588-1596`
- **Validate**: `python -m pytest tests/test_db.py -q -k "prd013"` is green with 22 cases. `python -m pytest tests/test_db.py -q` is green.
  - **If `str(dflt_value) == "0"` or the raw integer `0` in step 6 does not hold against libSQL, stop and report it.** Both were derived from SQLite's documented behaviour and not measured (F-7).

### Task 6: Prove the tests bite

- **Action**: temporary edits only, each reverted before commit. Use a script that restores the file in a `finally` block, as STORY-001 did.
- **Implement**: each change must fail the named tests.
  1. `_SUMMARY_SQL`: drop the `'streamed', streamed` pair. `test_prd013_fields_survive_the_batched_read` fails, and `test_prd013_fields_round_trip` still passes. This is the batched-path-only failure the story describes.
  2. `insert_audit_log`: swap `entry.streamed` and `entry.has_tool_calls` in the value tuple. The round-trip test fails.
  3. `insert_audit_log`: swap `entry.input_tokens` and `entry.output_tokens`. The round-trip test fails.
  4. `_row_to_audit_log`: drop `bool(...)` from `streamed`. The round-trip and batched-read tests fail on the `is True` / `type(...) is bool` assertions.
  5. `AUDIT_LOGS_ADDED_COLUMNS`: remove `limit_exceeded`. The AC 1 case for it and `test_init_db_migrates_a_pre_prd013_database` fail.
  6. `CREATE_AUDIT_LOGS_TABLE`: remove `conversation_key TEXT`. `test_every_added_column_is_also_declared_in_the_create` and the AC 1 case fail.
  7. `AUDIT_LOGS_ADDED_COLUMNS`: change `streamed` to `"INTEGER NOT NULL"`. `test_added_columns_declaring_not_null_also_declare_a_default` fails.
- **Validate**: `git status` shows only the five files of Tasks 1-5.

### Task 7: Full suite and commit

- **Implement**:
  - `python -m pytest -q`. Expected: the Task 0 pass count plus 34 (22 in `test_db.py`, 12 in the characterization module).
  - `git diff --stat $(git merge-base HEAD main)..HEAD -- tests/test_query_outcomes_regression.py tests/test_chat_outcomes_regression.py tests/test_duplicate_scope.py tests/test_pii_characterization.py` is empty (PRD Section 11).
  - `git diff 126f0da -- tests/test_audit_characterization.py` shows line 114 changed and additions only.
  - Commit: `feat(PRD-013): STORY-002 eight additive audit columns through the writer and both read shapes`.
- **Validate**: any failing test is re-run in isolation and named in the report. A failure in a test that passes alone is recorded as flakiness, not ignored.

### Task 8: Report

- **File**: `.agents/reports/PRD-013-audit-and-usage-limits/STORY-002-audit-columns.report.md` (written by `/implement`, in the shape of the STORY-001 report)
- **Must contain**:
  - **AC 5 as it was met:** no assertion changed except three pinned column and field inventories, each named with its file and line and each carrying a PRD-013 comment (F-2).
  - The two unmeasured values of Task 5 and whether they held.
  - The seven bite checks and what failed for each.
  - **For STORY-005:** `_UNSET_THROUGH_DRIVE` deliberately leaves out `message_count` and `conversation_key`, so the per-arm assertions for those two are STORY-005's to add. `insert_audit_log` and both read shapes already carry all eight.
  - **For STORY-006:** `AuditQueryEntry` and `/audit` do not expose the fields yet.
  - **For STORY-011:** `limit_exceeded` exists and round-trips; `find_duplicate_timestamp` has no predicate on it yet.
  - **For STORY-018:** `scripts/migrate_to_turso.py::_audit_log_from_source` maps the first 19 fields only (F-4).

---

## End-to-End Tests

Nothing user-visible changes. The checks are at the storage boundary:

- [ ] With the libSQL container up, `pytest tests/test_db.py -q -k "prd013"` is green with 22 cases.
- [ ] `pytest tests/test_audit_characterization.py -q` is green with 39 cases, and its diff against `126f0da` is one changed line plus additions.
- [ ] `pytest tests/test_db.py::test_init_db_issues_no_alter_when_schema_is_current -q` is green and the test is unedited (AC 3).
- [ ] Convergence by hand: build a database with the pre-story 24-column table and a few rows, start the API (`uvicorn app.main:app`), and confirm `PRAGMA table_info(audit_logs)` lists 32 columns, the old rows read NULL ×6 and 0 ×2, and a restart issues no `ALTER`.
- [ ] `GET /health` returns 200 after that boot.
- [ ] `GET /audit` and `GET /stats` return the same keys as before the story (no field is exposed yet), and the admin console summary still renders, which shows the batched read works with the wider `json_object`.
- [ ] `pytest tests/test_migrate_to_turso_cli.py tests/test_two_instance_smoke.py -q` is green.
- [ ] All seven Task 6 bite checks fail as described and pass after revert.
- [ ] The full suite matches the Task 0 baseline plus 34.

---

## Validation

```bash
# libSQL dev server must be up (tests/conftest.py; container harness-libsql-dev)
PY=/c/Users/tobip/.venvs/harness-ai/Scripts/python.exe
$PY -c "from app.main import app"
$PY -m pytest tests/test_db.py -q -k "prd013"
$PY -m pytest tests/test_db.py tests/test_audit_characterization.py tests/test_migrate_to_turso_cli.py -q
$PY -m pytest -q
git diff 126f0da -- tests/test_audit_characterization.py
```

There is no frontend lint: the UI is Reflex (Python) and this story does not touch it.

---

## Risks + Mitigations

| Risk | Mitigation |
|---|---|
| AC 5 is read literally and the three inventory edits are taken as a violation | F-2 states the conflict before any code is written. The edits are confined to Task 3, each carries a PRD-013 comment, and the report names them |
| A miscount in `insert_audit_log`'s 31 columns, placeholders or values | A wrong count fails every insert in the suite. A transposition is caught by D-3's distinct values and opposite flags, and bite checks 2 and 3 confirm it |
| The `json_object` list is missed or mistyped, breaking only the batched path | `test_prd013_fields_survive_the_batched_read` checks the raw JSON keys and the mapped rows. Bite check 1 confirms the test separates the two paths |
| `ADD COLUMN ... NOT NULL DEFAULT 0` behaves differently on libSQL than on SQLite | `pii_detected_input` already converges with the same DDL (`models.py:50`). The pre-PRD-013 migration test runs it against the real server |
| `PRAGMA table_info` reports `dflt_value` in a form other than `"0"` | The assertion compares `str(...)`, and Task 5 stops and reports if it does not hold |
| An assertion added to the characterization module has to be changed by STORY-005 | The added test pins only the six fields that stay at their defaults through `_drive` (F-3) |
| A pre-existing database on a shared deployment is ALTERed by two instances at once | Unchanged mechanism: `_add_missing_columns` tolerates `duplicate column name`, and the existing race tests now run over all 18 entries (F-6) |
| libSQL flakiness hides a real failure | Every failing test is re-run in isolation and named in the report (Task 7) |

---

## Acceptance Criteria

(Copied from story `STORY-002`)

- [ ] Given `app/db/models.py`, when it is read, then `ingress TEXT`, `message_count INTEGER`, `input_tokens INTEGER`, `output_tokens INTEGER`, `streamed INTEGER NOT NULL DEFAULT 0`, `has_tool_calls INTEGER NOT NULL DEFAULT 0`, `conversation_key TEXT` and `limit_exceeded TEXT` are each declared in both `CREATE_AUDIT_LOGS_TABLE` and `AUDIT_LOGS_ADDED_COLUMNS`.
- [ ] Given a database created before this story with existing rows, when `init_db()` runs, then all eight columns exist, existing rows read `NULL` for the six nullable ones and `0` for `streamed` and `has_tool_calls`, and no row is updated.
- [ ] Given a database already at the current schema, when `init_db()` runs, then no `ALTER` is issued (`test_init_db_issues_no_alter_when_schema_is_current` still passes).
- [ ] Given an `AuditLog` with all eight fields set, when it is written by `insert_audit_log` and read back by `get_audit_log` and by `summary_snapshot().rows`, then both return the same eight values, with the two flags as `bool`.
- [ ] Given the full suite, when it runs, then STORY-001's characterization and every existing test pass with no assertion changed. **Met with one stated exception:** three pinned column and field inventories gain the eight names (F-2).
- [ ] All tasks completed
- [ ] Backend imports and the server starts without error
- [ ] Follows existing patterns (both-places declaration with a reason per column, field before `id`, `int`/`bool` on flags, pre-migration fixture, raw-JSON check on the batched read)
