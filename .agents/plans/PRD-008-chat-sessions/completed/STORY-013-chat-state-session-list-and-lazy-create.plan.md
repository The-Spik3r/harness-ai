---
story: STORY-013
prd: PRD-008
slug: chat-state-session-list-and-lazy-create
title: "ChatState holds the session list, creates lazily on first send, and passes session_id to run_query"
type: NEW_CAPABILITY
complexity: HIGH
epic_branch: epic/PRD-008-chat-sessions
created: 2026-09-04
---

# Plan: ChatState holds the session list, creates lazily on first send, and passes session_id to run_query

## Summary

`ChatState` gains the concept of *which conversation this send belongs to*. Three vars (`sessions`, `active_session_id`, `sessions_error`), a session-list read at sign-in, a lazy `chat_sessions.create(...)` on the first send only, and `session_id=` on the existing `run_query(...)` call. Nothing is rendered, no transcript row is written, and no row is read back — [[STORY-014]] and [[STORY-015]] own those, and keeping them out is what makes this diff reviewable as "the send now has an address".

Two structural decisions carry the story, and both were verified against the pinned Reflex tree rather than recalled.

**`login()` becomes `async`.** AC 2 requires that *"when `login()` completes... the rail's data is in state"*, with the read offloaded through `asyncio.to_thread(...)`. A background event cannot deliver that — `reflex/state.py:102-133` installs `_no_chain_background_task`, so a background handler cannot be called from another handler at all, only returned as a follow-up event, and a follow-up event completes *after* `login()` does. A plain `async` handler is the one shape that satisfies the AC: `reflex/app.py:1427-1429` holds the exclusive state lock across the whole handler ("No other event handler can modify the state while in this context"), and `reflex/istate/proxy.py:38-52` confirms the `StateProxy` — and therefore the `async with self` requirement — is installed **only** for background tasks. So `login()` awaits the offloaded read and mutates `self` directly, with no `async with self`. `_do_send` is unchanged in this respect: it *is* a background context, so every new mutation there stays inside `async with self` and every new database call stays outside it.

**The lazy create sits between the user bubble and the pipeline call.** It goes inside the existing `try:` at `state.py:138`, so the `finally` at `:250-252` that PRD-004 Risk 3 exists to protect still clears `pending` on the new failure path — that is AC 9, and it is satisfied by placement rather than by a second `try`. It goes *after* the bubble append at `:139-154` so a slow or failing create never leaves the user's own text off screen, and *before* `run_query` at `:156` so `active_session_id` is set when the audit row is written.

Three things follow from the service's contract and need no branching in this class. History off makes `create(...)` return `None` and `list_for(...)` return `[]`, so the flag-off AC (AC 7) is met by *not* writing code — `tests/test_chat_sessions.py:1281` fails the build on a `CHAT_HISTORY_ENABLED` reference anywhere outside `config.py` and the service, so the absence is enforced, not merely intended. `ChatSessionError` is caught around the create and degrades to `session_id = None`, so the send proceeds (AC 8). And `active_session_id` is a `str` var whose empty value must reach `run_query` as `None`, never as `""`, or every pre-session audit row would carry an empty-string conversation id.

## User Story

As an employee
I want to keep separate conversations for separate subjects
So that starting a new line of enquiry does not bury the previous one.

## Story Reference

