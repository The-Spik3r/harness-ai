---
story: STORY-006
prd: PRD-008
slug: chat-sessions-service
title: "app/services/chat_sessions.py: the ownership rule and the CHAT_HISTORY_ENABLED short-circuit in one place"
type: NEW_CAPABILITY
complexity: MEDIUM
epic_branch: epic/PRD-008-chat-sessions
created: 2026-09-03
---

# Plan: app/services/chat_sessions.py — the ownership rule and the CHAT_HISTORY_ENABLED short-circuit in one place

## Summary

Add `app/services/chat_sessions.py`: eight functions (`create`, `list_for`, `get`, `rename`, `touch`, `delete`, `append_message`, `messages_for`), each taking an `Identity` first, each converting that `Identity` into the `user_id` the nine `database.py` functions from STORY-004/005 already require, and each returning early — before any statement is issued — when `settings.CHAT_HISTORY_ENABLED` is false. `StorageError` from the store is wrapped in a module-owned `ChatSessionError`, the way `duplicate_checker.py` wraps it in `DuplicateCheckError`. The `CHAT_SESSION_LIMIT` cap is applied here and nowhere else, so no caller supplies a limit and no caller branches on the flag. Tests extend the existing `tests/test_chat_sessions.py` with a labelled STORY-006 section, following the precedent that file's own docstring records for STORY-005.

## User Story

As a maintainer
I want one module that owns both "whose row is this" and "is history on at all"
So that no caller has to remember either — the way `app/services/authz.py` owns the permission matrix so no caller writes a role check.

## Story Reference

- Story file: `.agents/stories/PRD-008-chat-sessions/STORY-006-chat-sessions-service.md`
- PRD: `.agents/PRDs/PRD-008-chat-sessions/PRD.md` — Section 4, Section 6, Section 9, Section 12 Phase 1, Risks 1 & 2

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | MEDIUM |
| Systems Affected | `app/services/` (new module), `tests/` (extended suite) |
| Story | STORY-006 |
| PRD | PRD-008 |
| Epic Branch | `epic/PRD-008-chat-sessions` (commit directly on this branch) |

**Dependencies verified**: STORY-001 (`8830745`), STORY-004 (`fdbc538`), STORY-005 (`1851c25`) are all `status: done`. Nothing blocks this story.

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | `.agents/skills/` contains only `frontend-design`, whose `description` scopes it to "distinctive, intentional visual design when building new UI or reshaping an existing one". This story produces no rendered output and touches no file under `chat_ui/`. | None |

The story's own Technical Notes reach the same conclusion; this plan re-ran the scan rather than inheriting it. `chat_ui/AGENTS.md`'s **reflex-docs** rule is likewise not engaged — no Reflex API is used.

---

## Decision: how `create` gets its title

**Resolved with the user before this plan was written.** It is the one place where the story's own constraints do not compose, so the resolution is recorded here rather than discovered during implementation.

