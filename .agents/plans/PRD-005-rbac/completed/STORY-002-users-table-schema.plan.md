---
story: STORY-002
prd: PRD-005
slug: users-table-schema
title: users table schema and CRUD helpers
type: NEW_CAPABILITY
complexity: LOW
epic_branch: epic/PRD-005-rbac        # all stories commit here, no per-story branch
created: 2026-08-28
---

# Plan: users table schema and CRUD helpers

## Summary

This story gives identity a storage home. It adds a `users` table to the *existing* SQLite database — no second file, no ORM, no new dependency — plus the read/write helpers that STORY-003 (identity resolution), STORY-004 (bootstrap CLI) and STORY-016 (startup guard) will call. The work is deliberately **storage only**: this layer stores an opaque `token_hash` string and never generates, hashes, or compares a credential. Token generation (`secrets.token_urlsafe(32)`) and SHA-256 hashing are STORY-003's scope, and keeping them out of `app/db/` is what stops the database layer from becoming a second authorization surface. Structurally the change is small and additive: two constants and a `User` dataclass in `app/db/models.py`, eight helper functions in `app/db/database.py` written to the exact convention every existing helper follows (one `with get_connection() as conn:`, `sqlite3.Row`, parameterized SQL), two extra statements in `init_db()`, and eighteen tests in `tests/test_db.py`. Nothing that already exists changes behavior — `audit_logs`, the additive-migration mechanism STORY-001 hardened, and all 251 currently-passing tests are untouched.

## User Story

As a maintainer
I want a `users` table with CRUD helpers in the existing SQLite database
So that identity has a storage home without adding a dependency or a second service

## Story Reference

- Story file: `.agents/stories/PRD-005-rbac/STORY-002-users-table-schema.md`
- PRD: `.agents/PRDs/PRD-005-rbac/PRD.md` — Sections 4 (In Scope), 6 (Core Architecture), 8 (Technology Stack)
- Upstream plan: `.agents/plans/PRD-005-rbac/completed/STORY-001-additive-audit-log-migration.plan.md` — its Design Note 7 and Handoff section scope this story precisely

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY (new table + new helpers; no existing behavior modified) |
| Complexity | LOW |
| Systems Affected | `app/db/models.py`, `app/db/database.py`, `tests/test_db.py` |
| Story | STORY-002 |
| PRD | PRD-005 |
| Epic Branch | `epic/PRD-005-rbac` (commit directly on this branch) |

**Dependency status**: `depends_on: [STORY-001]` — **satisfied**. STORY-001 is `status: done`, commit `936cff8`, report at `.agents/reports/PRD-005-rbac/STORY-001-additive-audit-log-migration.report.md`. In practice this story consumes nothing from STORY-001's migration mechanism (Design Note 1); the dependency is a sequencing one, and it is met.

**Blocks**: STORY-003 (needs `find_user_by_token_hash`), STORY-016 (needs `count_active_users`). STORY-004's CLI is a further consumer via STORY-003.

---

## Skills In Use

None.

`.agents/skills/` contains exactly one skill, `frontend-design`, whose frontmatter description scopes it to *"distinctive, intentional visual design when building new UI or reshaping an existing one"*. This story touches `app/db/` and `tests/` only — there is no UI surface anywhere in its diff — so it does not apply. The story's `skills:` frontmatter field is `[]`, consistent with that reading. No other `SKILL.md` exists in the repository to match against the story domain.

