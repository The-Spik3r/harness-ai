---
story: STORY-003
prd: PRD-008
slug: init-db-tables-and-audit-column
title: "init_db() creates both transcript tables and converges the audit_logs.session_id column"
type: NEW_CAPABILITY
complexity: LOW
epic_branch: epic/PRD-008-chat-sessions
created: 2026-09-03
---

# Plan: init_db() creates both transcript tables and converges the audit_logs.session_id column

## Summary

Teach `init_db()` to execute the four DDL constants STORY-002 declared and left unreferenced — `CREATE_CHAT_SESSIONS_TABLE`, `CREATE_CHAT_SESSIONS_USER_INDEX`, `CREATE_CHAT_MESSAGES_TABLE`, `CREATE_CHAT_MESSAGES_SESSION_INDEX` — inside the same `_session()` block that already creates `audit_logs` and `users` (`app/db/database.py:474-478`). Four imports and four `conn.execute(...)` lines. No new function, no edit to `_add_missing_columns`, no change to the migration rule.

Three facts from exploration shape the diff, and two of them are not in the story text:

1. **The `session_id` column already converges.** `_add_missing_columns()` iterates `AUDIT_LOGS_ADDED_COLUMNS` (`app/db/database.py:519`), and STORY-002 put `"session_id": "TEXT"` in that dict (`app/db/models.py:52`). So AC 3 and AC 4 are already *true* on this branch — the whole of this story's work on them is **assertion**, not implementation. The story says so ("Assert it, do not assume it"), and the existing concurrency tests cover it only *generically* (`set(AUDIT_LOGS_ADDED_COLUMNS) <= set(columns)`), which passes whether or not `session_id` is the column that raced. This plan adds tests that name `session_id` and fixture a database missing exactly it.

2. **One test outside `tests/test_db.py` must change, and there is no way around it.** `tests/test_two_instance_smoke.py:484` asserts `schema["tables"] == ["audit_logs", "users"]` — exact equality on the sorted table list each child instance records at boot. The moment `init_db()` creates two more tables, that assertion is false. It is a factual pin, not a regression. `test_two_instance_smoke.py` is **not** on PRD Section 15's must-pass-unmodified list (that list is `test_query_router`, `test_integration`, `test_route_reservations`, `test_admin_auth`, `test_audit_router`, `test_stats_router`, `test_rbac`, `test_summary`), and PRD-006's byte-equality guard in `tests/test_untouched_app.py:84-90` does not pin it either. Task 4 extends the literal to the four sorted names and adds the new column assertions, in the same style as the `users` assertion two lines below it. Story AC 7's "every other suite passes unmodified" is met in spirit and cannot be met in letter; the deviation is recorded here rather than discovered during `/implement`.

3. **`scripts/migrate_to_turso.py` needs nothing.** It calls `init_db()` at `:680` and will now create two empty extra tables at the destination, but its `_TABLES = ("audit_logs", "users")` (`:64`) drives what it *copies*, not what must exist, and `test_dest_columns_match_the_ddl` (`tests/test_migrate_to_turso_cli.py:155`) pins the `audit_logs` and `users` DDL only. Verified, not assumed. No edit.

There is no linter and no formatter in this repo — CI runs `pip install -r requirements.txt` then `pytest -q` — so "validate" means the suite, and the suite needs the local libSQL dev server documented at `tests/conftest.py:26-31`.

## User Story

As a **maintainer**
I want the new schema created by the same idempotent bootstrap every other table uses
So that a hot reload, a second instance, and a fresh database all converge on the same shape without a migration tool.

## Story Reference

- Story file: `.agents/stories/PRD-008-chat-sessions/STORY-003-init-db-tables-and-audit-column.md`
- PRD: `.agents/PRDs/PRD-008-chat-sessions/PRD.md` — Section 4 (Schema), Section 8, Section 11 (init_db assertions), Section 12 Phase 1, Risk 7
- Depends on: STORY-002 (`e3bb0c7`, done) — the four constants and the `AUDIT_LOGS_ADDED_COLUMNS` entry
- Risk 7 verbatim: "`init_db()` gains two more `CREATE TABLE` statements and one more `ALTER` candidate. It runs at import time on every Reflex hot reload and on every instance boot… *Mitigation*: the tables use `CREATE TABLE IF NOT EXISTS` and are therefore idempotent by construction; the one new column goes through `_add_missing_columns`, which already treats a duplicate-column loss as convergence."

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY (wiring only — four executes, no new function) |
| Complexity | LOW |
| Systems Affected | `app/db/database.py`, `tests/test_db.py`, `tests/test_two_instance_smoke.py` |
| Story | STORY-003 |
| PRD | PRD-008 |
| Epic Branch | `epic/PRD-008-chat-sessions` (commit directly on this branch) |

