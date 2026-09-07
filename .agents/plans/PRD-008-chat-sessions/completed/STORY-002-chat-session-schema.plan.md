---
story: STORY-002
prd: PRD-008
slug: chat-session-schema
title: "chat_sessions and chat_messages DDL and dataclasses in app/db/models.py"
type: NEW_CAPABILITY
complexity: LOW
epic_branch: epic/PRD-008-chat-sessions
created: 2026-09-03
---

# Plan: chat_sessions and chat_messages DDL and dataclasses in app/db/models.py

## Summary

Declare the transcript schema in `app/db/models.py` and nowhere else: two `CREATE TABLE IF NOT EXISTS` constants (`CREATE_CHAT_SESSIONS_TABLE`, `CREATE_CHAT_MESSAGES_TABLE`), the two `CREATE INDEX IF NOT EXISTS` constants that serve the only two access paths STORY-004 and STORY-005 will take, one new entry `"session_id": "TEXT"` in `AUDIT_LOGS_ADDED_COLUMNS`, and the `ChatSession` / `StoredMessage` dataclasses that mirror the two tables the way `AuditLog` and `User` mirror theirs. `AuditLog` gains `session_id: Optional[str] = None`. No SQL executes in this story — `init_db()` is STORY-003's edit, and the new table constants sit unreferenced by `database.py` until then.

`chat_messages` is `ChatMessage` from `chat_ui/chat_ui/models.py` given a table, minus exactly two fields. `duplicate_relative_info` and `duplicate_release_info` get **no column**, because they are humanized copy — PRD Section 6 fixes the rule ("the humanized copy is recomputed on load, not stored, so it stays relative to *now*"), and a stored `"2m ago"` is wrong the moment it is read back. Everything else a restored bubble needs to render through the existing `rx.match` is a column, because a lossier second model is precisely how a reloaded transcript would come to read differently from a live one — the bug this PRD exists to remove.

Exploration turned up three things the story text does not state, and each changes the diff:

1. **`_add_missing_columns` is already generic.** It iterates `AUDIT_LOGS_ADDED_COLUMNS` (`app/db/database.py:481`), so the instant `"session_id"` enters that dict, `init_db()` starts adding the column — in this story, not STORY-003. STORY-003 wires the *tables*; the *column* converges the moment the mapping changes.
2. **That makes one existing assertion fail.** `test_schema_has_no_ip_or_location_column` (`tests/test_db.py:441-466`) pins the `audit_logs` column set with `assert set(columns) == expected`. It must gain `"session_id"` in this story or the suite is red at the end of it. `tests/test_db.py` is *not* on PRD Section 15's "must pass unmodified" list, and this story's AC 9 explicitly expects it to be extended, so this is sanctioned — but it has to be done here.
3. **`session_id` belongs in `CREATE_AUDIT_LOGS_TABLE` as well as in the added-columns mapping.** Every column ever added through that mapping — `pii_detected_input`, `pii_detected_output`, `pii_entities`, `role`, `denied_permission` — appears in *both* (`app/db/models.py:5-25` and `:33-39`). The mapping migrates an old database; the `CREATE` is the current shape a fresh one is built to. Listing it in only one place would mean every new deployment ALTERs its own brand-new table on first boot, which is the opposite of PRD Section 11's "`init_db()` issues no `ALTER` on a current schema". Task 2 does both, following the established pair.

There is no linter and no formatter in this repo — CI runs `pip install -r requirements.txt` then `pytest -q` — so "validate" means the suite, and the suite needs the local libSQL dev server documented at `tests/conftest.py:26-31`.

## User Story

As a **maintainer**
I want the two transcript tables declared alongside `audit_logs` and `users`
So that a conversation has a shape in the schema before anything tries to write one.

## Story Reference

