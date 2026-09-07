---
story: STORY-007
prd: PRD-008
slug: ownership-signature-guard
title: "tests/test_session_ownership.py: the ownership rule asserted against signatures, not against memory"
type: ENHANCEMENT
complexity: LOW
epic_branch: epic/PRD-008-chat-sessions
created: 2026-09-03
---

# Plan: tests/test_session_ownership.py — the ownership rule asserted against signatures, not against memory

## Summary

Add one test module, `tests/test_session_ownership.py`, that **discovers** the session/message surface rather than listing it: every public function defined in `app/db/database.py` whose name contains `_chat_session` or `_chat_message`, and every public function defined in `app/services/chat_sessions.py`. Over the discovered store surface it asserts `user_id` is present, undefaulted and annotated `str`; over the discovered service surface it asserts `identity: Identity` is the first parameter and no `user_id` leaks back out. It then drives every discovered function with a foreign credential through one call table that is itself asserted to cover the discovered set — so a tenth function added next month fails the coverage test rather than being silently skipped. Reads must return empty / `None` / `False` / `0`; writes must leave both tables byte-identical by row count, and `count_audit_logs()` unchanged. No production code changes. This is PRD Risk 2's mitigation turned from a document into a suite.

## User Story

As a maintainer
I want the "every session function names an owner" rule enforced by a test that inspects the signatures
So that the rule still fails when someone adds a tenth function next month and nobody remembers the rule existed.

## Story Reference

- Story file: `.agents/stories/PRD-008-chat-sessions/STORY-007-ownership-signature-guard.md`
- PRD: `.agents/PRDs/PRD-008-chat-sessions/PRD.md` — Section 6, Section 11 (Quality indicators), Section 12 Phase 1, Risk 2

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT (test-only; no production code) |
| Complexity | LOW |
| Systems Affected | `tests/` (one new module). Nothing under `app/` or `chat_ui/`. |
| Story | STORY-007 |
| PRD | PRD-008 |
| Epic Branch | `epic/PRD-008-chat-sessions` (commit directly on this branch) |

**Dependencies verified** against `.agents/PRDs/PRD-008-chat-sessions/index.md`: STORY-004 (`fdbc538`), STORY-005 (`1851c25`), STORY-006 (`1f529d3`) are all `status: done`. Nothing blocks this story.

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | `.agents/skills/` was listed and holds exactly one skill, `frontend-design`, whose `description` scopes it to "distinctive, intentional visual design when building new UI or reshaping an existing one". This story writes one test module, renders nothing, and touches no file under `chat_ui/`. | None |

The story's Technical Notes reach the same conclusion; this plan re-ran the scan rather than inheriting it. `SKILL.md` was read in full to confirm the scope, not skimmed from its front matter. No `skills:` entry is set on the story frontmatter, and none should be added.

---

## Patterns to Follow

### Discovery over enumeration (the whole point of the story)

```python
# SOURCE: tests/test_chat_sessions.py:1027-1042
def _service_functions() -> dict:
    """Every public function *defined* in the service module.

    Discovered, not enumerated -- STORY-007's point, applied one story early so
    that the surface assertions here cannot go stale. `__module__` is what
    excludes `contextmanager`, a public callable in the module's namespace
    because it was imported there and no part of its surface.
    """
    return {
        name: obj
        for name, obj in vars(chat_sessions).items()
        if inspect.isfunction(obj)
        and not name.startswith("_")
        and obj.__module__ == chat_sessions.__name__
    }
```

The `__module__` filter is load-bearing and must be reproduced: `database.py` imports `datetime` and `uuid` into its namespace, and `chat_sessions.py` imports `contextmanager`. Without it the predicate sweeps in callables that are no part of either surface.

### Signature assertions

```python
# SOURCE: tests/test_chat_sessions.py:172-184
def test_every_signature_requires_an_undefaulted_user_id():
    for name in THE_SIX:
        parameters = inspect.signature(getattr(database, name)).parameters
        assert "user_id" in parameters, name
        user_id = parameters["user_id"]
        assert user_id.default is inspect.Parameter.empty, name
        assert user_id.annotation is str, name
        assert user_id.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD, name
```

```python
# SOURCE: tests/test_chat_sessions.py:1114-1123
def test_every_service_function_takes_an_identity_first():
    for name, function in _service_functions().items():
        parameters = list(inspect.signature(function).parameters.values())
        assert parameters, name
        assert parameters[0].name == "identity", name
        assert parameters[0].annotation is Identity, name
        assert parameters[0].default is inspect.Parameter.empty, name
```

