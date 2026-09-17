---
story: STORY-002
prd: PRD-009
slug: dedup-key-column-and-index
title: "audit_logs.dedup_key column and idx_audit_logs_dedup, converged by init_db() and round-tripped by AuditLog"
type: NEW_CAPABILITY
complexity: LOW
epic_branch: epic/PRD-009-duplicate-rescoping
created: 2026-09-16
---

# Plan: audit_logs.dedup_key column and idx_audit_logs_dedup, converged by init_db() and round-tripped by AuditLog

## Summary

Add a nullable `dedup_key TEXT` column to `audit_logs`, declared in both `CREATE_AUDIT_LOGS_TABLE` and `AUDIT_LOGS_ADDED_COLUMNS`. Add a non-unique composite index `idx_audit_logs_dedup ON audit_logs(user_id, dedup_key, timestamp)`, executed in `init_db()`'s single `_session()` block directly after `_add_missing_columns(conn)`. Add `AuditLog.dedup_key: Optional[str] = None`. Then extend the three places that list the audit columns explicitly: `insert_audit_log`'s column list, placeholders and values; `_row_to_audit_log`; and the `json_object(...)` inside `_SUMMARY_SQL`. `_add_missing_columns` and `_is_duplicate_column` get **no edit**. This story asserts that they already converge the new column, following PRD-008 STORY-003. Nothing in the pipeline writes a real key yet (STORY-006), and `AuditQueryEntry` gains no field (D5).

Exploration turned up four facts the story text does not mention:

1. **Three existing tests pin the exact column or field set, and they will fail as soon as the column exists.** None of them can be avoided:
   - `tests/test_db.py:607-634` `test_schema_has_no_ip_or_location_column`: literal `set(...) == expected`.
   - `tests/test_db.py:1631-1647` `test_audit_log_carries_session_id_without_breaking_construction`: `names[-2:] == ["session_id", "id"]`.
   - `tests/test_migrate_to_turso_cli.py:158-171` `test_dest_columns_match_the_ddl`: an exact ordered list from `_ddl_columns(CREATE_AUDIT_LOGS_TABLE)`.

   Each gets a one-entry extension plus a `# PRD-009 STORY-002` comment, the same way `session_id` was added (`# PRD-008 STORY-002`). None of the three is on PRD-009's must-pass-unmodified list (`test_query_router`, `test_integration`, `test_two_instance_smoke`, `test_stats_router`, `test_audit_router`).
2. **The PRD-008 race fixture stops isolating its column.** `_create_pre_chat_sessions_database` (`tests/test_db.py:307-352`) is main's 19-column shape. After this story it is missing **both** `session_id` and `dedup_key`, so the docstring claim in `test_two_init_db_calls_racing_on_session_id_both_converge` (`:2710`), "Here it is the **only** column in flight", becomes false. Its assertions still name `session_id` and still pass. So this story adds a fourth fixture, `_create_pre_dedup_key_database` (the current 20-column shape), where `dedup_key` is the only missing column. It also adds a note to the old helper's docstring saying that it now has two columns in flight.
3. **`scripts/migrate_to_turso.py` needs no edit.** It reads the column list and defaults from the DDL (`_ddl_columns` / `_ddl_defaults`, `:112-140`), so `dedup_key` becomes a defaulted-to-NULL column for every legacy SQLite source, which is exactly what `session_id` already is. `_audit_log_from_source` (`:457-483`) constructs `AuditLog` by keyword and already omits `session_id`, so the new field defaults to `None` on both sides of its `!=` read-back. That existing omission is recorded under Risks and left alone (out of scope).
4. **No generic `AuditLog(**row)` exists in `app/`, `chat_ui/` or `scripts/`.** Every construction is by keyword (`database.py:785`, `audit_logger.py:30`, `migrate_to_turso.py:463`). `tests/test_history_off_integration.py:265-292` compares `dataclasses.asdict` of two rows, and both will carry `dedup_key=None`, so it stays equal. `tests/test_admin_formatting.py:54` builds `AuditLog(**fields)` from a subset, so a new optional field is harmless.

There is no linter or formatter in this repo. "Validate" means pytest against the local libSQL dev server (`tests/conftest.py:26-31`).

## User Story

As a **maintainer**
I want the `dedup_key` column and its lookup index to arrive through the same idempotent bootstrap every other schema change used
So that a fresh database, a pre-PRD database, a hot reload and two instances booting together all converge without a migration tool.