*(The PRD Appendix states `.agents/skills/` does not exist in this repository. It does — it is simply irrelevant here. Same note as STORY-001's plan.)*

---

## Patterns to Follow

Every snippet below is copied from the current branch. The helpers in this story must be indistinguishable in shape from these.

### Schema constants and dataclass live in `app/db/models.py`
```python
# SOURCE: app/db/models.py:5-24, 41-59
CREATE_AUDIT_LOGS_TABLE = """
CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    user_id TEXT NOT NULL,
    ...
)
"""

@dataclass
class AuditLog:
    timestamp: str
    user_id: str
    prompt_hash: str
    device: Optional[str] = None
    ...
    was_duplicate_blocked: bool = False   # bool in Python, INTEGER in SQLite
    success: bool = True
    id: Optional[int] = None
```
Required fields first, optional-with-default after; booleans are `bool` on the dataclass and `INTEGER` in the DDL.

### `init_db()` — every DDL statement shares one connection
```python
# SOURCE: app/db/database.py:23-27
def init_db() -> None:
    with get_connection() as conn:
        conn.execute(CREATE_AUDIT_LOGS_TABLE)
        _add_missing_columns(conn)
```

### Write helper — one connection, parameterized, boolean coerced with `int()`
```python
# SOURCE: app/db/database.py:40-71
def insert_audit_log(entry: AuditLog) -> int:
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO audit_logs (
                timestamp, user_id, device, ...
            ) VALUES (?, ?, ?, ...)
            """,
            (
                entry.timestamp,
                entry.user_id,
                ...
                int(entry.was_duplicate_blocked),
                int(entry.success),
            ),
        )
        return cursor.lastrowid
```

### Row mapper — private, `bool()` on the way out
```python
# SOURCE: app/db/database.py:87-106
def _row_to_audit_log(row: sqlite3.Row) -> AuditLog:
    return AuditLog(
        id=row["id"],
        timestamp=row["timestamp"],
        ...
        was_duplicate_blocked=bool(row["was_duplicate_blocked"]),
        success=bool(row["success"]),
    )
```

### Single-row read — `fetchone()`, explicit `None` branch
```python
# SOURCE: app/db/database.py:109-116
def get_audit_log(audit_id: int) -> Optional[AuditLog]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM audit_logs WHERE id = ?", (audit_id,)
        ).fetchone()
        if row is None:
            return None
        return _row_to_audit_log(row)
```

### Count helper — `AS n`, return `row["n"]`
```python
# SOURCE: app/db/database.py:119-122, 158-163
def count_audit_logs() -> int:
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM audit_logs").fetchone()
        return row["n"]

def count_successful_queries() -> int:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM audit_logs WHERE success = 1"
        ).fetchone()
        return row["n"]
```

### List helper — `fetchall()` + comprehension through the row mapper
```python
# SOURCE: app/db/database.py:125-131
def list_audit_logs(limit: int = 100) -> list[AuditLog]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [_row_to_audit_log(row) for row in rows]
```

### UTC timestamp format — each module defines its own private constant
```python
# SOURCE: app/services/audit_logger.py:8
_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
# SOURCE: app/services/duplicate_checker.py:9  (second, independent definition)
_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
# SOURCE: app/services/audit_logger.py:28
timestamp=datetime.now(timezone.utc).strftime(_TIMESTAMP_FORMAT)
```
Two modules already declare this constant privately rather than importing one another's. `app/db/database.py` becomes the third — that is the established house style here, not duplication to be refactored away (Design Note 6).

### Tests: env bootstrap before any `app.*` import
```python
# SOURCE: tests/test_db.py:1-4
import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")
```
`app.config.Settings` requires both at import time. This block must stay at the top of the file, above every `app.*` import.

### Tests: temp DB via the monkeypatched settings singleton
```python
# SOURCE: tests/test_db.py:31-36
@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path}")
    init_db()
    return db_path
```
`_db_path()` reads `settings.DATABASE_URL` on every call, so patching the singleton attribute is enough — no re-import needed. Reuse this fixture; do **not** add a second one.

### Tests: boolean identity assertions, not truthiness
```python
# SOURCE: tests/test_db.py:250-255
assert fetched.was_duplicate_blocked is True
assert fetched.success is False
assert fetched.pii_detected_input is True
```
`is True` / `is False`, so a raw `1`/`0` leaking out of SQLite fails the test instead of passing on truthiness.

### Tests: legacy-database fixture already extracted by STORY-001 — reuse it
```python
# SOURCE: tests/test_db.py:120-152
def _create_pre_pii_database(db_path) -> None:
    """Builds the 14-column audit_logs table exactly as it shipped before PRD-003."""
    legacy = sqlite3.connect(db_path)
    legacy.execute("""CREATE TABLE audit_logs (...)""")
    legacy.execute(
        "INSERT INTO audit_logs (timestamp, user_id, prompt_hash) VALUES (?, ?, ?)",
        ("2026-07-04T10:30:00Z", "juan@empresa.com", "abc123"),
    )
    legacy.commit()
    legacy.close()
```
A database built this way has **no `users` table**, which makes it the exact fixture Task 6's "existing deployment gains the table" test needs. Do not write a second one.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/db/models.py` | UPDATE | Add `CREATE_USERS_TABLE`, `CREATE_USERS_TOKEN_HASH_INDEX`, and the `User` dataclass. Placed so the file reads schema-then-dataclass twice, in the same order as the audit block. |
| `app/db/database.py` | UPDATE | `init_db()` creates the users table and its index; add `_row_to_user`, `get_user`, `find_user_by_token_hash`, `list_users`, `count_active_users`, `insert_user`, `deactivate_user`, `set_user_token_hash`. |
| `tests/test_db.py` | UPDATE | 18 tests covering all five ACs plus the constraint, rotation and idempotence edges. Reuses `temp_db` and `_create_pre_pii_database`. |

**Explicitly NOT touched**:
- `_add_missing_columns()` and `AUDIT_LOGS_ADDED_COLUMNS` — `users` is a new table with no legacy shape; it needs nothing from the migration mechanism, and generalizing that function to take a table name is STORY-009's problem at the earliest (STORY-001 Design Note 7).
- `CREATE_AUDIT_LOGS_TABLE`, the `AuditLog` dataclass, and every existing helper in `app/db/database.py` — this story is purely additive.
- `tests/test_db.py::test_schema_has_no_ip_or_location_column` — it asserts on `PRAGMA table_info(audit_logs)` only, so a new *table* leaves it green. It is STORY-009 that must extend its 17-name set to 19.
- `app/services/`, `app/routers/`, `app/middleware/`, `chat_ui/` — nothing consumes these helpers until STORY-003. This story has **zero runtime-visible effect** beyond an empty table appearing in the database file.
- `hashlib`, `secrets`, and any notion of a plaintext token — Design Note 2.
- `requirements.txt` — stdlib only, per PRD Section 8.

---

## Design Notes (decisions worth stating up front)

1. **No migration mechanism is needed, and none should be reused.** `_add_missing_columns()` exists because `CREATE TABLE IF NOT EXISTS` is a no-op against an *existing* table, so new **columns** never reach an old database file. That problem does not arise for a new **table**: `CREATE TABLE IF NOT EXISTS users` creates it on a fresh database *and* on a five-month-old one, because no `users` table exists in either. Task 6's legacy-file test proves this rather than assuming it. Keep `_add_missing_columns` audit_logs-specific.

2. **This layer never sees a plaintext token.** `token_hash` is an opaque string as far as `app/db/` is concerned. No `hashlib` import, no `secrets` import, no `compare_digest`, and no `create_user(user_id, role, plaintext_token)` convenience wrapper — that helper belongs in STORY-003's `app/services/identity.py`, which owns hashing. Putting it here would mean two modules could decide what a valid credential is, and the PRD's "one enforcement point" principle starts by not scattering the primitives. A reviewer should be able to grep `app/db/` for `sha256` and find nothing.

3. **`user_id TEXT PRIMARY KEY` alone does not forbid NULL — declare `NOT NULL` explicitly.** This is a documented SQLite legacy quirk: outside of `INTEGER PRIMARY KEY`, a PRIMARY KEY column accepts NULL, and *multiple* NULLs at that. Verified on this machine (Python 3.13, SQLite 3.49.1): with `CREATE TABLE u (user_id TEXT PRIMARY KEY, role TEXT NOT NULL)`, two rows with `user_id = NULL` insert successfully and `PRAGMA table_info` reports `notnull = 0`; adding `NOT NULL` makes the same insert raise `IntegrityError`. Two nameless "users" in an identity table is not an acceptable failure mode, so the DDL declares `user_id TEXT PRIMARY KEY NOT NULL`. This is a **strengthening superset** of AC1's literal wording — every constraint the AC names is present, plus one it assumed it already had. Task 6's schema test asserts `notnull == 1` for `user_id` so the guard cannot be silently dropped.

4. **The `token_hash` index is `UNIQUE`.** AC5 asks only for "an index on `token_hash`", and a plain index would satisfy the letter. `UNIQUE` is chosen because it satisfies the index requirement *and* closes an ambiguity the plain form leaves open: without it, two rows could share a `token_hash` and `find_user_by_token_hash` would return whichever one SQLite reached first — one credential silently resolving to an arbitrary identity, in the module whose entire job is answering "who is this". A unique constraint turns that into an `IntegrityError` at write time, where it is diagnosable. Verified: `EXPLAIN QUERY PLAN SELECT * FROM users WHERE token_hash = ? AND active = 1` reports `SEARCH users USING INDEX idx_users_token_hash (token_hash=?)`, so AC5's no-table-scan requirement is met by the same object. The cost of the constraint is nil in practice — the values are 64-character SHA-256 digests of 256-bit random tokens.

5. **`find_user_by_token_hash` filters `active = 1` in SQL, not in Python.** AC2 requires a deactivated user not be returned. Doing it in the `WHERE` clause means there is no code path in which an inactive `User` object exists in the caller's hands, so STORY-003 cannot accidentally resolve one. The trade-off is that "unknown token" and "known but revoked token" become indistinguishable to the caller — which is the *correct* outcome here: PRD Section 9 maps both to `401`, and distinguishing them at the API boundary would be a credential-enumeration oracle. Administrative code that legitimately needs to see a deactivated row uses `get_user(user_id)` or `list_users()`, neither of which filters.

6. **`app/db/database.py` gains its own `_TIMESTAMP_FORMAT`, and `insert_user` stamps `created_at` when it is omitted.** Two precedents set the format convention: `app/services/audit_logger.py:8` and `app/services/duplicate_checker.py:9` each declare `_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"` privately rather than importing one another's. A third private declaration is the house style, and it is what the story's Technical Notes ask for ("`created_at` uses the same `%Y-%m-%dT%H:%M:%SZ` UTC format as `audit_logger.py`").
   The one deliberate deviation from `insert_audit_log` is that `User.created_at` defaults to `None` and `insert_user` fills it. `AuditLog.timestamp` is stamped by `audit_logger.log_query`, a service layer that already exists; `users` has no service layer in this story, and STORY-004's consumer is a standalone script — so without the default, the timestamp format would be re-implemented in `scripts/manage_users.py`, which is exactly the drift the story's note is trying to prevent. Passing `created_at` explicitly still works, and is what the deterministic tests do.

7. **`deactivate_user` returns `bool`, and revocation is never deletion.** AC3 requires the row survive deactivation, because historical `audit_logs` rows carry a bare `user_id` string with no foreign key — deleting the user would leave the audit trail pointing at an identity nothing can resolve, breaking attribution retroactively. So there is no `delete_user` helper, in this story or any other. `deactivate_user` returns `cursor.rowcount == 1`, giving STORY-004's CLI a truthful exit code instead of reporting success for a typo'd user id (verified: `UPDATE ... WHERE user_id = 'zzz'` yields `rowcount == 0`, a known id yields `1`).

8. **Constraint violations propagate as `sqlite3.IntegrityError`; they are not caught here.** A duplicate `user_id` or a duplicate `token_hash` raises out of `insert_user`. `app/db/database.py` has no exception handling anywhere today — `check_duplicate` in `app/services/duplicate_checker.py:30-33` catches `sqlite3.Error` and re-raises it as a domain error one layer up, which is where this belongs too. Swallowing an `IntegrityError` in the DB layer would turn "this user already exists" into a silent no-op.

9. **`active` is `bool` on the dataclass, `INTEGER` in SQLite.** Mirrors `was_duplicate_blocked` and `success` exactly: `int(entry.active)` on write (`app/db/database.py:63,66`), `bool(row["active"])` on read (`app/db/database.py:99,101`). The tests assert `is True` / `is False` so a raw `1` leaking through the mapper fails.

10. **Ordering inside `init_db()`.** Keep `conn.execute(CREATE_AUDIT_LOGS_TABLE)` immediately followed by `_add_missing_columns(conn)` — that pairing is the audit table's create-then-migrate unit, and separating them invites someone to migrate before creating. The two `users` statements go after, in the same single `with get_connection() as conn:` block. `init_db()` runs on **every Reflex hot reload** (`chat_ui/chat_ui/chat_ui.py:24`), so both new statements use `IF NOT EXISTS` and Task 6 proves three consecutive calls stay clean.

11. **The helper set is bounded by named downstream consumers.** Included: `insert_user` (STORY-004 `create-user`), `get_user` (CLI lookups; sees deactivated rows), `find_user_by_token_hash` (STORY-003 resolution — AC2), `list_users` (STORY-004 `list`), `count_active_users` (STORY-016 startup guard — AC4), `deactivate_user` (STORY-004 `deactivate` — AC3), `set_user_token_hash` (STORY-004 `issue-token`, the "U" in the CRUD the story title asks for). Excluded on purpose: `delete_user` (Note 7), `update_user_role` (no story asks for it; the PRD has no role-change flow in MVP scope), and anything taking a plaintext credential (Note 2).

12. **Pre-existing issue observed, deliberately left alone.** `with get_connection() as conn:` commits but never closes — `sqlite3`'s context manager is a transaction manager, not a resource manager — so every helper in the module leaks a connection, and on Windows that prevents deleting the database file while the process lives (STORY-001 report, Design Note 8a; hit empirically during that story's E2E). The new helpers follow the same shape *on purpose*: this story is not the place to change the module's connection lifecycle, and diverging would make the users helpers the odd ones out. `pytest`'s `tmp_path` cleanup is lazy, so it does not affect these tests. Worth a dedicated cleanup story.

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Verify the baseline before writing anything