- Story file: `.agents/stories/PRD-008-chat-sessions/STORY-013-chat-state-session-list-and-lazy-create.md`
- PRD: `.agents/PRDs/PRD-008-chat-sessions/PRD.md` — Section 4 (Chat state), Section 5 (story 2), Section 6 (send path, Design patterns), Section 12 Phase 3, Risk 3

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | HIGH |
| Systems Affected | `chat_ui/chat_ui/state.py`, `tests/test_chat_state.py`, `tests/test_rbac.py` |
| Story | STORY-013 |
| PRD | PRD-008 |
| Epic Branch | `epic/PRD-008-chat-sessions` (commit directly on this branch) |
| Depends on | STORY-006 ✅, STORY-009 ✅, STORY-012 ✅ (all verified `status: done`) |
| Blocks | STORY-014, STORY-016, STORY-018 |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| `reflex-docs` (plugin, named in story frontmatter) | `chat_ui/AGENTS.md`, verbatim: *"For anything about Reflex APIs — components, state management, events, styling, database, routing, authentication — use the **reflex-docs** skill rather than relying on memory."* Governs the `login()` async decision, the background-task chaining rule, and the `async with self` boundary in `_do_send`. | Tasks 2, 3 |
| `reflex-process-management` (plugin, named in story frontmatter) | `chat_ui/AGENTS.md`, verbatim: *"When you need to compile, run, reload, or debug a Reflex application, follow the **reflex-process-management** skill for the correct sequence and error investigation steps."* Its first step is `reflex compile --dry`, run from `chat_ui/`. | Task 7, Validation |
| `.agents/skills/frontend-design` | Listed and read in full. Scoped to *"distinctive, intentional visual design when building new UI"*. **This story renders nothing** — the story's own Technical Notes say so, and this plan confirms it independently: no component file is touched and no copy constant is added. Its rules land in STORY-017/018. | None |

`.agents/skills/` was listed and holds exactly one skill (`frontend-design`); its `description` was read and does not match this story's domain.

### `reflex-docs` outcome — the three API facts this plan depends on

Verified against the installed `reflex==0.9.6.post1` tree, not recalled:

| Fact | Evidence |
|---|---|
| A background task cannot be invoked directly from another handler; it must be returned or yielded as an event. | `reflex/state.py:102-133` `_no_chain_background_task`, and `reflex/state.py:1456-1457` which installs it. This is also why `tests/test_chat_state.py:93-96` reaches for `type(state).event_handlers["send"].fn(state)`. |
| A **non-background** async handler holds the exclusive state lock for its entire duration, including across `await`, and receives the real state as `self`. | `reflex/app.py:1427-1429`: *"Get exclusive access to the state... No other event handler can modify the state while in this context."* |
| `async with self` is a **background-task-only** requirement. | `reflex/istate/proxy.py:38-52`: *"A background task will be passed the `StateProxy` as `self`, so mutability can be safely performed inside an `async with self` block."* `StateProxy` is constructed nowhere else in the tree. |

---

## Patterns to Follow

### Offloading a blocking call and mutating under the lock — the shape `_do_send` already has

Every database-bound call leaves the event loop; every mutation happens inside `async with self`. Both rules are already load-bearing here, and the new create must obey both.

```python
# SOURCE: chat_ui/chat_ui/state.py:139-165
            async with self:
                self.messages.append(
                    ChatMessage(kind="user", content=text, prompt=text)
                )
                self.input_text = ""
                model = self.selected_model
                ...
            try:
                result = await asyncio.to_thread(
                    run_query,
                    identity=identity,
                    prompt=text,
                    device=device,
                    model=model,
                    openrouter_api_key=None,
                    call_openrouter=call_openrouter,
                )
```

Note the read-under-lock-into-a-local idiom (`model = self.selected_model`): state is read inside the block and used outside it. `active_session_id` is captured the same way, in the same block.

### The `pending` guard that must survive a new failure mode

```python
# SOURCE: chat_ui/chat_ui/state.py:107-119, 250-252
    async def _do_send(self, text: str):
        # Claim the in-flight slot first and on its own, so everything that can
        # raise afterwards is inside the try/finally that clears `pending`
        # (PRD-004 Risk 3: a stuck flag locks the composer permanently).
        async with self:
            ...
            self.pending = True
        ...
        finally:
            async with self:
                self.pending = False
```

AC 9 is met by putting the create **inside** the `try` that this `finally` closes. No new `try/finally` is introduced.

### Error into a `*_error` string var — the `login_error` discipline

`sessions_error` follows `login_error`: written only where the failure happens, cleared on the success path of the same operation.

```python
# SOURCE: chat_ui/chat_ui/state.py:71-86
    @rx.event
    def login(self):
        token = self.token_input.strip()
        if not token:
            self.login_error = LOGIN_TOKEN_REQUIRED_ERROR
            return
        identity = resolve(token)
        if identity is None:
            self.login_error = LOGIN_INVALID_TOKEN_ERROR
            return
        self.login_error = ""
        ...
```

