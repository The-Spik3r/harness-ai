---
story: STORY-005
prd: PRD-002
slug: session-user-id-entry
title: "Session user_id entry field"
type: feature
complexity: LOW
epic_branch: epic/PRD-002-reflex-chat-ui
created: 2026-07-05
---

# Plan: Session user_id entry field

## Summary

Add a `user_id` field to `ChatState` and a full-page entry form (`user_id_prompt()`) that gates the chat layout: while `ChatState.user_id` is empty, `index()` renders the entry form instead of the message list/input bar; once a non-blank `user_id` is submitted, `index()` renders the existing chat layout for the rest of the browser session (Reflex's per-connection `State` instance means it is never asked again without a fresh session). `ChatState.send()` also gets a defense-in-depth guard mirroring PRD-001's `if not request.user_id.strip()` presence check, so a blank/whitespace `user_id` blocks the send action with the same intent even though the UI gate already prevents reaching it. This story stores `user_id` only in Reflex state — no `run_query(...)` call yet (that is STORY-006) and no password/token/OAuth flow (explicitly out of scope per PRD Section 4).

## User Story

As an end user
I want to enter a simple `user_id` once per browser session
So that my chat messages carry the same identity the harness already requires on `POST /query`, without any new login/auth system

## Story Reference

- Story file: `.agents/stories/PRD-002-reflex-chat-ui/STORY-005-session-user-id-entry.md`
- PRD: `.agents/PRDs/PRD-002-reflex-chat-ui/PRD.md`

## Metadata

| Field | Value |
|-------|-------|
| Type | feature |
| Complexity | LOW |
| Systems Affected | `chat_ui/chat_ui/state.py`, `chat_ui/chat_ui/components/chat.py`, `chat_ui/chat_ui/chat_ui.py` |
| Story | STORY-005 |
| PRD | PRD-002 |
| Epic Branch | `epic/PRD-002-reflex-chat-ui` (commit directly on this branch) |

---

## Skills In Use

None apply beyond what STORY-004's plan already established. `.agents/skills/` does not exist and the story's `skills:` frontmatter is empty. `chat_ui/AGENTS.md` asks for the `reflex-dev/agent-skills` plugin (`reflex-docs`, `setup-python-env`, `reflex-process-management`); only `reflex-docs` is installed in this environment (confirmed via the Skill tool — it returned its reference index of doc URLs, no component-level pages fetched). Component APIs (`rx.center`, `rx.button`, `rx.text`, `rx.cond`, `rx.form`) used below were confirmed present against the installed `reflex` package (`python -c "import reflex as rx; ... 'center' in dir(rx)"` → all `True`) rather than relying on memory or the missing local skill files.

Per-session isolation was confirmed via `reflex.dev/docs/state/overview` (fetched through WebFetch): "Reflex internally creates a new instance of the state for each user" — each browser connection gets its own `ChatState`, so storing `user_id` as a plain base var already satisfies "once per session, not persisted across sessions/browsers" (PRD Section 4, Out of Scope) with zero extra client-storage mechanism (`rx.LocalStorage`/cookies not needed or wanted here).

---

## Patterns to Follow

### Existing state var + setter + guarded event handler
```python
// SOURCE: chat_ui/chat_ui/state.py:19-29
@rx.event
def set_input_text(self, text: str):
    self.input_text = text

@rx.event
def send(self):
    text = self.input_text.strip()
    if not text:
        return
    self.messages.append({"role": "user", "content": text})
    self.input_text = ""
```
`user_id_input`/`set_user_id_input`/`submit_user_id` follow this exact base-var + setter + guarded-handler shape.

### Existing form + input + submit-button component
```python
// SOURCE: chat_ui/chat_ui/components/chat.py:53-73
def chat_input() -> rx.Component:
    return rx.form(
        rx.hstack(
            rx.input(
                value=ChatState.input_text,
                on_change=ChatState.set_input_text,
                placeholder="Message...",
                width="100%",
            ),
            rx.icon_button(rx.icon("send", size=18), type="submit"),
            width="100%",
            padding="1rem",
        ),
        on_submit=ChatState.send,
        reset_on_submit=True,
        width="100%",
    )
```
`user_id_prompt()` reuses the same `rx.form(..., on_submit=..., ...)` + bound `rx.input` shape.

### Existing rx.cond usage for role-based branching
```python
// SOURCE: chat_ui/chat_ui/components/chat.py:8-36
return rx.cond(
    message["role"] == "user",
    rx.hstack(...),
    rx.hstack(...),
)
```
`index()` uses the same `rx.cond(condition, branch_a, branch_b)` shape to switch between the entry form and the chat layout.

### Presence-check intent to mirror (backend, PRD-001)
```python
// SOURCE: app/routers/query.py:12-14
if not request.user_id.strip():
    raise HTTPException(status_code=400, detail="user_id is required")
```
`send()`'s new guard (`if not self.user_id.strip(): return`) mirrors this check's *intent* client-side — block, don't send — per STORY-005 AC3. It does not raise/HTTP-error since there is no request cycle yet; STORY-006 is what actually calls `run_query(...)`.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `chat_ui/chat_ui/state.py` | UPDATE | Add `user_id`, `user_id_input` vars, `set_user_id_input()`, `submit_user_id()` handlers; guard `send()` on blank `user_id` |
| `chat_ui/chat_ui/components/chat.py` | UPDATE | Add `user_id_prompt()` component (entry form) |
| `chat_ui/chat_ui/chat_ui.py` | UPDATE | Gate `index()` with `rx.cond(ChatState.user_id != "", <chat layout>, user_id_prompt())` |

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Add `user_id` state, setter, and submit handler to `ChatState`

- **File**: `chat_ui/chat_ui/state.py`
- **Action**: UPDATE
- **Implement**: Add two new base vars and two new event handlers, and guard `send()`:
  ```python
  class ChatState(rx.State):
      messages: list[dict[str, str]] = [WELCOME_MESSAGE]
      input_text: str = ""
      user_id: str = ""
      user_id_input: str = ""

      @rx.event
      def set_input_text(self, text: str):
          self.input_text = text

      @rx.event
      def set_user_id_input(self, text: str):
          self.user_id_input = text

      @rx.event
      def submit_user_id(self):
          text = self.user_id_input.strip()
          if not text:
              return
          self.user_id = text

      @rx.event
      def send(self):
          if not self.user_id.strip():
              return
          text = self.input_text.strip()
          if not text:
              return
          self.messages.append({"role": "user", "content": text})
          self.input_text = ""
  ```
  Update the class docstring to note `user_id` is collected once per session and reused by `send()` (and, from STORY-006 onward, passed into `run_query(...)`).
- **Mirror**: `chat_ui/chat_ui/state.py:19-29` (existing `set_input_text`/`send()` shape).
- **Validate**: `python -c "import ast; ast.parse(open('chat_ui/chat_ui/state.py').read())"`

### Task 2: Add the `user_id_prompt()` component

- **File**: `chat_ui/chat_ui/components/chat.py`
- **Action**: UPDATE
- **Implement**: Add a new component, plain text field only (no password/token/OAuth):
  ```python
  def user_id_prompt() -> rx.Component:
      """Full-page form collecting the session's user_id once, before the chat becomes usable."""
      return rx.center(
          rx.form(
              rx.vstack(
                  rx.text("Enter a user ID to start chatting", size="4", weight="bold"),
                  rx.input(
                      value=ChatState.user_id_input,
                      on_change=ChatState.set_user_id_input,
                      placeholder="user_id",
                      width="100%",
                  ),
                  rx.button("Continue", type="submit"),
                  spacing="3",
                  width="20rem",
              ),
              on_submit=ChatState.submit_user_id,
          ),
          height="100vh",
          width="100%",
      )
  ```
- **Mirror**: `chat_ui/chat_ui/components/chat.py:53-73` (`chat_input()`'s `rx.form`/bound-`rx.input`/submit shape).
- **Validate**: `python -c "import ast; ast.parse(open('chat_ui/chat_ui/components/chat.py').read())"`

### Task 3: Gate `index()` on `ChatState.user_id`

- **File**: `chat_ui/chat_ui/chat_ui.py`
- **Action**: UPDATE
- **Implement**: Import `user_id_prompt` alongside the existing `chat_input`/`message_list` import; wrap the current chat layout in `rx.cond`:
  ```python
  from chat_ui.components.chat import chat_input, message_list, user_id_prompt

  def index() -> rx.Component:
      return rx.cond(
          ChatState.user_id != "",
          rx.vstack(
              message_list(),
              chat_input(),
              height="100vh",
              width="100%",
              spacing="0",
          ),
          user_id_prompt(),
      )
  ```
  This requires importing `ChatState` in `chat_ui.py` (not currently imported there — currently only `chat_input`/`message_list` are imported, which internally reference `ChatState`). Add `from chat_ui.state import ChatState`.
- **Mirror**: `chat_ui/chat_ui/components/chat.py:8-13` (`rx.cond(condition, branch_a, branch_b)` shape already used for `message_bubble`).
- **Validate**: `python -c "import ast; ast.parse(open('chat_ui/chat_ui/chat_ui.py').read())"`

### Task 4: Manual UI walkthrough (Reflex dev server)

- **File**: N/A (validation only)
- **Action**: N/A
- **Implement**: Run `reflex run` (dev mode) from `chat_ui/`, open the served URL. Confirm: (a) the entry form renders instead of the chat layout on first load; (b) submitting a blank/whitespace value does nothing (form stays); (c) submitting a non-blank `user_id` swaps the view to the chat layout (seeded welcome bubble + input bar); (d) reloading the same browser tab does not re-persist `user_id` across a fresh Reflex session load (state is server-side per-connection, matching "no persistence across sessions/browsers" — refreshing the page is expected to re-prompt, which is consistent with PRD Section 4's Out of Scope) — do not treat this as a bug; (e) sending a message afterward works exactly as STORY-004 left it.
- **Mirror**: STORY-004 plan's Task 4 manual-walkthrough style.
- **Validate**: Visual review — entry form gates the chat, non-blank submission reveals chat, blank submission is a no-op.

---

## End-to-End Tests

- [ ] `reflex run` boots without errors from `chat_ui/`
- [ ] Loading the served URL shows the `user_id` entry form, not the chat layout
- [ ] Submitting a blank/whitespace `user_id` leaves the entry form in place (no state change, no crash)
- [ ] Submitting a non-blank `user_id` reveals the chat layout (message list + input bar) for the rest of that browser session
- [ ] `ChatState.send()` is a no-op if `user_id` is somehow blank (code-inspection check of the added guard) — confirms client-side blocking with the same intent as `app/routers/query.py:13`
- [ ] Full `pytest` suite (repo root) passes unmodified — this story touches no backend/test files

---

## Validation

```bash
cd chat_ui && python -c "import ast; ast.parse(open('chat_ui/state.py').read()); ast.parse(open('chat_ui/components/chat.py').read()); ast.parse(open('chat_ui/chat_ui.py').read())"
cd chat_ui && reflex run
cd f:/AI/harness-ai && pytest
```

---

## Risks & Notes

1. **No cross-reload persistence**: `user_id` lives only in the Reflex `State` instance for the current connection. A hard page reload gets a fresh state and re-prompts. This matches PRD Section 4's Out of Scope ("no persisted chat history across sessions or browsers") and the story's own technical note ("it does not need to be persisted server-side or across browser sessions") — not a gap to fix here. If product later wants "survive a reload," that would be `rx.LocalStorage`/cookie-backed state, explicitly deferred.
2. **`send()` guard is currently unreachable via the UI**: because `index()` fully gates the chat layout behind `user_id != ""`, a user cannot reach `chat_input()`'s submit button without `user_id` already set — so the new guard in `send()` is defense-in-depth (matches AC3's literal wording) rather than the only enforcement point. Both layers together satisfy the AC without duplicating pipeline logic.
3. **No error message on blank submit**: the entry form silently no-ops on blank/whitespace submission (matching `send()`'s existing style of silent no-op on blank `input_text`, per `chat_ui/chat_ui/state.py:24-27`) rather than introducing a new error-display pattern not requested by the story. If a future story wants inline validation text, that is a separate concern.
4. **STORY-006 handoff**: `ChatState.user_id` is now populated and ready for STORY-006 to pass into `run_query(user_id=self.user_id, ...)` — no interface changes anticipated there beyond reading this existing field.

---

## Acceptance Criteria

(Copied from story STORY-005)

- [ ] Given the chat page loads with no `user_id` set for the session, when the user is prompted, then a simple text field collects a `user_id` before the chat input becomes usable.
- [ ] Given a `user_id` has been entered once, when the user sends subsequent messages in the same browser session, then the same `user_id` is reused automatically — the field is not asked again mid-session.
- [ ] Given no `user_id` is entered (blank/whitespace), when the user attempts to send a message, then the send action is blocked client-side with the same intent as PRD-001's existing presence check.
- [ ] Given this is explicitly not a new identity system, when reviewed, then no password, token, or OAuth flow is introduced — this is a plain text field only.
- [ ] Given the field is implemented, when PRD-001's existing test suite runs, then it continues to pass unmodified.
- [ ] All tasks completed.
- [ ] Follows existing patterns.
