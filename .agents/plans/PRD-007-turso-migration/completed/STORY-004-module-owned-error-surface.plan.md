---
story: STORY-004
prd: PRD-007
slug: module-owned-error-surface
title: "app/db/errors.py: a module-owned exception surface, decoupling the three catch sites from sqlite3"
type: REFACTOR
complexity: LOW
epic_branch: epic/PRD-007-turso-migration
created: 2026-09-01
---

# Plan: app/db/errors.py — a module-owned exception surface

## Summary

`app/db/` is already the only module that knows how data is stored, except for its exception
types: `app/services/duplicate_checker.py` and `scripts/manage_users.py` both `import sqlite3`
purely to name an exception class in an `except` clause. This story closes that leak **while still
running on `sqlite3`**, so the refactor is verifiable against a green baseline before the driver
swap in [[STORY-006]] removes one. The approach is a new `app/db/errors.py` declaring three
exception types, plus one `contextmanager` in `app/db/database.py` — `_translated()` — that is the
single place in the codebase aware of the driver's exception hierarchy. Every one of the 21
`with get_connection() as conn:` blocks becomes `with _session() as conn:`, which opens the
connection, keeps sqlite3's existing commit/rollback semantics, and translates any driver
exception on the way out. The three catch sites are then rewritten against the module-owned types.
No public signature, return type, or observable behavior changes, with one deliberate exception
recorded in Design Note 3.

## User Story

As a maintainer
I want `app/db/` to raise its own exceptions rather than leaking the driver's
So that swapping the driver in [[STORY-006]] cannot silently break a `catch` clause elsewhere

## Story Reference

- Story file: `.agents/stories/PRD-007-turso-migration/STORY-004-module-owned-error-surface.md`
- PRD: `.agents/PRDs/PRD-007-turso-migration/PRD.md` — Section 6 Pattern 6, Section 7.2,
  Section 11 (functional requirements), Section 12 Phase 2

## Metadata

| Field | Value |
|-------|-------|
| Type | REFACTOR |
| Complexity | LOW (small surface, high blast radius — 21 call sites, one auth path) |
| Systems Affected | `app/db/`, `app/services/duplicate_checker.py`, `scripts/manage_users.py`, `tests/test_db.py` |
| Story | STORY-004 |
| PRD | PRD-007 |
| Epic Branch | `epic/PRD-007-turso-migration` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | none | — |

`.agents/skills/` was listed and contains exactly one skill, `frontend-design`, whose
`description` scopes it to *"distinctive, intentional visual design when building new UI or
reshaping an existing one — aesthetic direction, typography, and making choices that don't read as
templated defaults."* This story changes no rendered output: it touches `app/db/`, one service
module, one CLI script, and one test file. No rule from that SKILL.md constrains any task below.
The story frontmatter's `skills: []` is confirmed correct, not merely inherited.

---

## Findings from Exploration

Five things the story does not state that change what gets built. Each was verified, not assumed.

### F1 — AC4 and AC7 are in direct contradiction; AC7 wins (user-confirmed)

AC4 asks that `scripts/manage_users.py` report a duplicate `user_id` and a duplicate `token_hash`
"distinguishably". It does not today — `scripts/manage_users.py:37-39` prints one message for both
constraint violations. STORY-002 pinned exactly that gap:

```python
# SOURCE: tests/test_manage_users_cli.py:948-990
def test_create_user_duplicate_token_hash_is_not_distinguished_from_duplicate_user_id(...):
    """PRD-007 STORY-002 characterization test -- pins a real gap, not a
    desirable behavior.
    ...
    The story's AC4 asks that the two cases be distinguishable. They are not.
    ... Making them distinguishable is a behavior change and belongs in its
    own story."""
    assert captured.err == "Error: a user with user_id 'bob' already exists.\n"
```

AC7 requires every STORY-002 characterization test to pass **unmodified**. Making the two cases
distinguishable would require rewriting that test — which AC7 forbids, and which would mix a
behavior change into the one refactor whose entire value is a green baseline.

**Resolution (confirmed with the user before planning):** preserve the CLI's current output
byte-for-byte. AC1's requirement is met in full — the module-owned integrity error **carries** the
constraint that failed (`.constraint == "users.token_hash"` vs `"users.user_id"`), so a caller
*can* tell the two apart. AC4's "distinguishably" is therefore **not met by this story** and must
be recorded as such in the story report, with the follow-up left to its own story exactly as the
STORY-002 test docstring prescribes.