## Story Reference

- Story file: `.agents/stories/PRD-009-duplicate-rescoping/STORY-002-dedup-key-column-and-index.md`
- PRD: `.agents/PRDs/PRD-009-duplicate-rescoping/PRD.md`, Sections 4 (Schema), 6.3 (index = lookup access path), 6.7 (patterns), 7 (F2), 11, 14 (Risk 2)
- Depends on: STORY-001 (`9abef61`, **done**)
- Blocks: STORY-006
- Precedent: `.agents/stories/PRD-008-chat-sessions/STORY-003-init-db-tables-and-audit-column.md` and its plan `.agents/plans/PRD-008-chat-sessions/completed/STORY-003-init-db-tables-and-audit-column.plan.md`

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY (additive schema: column + index + dataclass field, no reader yet) |
| Complexity | LOW |
| Systems Affected | `app/db/models.py`, `app/db/database.py`, `tests/test_db.py`, `tests/test_migrate_to_turso_cli.py` |
| Story | STORY-002 |
| PRD | PRD-009 |
| Epic Branch | `epic/PRD-009-duplicate-rescoping` (commit directly on this branch) |

---

## Skills In Use

I listed `.agents/skills/` in full. It holds exactly one skill:

| Skill | Applies? | Reason |
|-------|----------|--------|
| `frontend-design` | **No** | Its `description` scopes it to "distinctive, intentional visual design when building new UI or reshaping an existing one." This story edits the storage layer and two test modules and renders nothing. |

The story's `skills:` frontmatter is `[]`, and both its Technical Notes and PRD Section 8 reach the same conclusion. **No skill constrains any task below.**

---

## Patterns to Follow

### Naming: DDL constant for an index, with a comment on why it is not UNIQUE

```python
# SOURCE: app/db/models.py:106-112
# Not UNIQUE, unlike idx_users_token_hash: one user has many sessions, so this
# index serves ordering and filtering rather than a uniqueness claim. The column
# order is the rail's read exactly -- filter by owner, newest activity first.
CREATE_CHAT_SESSIONS_USER_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_updated "
    "ON chat_sessions(user_id, updated_at DESC)"
)
```

### Additive column: declared twice, commented with its PRD

```python
# SOURCE: app/db/models.py:43-53
AUDIT_LOGS_ADDED_COLUMNS = {
    ...
    "denied_permission": "TEXT",
    # PRD-008: the join key between the evidence log and the transcript.
    # Nullable with no default on purpose -- a POST /query that omits session_id
    # writes NULL, which is today's behaviour exactly (PRD Section 10).
    "session_id": "TEXT",
}
```

### Bootstrap block: one `_session()`, with columns converged before anything that depends on them

```python
# SOURCE: app/db/database.py:663-674
    check_database_reachable()
    with _session() as conn:
        conn.execute(CREATE_AUDIT_LOGS_TABLE)
        _add_missing_columns(conn)
        conn.execute(CREATE_USERS_TABLE)
        conn.execute(CREATE_USERS_TOKEN_HASH_INDEX)
        ...
```

### Error handling: the only tolerated failure is a duplicate column that names the column being added (no change here)

```python
# SOURCE: app/db/database.py:709-718
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(audit_logs)")}
    for name, ddl in AUDIT_LOGS_ADDED_COLUMNS.items():
        if name in existing:
            continue
        try:
            with _translated():
                conn.execute(f"ALTER TABLE audit_logs ADD COLUMN {name} {ddl}")
        except StorageError as exc:
            if not _is_duplicate_column(exc, name):
                raise
```

The `CREATE INDEX IF NOT EXISTS` is idempotent by construction, so it needs no `try`. Any failure there (e.g. `no such column: dedup_key` if it were ever moved above the column add) must propagate. That failure is the signal that the ordering is wrong.

### Two read shapes, one mapper

```python
# SOURCE: app/db/database.py:1111-1132 (_SUMMARY_SQL) and :772-806 (_row_to_audit_log)
              'denied_permission', denied_permission,
              'session_id', session_id))
     FROM (SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT ?)
...
        denied_permission=row["denied_permission"],
        session_id=row["session_id"],
    )
```

### Tests: round trip on both read shapes, then pre-PRD migration, then forced race

