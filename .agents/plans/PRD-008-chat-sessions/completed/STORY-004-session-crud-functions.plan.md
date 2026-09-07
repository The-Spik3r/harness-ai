---
story: STORY-004
prd: PRD-008
slug: session-crud-functions
title: "Six user-scoped chat_sessions functions in database.py, with delete as one transaction"
type: NEW_CAPABILITY
complexity: MEDIUM
epic_branch: epic/PRD-008-chat-sessions
created: 2026-09-03
---

# Plan: Six user-scoped chat_sessions functions in database.py, with delete as one transaction

## Summary

Add six new functions to `app/db/database.py` — `create_chat_session`, `get_chat_session`,
`list_chat_sessions`, `rename_chat_session`, `touch_chat_session`, `delete_chat_session` —
plus one `_row_to_chat_session` mapper, over the `chat_sessions` table STORY-002 declared and
STORY-003 creates. Every signature takes `user_id: str` **required and undefaulted**, and every
statement carries `user_id = ?` in its `WHERE`, so PRD Risk 2's silent failure mode ("a missing
`WHERE user_id = ?` returns data rather than an error") becomes a `TypeError` at the call site
instead. Ids are minted here with `uuid.uuid4()`, never accepted from the caller, because
`active_session_id` is a client-visible Reflex var (PRD Risk 3). `delete_chat_session` issues
both deletes inside one `_session()` block, scoping the `chat_messages` delete by the same
ownership check rather than by `session_id` alone, and touches no `audit_logs` row. A new
`tests/test_chat_sessions.py` drives every read and write path with a second user's id.

## User Story

As a maintainer
I want the session table reachable through functions that cannot be called without naming an owner
So that the first row-level authorization in this codebase is a property of the signatures rather
than a habit callers have to keep.

## Story Reference

- Story file: `.agents/stories/PRD-008-chat-sessions/STORY-004-session-crud-functions.md`
- PRD: `.agents/PRDs/PRD-008-chat-sessions/PRD.md` — Section 4 (Data access), Section 6 (Ownership
  as a signature rule), Section 9 (Deletion semantics), Section 12 Phase 1, Risk 2

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | MEDIUM |
| Systems Affected | `app/db/database.py`, `tests/` |
| Story | STORY-004 |
| PRD | PRD-008 |
| Epic Branch | `epic/PRD-008-chat-sessions` (commit directly on this branch) |

**Dependency check**: STORY-002 (`status: done`, commit `e3bb0c7`) and STORY-003 (`status: done`,
commit `e42eed9`) are both complete. `ChatSession`, `CREATE_CHAT_SESSIONS_TABLE` and the
`(user_id, updated_at DESC)` index all exist, and `init_db()` already creates the table
(`app/db/database.py:489-492`). Nothing blocks this story.

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | `.agents/skills/` was listed and holds only `frontend-design`, whose `description` scopes it to "distinctive, intentional visual design when building new UI or reshaping an existing one". This story touches no UI and renders nothing. | None |

Story frontmatter `skills: []` agrees. No skill constrains any task below.

---

## Patterns to Follow

### Naming — the row mapper

```python
# SOURCE: app/db/database.py:1101-1109
def _row_to_user(row: _Row) -> User:
    return User(
        user_id=row["user_id"],
        role=row["role"],
        token_hash=row["token_hash"],
        active=bool(row["active"]),
        created_at=row["created_at"],
    )
```

`_row_to_chat_session(row: _Row) -> ChatSession` is written to this shape exactly: private,
column-name indexing, one keyword-only constructor call.

### Reads — `_session()`, `?` placeholders, `None` on miss

```python
# SOURCE: app/db/database.py:1111-1121
def get_user(user_id: str) -> Optional[User]:
    with _session() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        if row is None:
            return None
        return _row_to_user(row)
```

### Ordered, capped list reads

```python
# SOURCE: app/db/database.py:1149-1156
def list_users(limit: int = 100) -> list[User]:
    with _session() as conn:
        rows = conn.execute(
            "SELECT * FROM users ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [_row_to_user(row) for row in rows]
```