- **File**: — (no file change)
- **Action**: VERIFY
- **Implement**:
  - `git branch --show-current` → `epic/PRD-005-rbac`.
  - `app/db/database.py` contains `init_db()`, `_add_missing_columns()`, `_row_to_audit_log()`, `insert_audit_log()` and has **no** `users` reference.
  - `tests/test_db.py` contains the `temp_db` fixture and the module-level `_create_pre_pii_database()` helper STORY-001 extracted — both are reused, not rewritten.
  - Full suite is green at **251 passed**, `tests/test_db.py` at **27**.
  - If any of the above differs, stop and re-plan — the branch is not where this plan assumes it is.
- **Mirror**: STORY-001 plan Task 1 (same verification-gate shape)
- **Validate**:
  ```bash
  .venv/Scripts/python.exe -m pytest -q                    # 251 passed
  .venv/Scripts/python.exe -m pytest tests/test_db.py -q   # 27 passed
  ```

### Task 2: Add the users schema constants and the `User` dataclass

- **File**: `app/db/models.py`
- **Action**: UPDATE
- **Implement**: After the `AUDIT_LOGS_ADDED_COLUMNS` block and before `@dataclass class AuditLog`, add the two DDL constants; after the `AuditLog` dataclass, add `User`.
  ```python
  # Identity store (PRD-005). Lives in the same SQLite file as audit_logs -- no
  # second service, no ORM, stdlib only.
  #
  # user_id declares NOT NULL explicitly: outside INTEGER PRIMARY KEY, SQLite
  # lets a PRIMARY KEY column hold NULL, and more than one row of them.
  #
  # token_hash holds a SHA-256 digest produced by app/services/identity.py
  # (STORY-003). Nothing in app/db/ ever sees the plaintext token.
  CREATE_USERS_TABLE = """
  CREATE TABLE IF NOT EXISTS users (
      user_id TEXT PRIMARY KEY NOT NULL,
      role TEXT NOT NULL,
      token_hash TEXT NOT NULL,
      active INTEGER NOT NULL DEFAULT 1,
      created_at TEXT NOT NULL
  )
  """

  # UNIQUE, not merely indexed: it serves the lookup path (no table scan) and
  # makes two users sharing a credential an IntegrityError at write time rather
  # than an arbitrary winner at read time.
  CREATE_USERS_TOKEN_HASH_INDEX = (
      "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_token_hash ON users(token_hash)"
  )
  ```
  ```python
  @dataclass
  class User:
      user_id: str
      role: str
      token_hash: str
      active: bool = True
      created_at: Optional[str] = None  # insert_user() stamps it when omitted
  ```
  No new imports — `dataclass` and `Optional` are already imported at `app/db/models.py:1-2`.