AC 6 requires `create(identity, first_prompt)` to title the session from the prompt with the derivation **delegated** to STORY-012. STORY-012 (PRD Section 6's file map, and its own AC 2) puts `derive_title(prompt)` in `chat_ui/chat_ui/formatting.py`. But this story's Technical Notes forbid the service importing anything from `chat_ui/`, and the repository's import direction is strictly one-way — `chat_ui/chat_ui/state.py:4-14` and `admin_state.py:33-34` import from `app`, and `grep -rn chat_ui app/` finds no import in the other direction, only prose in comments. STORY-012 is also `status: todo` and is **not** a declared dependency of this story, so `derive_title` will not exist when this is implemented.

**Chosen: inject the deriver.**

```python
def create(
    identity: Identity,
    first_prompt: str,
    derive_title: Callable[[str], str],
) -> Optional[str]:
```

The service calls the deriver and never implements it, so AC 6's "delegated, not reimplemented" holds literally; `first_prompt` stays in the signature as AC 6 spells it; `app/` gains no dependency on `chat_ui/`; and STORY-006 ships with no dependency on STORY-012 at all. The cost is one argument at STORY-013's call site — `chat_sessions.create(identity, prompt, formatting.derive_title)` — which is a fact about the caller's own module, not a rule the caller has to remember about persistence.

The three alternatives and why they lost: a ready `title: str` parameter drops `first_prompt` from the signature AC 6 names and moves the remembering back to the caller; moving `derive_title` into `app/` takes work STORY-012 owns and contradicts PRD Section 6's file map; a function-local `from chat_ui.chat_ui.formatting import ...` inverts the project's import direction and couples the FastAPI app to the Reflex package.

**`derive_title` is required, not defaulted.** A default would have to be *some* derivation living in this module, which is the reimplementation AC 6 forbids.

---

## Patterns to Follow

### Error wrapping — the shape to copy exactly

```python
# SOURCE: app/services/duplicate_checker.py:12-13, 30-33
class DuplicateCheckError(Exception):
    pass

    try:
        match = find_duplicate_timestamp(prompt_hash, cutoff)
    except StorageError as exc:
        raise DuplicateCheckError(f"Duplicate lookup failed: {exc}") from exc
```

### The flag short-circuit — read at call time, return before any work

```python
# SOURCE: app/services/pii_redactor.py:49-51
def redact(text: str) -> Tuple[str, List[str]]:
    if not settings.PII_REDACTION_ENABLED or not text:
        return text, []
```

`settings.PII_REDACTION_ENABLED` is read inside the function on every call, never captured at import. `app/services/authz.py:67-72`'s `load()` is the deliberate counter-example, and its docstring says why: "Called once at startup... never call this per request."

### Indistinguishable failure — the precedent this story cites

```python
# SOURCE: app/services/identity.py:46-51
def resolve(token: Optional[str]) -> Optional[Identity]:
    """Verifies a credential and returns the Identity it belongs to, or
    None. None covers every failure case alike -- unknown, malformed,
    empty, or deactivated -- so the caller cannot distinguish them (PRD
    Section 9; STORY-002 Design Note 5 makes the same choice one layer
    down)."""
```

`app/db/database.py:1264-1280` (`get_chat_session`) already holds the same line one layer down: "A session that exists but belongs to someone else returns `None`, exactly as a session that does not exist does."

### Identity → user_id, and nothing else read off the Identity

```python
# SOURCE: app/services/authz.py:126-136
def authorize(identity: Identity, permission: str) -> None:
    if not settings.RBAC_ENABLED:
        return
    role_permissions = ROLE_PERMISSIONS.get(identity.role)
```

`authz` reads `identity.role`; this service reads `identity.user_id` and never `identity.role` — Section 9's division: "RBAC answers what a role may do, ownership answers whose row this is."

### Tests — structural assertions via `inspect` / `ast`, in the file that already has them

```python
# SOURCE: tests/test_chat_sessions.py:153-158
def test_the_six_functions_are_declared():
    """AC 1. No database needed: this is a statement about the module."""
    for name in THE_SIX:
        assert hasattr(database, name), name
        assert callable(getattr(database, name)), name
```

```python
# SOURCE: tests/test_duplicate_checker.py:99-101
def test_malformed_db_raises_duplicate_check_error(uninitialized_db):
    with pytest.raises(DuplicateCheckError):
        check_duplicate("anything")
```

The `uninitialized_db` fixture (`tests/conftest.py:181-189`) is a database `init_db()` never ran against — the ready-made way to produce a real `StorageError` without stubbing.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/chat_sessions.py` | CREATE | The eight functions, `ChatSessionError`, the flag short-circuit, the `CHAT_SESSION_LIMIT` cap. |
| `tests/test_chat_sessions.py` | UPDATE | Add a labelled STORY-006 section: flag-off, foreign-identity, error-wrapping, delegation, and the no-caller-branches guard. |

Nothing else. In particular `app/services/authz.py` is **not** touched — PRD Section 9: "`query:submit` still gates sending; owning a session grants nothing beyond reading and deleting it." No `chat:read:own` permission is added.

---

## Design

### The surface

Eight public functions, `Identity` first on every one (which is also STORY-007's AC 3):

| Function | Signature | Flag-off return | Foreign / unknown `session_id` |
|---|---|---|---|
| `create` | `(identity, first_prompt, derive_title) -> Optional[str]` | `None` | n/a |
| `list_for` | `(identity) -> list[ChatSession]` | `[]` | n/a |
| `get` | `(identity, session_id) -> Optional[ChatSession]` | `None` | `None` |
| `rename` | `(identity, session_id, title) -> bool` | `False` | `False` |
| `touch` | `(identity, session_id) -> bool` | `False` | `False` |
| `delete` | `(identity, session_id) -> bool` | `False` | `False` |
| `append_message` | `(identity, session_id, message) -> Optional[int]` | `None` | raises `ChatSessionError` |
| `messages_for` | `(identity, session_id) -> list[StoredMessage]` | `[]` | `[]` |

`count_chat_sessions` is deliberately **not** exposed. The story names exactly eight functions; the rail's "50 of 200" count is STORY-018's problem and can add a ninth then, with its own reason.

### Two judgment calls worth stating

**1. `append_message` raises for a foreign session, and that is AC 7 satisfied rather than violated.** `database.append_chat_message` raises `StorageError("chat session not available for this owner")` for a foreign *and* an unknown session — one message, deliberately: `app/db/database.py:1460-1470` records that "AC 6 requires a *visible* failure here rather than a `None`, since the return type is the new row id and a silent no-op would read as a successful write." AC 7's requirement is that the caller cannot **distinguish** the two cases, and wrapping both in one `ChatSessionError` carrying one message keeps them indistinguishable. Converting them to `None` instead would collide with the flag-off `None` and hand STORY-014's degraded arm a silent-success signal for a write that never landed. A test asserts the two cases raise with byte-identical messages.

**2. The module imports `from app.db import database` and calls `database.create_chat_session(...)` qualified**, rather than `duplicate_checker`'s `from app.db.database import find_duplicate_timestamp`. AC 4 requires the flag-off proof to be made "by patching the database module and observing that nothing on it was called" — a qualified call lets one sentinel object replace the whole module and catch every one of the nine functions, where name-imports would need nine separate patches and a tenth function added next month would slip past. `tests/test_chat_sessions.py:29` already imports the module this way for the same reason.

### Dependency order

`ChatSessionError` → the eight functions (independent of each other) → the tests. No file depends on another being written first.

### Risks

| Risk | Mitigation |
|---|---|
| A future caller writes `if settings.CHAT_HISTORY_ENABLED` in `state.py` and the "no caller branches" property rots silently. | Task 4 adds a structural guard that scans `app/` and `chat_ui/` for the identifier and fails on any occurrence outside `app/config.py` and this module. A property nobody tests is a property that lasted one story. |
| The flag-off assertion passes for the wrong reason — an empty database also returns `[]`. | Every flag-off test patches `chat_sessions.database` with an object that raises on **any** attribute access, so a statement issued is a test failure rather than an empty result. This is AC 4's wording made literal. |
| `create` returning `None` when the flag is off is mistaken by STORY-013 for a failure. | Docstring states it plainly and the tests name it; STORY-013's lazy-create arm is where it is consumed, and the return type `Optional[str]` forces the caller to face it. |
| The libSQL dev server degrades under repeated suite runs and produces mass fixture errors. | Recorded already: restart the container rather than bisecting the code. `docker restart harness-libsql-dev`. |
| STORY-012 later lands `derive_title` with a different signature than `Callable[[str], str]`. | The parameter is typed and exercised by a test double, so a mismatch is a `TypeError` at STORY-013's call site, not a wrong title. STORY-012's AC 2 already fixes the shape as `derive_title(prompt) -> str`. |

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Create the module with `ChatSessionError` and the flag/ownership scaffolding

- **File**: `app/services/chat_sessions.py`
- **Action**: CREATE
- **Implement**:
  - Module docstring stating the two things this module owns (ownership conversion, the `CHAT_HISTORY_ENABLED` short-circuit), quoting PRD Section 6's "`ChatState` calls the service, never `database.py` directly" and "No caller branches on the flag."
  - `from app.config import settings`, `from app.db import database`, `from app.db.errors import StorageError`, `from app.db.models import ChatSession, StoredMessage`, `from app.services.identity import Identity`. Nothing from `chat_ui/`.
  - `class ChatSessionError(Exception): pass`
  - A private `@contextmanager def _wrapped(operation: str)` that catches `StorageError` and re-raises `ChatSessionError(f"{operation} failed: {exc}") from exc`, so the wrap is written once rather than eight times. Docstring must say it mirrors `duplicate_checker.check_duplicate`'s arm and why one helper replaces eight copies.
- **Mirror**: `app/services/duplicate_checker.py:12-13,30-33` for the exception and the wrap; `app/services/identity.py:19-30` for the docstring register.
- **Validate**: `python -c "import app.services.chat_sessions"` (imports clean, no circular import with `app.db`)

### Task 2: The five session functions — `create`, `list_for`, `get`, `rename`, `touch`, `delete`

- **File**: `app/services/chat_sessions.py`
- **Action**: UPDATE
- **Implement**: each function per the surface table above.
  - Every one opens with the flag guard, returning the table's flag-off value **before** touching `database` — `if not settings.CHAT_HISTORY_ENABLED: return ...`, reading the setting at call time.
  - Every one passes `identity.user_id` and never accepts a `user_id` string; none reads `identity.role`.
  - `create(identity, first_prompt, derive_title)` calls `derive_title(first_prompt)` and hands the result to `database.create_chat_session(identity.user_id, title)`. It derives nothing itself — see the Decision section above.
  - `list_for(identity)` passes `limit=settings.CHAT_SESSION_LIMIT` and takes **no** `limit` parameter, so no caller can supply one (AC 5). Docstring states the cap is a deployment decision, and points at `database.list_chat_sessions`'s docstring, which already says the policy lives here.
  - `get`/`rename`/`touch`/`delete` return the store's `None`/`bool` unchanged — the foreign-session behaviour is already correct one layer down (`app/db/database.py:1264-1280`, `1323-1337`, `1346-1352`, `1362-1384`) and the service must not add a branch that would let the two cases be told apart.
  - All six wrap store calls in `_wrapped(...)`.
  - The break-glass `admin` identity gets **no** special case — PRD Section 9.
- **Mirror**: `app/services/authz.py:126-136` for the `identity`-first shape; `app/services/pii_redactor.py:49-51` for the call-time flag read.
- **Validate**: `python -c "import inspect, app.services.chat_sessions as m; [print(n, inspect.signature(f)) for n, f in vars(m).items() if callable(f) and not n.startswith('_')]"` — every public function shows `identity` first.

### Task 3: The two message functions — `append_message`, `messages_for`

- **File**: `app/services/chat_sessions.py`
- **Action**: UPDATE
- **Implement**:
  - `append_message(identity, session_id, message)` → `database.append_chat_message(message, session_id, identity.user_id)`, returning the new row id. Flag off → `None`, no statement.
  - `messages_for(identity, session_id)` → `database.list_chat_messages(session_id, identity.user_id)`. Flag off → `[]`, no statement. No `limit` parameter — `database.list_chat_messages` takes none by design.
  - `append_message`'s docstring must state judgment call 1 above: the foreign and the unknown session raise the same `ChatSessionError` with the same message, and why that satisfies AC 7 rather than breaking it.
  - Note in the docstring that `message.session_id` is not read by the store — the `session_id` parameter wins in both the column and the `EXISTS` predicate (`app/db/database.py:1451-1459`) — so the service does not need to reconcile the two and deliberately does not try.
- **Mirror**: `app/db/database.py:1438-1533` docstrings for the reasoning to carry forward.
- **Validate**: `python -c "import app.services.chat_sessions"`

### Task 4: Extend `tests/test_chat_sessions.py` with the STORY-006 section

- **File**: `tests/test_chat_sessions.py`
- **Action**: UPDATE
- **Implement**: append a labelled `STORY-006 -- the service` section, and extend the module docstring to record that a third story extended this file (as the docstring already does for STORY-005). Add a `THE_EIGHT` tuple beside `THE_SIX`/`THE_THREE`. Cases:
  - **AC 1** — all eight are declared and callable on the service module.
  - **AC 1/AC 2 + STORY-007 AC 3** — every public function's first parameter is named `identity` and annotated `Identity`; none has a parameter named `user_id`. Via `inspect.signature`, discovered not enumerated.
  - **AC 3 (flag off, writes)** — with `settings.CHAT_HISTORY_ENABLED` patched `False` and `chat_sessions.database` replaced by an object raising `AssertionError` on any attribute access: `create` → `None`, `append_message` → `None`, `touch`/`rename`/`delete` → `False`. Parametrized over the write functions so a ninth cannot be added untested.
  - **AC 4 (flag off, reads)** — same double: `list_for` → `[]`, `get` → `None`, `messages_for` → `[]`, and nothing on the database module was touched. The assertion is that the double never fired, not that the result was empty.
  - **AC 5** — `list_for` has no `limit` parameter (`inspect.signature`), and with `settings.CHAT_SESSION_LIMIT` patched to a small value against a user with more sessions, it returns exactly that many.
  - **AC 6** — `create` calls the injected deriver exactly once with the prompt and writes its return value as the title; a deriver returning a sentinel string proves the service reimplemented nothing.
  - **AC 7** — two seeded users: every read driven with the wrong identity returns `[]`/`None`; every write returns `False`/raises and leaves both tables' row counts unchanged; and `get` for a foreign id is indistinguishable from `get` for a random UUID.
  - **AC 8 (error wrapping)** — against `uninitialized_db`, each of the eight raises `ChatSessionError` (not `StorageError`), and `__cause__` is the `StorageError`.
  - **AC 8, second case** — `append_message` for a foreign session and for an unknown session raise `ChatSessionError` with **identical** `str(exc)`.
  - **Risk guard: no caller branches on the flag** — `ast`-walk every `.py` under `app/` and `chat_ui/` and assert the identifier `CHAT_HISTORY_ENABLED` appears only in `app/config.py` and `app/services/chat_sessions.py`. Read through `ast` and not a text grep, so the comments in `app/config.py` that name the setting in prose do not have to be special-cased in other files.
- **Mirror**: `tests/test_chat_sessions.py:148-205` for the structural-assertion idiom and section labelling; `tests/test_duplicate_checker.py:99-101` for the `uninitialized_db` error case; `tests/test_chat_sessions.py:508-560` (`test_two_users_see_nothing_of_each_others_sessions`) for the two-user seeding shape.
- **Validate**: `python -m pytest tests/test_chat_sessions.py -q`

### Task 5: Full-suite regression

- **File**: —
- **Action**: verify
- **Implement**: run the whole suite. This story adds a new module and touches no existing one, so any red outside `tests/test_chat_sessions.py` is either the guard in Task 4 finding a real pre-existing `CHAT_HISTORY_ENABLED` branch (there should be none — `grep` currently finds the identifier only in `app/config.py`) or the libSQL dev-server degradation.
- **Validate**: `python -m pytest -q`

---

## End-to-End Tests

For `/implement` to execute:

- [ ] `docker ps` shows `harness-libsql-dev` running (restart it rather than bisecting if fixtures error en masse)
- [ ] `python -m pytest tests/test_chat_sessions.py -q` — the STORY-004, STORY-005 and new STORY-006 sections all pass
- [ ] `python -m pytest tests/test_config.py tests/test_db.py tests/test_identity.py tests/test_authz.py -q` — the modules this one imports are unaffected
- [ ] `python -m pytest -q` — no regression anywhere
- [ ] Manual round trip in a REPL against the dev database: `init_db()`, resolve an `Identity`, `create` → `append_message` → `messages_for` → `touch` → `list_for` → `delete`, then the same sequence under a second identity against the first's `session_id`, confirming nothing is returned and nothing is deleted
- [ ] Same round trip with `settings.CHAT_HISTORY_ENABLED = False`: every call returns its flag-off value and `count_chat_sessions` is unchanged at the end

## Validation

```bash
python -c "import app.services.chat_sessions"
python -m pytest tests/test_chat_sessions.py -q
python -m pytest -q
grep -rn "CHAT_HISTORY_ENABLED" app/ chat_ui/ --include=*.py   # only config.py and chat_sessions.py
grep -rn "chat_ui" app/services/chat_sessions.py               # no match
```

## Acceptance Criteria

(Copied from story STORY-006)

- [ ] Given `app/services/chat_sessions.py`, when it is read, then it exposes `create`, `list_for`, `get`, `rename`, `touch`, `delete`, `append_message` and `messages_for`, each taking an `Identity` rather than a bare `user_id` string.
- [ ] Given every function, when it calls into `app/db/database.py`, then it passes `identity.user_id` — the service is the only place that converts an Identity into an owner, and no caller outside it reaches `database.py`'s session functions.
- [ ] Given `settings.CHAT_HISTORY_ENABLED is False`, when any write function is called, then **no statement is issued** and the caller receives a value it can proceed with: `create` returns `None`, `append_message` returns `None`, `touch`/`rename`/`delete` return `False`.
- [ ] Given `settings.CHAT_HISTORY_ENABLED is False`, when any read function is called, then it returns an empty list or `None` without issuing a statement — asserted by patching the database module and observing that nothing on it was called, not merely by observing an empty result.
- [ ] Given `CHAT_SESSION_LIMIT`, when `list_for` is called, then it passes that setting as the limit, and no caller supplies its own.
- [ ] Given `create(identity, first_prompt)`, when it is called, then the session is created with a title derived from the prompt, and the derivation is **delegated**, not reimplemented — STORY-012 owns the rule. (Delegated via an injected `derive_title` callable; see the Decision section.)
- [ ] Given a foreign `session_id`, when it is passed to any function, then the service returns the same not-found value as a genuinely missing id — the caller cannot distinguish "does not exist" from "not yours".
- [ ] Given a `StorageError` from the database layer, when it reaches the service, then it is wrapped in a module-owned `ChatSessionError`, in the pattern `app/services/duplicate_checker.py` uses for `DuplicateCheckError`.
- [ ] Given `tests/test_chat_sessions.py`, when it runs, then the flag-off case, the foreign-identity case and the error-wrapping case each have their own assertion.
- [ ] All tasks completed
- [ ] Full test suite passes
- [ ] No `if settings.CHAT_HISTORY_ENABLED` anywhere outside this module and `app/config.py`
- [ ] `app/services/chat_sessions.py` imports nothing from `chat_ui/`
- [ ] Follows existing patterns