Note the literal default: `database.py` never reads `settings` for a limit, and callers pass one
explicitly (`app/routers/admin.py:53`, `app/db/database.py:1033`). `list_chat_sessions` keeps that
split — literal `50` here, `settings.CHAT_SESSION_LIMIT` passed by the service in STORY-006.

### Writes — timestamp defaulting

```python
# SOURCE: app/db/database.py:1166-1189
def insert_user(entry: User) -> str:
    created_at = entry.created_at or datetime.now(timezone.utc).strftime(
        _TIMESTAMP_FORMAT
    )
    with _session() as conn:
        conn.execute(
            """
            INSERT INTO users (user_id, role, token_hash, active, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (...),
        )
    return entry.user_id
```

`_TIMESTAMP_FORMAT` is `"%Y-%m-%dT%H:%M:%SZ"` (`app/db/database.py:33`) — the module's one
timestamp spelling, and the reason `updated_at` sorts lexically.

### The zero-row boolean

```python
# SOURCE: app/db/database.py:1191-1200
def deactivate_user(user_id: str) -> bool:
    """... Returns False when no such user exists, so the CLI can report a typo."""
    with _session() as conn:
        cursor = conn.execute(
            "UPDATE users SET active = 0 WHERE user_id = ?", (user_id,)
        )
        return cursor.rowcount == 1
```

`_Cursor.rowcount` is a real passthrough to the driver cursor (`app/db/database.py:172-174`).
`rowcount` counts **matched** rows, not changed ones — `test_deactivate_user_is_idempotent`
(`tests/test_db.py:1902-1908`) pins that, and `rename_chat_session` inherits it: renaming to the
same title still returns `True`, which is correct and must be asserted so nobody "fixes" it.

### Transaction semantics

```python
# SOURCE: app/db/database.py:444-455
@contextmanager
def _session() -> Iterator[_Connection]:
    with _translated():
        conn = get_connection()
        with conn:
            yield conn
```

`_Connection.__exit__` (`app/db/database.py:218-224`) commits explicitly on clean exit and rolls
back on exception. **One `with _session() as conn:` block is one transaction**, which is precisely
what AC 6 requires of `delete_chat_session` — two statements in one block, not two blocks.

### Tests

```python
# SOURCE: tests/test_db.py:1877-1895
def test_deactivate_user_retains_the_row(temp_db):
    """Revocation is not deletion: audit_logs rows carry a bare user_id with no
    foreign key, so deleting the user would orphan the audit trail."""
    insert_user(
        User(
            user_id="ana",
            role="user",
            token_hash="hash-ana",
            created_at="2026-08-28T10:00:00Z",
        )
    )

    assert deactivate_user("ana") is True
```

`temp_db` (`tests/conftest.py:170-177`) is an isolated database with `init_db()` already run; the
autouse `_never_the_configured_database` fixture empties the database before every test. Do not
add a second fixture — STORY-007's notes forbid it and this story has no reason to.

```python
# SOURCE: tests/test_db.py:1266-1289
def test_summary_snapshot_leaves_the_ten_standalone_signatures_unchanged(temp_db):
    expected = {
        "count_audit_logs": "(user_id: Optional[str] = None) -> int",
        # ...
    }
    for name, signature in expected.items():
        assert str(inspect.signature(getattr(database, name))) == signature, name
```