### F2 — `MissingRelationError` and `IntegrityError` must subclass the general error, or two green tests go red

`app/services/duplicate_checker.py:32` catches `sqlite3.Error`, the **root** of the driver
hierarchy, which subsumes both `OperationalError` and `IntegrityError`. Two currently-passing
tests reach it through a *missing table*, not a generic failure:

```python
# SOURCE: tests/test_duplicate_checker.py:99-100
def test_malformed_db_raises_duplicate_check_error(uninitialized_db):
    with pytest.raises(DuplicateCheckError):
```
```python
# SOURCE: tests/test_query_router.py:191-215  (STORY-002 characterization test)
    with get_connection() as conn:
        conn.execute("DROP TABLE audit_logs")
    ...
    assert response.status_code == 500
```

Both induce `sqlite3.OperationalError: no such table: audit_logs`. If `MissingRelationError` were a
sibling of the general storage error rather than a subclass, `duplicate_checker`'s
`except StorageError` would stop catching it and both tests would break — one of them a
characterization test AC7 protects. So the hierarchy must mirror the driver's exactly:
`StorageError` ≙ `sqlite3.Error`, with the other two beneath it.

### F3 — Two **non**-characterization tests in `test_db.py` assert the driver type and must be updated

```python
# SOURCE: tests/test_db.py:1025-1038
def test_insert_user_rejects_duplicate_user_id(temp_db):
    ...
    with pytest.raises(sqlite3.IntegrityError):
        insert_user(User(user_id="ana", role="admin", token_hash="h-2"))

def test_insert_user_rejects_duplicate_token_hash(temp_db):
    ...
    with pytest.raises(sqlite3.IntegrityError):
        insert_user(User(user_id="bob", role="user", token_hash="shared-hash"))
```

These are PRD-005-era tests, **not** STORY-002 characterization tests (which were written to assert
by return value and CLI surface precisely so they would survive this change untouched). AC2 —
"no driver exception reaches a caller" — makes updating these two `pytest.raises` targets
mandatory, not optional. They are the *only* two in the suite, verified by
`grep -rn "sqlite3\." tests/`. AC7 is unaffected: it protects the characterization tests, and
these are not among them.

Editing `tests/test_db.py` costs no new red: `tests/test_untouched_app.py:88-95` pins it
byte-for-byte and **that parametrization is already failing** on this branch (see F5).

### F4 — The constraint that failed is recoverable from the driver message, and only from it

Probed against this environment (Python 3.14.4, SQLite 3.50.4) with the real DDL from
`app/db/models.py:52-60` and `:65-67`:

```
IntegrityError   | UNIQUE constraint failed: users.user_id    | sqlite_errorname=SQLITE_CONSTRAINT_PRIMARYKEY
IntegrityError   | UNIQUE constraint failed: users.token_hash | sqlite_errorname=SQLITE_CONSTRAINT_UNIQUE
OperationalError | no such table: nope                        | sqlite_errorname=SQLITE_ERROR
OperationalError | duplicate column name: role                | sqlite_errorname=SQLITE_ERROR
```

Two consequences. **The message is the only portable signal** — `sqlite_errorname` is a
CPython-3.11+ `sqlite3` attribute a libSQL client will not carry, and both `no such table` and
`duplicate column name` collapse to the same `SQLITE_ERROR` name anyway, so it cannot separate
them. Translation parses the message. **And the missing-relation test must be narrow**:
`duplicate column name` is also an `OperationalError`, raised by `_add_missing_columns` if the
`PRAGMA table_info` guard is ever bypassed (`tests/test_db.py:258-260` documents it), and it must
map to a general storage failure, never to "relation missing".

### F5 — The baseline is not green: 7 failures, none of them this story's

`python -m pytest tests -q` on `a8f75c5` with a clean tree:

```
FAILED tests/test_chat_state.py::test_chat_state_holds_no_token_or_role_var
FAILED tests/test_untouched_app.py::test_no_file_under_app_changed_since_prd_006_began
FAILED tests/test_untouched_app.py::test_the_chat_modules_are_unchanged_since_prd_006_began
FAILED tests/test_untouched_app.py::test_the_pinned_suites_are_byte_unmodified[tests/test_audit_router.py]
FAILED tests/test_untouched_app.py::test_the_pinned_suites_are_byte_unmodified[tests/test_stats_router.py]
FAILED tests/test_untouched_app.py::test_the_pinned_suites_are_byte_unmodified[tests/test_db.py]
FAILED tests/test_untouched_app.py::test_the_pinned_suites_are_byte_unmodified[tests/test_chat_state.py]
7 failed, 1033 passed, 1 warning in 17.52s
```