```python
# SOURCE: tests/test_db.py:571-600
def test_session_id_survives_the_batched_read(temp_db):
    ...
    snapshot = summary_snapshot()

    assert snapshot.errors == {}
    assert snapshot.rows == list_audit_logs()
    assert [row.session_id for row in snapshot.rows] == [None, "0f6c2e5a-..."]
```

```python
# SOURCE: tests/test_db.py:2710-2750
def test_two_init_db_calls_racing_on_session_id_both_converge(
    uninitialized_db, db_connect, monkeypatch
):
    _create_pre_chat_sessions_database(db_connect, uninitialized_db)
    gate = threading.Barrier(2, timeout=30)
    _install(monkeypatch, lambda conn: _GatedConnection(conn, gate))

    failures = _run_concurrently(2, init_db)

    assert not failures, f"a concurrent init_db() raised: {failures}"

    monkeypatch.undo()
    with get_connection() as conn:
        columns = [row["name"] for row in conn.execute("PRAGMA table_info(audit_logs)")]

    assert columns.count("session_id") == 1, columns
    assert set(AUDIT_LOGS_ADDED_COLUMNS) <= set(columns)
    assert count_audit_logs() == 1
    preserved = get_audit_log(1)
    assert preserved.user_id == "carla@empresa.com"
    assert preserved.session_id is None
```

### Tests: index present, and used by the access path

```python
# SOURCE: tests/test_db.py:1711-1720 and :2006-2022
@pytest.mark.parametrize("index", _CHAT_INDEXES)
def test_init_db_creates_the_chat_indexes(temp_db, index):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name=?", (index,)
        ).fetchone()
    assert row is not None
...
    assert "idx_users_token_hash" in plan, plan
    assert "SCAN" not in plan.upper(), plan
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/db/models.py` | UPDATE | `dedup_key TEXT` in `CREATE_AUDIT_LOGS_TABLE` and `AUDIT_LOGS_ADDED_COLUMNS`; new `CREATE_AUDIT_LOGS_DEDUP_INDEX`; `AuditLog.dedup_key` field + PRD-009 comment |
| `app/db/database.py` | UPDATE | Import + execute the index after `_add_missing_columns(conn)`; `init_db` docstring note; `insert_audit_log` column/placeholder/value; `_row_to_audit_log`; `'dedup_key', dedup_key` in `_SUMMARY_SQL` |
| `tests/test_db.py` | UPDATE | New coverage (constants, built index + column order, EXPLAIN plan, round trip on both read shapes, pre-PRD migration, index-after-ALTER ordering, forced race); three deliberate pin updates + one docstring note |
| `tests/test_migrate_to_turso_cli.py` | UPDATE | Extend `test_dest_columns_match_the_ddl`'s literal list by `"dedup_key"` |

No files are created. `_add_missing_columns`, `_is_duplicate_column`, `app/models/schemas.py`, `app/routers/*`, `app/services/*` and `scripts/migrate_to_turso.py` are **not touched**.

---

## Tasks

Execute in order. Each task is atomic + verifiable. Tasks 1–3 are production code; Tasks 4–10 are tests.

### Task 1: Declare the column, the index DDL and the dataclass field

- **File**: `app/db/models.py`
- **Action**: UPDATE
- **Implement**:
  1. `CREATE_AUDIT_LOGS_TABLE`: change `    session_id TEXT` to `    session_id TEXT,` and add `    dedup_key TEXT` as the last column. Keep one column per line and no table constraints; `_declared_columns` in tests and `_ddl_columns` in the migration script both depend on that shape.
  2. `AUDIT_LOGS_ADDED_COLUMNS`: append `"dedup_key": "TEXT"`, with a comment in the `session_id` entry's style: PRD-009, the per-caller duplicate key over a conversation (PRD Section 6.2). It is nullable with no default because pre-PRD rows stay NULL and are never backfilled (D6), and a NULL key can never match a lookup. Extend the header comment's history line (`:29-30`) with "PRD-009 STORY-002 adds dedup_key".
  3. After `CREATE_AUDIT_LOGS_TABLE`/`AUDIT_LOGS_ADDED_COLUMNS` (before the users block), add:
     ```python
     CREATE_AUDIT_LOGS_DEDUP_INDEX = (
         "CREATE INDEX IF NOT EXISTS idx_audit_logs_dedup "
         "ON audit_logs(user_id, dedup_key, timestamp)"
     )
     ```
     Put a comment above it, mirroring `:106-108`. The comment should say: **Not UNIQUE**, because the same key legitimately repeats (duplicate-blocked rows, failures, denials). The column order is the lookup's access path from PRD Section 6.3: equality on `user_id`, equality on `dedup_key`, range on `timestamp`. The three flag predicates are left unindexed on purpose. Also say that `init_db()` must execute it after `_add_missing_columns()`, because on a pre-PRD database the column does not exist until then.
  4. `AuditLog`: add `dedup_key: Optional[str] = None` **after `session_id` and before `id`** (declaration order mirrors the table; `id` stays the trailing field). Update the comment block above `session_id` with a PRD-009 note in the same pattern: written by `insert_audit_log()` and mapped back by `_row_to_audit_log()` on both read shapes as of PRD-009 STORY-002. Nothing sets a real key until STORY-006, and it is never exposed on `GET /audit` (D5).