The message stored is `str(exc)`, matching how `_do_send` already carries a caught exception's text (`detail=str(exc)`, `state.py:173`). It is deliberately **not** a `copy.py` constant: `copy.py:109` reserves the rail's own strings for STORY-017, and inventing one here would pre-empt that story's decision about how a failed rail reads.

### The service contract — the caller never branches on the flag

```python
# SOURCE: app/services/chat_sessions.py:119-123
    if not settings.CHAT_HISTORY_ENABLED:
        return None

    with _wrapped("create"):
        return database.create_chat_session(identity.user_id, derive_title(first_prompt))
```

and its docstring, verbatim: *"STORY-013's lazy-create arm reads it as 'there is no session to record against' and sends the turn anyway."* `derive_title` is undefaulted, so `formatting.derive_title` is passed explicitly.

### Tests — driving the state directly, past the background-task guard

```python
# SOURCE: tests/test_chat_state.py:86-96
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
# SOURCE: tests/test_chat_state.py:252-258 -- the fake whose signature must grow
    def _fake_run_query(identity, prompt, device, model, openrouter_api_key, call_openrouter):
        ...
    monkeypatch.setattr(chat_state_mod, "run_query", _fake_run_query)
```

```python
# SOURCE: tests/test_chat_sessions.py:1186-1195 -- how the flag is turned off in a test
@pytest.fixture
def history_off(monkeypatch):
    monkeypatch.setattr(settings, "CHAT_HISTORY_ENABLED", False)
    monkeypatch.setattr(chat_sessions, "database", _Tripwire())
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `chat_ui/chat_ui/state.py` | UPDATE | The three vars, the async `login()` session load, the lazy create in `_do_send`, and `session_id=` on the `run_query` call. |
| `tests/test_chat_state.py` | UPDATE | Six `_fake_run_query` signatures absorb `session_id`; five `login` tests become async; the new AC assertions. |
| `tests/test_rbac.py` | UPDATE | **One** `_fake_run_query` signature at `:311`. Signature only — no assertion changes. See **Deviations**. |

No new file. No component, copy or theme file is touched.

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Imports and the three state vars

- **File**: `chat_ui/chat_ui/state.py`
- **Action**: UPDATE
- **Implement**:
  - Add `from app.services import chat_sessions` and `from app.services.chat_sessions import ChatSessionError` to the `app.services` import block (`:10-14`), keeping its alphabetical order — `chat_sessions` sorts before `duplicate_checker`.
  - Extend `from .models import ChatMessage` (`:15`) to `ChatMessage, ChatSessionSummary`.
  - Extend `from .formatting import format_duplicate_info` (`:21`) to also import `derive_title` and `format_activity`.
  - Add `from datetime import datetime, timezone` for the single shared clock read (Task 2).
  - Declare the three vars after `selected_model` (`:51`) and **above** the `_token` blank-line group, so the backend-only var keeps its visual isolation:
    ```python
    sessions: list[ChatSessionSummary] = []
    active_session_id: str = ""
    sessions_error: str = ""
    ```
  - Add a fourth paragraph to the class docstring recording, in the file's own voice, that `active_session_id` is client-visible **on purpose** (PRD Risk 3) — the rail must render which row is active — and that this is safe only because `app/services/chat_sessions.py` re-checks ownership against a freshly resolved Identity on every read, never against the var. Reference STORY-010's 403 as the API-side half of the same rule.
- **Mirror**: `chat_ui/chat_ui/state.py:45-53` (var block and its ordering); `state.py:35-42` (the docstring paragraph that already argues the analogous point for `_token`).
- **Do not**: import `app.db.database`, or reference `settings.CHAT_HISTORY_ENABLED`. Both are AST-guarded (`tests/test_chat_sessions.py:1158`, `:1281`).
- **Validate**: `python -c "import chat_ui.chat_ui.state; print('ok')"` and `python -m pytest tests/test_chat_sessions.py -q` (the two AST guards still pass).

### Task 2: `login()` becomes async and loads the session list

- **File**: `chat_ui/chat_ui/state.py`
- **Action**: UPDATE
- **Implement**:
  - Change `def login(self):` (`:72`) to `async def login(self):`. The `@rx.event` decorator is unchanged and `background=True` is **not** added — see the Summary for why.
  - The two early-return arms (`:74-81`) are untouched: an empty or invalid token still returns before any database contact, so the two login tests that run without a `temp_db` fixture keep working.
  - After `self.user_id = identity.user_id` (`:86`), append the load:
    ```python
    self.sessions_error = ""
    try:
        rows = await asyncio.to_thread(chat_sessions.list_for, identity)
    except ChatSessionError as exc:
        self.sessions = []
        self.sessions_error = str(exc)
    else:
        now = datetime.now(timezone.utc)
        self.sessions = [
            ChatSessionSummary(
                session_id=row.session_id,
                title=row.title,
                activity_info=format_activity(row.updated_at, now),
            )
            for row in rows
        ]
    ```
  - **One clock read for the whole list.** `format_activity`'s docstring gives the reason verbatim: *"a rail of thirty rows shares one clock read"*. `now` is hoisted out of the comprehension.
  - Mutations are direct on `self` with **no** `async with self`: this is a non-background handler holding the exclusive lock (evidence table above). Adding `async with self` here would deadlock.
  - `row.updated_at` is `Optional[str]` (`app/db/models.py:201`); `format_activity` guards it with `if not updated_at` (`formatting.py:170`), so `None` degrades to `SESSION_ACTIVITY_UNKNOWN` rather than raising.
- **Mirror**: `chat_ui/chat_ui/state.py:156-165` for the `asyncio.to_thread` call shape; `state.py:83` for clearing the error var on the success path.
- **Validate**: `python -m pytest tests/test_chat_state.py -q -k login` (after Task 5 converts those tests to async).

### Task 3: Lazy session creation in `_do_send`

- **File**: `chat_ui/chat_ui/state.py`
- **Action**: UPDATE
- **Implement**:
  - In the existing lock block at `:139-154`, alongside `model = self.selected_model`, capture `session_id = self.active_session_id`. Reading it here rather than later is the same discipline `model` already follows: a background task has no exclusive access outside the block.
  - Immediately after that block closes (i.e. after `:154`, before the `try:` at `:156`) and **inside** the outer `try:` opened at `:138`:
    ```python
            if not session_id:
                try:
                    session_id = await asyncio.to_thread(
                        chat_sessions.create, identity, text, derive_title
                    )
                except ChatSessionError as exc:
                    # A broken rail does not block the composer: the turn is
                    # sent unattached rather than refused. PRD Section 9's
                    # "the chat behaves exactly as it did before this PRD".
                    session_id = None
                    async with self:
                        self.sessions_error = str(exc)
                else:
                    if session_id:
                        async with self:
                            self.active_session_id = session_id
                            self.sessions_error = ""
    ```
  - `create` is positional (`identity, first_prompt, derive_title`) to match the service signature; `derive_title` is passed explicitly because the service defaults it on purpose (`chat_sessions.py:114-117`).
  - `text` at this point is already stripped (`:114`), so the auto-title derives from the same text the user's bubble shows.
  - The `if session_id:` guard inside the `else` is what makes the flag-off path work without branching on the flag: history off returns `None`, `active_session_id` stays `""`, and nothing is written.
  - Change the `run_query` call (`:157-165`) to add, as the last keyword argument:
    ```python
                    session_id=session_id or None,
    ```
    **`or None` is load-bearing.** `active_session_id` is a `str` var whose unset value is `""`; `run_query`/`log_query` take `Optional[str]`, and writing `""` would put an empty-string conversation id on every pre-session audit row instead of `NULL`.
- **Do not**: call `chat_sessions.touch(...)`, write any transcript row, or mutate `self.sessions` here. Those belong to [[STORY-014]] — see **Deviations** for the `sessions` decision and what STORY-014 must do about it.
- **Mirror**: `chat_ui/chat_ui/state.py:139-165`.
- **Verify placement afterwards**: the new code must sit between `state.py:154` and the `try:` at `:156`, i.e. inside the `try:` at `:138` and above the `finally:` at `:250`. Confirm with `sed -n '138,175p' chat_ui/chat_ui/state.py`.
- **Validate**: `python -c "import chat_ui.chat_ui.state; print('ok')"`.

### Task 4: Absorb `session_id` into the six existing `run_query` fakes in `tests/test_chat_state.py`

- **File**: `tests/test_chat_state.py`
- **Action**: UPDATE
- **Implement**: add a trailing `session_id=None` parameter to each `_fake_run_query` at lines **252, 277, 391, 654, 677, 704**. `asyncio.to_thread` forwards everything as keywords, so a defaulted trailing parameter is sufficient and keeps each fake's existing captures intact.
  ```python
  def _fake_run_query(identity, prompt, device, model, openrouter_api_key, call_openrouter, session_id=None):
  ```
  Do **not** switch them to `**kwargs`: the explicit list is what makes an accidentally-dropped argument fail here, which is the point of `test_chat_state_send_passes_resolved_identity_and_prompt_to_run_query` (`:385-406`).
- **Why this is mandatory**: without it, the new keyword raises `TypeError` inside the `try` at `:156`, which the bare `except Exception` at `:188` converts into an `internal_error` bubble — so these tests would fail *misleadingly*, as assertion errors about bubble kinds rather than as a signature mismatch.
- **Census safety**: no test function is renamed or removed, so `tests/test_untouched_app.py:test_no_test_was_removed_from_the_six_pinned_suites` (which pins `tests/test_chat_state.py` by name at `:77`) still passes. That guard is a census of test *names*, not byte equality.
- **Validate**: `python -m pytest tests/test_chat_state.py -q` — green except for the login tests, which Task 5 converts.

### Task 5: Convert the five `login` tests to async

- **File**: `tests/test_chat_state.py`
- **Action**: UPDATE
- **Implement**: `login()` is now a coroutine, so `state.login()` at lines **571, 584, 592, 601, 615** returns an un-awaited coroutine and the assertions that follow read unset state. Add `@pytest.mark.asyncio`, make each `def` an `async def`, and `await state.login()`. **Keep every test name byte-identical** (census). The affected tests:
  - `test_chat_state_login_empty_token_shows_error` (`:571`)
  - `test_chat_state_login_invalid_token_shows_error_and_stays_locked` (`:584`)
  - `test_chat_state_login_deactivated_token_rejected` (`:592`)
  - `test_chat_state_login_valid_token_sets_user_id_and_clears_error` (`:601`)
  - `test_chat_state_logout_clears_session_and_credential` (`:615`)
- **Note**: these fail loudly rather than vacuously if missed — each asserts on `state.user_id` or `state.login_error`, which stay at their defaults when the coroutine is never awaited.
- **Validate**: `python -m pytest tests/test_chat_state.py -q` — fully green.

### Task 6: The new state-level tests

- **File**: `tests/test_chat_state.py`
- **Action**: UPDATE
- **Implement**: a new section banner (matching the `# ---` style at `:99-101`, `:183-185`, `:408-410`, `:780-784`) reading `# --- Session list and lazy creation (STORY-013) ---`, then the assertions below. Each docstring cites its AC number, per the suite's convention. Use `_make_state`/`_send` (`:86-96`) and, for direct database inspection, the `list_chat_sessions` / `count_chat_sessions` functions via `app.db.database` — **in the test file only**; the AST guards scan `app/` and `chat_ui/`, not `tests/`.

  | # | Test | Asserts (AC) |
  |---|---|---|
  | 1 | `test_chat_state_declares_the_three_session_vars` | AC 1 — `sessions`, `active_session_id`, `sessions_error` present in `ChatState.__annotations__` with the right types. Mirrors `test_chat_state_holds_no_token_or_role_var` (`:294-301`). |
  | 2 | `test_login_loads_the_session_list_into_state` | AC 2 — seed two sessions for the user, `await state.login()`, assert `state.sessions` has both, newest first, each with a non-empty `title` and `activity_info`. |
  | 3 | `test_login_offloads_the_session_read_to_a_thread` | AC 2's second half — patch `chat_state_mod.asyncio.to_thread` with a recording wrapper (the idiom at `:535-541`) and assert `chat_sessions.list_for` was the function passed to it. |
  | 4 | `test_an_idle_mount_creates_no_session_row` | AC 3 — build the state, `await state.login()`, send nothing, assert `count_chat_sessions(user_id) == 0`. The PRD's *"an opened-and-abandoned tab leaves nothing behind"*. |
  | 5 | `test_first_send_creates_exactly_one_session_titled_from_the_prompt` | AC 4 — one send, `count == 1`, the row's `title` equals `derive_title(prompt)`, and `state.active_session_id` equals the row's id. |
  | 6 | `test_active_session_id_is_set_before_run_query_is_called` | AC 4's ordering half — the fake `run_query` records `session_id`; assert it is non-empty and equal to the created row's id. This is the assertion that would catch a create placed *after* the call. |
  | 7 | `test_second_send_reuses_the_session_and_creates_no_second_row` | AC 5 — two sends, `count == 1`, `active_session_id` unchanged across both. |
  | 8 | `test_run_query_receives_the_active_session_id_on_every_outcome` | AC 6 — parametrized over success, duplicate, injection and forbidden results; each fake records `session_id` and each asserts it is the active id. Covers STORY-009's blocked arms. |
  | 9 | `test_history_off_creates_no_session_and_passes_none_to_run_query` | AC 7 — `monkeypatch.setattr(settings, "CHAT_HISTORY_ENABLED", False)` (the fixture shape at `test_chat_sessions.py:1186`), then assert `count == 0`, `state.active_session_id == ""`, the recorded `session_id is None`, and the assistant bubble is still appended. |
  | 10 | `test_a_session_error_while_creating_sets_the_error_and_still_sends` | AC 8 — patch `chat_state_mod.chat_sessions.create` to raise `ChatSessionError`; assert `state.sessions_error` is non-empty, the assistant bubble is present, and the recorded `session_id is None`. |
  | 11 | `test_a_session_error_while_loading_sets_the_error_and_still_signs_in` | AC 8's load half — patch `list_for` to raise; assert `state.user_id` is set, `state.sessions == []`, `state.sessions_error` non-empty. |
  | 12 | `test_pending_clears_when_session_creation_raises` | AC 9 — the new failure mode against PRD-004 Risk 3. `state.pending is False` after the failing send. |