---

## Skills In Use

`.agents/skills/` was listed in full. It holds exactly one skill:

| Skill | Applies? | Reason |
|-------|----------|--------|
| `frontend-design` | **No** | Scoped by its own `description` to "distinctive, intentional visual design when building new UI or reshaping an existing one." This story edits `app/db/database.py` and two test modules. It renders nothing. |

The story's `skills:` frontmatter is `[]` and its Technical Notes reach the same conclusion. **No skill constrains any task below**, and no task names one. (`reflex-docs` / `reflex-process-management` govern `chat_ui/` work — Phases 3 and 4. Nothing here imports Reflex.)

---

## Patterns to Follow

### The bootstrap block — one `_session()`, CREATE then its index

```python
# SOURCE: app/db/database.py:470-478
    if not settings.DB_BOOTSTRAP_ENABLED:
        return

    check_database_reachable()
    with _session() as conn:
        conn.execute(CREATE_AUDIT_LOGS_TABLE)
        _add_missing_columns(conn)
        conn.execute(CREATE_USERS_TABLE)
        conn.execute(CREATE_USERS_TOKEN_HASH_INDEX)
```

### Table-existence assertion

```python
# SOURCE: tests/test_db.py:1230-1235
def test_init_db_creates_users_table(temp_db):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
        ).fetchone()
    assert row is not None
```

### PRAGMA column-set assertion, with `notnull` / `dflt_value` / `pk` pinned

```python
# SOURCE: tests/test_db.py:1239-1265
    with get_connection() as conn:
        info = list(conn.execute("PRAGMA table_info(users)"))

    columns = {row["name"]: row for row in info}
    assert set(columns) == {"user_id", "role", "token_hash", "active", "created_at"}
    for name, row in columns.items():
        assert row["notnull"] == 1, f"{name} must be NOT NULL"
    assert columns["active"]["dflt_value"] == "1"
    assert columns["user_id"]["pk"] == 1
```

### The pre-migration fixture idiom — raw DDL through `db_connect`, one surviving row

```python
# SOURCE: tests/test_db.py:257-277 (_create_pre_rbac_database)
def _create_pre_rbac_database(connect, url) -> None:
    legacy = connect(url)
    legacy.execute("""CREATE TABLE audit_logs ( ... )""")
    legacy.execute(
        "INSERT INTO audit_logs (timestamp, user_id, prompt_hash) VALUES (?, ?, ?)",
        ("2026-08-20T09:00:00Z", "ana@empresa.com", "xyz789"),
    )
    legacy.commit()
    legacy.close()
```

### The recording proxy — what `init_db()` actually issued

```python
# SOURCE: tests/test_db.py:124-166
    class _RecordingConnection:
        def __init__(self, conn): self._conn = conn
        def __enter__(self): self._conn.__enter__(); return self
        def __exit__(self, *exc_info): return self._conn.__exit__(*exc_info)
        def execute(self, sql, *parameters):
            statements.append(sql)
            return self._conn.execute(sql, *parameters)

    monkeypatch.setattr(database, "get_connection",
                        lambda: _RecordingConnection(real_get_connection()))
    init_db()
    assert statements, "the proxy captured nothing -- the patch did not take"
    assert not any("ALTER" in sql.upper() for sql in statements), statements
```

### The forced race — a barrier released after `PRAGMA table_info` returns

```python
# SOURCE: tests/test_db.py:1877-1889 (_GatedConnection) and :2007-2020
    _create_pre_pii_database(db_connect, uninitialized_db)
    gate = threading.Barrier(2, timeout=30)
    _install(monkeypatch, lambda conn: _GatedConnection(conn, gate))

    failures = _run_concurrently(2, init_db)
    assert not failures, f"a concurrent init_db() raised: {failures}"
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/db/database.py` | UPDATE | Import the four chat DDL constants; execute them in `init_db()`'s existing `_session()` block |
| `tests/test_db.py` | UPDATE | PRAGMA-level assertions for both tables and both indexes; the pre-PRD-008 migration case; the `session_id`-named race; the bootstrap-off case; extend the no-ALTER test to prove one connection |
| `tests/test_two_instance_smoke.py` | UPDATE | One literal: the boot-time table list is now four tables (see Summary point 2) |