- **Mirror**: `app/db/models.py:43-53` (column entry), `:106-112` (index constant), `:179-183` (field comment)
- **Validate**: `python -c "from app.db.models import AUDIT_LOGS_ADDED_COLUMNS, CREATE_AUDIT_LOGS_TABLE, CREATE_AUDIT_LOGS_DEDUP_INDEX, AuditLog; assert AuditLog(timestamp='t', user_id='u', prompt_hash='h').dedup_key is None"`

### Task 2: Create the index in `init_db()`, directly after the column convergence

- **File**: `app/db/database.py`
- **Action**: UPDATE
- **Implement**:
  1. Add `CREATE_AUDIT_LOGS_DEDUP_INDEX` to the `from app.db.models import (...)` block (alphabetical, after `AUDIT_LOGS_ADDED_COLUMNS`/`CREATE_AUDIT_LOGS_TABLE`, matching the existing sort).
  2. In `init_db()`'s `with _session() as conn:` block, insert `conn.execute(CREATE_AUDIT_LOGS_DEDUP_INDEX)` on the line **immediately after** `_add_missing_columns(conn)` and before `CREATE_USERS_TABLE`. Keep it in the same block: no second `_session()`. `test_init_db_issues_no_alter_when_schema_is_current` counts connections (`== 2`).
  3. Extend the `init_db` docstring with a short PRD-009 paragraph. PRD-009 adds one more column (`dedup_key`), which rides `_add_missing_columns()` with no new code there, like `session_id`. It also adds the first index on `audit_logs`, the one statement in this block whose position is load-bearing: an index on a column that does not exist yet fails on a pre-PRD database, so it sits after the column add. The steady-state cost is one more `CREATE INDEX IF NOT EXISTS` no-op.
  4. **Do not edit `_add_missing_columns` or `_is_duplicate_column`.** If a task seems to need that, stop. The story says to assert this path, not change it.
- **Mirror**: `app/db/database.py:666-674`
- **Validate**: `pytest tests/test_db.py -q -k "init_db"` (the existing bootstrap, migration and no-ALTER tests stay green)

### Task 3: Write and read `dedup_key` on every audit read/write shape

- **File**: `app/db/database.py`
- **Action**: UPDATE
- **Implement**:
  1. `insert_audit_log` (`:721-755`): append `dedup_key` to the column list after `session_id`, add a **20th** `?` to `VALUES`, and append `entry.dedup_key,` to the tuple after `entry.session_id,`. Count the placeholders: 20 columns, 20 `?`, 20 values.
  2. `_row_to_audit_log` (`:772-806`): add `dedup_key=row["dedup_key"],` after `session_id=row["session_id"],`.
  3. `_SUMMARY_SQL` (`:1111-1131`): change `'session_id', session_id))` to `'session_id', session_id,` and add `'dedup_key', dedup_key))`. **Same commit as step 2.** Without it, `_decode_rows` raises `KeyError` and `summary_snapshot().rows` fails on every call.
- **Mirror**: the `session_id` threading in the same three places
- **Validate**: `pytest tests/test_db.py -q -k "round_trip or batched_read or summary_snapshot"`

### Task 4: Update the three exact-set pins, deliberately and with citations