### Two real users, so a foreign id is a foreign id that exists

```python
# SOURCE: tests/test_chat_sessions.py:105-114
def _seed_users() -> None:
    """Two real users, so a foreign id in a test is a foreign id that exists.

    A test that drives a read with `"bob"` when no bob row exists proves less
    than one where bob is a genuine account: the first can pass because the id
    is unknown, the second only passes because the `WHERE` clause scopes.
    """
    insert_user(User(user_id="ana", role="user", token_hash="hash-ana"))
    insert_user(User(user_id="bob", role="user", token_hash="hash-bob"))
```

This story's Technical Notes require the stronger version — real credentials rather than hand-written hashes — which is `tests/test_rbac.py`'s idiom:

```python
# SOURCE: tests/test_rbac.py:97-98, with app/services/identity.py:34-42
token = f"{role}-token"
insert_user(User(user_id=f"{role}-id", role=role, token_hash=hash_token(token)))
```

Here: `token = issue_token()` per user, `token_hash=hash_token(token)`, and the `Identity` is then obtained through `resolve(token)`, so the credential path is the one that produced it.

### One call table, driving the whole surface

```python
# SOURCE: tests/test_chat_sessions.py:1059-1083
def _call(name: str, identity: Identity, session_id: str, **overrides):
    """Calls one service function with arguments valid for its signature.

    One table of call shapes, so the flag-off, foreign-identity and
    error-wrapping cases below can drive all eight without any of them
    enumerating arguments a second time -- and so a signature change breaks one
    place rather than three.
    """
    shapes = {"create": lambda: chat_sessions.create(identity, prompt, derive), ...}
    return shapes[name]()
```

### Fixtures

`tests/conftest.py:180-190` — `temp_db` is the only fixture this module uses (`init_db()` already run; the database is emptied per test by the autouse `_never_the_configured_database`). The story forbids adding a second fixture, and none is needed.

### Test naming and prose

Sentence-shaped names (`test_every_read_path_returns_nothing_for_a_foreign_credential`) and docstrings that name the AC and say *why* the assertion is the honest one — the idiom of `tests/test_chat_sessions.py` and `tests/test_untouched_app.py` throughout.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `tests/test_session_ownership.py` | CREATE | The whole story: the ownership rule discovered from the modules and driven with a foreign credential. |
| `.agents/stories/PRD-008-chat-sessions/STORY-007-ownership-signature-guard.md` | UPDATE | `plan`, `status`, `updated` (Phase 5 of `/plan`, done at plan time). |
| `.agents/PRDs/PRD-008-chat-sessions/index.md` | UPDATE | Status + plan link (Phase 5). |

**No file under `app/` or `chat_ui/` is touched.** If a signature has to change to make a test pass, that is a defect in STORY-004, STORY-005 or STORY-006 and is fixed there, with the reason recorded in this story's report — the story's Technical Notes say so, and this plan reserves no task for it because the current surface already satisfies the rule (verified below).

### Surface as it stands today (verified while planning, not assumed)

Nine public store functions match the story's glob, all in `app/db/database.py`:

| Function | Line | `user_id` |
|---|---|---|
| `create_chat_session(user_id, title)` | 1231 | required, `str`, first |
| `get_chat_session(session_id, user_id)` | 1264 | required, `str` |
| `list_chat_sessions(user_id, limit=50)` | 1290 | required, `str` |
| `rename_chat_session(session_id, user_id, title)` | 1323 | required, `str` |
| `touch_chat_session(session_id, user_id)` | 1346 | required, `str` |
| `delete_chat_session(session_id, user_id)` | 1362 | required, `str` |
| `append_chat_message(message, session_id, user_id)` | 1438 | required, `str` |
| `list_chat_messages(session_id, user_id)` | 1533 | required, `str` |
| `count_chat_sessions(user_id)` | 1580 | required, `str` |

Eight public service functions in `app/services/chat_sessions.py`: `create`, `list_for`, `get`, `rename`, `touch`, `delete`, `append_message`, `messages_for` — each `identity: Identity` first.

`count_audit_logs(user_id=None)` is deliberately **outside** the discovered surface: its name matches neither glob, and its `user_id` is an optional admin filter, not an ownership scope. The discovery predicate must not widen to catch it — a plain substring test on `_chat_session` / `_chat_message` is exactly right, and this is why.