- Story file: `.agents/stories/PRD-008-chat-sessions/STORY-002-chat-session-schema.md`
- PRD: `.agents/PRDs/PRD-008-chat-sessions/PRD.md` — Section 4 (Schema), Section 6 (stored message table, Ordering), Section 8, Section 12 Phase 1, Risk 7
- Constraint quoted verbatim from `app/db/models.py:29-33`: "Additive only: no drops, renames, or type changes. Every NOT NULL entry needs a non-NULL DEFAULT -- SQLite rejects ADD COLUMN NOT NULL without one."

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY (declaration only — no SQL executed, no function added) |
| Complexity | LOW — one source file, one test file |
| Systems Affected | `app/db/models.py`, `tests/test_db.py` |
| Story | STORY-002 |
| PRD | PRD-008 |
| Epic Branch | `epic/PRD-008-chat-sessions` (commit directly on this branch) |

---

## Skills In Use

`.agents/skills/` was listed in full. It holds exactly one skill:

| Skill | Applies? | Reason |
|-------|----------|--------|
| `frontend-design` | **No** | Its `description` scopes it to "distinctive, intentional visual design when building new UI or reshaping an existing one." This story edits `app/db/models.py` and `tests/test_db.py`. It renders nothing. |

The story's `skills:` frontmatter is `[]` and its Technical Notes reach the same conclusion independently. **No skill constrains any task below**, and no task names one. (`reflex-docs` and `reflex-process-management`, named by PRD Section 6, govern `chat_ui/` work — Phase 3 and 4 stories. Nothing here imports Reflex.)

---

## Patterns to Follow

### Naming — a table constant, its comment naming the PRD, and its index beside it

```python
# SOURCE: app/db/models.py:42-67
# Identity store (PRD-005). Lives in the same SQLite file as audit_logs -- no
# second service, no ORM, stdlib only.
#
# user_id declares NOT NULL explicitly: outside INTEGER PRIMARY KEY, SQLite lets
# a PRIMARY KEY column hold NULL, and more than one row of them.
CREATE_USERS_TABLE = """
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY NOT NULL,
    role TEXT NOT NULL,
    token_hash TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
)
"""

CREATE_USERS_TOKEN_HASH_INDEX = (
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_token_hash ON users(token_hash)"
)
```

`CREATE_<TABLE>_TABLE` for DDL, `CREATE_<TABLE>_<PURPOSE>_INDEX` for an index constant, `idx_<table>_<columns>` for the index's own name. The explicit `NOT NULL` on a TEXT primary key, and the comment giving its reason, transfer verbatim to `chat_sessions.session_id`.

### Error handling — the invariant is stated in a comment and enforced by a test, not by review

```python
# SOURCE: app/db/models.py:27-39
# Columns added after the initial schema shipped (PRD-003 PII telemetry; PRD-005
# RBAC adds to this in STORY-009). CREATE TABLE IF NOT EXISTS is a no-op against
# a database created before they existed, so init_db() ALTERs in whichever of
# these an old file is missing.
# Additive only: no drops, renames, or type changes.
# Every NOT NULL entry needs a non-NULL DEFAULT -- SQLite rejects ADD COLUMN
# NOT NULL without one. Enforced by
# tests/test_db.py::test_added_columns_declaring_not_null_also_declare_a_default.
AUDIT_LOGS_ADDED_COLUMNS = {
    "pii_detected_input": "INTEGER NOT NULL DEFAULT 0",
    ...
    "denied_permission": "TEXT",
}
```

`"session_id": "TEXT"` is nullable, so it is compliant by construction and `test_added_columns_declaring_not_null_also_declare_a_default` (`tests/test_db.py:62-78`) keeps passing **unmodified** — that test only constrains entries containing `NOT NULL`. Nullable is also right on the merits: PRD Section 10 requires a request that omits `session_id` to write `NULL`.

### Dataclasses — required fields first, optionals defaulted, surrogate key last