- **Files**: `tests/test_db.py`, `tests/test_migrate_to_turso_cli.py`
- **Action**: UPDATE
- **Implement**:
  1. `tests/test_db.py::test_schema_has_no_ip_or_location_column` (`:630-631`): add `"dedup_key",  # PRD-009 STORY-002` after the `session_id` entry.
  2. `tests/test_db.py::test_audit_log_carries_session_id_without_breaking_construction` (`:1646-1647`): change to `assert names[-3:] == ["session_id", "dedup_key", "id"]`, with a comment: PRD-009 STORY-002 appended `dedup_key` after `session_id`, and the test's claim that the surrogate key stays the trailing field is unchanged.
  3. `tests/test_migrate_to_turso_cli.py::test_dest_columns_match_the_ddl` (`:170`): change to `"denied_permission", "session_id", "dedup_key",  # session_id: PRD-008 STORY-002; dedup_key: PRD-009 STORY-002`.
- **Mirror**: the `# PRD-008 STORY-002` annotations already on those lines
- **Validate**: `pytest tests/test_db.py::test_schema_has_no_ip_or_location_column tests/test_db.py::test_audit_log_carries_session_id_without_breaking_construction tests/test_migrate_to_turso_cli.py::test_dest_columns_match_the_ddl -v`

### Task 5: Constant-level tests for the column and index declarations

- **File**: `tests/test_db.py`
- **Action**: UPDATE (add `CREATE_AUDIT_LOGS_DEDUP_INDEX` to the `app.db.models` import)
- **Implement**: add these next to `test_audit_logs_added_columns_carries_a_nullable_session_id` (`:1610`):
  - `test_audit_logs_added_columns_carries_a_nullable_dedup_key`: `AUDIT_LOGS_ADDED_COLUMNS["dedup_key"] == "TEXT"` and `"dedup_key TEXT" in CREATE_AUDIT_LOGS_TABLE`. The docstring cites D6: no default, pre-PRD rows stay NULL, and a NULL key never matches.
  - `test_audit_logs_dedup_index_is_the_lookup_access_path`: `"CREATE INDEX IF NOT EXISTS" in CREATE_AUDIT_LOGS_DEDUP_INDEX`, `"idx_audit_logs_dedup ON audit_logs(user_id, dedup_key, timestamp)" in CREATE_AUDIT_LOGS_DEDUP_INDEX`, and `"UNIQUE" not in CREATE_AUDIT_LOGS_DEDUP_INDEX.upper()`. The docstring cites PRD 6.3 (equality, equality, range) and why it is not unique.
  - `test_audit_log_carries_dedup_key_without_breaking_construction`: defaults to `None`; carries a supplied value.
  - `test_every_added_column_is_also_declared_in_the_create` is **unchanged** and must pass (AC 1).
- **Mirror**: `tests/test_db.py:1586-1647`
- **Validate**: `pytest tests/test_db.py -q -k "dedup or every_added_column"`

### Task 6: Round-trip tests on both read shapes (AC 4)

- **File**: `tests/test_db.py`
- **Action**: UPDATE
- **Implement**: next to the `session_id` round-trip tests (`:526-600`):
  - `test_dedup_key_defaults_to_none_when_not_supplied`: insert without it → `get_audit_log(id).dedup_key is None`.
  - `test_dedup_key_round_trips`: insert with `dedup_key="k"` and a `session_id`. Assert `get_audit_log(...).dedup_key == "k"` **and** that the neighbours `session_id`, `prompt_hash` and `denied_permission` are correct, which catches a miscounted placeholder shift. Also check through `list_audit_logs()[0].dedup_key`.
  - `test_dedup_key_survives_the_batched_read`: insert one row with `dedup_key="k"` and one without. Assert `snapshot.errors == {}`, `snapshot.rows == list_audit_logs()` and `[r.dedup_key for r in snapshot.rows] == [None, "k"]`, ordered newest first as in `:597`.
- **Mirror**: `tests/test_db.py:526-600`
- **Validate**: `pytest tests/test_db.py -q -k "dedup_key"`

### Task 7: The index as built on a fresh database, and used by the lookup shape (AC 2)