---

## Design notes taken before writing tests

**1. Why a new file rather than more of `tests/test_chat_sessions.py`.** The story names the file, and that file's own docstring (`tests/test_chat_sessions.py:11-16`) already reserves the scope: *"What this file does not do is enumerate the ownership rule structurally for the whole surface. STORY-007 owns `tests/test_session_ownership.py`, which discovers every `*_chat_session*` / `*_chat_message*` callable and asserts the rule against whatever it finds."* The overlap with the named assertions there is intentional and is recorded in the new module's docstring: one rule, two scopes — nine named functions that make STORY-004/005 verifiable on their own, and a discovered set that outlives their names.

**2. The predicate must have a floor.** A discovery test whose predicate breaks finds nothing and passes vacuously — the failure mode that would make discovery *weaker* than enumeration. Every discovery here is guarded by a census test asserting the found set is non-empty and contains the nine (resp. eight) functions that exist today. That assertion may grow, never shrink.

**3. The call table is asserted against the discovery, not written beside it.** `_call_store(name, ...)` / `_call_service(name, ...)` map each discovered name to a call shape, and a test asserts `sorted(table) == sorted(discovered)`. This is what makes the tenth function fail: it is discovered, it has no call shape, and the coverage test goes red before anyone reaches the ownership assertions.

**4. `create_chat_session` / `create` are exempt from the foreign-credential drive, and the exemption is written down.** They take no session id and mint a row owned by whoever is named — there is no foreign row to reach. The other eight store functions and the other seven service functions are all driven. `tests/test_chat_sessions.py:194-215` establishes the shape of this exemption for the SQL half; the same reasoning is stated in the new file rather than cross-referenced.

**5. Write invariance is asserted by counting rows, not by trusting the return.** AC 5 requires this explicitly: `SELECT COUNT(*)` over `chat_sessions` and `chat_messages` before and after, plus the full row tuples for the owner's session, so a same-count mutation (a foreign `rename` that changed a title) cannot pass. `count_audit_logs()` is captured across the foreign `delete` for AC 6, alongside the owner's `chat_messages` count.

**6. `append_chat_message` raises rather than returning falsy, and the test must expect that.** The store raises `StorageError` for a foreign or unknown session (`app/db/database.py:1438`ff), and the service wraps it as `ChatSessionError` (`app/services/chat_sessions.py:246-273`). AC 4's "empty, `None` or `False`" describes the **read** paths; the write paths raise, deliberately — *"a read that finds nothing is an ordinary outcome, a write that silently lands nowhere is not"*. The foreign-write test therefore accepts *either* a falsy return *or* the module's own exception type, and asserts the row counts unchanged in both arms. Nothing here changes production behaviour to fit the criterion.

**7. Offline (AC 7).** The module imports nothing new, reads no environment variable, opens no client of its own, and takes its database from `temp_db` — which `tests/conftest.py` points at the local libSQL dev server. That is the property PRD-007 STORY-006 established for every test in this repository, and it is preserved by not deviating from the fixture.

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Module docstring, imports and discovery helpers

- **File**: `tests/test_session_ownership.py`
- **Action**: CREATE
- **Implement**:
  - Module docstring in the register of `tests/test_untouched_app.py:1-32`: the rule was a document, and a document does not fail when someone adds a database function next month; why this file overlaps `tests/test_chat_sessions.py` and what each scope owns (Design note 1); PRD Risk 2's mitigation quoted verbatim.
  - Imports: `inspect`, `pytest`, `from app.db import database`, `from app.db.errors import StorageError`, `from app.db.database import count_audit_logs, get_connection, insert_audit_log, insert_user`, `from app.db.models import AuditLog, StoredMessage, User`, `from app.services import chat_sessions`, `from app.services.chat_sessions import ChatSessionError`, `from app.services.identity import Identity, hash_token, issue_token, resolve`.
  - `_SURFACE_MARKERS = ("_chat_session", "_chat_message")`, with a comment naming `count_audit_logs` as the function this must *not* catch, and why.
  - `_store_surface() -> dict` and `_service_surface() -> dict`, both filtering on `inspect.isfunction`, `not name.startswith("_")` and `obj.__module__ == <module>.__name__`; the store one additionally on the markers.