- **Do not** add a test for logout clearing the new vars — that is STORY-016's AC, and `test_logout_clears_the_transcript` (`:764`) is left as it is.
- **Mirror**: `tests/test_chat_state.py:246-267` (fake-and-capture), `:498-530` (parametrized outcomes), `:532-555` (patching `to_thread`).
- **Validate**: `python -m pytest tests/test_chat_state.py -q`.

### Task 7: The one signature fix in `tests/test_rbac.py`

- **File**: `tests/test_rbac.py`
- **Action**: UPDATE
- **Implement**: add `session_id=None` to the `_fake_run_query` signature at `:311`, inside `test_chat_state_never_forwards_a_byok_key_so_query_byok_has_no_chat_ingress`. **Signature only.** The test's premise — that `ChatState` hardcodes `openrouter_api_key=None` — and both of its assertions are untouched.
- **Why it cannot be avoided**: this is the only test outside `tests/test_chat_state.py` that patches `chat_state_mod.run_query` and drives a send. PRD Section 11 lists `tests/test_rbac.py` among the suites that must pass *unmodified*; this plan cannot honour that line literally and also add a keyword argument to the call the fake stands in for. Recorded under **Deviations** rather than done quietly.
- **Guard check**: `tests/test_rbac.py` is **not** in `test_untouched_app.py`'s `_UNMODIFIED_SUITES` (`:71-78`) — that census covers six suites, and this is not one of them. No automated guard is tripped; only the PRD's prose, which the deviation table answers.
- **Validate**: `python -m pytest tests/test_rbac.py -q`.

