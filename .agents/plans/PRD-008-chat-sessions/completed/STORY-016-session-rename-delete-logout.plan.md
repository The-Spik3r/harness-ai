---
story: STORY-016
prd: PRD-008
slug: session-rename-delete-logout
title: "New chat, rename, delete, and a logout that clears state without deleting rows"
type: NEW_CAPABILITY
complexity: MEDIUM
epic_branch: epic/PRD-008-chat-sessions
created: 2026-09-06
---

# Plan: New chat, rename, delete, and a logout that clears state without deleting rows

## Summary

`ChatState` can open a chat, send into it, restore it and switch between them. It cannot start a blank one, rename one, delete one, or let go of the list on sign-out. This story adds three event handlers — `new_chat()`, `rename_session(session_id, title)`, `delete_session(session_id)` — and three lines to `logout()`, plus the one string the delete flow says out loud. No store function and no service function is written: `chat_sessions.rename`, `chat_sessions.delete` and `chat_sessions.messages_for` already exist and already carry the ownership rule (`app/services/chat_sessions.py:206-259`, STORY-006). This story is the caller.

Four decisions carry it.

**`logout()` clears state; `delete_session()` deletes rows. The two must not touch each other's mechanism.** The story names this as "the destructive bug in this story's neighbourhood", and it is a real one: both handlers end with an empty transcript on screen, and a `logout()` that reached for `chat_sessions.delete` to "clean up" would destroy a user's history on every sign-out of a shared machine. `logout()` stays synchronous and calls no service at all — it assigns `""` and `[]`, and its inability to write is structural rather than remembered. The tests assert row counts *across* the logout, so the two are separated by an assertion and not only by a comment.

**`new_chat()` writes nothing, because writing nothing is what makes it correct.** STORY-013 made session creation lazy — "a session row is written on the first send, never on page load" (PRD Section 4) — and `_do_send` already creates on an empty `active_session_id` (`state.py:520-548`). So `new_chat()` is the act of emptying that var, and the next send does the rest. Clicking it ten times leaves ten times nothing in the database. Any implementation that calls `chat_sessions.create` here re-introduces the abandoned-tab row the lazy rule exists to prevent.

**Rename is not activity.** `database.rename_chat_session:1502-1508` refuses to bump `updated_at` and records the reason — "a rename that bumped the timestamp would reorder the rail and move the row the user was looking at while they were looking at it". The state layer's half of that contract is that the rail is rebuilt **in place**: the renamed row keeps its index and its `activity_info`, and nothing re-sorts. And nothing re-derives: `formatting.derive_title` is called exactly once, in `chat_sessions.create` (`chat_sessions.py:88-124`), so a rename that outlives the next send is a property of never calling it again — this plan adds no second call site.

**A delete that lands on the active chat must land somewhere real.** The rail is `ORDER BY updated_at DESC`, so after dropping the deleted row `self.sessions[0]` *is* the next most recent chat, and the transcript for it is read through the same `_read_transcript` helper `login()` and `select_session()` use. The failure arm is the one place this story departs from STORY-015's: `select_session` leaves the old transcript standing when a read fails, and here it cannot — the old transcript belongs to a session that no longer exists. So the failure arm clears `messages` and reports, which is AC 6's "never on a transcript belonging to a deleted id" taken literally.

## User Story

As an employee
I want to start a fresh chat, rename one, delete one I no longer want on screen, and sign out of a shared machine
So that the list stays mine — and signing out takes my transcripts off the screen without taking them out of my account.

## Story Reference

