---
story: STORY-007
prd: PRD-018
slug: chat-ui-storage-failures
title: Chat UI — resolve() inside the send's try/finally, sign-in storage notice, fixed storage_unavailable copy
type: BUG_FIX
complexity: LOW
epic_branch: epic/PRD-018-db-resilience
created: 2026-11-17
---

# Plan: Chat UI survives a storage failure

## Summary

Three small changes in `chat_ui/chat_ui/state.py`, two new strings in
`chat_ui/chat_ui/copy.py`, and one new non-`db` test file. No markup changes.

1. `_do_send`: `resolve(token)` moves inside the `try`/`finally` that clears
   `pending`, and runs off the event loop through `asyncio.to_thread`. A
   `StorageError` (which includes `StorageUnavailableError`) from it appends an
   `internal_error` bubble whose detail is fixed copy, and the `finally` clears
   `pending`.
2. `login`: the same `resolve()` call, also through `asyncio.to_thread`, gets an
   `except StorageError` arm that sets `login_error` to a new storage notice. The
   user stays signed out.
3. The gate arm (`DuplicateCheckError`, `PiiRedactorError`, `UsageLimitError`,
   plus `ChatSessionError`, moved there from the catch-all) uses the fixed copy
   when `storage_unavailable_cause(exc)` (STORY-006,
   `app/services/storage_faults.py:25-43`) finds a `StorageUnavailableError`
   behind a `ChatSessionError` / `DuplicateCheckError` / `UsageLimitError`. Every
   other cause keeps `detail=str(exc)`, as today.

No retry in the UI (the unit of work already retried). Driver text never reaches a
bubble or `login_error` on these paths.

## User Story

As a chat user
I want a storage failure during sign-in or at the start of a send to show a clear message and leave the composer usable
So that I am never stuck with a locked composer and driver text in a bubble.

## Story Reference

- Story file: `.agents/stories/PRD-018-db-resilience/STORY-007-chat-ui-storage-failures.md`
- PRD: `.agents/PRDs/PRD-018-db-resilience/PRD.md` (Sections 3 "Chat user", 6.7 chat column, 9.2 T9, 11 "`pending == False`")

## Metadata