### Task 8: Compile the Reflex app

- **File**: —
- **Action**: VERIFY
- **Implement**: per the **reflex-process-management** skill, whose first step is the dry compile. Run from `chat_ui/`, since that is where `rxconfig.py` lives.
- **Validate**: `cd chat_ui && reflex compile --dry` → "App compiled successfully". If it fails, read the traceback rather than guessing; the skill's investigation step is to read `reflex.log`, which only exists once the server has been run.

---

## End-to-End Tests

- [ ] `cd chat_ui && reflex compile --dry` → compiles, no new warnings.
- [ ] Sign in with a seeded token → `ChatState.sessions` is populated from the database and `sessions_error` is empty (state-level, Task 6 test 2).
- [ ] Sign in and send nothing → `count_chat_sessions(user_id)` is `0` (Task 6 test 4). This is the PRD's headline behavioural claim and the one most easily regressed.
- [ ] First send → exactly one `chat_sessions` row, titled from the prompt; its `session_id` reaches the `audit_logs` row for that send (join the audit row written by the real pipeline, not a fake).
- [ ] Second send in the same state → still exactly one row.
- [ ] `CHAT_HISTORY_ENABLED=false` → zero rows, `active_session_id == ""`, the audit row's `session_id` is `NULL`, and the assistant bubble is unchanged.
- [ ] `chat_sessions.create` patched to raise → the assistant bubble is present, `sessions_error` is set, `pending` is `False`.
- [ ] A live boot (`reflex run --env prod --single-port`, per the skill) reaches the chat page and a send completes — the gate's `on_submit=ChatState.login` (`components/shell.py:273`) still fires now that the handler is a coroutine.