- Story file: `.agents/stories/PRD-008-chat-sessions/STORY-016-session-rename-delete-logout.md`
- PRD: `.agents/PRDs/PRD-008-chat-sessions/PRD.md` — Section 4 (Chat state), Section 5 (story 4), Section 6.1 (Copy), Section 9 (Deletion semantics), Section 11, Section 12 Phase 3

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | MEDIUM |
| Systems Affected | `chat_ui/chat_ui/state.py`, `chat_ui/chat_ui/copy.py`, `tests/test_chat_state.py`, `tests/test_copy.py` |
| Story | STORY-016 |
| PRD | PRD-008 |
| Epic Branch | `epic/PRD-008-chat-sessions` (commit directly on this branch) |
| Depends on | STORY-013 ✅ (`status: done`, commit `ba43c5c`), STORY-015 ✅ (`status: done`, commit `f096f2f`) |
| Blocks | STORY-018, STORY-021 |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| `reflex-docs` (plugin, named in the story's `skills:` frontmatter) | `chat_ui/AGENTS.md`, verbatim: *"For anything about Reflex APIs — components, state management, events, styling, database, routing, authentication — use the **reflex-docs** skill rather than relying on memory."* Governs the handler kind (plain async vs `background=True`) and the lock discipline of all three new handlers, and the one claim this plan makes about how STORY-018 will render the confirmation string. | Tasks 2, 3, 4 |
| `reflex-process-management` (plugin, in `chat_ui/AGENTS.md`) | Verbatim: *"When you need to compile, run, reload, or debug a Reflex application, follow the **reflex-process-management** skill for the correct sequence and error investigation steps."* Its first step is `reflex compile --dry` from `chat_ui/`. | Task 8, Validation |
| `.agents/skills/frontend-design` | `.agents/skills/` was listed; it holds exactly one skill and its `description` was read and matched. This story renders no component, so it applies to the copy only, under two rules quoted verbatim in the story: *"Write from the end user's side of the screen. Name things by what people control and recognize, never by how the system is built"* and *"An action keeps the same name through the whole flow, so the button that says 'Publish' produces a toast that says 'Published.'"* | Task 1 |

### `reflex-docs` outcome — the four API facts this plan depends on

The skill was invoked and directs to the reference documentation rather than to recall. Each fact below is stated from that documentation and then verified against the pinned tree in `.venv/` — the code that will actually run — because the published pages are thin on the lock semantics.

| Fact | Evidence |
|---|---|
| A background task must enter `async with self` to touch state, and **cannot be called from another event handler** — it has to be returned or yielded as a follow-up event. | Fetched `https://reflex.dev/docs/events/background-events/`: *"Whenever a background task needs to interact with the state, it must enter an `async with self` context block"*, and *"Background tasks cannot be directly invoked from other event handlers or background tasks... you must use `yield` or `return`."* This is the rule `login()`'s docstring already cites (`state.py:183-195`) as the reason STORY-013's session load lives inside `login()`. |
| A plain async handler holds the exclusive state lock for its entire duration, so `self` is the real state, mutations are direct, and `async with self` inside one deadlocks. Nesting the block is an explicit error in a background task. | The published page does not settle the plain-async half (it addresses background tasks only), so the pinned tree is authority: `.venv/Lib/site-packages/reflex/istate/proxy.py:132-137` raises `ImmutableStateError("The state is already mutable. Do not nest \`async with self\` blocks.")`. `state.py:183-195` and `:395-399` record both halves as settled practice in this file. **Consequence:** all three new handlers are plain (`@rx.event`), never `background=True`, and none of them opens `async with self`. |
| `rx.window_alert(message)` exists (`EventSpec`, one `str \| Var[str]` argument) and `rx.alert_dialog` exists with `root/trigger/content/title/description/action/cancel`. | `python -c "import reflex as rx; inspect.signature(rx.window_alert)"` against the pinned tree → `(message: str \| Var[str]) -> EventSpec`; `rx.alert_dialog` resolves to `reflex_components_radix.themes.components.alert_dialog.AlertDialog`. **Consequence:** neither is used here. `delete_session` performs the delete unconditionally; the confirmation is STORY-018's component, and a state handler that popped its own browser dialog would put half the flow in the wrong layer. |
| `"...{title}...".format(title=<Var>)` produces a Var-embedded string that Reflex resolves at render, exactly as an f-string does — so a single-placeholder template is renderable per row inside `rx.foreach`. | Executed against the pinned tree: both `tpl.format(title=S.title)` and `f"Delete {S.title}?"` return the same `<reflex.Var>…</reflex.Var>` marker form rather than raising. **Consequence:** the confirmation string is written as one template with one `{title}` placeholder — the shape `PII_BADGE_TEMPLATE` (`copy.py:74`) already uses — and STORY-018 can format it against a `rx.foreach` row without needing a computed var from this story. |

---

## Patterns to Follow

### The handler this story copies four times over — identity, offload, degraded arm

```python
# SOURCE: chat_ui/chat_ui/state.py:276-325 (select_session, STORY-015)
    @rx.event
    async def select_session(self, session_id: str):
        if self.pending:
            return

        identity = resolve(self._token)
        if identity is None:
            self.sessions_error = SESSION_INVALIDATED_ERROR
            return

        try:
            restored = await self._read_transcript(identity, session_id)
        except Exception:
            self.sessions_error = TRANSCRIPT_NOT_LOADED_NOTICE
            return

        self.messages = restored
        self.active_session_id = session_id
        self.sessions_error = ""
        self.transcript_error = ""
```

Every element of it recurs below: the `pending` guard, the fresh `resolve(self._token)` (never a cached role — PRD-005 Risk 5), the `asyncio.to_thread` offload inside the helper, direct mutation with no `async with self`, and the notice slot chosen for what actually failed.

### Rebuilding the rail without re-deriving anything

```python
# SOURCE: chat_ui/chat_ui/state.py:326-346 (_promote_session, STORY-014)
        remaining = [s for s in self.sessions if s.session_id != row.session_id]
        self.sessions = [
            ChatSessionSummary(
                session_id=row.session_id,
                title=row.title,
                activity_info=format_activity(row.updated_at, now),
            ),
            *remaining,
        ]
```

Its docstring carries the rule this story's rename inherits: *"The title in particular must not be re-derived here — `formatting.derive_title` is 'called exactly once per session'... so the rail shows the title that is stored."* Note the whole-list reassignment: a Reflex list var is replaced, not mutated in place.

### The service calls, and their deliberate `False`

```python
# SOURCE: app/services/chat_sessions.py:206-224
def rename(identity: Identity, session_id: str, title: str) -> bool:
    """Retitles this identity's session. `False` when there is no such owned row.

    `False` covers the unknown session and the foreign one without separating
    them... It is also what history-off returns, so a caller writes one
    `if not renamed:` arm and never learns which of the three it hit.
    """
```

```python
# SOURCE: app/services/chat_sessions.py:242-259
def delete(identity: Identity, session_id: str) -> bool:
    """Removes this identity's session and its transcript. `False` if not owned.
    ...
    `audit_logs` is untouched, by design (PRD Section 9): deleting a
    conversation deletes a conversation, it does not edit the record of what was
    asked.
    """
```

Three outcomes, one `False`, one arm. AC 10's "a foreign `session_id` changes nothing" is therefore the same code path as history-off, and neither needs a branch.

### The store's own record of what a rename must not do

```python
# SOURCE: app/db/database.py:1499-1520
def rename_chat_session(session_id: str, user_id: str, title: str) -> bool:
    """Retitles an owned session. False when there was no such owned row.

    **`updated_at` is deliberately not touched.** Renaming is not activity: a
    rename that bumped the timestamp would reorder the rail and move the row the
    user was looking at while they were looking at it. The omission is a
    decision, not an oversight.
    """
```

### Copy voice, and where a new constant goes

```python
# SOURCE: chat_ui/chat_ui/copy.py:105-113
# --- Session fallbacks ---------------------------------------------------
# The two strings a session row falls back to. Both are failures of the
# *input*, not of the reader, so neither apologizes and neither explains the
# mechanism... The rail's own strings are STORY-017's.
SESSION_UNTITLED_TITLE = "Untitled chat"
```

```python
# SOURCE: chat_ui/chat_ui/copy.py:74 (a one-placeholder template rendered per row)
PII_BADGE_TEMPLATE = "{count} PII types masked in this exchange: {entities}"
```

### Tests

```python
# SOURCE: tests/test_chat_state.py:105-118
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
# SOURCE: tests/test_chat_state.py:1643-1652 (the STORY-015 driver for a plain async handler)
async def _select(state: ChatState, session_id: str) -> None:
    handler = type(state).event_handlers["select_session"]
    await handler.fn(state, session_id)
```

```python
# SOURCE: tests/test_chat_state.py:76-80 (the row count this story asserts across a logout)
def _count_audit_rows() -> int:
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM audit_logs").fetchone()
        return row["n"]
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `chat_ui/chat_ui/copy.py` | UPDATE | The delete flow's two strings: the confirmation template and the confirming control's label. |
| `chat_ui/chat_ui/state.py` | UPDATE | `new_chat()`, `rename_session()`, `delete_session()`; three lines and a docstring in `logout()`; one line in `_read_transcript`'s docstring naming its third legal caller. |
| `tests/test_copy.py` | UPDATE | The new constants exist, are non-empty, carry `{title}`, and hold the voice rules. |
| `tests/test_chat_state.py` | UPDATE | The STORY-016 section: fourteen cases, including the row counts across logout. |

No file is created. No function is added to `app/` — `app/services/chat_sessions.py` and `app/db/database.py` are read, not modified.

## Dependency Order

1. Copy (Task 1) — `state.py` imports nothing from it for these handlers, but the delete flow's words are settled first so the handler docstrings can cite them.
2. `logout()` (Task 2) — the smallest change, and the one the other two must not resemble.
3. `new_chat()` (Task 3) — no I/O, no identity.
4. `rename_session()` (Task 4) and `delete_session()` (Task 5) — the two offloaded handlers; delete depends on `_read_transcript` (Task 6 updates its docstring).
5. Tests (Tasks 7, 8), then compile and full suite (Task 9).

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: The delete flow's copy

- **File**: `chat_ui/chat_ui/copy.py`
- **Action**: UPDATE
- **Implement**: Add a new `# --- Session deletion ---` block after the Session fallbacks block (after `:113`, before `# --- Transcript persistence ---` at `:115`):
  - `SESSION_DELETE_CONFIRM_TEMPLATE` — one `{title}` placeholder, naming the chat, stating that the conversation and its messages go and that **the record of what was checked is kept**. Per PRD Section 9 the fact must be told "in the user's words": no `audit_logs`, no "rows", no "table", no "database".
  - `SESSION_DELETE_CONFIRM_LABEL = "Delete"` — the confirming control. Per the story's verbatim quote of the **frontend-design** skill, *"an action keeps the same name through the whole flow"*: the affordance says Delete, the confirmation says Delete, and neither says Remove.
  - A comment above the block recording (a) that STORY-016 owns the delete flow's words and STORY-017 adds the remaining rail strings, so the two do not both write these, and (b) why the template is a single `{title}` placeholder: it is formatted per row in STORY-018's `rx.foreach`, the shape `PII_BADGE_TEMPLATE` already uses.
- **Mirror**: `chat_ui/chat_ui/copy.py:105-113` for the block shape and comment voice; `:74` for the template shape.
- **Constraints**: sentence case; no apology; no mechanism; the word `Delete` appears; `{title}` appears exactly once; the string must not claim anything is deleted from the record.
- **Validate**: `python -c "from chat_ui.chat_ui.copy import SESSION_DELETE_CONFIRM_TEMPLATE as t; print(t.format(title='Q3 vendor spend'))"`

### Task 2: `logout()` lets go of the rail — and of nothing in the database

- **File**: `chat_ui/chat_ui/state.py` (`:251-267`)
- **Action**: UPDATE
- **Implement**: Add `self.sessions = []`, `self.active_session_id = ""` and `self.sessions_error = ""` beside the existing clears. Replace the comment at `:262-266` that forward-references this story ("STORY-016 clears `sessions`, `active_session_id` and `sessions_error`") with the reason those three now clear here — extending the existing docstring's argument verbatim: the header names who is sending, and a session list is a list of one person's subjects, so leaving it under another user's ID misattributes it on a surface people read as a record. State explicitly, in the docstring, that this handler **calls no service and writes nothing**: `logout()` clears state, `delete_session()` deletes rows, and conflating them would destroy a user's history on every sign-out of a shared machine.
- **Mirror**: the existing docstring at `:252-255` — extend its argument, do not restate it.
- **Constraints**: stays `@rx.event` and **synchronous**. No `await`, no `asyncio.to_thread`, no `chat_sessions.*` call, no `resolve()`. `selected_model` stays untouched (`test_chat_state_model_selection:800` pins it). `messages`, `input_text`, `transcript_error`, `_token`, `user_id`, `token_input`, `login_error` keep their current clears.
- **Validate**: `python -m pytest tests/test_chat_state.py -q -k "logout"` — the three existing logout tests still pass.

### Task 3: `new_chat()` — the handler whose correctness is that it writes nothing

- **File**: `chat_ui/chat_ui/state.py` (immediately after `logout`, before `edit_and_resend` at `:270`)
- **Action**: UPDATE
- **Implement**: A synchronous `@rx.event def new_chat(self)` that returns early when `self.pending`, then sets `active_session_id = ""`, `messages = []`, `transcript_error = ""`. Docstring: no row is written and none should be — STORY-013 made creation lazy, `_do_send`'s `if not session_id:` arm (`:520`) is what will create the row on the first send, and calling `chat_sessions.create` here would re-introduce the abandoned-tab row PRD Section 4 refuses ("a session row is written on the first send, never on page load"). Record the two vars deliberately **not** touched and why: `sessions_error` is the rail's slot and a failed list read is still true after starting a new chat; `input_text` is the person's half-typed text and belongs to them rather than to the chat, which is the choice `select_session` already makes for the same reason. Record why `pending` is guarded: clearing `messages` under an in-flight send files that send's answer into a chat the user has left — the sharper half of `select_session`'s own guard (`:283-288`).
- **Mirror**: `chat_ui/chat_ui/state.py:270-275` (`edit_and_resend`) for the sync-handler-with-`pending`-guard shape.
- **Constraints**: no `await`, no service call, no `resolve()`. `transcript_error` clears because it is about the transcript being cleared on the line above — `logout`'s recorded reasoning for the same var.
- **Validate**: `python -c "import chat_ui.chat_ui.state as s; print('new_chat' in s.ChatState.event_handlers)"`

### Task 4: `rename_session(session_id, title)` — a retitle that does not move the row

- **File**: `chat_ui/chat_ui/state.py` (after `select_session`, before `_promote_session` at `:326`)
- **Action**: UPDATE
- **Implement**: A plain `@rx.event async def rename_session(self, session_id: str, title: str)`:
  1. `title = title.strip()`; `if not title: return` — refused before any identity work, before any I/O, and **silently**: an empty title is a slip in the input, not a fault of the system, and the existing title standing is the whole feedback. No new copy for it.
  2. `identity = resolve(self._token)`; `None` → `self.sessions_error = SESSION_INVALIDATED_ERROR` and return.
  3. `renamed = await asyncio.to_thread(chat_sessions.rename, identity, session_id, title)`, wrapped in `try/except ChatSessionError as exc: self.sessions_error = str(exc); return`.
  4. `if not renamed: return` — one arm for the foreign id, the unknown id and history-off alike (`chat_sessions.py:209-213`), and nothing mutates on it, which is AC 10 for rename.
  5. Rebuild `self.sessions` **in place**: a new list, same order, with the matching row replaced by a `ChatSessionSummary` carrying the new title and the **existing** `activity_info`. Then `self.sessions_error = ""`.
- **Mirror**: `state.py:276-325` for the handler shape; `state.py:335-345` for the list reassignment.
- **Constraints**: plain async, `@rx.event`, **no** `background=True`, **no** `async with self` (it would deadlock — see the reflex-docs table). Never calls `derive_title` — the rule at `chat_sessions.py:99-115`, so this plan adds no second call site. Never calls `chat_sessions.touch` and never writes an `activity_info` recomputed from a new clock: `updated_at` is not touched by the store and the rail must not pretend otherwise. Never re-sorts `self.sessions`. `title` is stored stripped, so " Q3 " and "Q3" are the same rename.
- **Validate**: `python -m pytest tests/test_chat_state.py -q` (green before its own tests land in Task 8)

### Task 5: `delete_session(session_id)` — rows go, and the screen lands somewhere real

- **File**: `chat_ui/chat_ui/state.py` (after `rename_session`)
- **Action**: UPDATE
- **Implement**: A plain `@rx.event async def delete_session(self, session_id: str)`:
  1. `if self.pending: return` — same reason as `new_chat`, and sharper: an in-flight send holds this `session_id` in a local and will try to append to it.
  2. `identity = resolve(self._token)`; `None` → `SESSION_INVALIDATED_ERROR`, return.
  3. `deleted = await asyncio.to_thread(chat_sessions.delete, identity, session_id)`, `except ChatSessionError as exc: self.sessions_error = str(exc); return`.
  4. `if not deleted: return` — foreign, unknown and history-off in one arm, nothing mutated (AC 10).
  5. `remaining = [s for s in self.sessions if s.session_id != session_id]`; assign `self.sessions = remaining`; `self.sessions_error = ""`.
  6. `if self.active_session_id != session_id: return` — deleting a chat the user is not looking at changes the rail and nothing else.
  7. Otherwise `self.transcript_error = ""` (it was about the transcript being replaced below), then: no `remaining` → `active_session_id = ""`, `messages = []`, return (the empty state). Some `remaining` → `next_id = remaining[0].session_id` (the list is `updated_at DESC`, so index 0 *is* the next most recent), `restored = await self._read_transcript(identity, next_id)` inside `try/except Exception`; on success assign `messages` and `active_session_id`; on failure assign `active_session_id = next_id`, `messages = []`, `sessions_error = TRANSCRIPT_NOT_LOADED_NOTICE`.
- **Mirror**: `state.py:276-325`; the read is `state.py:348-372`.
- **Constraints**: plain async, no `async with self`. **Calls no `database.py` function** (PRD Section 6: "`ChatState` calls the service, never `database.py` directly"). Touches nothing in `audit_logs` — it cannot, because the only write it makes is `chat_sessions.delete`, whose store function is documented as never touching an audit row (`database.py:1573-1577`). Performs **no ownership check of its own**: the service scopes on the freshly resolved `identity.user_id`, and a second check in `state.py` would be a client-side one wearing a server-side name. Pops **no** dialog: `rx.window_alert` exists and is not used; the confirmation is STORY-018's component and this handler runs only after it.
- **Note the deliberate divergence from `select_session`**: there, a failed read leaves the old transcript standing; here it must not. The old transcript belongs to a session that was just deleted, and AC 6 forbids landing on it. The failure arm therefore clears `messages` — the one place in `state.py` where a failed read empties the screen, and the docstring says why.
- **Validate**: `python -m pytest tests/test_chat_state.py tests/test_chat_sessions.py -q`

### Task 6: `_read_transcript` gains a third legal caller

- **File**: `chat_ui/chat_ui/state.py:348-372`
- **Action**: UPDATE
- **Implement**: Docstring only. It currently reads *"Both callers (`login` and `select_session`) hold the exclusive state lock..."*. Name `delete_session` as the third, and keep the rule that makes the list meaningful: every caller is a plain async handler, so `self` is the real state and an `async with self` here would deadlock. No code change.
- **Mirror**: the existing docstring's own wording.
- **Constraints**: the sentence must stay a *rule* about handler kind, not a list of names that a fourth caller can join without meeting it.
- **Validate**: `python -c "from chat_ui.chat_ui.state import ChatState; print('delete_session' in ChatState._read_transcript.__doc__)"`

### Task 7: Copy assertions

- **File**: `tests/test_copy.py`
- **Action**: UPDATE
- **Implement**: One test for the delete flow's copy, following the file's existing pattern (the `TRANSCRIPT_NOT_LOADED_NOTICE` test at `:612-636` is the model):
  1. Both constants exist and are non-empty.
  2. `SESSION_DELETE_CONFIRM_TEMPLATE.count("{title}") == 1`, and `.format(title="Q3 vendor spend")` contains that title.
  3. The confirmation states the record is kept: it contains `"kept"` (or the chosen wording — assert the actual promise, not a synonym list), and contains none of `audit`, `audit_logs`, `row`, `rows`, `table`, `database`, `sql`, `schema` — PRD Section 9's "in the user's words".
  4. Voice: starts uppercase; no `sorry`, `apologise`, `apologize`, `oops`, `unfortunately`.
  5. The naming rule, verbatim from the story: `SESSION_DELETE_CONFIRM_LABEL == "Delete"`, and `"remove"` appears in neither constant (lowercased) — the flow keeps one name.
  6. The confirmation must not promise the opposite of what `delete_chat_session` does: assert `"audit" not in ...lower()` is already covered by (3); additionally assert the string does not contain `"permanent"` unless the wording chosen actually is permanent — deletion here *is* permanent for the transcript, so if that word is used it must be true of the conversation and not of the record.
- **Mirror**: `tests/test_copy.py:612-636`.
- **Validate**: `python -m pytest tests/test_copy.py -q`

### Task 8: The STORY-016 test section

- **File**: `tests/test_chat_state.py` (append a new section at the end, after the STORY-015 block)
- **Action**: UPDATE
- **Implement**: A `# --- New chat, rename, delete, logout (STORY-016) ---` banner, three drivers in the shape of `_select` (`:1643-1647`) —

  ```python
  async def _rename(state, session_id, title): ...   # event_handlers["rename_session"]
  async def _delete(state, session_id): ...          # event_handlers["delete_session"]
  def _new_chat(state): ...                          # event_handlers["new_chat"] (sync)
  ```

  — and these cases, each named for the AC it pins:

  | # | Case | Asserts |
  |---|---|---|
  | 1 | `new_chat` clears the active id and the transcript, and writes no row | `active_session_id == ""`, `messages == []`, `count_chat_sessions(_AUTH_USER_ID)` unchanged (AC 1) |
  | 2 | `new_chat` twice with no send between leaves no session | `count_chat_sessions == 0` after two calls on a fresh state (AC 2) |
  | 3 | `new_chat` then a send creates exactly one session, and the rail keeps the old chat | one new row, `active_session_id` non-empty, both summaries in `sessions` (AC 1's "the next send creates the session") |
  | 4 | rename persists, updates the rail, and does not move `updated_at` | read `updated_at` via `list_chat_sessions` before and after — identical string; `sessions[i].title` is the new title at the **same index**; `activity_info` unchanged (AC 3) |
  | 5 | rename to `""` and to `"   "` is refused | `list_chat_sessions` title unchanged; `sessions` unchanged; parametrized over both (AC 4) |
  | 6 | rename never re-derives after a further send | rename, then `_send` into the same session, then re-read: the title is still the renamed one, not `derive_title(prompt)` (Technical Notes) |
  | 7 | delete removes the session and its messages, and leaves the audit trail alone | `count_chat_sessions` drops by one, `list_chat_messages(deleted, user) == []`, `_count_audit_rows()` identical across the delete (AC 5) |
  | 8 | deleting the active session lands on the next most recent | two sessions, older backdated with `_backdate_session`; delete the active newer one → `active_session_id == older`, `messages` are the older chat's (AC 6) |
  | 9 | deleting the last session lands on the empty state | `active_session_id == ""`, `messages == []`, `sessions == []` (AC 6) |
  | 10 | deleting a non-active session leaves the transcript alone | `messages` and `active_session_id` unchanged, the row is gone from `sessions` (AC 6) |
  | 11 | a failed read after deleting the active session does not land on the deleted transcript | patch `chat_state_mod.chat_sessions.messages_for` to raise; assert `messages == []`, `active_session_id == next_id`, `sessions_error == TRANSCRIPT_NOT_LOADED_NOTICE` (AC 6, the divergence recorded in Task 5) |
  | 12 | logout clears every named var **and every row survives** | count sessions and messages before and after `state.logout()` — identical; `sessions == []`, `active_session_id == ""`, `messages == []`, `sessions_error == ""`, `_token == ""`, `user_id == ""` (AC 8) |
  | 13 | signing back in lists the sessions again | after logout, a fresh `ChatState` + `login()` → the same session ids in `sessions` (AC 9) |
  | 14 | a foreign `session_id` changes nothing, through rename and delete | seed a second user's session (`insert_user` + `create_chat_session`), drive both handlers from `_AUTH_USER_ID`'s state; assert the foreign row's title and `count_chat_sessions(other)` are unchanged and `self.sessions` is untouched; parametrized over the two handlers (AC 10) |
  | 15 | `logout` calls no service | AST walk over `ChatState.logout` asserting it contains no `await`, no `asyncio.to_thread` and no attribute call on `chat_sessions` — the structural half of "logout clears state, delete deletes rows" |

- **Mirror**: `tests/test_chat_state.py:1953-2050` (STORY-015 cases), `:1599-1636` (the AST-walk shape for case 15), `:76-80` (`_count_audit_rows`), `:1243-1249` (`_stored_messages`).
- **Constraints**: use the existing `temp_db` fixture, `_make_state`, `_send`, `_capturing_run_query` and `_backdate_session`. Do not modify any existing test. Case 14 needs a second seeded user — follow `insert_user(User(...))` with `hash_token` as the fixture does at `:66-71`.
- **Validate**: `python -m pytest tests/test_chat_state.py -q`

### Task 9: Compile and full suite

- **File**: —
- **Action**: VERIFY
- **Implement**: Run the Validation block below in order, per **reflex-process-management** (`reflex compile --dry` from `chat_ui/` first, then the suites). Investigate any new warning rather than accepting it.
- **Validate**: `python -m pytest -q` green, with the count compared against STORY-015's report plus this story's new cases.

---

## End-to-End Tests

- [ ] `cd chat_ui && reflex compile --dry` succeeds with no new warning.
- [ ] Sign in with a seeded token, send two prompts, drive `new_chat()` from a REPL against the live `ChatState` → the screen is empty, `active_session_id` is `""`, and `count_chat_sessions` is unchanged; send once more → exactly one new row appears.
- [ ] Drive `rename_session(active, "Vendor contract review")` → `list_chat_sessions` shows the new title and the **same** `updated_at`; send again → the title survives.
- [ ] Drive `rename_session(active, "   ")` → the title stands.
- [ ] With two chats stored, drive `delete_session(active)` → the rail drops the row, the older chat's transcript is on screen, and `SELECT COUNT(*) FROM audit_logs` is unchanged.
- [ ] Sign out, then sign in again as the same user → the rail lists the same chats and the most recent transcript is back.
- [ ] `CHAT_HISTORY_ENABLED=false`, restart, sign in, drive all three handlers → nothing is written, nothing raises, and the chat still sends.

> Note: none of the three handlers is reachable by click until STORY-018 renders the rail, so the E2E column is a REPL — the same known debt `select_session` has carried since STORY-015, with the same named owner. Recorded in Risks.

---

## Validation

```bash
# The story's own suites
python -m pytest tests/test_chat_state.py tests/test_copy.py -q

# The service and store the three handlers call through
python -m pytest tests/test_chat_sessions.py tests/test_session_ownership.py tests/test_db.py -q

# The structural guards: the AST walks over app/ and chat_ui/, and the census
python -m pytest tests/test_untouched_app.py -q

# The chat still imports and its components still build
python -c "import chat_ui.chat_ui.state; print('ok')"
python -m pytest tests/test_chat_components_import.py tests/test_render_invariants.py -q

# The other suite that drives a chat send
python -m pytest tests/test_rbac.py -q

# The Reflex app compiles (reflex-process-management, step 1)
cd chat_ui && reflex compile --dry && cd ..

# Full suite before the commit
python -m pytest -q
```

---

## Deviations

| PRD / story says | Plan does | Why |
|---|---|---|
| Story Technical Notes: *"this story provides the event handlers and the copy it will call"*; STORY-017 AC: `copy.py` *"carries every rail string: the **New chat** label, the empty-rail invitation, the read-failure line... the delete confirmation, the rename affordance and the fallback title"*. | Adds **only** the delete confirmation template and the confirming control's label. The **New chat** label, the empty-rail invitation, the read-failure line and the rename affordance stay STORY-017's. | Two stories cannot both write the same constant. The split follows the precedent already in the file: STORY-014 and STORY-015 each added the *notice their own handler produces* to `copy.py` and left the rail's labels alone (`copy.py:109`, *"The rail's own strings are STORY-017's"*). The delete confirmation is the one string this story's own AC 7 makes a requirement — "the prompt names the chat by title and states that the audit record is unaffected" — so it lands here, with a comment in the block saying so. STORY-017 then adds the remaining four and asserts the whole set, which its AC already asks for. |
| Story AC 7: *"when the user is asked to confirm, then the prompt names the chat by title..."* | Provides the string; `delete_session` deletes unconditionally and asks nothing. | The story itself scopes the surface out: *"The confirmation UI itself is STORY-018."* `rx.window_alert` and `rx.alert_dialog` both exist in the pinned tree (verified), and using either here would put the flow's gate in the state layer where STORY-018's component cannot replace it — and would make `delete_session` untestable at state level, which is what AC 11 requires it to be. The handler is the confirmed branch, not the branch and its question. |
| Story AC 6: the UI *"lands on the next most recent session"*. | Reads `self.sessions[0]` after removing the deleted row, rather than re-listing from the store. | `self.sessions` is `list_for`'s output, `ORDER BY updated_at DESC` (`database.py:1466-1497`), so index 0 after the removal *is* the next most recent — and a re-list would be a second database round trip on a path that has already made two, for a list the handler is holding. If the list is stale the transcript read still goes to the store against the fresh Identity, so a stale row costs a failed read and its notice, not a wrong transcript. |
| STORY-015's precedent: a failed `_read_transcript` leaves `messages` and `active_session_id` exactly as they were. | After a delete of the active session, a failed read **clears** `messages` and moves `active_session_id`. | The precedent's reason does not survive the delete. STORY-015 left the transcript standing because it was still a real conversation the reader could be looking at; here it belongs to a session that no longer exists, and AC 6 says the UI must "never [land] on a transcript belonging to a deleted id". The notice (`TRANSCRIPT_NOT_LOADED_NOTICE`, *"The conversation on screen is unchanged"*) is reused because its second sentence stays true — the screen is empty and that *is* what is on it — but if the implementer finds it reads as a lie against an empty screen, the correct fix is a new constant in Task 1, not leaving the deleted transcript up. Flagged rather than decided silently. |
| Story: *"logout() clears state, delete_session() deletes rows. Conflating them is the destructive bug in this story's neighbourhood."* | `logout()` stays synchronous and Task 8 case 15 walks its AST for any `await`, `to_thread` or `chat_sessions` call. | A comment saying "this must not delete" is exactly the artifact that survives the edit that makes it false. The synchronous signature makes a service call awkward and the AST walk makes it fail a test — the shape `test_chat_state_never_names_the_history_flag` (`:1155`) and the `_do_send` append guard (`:1599`) already use in this file. |
| Story AC 4: an empty rename *"is refused and the existing title stands."* | Refused **silently** — no notice, no copy constant. | The refusal is of the input, not of the system, and the existing title standing is the whole feedback. A notice on the rail's error slot would report a stale *list* for a keystroke, which is the conflation `state.py:156-161` records as making one of the two notices a lie. The inline validation is STORY-018's component to render if it wants one; nothing here writes a string that the surface would then have to un-say. |
| Story Technical Notes: *"All service calls go through `asyncio.to_thread(...)`; all state mutation inside `async with self`."* | Keeps the first half exactly; **does not** wrap any mutation in `async with self`. | The second half is true of `_do_send` and false of every handler this story writes. `_do_send` is `rx.event(background=True)`, so `self` is a `StateProxy` and mutation *requires* the block; all three new handlers are plain `@rx.event`, so they already hold the exclusive lock for their whole duration and `async with self` inside one would **deadlock on a lock the handler already holds** — `login`'s docstring (`state.py:183-195`) records exactly this, and `select_session`, the nearest sibling to two of these handlers, mutates directly for the same reason. The note is a generalization of the send path; following it literally would hang the app. The instruction it *is* obeyed on — verify the Reflex API rather than recall it (`chat_ui/AGENTS.md`) — is what produced this finding; the evidence is in the reflex-docs table. |
| PRD Section 6: *"`ChatState` calls the service, never `database.py` directly."* | Unchanged in production code; the **tests** call `database.py` directly to count rows and to seed a second user. | Already the suite's pattern (`tests/test_chat_state.py:15-26` imports `count_chat_sessions`, `list_chat_messages`, `create_chat_session`, `insert_user`). Counting rows across a logout is precisely an assertion about the store, and it has to reach the store to make it. No line under `chat_ui/` gains a `database` import. |
| Story: `new_chat()` clears *"`active_session_id` and `messages`"*. | Also clears `transcript_error`, and deliberately does **not** clear `input_text` or `sessions_error`. | `transcript_error` is about the transcript being cleared on the line above — `logout`'s recorded reasoning for the same var (`state.py:262-266`), and `select_session`'s (`:322-324`). `input_text` is the person's half-typed text, and `select_session` already leaves it alone on the same reasoning; `logout` clears it only because the person themselves is leaving. `sessions_error` is the rail's slot and a list that failed to load is still failed after starting a new chat. |

---

## Risks

| Risk | Mitigation |
|---|---|
| **The destructive one**: a later edit makes `logout()` call `chat_sessions.delete` — "clearing" the list by emptying it in the database — and every sign-out on a shared machine destroys the user's history. | Three layers. The handler is synchronous, so a service call cannot be awaited into it without changing the signature. Task 8 case 12 counts sessions **and** messages across the logout. Task 8 case 15 walks the AST and fails on any `await`, `to_thread` or `chat_sessions.*` inside `logout`. The docstring states the distinction in the same paragraph as the argument it extends. |
| **PRD Risk 3** — `session_id` reaches both new handlers from the client and names a row. A rename or delete that trusted it would retitle or destroy another user's conversation. | Neither handler validates the id and neither should: `chat_sessions.rename`/`delete` scope the `WHERE` on an Identity re-resolved from `_token` inside the handler (`chat_sessions.py:206-259` → `database.py:1499-1520`, `:1538+`), and both return `False` for a foreign id, an unknown id and history-off alike. Task 8 case 14 drives both handlers with a second user's session and asserts nothing moved. `tests/test_session_ownership.py` already pins the signatures. |
| A rename bumps `updated_at` — through `chat_sessions.touch`, or through an `activity_info` recomputed from a fresh clock — and the row jumps to the top of the rail while the user's cursor is in it. | The store refuses to write `updated_at` on a rename and says why (`database.py:1502-1508`); this plan adds no `touch` call and reuses the **existing** `activity_info` on the rebuilt summary. Task 8 case 4 asserts the stored `updated_at` string is byte-identical across the rename **and** that the row's index in `sessions` did not change. |
| The rename re-derives on the next send, silently undoing the user's edit — the failure the story names. | Structurally unbuildable here: `derive_title` is called in exactly one place, `chat_sessions.create` (`chat_sessions.py:123`), which runs only when `active_session_id` is empty. This plan adds no second call site. Task 8 case 6 asserts it positively anyway by sending after the rename. |
| A delete that fails halfway leaves the session gone and its messages orphaned, or the reverse. | Not this layer's to solve, and already solved: `database.delete_chat_session` does both statements in one `_session()` block, one transaction, messages first, scoped by an ownership subselect (`database.py:1538-1577`). This handler makes one call and reads one boolean. Task 8 case 7 asserts both counts. |
| A delete quietly takes audit rows with it, destroying evidence — the exact thing PRD Section 9 exists to prevent. | Structurally unreachable: the only write this handler makes is `chat_sessions.delete`, and no statement under it names `audit_logs`. Task 8 case 7 asserts `_count_audit_rows()` is identical across the delete, which is AC 5's own wording. |
| The active session is deleted while a send is in flight; `_do_send` holds the id in a local and appends the answer to a session that no longer exists. | `delete_session` returns early on `pending`, as `select_session` and `new_chat` do. If the delete lands between the guard and the append anyway, `append_chat_message` fails on the missing row and STORY-014's degraded arm keeps the bubble and reports it (`state.py:420-427`) — the failure mode is a notice, not a lost turn. |
| Someone writes `async with self` in one of the two async handlers, copying the pattern from `_append_and_persist` sixty lines away. | It deadlocks on a lock the handler already holds, and the whole suite hangs rather than failing subtly. The rule is in `login`'s docstring (`:183-195`), restated in `_read_transcript`'s (`:352-360`) and named again in each new handler's. The reflex-docs table above records both halves with the pinned-tree citation. |
| Someone makes one of them `background=True` so it "does not block", and it silently stops being callable from another handler. | The reflex-docs table records the constraint verbatim from the published page; the handlers mutate directly and would raise `ImmutableStateError` outside `async with self` the moment the decorator changed, so the change fails loudly rather than drifting. |
| The three handlers are unreachable in the running app until the rail exists, so nothing on screen proves any of this. | Bounded, understood, and identical to the interval `select_session` has sat in since STORY-015 and `sessions_error` since STORY-013. STORY-018 is the named owner and depends on this story; STORY-021's two-instance smoke closes it end to end. The state-level tests are the AC (*"each of the above is asserted at state level"*). |
| STORY-017 also adds `SESSION_DELETE_CONFIRM_TEMPLATE` and the two collide, or it assumes the constant is missing and the delete confirmation ends up written twice in two voices. | The Deviations row above states the split, and Task 1 puts the same statement in a comment at the constant itself, where STORY-017's implementer will be reading. STORY-017's own AC ("`copy.py` carries every rail string") is satisfied by a constant that is already there. |
| The confirmation says the record is kept in words a compliance reader would dispute — or names `audit_logs` and stops being the user's words. | Task 7 asserts both directions: the promise is present, and the schema vocabulary is absent. PRD Section 9's sentence is the source and is quoted in the story. |

---

## Acceptance Criteria

(Copied from story `STORY-016`)

- [ ] Given `new_chat()`, when it runs, then `active_session_id` and `messages` are cleared and **no row is written** — the next send creates the session, per STORY-013's lazy rule.
- [ ] Given `new_chat()` called twice with no send in between, when the database is inspected, then no session exists.
- [ ] Given `rename_session(session_id, title)`, when it runs on an owned session, then the title persists, the rail updates, and `updated_at` is **not** touched — a rename is not activity and must not reorder the rail under the user's cursor.
- [ ] Given a rename to an empty or whitespace title, when it is submitted, then it is refused and the existing title stands.
- [ ] Given `delete_session(session_id)`, when it is confirmed, then the session and its messages are removed, the rail drops the row, and `count_audit_logs()` is unchanged.
- [ ] Given the active session being deleted, when the delete completes, then the UI lands on the next most recent session, or on the empty state if none remains — never on a transcript belonging to a deleted id.
- [ ] Given a delete, when the user is asked to confirm, then the prompt names the chat by title and states that the audit record is unaffected.
- [ ] Given `logout()`, when it runs, then `sessions`, `active_session_id`, `messages`, `_token`, `user_id` and `sessions_error` are all cleared, and **every row survives in the database** — asserted by counting sessions and messages across the logout.
- [ ] Given a signed-out user, when they sign back in, then their sessions are listed again.
- [ ] Given a foreign `session_id` submitted to `rename_session` or `delete_session`, when it runs, then nothing changes in the database and the rail is unaffected.
- [ ] Given `tests/test_chat_state.py`, when it runs, then each of the above is asserted at state level, including the row counts across logout.
- [ ] All tasks completed
- [ ] `cd chat_ui && reflex compile --dry` succeeds
- [ ] Full suite green (`python -m pytest -q`)
- [ ] Follows existing patterns