```python
# SOURCE: app/db/models.py:70-99
@dataclass
class AuditLog:
    timestamp: str
    user_id: str
    prompt_hash: str
    device: Optional[str] = None
    ...
    denied_permission: Optional[str] = None
    id: Optional[int] = None


@dataclass
class User:
    user_id: str
    role: str
    token_hash: str
    active: bool = True
    created_at: Optional[str] = None  # insert_user() stamps it when omitted
```

Two rules read off this: the autoincrement `id` is the **last** field, and a timestamp the insert function stamps is `Optional[str] = None` with an inline comment saying so. `session_id` therefore goes immediately *before* `AuditLog.id`, which keeps `id` trailing and breaks nothing — every one of the 20-odd call sites found by `grep -rn "AuditLog(" app tests chat_ui` is keyword-only.

### Booleans — INTEGER with an explicit default in SQL, `bool` in the dataclass

```python
# SOURCE: app/db/models.py:16-20
    was_duplicate_blocked INTEGER NOT NULL DEFAULT 0,
    ...
    pii_detected_input INTEGER NOT NULL DEFAULT 0,
```
```python
# SOURCE: app/db/models.py:80,84
    was_duplicate_blocked: bool = False
    pii_detected_input: bool = False
```

`pii_redacted` on `chat_messages` follows exactly: `INTEGER NOT NULL DEFAULT 0` in the DDL, `bool = False` on `StoredMessage`.

### Tests — one test per claim, docstring stating why the claim matters

```python
# SOURCE: tests/test_db.py:1227-1252
def test_users_schema_matches_expected_columns(temp_db):
    """Pins the identity schema, including the explicit NOT NULL on user_id.

    Outside INTEGER PRIMARY KEY, SQLite lets a PRIMARY KEY column hold NULL --
    and more than one row of them -- so dropping that NOT NULL would silently
    allow nameless users in the table that answers "who is this".
    """
    with get_connection() as conn:
        info = list(conn.execute("PRAGMA table_info(users)"))

    columns = {row["name"]: row for row in info}
    assert set(columns) == {"user_id", "role", "token_hash", "active", "created_at"}
    for name, row in columns.items():
        assert row["notnull"] == 1, f"{name} must be NOT NULL"
    assert columns["active"]["dflt_value"] == "1"
    assert columns["user_id"]["pk"] == 1
```