## Validation

```bash
# The story's own suite, and the one other suite that drives a chat send
python -m pytest tests/test_chat_state.py tests/test_rbac.py -q

# The service's structural guards -- the two AST walks over app/ and chat_ui/
python -m pytest tests/test_chat_sessions.py tests/test_session_ownership.py -q

# The census that pins tests/test_chat_state.py by name
python -m pytest tests/test_untouched_app.py -q

# The chat still imports and its components still build
python -c "import chat_ui.chat_ui.state; print('ok')"
python -m pytest tests/test_chat_components_import.py tests/test_render_invariants.py -q

# The Reflex app compiles (reflex-process-management, step 1)
cd chat_ui && reflex compile --dry && cd ..

# Full suite before the commit
python -m pytest -q
```

---

## Deviations

| PRD / story says | Plan does | Why |
|---|---|---|
| PRD Section 11: `tests/test_rbac.py` passes **unmodified** | One parameter added to a test double at `tests/test_rbac.py:311` | It is the only test outside `test_chat_state.py` that patches `chat_state_mod.run_query` and drives a send, and its fake has a closed positional signature. Adding `session_id=` to the call — which AC 6 requires — makes that fake raise `TypeError`. No assertion, name or premise changes, so the suite's *meaning* is unmodified even though its bytes are not. `tests/test_rbac.py` is not in `test_untouched_app.py`'s census, so nothing automated is being worked around. |
| Story AC 4 implies the rail gains the new chat | `self.sessions` is **not** mutated in `_do_send` | `chat_sessions.create(...)` returns only a `session_id` — no `ChatSession`, and therefore no `updated_at`. Inserting a rail row would mean either a second read (`get(...)`) or synthesizing a timestamp so `format_activity` reads "just now"; both are beyond this story's ACs, which never mention `sessions` in the send path. **STORY-014 must reconcile this**: its AC says *"the in-state `sessions` list reorders so the active chat is first"*, and with the new row absent from `sessions`, that story must re-read the list after `touch(...)` rather than reorder in place. Flagged so it is a decision that story inherits, not a bug it discovers. |
| PRD Section 4: *"`logout()` clears session state as it clears `messages` today"* | `logout()` is left untouched | STORY-016 owns it explicitly — its AC 8 names `sessions`, `active_session_id` and `sessions_error` by name and asserts row counts across the logout. Doing it here would take an assertion out of that story. See **Risks** for the interim exposure. |
| Story: *"`ChatState` ... never `app/db/database.py` directly"* | Honoured in `chat_ui/`; the **tests** call `database.count_chat_sessions` directly | The AST guard at `tests/test_chat_sessions.py:1158` scans `app/` and `chat_ui/` only. Asserting "no row exists" through the service would be asserting the service against itself; AC 3 says *"when the database is inspected"*. |