The precedent for asserting the ownership rule structurally. STORY-004 asserts it for its own six
(required + undefaulted `user_id`); STORY-007 generalises it to a discovery-based sweep over
`*_chat_session*` / `*_chat_message*`. Write the STORY-004 version against the six by name and
leave the discovery version to STORY-007 — putting both here would give one rule two definitions
in two files.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/db/database.py` | UPDATE | Add `import uuid`, import `ChatSession`, append `_row_to_chat_session` + the six functions at the end of the module |
| `tests/test_chat_sessions.py` | CREATE | Behavioural + ownership tests for the six (STORY-005 extends this same file with the message round trips) |

**Not touched**: the existing 22 functions, the module's organisation, `app/db/models.py`,
`init_db()`, `app/services/`, `audit_logs` in any form.

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Imports for uuid and the ChatSession dataclass

- **File**: `app/db/database.py`
- **Action**: UPDATE
- **Implement**:
  - Add `import uuid` to the stdlib import block at the top — alphabetical among the bare `import`
    lines (`json`, `re`, `threading` at lines 1-3), so it lands after `import threading`.
  - Add `ChatSession` to the `from app.db.models import (...)` list (lines 20-31). That list is
    constants first, then classes (`AuditLog`, `User`); `ChatSession` goes between the two classes.
  - Do **not** import `StoredMessage` — that is STORY-005's.
- **Mirror**: `app/db/database.py:1-31`
- **Validate**: `python -c "import app.db.database"` — no ImportError.

### Task 2: `_row_to_chat_session`

- **File**: `app/db/database.py`
- **Action**: UPDATE (append at end of module)
- **Implement**: `def _row_to_chat_session(row: _Row) -> ChatSession:` returning a `ChatSession`
  with `session_id`, `user_id`, `title`, `created_at`, `updated_at` read by column name. All five
  columns are `TEXT NOT NULL` in the DDL (`app/db/models.py:96-104`), so no `bool()`/`int()`
  coercion is needed — unlike `_row_to_user`, which coerces `active`.
- **Mirror**: `app/db/database.py:1101-1109`
- **Validate**: `python -c "import app.db.database"`.

### Task 3: `create_chat_session`

- **File**: `app/db/database.py`
- **Action**: UPDATE
- **Implement**:
  ```python
  def create_chat_session(user_id: str, title: str) -> str:
  ```
  - `session_id = str(uuid.uuid4())` — minted **here**. The signature deliberately has no
    `session_id` parameter at all: a caller-supplied id is a caller-chosen id, and
    `active_session_id` is a client-visible Reflex var (PRD Risk 3), so accepting one would let a
    client pick primary keys. Returns the new `session_id`.
  - `now = datetime.now(timezone.utc).strftime(_TIMESTAMP_FORMAT)` written to **both** `created_at`
    and `updated_at` from the same value, so a new session sorts to the top of the rail and the two
    columns cannot disagree by a second.
  - One `INSERT INTO chat_sessions (session_id, user_id, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?)`
    inside `with _session() as conn:`.
  - Docstring records: the id is minted here and why; both timestamps come from one `now`; `user_id`
    is positional-first because it is the owner and there is no defaulted form of this call.
- **Mirror**: `app/db/database.py:1166-1189` (`insert_user`)
- **Validate**: `pytest tests/test_chat_sessions.py -k create -q` (after Task 9).

### Task 4: `get_chat_session`

- **File**: `app/db/database.py`
- **Action**: UPDATE
- **Implement**:
  ```python
  def get_chat_session(session_id: str, user_id: str) -> Optional[ChatSession]:
  ```
  - `SELECT * FROM chat_sessions WHERE session_id = ? AND user_id = ?`, `.fetchone()`, `None` on
    miss, else `_row_to_chat_session(row)`.
  - Docstring records AC 3 explicitly: a row that exists but belongs to another user returns `None`,
    identically to a row that does not exist. Not an exception, and not a distinguishable one — the
    same refusal-to-be-an-oracle reasoning `find_user_by_token_hash` (`app/db/database.py:1123-1147`)
    already applies to credentials.
  - Do **not** copy that function's `MissingRelationError` arm. It exists because credential
    resolution needs a closed door rather than a 500; a missing `chat_sessions` table is a broken
    boot and must surface.
- **Mirror**: `app/db/database.py:1111-1121` (`get_user`)
- **Validate**: `pytest tests/test_chat_sessions.py -k get -q`.

### Task 5: `list_chat_sessions`

- **File**: `app/db/database.py`
- **Action**: UPDATE
- **Implement**:
  ```python
  def list_chat_sessions(user_id: str, limit: int = 50) -> list[ChatSession]:
  ```
  - `SELECT * FROM chat_sessions WHERE user_id = ? ORDER BY updated_at DESC LIMIT ?`.
  - `user_id` is first and undefaulted; `limit` is second with a literal default, matching
    `list_users(limit: int = 100)`. **Do not read `settings.CHAT_SESSION_LIMIT` here** — no function
    in this module reads a setting for a limit, and that policy belongs to the service layer
    (STORY-006), exactly as `app/routers/admin.py:53` passes `limit=100` explicitly.
  - `WHERE user_id = ? ORDER BY updated_at DESC` is the index `idx_chat_sessions_user_updated`
    read exactly (`app/db/models.py:109-112`).
  - Docstring records the known tie: second-resolution TEXT timestamps mean two sessions touched in
    the same second order arbitrarily (PRD-006 Section 13). For the rail a tie is cosmetic; for the
    transcript it is not, which is why STORY-005 orders `chat_messages` by `id`.
- **Mirror**: `app/db/database.py:1149-1156` (`list_users`)
- **Validate**: `pytest tests/test_chat_sessions.py -k list -q`.

### Task 6: `rename_chat_session`

- **File**: `app/db/database.py`
- **Action**: UPDATE
- **Implement**:
  ```python
  def rename_chat_session(session_id: str, user_id: str, title: str) -> bool:
  ```
  - `UPDATE chat_sessions SET title = ? WHERE session_id = ? AND user_id = ?`, then
    `return cursor.rowcount == 1`.
  - **`updated_at` is deliberately not touched.** Renaming is not activity, and a rename that
    reordered the rail would move the row the user was just looking at. Say this in the docstring;
    it is exactly the kind of omission a later reader "fixes".
  - The `False` arm covers both "no such session" and "someone else's session" — the zero-row case
    PRD-007 STORY-006 flagged as the one that regresses silently.
- **Mirror**: `app/db/database.py:1202-1210` (`set_user_token_hash`)
- **Validate**: `pytest tests/test_chat_sessions.py -k rename -q`.

### Task 7: `touch_chat_session`

- **File**: `app/db/database.py`
- **Action**: UPDATE
- **Implement**:
  ```python
  def touch_chat_session(session_id: str, user_id: str) -> bool:
  ```
  - `UPDATE chat_sessions SET updated_at = ? WHERE session_id = ? AND user_id = ?` with
    `datetime.now(timezone.utc).strftime(_TIMESTAMP_FORMAT)`, then `return cursor.rowcount == 1`.
  - Same `False` arm and same reason as Task 6.
  - Docstring: this is the send path's reorder — PRD Section 6's send-path diagram calls it after
    `append_chat_message` — and it is the only function that writes `updated_at` after creation.
- **Mirror**: `app/db/database.py:1202-1210` (`set_user_token_hash`)
- **Validate**: `pytest tests/test_chat_sessions.py -k touch -q`.

### Task 8: `delete_chat_session` — both deletes in one transaction

- **File**: `app/db/database.py`
- **Action**: UPDATE
- **Implement**:
  ```python
  def delete_chat_session(session_id: str, user_id: str) -> bool:
      with _session() as conn:
          conn.execute(
              """
              DELETE FROM chat_messages
               WHERE session_id = ?
                 AND session_id IN (
                     SELECT session_id FROM chat_sessions
                      WHERE session_id = ? AND user_id = ?
                 )
              """,
              (session_id, session_id, user_id),
          )
          cursor = conn.execute(
              "DELETE FROM chat_sessions WHERE session_id = ? AND user_id = ?",
              (session_id, user_id),
          )
          return cursor.rowcount == 1
  ```
  - **The subselect is the point of AC 7**, and is the one statement in this story that is not a
    mechanical copy of an existing one. `chat_messages` carries no `user_id` column
    (`app/db/models.py:131-149`), so a delete scoped by `session_id` alone would destroy a foreign
    owner's messages while correctly refusing to delete their session row: the return value would
    say `False` and the data would be gone anyway.
  - **Messages first, then the session**, in that order, inside **one** `_session()` block.
    STORY-002 deliberately declared no foreign key; this transaction is the enforcement, and the
    story that adds a foreign key must replace it with something.
  - **No `audit_logs` statement of any kind.** PRD Section 9: "the orphaned `session_id` on those
    rows is expected, and it is what preserves the evidence when a user tidies their list." The
    docstring says so, and the test asserts `count_audit_logs()` across the call rather than
    trusting the absence of a statement.
- **Mirror**: transaction shape from `init_db` (`app/db/database.py:486-493`) — several statements,
  one block; boolean return from `app/db/database.py:1191-1200`.
- **Validate**: `pytest tests/test_chat_sessions.py -k delete -q`.

### Task 9: `tests/test_chat_sessions.py`

- **File**: `tests/test_chat_sessions.py`
- **Action**: CREATE
- **Implement**: a module docstring naming STORY-004 and stating that STORY-005 extends this same
  file with the message round trips, so the next author adds to it rather than opening a third.
  Import `inspect`, `uuid`, `datetime`, `from app.db import database`, the six functions plus
  `count_audit_logs`, `insert_audit_log`, `insert_user`, `get_connection`, and `AuditLog` / `User`
  from `app.db.models`. Every test takes `temp_db`.

  Tests, one per acceptance criterion:
  1. `test_the_six_functions_are_declared` — AC 1. `hasattr(database, name)` and `callable(...)`
     for the six names.
  2. `test_every_signature_requires_an_undefaulted_user_id` — AC 2. For each of the six,
     `inspect.signature(...).parameters["user_id"]` exists, `param.default is inspect.Parameter.empty`,
     and `param.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD`. Assert with the name in the
     message, as `tests/test_db.py:1289` does.
  3. `test_every_statement_scopes_on_user_id` — AC 2, the SQL half. Read each of the six with
     `inspect.getsource(...)` and assert `"user_id = ?"` appears. A crude check a later reader can
     strengthen; it catches the exact regression Risk 2 names.
  4. `test_create_returns_a_uuid4_string_that_get_retrieves` — AC 8. `uuid.UUID(sid).version == 4`,
     then `get_chat_session(sid, "ana")` returns a `ChatSession` with the same id and title through
     a **separate** call.
  5. `test_create_stamps_created_at_and_updated_at_together` — both parse under
     `_TIMESTAMP_FORMAT` via `datetime.strptime`, and are equal on a fresh row.
  6. `test_get_chat_session_returns_none_for_a_foreign_owner` — AC 3. Seed under `ana`, read as
     `bob`, assert `is None`; and assert an unknown id returns the same `None`, so the two cases
     are indistinguishable.
  7. `test_list_orders_by_updated_at_desc_and_caps_at_limit` — AC 4. Seed three sessions for `ana`
     and set explicit descending `updated_at` values through `get_connection()`; assert the order,
     and that `limit=2` returns two.
  8. `test_list_never_returns_another_users_rows` — AC 4. `ana` has 2, `bob` has 1;
     `list_chat_sessions("bob")` returns exactly `bob`'s, and `list_chat_sessions("nobody") == []`.
  9. `test_rename_returns_true_when_owned_and_false_otherwise` — AC 5. Owned → `True` and the title
     changed; unknown id → `False`; foreign owner → `False` **and the title is unchanged**.
  10. `test_rename_leaves_updated_at_alone` — the Task 6 decision, asserted so a later change to
      "fix" it fails here.
  11. `test_touch_moves_updated_at_and_returns_true` plus
      `test_touch_returns_false_for_unknown_or_foreign` — AC 5. Seed `updated_at` in the past
      explicitly, touch, assert it moved and that `created_at` did not.
  12. `test_delete_removes_the_session_and_its_messages` — AC 6. Insert `chat_messages` rows
      directly through `get_connection()` — `append_chat_message` is STORY-005 and must not be
      depended on here — delete, then assert both tables hold zero rows for that session and the
      call returned `True`.
  13. `test_delete_leaves_audit_logs_untouched` — AC 6. `insert_audit_log(AuditLog(...))` twice,
      capture `count_audit_logs()`, delete, assert the count is **identical**.
  14. `test_delete_with_a_foreign_user_deletes_nothing` — AC 7, the one that matters most. `ana`
      owns a session with two messages; `delete_chat_session(sid, "bob")` returns `False`, the
      session row survives, and **both message rows survive** — counted with a direct
      `SELECT COUNT(*)`, not inferred from the return value.
  15. `test_two_users_see_nothing_of_each_others_sessions` — AC 9. The summarising test: create
      `ana` and `bob` through `insert_user` so the fixture data is real, then drive `get_`, `list_`,
      `rename_`, `touch_` and `delete_` with the other's id and assert `None` / `[]` / `False` in
      each case.
- **Mirror**: `tests/test_db.py:1877-1925` for the seed-assert shape; `tests/test_db.py:1266-1289`
  for the signature assertions.
- **Validate**: `pytest tests/test_chat_sessions.py -q` — all green.

### Task 10: Full-suite regression check

- **File**: —
- **Action**: verify
- **Implement**: run the whole suite. The 22 existing functions are untouched, so nothing should
  move; a failure here means Task 1's import edit or a stray reorganisation, not a new test.
- **Note**: if the run produces *mass* fixture errors rather than a handful of failures, the libSQL
  dev container has degraded — restart it and re-run before reading the failures as code defects.
  Recorded during STORY-003 validation.
- **Validate**: `pytest -q`.

---

## End-to-End Tests

- [ ] Start the libSQL dev server, run `python -c "from app.db.database import init_db; init_db()"`
      against it, then drive a full lifecycle in a REPL: `create_chat_session("ana", "First")` →
      `get_chat_session(sid, "ana")` → `rename_chat_session(sid, "ana", "Renamed")` →
      `touch_chat_session(sid, "ana")` → `list_chat_sessions("ana")` →
      `delete_chat_session(sid, "ana")` → `get_chat_session(sid, "ana") is None`.
- [ ] The same lifecycle driven with `"bob"` at each step returns `None` / `[]` / `False` and leaves
      `ana`'s rows intact.
- [ ] `count_audit_logs()` is identical before and after a successful delete, with audit rows present.
- [ ] `init_db()` run twice in one process still issues no `ALTER` — this story adds no DDL, so
      `test_init_db_issues_no_alter_when_schema_is_current` must stay green untouched.

---

## Validation

```bash
# libSQL dev server must be up (tests/conftest.py:26-32)
docker start harness-libsql-dev