Files deliberately **not** changed, each verified:

- `app/db/models.py` — STORY-002 owns every constant this story executes.
- `_add_missing_columns()` — it iterates the mapping; `session_id` is already in it. The story says stop and ask why if you find yourself editing it. Nothing here requires it.
- `scripts/migrate_to_turso.py` — see Summary point 3.
- `app/main.py`, `chat_ui/chat_ui/chat_ui.py`, `scripts/manage_users.py` — all four `init_db()` call sites are unchanged by construction; that is the point of putting the work inside the function.

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Import the four chat DDL constants

- **File**: `app/db/database.py`
- **Action**: UPDATE
- **Implement**: Extend the existing `from app.db.models import (...)` block (`app/db/database.py:19-26`) with `CREATE_CHAT_MESSAGES_SESSION_INDEX`, `CREATE_CHAT_MESSAGES_TABLE`, `CREATE_CHAT_SESSIONS_TABLE`, `CREATE_CHAT_SESSIONS_USER_INDEX`. Keep the block's existing ordering convention: `CREATE_*` constants alphabetically, then the dataclasses (`AuditLog`, `User`). Do **not** import `ChatSession` or `StoredMessage` — nothing in this story constructs one, and an unused import is a claim that something does.
- **Mirror**: `app/db/database.py:19-26`
- **Validate**: `python -c "import app.db.database"` (with `DATABASE_URL`, `OPENROUTER_API_KEY`, `ADMIN_TOKEN` set) — imports without error.

### Task 2: Execute the four statements in `init_db()`'s existing `_session()` block

- **File**: `app/db/database.py`
- **Action**: UPDATE
- **Implement**: Inside the `with _session() as conn:` block at `:474`, after the two `users` statements, append four executes in schema order — table, then its index, for each:

  ```python
        conn.execute(CREATE_CHAT_SESSIONS_TABLE)
        conn.execute(CREATE_CHAT_SESSIONS_USER_INDEX)
        conn.execute(CREATE_CHAT_MESSAGES_TABLE)
        conn.execute(CREATE_CHAT_MESSAGES_SESSION_INDEX)
  ```

  **Same block, not a second one.** One `_session()` is one transaction and one connection; a second block would mean a boot that can commit half a schema, and would add round trips on a path that runs on every Reflex hot reload (Risk 7). `_add_missing_columns(conn)` stays exactly where it is, immediately after the `audit_logs` CREATE — it is audit-logs-specific and the chat tables need no equivalent, for the reason `test_init_db_adds_users_table_to_pre_rbac_database` (`tests/test_db.py:1295-1317`) already records: `CREATE TABLE IF NOT EXISTS` reaches an existing database, unlike a new column.

  Extend `init_db()`'s docstring by one short paragraph naming what the block now builds and why nothing else moved: the two transcript tables are idempotent by construction, so Risk 7's cost in steady state is four extra no-op statements on one already-open connection, and the one new *column* rides the `_add_missing_columns` path that was already there. Do not restate the concurrency argument — `_add_missing_columns`' own docstring (`:481-511`) owns it, verbatim, and duplicating it is how two copies come to disagree.
- **Mirror**: `app/db/database.py:474-478`
- **Validate**: `pytest tests/test_db.py -q`

### Task 3: PRAGMA-level and migration coverage in `tests/test_db.py`