- **Mirror**: `app/db/models.py:5-24` (DDL constant shape), `app/db/models.py:41-59` (dataclass: required fields first, optional-with-default after, `bool` for INTEGER flags)
- **Validate**:
  ```bash
  .venv/Scripts/python.exe -c "from app.db.models import CREATE_USERS_TABLE, CREATE_USERS_TOKEN_HASH_INDEX, User; print(User('ana','user','h'))"
  ```
  prints `User(user_id='ana', role='user', token_hash='h', active=True, created_at=None)`

### Task 3: Create the table and its index in `init_db()`

- **File**: `app/db/database.py`
- **Action**: UPDATE
- **Implement**: Extend the import at line 5 to include `CREATE_USERS_TABLE`, `CREATE_USERS_TOKEN_HASH_INDEX` and `User` (keep the names sorted inside the parenthesized import, as they are today). Then add the two statements to `init_db()` **after** the audit pair:
  ```python
  def init_db() -> None:
      with get_connection() as conn:
          conn.execute(CREATE_AUDIT_LOGS_TABLE)
          _add_missing_columns(conn)
          conn.execute(CREATE_USERS_TABLE)
          conn.execute(CREATE_USERS_TOKEN_HASH_INDEX)
  ```
  Do **not** touch `_add_missing_columns` and do not call it for `users` (Design Note 1). Add `from datetime import datetime, timezone` and the module constant `_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"` in this task — Task 5 uses them — placing the constant just below `_SQLITE_PREFIX` at line 7.
- **Mirror**: `app/db/database.py:23-27` (single shared connection for all DDL), `app/services/audit_logger.py:8` (`_TIMESTAMP_FORMAT`)
- **Validate**:
  ```bash
  .venv/Scripts/python.exe -m pytest tests/test_db.py -q   # still 27 passed -- nothing existing broke
  .venv/Scripts/python.exe -c "from app.main import app"   # imports clean
  ```