The same set STORY-003 recorded (one environmental Reflex-annotation failure, six from PRD-006's
containment guard measuring `git diff` against pinned baseline `d3e6279`). "Green" for this story
means **exactly these seven and no others**, with the pass count unchanged at 1033.
`test_no_file_under_app_changed_since_prd_006_began` is already failing, so this story's edits
under `app/` add no new failure.

---

## Patterns to Follow

### Naming + a data-carrying exception

```python
# SOURCE: app/services/authz.py:52-58
class PermissionDenied(Exception):
    """Raised by authorize() on any denial. Carries the permission name so
    callers can report and audit it without re-deriving it."""

    def __init__(self, permission: str) -> None:
        self.permission = permission
        super().__init__(f"Permission denied: {permission}")
```

`app/db/errors.py`'s integrity error mirrors this shape exactly: attributes set before
`super().__init__`, and a docstring saying who catches it and why the attribute exists.

### The plain module-owned error, where no data is carried

```python
# SOURCE: app/services/duplicate_checker.py:12-13
class DuplicateCheckError(Exception):
    pass
```

Also `app/services/openrouter_client.py:13`, `app/services/pii_redactor.py:13`. The codebase's
convention is that a module owns its error type and callers import it from that module — never a
central `exceptions.py`, never a re-export through `__init__.py`. See Design Note 4.

### The connection block being replaced (21 occurrences)

```python
# SOURCE: app/db/database.py:120-126
def get_audit_log(audit_id: int) -> Optional[AuditLog]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM audit_logs WHERE id = ?", (audit_id,)
        ).fetchone()
        if row is None:
            return None
        return _row_to_audit_log(row)
```

`with conn:` on a `sqlite3.Connection` commits on success and rolls back on exception; it does
**not** close. `_session()` must preserve that exactly — see Design Note 2.

### The narrow catch being translated

```python
# SOURCE: app/db/database.py:274-292
def find_user_by_token_hash(token_hash: str) -> Optional[User]:
    """...
    A `users` table that hasn't been created yet (init_db() never ran against
    this connection) is folded into the same "no match" outcome rather than
    raised -- callers resolving a credential need a closed door, not a 500."""
    with get_connection() as conn:
        try:
            row = conn.execute(...).fetchone()
        except sqlite3.OperationalError:
            return None
```

### Tests

```python
# SOURCE: tests/test_db.py:1025-1030
def test_insert_user_rejects_duplicate_user_id(temp_db):
    insert_user(User(user_id="ana", role="user", token_hash="h-1"))

    with pytest.raises(sqlite3.IntegrityError):
        insert_user(User(user_id="ana", role="admin", token_hash="h-2"))
```

Fixtures come from `tests/conftest.py` (STORY-003): `temp_db` for a migrated database,
`uninitialized_db` for one where no table exists. No test opens its own connection except through
`db_connect`.

---

## Design

### The three types (`app/db/errors.py`)

```
StorageError(Exception)              # a storage operation failed   ≙ sqlite3.Error
├── MissingRelationError             # a named table does not exist ≙ "no such table: ..."
│   .relation: str
└── IntegrityError                   # a constraint was violated    ≙ sqlite3.IntegrityError
    .constraint: str | None          #   e.g. "users.token_hash"
```

Three types, three catchers, no orphans — the story's "every exception type that exists must have a
caller that catches it specifically" holds:

| Type | Caught specifically by | Behavior preserved |
|---|---|---|
| `StorageError` | `app/services/duplicate_checker.py:32` | storage failure → `DuplicateCheckError` → 500 |
| `MissingRelationError` | `app/db/database.py:289` | missing `users` table → `None` → **401, not 500** |
| `IntegrityError` | `scripts/manage_users.py:37` | duplicate on create → exit 1, message on stderr |

The subclassing is not decoration: it is what keeps `duplicate_checker` catching a missing table,
exactly as `except sqlite3.Error` does today (F2).

### Translation lives in `database.py`, never in `errors.py`