- **Mirror**: `tests/test_chat_sessions.py:1027-1042` (`_service_functions`); docstring register from `tests/test_untouched_app.py:1-32`.
- **Validate**: `python -c "from tests.test_session_ownership import _store_surface, _service_surface; print(sorted(_store_surface()), sorted(_service_surface()))"` prints the nine and the eight.

### Task 2: The census tests — the floor under the discovery

- **File**: `tests/test_session_ownership.py`
- **Action**: UPDATE
- **Implement**: `test_the_store_surface_is_discovered_and_not_empty` and `test_the_service_surface_is_discovered_and_not_empty`. Each asserts the discovered set is non-empty and a **superset** of the functions that exist today (listed as `_KNOWN_STORE` / `_KNOWN_SERVICE`). Docstring says why: a broken predicate finds nothing and every assertion below passes vacuously, which would make discovery weaker than the enumeration it replaces (Design note 2). Superset, not equality, so adding a function is a change to the *rule* tests, not to this one.
- **Mirror**: `tests/test_chat_sessions.py:1100-1112`.
- **Validate**: `pytest tests/test_session_ownership.py -k discovered -q` → 2 passed.

### Task 3: AC 1 — every store function declares a required, undefaulted `user_id`

- **File**: `tests/test_session_ownership.py`
- **Action**: UPDATE
- **Implement**:
  - `test_every_discovered_store_function_requires_an_undefaulted_user_id`: over `_store_surface()`, assert `"user_id" in parameters`, `default is inspect.Parameter.empty`, `annotation is str`, `kind is POSITIONAL_OR_KEYWORD`. The failure message names the function.
  - `test_omitting_user_id_is_a_type_error_on_every_discovered_function`: `pytest.raises(TypeError)` calling each with no arguments — the consequence Risk 2 names ("a `TypeError` at the call site rather than a leak at runtime"), exercised rather than only asserted structurally.
- **Mirror**: `tests/test_chat_sessions.py:172-192`.
- **Validate**: `pytest tests/test_session_ownership.py -k user_id -q` → passed.

### Task 4: AC 3 — every service function takes an `Identity` first, and no bare `user_id`

- **File**: `tests/test_session_ownership.py`
- **Action**: UPDATE
- **Implement**:
  - `test_every_discovered_service_function_takes_an_identity_first`: first parameter named `identity`, annotated `Identity`, undefaulted.
  - `test_no_discovered_service_function_accepts_a_bare_user_id`: `"user_id" not in signature.parameters` — the conversion happens once, inside the service, and a `user_id` parameter up here would mean it leaked back out.
- **Mirror**: `tests/test_chat_sessions.py:1114-1132`.
- **Validate**: `pytest tests/test_session_ownership.py -k identity -q` → passed.

### Task 5: Two real users, and the call tables that cover the surface

- **File**: `tests/test_session_ownership.py`
- **Action**: UPDATE
- **Implement**:
  - `_seed_two_users() -> tuple[Identity, Identity]`: for each of `ana` and `bob`, `token = issue_token()`, `insert_user(User(user_id=..., role="user", token_hash=hash_token(token)))`, then `identity = resolve(token)`; assert both resolved. Docstring: hashes are not fabricated by hand (story Technical Notes), and both users are real, so a foreign id is a foreign id that *exists* (`tests/test_chat_sessions.py:105-114`).
  - `_stored(session_id)` returning a minimal `StoredMessage(kind="user", content=...)`.
  - `_call_store(name, *, user_id, session_id)` and `_call_service(name, *, identity, session_id)`: one lambda per discovered name, `create_chat_session` / `create` included so the tables are complete.
  - `_EXEMPT_STORE = {"create_chat_session"}` and `_EXEMPT_SERVICE = {"create"}`, each carrying the comment from Design note 4.
  - `test_the_store_call_table_covers_every_discovered_function` and `test_the_service_call_table_covers_every_discovered_function`: `sorted(table) == sorted(surface)`. **This is the test that catches the tenth function.**
  - `_count(table)` over `get_connection()` for `chat_sessions` / `chat_messages`, and `_owner_rows()` returning the owner's session and message rows as tuples.
- **Mirror**: `tests/test_chat_sessions.py:1059-1092` (call table + counters); `tests/test_rbac.py:97-98` with `app/services/identity.py:34-42` (credential seeding).
- **Validate**: `pytest tests/test_session_ownership.py -k call_table -q` → 2 passed.

### Task 6: AC 4 — every read path driven with the other user's credential returns nothing