### Task 4: Add the row mapper and the read helpers

- **File**: `app/db/database.py`
- **Action**: UPDATE
- **Implement**: Append after `top_pii_entities` (end of file), so the users helpers form one contiguous block rather than interleaving with the audit ones.
  ```python
  def _row_to_user(row: sqlite3.Row) -> User:
      return User(
          user_id=row["user_id"],
          role=row["role"],
          token_hash=row["token_hash"],
          active=bool(row["active"]),
          created_at=row["created_at"],
      )


  def get_user(user_id: str) -> Optional[User]:
      """Returns the user regardless of active state -- administrative reads
      (CLI list/deactivate) must be able to see a revoked row."""
      with get_connection() as conn:
          row = conn.execute(
              "SELECT * FROM users WHERE user_id = ?", (user_id,)
          ).fetchone()
          if row is None:
              return None
          return _row_to_user(row)


  def find_user_by_token_hash(token_hash: str) -> Optional[User]:
      """Active users only. A revoked credential is indistinguishable from an
      unknown one by design -- PRD Section 9 maps both to 401, and separating
      them would be a credential-enumeration oracle."""
      with get_connection() as conn:
          row = conn.execute(
              "SELECT * FROM users WHERE token_hash = ? AND active = 1",
              (token_hash,),
          ).fetchone()
          if row is None:
              return None
          return _row_to_user(row)


  def list_users(limit: int = 100) -> list[User]:
      with get_connection() as conn:
          rows = conn.execute(
              "SELECT * FROM users ORDER BY created_at DESC LIMIT ?",
              (limit,),
          ).fetchall()
          return [_row_to_user(row) for row in rows]


  def count_active_users() -> int:
      with get_connection() as conn:
          row = conn.execute(
              "SELECT COUNT(*) AS n FROM users WHERE active = 1"
          ).fetchone()
          return row["n"]
  ```
- **Mirror**: `app/db/database.py:87-106` (`_row_to_audit_log`), `:109-116` (`get_audit_log`), `:125-131` (`list_audit_logs`), `:158-163` (`count_successful_queries`)
- **Validate**:
  ```bash
  .venv/Scripts/python.exe -c "from app.db.database import get_user, find_user_by_token_hash, list_users, count_active_users; print('ok')"
  ```

### Task 5: Add the write helpers

- **File**: `app/db/database.py`
- **Action**: UPDATE
- **Implement**: Append below the read helpers.
  ```python
  def insert_user(entry: User) -> str:
      """Raises sqlite3.IntegrityError on a duplicate user_id or token_hash --
      deliberately not caught here; app/db/ has no error handling anywhere and
      the caller needs to tell those two cases apart."""
      created_at = entry.created_at or datetime.now(timezone.utc).strftime(
          _TIMESTAMP_FORMAT
      )
      with get_connection() as conn:
          conn.execute(
              """
              INSERT INTO users (user_id, role, token_hash, active, created_at)
              VALUES (?, ?, ?, ?, ?)
              """,
              (
                  entry.user_id,
                  entry.role,
                  entry.token_hash,
                  int(entry.active),
                  created_at,
              ),
          )
      return entry.user_id


  def deactivate_user(user_id: str) -> bool:
      """Revocation is not deletion: audit_logs rows carry a bare user_id with
      no foreign key, so removing the row would orphan the audit trail.
      Returns False when no such user exists, so the CLI can report a typo."""
      with get_connection() as conn:
          cursor = conn.execute(
              "UPDATE users SET active = 0 WHERE user_id = ?", (user_id,)
          )
          return cursor.rowcount == 1


  def set_user_token_hash(user_id: str, token_hash: str) -> bool:
      """Credential rotation (STORY-004 `issue-token`). The old hash stops
      resolving the moment this returns."""
      with get_connection() as conn:
          cursor = conn.execute(
              "UPDATE users SET token_hash = ? WHERE user_id = ?",
              (token_hash, user_id),
          )
          return cursor.rowcount == 1
  ```
  `insert_user` returns the `user_id` rather than a `lastrowid`, because the table has no autoincrement surrogate key — the primary key is the caller's own string.
- **Mirror**: `app/db/database.py:40-71` (`insert_audit_log`: one connection, parameterized, `int()` on booleans), `app/services/audit_logger.py:28` (UTC stamping)
- **Validate**:
  ```bash
  DATABASE_URL=sqlite:///scratch.db .venv/Scripts/python.exe -c "
  from app.db.database import init_db, insert_user, find_user_by_token_hash, count_active_users, deactivate_user
  from app.db.models import User
  init_db(); insert_user(User('ana','user','h1'))
  print(find_user_by_token_hash('h1'), count_active_users())
  print(deactivate_user('ana'), find_user_by_token_hash('h1'), count_active_users())
  "
  ```
  expect an active `User` then `1`; then `True`, `None`, `0`. Delete `scratch.db` afterwards (the process must exit first — Design Note 12).

### Task 6: Tests — schema shape, idempotence, and the legacy-file path (AC1)