---

## Risks

| Risk | Mitigation |
|---|---|
| `login()` becoming a coroutine silently breaks a caller that is not a Reflex event trigger. | Only two call sites exist: `components/shell.py:273` (`on_submit=ChatState.login`, which Reflex awaits like any async handler) and the five tests in Task 5. Both were enumerated by grep, not assumed. The tests fail loudly rather than vacuously — each asserts on state that stays at its default when the coroutine is dropped. |
| Someone "fixes" the `async with self` asymmetry — adding one to `login()`, or removing one from `_do_send`. | The docstring paragraph in Task 1 and the evidence table in **Skills In Use** record which handler is which and why. Adding `async with self` to `login()` deadlocks (it already holds the lock); removing one from `_do_send` raises `ImmutableStateError`. Both fail immediately rather than subtly. |
| `session_id=session_id or None` is simplified to `session_id=session_id`, putting `""` on pre-session audit rows. | Task 6 test 9 asserts the recorded value `is None` — identity, not falsiness — on the flag-off path, so the empty string fails it. The inline comment in Task 3 states the reason at the call site. |
| A create placed after `run_query` would still pass most tests — the row exists, the count is right, only the audit row is wrong. | Task 6 test 6 asserts on the value `run_query` actually *received*, which is the only assertion that distinguishes the two orderings. |
| The new `ChatSessionError` arm sits outside a `try/finally` and leaves `pending` stuck, re-opening PRD-004 Risk 3. | The create goes inside the existing `try:` at `state.py:138`; no second `try/finally` is introduced. Task 3 carries an explicit placement check, and Task 6 test 12 asserts `pending is False` after a raising create. |
| Between this story and STORY-016, a logout leaves the previous user's session titles in `state.sessions` — visible to the next sign-in on the same tab. | Bounded and understood: nothing renders `sessions` until STORY-018, so no title reaches a screen in the interim, and `login()` overwrites the list on every successful sign-in. Recorded here so STORY-016's logout clearing is understood as closing a real gap rather than as tidying. |
| `format_activity` is called once per row with a fresh `datetime.now()`, making a thirty-row rail read against thirty clocks. | `now` is hoisted above the comprehension in Task 2, which is what `format_activity`'s own docstring asks for: *"a rail of thirty rows shares one clock read"*. |