- **File**: `tests/test_session_ownership.py`
- **Action**: UPDATE
- **Implement**: parametrized over the discovered read paths in both modules (`get_chat_session`, `list_chat_sessions`, `list_chat_messages`, `count_chat_sessions`; `get`, `list_for`, `messages_for`). Seed `ana`'s session with two messages, drive each call with `bob`'s `user_id` / `Identity` and `ana`'s `session_id`, and assert the result is one of `None`, `[]`, `False`, `0` — and specifically **not** a row: for the list paths assert `result == []` rather than only falsiness, so a one-row leak cannot pass as truthy-but-unchecked. The docstring records that `count_chat_sessions` returning `0` is the count-shaped spelling of "no rows", which is what AC 4 asks of it.
- **Mirror**: `tests/test_chat_sessions.py:520-550`, `839-853`.
- **Validate**: `pytest tests/test_session_ownership.py -k foreign_read -q` → passed.

### Task 7: AC 5 — every write path driven with a foreign credential changes nothing

- **File**: `tests/test_session_ownership.py`
- **Action**: UPDATE
- **Implement**: parametrized over the discovered write paths minus the exemptions (`rename_chat_session`, `touch_chat_session`, `delete_chat_session`, `append_chat_message`; `rename`, `touch`, `delete`, `append_message`). Capture `_count("chat_sessions")`, `_count("chat_messages")` and `_owner_rows()` before; drive the call with `bob`'s credential against `ana`'s session inside a `try/except (StorageError, ChatSessionError)`; assert counts and row tuples identical afterwards — **in both the returned-falsy and the raised arm** (Design note 6). Assert the return value is falsy whenever the call did return. Docstring quotes AC 5: "asserted by counting rows in both tables, not by trusting the return value".
- **Mirror**: `tests/test_chat_sessions.py:484-518`, `855-890`.
- **Validate**: `pytest tests/test_session_ownership.py -k foreign_write -q` → passed.

### Task 8: AC 6 — `count_audit_logs()` and the owner's messages survive a foreign delete

- **File**: `tests/test_session_ownership.py`
- **Action**: UPDATE
- **Implement**: `test_a_foreign_delete_leaves_audit_logs_and_the_owners_messages_alone`. Seed two users, one `ana` session with two messages, and two `audit_logs` rows via `insert_audit_log`. Capture `count_audit_logs()` and the owner's `chat_messages` count; attempt `database.delete_chat_session(session_id, bob.user_id)` **and** `chat_sessions.delete(bob_identity, session_id)`; assert `False` from each, `count_audit_logs()` unchanged, the owner's message count unchanged, and the session still readable by `ana`. Docstring names PRD Section 9: deleting a conversation deletes a conversation, it does not edit the record of what was asked — and here nothing was deleted at all.
- **Mirror**: `tests/test_chat_sessions.py:462-518` (`test_delete_leaves_audit_logs_untouched`, `test_delete_with_a_foreign_user_leaves_audit_logs_untouched`), including its `AuditLog` construction.
- **Validate**: `pytest tests/test_session_ownership.py -k audit -q` → passed.

### Task 9: AC 2 — prove the guard fails on a new function, then remove the proof

- **File**: `app/db/database.py` and `app/services/chat_sessions.py` (both temporary); `tests/test_session_ownership.py` unchanged
- **Action**: UPDATE then REVERT
- **Implement**:
  1. Temporarily append to `app/db/database.py`:
     ```python
     def list_chat_messages_for_everyone(session_id: str) -> list:  # TEMPORARY - STORY-007 AC 2
         return []
     ```
  2. Run `pytest tests/test_session_ownership.py -q` and **record the failures**: the `user_id` signature test, the `TypeError` test and the store call-table coverage test must go red, naming the new function.
  3. Repeat on the service side with a temporary `def purge(session_id: str) -> bool: return False` in `app/services/chat_sessions.py`, confirming the `identity`-first test, the bare-`user_id` test and the service call-table test go red.
  4. Delete both probes. Confirm `git status` is clean for `app/` and `git diff -- app/` is empty.
- **Mirror**: the story's AC 2 — "verified during implementation by adding one temporarily and observing the red, then removing it".
- **Validate**: red observed and pasted into the story report; afterwards `git diff --stat -- app/ chat_ui/` is empty and `pytest tests/test_session_ownership.py -q` is green.

### Task 10: Full-suite regression and the offline property