**But note the fixture.** `temp_db` gives a database that `init_db()` has already built — and `init_db()` does not know about the new tables until STORY-003. So the tests this story adds assert against the **DDL constants as strings**, not against `PRAGMA table_info`. That is what AC 9 asks for in its own words ("the new DDL constants asserted for the `IF NOT EXISTS` clause and for the explicit `NOT NULL` on both key columns"), and it is what keeps this story's tests green before its successor lands. STORY-003's AC 6 owns the `PRAGMA table_info(chat_messages)` assertion; writing it here would fail.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/db/models.py` | UPDATE | The two DDL constants, the two index constants, `session_id` in `CREATE_AUDIT_LOGS_TABLE` and in `AUDIT_LOGS_ADDED_COLUMNS`, `AuditLog.session_id`, `ChatSession`, `StoredMessage` |
| `tests/test_db.py` | UPDATE | New constant-level assertions; `"session_id"` added to the pinned `audit_logs` column set at `:441` |

No file is created. `app/db/database.py` is **not** touched — it does not import the new table constants until STORY-003.

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Add `session_id` to `AUDIT_LOGS_ADDED_COLUMNS`

- **File**: `app/db/models.py`
- **Action**: UPDATE
- **Implement**: Add `"session_id": "TEXT",` as the last entry of the `AUDIT_LOGS_ADDED_COLUMNS` dict, and extend the comment block above it to name PRD-008 alongside PRD-003 and PRD-005 — that comment is the register of which PRD added what, and leaving it stale is how the next reader mis-attributes a column. Nullable, no default: the compliant shape under the block's own stated rule, and PRD Section 10 requires an omitted `session_id` to write `NULL`.
- **Mirror**: `app/db/models.py:27-39` — the existing mapping, with `"denied_permission": "TEXT"` as the precedent for a bare nullable TEXT entry.
- **Do not**: touch `_add_missing_columns` in `app/db/database.py`. It iterates this dict and needs no edit — STORY-003's Technical Notes say "if you find yourself editing that function, stop and ask why."
- **Validate**: `python -c "from app.db.models import AUDIT_LOGS_ADDED_COLUMNS as c; assert c['session_id'] == 'TEXT'"`, then `pytest tests/test_db.py::test_added_columns_declaring_not_null_also_declare_a_default -q` (must pass with that test unmodified).

### Task 2: Add `session_id TEXT` to `CREATE_AUDIT_LOGS_TABLE`

- **File**: `app/db/models.py`
- **Action**: UPDATE
- **Implement**: Append `session_id TEXT` as the final column of the `CREATE_AUDIT_LOGS_TABLE` body, after `denied_permission TEXT`. Nullable, no default, matching Task 1's mapping entry exactly — the two declarations of one column must agree or a fresh database and a migrated one diverge.
- **Mirror**: `app/db/models.py:20-23` — `pii_entities`, `role` and `denied_permission` each appear in *both* the `CREATE` and the added-columns mapping. This is the house pair, not a duplication to optimize away: the mapping is for a database that predates the column, the `CREATE` is the current shape.
- **Why this is in scope though AC 6 names only the mapping**: without it, every fresh deployment ALTERs its own newly created table on first boot, contradicting PRD Section 11's "`init_db()` issues no `ALTER` on a current schema" and undercutting Risk 7's mitigation. It also keeps `test_init_db_issues_no_alter_when_schema_is_current` (`tests/test_db.py:112`) true for the right reason rather than by accident of fixture ordering.
- **Validate**: `pytest tests/test_db.py -q` — expect exactly one failure at this point, `test_schema_has_no_ip_or_location_column`, which Task 7 repairs. Confirm the failure names `session_id` and nothing else; any other failure means the DDL is malformed.

### Task 3: Declare `CREATE_CHAT_SESSIONS_TABLE` and its index

- **File**: `app/db/models.py`
- **Action**: UPDATE
- **Implement**: After `CREATE_USERS_TOKEN_HASH_INDEX`, add a comment block naming PRD-008 and the two tables, then:

```python
CREATE_CHAT_SESSIONS_TABLE = """
CREATE TABLE IF NOT EXISTS chat_sessions (
    session_id TEXT PRIMARY KEY NOT NULL,
    user_id TEXT NOT NULL,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

CREATE_CHAT_SESSIONS_USER_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_updated "
    "ON chat_sessions(user_id, updated_at DESC)"
)
```

  The comment must carry the `session_id` NOT NULL reason in the `users` table's own words — "outside INTEGER PRIMARY KEY, SQLite lets a PRIMARY KEY column hold NULL, and more than one row of them" (AC 2 requires it verbatim) — and must state the no-foreign-key decision from the story's Technical Notes: SQLite enforces foreign keys only under `PRAGMA foreign_keys=ON` per connection, the shared libSQL client from PRD-007 gives no place to guarantee that on every path, and a declared-but-unenforced constraint reads as a guarantee it is not. STORY-004's single-transaction `delete_chat_session` is the enforcement.
- **Not `UNIQUE`**: unlike `idx_users_token_hash`, this index serves ordering and filtering, not a uniqueness claim — one user has many sessions. `(user_id, updated_at DESC)` is the exact shape of STORY-004's `list_chat_sessions` read: filter by owner, newest activity first.
- **Mirror**: `app/db/models.py:42-67`.
- **Validate**: `python -c "from app.db import models as m; assert 'IF NOT EXISTS' in m.CREATE_CHAT_SESSIONS_TABLE; assert 'session_id TEXT PRIMARY KEY NOT NULL' in m.CREATE_CHAT_SESSIONS_TABLE; assert 'user_id TEXT NOT NULL' in m.CREATE_CHAT_SESSIONS_TABLE"`

### Task 4: Declare `CREATE_CHAT_MESSAGES_TABLE` and its index

- **File**: `app/db/models.py`
- **Action**: UPDATE
- **Implement**: Directly below Task 3's block:

```python
CREATE_CHAT_MESSAGES_TABLE = """
CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    prompt TEXT,
    model_used TEXT,
    tokens_used INTEGER,
    audit_id INTEGER,
    pii_redacted INTEGER NOT NULL DEFAULT 0,
    pii_entities TEXT,
    pattern TEXT,
    required_permission TEXT,
    first_query_at TEXT,
    detail TEXT
)
"""

CREATE_CHAT_MESSAGES_SESSION_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_chat_messages_session_id "
    "ON chat_messages(session_id, id)"
)
```

- **Field-by-field justification** — this is the mapping STORY-015 rehydrates through, so it is worth stating once, here:

  | Column | Source | Why this shape |
  |---|---|---|
  | `id` | — | `INTEGER PRIMARY KEY AUTOINCREMENT`; PRD Section 6 "Ordering" makes it *the* order, read `ORDER BY id ASC`, never by timestamp |
  | `session_id`, `kind`, `content` | `ChatMessage.kind` / `.content` | The three facts every bubble has; `NOT NULL` |
  | `created_at` | stamped on insert | `NOT NULL`, displayed only — never sorted on |
  | `prompt` | `ChatMessage.prompt` | TEXT, nullable — only `user`-kind rows carry it |
  | `model_used` | `ChatMessage.model_used` | TEXT |
  | `tokens_used` | `ChatMessage.tokens_used` | INTEGER |
  | `audit_id` | `ChatMessage.audit_id` | INTEGER — the join back to `audit_logs`, mirroring the `session_id` join Task 1 adds in the other direction |
  | `pii_redacted` | `ChatMessage.pii_redacted` | `INTEGER NOT NULL DEFAULT 0`, the boolean convention `audit_logs` uses throughout |
  | `pii_entities` | `ChatMessage.pii_entities: list[str]` | **TEXT, comma-joined** — matching `",".join(pii_entities)` at `app/services/audit_logger.py:45`. One encoding for one concept; do not invent JSON here |
  | `pattern`, `required_permission`, `first_query_at`, `detail` | same names on `ChatMessage` | TEXT, each nullable — each belongs to one verdict kind |

- **Two columns deliberately absent**: `duplicate_relative_info` and `duplicate_release_info`. AC 4 and PRD Section 6 — the humanized copy is recomputed on load so it stays relative to *now*; a stored `"2m ago"` is wrong the moment it is read back. Put a comment on the DDL saying so. Their absence is a decision and must not read as an oversight.
- **One column deliberately absent**: `archived`. Per the story's Technical Notes it appeared in an early scope draft, is not in PRD Section 4's final list, and deletion is the only lifecycle operation this PRD ships.
- **No foreign key** on `session_id` — reasoning in Task 3.
- **Index shape**: `(session_id, id)` is STORY-005's `list_chat_messages` read exactly — every message of one session, in key order.
- **Validate**: `python -c "from app.db import models as m; d = m.CREATE_CHAT_MESSAGES_TABLE; assert 'id INTEGER PRIMARY KEY AUTOINCREMENT' in d; assert all(n in d for n in ('prompt','model_used','tokens_used','audit_id','pii_redacted','pii_entities','pattern','required_permission','first_query_at','detail')); assert 'duplicate_relative_info' not in d and 'duplicate_release_info' not in d"`

### Task 5: Add `session_id` to the `AuditLog` dataclass

- **File**: `app/db/models.py`
- **Action**: UPDATE
- **Implement**: Insert `session_id: Optional[str] = None` between `denied_permission` and `id`.
- **Mirror**: `app/db/models.py:70-91`. The position is the point: `id` stays the trailing field, matching the shape `AuditLog` and `User` already have, and no construction anywhere changes.
- **Scope boundary**: this story adds the *field* only. `insert_audit_log`, `_row_to_audit_log` (`app/db/database.py:525`, `:575`) and `log_query` are STORY-008's edit. Until then a read returns `session_id=None` regardless of the column's value — correct and inert, because nothing reads the attribute yet.
- **Validate**: `pytest tests/test_db.py tests/test_audit_router.py tests/test_admin_state.py tests/test_admin_models.py -q` — all pass except the one known failure from Task 2.

### Task 6: Add the `ChatSession` and `StoredMessage` dataclasses

- **File**: `app/db/models.py`
- **Action**: UPDATE
- **Implement**: After `User`, in the same style:

```python
@dataclass
class ChatSession:
    session_id: str
    user_id: str
    title: str
    created_at: Optional[str] = None  # create_chat_session() stamps it when omitted
    updated_at: Optional[str] = None  # touch_chat_session() moves it


@dataclass
class StoredMessage:
    session_id: str
    kind: str
    content: str
    prompt: Optional[str] = None
    model_used: Optional[str] = None
    tokens_used: Optional[int] = None
    audit_id: Optional[int] = None
    pii_redacted: bool = False
    pii_entities: Optional[str] = None
    pattern: Optional[str] = None
    required_permission: Optional[str] = None
    first_query_at: Optional[str] = None
    detail: Optional[str] = None
    created_at: Optional[str] = None  # append_chat_message() stamps it when omitted
    id: Optional[int] = None
```

- **Mirror**: `AuditLog` for the required-then-optional-then-`id` ordering and the `bool` convention; `User.created_at`'s inline comment for the stamped-on-insert note.
- **`pii_entities: Optional[str]`, not `list[str]`** — the dataclass mirrors the *table*, and the table stores the comma-joined string. Splitting it is the rehydration step STORY-015 owns, on the way back into `ChatMessage`.
- **Validate**: `python -c "import dataclasses; from app.db.models import ChatSession, StoredMessage; print([f.name for f in dataclasses.fields(StoredMessage)])"` — the field names must match the `chat_messages` columns one for one.

### Task 7: Extend `tests/test_db.py`

- **File**: `tests/test_db.py`
- **Action**: UPDATE
- **Implement**, in two parts:

  **(a) Repair the pinned column set.** In `test_schema_has_no_ip_or_location_column` (`tests/test_db.py:441-466`), add `"session_id"` to `expected`. This is required, not optional: `_add_missing_columns` iterates `AUDIT_LOGS_ADDED_COLUMNS`, so Task 1 alone makes the column real on every database and `assert set(columns) == expected` fails. The test's actual claim — no `ip` and no `location` column — is untouched, and the `not any(...)` line below still holds (`session_id` contains neither substring). `tests/test_db.py` is absent from PRD Section 15's must-pass-unmodified list precisely so schema stories can do this.

  **(b) Add constant-level tests**, near the existing `users` schema tests around `tests/test_db.py:1219`, asserting against the DDL **strings** rather than `PRAGMA` (see Patterns → Tests for why):

  - `test_chat_session_ddl_declares_if_not_exists` and `test_chat_message_ddl_declares_if_not_exists` — AC 5's idempotency claim and Risk 7's mitigation, checkable before `init_db()` ever runs them.
  - `test_chat_session_key_columns_declare_not_null_explicitly` — `session_id TEXT PRIMARY KEY NOT NULL` and `user_id TEXT NOT NULL`, docstring restating the `users` reason: outside `INTEGER PRIMARY KEY`, SQLite lets a PRIMARY KEY column hold NULL, and more than one row of them.
  - `test_chat_messages_ddl_carries_every_restorable_chat_message_field` — parametrized or looped over the ten metadata names, so the list is legible and a dropped column names itself in the failure.
  - `test_chat_messages_ddl_stores_no_humanized_duplicate_copy` — asserts `duplicate_relative_info` and `duplicate_release_info` are absent, with PRD Section 6's sentence as the docstring. This is the one test that will look strange to a future reader, so it is the one that most needs its reason written down.
  - `test_chat_indexes_cover_the_two_read_paths` — `idx_chat_sessions_user_updated` over `chat_sessions(user_id, updated_at DESC)` and `idx_chat_messages_session_id` over `chat_messages(session_id, id)`, both `CREATE INDEX IF NOT EXISTS`.
  - `test_audit_logs_added_columns_carries_a_nullable_session_id` — `AUDIT_LOGS_ADDED_COLUMNS["session_id"] == "TEXT"`, and `CREATE_AUDIT_LOGS_TABLE` declares it too, pinning the both-places pair from Task 2.
  - `test_audit_log_carries_session_id_without_breaking_construction` — `AuditLog(timestamp=..., user_id=..., prompt_hash=...).session_id is None`, and a keyword-constructed row with `session_id="..."` keeps it.
  - `test_stored_message_mirrors_the_chat_messages_columns` — `{f.name for f in dataclasses.fields(StoredMessage)}` equals the column names parsed out of `CREATE_CHAT_MESSAGES_TABLE`. This is the test that stops the dataclass and the table drifting, which is the real long-run risk in this file.

  Extend the module's `from app.db.models import ...` block with the five new constants and the two new dataclasses. `dataclasses` needs importing; `inspect` and `re` are already imported at `tests/test_db.py:6-7`.
- **Do not add**: any `PRAGMA table_info(chat_sessions)` or `PRAGMA table_info(chat_messages)` test. `init_db()` does not create those tables until STORY-003, whose AC 6 owns that assertion; written here it fails.
- **Mirror**: `tests/test_db.py:1227-1252` for the docstring-states-the-why shape; `tests/test_db.py:62-78` for a constant-level test that needs no database.
- **Validate**: `pytest tests/test_db.py -q` — fully green.

### Task 8: Full-suite regression

- **File**: — (verification only)
- **Action**: none
- **Implement**: Run the whole suite and confirm the blast radius is exactly the two files this plan touches.
- **Validate**: `pytest -q`. Every suite in PRD Section 15's must-pass-unmodified list passes with no edit: `tests/test_query_router.py`, `tests/test_integration.py`, `tests/test_route_reservations.py`, `tests/test_admin_auth.py`, `tests/test_audit_router.py`, `tests/test_stats_router.py`, `tests/test_rbac.py`, `tests/test_authz.py`, `tests/test_identity.py`, `tests/test_duplicate_checker.py`, `tests/test_pattern_detector.py`, `tests/test_pii_redactor.py`, `tests/test_summary.py`, `tests/test_register.py`. Then `git status --short` shows only `app/db/models.py` and `tests/test_db.py`.

---

## Risks + Mitigations

| Risk | Mitigation |
|---|---|
| Adding `session_id` to the mapping silently migrates every database mid-story, breaking a pinned column set | Task 2's validate step *expects* that one failure and names it; Task 7(a) repairs it in the same story. Called out here so it reads as sequencing, not breakage. |
| The dataclass and the table drift as later stories add fields | `test_stored_message_mirrors_the_chat_messages_columns` compares them mechanically rather than by eye. |
| A reviewer "helpfully" adds the missing foreign key on `chat_messages.session_id` | The decision and its reason live in the DDL comment (Task 3), not only in the story file, so the argument travels with the code. |
| A later story stores `duplicate_relative_info` because the column looks missing | `test_chat_messages_ddl_stores_no_humanized_duplicate_copy` fails on it, with PRD Section 6's sentence in the docstring. |
| `AuditLog.session_id` is set but never persisted, and someone assumes it round-trips | Task 5 states the boundary explicitly; STORY-008 owns `insert_audit_log` and `_row_to_audit_log`. No test in this story asserts a round trip, because there is not one yet. |

---

## End-to-End Tests

The suite needs the local libSQL dev server (`tests/conftest.py:26-31`) — offline, no token, cannot reach production:

```bash
docker run -d --name harness-libsql-dev -p 8080:8080 -e SQLD_NODE=primary \
  ghcr.io/tursodatabase/libsql-server@sha256:6dd3eb276d9d3604e4a48ac4a999a2e267814732d57d7e94c04ba71482333a67
```

- [ ] `pytest tests/test_db.py -q` → green, including the new constant-level tests
- [ ] `pytest -q` → green; no suite outside `tests/test_db.py` needed an edit
- [ ] `python -c "from app.db import models"` → imports clean; no syntax error in the DDL strings
- [ ] `python -c "from app.db.database import init_db"` → `database.py` still imports without referencing the new table constants (proves the scope boundary with STORY-003 held)
- [ ] Fresh database: `PRAGMA table_info(audit_logs)` after `init_db()` shows `session_id` nullable (`notnull == 0`, `dflt_value is None`) — the shape STORY-008 will write `NULL` into
- [ ] `git diff --stat` names exactly two files

---

## Validation

```bash
pytest tests/test_db.py -q
pytest -q
git status --short          # expect only app/db/models.py and tests/test_db.py
```

There is no lint or format step in this repo — CI (`.github/workflows/ci.yml`) installs requirements and runs `pytest -q`, and nothing else.

---

## Acceptance Criteria

(Copied from story `STORY-002`)

- [ ] `CREATE_CHAT_SESSIONS_TABLE` declares `session_id TEXT PRIMARY KEY NOT NULL`, `user_id TEXT NOT NULL`, `title TEXT NOT NULL`, `created_at TEXT NOT NULL`, `updated_at TEXT NOT NULL`
- [ ] `session_id` and `user_id` both declare `NOT NULL` **explicitly**, with the `users` table's reason stated verbatim: "outside INTEGER PRIMARY KEY, SQLite lets a PRIMARY KEY column hold NULL, and more than one row of them."
- [ ] `CREATE_CHAT_MESSAGES_TABLE` declares `id INTEGER PRIMARY KEY AUTOINCREMENT`, `session_id TEXT NOT NULL`, `kind TEXT NOT NULL`, `content TEXT NOT NULL`, `created_at TEXT NOT NULL`, plus `prompt`, `model_used`, `tokens_used`, `audit_id`, `pii_redacted`, `pii_entities`, `pattern`, `required_permission`, `first_query_at`, `detail`
- [ ] Neither `duplicate_relative_info` nor `duplicate_release_info` has a column
- [ ] `CREATE_CHAT_SESSIONS_USER_INDEX` and `CREATE_CHAT_MESSAGES_SESSION_INDEX` are `CREATE INDEX IF NOT EXISTS` over `chat_sessions(user_id, updated_at DESC)` and `chat_messages(session_id, id)`
- [ ] `AUDIT_LOGS_ADDED_COLUMNS` carries `"session_id": "TEXT"` — nullable, no default, so `test_added_columns_declaring_not_null_also_declare_a_default` holds unmodified
- [ ] `AuditLog` carries `session_id: Optional[str] = None`, positioned so no existing positional construction breaks
- [ ] `ChatSession` and `StoredMessage` mirror their tables, in the style of `AuditLog` and `User`
- [ ] `tests/test_db.py` passes, with the new DDL constants asserted for the `IF NOT EXISTS` clause and for the explicit `NOT NULL` on both key columns
- [ ] All tasks completed
- [ ] Full suite green; the fourteen suites in PRD Section 15 pass unmodified
- [ ] No SQL executed and no function added — `app/db/database.py` untouched
- [ ] Follows existing patterns