pytest tests/test_chat_sessions.py -q      # this story's suite
pytest tests/test_db.py -q                 # the 22 untouched functions
pytest -q                                  # full suite
python -c "import app.db.database"         # import-time sanity
```

---

## Acceptance Criteria

(Copied from story `STORY-004`)

- [ ] Given `app/db/database.py`, when it is read, then it declares `create_chat_session`,
      `get_chat_session`, `list_chat_sessions`, `rename_chat_session`, `touch_chat_session` and
      `delete_chat_session`.
- [ ] Given every one of those six signatures, when it is inspected, then `user_id: str` is
      **required and undefaulted**, and every statement they issue carries `WHERE ... user_id = ?`.
- [ ] Given `get_chat_session(session_id, user_id)` where the row exists but belongs to another
      user, when it is called, then it returns `None` — not the row, and not an exception that
      distinguishes "yours but missing" from "someone else's".
- [ ] Given `list_chat_sessions(user_id, limit)`, when it is called, then it returns that user's
      sessions ordered `updated_at DESC`, capped at `limit`, and never a row belonging to anyone
      else.
- [ ] Given `rename_chat_session` and `touch_chat_session`, when the target exists and is owned,
      then each returns `True`; when it does not exist, or exists under another user, then each
      returns `False`.
- [ ] Given `delete_chat_session(session_id, user_id)`, when it is called on an owned session, then
      the session row and every one of its `chat_messages` rows are removed **inside one
      `_session()` block**, and `count_audit_logs()` is identical before and after.
- [ ] Given `delete_chat_session` called with a foreign `user_id`, when it returns, then it returns
      `False` and **no message row is deleted**.
- [ ] Given `create_chat_session`, when it returns, then the new `session_id` is a UUID4 string and
      `get_chat_session` retrieves the same row through a separate call.
- [ ] Given `tests/test_chat_sessions.py`, when it runs, then two users are created and every read
      and write path is driven with the other user's id, asserting empty or `False` in each case.
- [ ] All tasks completed
- [ ] The existing 22 functions in `database.py` are unmodified and the module is not reorganised
- [ ] Full suite green