- **File**: —
- **Action**: VERIFY
- **Implement**:
  - `pytest tests/test_session_ownership.py -q` green.
  - `pytest tests/test_chat_sessions.py tests/test_rbac.py tests/test_db.py tests/test_identity.py -q` green — the neighbours this file overlaps.
  - `pytest -q` green (full suite). If the run shows mass fixture errors, restart the libSQL dev container before concluding anything about the code — that degradation is environmental, not a regression to bisect.
  - AC 7: confirm no `TURSO_*` variable is set in the shell and no `.env` is required — the runs above already use `tests/conftest.py`'s local endpoint. Grep the new file for `os.environ`, `turso`, `libsql` and confirm zero hits.
- **Validate**: `pytest -q` green, and `grep -niE "os\.environ|turso|libsql" tests/test_session_ownership.py` → no matches.

### Task 11: Report and commit on the epic branch

- **File**: `.agents/reports/PRD-008-chat-sessions/STORY-007-*.md`, `.agents/stories/.../STORY-007-*.md`, `.agents/PRDs/PRD-008-chat-sessions/index.md`
- **Action**: CREATE / UPDATE / COMMIT
- **Implement**: write the story report (including the Task 9 red output and the note that no production signature had to change), then `git add tests/test_session_ownership.py` plus the story/report/index updates and commit on `epic/PRD-008-chat-sessions` with `test(PRD-008): STORY-007 ownership rule asserted against discovered signatures`. Record the SHA in the story frontmatter, the report and `index.md`, as STORY-004/005/006 did.
- **Validate**: `git log --oneline -1`, `git status` clean, and `git diff --stat HEAD~1 -- app/ chat_ui/` empty.

---

## End-to-End Tests

- [ ] `pytest tests/test_session_ownership.py -q` — green
- [ ] Temporarily add `list_chat_messages_for_everyone(session_id)` to `database.py` → the suite goes red on the signature test **and** the store call-table coverage test; remove it → green (AC 2)
- [ ] Temporarily add `purge(session_id)` to `chat_sessions.py` → the service `identity`-first test and the service call-table test go red; remove it → green (AC 3)
- [ ] Drive every read path with the other user's credential → `None` / `[]` / `False` / `0`, never a row (AC 4)
- [ ] Drive every write path with a foreign credential → row counts in `chat_sessions` and `chat_messages` identical before and after (AC 5)
- [ ] Foreign `delete` → `count_audit_logs()` unchanged and the owner's `chat_messages` count unchanged (AC 6)
- [ ] Full suite `pytest -q` green with no `.env` and no Turso credential in the environment (AC 7)
- [ ] `git diff -- app/ chat_ui/` empty at the end (this story adds no production code)

---

## Validation

```bash
pytest tests/test_session_ownership.py -q
pytest tests/test_chat_sessions.py tests/test_rbac.py tests/test_db.py -q
pytest -q
grep -niE "os\.environ|turso|libsql" tests/test_session_ownership.py   # expect no matches
git diff --stat -- app/ chat_ui/                                        # expect empty
```

---

## Acceptance Criteria

(Copied from story `STORY-007`)

- [ ] Given `tests/test_session_ownership.py`, when it runs, then it enumerates every public callable in `app/db/database.py` whose name matches the session/message surface (`*_chat_session*`, `*_chat_message*`) and asserts each declares a `user_id` parameter that is **required and has no default**.
- [ ] Given a hypothetical new function added to that surface without `user_id`, when the suite runs, then this test fails — verified during implementation by adding one temporarily and observing the red, then removing it.
- [ ] Given `app/services/chat_sessions.py`, when the same inspection runs over it, then every public function takes an `Identity` as its first parameter.
- [ ] Given two seeded users, when every read path in both modules is driven with the other user's credential, then each returns empty, `None` or `False`, and never a row.
- [ ] Given every write path driven with a foreign credential, when the call returns, then the database is byte-identical to before — asserted by counting rows in both tables, not by trusting the return value.
- [ ] Given `count_audit_logs()`, when a foreign-credential `delete` is attempted, then it is unchanged, and so is the count of `chat_messages` rows belonging to the real owner.
- [ ] Given the suite, when it runs offline with no Turso account, then it passes — the property PRD-007 STORY-006 established for every test in this repository.
- [ ] All tasks completed
- [ ] No production code changed (`git diff -- app/ chat_ui/` empty)
- [ ] Full suite green
- [ ] Follows existing patterns