- **File**: `tests/test_db.py`
- **Action**: UPDATE
- **Implement**: next to `test_init_db_creates_the_chat_indexes` (`:1712`):
  - `test_init_db_creates_the_dedup_index_with_its_columns_in_order(temp_db)`: `PRAGMA index_list(audit_logs)` includes a row named `idx_audit_logs_dedup` with `unique == 0`, and `[r["name"] for r in PRAGMA index_info(idx_audit_logs_dedup)]` ordered by `seqno` `== ["user_id", "dedup_key", "timestamp"]`.
  - `test_init_db_adds_a_nullable_dedup_key_column(temp_db)`: `PRAGMA table_info(audit_logs)` row for `dedup_key` has `type == "TEXT"`, `notnull == 0`, `dflt_value is None`.
  - `test_dedup_lookup_shape_uses_the_dedup_index(temp_db)`: insert one row, then run `EXPLAIN QUERY PLAN` over PRD 6.3's future lookup SQL (`SELECT timestamp FROM audit_logs WHERE user_id = ? AND dedup_key = ? AND timestamp >= ? AND success = 1 AND was_duplicate_blocked = 0 AND denied_permission IS NULL ORDER BY timestamp ASC LIMIT 1`). Assert `"idx_audit_logs_dedup" in plan` and `"SCAN" not in plan.upper()`. The docstring says the SQL is PRD 6.3's shape, written out here because `find_duplicate_timestamp` does not use it until STORY-007, and that this test proves the index serves that access path.
- **Mirror**: `tests/test_db.py:1711-1720`, `:2006-2022`, `:1394-1419` (`PRAGMA` row access by name)
- **Validate**: `pytest tests/test_db.py -q -k "dedup_index or dedup_key_column or lookup_shape"`

### Task 8: A pre-PRD-009 database converges, with the index created after the ALTER (AC 2)

- **File**: `tests/test_db.py`
- **Action**: UPDATE
- **Implement**:
  1. Add `_create_pre_dedup_key_database(connect, url)` after `_create_pre_chat_sessions_database` (`:307-352`). It builds the **20-column** `audit_logs` exactly as it ships before this PRD (the 19 columns + `session_id TEXT`) with no index, and inserts one row (`timestamp`, `user_id="carla@empresa.com"`, `prompt_hash="pre009"`, `role="user"`, `session_id="0f6c2e5a-9b3d-4c81-a7f2-1d5e8c9b0a34"`). The docstring follows the helper above it: the fourth of these fixtures, and the only one where `dedup_key` is the sole column in flight.
  2. In `_create_pre_chat_sessions_database`'s docstring, add a PRD-009 note: since STORY-002 this fixture has two columns in flight (`session_id`, `dedup_key`), and the tests on it still assert `session_id` by name. Isolating `dedup_key` is `_create_pre_dedup_key_database`'s job. Add the same one-line note to `test_two_init_db_calls_racing_on_session_id_both_converge`'s docstring. **Change no assertions.**
  3. `test_init_db_migrates_a_pre_dedup_key_database(uninitialized_db, db_connect)`: `init_db()`, then assert that `dedup_key` is in the columns, `idx_audit_logs_dedup` is in `PRAGMA index_list(audit_logs)`, `count_audit_logs() == 1`, `get_audit_log(1).dedup_key is None`, and `session_id` was preserved (migrated, not rewritten). Then insert a row with `dedup_key="k"` and assert it reads back. The docstring says `_add_missing_columns()` is unmodified.
  4. `test_init_db_creates_the_dedup_index_after_adding_the_column(uninitialized_db, db_connect, monkeypatch)`: pre-dedup database. Record statements through the proxy idiom from `test_init_db_issues_no_alter_when_schema_is_current` (`:152-173`), or an `_install` + `_DelegatingConnection` subclass that appends SQL. Assert that the index of the `ALTER TABLE audit_logs ADD COLUMN dedup_key` statement is **less than** the index of `CREATE_AUDIT_LOGS_DEDUP_INDEX`, and that there is exactly one `_session()` connection plus the `SELECT 1` probe. This locks the story's "after `_add_missing_columns`, inside the same block" rule so it cannot quietly regress.
  5. In `test_init_db_issues_no_alter_when_schema_is_current` (`:188-194`), add `CREATE_AUDIT_LOGS_DEDUP_INDEX` to the tuple of DDL that must be issued, with `# PRD-009 STORY-002`. The no-ALTER and two-connection assertions are unchanged and must pass (AC 3).
- **Mirror**: `tests/test_db.py:307-352`, `:1833-1874`, `:125-194`, `:2544-2596`
- **Validate**: `pytest tests/test_db.py -q -k "pre_dedup_key or dedup_index_after or no_alter_when_schema_is_current or pre_chat_sessions"`

### Task 9: Two `init_db()` calls racing on the `dedup_key` ALTER converge (AC 3)