```python
# app/db/database.py — the only code in the repository that names a driver exception class
_MISSING_RELATION = re.compile(r"no such table: (\w+)")
_CONSTRAINT = re.compile(r"constraint failed: ([\w.]+)")


@contextmanager
def _translated() -> Iterator[None]:
    """Driver exceptions in, app.db.errors exceptions out. The single seam
    where sqlite3's hierarchy is known; STORY-006 rewrites this body and
    nothing else has to change."""
    try:
        yield
    except sqlite3.IntegrityError as exc:
        raise IntegrityError(_constraint_of(exc), str(exc)) from exc
    except sqlite3.OperationalError as exc:
        match = _MISSING_RELATION.search(str(exc))
        if match is not None:
            raise MissingRelationError(match.group(1), str(exc)) from exc
        raise StorageError(str(exc)) from exc
    except sqlite3.Error as exc:
        raise StorageError(str(exc)) from exc


@contextmanager
def _session() -> Iterator[sqlite3.Connection]:
    """`with get_connection() as conn:` plus translation. Same commit-on-success,
    rollback-on-exception, do-not-close semantics as the block it replaces."""
    with _translated():
        conn = get_connection()
        with conn:
            yield conn
```

`errors.py` imports nothing from `app/` and no driver — `import app.db.errors` must not pull in
`sqlite3`, which is what makes it survive [[STORY-006]] unchanged.

### `find_user_by_token_hash` — nested, narrow

```python
    with _session() as conn:
        try:
            with _translated():
                row = conn.execute(...).fetchone()
        except MissingRelationError:
            return None
```

The inner `_translated()` converts before the outer one sees anything; `MissingRelationError` is
not a `sqlite3` type, so it would pass through `_session` untouched — and it is caught one line
later regardless. A storage failure that is *not* a missing table becomes `StorageError` and
escapes, which is the point (Design Note 3).

### Design Note 1 — why a context manager and not a decorator on 22 functions

A `@_translates` decorator would need 22 applications and would still leave the
`find_user_by_token_hash` arm untranslated, because that catch sits *inside* the connection block
around one specific `execute`. `_session()` is a single mechanical substitution at a site that
already exists in every function, it puts translation and connection lifetime in one object, and it
leaves `get_connection()`'s name, signature, and return type untouched — which PRD Section 11
requires ("the 22 public functions keep their names, signatures, and return types") and which the
`monkeypatch.setattr(database, "get_connection", traced)` test at `tests/test_db.py:103-110`
depends on. `_session` resolves `get_connection` through the module global, so that patch keeps
working.

### Design Note 2 — `_session` must not close the connection

`with sqlite3.Connection` commits or rolls back and leaves the connection open; today nothing
closes it and the object is collected. Adding `conn.close()` would be an improvement in isolation
and a behavior change here — `tests/test_db.py:99-115` traces statements on a connection handed
back by a patched `get_connection`, and the whole lifecycle is rewritten by [[STORY-006]]'s shared
client anyway. Keep the semantics identical; leave the improvement to the story that owns it.

### Design Note 3 — the 401 catch narrows, deliberately (user-confirmed)

Today `except sqlite3.OperationalError` at `app/db/database.py:289` swallows *any* operational
failure into `None` → 401: a locked database, an unreadable file, a disk error. After this change
only `no such table` does; everything else raises `StorageError` and surfaces as a 500.

This is what the story's Technical Notes explicitly direct — *"Do not broaden that catch while
translating it. Catching more than the missing-relation case here would turn a real storage outage
into a silent 401."* It is nonetheless a real behavior change, invisible to the suite (no test
covers a locked database), and it must be named in the story report rather than discovered later.
The STORY-002 characterization test covers the missing-table case only and stays green.

### Design Note 4 — `app/db/__init__.py` stays empty