- **File**: `tests/test_db.py`
- **Action**: UPDATE
- **Implement**: The four chat constants are already imported at `tests/test_db.py:50-60` — no import change is needed for them. Add a new section, `# PRD-008 STORY-003: init_db() executes the transcript schema`, placed **after** the STORY-002 constant-level block that ends around `:1478`, so the file reads declaration-then-execution in story order. The comment block at `:1319-1326` says STORY-003 owns the PRAGMA assertions; add one line there pointing forward to the new section, so the two halves find each other.

  Tests to write, one claim each:

  1. `test_init_db_creates_the_chat_tables(temp_db)` — both names present in `sqlite_master`. **(AC 1)**
  2. `test_init_db_creates_the_chat_indexes(temp_db)` — `idx_chat_sessions_user_updated` and `idx_chat_messages_session_id` present as `type='index'`. **(AC 1)**
  3. `test_chat_sessions_table_matches_its_ddl(temp_db)` — `PRAGMA table_info(chat_sessions)`: column set is exactly the five names, every one `notnull == 1`, `session_id` has `pk == 1` and the other four `pk == 0`. Mirrors `test_users_schema_matches_expected_columns`. **(AC 6)**
  4. `test_chat_messages_table_matches_its_ddl(temp_db)` — `PRAGMA table_info(chat_messages)`: compare `[row["name"] for row in info]` against `_declared_columns(CREATE_CHAT_MESSAGES_TABLE)` (the helper at `:1344`) **as an ordered list**, so the table and the constant are pinned to each other mechanically rather than by a second hand-typed literal that can drift. Then assert `pii_redacted` has `dflt_value == "0"` and `notnull == 1`, and that `id` is `pk == 1`. **(AC 6)**
  5. `test_chat_messages_table_stores_no_humanized_duplicate_copy(temp_db)` — parametrized over `("duplicate_relative_info", "duplicate_release_info")`, asserting absence from `PRAGMA table_info(chat_messages)`. The constant-level twin at `:1404-1417` asserts the omission in the DDL string; this asserts it in the built table, which is what AC 6 names. Carry PRD Section 6's sentence into the docstring, as its twin does — an assertion of an omission that does not say why is one a future reader deletes. **(AC 6)**
  6. `test_init_db_is_idempotent_for_the_chat_tables(temp_db)` — call `init_db()` three more times; both tables still exist, both indexes still exist, and `PRAGMA table_info` for each still has no duplicated column name. Mirrors `test_init_db_is_idempotent_for_users_table` (`:1277`). **(AC 2, Risk 7)**
  7. `test_init_db_adds_the_chat_tables_to_a_pre_chat_database(uninitialized_db, db_connect)` — build with the existing `_create_pre_pii_database` helper (`:167`, `audit_logs` only), run `init_db()`, assert `{"audit_logs", "users", "chat_sessions", "chat_messages"} <= tables`, and that the legacy audit row survives (`count_audit_logs() == 1`, `get_audit_log(1).user_id == "juan@empresa.com"`). Mirrors `:1295`. **(AC 1)**
  8. `_create_pre_chat_sessions_database(connect, url)` — a **new** fixture helper beside the two existing ones, building `audit_logs` at its exact pre-PRD-008 shape: the 17 pre-RBAC columns **plus** `role TEXT` and `denied_permission TEXT`, and no `session_id`. That is the shape `main` ships today, and it is the only fixture that isolates `session_id` as the single missing column. Insert one row. Its docstring should say what distinguishes it from `_create_pre_rbac_database`, the way that helper's docstring distinguishes itself from `_create_pre_pii_database`.
  9. `test_init_db_migrates_a_pre_chat_sessions_database(uninitialized_db, db_connect)` — the helper above, then `init_db()`: `session_id` is in `PRAGMA table_info(audit_logs)`, `count_audit_logs() == 1`, `get_audit_log(1).session_id is None`, and `get_audit_log(1).user_id` is unchanged — the existing row took `NULL` and was not rewritten. Then insert a new `AuditLog` carrying a `session_id` and read it back, proving the upgraded table accepts writes, exactly as `test_init_db_migrates_pre_rbac_database` (`:278`) does. **(AC 3)**
  10. `test_two_init_db_calls_racing_on_session_id_both_converge(uninitialized_db, db_connect, monkeypatch)` — the helper from (8) plus the existing `_GatedConnection` / `_install` / `_run_concurrently` machinery (`:1877`, `:1911`, `:1930`), so both threads hold the same stale `PRAGMA` view and both attempt `ADD COLUMN session_id`. Assert no failures, `session_id` present, and `columns.count("session_id") == 1`. **This is AC 4's "assert it, do not assume it"**: the two existing race tests use the pre-PII fixture, where five columns are missing and the assertion is the generic `set(AUDIT_LOGS_ADDED_COLUMNS) <= set(columns)` — they would pass unchanged if `session_id` were never involved. Here it is the *only* column in flight, so the test fails if the new column ever leaves the converging path. The docstring must say that `_add_missing_columns` is unmodified and that this test is evidence for an existing guarantee, not for new code. **(AC 4)**
  11. `test_bootstrap_disabled_creates_no_chat_tables(database_url, monkeypatch)` — set `settings.DB_BOOTSTRAP_ENABLED = False` against the reachable test endpoint on an empty database, call `init_db()`, and assert `sqlite_master` holds no table at all. The existing `test_bootstrap_disabled_skips_the_guard_and_the_schema` (`:2351`) points at an unreachable URL and therefore proves the *guard* was skipped but can never inspect a schema; this one proves the *schema work* was skipped, which is the half AC 5 names. Cross-reference the two in the docstring. **(AC 5)**

  Extend the existing `test_init_db_issues_no_alter_when_schema_is_current` (`:124`) rather than adding a near-duplicate: count connections (an `__enter__` counter on its `_RecordingConnection`, or a counter in the patched lambda) and assert, alongside the unchanged no-ALTER assertion, that (a) the run used exactly one connection, and (b) `statements` contains all four chat DDL statements. That is the mechanical proof of AC 1's "inside the **same** `_session()` block", and it keeps AC 2's assertion in the one test the PRD names. **(AC 1, AC 2)**