- **File**: `tests/test_db.py`
- **Action**: UPDATE
- **Implement**: directly after `test_two_init_db_calls_racing_on_session_id_both_converge` (`:2710-2750`), add `test_two_init_db_calls_racing_on_dedup_key_both_converge(uninitialized_db, db_connect, monkeypatch)`, a structural copy using `_create_pre_dedup_key_database`, `threading.Barrier(2, timeout=30)`, `_install(... _GatedConnection ...)` and `_run_concurrently(2, init_db)`. Assertions:
  - `not failures`
  - `columns.count("dedup_key") == 1`
  - `set(AUDIT_LOGS_ADDED_COLUMNS) <= set(columns)`
  - `idx_audit_logs_dedup` present exactly once in `PRAGMA index_list(audit_logs)`. Both threads ran `CREATE INDEX IF NOT EXISTS`, so this proves that statement is race-safe too.
  - `count_audit_logs() == 1`, `get_audit_log(1).user_id == "carla@empresa.com"`, `.dedup_key is None`
  
  The docstring says: PRD-009 STORY-002 AC 3; `dedup_key` is the only column in flight; `_add_missing_columns()` is unmodified; evidence, not new code.
- **Mirror**: `tests/test_db.py:2710-2750`
- **Validate**: `pytest tests/test_db.py -q -k "racing"` (run it 3× to catch a flaky interleave: `for i in 1 2 3; do pytest tests/test_db.py -q -k racing || break; done`)

### Task 10: Confirm the untouched surfaces (AC 5)

- **Files**: none edited
- **Action**: VERIFY
- **Implement**:
  - `git diff --stat -- app/models/schemas.py app/routers app/services scripts tests/test_stats_router.py tests/test_audit_router.py tests/test_pii_redaction_integration.py tests/test_two_instance_smoke.py tests/test_query_router.py tests/test_integration.py` → empty.
  - `pytest tests/test_audit_router.py tests/test_stats_router.py tests/test_pii_redaction_integration.py tests/test_admin_models.py tests/test_history_off_integration.py tests/test_migrate_to_turso_cli.py tests/test_two_instance_smoke.py -q` → green. `test_audit_router.py:75-89` and `test_pii_redaction_integration.py:195-210` pin the `/audit` entry key set, so passing them unmodified is the D5 proof.
  - Full suite: `pytest tests/ -q`.
- **Validate**: all of the above green; diff stat empty for the listed paths

---

## End-to-End Tests

For `/implement` to execute:

- [ ] Start libSQL dev server (`docker start harness-libsql-dev`), run `pytest tests/test_db.py -q` → green, including every new `dedup` test
- [ ] Fresh DB: `init_db()` → `PRAGMA index_info(idx_audit_logs_dedup)` = `user_id, dedup_key, timestamp`; `dedup_key` nullable TEXT
- [ ] Pre-PRD DB (20 columns, one row): `init_db()` → column added, row reads `dedup_key=None`, index present, new insert with a key round-trips
- [ ] Steady state: second `init_db()` issues no `ALTER`, uses one `_session()` connection + probe
- [ ] Race: two gated `init_db()` on a pre-PRD DB → no failures, one `dedup_key` column, one index (run 3×)
- [ ] `insert_audit_log(AuditLog(..., dedup_key="k"))` → `get_audit_log`, `list_audit_logs` and `summary_snapshot().rows` all return `"k"`; `summary_snapshot().errors == {}`
- [ ] `GET /audit` and `GET /stats` response shapes unchanged: `tests/test_audit_router.py`, `tests/test_stats_router.py`, `tests/test_pii_redaction_integration.py` pass unmodified
- [ ] Full suite `pytest tests/ -q` green. On mass fixture errors, `docker restart harness-libsql-dev` and re-run; a single scattered `no such table` in an unrelated test is the known environment flake, so re-run and confirm it moves

---

## Validation

```bash
docker start harness-libsql-dev   # or the docker run command in tests/conftest.py:29-30
pytest tests/test_db.py -q
pytest tests/test_migrate_to_turso_cli.py tests/test_audit_router.py tests/test_stats_router.py tests/test_pii_redaction_integration.py tests/test_history_off_integration.py tests/test_two_instance_smoke.py -q
pytest tests/ -q
git diff --stat main -- app/ tests/ scripts/
git diff --stat -- app/models/schemas.py app/routers app/services scripts   # must be empty
```