- **File**: `tests/test_db.py`
- **Action**: UPDATE
- **Implement**: Extend the existing import block at lines 12-28 with `count_active_users`, `deactivate_user`, `find_user_by_token_hash`, `get_user`, `insert_user`, `list_users`, `set_user_token_hash` and `User` (keep both blocks sorted). Add:
  - `test_init_db_creates_users_table` — `SELECT name FROM sqlite_master WHERE type='table' AND name='users'` is not `None`. Mirrors `tests/test_db.py:39-46`.
  - `test_users_schema_matches_expected_columns` — from `PRAGMA table_info(users)` assert the column-name set is exactly `{"user_id","role","token_hash","active","created_at"}`; assert `notnull == 1` for **all five** (this is the Design Note 3 guard — it fails if the explicit `NOT NULL` on `user_id` is ever dropped); assert `active`'s `dflt_value == "1"`; assert `pk == 1` for `user_id` and `0` for the rest. Mirrors `tests/test_db.py:300-324`.
  - `test_init_db_creates_users_token_hash_index` — `SELECT name FROM sqlite_master WHERE type='index' AND name='idx_users_token_hash'` is not `None`.
  - `test_init_db_is_idempotent_for_users_table` — call `init_db()` three times on `temp_db`, insert a user, assert `count_active_users() == 1` and the index still exists. Mirrors `tests/test_db.py:193-213`.
  - `test_init_db_adds_users_table_to_pre_rbac_database` — build a legacy file with the **existing** `_create_pre_pii_database(db_path)` (`tests/test_db.py:120-152`, which creates `audit_logs` only), point `settings.DATABASE_URL` at it, run `init_db()`, then assert the `users` table exists, `count_active_users() == 0`, and the legacy audit row survives (`count_audit_logs() == 1`). This is the Design Note 1 proof that a new table needs no migration mechanism.
- **Mirror**: `tests/test_db.py:31-36` (`temp_db` fixture — reuse, do not add another), `:120-152` (`_create_pre_pii_database` — reuse), `:155-191` (legacy-file test shape)
- **Validate**: `.venv/Scripts/python.exe -m pytest tests/test_db.py -q -k users`

### Task 7: Tests — token-hash lookup and the active filter (AC2)

- **File**: `tests/test_db.py`
- **Action**: UPDATE
- **Implement**:
  - `test_find_user_by_token_hash_returns_active_user` — insert `User("ana","user","hash-ana", created_at="2026-08-28T10:00:00Z")`; the lookup returns a `User` whose `user_id == "ana"`, `role == "user"` and `active is True`.
  - `test_find_user_by_token_hash_ignores_deactivated_user` — insert, `deactivate_user("ana")`, then assert the lookup returns `None` **while** `get_user("ana")` still returns the row with `active is False`. One test proving both halves of AC2 and the Note 5 split.
  - `test_find_user_by_token_hash_unknown_returns_none` — `find_user_by_token_hash("nope") is None`. Mirrors `tests/test_db.py:296-297`.
  - `test_find_user_by_token_hash_is_exact_not_prefix` — insert `token_hash="abc123"`; assert `find_user_by_token_hash("abc") is None`. Guards against anyone "optimizing" the `=` into a `LIKE`.
- **Mirror**: `tests/test_db.py:250-256` (`is True`/`is False` identity assertions)
- **Validate**: `.venv/Scripts/python.exe -m pytest tests/test_db.py -q -k token_hash`

### Task 8: Tests — deactivation retains the row (AC3) and active counting (AC4)

- **File**: `tests/test_db.py`
- **Action**: UPDATE
- **Implement**:
  - `test_deactivate_user_retains_the_row` — insert, deactivate, then assert `deactivate_user(...) is True`, `get_user("ana") is not None`, `get_user("ana").active is False`, and `created_at` is unchanged. Explicitly asserts the row was **not** deleted, which is the whole point of AC3.
  - `test_deactivate_user_unknown_returns_false` — `deactivate_user("ghost") is False`.
  - `test_deactivate_user_is_idempotent` — deactivating twice: the second call still returns `True` (the row matched) and `active` stays `False`. Documents the chosen semantics — `rowcount` counts matched rows, not changed ones — so nobody "fixes" it later by accident.
  - `test_count_active_users_empty_returns_zero` — on `temp_db`, `count_active_users() == 0` (AC4). Mirrors `tests/test_db.py:327-328`.
  - `test_count_active_users_excludes_deactivated` — insert three users, deactivate one, assert `count_active_users() == 2` while `len(list_users()) == 3`.
- **Mirror**: `tests/test_db.py:327-341` (`count_*` empty-then-populated pair)
- **Validate**: `.venv/Scripts/python.exe -m pytest tests/test_db.py -q -k "deactivate or count_active"`

### Task 9: Test — the lookup uses the index and does not table-scan (AC5)

- **File**: `tests/test_db.py`
- **Action**: UPDATE
- **Implement**: `test_find_user_by_token_hash_uses_the_index` — run the helper's exact query through `EXPLAIN QUERY PLAN` and assert the plan names the index and contains no full scan:
  ```python
  def test_find_user_by_token_hash_uses_the_index(temp_db):
      """AC5: the lookup is on the hot path of every authenticated request, so
      it must not degrade to a table scan as the users table grows."""
      insert_user(User(user_id="ana", role="user", token_hash="hash-ana"))

      with get_connection() as conn:
          plan = " ".join(
              row["detail"]
              for row in conn.execute(
                  "EXPLAIN QUERY PLAN "
                  "SELECT * FROM users WHERE token_hash = ? AND active = 1",
                  ("hash-ana",),
              )
          )

      assert "idx_users_token_hash" in plan, plan
      assert "SCAN" not in plan.upper(), plan
  ```
  Verified on this machine: the plan is `SEARCH users USING INDEX idx_users_token_hash (token_hash=?)` — the trailing `active = 1` predicate does not defeat the index. Note `sqlite3.Row` exposes the plan text under the column name `detail`.
- **Mirror**: `tests/test_db.py:101-117` (the STORY-001 precedent for asserting on *how* SQLite executed something, not only on the result)
- **Validate**: `.venv/Scripts/python.exe -m pytest tests/test_db.py -q -k index`