- **Mirror**: `tests/test_db.py:1232-1317` (users PRAGMA + idempotence + pre-existing database), `:278-306` (migration), `:1990-2032` (the forced race), `:124-166` (recording proxy)
- **Validate**: `pytest tests/test_db.py -q` — the 124 pre-existing cases plus the new ones, all green.

### Task 4: Correct the boot-time table pin in the two-instance smoke test

- **File**: `tests/test_two_instance_smoke.py`
- **Action**: UPDATE
- **Implement**: At `:484`, change `assert schema["tables"] == ["audit_logs", "users"]` to the four sorted names — `["audit_logs", "chat_messages", "chat_sessions", "users"]` — and add, beneath the existing `users` column assertion (`:490-496`), a sorted-column-list assertion for `chat_sessions` and a containment assertion for `chat_messages`' five required columns (`session_id`, `kind`, `content`, `created_at`, `id`). Do **not** spell all fifteen `chat_messages` columns there: the point of that test is that **two instances converged on the same schema**, `tests/test_db.py` Task 3(4) already pins the full shape against the DDL, and a fifteen-name literal in a second file is a maintenance liability that adds nothing to the claim.

  Add a one-line comment naming PRD-008 STORY-003 as the reason the list grew — the existing comment at `:485-486` ("a column added to the schema later must make this test stronger rather than leave it quietly passing") is the standard this edit is held to.

  **This is a sanctioned deviation from AC 7's "every other suite passes unmodified".** The assertion is an exact-equality pin on a table set this story deliberately changes; no implementation choice keeps it true. `test_two_instance_smoke.py` is absent from PRD Section 15's unmodified list and from `tests/test_untouched_app.py:84-90`'s byte-equality pin, and STORY-021 already owns extending this file. Record it in the story report under Deviations.
- **Mirror**: `tests/test_two_instance_smoke.py:481-496`
- **Validate**: `pytest tests/test_two_instance_smoke.py -q` (spawns child instances; slower than the rest)

### Task 5: Full-suite regression check against the measured baseline

- **File**: — (no edit)
- **Action**: VERIFY
- **Implement**: Run the whole suite and compare the failure list against STORY-002's recorded baseline: **7 failures, all in `tests/test_untouched_app.py`, all pre-existing** — PRD-006-scoped byte-equality guards that PRD-007 and PRD-008 have legitimately invalidated, including `test_the_pinned_suites_are_byte_unmodified[tests/test_db.py]`, which pins the very file Task 3 edits and was already failing before this story. Any *eighth* failure, or any failure outside that module, belongs to this story. Confirm in particular that the eight suites PRD Section 15 pins (`test_query_router`, `test_integration`, `test_route_reservations`, `test_admin_auth`, `test_audit_router`, `test_stats_router`, `test_rbac`, `test_summary`) and `tests/test_migrate_to_turso_cli.py` are green with no edit.
- **Validate**: `pytest -q`

---

## End-to-End Tests