No frontend and no server-start change, so the template's `npm run lint` and `uvicorn` checks don't apply. `init_db()` is exercised by the fixtures themselves, and `tests/test_two_instance_smoke.py` boots real instances through it.

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Index statement placed before `_add_missing_columns` → a pre-PRD database fails boot with `no such column: dedup_key` (PRD Risk 2) | Task 2 places it on the next line; Task 8.3 (pre-PRD migration) fails if it moves, and Task 8.4 asserts the statement order explicitly |
| `json_object` in `_SUMMARY_SQL` not updated → `KeyError` on every `summary_snapshot()` | Task 3 edits the mapper and the SQL together; Task 6's batched-read test asserts `errors == {}` and the value |
| Miscounted `VALUES` placeholders shift every later value | Task 3 counts 20/20/20; Task 6 asserts neighbouring fields on the same row |
| Pinned exact-set tests break (3 known) | Task 4 updates each with a PRD-009 citation; no must-pass-unmodified file is among them |
| The PRD-008 race fixture silently stops isolating `session_id` | Task 8.1–8.2 adds a dedup-only fixture and records the two-in-flight fact in the old docstrings, without changing assertions |
| `PRAGMA index_list` / `index_info` unsupported or shaped differently over libSQL Hrana | `PRAGMA table_info` already works through the same client. If the index PRAGMAs misbehave, fall back to `SELECT sql FROM sqlite_master WHERE type='index' AND name='idx_audit_logs_dedup'` and assert the column text, and record the deviation in the report |
| SQLite planner picks a scan on a tiny table in the EXPLAIN test | `idx_audit_logs_dedup` is the only index on `audit_logs`, and equality on its leading two columns makes it the only non-scan plan. If the planner still scans, seed a few rows before `EXPLAIN` |
| `scripts/migrate_to_turso.py::_audit_log_from_source` omits `session_id` (and will omit `dedup_key`) | Existing gap, out of scope: legacy SQLite sources never carry either column, so both sides default to `None`. Noted for the report, not fixed here |
| libSQL dev server degrades across repeated runs | Restart the container on mass fixture errors; don't bisect code |

---

## Acceptance Criteria

(Copied from story `STORY-002`)

- [ ] Given [app/db/models.py](../../../app/db/models.py), when it is read, then `dedup_key TEXT` appears in **both** `CREATE_AUDIT_LOGS_TABLE` and `AUDIT_LOGS_ADDED_COLUMNS` (nullable, no default), `CREATE_AUDIT_LOGS_DEDUP_INDEX` is `CREATE INDEX IF NOT EXISTS idx_audit_logs_dedup ON audit_logs(user_id, dedup_key, timestamp)`, and `AuditLog` gains `dedup_key: Optional[str] = None`. `test_every_added_column_is_also_declared_in_the_create` passes.
- [ ] Given `init_db()`, when it runs on a fresh database and on a database created before this PRD, then the column exists, existing rows read `NULL`, and `PRAGMA index_list(audit_logs)` includes `idx_audit_logs_dedup` with columns `(user_id, dedup_key, timestamp)` in that order. The index statement runs **after** `_add_missing_columns(conn)`, inside the same `_session()` block.
- [ ] Given a schema that is already current, when `init_db()` runs again, then `test_init_db_issues_no_alter_when_schema_is_current` passes. Given two `init_db()` calls racing on the `dedup_key` `ALTER`, then both converge, asserted the way `test_two_init_db_calls_racing_on_session_id_both_converge` asserts it for `session_id`.
- [ ] Given `insert_audit_log(AuditLog(..., dedup_key="k"))`, when the row is read back through `get_audit_log` **and** through `summary_snapshot().rows`, then `dedup_key == "k"`. An entry built without it reads back `None`.
- [ ] Given `GET /audit` and `GET /stats`, when called, then their response shapes are unchanged: `AuditQueryEntry` gains no field (D5). The full suite passes, including [tests/test_stats_router.py](../../../tests/test_stats_router.py) and [tests/test_audit_router.py](../../../tests/test_audit_router.py) unmodified.
- [ ] All tasks completed
- [ ] Full test suite passes (`pytest tests/ -q`), since this repo has no frontend lint
- [ ] `init_db()` boots cleanly on fresh, pre-PRD and concurrent databases (the backend-start equivalent for a schema story)
- [ ] Follows existing patterns (PRD-008 STORY-003 convergence; `_add_missing_columns` unmodified)