The story allows "possibly `app/db/__init__.py` for the export". It should not be used. The file is
empty today, and every consumer already imports from the concrete module —
`from app.db.database import ...`, `from app.db.models import User`. A re-export would create two
spellings for one type and diverge from `app/services/`'s convention, where each module owns and
exports its own error. Callers import `from app.db.errors import StorageError`.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/db/errors.py` | CREATE | The three module-owned exception types; imports no driver |
| `app/db/database.py` | UPDATE | `_translated()` + `_session()`; 21 call-site swaps; narrow 401 arm; `insert_user` docstring |
| `app/services/duplicate_checker.py` | UPDATE | Drop `import sqlite3`; catch `StorageError` |
| `scripts/manage_users.py` | UPDATE | Drop `import sqlite3`; catch `IntegrityError` |
| `tests/test_db.py` | UPDATE | Two `pytest.raises` targets → module-owned type (F3) |

Nothing else. `app/db/__init__.py`, `app/db/models.py`, `tests/conftest.py`, and every
characterization test are untouched.

### Dependency order

Task 1 (types) → Task 2 (seam) → Task 3 (call sites) → Task 4 (401 arm) → Tasks 5–6 (the two
external catch sites, which must land together with Task 3 or the suite stays red in between) →
Task 7 (docstring) → Task 8 (tests) → Tasks 9–10 (verify, commit).

### Risks

| Risk | Mitigation |
|---|---|
| A driver exception escapes through a path `_session` does not wrap (e.g. a `conn.execute` in a `finally`, or a lazily-evaluated cursor read outside the block) | Task 9's `grep -rn "sqlite3\." app/ chat_ui/ scripts/` plus the full suite. Every `.fetchone()`/`.fetchall()` in `database.py` is already inside its `with` block — verified; `top_pii_entities` is the only function doing post-processing after the block, and it operates on already-fetched rows. |
| The suite is red between Task 3 and Task 5 (`duplicate_checker` still catching `sqlite3.Error`) | Expected and stated in Task 3's validation. Do not "fix" it by widening anything in `database.py`; Task 5 closes it. |
| Message-parsing translation is brittle if libSQL words its errors differently | Out of scope here — this story runs on `sqlite3` and F4 records the exact strings. [[STORY-006]] re-verifies `_translated()` against the real client; that is why the parsing lives in one function. |
| The narrowed 401 arm changes production behavior with no test covering it | Design Note 3; recorded in the story report as an intentional, story-directed change. |

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 0: Record the baseline

- **File**: none (scratchpad only)
- **Action**: VERIFY
- **Implement**: capture the pre-change state the whole story is measured against.
  ```bash
  SCRATCH="C:/Users/tobip/AppData/Local/Temp/claude/c--Users-tobip-Documents-prog-harness-ai/437e0591-380a-4936-bcf2-7c0baf822274/scratchpad"
  git status --porcelain          # must be empty before starting
  python -m pytest tests -q > "$SCRATCH/s004-baseline.txt" 2>&1
  grep -rn "import sqlite3" app/ chat_ui/ scripts/ > "$SCRATCH/s004-imports.txt"
  ```
- **Validate**: `s004-baseline.txt` ends with `7 failed, 1033 passed` and lists exactly the seven
  failures in F5; `s004-imports.txt` has 3 lines (`app/db/database.py:1`,
  `app/services/duplicate_checker.py:2`, `scripts/manage_users.py:2`).

### Task 1: Create the exception surface

- **File**: `app/db/errors.py`
- **Action**: CREATE
- **Implement**: the three types from the Design section, and nothing else.
  - Module docstring: this is the surface `app/db/` raises; no consumer imports a driver
    (PRD Section 7.2); translation happens at the `database.py` boundary, not here; and this module
    deliberately imports no driver, so it survives the driver swap unchanged.
  - `StorageError(Exception)` — a storage operation failed. Docstring names
    `app/services/duplicate_checker.py` as its catcher and states that it is the base of the other
    two on purpose, mirroring `sqlite3.Error`, so a catcher of the general case still catches the
    specific ones (F2).
  - `MissingRelationError(StorageError)` — `__init__(self, relation: str, message: str)`, sets
    `self.relation`. Docstring names `find_user_by_token_hash` as its catcher and the 401-not-500
    contract (PRD-005 §9).
  - `IntegrityError(StorageError)` — `__init__(self, constraint: Optional[str], message: str)`,
    sets `self.constraint` (e.g. `"users.user_id"`, `"users.token_hash"`, `None` when the driver
    message is unparseable). Docstring names `scripts/manage_users.py` as its catcher, states that
    `.constraint` exists so a caller *can* tell a duplicate `user_id` from a duplicate `token_hash`
    (AC1), and records that the CLI does not branch on it yet (F1) with a pointer to
    `tests/test_manage_users_cli.py:948`. Note that the name matches the driver's *concept*, not
    its class — nothing here inherits from `sqlite3`.
  - Every `__init__` sets its attribute then calls `super().__init__(message)`.
- **Mirror**: `app/services/authz.py:52-58` (data-carrying), `app/services/duplicate_checker.py:12-13` (plain)
- **Validate**:
  ```bash
  python -c "import app.db.errors as e; print(e.IntegrityError.__mro__)"
  python -c "import ast; m=ast.parse(open('app/db/errors.py').read()); print([n.__class__.__name__ for n in ast.walk(m) if isinstance(n,(ast.Import,ast.ImportFrom))])"
  ```
  The MRO shows `IntegrityError -> StorageError -> Exception`; the import list contains nothing but
  `typing` (if `Optional` is used).

### Task 2: Add the translation seam to `database.py`

- **File**: `app/db/database.py`
- **Action**: UPDATE
- **Implement**: add `import re`, `from contextlib import contextmanager`,
  `from typing import Iterator` (extending the existing `from typing import Optional`), and
  `from app.db.errors import IntegrityError, MissingRelationError, StorageError`. Add, immediately
  below `get_connection()`:
  - `_MISSING_RELATION` and `_CONSTRAINT` as in the Design section, each with a one-line comment
    citing the probed driver messages in F4 and noting that libSQL is SQLite-derived and emits the
    same text.
  - `_constraint_of(exc) -> Optional[str]` — first match group of `_CONSTRAINT`, else `None`.
  - `_translated()` and `_session()` exactly as in the Design section, with the docstrings shown
    there. The `except` order matters: `IntegrityError` and `OperationalError` before the
    `sqlite3.Error` catch-all.
- **Mirror**: the placement convention of the existing private helpers `_db_path` and
  `_add_missing_columns` (`app/db/database.py:19-48`) — a private helper sits next to what it serves.
- **Validate**: `python -m pytest tests/test_db.py -q` — unchanged from baseline. Nothing calls the
  new helpers yet, so this only proves the module still imports cleanly.

### Task 3: Route the 21 connection blocks through `_session()`

- **File**: `app/db/database.py`
- **Action**: UPDATE
- **Implement**: replace every `with get_connection() as conn:` with `with _session() as conn:`.
  There are exactly 21, in `init_db`, `insert_audit_log`, `find_duplicate_timestamp`,
  `get_audit_log`, `count_audit_logs`, `list_audit_logs`, `count_blocked_duplicates`,
  `count_blocked_suspicious`, `count_unique_users`, `count_successful_queries`, `top_models`,
  `top_users`, `count_pii_detected_queries`, `top_pii_entities`, `get_user`,
  `find_user_by_token_hash`, `list_users`, `count_active_users`, `insert_user`, `deactivate_user`,
  `set_user_token_hash`. Do not touch `get_connection()` itself — it keeps its name, signature and
  `sqlite3.Connection` return type (Design Note 1), and stays the raw seam `tests/conftest.py` and
  `tests/test_db.py` use.
- **Validate**:
  ```bash
  grep -c "with _session() as conn:" app/db/database.py        # 21
  grep -c "with get_connection() as conn:" app/db/database.py  # 0
  python -m pytest tests/test_db.py -q
  ```
  `test_db.py` matches its baseline except the two F3 tests, which now fail on the exception type
  (Task 8 fixes them). `tests/test_duplicate_checker.py` and `tests/test_query_router.py` are
  **expected to be red at this point** — `duplicate_checker` still catches `sqlite3.Error`, which
  no longer reaches it. That is the leak this story exists to close; Task 5 closes it. Do not widen
  anything in `database.py` to make them pass early.

### Task 4: Translate the 401 arm

- **File**: `app/db/database.py` (`find_user_by_token_hash`, ~line 274)
- **Action**: UPDATE
- **Implement**: replace `except sqlite3.OperationalError: return None` with the nested
  `with _translated():` / `except MissingRelationError: return None` form from the Design section.
  Extend the existing docstring — keep its wording verbatim — with one sentence: the arm now catches
  `MissingRelationError` only, so a storage failure that is not a missing table surfaces as a 500
  rather than a silent 401 (Design Note 3).
- **Mirror**: `app/db/database.py:274-292` — the docstring's existing two-paragraph shape
- **Validate**: `python -m pytest tests/test_db.py -k "find_user_by_token_hash" -q` — all pass,
  including the STORY-002 characterization test
  `test_find_user_by_token_hash_returns_none_when_users_table_does_not_exist`, with
  `tests/test_db.py` still unmodified at this point.

### Task 5: Rewrite `duplicate_checker`

- **File**: `app/services/duplicate_checker.py`
- **Action**: UPDATE
- **Implement**: delete `import sqlite3` (line 2); add `from app.db.errors import StorageError`
  beside the existing `from app.db.database import find_duplicate_timestamp` (line 7); change
  `except sqlite3.Error as exc:` (line 32) to `except StorageError as exc:`. The raised
  `DuplicateCheckError(f"Duplicate lookup failed: {exc}")` message is asserted verbatim by
  `tests/test_query_router.py:215` — do not reword it.
- **Mirror**: `app/services/duplicate_checker.py:28-33`
- **Validate**: `python -m pytest tests/test_duplicate_checker.py tests/test_query_router.py -q` —
  all pass, including both F2 tests; Task 3's expected red is now closed.

### Task 6: Rewrite the CLI catch

- **File**: `scripts/manage_users.py`
- **Action**: UPDATE
- **Implement**: delete `import sqlite3` (line 2); add `from app.db.errors import IntegrityError`
  beside the existing `from app.db.models import User` (line 21); change
  `except sqlite3.IntegrityError:` (line 37) to `except IntegrityError:`. **The message and exit
  code do not change** (F1): the `print(...)` and `return 1` stay byte-identical. Add a two-line
  comment above the `except` recording that `IntegrityError.constraint` distinguishes
  `users.user_id` from `users.token_hash`, that the CLI deliberately does not branch on it yet, and
  pointing at `tests/test_manage_users_cli.py:948` for why.
- **Mirror**: `scripts/manage_users.py:33-41`
- **Validate**: `python -m pytest tests/test_manage_users_cli.py -q` — all pass, specifically
  `test_create_user_duplicate_user_id_exits_nonzero` and
  `test_create_user_duplicate_token_hash_is_not_distinguished_from_duplicate_user_id`, with
  `git diff --stat tests/test_manage_users_cli.py` empty.

### Task 7: Update `insert_user`'s docstring

- **File**: `app/db/database.py` (`insert_user`, ~line 313)
- **Action**: UPDATE
- **Implement**: rewrite the first clause to name the new type, preserving *"deliberately not caught
  here"* and its reason:
  > `Raises app.db.errors.IntegrityError on a duplicate user_id or token_hash -- deliberately not
  > caught here; the translation happens at this module's boundary but the handling stays with the
  > caller, which needs to tell those two cases apart. IntegrityError.constraint carries which
  > constraint failed.`
- **Mirror**: `app/db/database.py:313-316` (the docstring being replaced)
- **Validate**: `grep -n "sqlite3.IntegrityError" app/db/database.py` returns nothing.

### Task 8: Update the two driver-typed assertions in `test_db.py`

- **File**: `tests/test_db.py`
- **Action**: UPDATE
- **Implement**: in `test_insert_user_rejects_duplicate_user_id` (~line 1025) and
  `test_insert_user_rejects_duplicate_token_hash` (~line 1032), change
  `pytest.raises(sqlite3.IntegrityError)` to `pytest.raises(IntegrityError)`, imported as
  `from app.db.errors import IntegrityError` beside the existing `from app.db.database import (...)`
  block. Strengthen each with one assertion on the carried constraint — that is the AC1 evidence,
  and without it nothing in the suite proves `.constraint` is populated:
  ```python
  with pytest.raises(IntegrityError) as exc_info:
      insert_user(User(user_id="ana", role="admin", token_hash="h-2"))
  assert exc_info.value.constraint == "users.user_id"
  ```
  and `"users.token_hash"` in the other. Keep `import sqlite3` at `tests/test_db.py:7` — it is still
  used by `test_init_db_issues_no_alter_when_schema_is_current`'s annotation at line 105. Change
  nothing else in this file.
- **Mirror**: `tests/test_db.py:1025-1038`
- **Validate**: `python -m pytest tests/test_db.py -q` — matches the Task 0 baseline result for this
  file; `git diff -U0 tests/test_db.py` shows only these two tests plus the import.

### Task 9: Prove the decoupling

- **File**: none
- **Action**: VERIFY
- **Implement**:
  ```bash
  grep -rn "import sqlite3" app/ chat_ui/ scripts/            # AC6
  grep -rn "sqlite3\." app/ chat_ui/ scripts/ --include=*.py
  python -m pytest tests -q
  ```
- **Validate**: the first grep returns exactly one line, `app/db/database.py:1`. The second returns
  only lines inside `app/db/database.py`. The suite ends at **`7 failed, 1033 passed`** with a
  failure list byte-identical to `s004-baseline.txt` — no new failure, no lost pass.

### Task 10: Commit

- **File**: none
- **Action**: VERIFY
- **Implement**: stage only the five files in *Files to Change* and commit on
  `epic/PRD-007-turso-migration` (no per-story branch), message
  `refactor(db): STORY-004 module-owned error surface, decoupling the three catch sites from sqlite3`.
- **Validate**: `git diff --cached --name-only` lists exactly `app/db/errors.py`,
  `app/db/database.py`, `app/services/duplicate_checker.py`, `scripts/manage_users.py`,
  `tests/test_db.py` — and nothing else.

---

## End-to-End Tests

- [ ] **The 401 survives.** With `DATABASE_URL` pointed at an empty temp database `init_db()` never
      ran against,
      `python -c "from app.db.database import find_user_by_token_hash as f; print(f('x'))"`
      prints `None` — not a traceback.
- [ ] **The CLI still reports a duplicate.** Against a temp database,
      `python scripts/manage_users.py create-user --user-id ana` twice — the second exits `1` and
      prints `Error: a user with user_id 'ana' already exists.` on **stderr**, with no token on
      stdout.
- [ ] **A dropped table still degrades to a 500, not a crash.** Covered by
      `tests/test_query_router.py::test_duplicate_check_storage_failure_returns_500`; confirm it
      passes unmodified.
- [ ] **`errors.py` is driver-free.** `python -c "import app.db.errors"` succeeds and the module's
      AST contains no `sqlite3` import.
- [ ] **The app still boots.** `python -c "from app.main import app; print(app.title)"` — no import
      error from the new module.

## Validation

```bash
python -m pytest tests -q                                 # 7 failed, 1033 passed — the same seven
grep -rn "import sqlite3" app/ chat_ui/ scripts/          # exactly one hit, inside app/db/
git diff --stat tests/                                    # only tests/test_db.py
python -c "import app.db.errors"                          # imports with no driver
python -c "from app.main import app"                      # app still boots
```

---

## Acceptance Criteria

(Copied from story `STORY-004`)

- [ ] AC1 — `app/db/errors.py` declares an exception surface covering the three conditions the
      codebase distinguishes today (integrity violation, missing relation, general storage failure),
      and the integrity error carries enough information to tell a duplicate `user_id` from a
      duplicate `token_hash` (`IntegrityError.constraint`, asserted in Task 8).
- [ ] AC2 — every driver exception escaping a query in `app/db/database.py` is translated at the
      module boundary; no driver exception reaches a caller.
- [ ] AC3 — `app/services/duplicate_checker.py` no longer imports `sqlite3` and catches
      `StorageError`; a storage failure still produces `DuplicateCheckError` with the same message.
- [ ] AC4 — `scripts/manage_users.py` no longer imports `sqlite3` and catches the module-owned
      integrity error. **Partially met by design:** the two cases are *distinguishable through the
      exception* (`.constraint`), but the CLI still prints one message for both, because AC7 and the
      STORY-002 characterization test at `tests/test_manage_users_cli.py:948` require exactly that
      output. See Finding F1; confirmed with the user. The story report must record AC4 as not fully
      met and name the follow-up.
- [ ] AC5 — `find_user_by_token_hash(...)` against a database with no `users` table still returns
      `None` — 401, not 500 — now via `MissingRelationError`.
- [ ] AC6 — `grep -rn "import sqlite3" app/ chat_ui/ scripts/` hits only inside `app/db/`.
- [ ] AC7 — all STORY-002 characterization tests pass unmodified
      (`test_find_user_by_token_hash_returns_none_when_users_table_does_not_exist`,
      `test_create_user_duplicate_user_id_exits_nonzero`,
      `test_create_user_duplicate_token_hash_is_not_distinguished_from_duplicate_user_id`,
      `test_duplicate_check_storage_failure_returns_500`), verified by an empty `git diff` on
      `tests/test_query_router.py` and `tests/test_manage_users_cli.py`.
- [ ] All tasks completed
- [ ] `python -m pytest tests -q` ends at `7 failed, 1033 passed` with the same seven failures
- [ ] Backend imports without error (`python -c "from app.main import app"`)
- [ ] Follows existing patterns (`app/services/authz.py:52-58` for the data-carrying exception;
      per-module error ownership rather than a re-export through `app/db/__init__.py`)