- [ ] Against an empty database, `init_db()` leaves `audit_logs`, `users`, `chat_sessions`, `chat_messages` and the three indexes present
- [ ] `init_db(); init_db(); init_db()` issues no `ALTER` on the second and third runs and raises nothing
- [ ] Against a database at today's `main` shape, `init_db()` adds `session_id` to `audit_logs`, leaves every existing row's other fields untouched, and gives them `NULL`
- [ ] Two threads racing the `session_id` `ADD COLUMN` from the same stale `PRAGMA` view both return; the column exists exactly once
- [ ] `DB_BOOTSTRAP_ENABLED=False` returns before any statement — no table is created against a reachable, empty database
- [ ] `python -c "import chat_ui.chat_ui"` with `DB_BOOTSTRAP_ENABLED=false` and no reachable database succeeds (the Dockerfile builder stage's case, AC 5)
- [ ] Two child instances booting simultaneously record the same four-table schema

---

## Validation

```bash
# The local libSQL dev server the suite requires (tests/conftest.py:26-31)
docker run -d --name harness-libsql-dev -p 8080:8080 -e SQLD_NODE=primary \
  ghcr.io/tursodatabase/libsql-server@sha256:6dd3eb276d9d3604e4a48ac4a999a2e267814732d57d7e94c04ba71482333a67

pytest tests/test_db.py -q
pytest tests/test_two_instance_smoke.py -q
pytest tests/test_migrate_to_turso_cli.py -q     # must pass with no edit
pytest -q                                        # 7 pre-existing failures, all in test_untouched_app.py

# AC 5, the builder stage, without a database at all
DB_BOOTSTRAP_ENABLED=false DATABASE_URL=http://127.0.0.1:1 \
OPENROUTER_API_KEY=x ADMIN_TOKEN=x python -c "import chat_ui.chat_ui"
```

There is no lint step: CI runs `pip install -r requirements.txt` then `pytest -q`.

---

## Risks

| Risk | Mitigation |
|------|-----------|
| A second `_session()` block for the chat tables — plausible-looking, and wrong | Task 2 puts all four executes in the existing block; the extended no-ALTER test counts connections, so a split block fails a test rather than a review |
| Someone "finishes" the migration by teaching `_add_missing_columns` about the chat tables | New tables need no ALTER path; `test_init_db_adds_the_chat_tables_to_a_pre_chat_database` proves `CREATE TABLE IF NOT EXISTS` is sufficient, and the story says to stop and ask why |
| The four extra statements cost something on every Reflex hot reload (Risk 7) | They are `IF NOT EXISTS` no-ops on one already-open connection inside an existing transaction — no extra handshake, no ALTER. The no-ALTER test is the steady-state guard |
| Another exact-equality schema pin exists that exploration missed | Searched: `sqlite_master` across `tests/` and `scripts/`, and the literals `{"audit_logs", "users"}` / `("audit_logs", "users")`. Four sites found — `tests/conftest.py:99` (a `DROP` loop, shape-agnostic), `tests/test_db.py:1308` (containment `<=`, unaffected), `tests/test_migrate_to_turso_cli.py:151` (a `COUNT(*)` over the two tables it copies, unaffected), and `tests/test_two_instance_smoke.py:484` (the one Task 4 fixes) |
| The suite cannot run without the libSQL dev server, and a skipped storage suite still reports green | `tests/conftest.py:_libsql_endpoint` calls `pytest.exit` rather than skipping. The Validation block starts the container |

---

## Acceptance Criteria

(Copied from story `STORY-003`)

- [ ] `init_db()` executes `CREATE_CHAT_SESSIONS_TABLE`, `CREATE_CHAT_MESSAGES_TABLE` and both indexes inside the **same** `_session()` block that already creates `audit_logs` and `users`
- [ ] A database that already has every table issues **no `ALTER`** on a re-run — `test_init_db_issues_no_alter_when_schema_is_current` passes with the new column present
- [ ] A database created before this PRD gains `session_id` on `audit_logs` via `_add_missing_columns`; every existing row takes `NULL` and no row is rewritten
- [ ] Two processes racing the `session_id` `ALTER` both converge — asserted through the existing `_is_duplicate_column` path, which needs no change
- [ ] `settings.DB_BOOTSTRAP_ENABLED=False` returns before touching the database; the Dockerfile builder stage still imports `chat_ui.chat_ui` with no reachable database
- [ ] `PRAGMA table_info(chat_messages)` after a fresh `init_db()` matches STORY-002's DDL exactly; `duplicate_relative_info` and `duplicate_release_info` are absent
- [ ] `tests/test_db.py` passes with new coverage for both tables and the new column; every other suite passes unmodified **except `tests/test_two_instance_smoke.py`**, whose exact-equality table pin this story necessarily updates (see Task 4)
- [ ] All tasks completed
- [ ] Backend imports without error
- [ ] Follows existing patterns