---

## Acceptance Criteria

(Copied from story `STORY-013`)

- [ ] Given `chat_ui/chat_ui/state.py`, when `ChatState` is read, then it declares `sessions: list[ChatSessionSummary]`, `active_session_id: str` and `sessions_error: str`.
- [ ] Given a successful sign-in, when `login()` completes, then the session list is loaded through `chat_sessions.list_for(identity)` and the rail's data is in state — with the read offloaded via `asyncio.to_thread(...)`.
- [ ] Given a user who opens the app and sends nothing, when the database is inspected, then **no `chat_sessions` row exists**.
- [ ] Given the first send in a new chat, when it runs, then exactly one session is created, titled from that prompt, and `active_session_id` is set before `run_query` is called.
- [ ] Given a second send in the same chat, when it runs, then **no** session is created and the existing `active_session_id` is reused.
- [ ] Given any send, when `run_query(...)` is invoked, then it receives `session_id=self.active_session_id` — so the audit row carries it on every outcome, including the blocked and failed ones from STORY-009.
- [ ] Given `settings.CHAT_HISTORY_ENABLED is False`, when a send runs, then no session is created, `active_session_id` stays empty, `run_query` receives `None`, and the send otherwise behaves exactly as it does today.
- [ ] Given a `ChatSessionError` while loading or creating, when it is raised, then `sessions_error` is set and **the send still proceeds** — a broken rail does not block the composer.
- [ ] Given the in-flight guard, when session creation is added, then the `pending` flag still clears on every path — the `try/finally` that PRD-004 Risk 3 exists to protect is not broken by the new failure mode.
- [ ] Given `tests/test_chat_state.py`, when it runs, then the existing assertions pass and new ones drive the state directly: one send creates one session, two sends create one, an idle mount creates none, and the flag-off path creates none.
- [ ] All tasks completed
- [ ] Backend server starts without error (`python -c "import chat_ui.chat_ui.state"` clean)
- [ ] `cd chat_ui && reflex compile --dry` succeeds
- [ ] Follows existing patterns