### Task 10: Tests — round trip, constraints, rotation, timestamp default

- **File**: `tests/test_db.py`
- **Action**: UPDATE
- **Implement**:
  - `test_insert_and_read_user_round_trip` — every field set explicitly (including `created_at` and `active=False`), read back via `get_user`, assert field-by-field with `is True`/`is False` on `active`. Mirrors `tests/test_db.py:216-256`.
  - `test_insert_user_defaults_created_at_to_utc_now` — insert with `created_at=None`; assert the stored value matches `r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"` and parses under `datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")` (Design Note 6 / the story's Technical Note).
  - `test_insert_user_rejects_duplicate_user_id` — `pytest.raises(sqlite3.IntegrityError)` on a second insert with the same `user_id` and a different hash.
  - `test_insert_user_rejects_duplicate_token_hash` — `pytest.raises(sqlite3.IntegrityError)` on a different `user_id` with the same hash. This is the Design Note 4 guard; it fails if the index is ever downgraded from `UNIQUE`.
  - `test_get_user_missing_returns_none` — `get_user("ghost") is None`.
  - `test_list_users_includes_deactivated` — insert two, deactivate one, `len(list_users()) == 2`.
  - `test_set_user_token_hash_rotates_the_credential` — insert with `"old-hash"`, call `set_user_token_hash("ana", "new-hash")`, assert it returned `True`, `find_user_by_token_hash("old-hash") is None`, and `find_user_by_token_hash("new-hash").user_id == "ana"`.
  - `test_set_user_token_hash_unknown_returns_false` — `set_user_token_hash("ghost", "h") is False`.
  - Add `import re` and `from datetime import datetime` at the top of the file (neither is present today).
- **Mirror**: `tests/test_db.py:216-256` (exhaustive round-trip), `:259-273` (defaults-when-not-supplied)
- **Validate**: `.venv/Scripts/python.exe -m pytest tests/test_db.py -q` — 45 pass (27 existing + 18 new)

### Task 11: Full-suite regression and diff gate

- **File**: — (no file change)
- **Action**: VERIFY
- **Implement**:
  - `.venv/Scripts/python.exe -m pytest -q` → **269 passed** (251 + 18). Any *pre-existing* test that now fails is a real regression: this story is purely additive and must not change one line of existing behavior.
  - `git diff --name-only` lists exactly three files: `app/db/models.py`, `app/db/database.py`, `tests/test_db.py`. Anything else — especially `harness_ai.db` — must not be staged. (`README.md` is already modified on this branch and stays unstaged; it is STORY-018's territory.)
  - `git diff app/db/database.py` shows only additions plus the two-line `init_db()` insertion, the import-line extension, and the `datetime` import / `_TIMESTAMP_FORMAT` constant. No existing helper body is modified.
  - `grep -rn "sha256\|token_urlsafe\|compare_digest" app/db/` returns nothing (Design Note 2).
- **Mirror**: STORY-001 plan Task 7 (same regression + diff gate)
- **Validate**:
  ```bash
  .venv/Scripts/python.exe -m pytest -q
  git diff --name-only
  git status --short
  grep -rn "sha256\|token_urlsafe\|compare_digest" app/db/ || echo "clean: no credential primitives in the db layer"
  ```

---

## End-to-End Tests

Checks for `/implement` to execute:

- [ ] `.venv/Scripts/python.exe -m pytest tests/test_db.py -v` — 45 pass (27 existing + 18 new)
- [ ] `.venv/Scripts/python.exe -m pytest -q` — 269 pass, zero pre-existing failures
- [ ] `git diff --name-only` — exactly `app/db/models.py`, `app/db/database.py`, `tests/test_db.py` (plus the pre-existing unstaged `README.md`)
- [ ] `grep -rn "sha256\|token_urlsafe\|compare_digest" app/db/` — no matches (the DB layer never handles a credential primitive)
- [ ] **Real on-disk pre-RBAC file gains the table.** Build a database that has `audit_logs` and no `users`, migrate it twice, and confirm the audit row survives:
  ```bash
  .venv/Scripts/python.exe -c "import sqlite3; c=sqlite3.connect('probe.db'); c.executescript(\"CREATE TABLE audit_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL, user_id TEXT NOT NULL, device TEXT, prompt_hash TEXT NOT NULL, prompt_preview TEXT, response_hash TEXT, response_preview TEXT, model_used TEXT, tokens_used INTEGER, was_duplicate_blocked INTEGER NOT NULL DEFAULT 0, suspicious_pattern TEXT, success INTEGER NOT NULL DEFAULT 1, error_message TEXT); INSERT INTO audit_logs (timestamp,user_id,prompt_hash) VALUES ('2026-01-01T00:00:00Z','probe','h');\"); c.commit()"
  DATABASE_URL=sqlite:///probe.db .venv/Scripts/python.exe -c "from app.db.database import init_db, count_audit_logs, count_active_users, get_connection; init_db(); init_db(); print(sorted(r[0] for r in get_connection().execute(\"SELECT name FROM sqlite_master WHERE type='table'\")), count_audit_logs(), count_active_users())"
  ```
  expect the table list to include both `audit_logs` and `users`, then `1 0`; then delete `probe.db`
- [ ] **CRUD round trip against a real file** — create, resolve, rotate, revoke:
  ```bash
  DATABASE_URL=sqlite:///probe2.db .venv/Scripts/python.exe -c "
  from app.db.database import init_db, insert_user, find_user_by_token_hash, set_user_token_hash, deactivate_user, get_user, count_active_users, list_users
  from app.db.models import User
  init_db()
  insert_user(User('ana','user','h-ana')); insert_user(User('bob','auditor','h-bob'))
  print('resolve', find_user_by_token_hash('h-ana').role, count_active_users())
  print('rotate ', set_user_token_hash('ana','h-ana-2'), find_user_by_token_hash('h-ana'), find_user_by_token_hash('h-ana-2').user_id)
  print('revoke ', deactivate_user('bob'), find_user_by_token_hash('h-bob'), get_user('bob').active, count_active_users(), len(list_users()))
  "
  ```
  expect `user 2` / `True None ana` / `True None False 1 2` — note the revoked row is still listed and still readable by `get_user`; then delete `probe2.db`
- [ ] `.venv/Scripts/python.exe -m uvicorn app.main:app` — starts; the lifespan `init_db()` creates `users` in the repo-root `harness_ai.db` in place (additive, no existing data touched)
- [ ] `curl http://localhost:8000/health` — `{"status":"ok"}`
- [ ] `.venv/Scripts/python.exe -c "import sqlite3; c=sqlite3.connect('harness_ai.db'); print(sorted(r[0] for r in c.execute(\"SELECT name FROM sqlite_master WHERE type IN ('table','index') AND name NOT LIKE 'sqlite_%'\")))"` — includes `audit_logs`, `users`, `idx_users_token_hash`
- [ ] **Reflex ingress, repeated `init_db()`** — `chat_ui/chat_ui/chat_ui.py:24` calls `init_db()` at import and on every hot reload. Exercise the guarantee directly (a full `reflex run` needs an interactive Node build, so import the module and re-run the migration, per STORY-001's report Deviation 2):
  ```bash
  .venv/Scripts/python.exe -c "import chat_ui.chat_ui; from app.db.database import init_db; [init_db() for _ in range(4)]; print('no duplicate table/index error')"
  ```
- [ ] Existing behavior untouched: `.venv/Scripts/python.exe -m pytest tests/test_query_router.py tests/test_admin_auth.py tests/test_chat_state.py -q` — all green, unmodified

---

## Validation

```bash
cd /f/AI/harness-ai
.venv/Scripts/python.exe -m pytest tests/test_db.py -v
.venv/Scripts/python.exe -m pytest -q
git diff --name-only
git diff --stat
grep -rn "sha256\|token_urlsafe\|compare_digest" app/db/ || echo "clean"
.venv/Scripts/python.exe -c "from app.db.models import CREATE_USERS_TABLE, CREATE_USERS_TOKEN_HASH_INDEX, User; print(User('ana','user','h'))"
curl http://localhost:8000/health
```

Frontend lint: **N/A** — this repository has no npm frontend; the UI is Reflex (Python) and this story does not touch it.

---

## Handoff to downstream stories

- **STORY-003** (`app/services/identity.py`) owns token generation and hashing. It calls `find_user_by_token_hash(sha256(token).hexdigest())` and gets an active `User` or `None` — `None` covers both "unknown" and "revoked" on purpose (Design Note 5), and both map to `401` per PRD Section 9. It must build its `Identity` value object *from* the returned `User`; do not let `User` itself leak into the pipeline as the identity type.
- **STORY-004** (`scripts/manage_users.py`) has a helper for each subcommand: `create-user` → `insert_user` (catch `sqlite3.IntegrityError` for "user already exists"), `list` → `list_users`, `deactivate` → `deactivate_user` (its `False` return is the "no such user" exit code), `issue-token` → `set_user_token_hash`. The CLI generates and prints the plaintext token; only the digest reaches this layer.
- **STORY-016** (startup guard) calls `count_active_users() == 0` together with `RBAC_ENABLED` to fail fast. Note it counts *active* users, so a deployment whose only user was revoked correctly trips the guard.
- **STORY-009** adds `role` and `denied_permission` to `audit_logs`. It is unaffected by this story: `_add_missing_columns` is still audit_logs-only, and `test_schema_has_no_ip_or_location_column` still asserts on `PRAGMA table_info(audit_logs)`, so this story leaves it green at 17 names. STORY-009 still owes it the extension to 19 (STORY-001 handoff).
- **Not delivered, by design**: no `delete_user` (Design Note 7), no `update_user_role`, no plaintext-token helper (Design Note 2). Any story needing one should add it there with its own justification rather than assuming it was an oversight here.

---

## Acceptance Criteria

(Copied from story `STORY-002`)

- [ ] Given a fresh database, when `init_db()` runs, then `users(user_id TEXT PRIMARY KEY, role TEXT NOT NULL, token_hash TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL)` exists — *Tasks 2, 3, 6; the DDL adds an explicit `NOT NULL` to `user_id`, a strengthening superset of this wording (Design Note 3)*
- [ ] Given a `token_hash`, when `find_user_by_token_hash()` is called, then the matching **active** user is returned and a deactivated one is not — *Tasks 4, 7*
- [ ] Given a user id, when `deactivate_user()` is called, then `active` becomes `0` and the row is retained — revocation is not deletion, so historical audit rows keep resolving the id — *Tasks 5, 8*
- [ ] Given an empty table, when `count_active_users()` is called, then it returns `0` — *Tasks 4, 8*
- [ ] Given an index on `token_hash`, when a lookup runs, then it does not table-scan — *Tasks 2, 3, 9; satisfied by a `UNIQUE` index, verified via `EXPLAIN QUERY PLAN` (Design Note 4)*
- [ ] All tasks completed
- [ ] Backend server starts without error
- [ ] Full pytest suite green (45 in `tests/test_db.py`, 269 overall)
- [ ] No credential primitive (`sha256`, `token_urlsafe`, `compare_digest`) appears anywhere under `app/db/`
- [ ] Follows existing patterns