| Field | Value |
|-------|-------|
| Type | BUG_FIX |
| Complexity | LOW |
| Systems Affected | `chat_ui/chat_ui/state.py`, `chat_ui/chat_ui/copy.py`, tests |
| Story | STORY-007 |
| PRD | PRD-018 |
| Epic Branch | `epic/PRD-018-db-resilience` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| frontend-design (`.agents/skills/frontend-design/SKILL.md`) | Listed on the story. **No visual markup changes** (the existing `internal_error` bubble `components/bubbles.py:474-481` and the `login_error` slot `components/shell.py:585-587` render the new strings unchanged), so only its writing rules apply to the two new strings: "Write from the end user's side of the screen", "Errors don't apologize, and they are never vague about what happened", "An action keeps the same name through the whole flow" (the bubble's button is `RETRY_LABEL` = "Retry", `bubbles.py:457`, so the copy says "Retry"). | Task 1, Task 6 |

No other skill under `.agents/skills/` (only `frontend-design` exists).

---

## Verified facts the design rests on

- `_do_send` today (`state.py:950-985`): `pending = True` at `:962` inside the first
  `async with self`, `identity = resolve(token)` at `:967` on the event loop, the
  `identity is None` arm clears `pending` by hand at `:982-984`, and the `try`
  opens at `:995`. Its `finally` (`:1286-1295`) clears `pending` and re-applies
  `history_error`. `history_error = ""` is set at `:993`, before the `try`. So a
  `StorageError` from `:967` escapes the background task with `pending` stuck
  (PRD 3, "Chat user"). The story's line numbers are still accurate.
- `login` (`state.py:292-337`): plain async handler holding the state lock;
  `resolve(token)` at `:311`, unguarded, on the event loop. The session read in the
  same handler is already offloaded: `_load_sessions` uses `asyncio.to_thread`
  (`:359-360`). Its `invalid token` arm (`:312-314`) keeps `token_input`.
- Gate arms (`state.py:1153-1197`): `OpenRouterError` at `:1153`, the named arm
  `(DuplicateCheckError, PiiRedactorError, UsageLimitError)` at `:1175-1186` with
  `detail=str(exc)` at `:1181`, the catch-all `except Exception` at `:1187-1197`
  with `detail=str(exc)` at `:1193`.
- `resolve()` (`app/services/identity.py:69-92`): break-glass at `:78-81` does no
  read; `find_user_by_token_hash` at `:83` is the one storage call. Since STORY-005 it
  raises `StorageUnavailableError` for any infrastructure failure and a plain
  `StorageError` for a statement failure; `MissingRelationError` is folded into
  `None` one layer down (`app/db/errors.py:31-45`).
- `UsageLimitError` is raised only by `admit` (`app/services/usage_limits.py:155-162`),
  before the upstream call; `charge` fails open (`:204-216`). `DuplicateCheckError`
  is raised by `check_duplicate`, also before the upstream call. So "nothing was
  sent" is true for both, which is exactly what STORY-006 relied on for `/query`
  (`app/routers/query.py:40-45`).
- In the chat send path, no `ChatSessionError` reaches the gate arms today: the lazy
  create (`state.py:1044-1053`) and the history read (`:1080-1095`) each catch it
  into a degraded arm (PRD 6.4 table rows 3 and 11: "today's arm", unchanged). It is
  listed in AC 3 for parity with `/query`; moving it into the named arm costs nothing
  and makes AC 3 true by construction if a future pipeline call raises one.
- Driver text for an infra failure is already logged once by the unit of work
  through `_redacted()` (`app/db/database.py:1170-1185`). A plain statement-class
  `StorageError` is not logged there; see Task 2's single type-only log line.
- `state.py` already imports from `app.services` only; `app/middleware/auth.py:8`
  imports `StorageUnavailableError` from `app.db.errors` for the same `resolve()`
  call, which is the precedent for importing `StorageError` here (the exception
  surface, not a driver; PRD-007 7.2 holds).

### Decision: `resolve()` runs through `asyncio.to_thread` in both handlers

Chosen: **yes, for `login` and `_do_send`** (the two call sites this story owns).

- `resolve()` does a synchronous network read. Since STORY-003 that read can spend
  up to ~0.25 s in retry backoff (`database._retry_sleep`), and PRD-014 measured
  single-connection stalls of 7-21 s with no driver read timeout
  (`.agents/spikes/PRD-018-driver-failure-surface.md`). On the event loop, that
  freezes every connected chat and admin tab for the duration. Off the loop it
  freezes only this send.
- It matches the file's own rule: every other storage call in `state.py` is
  offloaded (`asyncio.to_thread` at `:359-360`, `:695`, `:766`, `:862`, `:918`,
  `:933`, `:940`, `:1046`; pipeline-side reads use `run_in_pipeline`, `:1085`).
  `asyncio.to_thread` rather than `run_in_pipeline`, because the identity read is a
  short rail-style read and the pipeline executor is reserved for pipeline work
  (PRD-010 STORY-006, comment at `state.py:1136-1139`).
- Safe for `login`: it is a plain async handler that already awaits
  `asyncio.to_thread` while holding the lock (`_load_sessions`, `:359`), so one more
  await changes nothing about its locking. Safe for `_do_send`: it is outside any
  `async with self` block.
- `asyncio.to_thread(resolve, token)` looks `resolve` up as a module global at call
  time, so `monkeypatch.setattr(chat_state_mod, "resolve", ...)` still works.
  `tests/test_chat_state.py:1189-1206` asserts `chat_sessions.list_for in offloaded`
  (membership, not equality), so the extra offloaded `resolve` does not break it.

Not changed (out of scope, reported as a follow-up): the four other inline
`resolve(self._token)` calls in `retry_sessions` (`:451`), `select_session`
(`:624`), `rename_session` (`:689`) and `delete_session` (`:760`). None of them
touches `pending`, so none can lock the composer; a `StorageError` there escapes as
an unhandled Reflex event error, as today.

---

## Patterns to Follow

### Naming / copy
```python
# SOURCE: chat_ui/chat_ui/copy.py:20-26
LOGIN_TOKEN_REQUIRED_ERROR = "Enter a token to sign in."
LOGIN_INVALID_TOKEN_ERROR = "Invalid or deactivated token."
# A credential can go bad mid-session (deactivated by an admin while the tab
# stays open). send() re-resolves on every call and surfaces this rather
# than silently keep using a role that no longer exists.
SESSION_INVALIDATED_ERROR = (
    "Your session credential is no longer valid. Sign out and sign in again."
)
```

### The "caused by" rule, as STORY-006 applied it
```python
# SOURCE: app/routers/v1.py:127 and :224-225
_STORAGE_GATE_FAULTS = (DuplicateCheckError, UsageLimitError)
...
    if isinstance(exc, _STORAGE_GATE_FAULTS) and storage_unavailable_cause(exc) is not None:
        return STORAGE_UNAVAILABLE
```
```python
# SOURCE: app/routers/query.py:46-59
    except (ChatSessionError, DuplicateCheckError, UsageLimitError) as exc:
        cause = storage_unavailable_cause(exc)
        if cause is not None:
            ...
                detail=STORAGE_UNAVAILABLE_NOT_SENT_DETAIL,
        ...
        raise HTTPException(status_code=500, detail=str(exc)) from exc
```

### Error handling: the existing no-identity bubble (one append path)
```python
# SOURCE: chat_ui/chat_ui/state.py:968-985
        if identity is None:
            # Through the same helper as every other bubble, even though its
            # guard will return before any write: ...
            await self._append_and_persist(
                ChatMessage(
                    kind="internal_error",
                    content="internal_error",
                    prompt=text,
                    detail=SESSION_INVALIDATED_ERROR,
                ),
                None,
                None,
            )
            async with self:
                self.pending = False
            return
```

### Tests
```python
# SOURCE: tests/test_chat_state.py:121-132
def _make_state(user_id: str = _AUTH_USER_ID, token: str = _AUTH_TOKEN) -> ChatState:
    state = ChatState(_reflex_internal_init=True)
    state.user_id = user_id
    state._token = token
    return state


async def _send(state: ChatState, text: str) -> None:
    state.input_text = text
    handler = type(state).event_handlers["send"]
    await handler.fn(state)  # bypasses the background-task chain guard on state.send()
```
```python
# SOURCE: tests/test_chat_state.py:437-451 (today's non-transient bubble; stays green unchanged)
async def test_chat_state_send_duplicate_check_error_appends_internal_error_bubble(temp_db, monkeypatch):
    def _raise_duplicate_check_error(*args, **kwargs):
        raise DuplicateCheckError("db locked")
    _stub_pipeline(monkeypatch, _raise_duplicate_check_error)
    ...
    assert state.messages[-1].detail == "db locked"
    assert state.pending is False
```
```python
# SOURCE: tests/test_chat_state.py:709 (stubbing run_in_pipeline directly)
    monkeypatch.setattr(chat_state_mod, "run_in_pipeline", _slow_run_in_pipeline)
```
```python
# SOURCE: tests/test_chat_state.py:755-761 (login test shape)
async def test_chat_state_login_invalid_token_shows_error_and_stays_locked(temp_db):
    state = ChatState(_reflex_internal_init=True)
    state.token_input = "not-a-real-token"
    await state.login()
    assert state.user_id == ""
    assert state.login_error == LOGIN_INVALID_TOKEN_ERROR
```
```python
# SOURCE: tests/test_copy.py:715-738 (copy-voice assertions)
        assert text[0].isupper() and text.endswith(".")
        for word in ("sorry", "apologise", "apologize", "oops", "unfortunately"):
            assert word not in text.lower()
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `chat_ui/chat_ui/copy.py` | UPDATE | Two new strings in the "Session gate" block: `LOGIN_STORAGE_UNAVAILABLE_ERROR`, `STORAGE_UNAVAILABLE_NOT_SENT_NOTICE` |
| `chat_ui/chat_ui/state.py` | UPDATE | `login` arm + offload; `_do_send` resolve inside `try`, offloaded, storage arm; gate arm applies the "caused by" rule; `ChatSessionError` joins the named arm; imports; one module logger |
| `tests/test_chat_ui_storage_failures.py` | CREATE | Non-`db` focused tests for AC 1, 2, 3 (resolve and pipeline stubbed) |
| `tests/test_copy.py` | UPDATE | Import the two new constants; one voice test |

No existing test assertion is modified. No pre-existing test is renamed or removed, so
`_DELIBERATELY_SUPERSEDED_TESTS` is not touched.

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: The two strings

- **File**: `chat_ui/chat_ui/copy.py`
- **Action**: UPDATE (insert after `SESSION_INVALIDATED_ERROR`, `:24-26`, inside "Session gate")
- **Implement**:
  ```python
  # PRD-018 Section 6.7 / T9: the database did not answer. Fixed sentences, never
  # the storage error's text (which can carry the driver's), and never the
  # invalid-token sentence above: an outage must not read as a bad credential.
  # The PRD fixes the meaning ("the harness's database is unavailable, nothing was
  # sent"); "Retry" is the bubble's own button (RETRY_LABEL), so the next step
  # carries the control's name. No retry happens here: storage already retried.
  LOGIN_STORAGE_UNAVAILABLE_ERROR = (
      "The harness's database is unavailable, so your token could not be "
      "checked. Sign in again in a moment."
  )
  STORAGE_UNAVAILABLE_NOT_SENT_NOTICE = (
      "The harness's database is unavailable, so nothing was sent. Retry in a moment."
  )
  ```
  Exact wording may be tuned, but it must: be English, start upper-case, end with
  ".", contain "unavailable", the bubble one contain "nothing was sent", neither
  contain "invalid", "Hrana", "StorageError" or an apology word.
- **Mirror**: `copy.py:20-26`.
- **Validate**: `.venv/Scripts/python -c "import chat_ui.chat_ui.copy as c; print(c.STORAGE_UNAVAILABLE_NOT_SENT_NOTICE)"` from the repo root.

### Task 2: Imports, logger, and the gate-fault tuple

- **File**: `chat_ui/chat_ui/state.py`
- **Action**: UPDATE
- **Implement**:
  - `import logging` beside `import asyncio` (`:1`); `logger = logging.getLogger(__name__)` after the imports (mirror `chat_ui/chat_ui/reports_state.py:28,49`).
  - `from app.db.errors import StorageError` (beside the `app.db.models` import, `:8`).
  - `from app.services.storage_faults import storage_unavailable_cause` (alphabetical among the `app.services` imports, `:18-26`).
  - Add `LOGIN_STORAGE_UNAVAILABLE_ERROR` and `STORAGE_UNAVAILABLE_NOT_SENT_NOTICE` to the `.copy` import (`:28-38`).
  - Module constant, with a comment citing PRD-018 D8 / Section 6.7 and `app/routers/query.py`:
    ```python
    # The gate errors whose cause decides the bubble's detail (PRD-018 D8, 6.7):
    # the /query set (routers/query.py). PiiRedactorError is not a storage gate.
    _STORAGE_GATE_FAULTS = (ChatSessionError, DuplicateCheckError, UsageLimitError)
    ```
  - Small helper next to `_to_chat_message` (module level, pure):
    ```python
    def _gate_fault_detail(exc: Exception) -> str:
        """The `internal_error` detail for a gate fault (PRD-018 T9, Section 6.7).

        Fixed copy when `storage_unavailable_cause` finds the outage behind it, so
        driver text never reaches the bubble; otherwise `str(exc)`, today's detail.
        """
    ```
  - Logging rule: log **only the exception type name**, never `str(exc)` (the driver
    text is logged once, redacted, by `_unit_of_work`; brief: "Logs never contain SQL,
    parameters or journal contents"). Never log the token.
- **Validate**: `.venv/Scripts/python -c "from app.main import app; print('OK')"` and the chat_ui probe (Task 7).

### Task 3: `login` maps a storage failure to a notice

- **File**: `chat_ui/chat_ui/state.py`
- **Action**: UPDATE `login` (`:292-316`)
- **Implement**: replace `identity = resolve(token)` (`:311`) with
  ```python
  # PRD-018 Section 6.7: off the event loop (the read can wait out a retry or a
  # stalled connection), and a storage failure is a notice, never "invalid
  # token" and never an unhandled event. Not signed in: nothing below runs.
  try:
      identity = await asyncio.to_thread(resolve, token)
  except StorageError as exc:
      logger.warning("chat sign-in: identity read failed (%s)", type(exc).__name__)
      self.login_error = LOGIN_STORAGE_UNAVAILABLE_ERROR
      return
  ```
  `token_input`, `_token` and `user_id` are left as they are (same as the invalid-token
  arm), so the user can press Sign in again. Add one sentence to the docstring naming
  the arm and the offload (cite PRD-018 6.7).
- **Mirror**: the invalid-token arm at `:312-314`; offload pattern at `:359`.
- **Validate**: Task 5's login tests.

### Task 4: `_do_send` resolves inside the `try`, off the loop, with a storage arm

- **File**: `chat_ui/chat_ui/state.py`
- **Action**: UPDATE `_do_send` (`:950-1000`)
- **Implement**:
  - Move the `identity = resolve(token)` block (`:965-985`) **into** the `try` that
    opens at `:995`, as its first statement, before the `async with self:` that clears
    `input_text` (so a failed resolve still leaves the user's text in the composer,
    as today's `identity is None` arm does). Keep `history_error = ""` before the `try`.
  - New code at the top of the `try`:
    ```python
    # PRD-005 Risk 5: re-resolved fresh on every call, never cached ...
    # PRD-018 (STORY-007): inside the try/finally, so a storage failure here
    # cannot leave `pending` set (PRD-004 Risk 3), and off the event loop,
    # like every other storage call in this class.
    try:
        identity = await asyncio.to_thread(resolve, token)
    except StorageError as exc:
        # Any storage failure, transient or not: the send never started, and the
        # bubble carries fixed copy, never the storage error's text (PRD-018 T9).
        logger.warning("chat send: identity read failed (%s)", type(exc).__name__)
        await self._append_and_persist(
            ChatMessage(
                kind="internal_error",
                content="internal_error",
                prompt=text,
                detail=STORAGE_UNAVAILABLE_NOT_SENT_NOTICE,
            ),
            None,
            None,
        )
        return
    if identity is None:
        ... existing bubble with SESSION_INVALIDATED_ERROR ...
        return
    ```
  - Delete the hand-written `async with self: self.pending = False` from the
    `identity is None` arm (`:982-984`): the `finally` now clears it. Update the comment
    at `:951-953` ("everything that can raise afterwards is inside the try/finally")
    so it is true again, citing PRD-018 STORY-007.
  - Both arms go through `_append_and_persist` with `None, None`, so
    `tests/test_chat_state.py:1833-1858` (no direct `self.messages.append` in
    `_do_send`) stays green, and the helper's guard (`:911-916`) skips any write.
- **Mirror**: `state.py:968-985`; offload pattern `state.py:1046`.
- **Validate**: Task 5's send tests; existing `test_chat_state_send_when_credential_revoked_mid_session_appends_internal_error` (`tests/test_chat_state.py:383-394`) and `test_chat_state_concurrent_send_guard` (`:696-723`).

### Task 5: The gate arm applies the "caused by" rule

- **File**: `chat_ui/chat_ui/state.py`
- **Action**: UPDATE the named arm (`:1171-1186`)
- **Implement**:
  - Widen the tuple to `(ChatSessionError, DuplicateCheckError, PiiRedactorError, UsageLimitError)`.
  - `detail=_gate_fault_detail(exc)` instead of `detail=str(exc)`.
  - Extend the comment above the arm: a gate fault caused by `StorageUnavailableError`
    shows fixed copy (PRD-018 D8 / T9); any other cause keeps `str(exc)`, today's
    bubble. `ChatSessionError` sits here for parity with `/query`; the chat path's own
    `ChatSessionError`s are caught earlier by the degraded create/history arms.
  - **The catch-all `except Exception` (`:1187-1197`) is unchanged**: see Risks (a bare
    `StorageUnavailableError` there can come from the audit write *after* the upstream
    call, where "nothing was sent" would be false; STORY-010 owns that arm via
    `AuditUnavailableError`).
  - Update `ChatState`'s docstring line (`:158-160`, "three named exceptions") to say
    the gate faults use fixed copy when storage is unavailable (one clause, cite PRD-018 6.7).
- **Validate**: Task 6's cause tests; existing `tests/test_chat_state.py:437-471` (plain
  `DuplicateCheckError("db locked")` / `UsageLimitError(...)`, no cause) must still show
  `str(exc)`: they are the "non-transient keeps today's bubble" pins and are not edited.

### Task 6: Tests

- **File**: `tests/test_chat_ui_storage_failures.py`
- **Action**: CREATE (non-`db`: no `temp_db`, no storage access; every storage seam is stubbed)
- **Implement**: module docstring citing PRD-018 STORY-007, Section 6.7, T9 and the Section 11 `pending` criterion. `os.environ.setdefault` for `OPENROUTER_API_KEY` / `ADMIN_TOKEN` as `tests/test_chat_state.py:7-8`. Local `_make_state` / `_send` copies of `tests/test_chat_state.py:121-132` (do not import private helpers across test modules). Stubs:
  - `_raise(exc)` returning a function that raises it; `monkeypatch.setattr(chat_state_mod, "resolve", ...)`.
  - For pipeline-cause tests: `resolve` stub returns `Identity(user_id="u@example.com", role="user")`; `monkeypatch.setattr(chat_sessions, "create", lambda *a, **k: None)` (the lazy create, so no write and `session_id=None`); `monkeypatch.setattr(chat_state_mod, "run_in_pipeline", fake)` where `async def fake(fn, *a, **k): raise exc`. With `session_id` empty the send takes the `run_query` branch and never reads history.
  - Build caused errors with `raise X("... Hrana: stream expired") from StorageUnavailableError("Hrana: stream expired", retry_after_seconds=3)` inside a helper so `__cause__` is set (or set `exc.__cause__` explicitly).
  - Every `pytest.mark.asyncio`.

  Tests:
  1. `test_send_storage_unavailable_in_resolve_unlocks_the_composer` (**AC 1, AC 5 pin**): `resolve` raises `StorageUnavailableError("Hrana: STREAM_EXPIRED", retry_after_seconds=2)`. After `_send`: `pending is False`; exactly one message; `kind == content == "internal_error"`; `detail == STORAGE_UNAVAILABLE_NOT_SENT_NOTICE`; `prompt == text`; `"Hrana" not in detail`; the pipeline stub (`run_in_pipeline` set to a fail-if-called) was never called; `input_text` still holds the text.
  2. `test_send_plain_storage_error_in_resolve_uses_the_same_bubble` (AC 1, "StorageError including"): `resolve` raises `StorageError("Hrana: SQL_PARSE_ERROR")`; same assertions on `pending` and `detail`.
  3. `test_send_after_a_resolve_failure_can_send_again` : first send fails as in 1, then `resolve` returns an Identity and the pipeline returns a `QuerySuccessResponse`; the second send produces an `assistant` bubble (composer usable, `pending is False`).
  4. `test_send_resolves_off_the_event_loop`: record `asyncio.to_thread` calls (mirror `tests/test_chat_state.py:1195-1201`) and assert `chat_state_mod.resolve` (the stub) was offloaded.
  5. `test_login_storage_unavailable_shows_the_storage_notice` (**AC 2**): parametrize over `StorageUnavailableError(..., retry_after_seconds=1)` and `StorageError(...)`. After `await state.login()`: `login_error == LOGIN_STORAGE_UNAVAILABLE_ERROR`, `!= LOGIN_INVALID_TOKEN_ERROR`, `user_id == ""`, `_token == ""`, `sessions == []`, and `token_input` is unchanged.
  6. `test_login_resolves_off_the_event_loop`: same recording pattern, `resolve` stub returns `None` (so nothing else runs); assert it was offloaded.
  7. `test_gate_fault_caused_by_an_outage_shows_fixed_copy` (**AC 3**): parametrize `DuplicateCheckError`, `UsageLimitError`, `ChatSessionError`, each raised `from StorageUnavailableError(...)` with "Hrana" in both messages. Assert `kind == "internal_error"`, `detail == STORAGE_UNAVAILABLE_NOT_SENT_NOTICE`, `"Hrana" not in detail`, `pending is False`.
  8. `test_gate_fault_with_a_non_transient_cause_keeps_todays_detail` (**AC 3, second sentence**): same three types raised `from StorageError("Hrana: SQL_PARSE_ERROR")` (statement class) and with no cause; `detail == str(exc)`.
  9. `test_pii_redactor_error_is_not_a_storage_gate`: `PiiRedactorError("x")` raised `from StorageUnavailableError(...)` keeps `detail == "x"` (the rule applies to the `/query` set only, PRD 6.7).

- **File**: `tests/test_copy.py`
- **Action**: UPDATE (import the two constants with a `# PRD-018 STORY-007` comment, like `:36-46`)
- **Implement**: `test_storage_unavailable_copy_names_the_outage_and_not_the_credential` (**AC 4**): both non-empty; sentence case and final "."; contain "unavailable"; the bubble one contains "nothing was sent"; neither contains "invalid", "token is", "hrana", "storageerror", "exception", "sql" or an apology word; `LOGIN_STORAGE_UNAVAILABLE_ERROR != LOGIN_INVALID_TOKEN_ERROR`; both are ASCII-letters English (`text.isascii()`). Docstring cites PRD-018 Section 6.7 and frontend-design's "errors don't apologize" rule. "database" is **allowed** here (the PRD fixed the wording), unlike `test_transcript_notices_name_the_saving_and_never_the_answer` (`:715-738`); say so in the docstring.
- **Validate**: Task 7.

### Task 7: Targeted regression run (per brief; no full suite)

One pytest process, `PYTHONUTF8=1`:

```bash
PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_chat_ui_storage_failures.py tests/test_copy.py tests/test_chat_state.py tests/test_chat_ui_startup_guard.py tests/test_chat_components_import.py tests/test_chat_outcomes_regression.py -q
```

`tests/test_chat_state.py` and `tests/test_chat_outcomes_regression.py` are `db` (need
`harness-libsql-dev` on :8080). `tests/test_chat_ui_startup_guard.py` is the brief's
chat_ui probe rule. Record exact pass/fail/skip counts. Then
`.venv/Scripts/python -c "from app.main import app; print('OK')"`.
Full suite: GitHub CI on push (user decision).

---

## End-to-End Tests

- [ ] New non-`db` tests prove: resolve failure (both `StorageError` kinds) gives the fixed bubble and `pending == False`; a second send works; sign-in shows the storage notice and stays signed out; gate faults caused by an outage show fixed copy; other causes keep `str(exc)`.
- [ ] Existing `tests/test_chat_state.py` send/login/offload/append-guard tests pass unchanged.
- [ ] `tests/test_chat_ui_startup_guard.py` (chat_ui import probe) passes.
- [ ] Optional manual check (not required): `docker pause harness-libsql-dev`, run the chat UI, sign in → storage notice; unpause. If done, leave the container **running and unpaused**.

---

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_chat_ui_storage_failures.py tests/test_copy.py tests/test_chat_state.py tests/test_chat_ui_startup_guard.py tests/test_chat_components_import.py tests/test_chat_outcomes_regression.py -q
```

---

## Risks / open points

1. **Catch-all arm left as is (T9 gap, reported to the orchestrator).** In the chat path
   a bare `StorageUnavailableError` / `StorageError` from the audit write (`log_query`,
   `app/services/query_pipeline.py:893`) escapes `run_query` *after* the upstream call
   and lands in `except Exception` (`state.py:1187-1197`) with `detail=str(exc)`, which
   can carry driver text. Applying "nothing was sent" there would be false. PRD 6.7
   gives that case to STORY-010 ("Row neither written nor journaled
   (`AuditUnavailableError`) → `internal_error` bubble"), so this story does not
   change it. If the orchestrator wants it closed now, the minimal change is a
   second fixed string without "nothing was sent" for `isinstance(exc, StorageError)`
   in the catch-all.
2. **Four other inline `resolve()` calls** (`state.py:451`, `:624`, `:689`, `:760`) stay
   on the event loop and unguarded. They cannot lock the composer. Follow-up candidate.
3. **A plain statement-class `StorageError` in `resolve()` now shows "unavailable"**,
   per AC 1 / AC 2 wording. Its cause is only visible as a type-name log line; the
   unit of work does not log statement failures. Acceptable: the identity read is a
   single fixed `SELECT`, so a statement failure there is a deployment defect, not a
   user one.
4. `asyncio.to_thread` adds a thread hop to every sign-in and send (~sub-ms). Accepted
   for the reason in the Decision section.
5. Import of `StorageError` from `app.db.errors` into `chat_ui/state.py`: the exception
   surface, not a driver (PRD-007 7.2); precedent `app/middleware/auth.py:8`.

---

## Acceptance Criteria

(Copied from story `STORY-007`)

- [ ] `_do_send`: `resolve(token)` raising `StorageError` (incl. `StorageUnavailableError`) → `internal_error` bubble with fixed copy, `pending == False`; `resolve()` now inside the `try`/`finally` (Task 4; tests 1-3)
- [ ] `login`: `resolve()` raising `StorageError` → `login_error` is the storage notice, not "invalid token"; not signed in (Task 3; test 5)
- [ ] `DuplicateCheckError` / `UsageLimitError` / `ChatSessionError` caused by `StorageUnavailableError` → fixed copy, no driver text; non-transient causes keep today's bubble (Task 5; tests 7-9 and `tests/test_chat_state.py:437-471` unchanged)
- [ ] New strings in `chat_ui/chat_ui/copy.py` beside the existing notices, in English (Task 1; `tests/test_copy.py` new test)
- [ ] Chat UI tests and `tests/test_chat_ui_startup_guard.py` pass; a new test pins `pending == False` after a `resolve()` storage failure (Task 7; test 1)
- [ ] All tasks completed
- [ ] Backend imports without error (`from app.main import app`)
- [ ] Follows existing patterns
