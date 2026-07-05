---
story: STORY-004
prd: PRD-002
slug: chat-ui-components
title: "Claude-like chat UI components (static)"
type: feature
complexity: medium
epic_branch: epic/PRD-002-reflex-chat-ui
created: 2026-07-05
---

# Plan: Claude-like chat UI components (static)

## Summary

Build a static, Claude-like chat interface in the Reflex app: a scrollable message list with avatar + alternating bubble alignment (user right/blue, assistant left/neutral), and an input bar with a submit action. This story introduces the first real `ChatState` (currently a one-line stub) holding `messages: list[dict[str, str]]` and `input_text: str`, with a `send()` handler that only appends the typed text as a new user-aligned bubble — no pipeline call, no assistant reply generation (that's STORY-006). The message list is seeded with one canned assistant message so the visual review can confirm both bubble alignments without sending anything first.

## User Story

As an end user
I want a chat window that looks and feels like Claude
So that the interface is immediately familiar even before it's wired to the real pipeline

## Story Reference

- Story file: `.agents/stories/PRD-002-reflex-chat-ui/STORY-004-chat-ui-components.md`
- PRD: `.agents/PRDs/PRD-002-reflex-chat-ui/PRD.md`

## Metadata

| Field | Value |
|-------|-------|
| Type | feature |
| Complexity | MEDIUM |
| Systems Affected | `chat_ui/chat_ui/state.py`, `chat_ui/chat_ui/components/chat.py` (new), `chat_ui/chat_ui/chat_ui.py` |
| Story | STORY-004 |
| PRD | PRD-002 |
| Epic Branch | `epic/PRD-002-reflex-chat-ui` (commit directly on this branch) |

---

## Skills In Use

None. `.agents/skills/` does not exist and the story's `skills:` frontmatter is empty. Note: `chat_ui/AGENTS.md` references an external Reflex plugin skill set (`reflex-docs`, `setup-python-env`, `reflex-process-management`) but it is **not installed** in this environment (checked `~/.claude/plugins` — absent). Component APIs for this plan were instead verified directly against the installed `reflex==0.9.6.post1` package source (`reflex_components_radix`, `reflex_components_lucide`) rather than relying on memory or the missing skill.

---

## Patterns to Follow

### Existing mount / page wiring
```python
// SOURCE: chat_ui/chat_ui/chat_ui.py:29-53
class State(rx.State):
    """The app state."""

def index() -> rx.Component:
    return rx.container(...)

app = rx.App(api_transformer=fastapi_app)
app.add_page(index)
```
The plan keeps `app = rx.App(api_transformer=fastapi_app)` and the eager `init_db()` untouched (STORY-003 concern) — only `index()`'s body and imports change.

### State stub being replaced
```python
// SOURCE: chat_ui/chat_ui/state.py:1
"""Stub — ChatState is added in STORY-006."""
```
This comment is stale relative to the story board: STORY-004 (this story) blocks STORY-005 (user_id field) and STORY-006 (wire `send()` to `run_query`), so `ChatState` must exist with `messages`/`input_text`/`send()` now, and STORY-006 extends `send()` in place rather than creating it. This is a one-line comment correction, not a scope conflict — flagged in Risks below.

### Confirmed available components (verified against installed `reflex==0.9.6.post1`, not memory)
```
// SOURCE: site-packages/reflex_components_radix/themes/components/avatar.pyi:93-95 (rx.avatar: src, fallback)
// SOURCE: site-packages/reflex_components_radix/themes/components/text_field.py:148 (rx.input == rx.text_field.input)
// SOURCE: site-packages/reflex_components_lucide/icon.py (icon names include "send", "user", "bot")
// SOURCE: site-packages/reflex_components_radix/themes/components/icon_button.py:28 (IconButton extends elements.Button -> supports type="submit")
```
`rx.foreach`, `rx.cond`, `rx.form`, `rx.vstack`/`hstack`/`box`/`scroll_area` are core `reflex` exports, confirmed present via `dir(rx)`.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `chat_ui/chat_ui/state.py` | UPDATE | Replace stub with `ChatState` (`messages`, `input_text`, `send()`) — presentation-only append, no pipeline call |
| `chat_ui/chat_ui/components/chat.py` | CREATE | `message_bubble()`, `message_list()`, `chat_input()` components (Claude-like styling) |
| `chat_ui/chat_ui/chat_ui.py` | UPDATE | Replace placeholder `index()` welcome page with the chat layout; remove the now-unused local `State` stub class |

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Replace the `state.py` stub with a real `ChatState`

- **File**: `chat_ui/chat_ui/state.py`
- **Action**: UPDATE
- **Implement**:
  ```python
  import reflex as rx

  WELCOME_MESSAGE = {
      "role": "assistant",
      "content": "Hi! Type a message below and press send.",
  }


  class ChatState(rx.State):
      """Holds chat messages and the input box's text.

      send() only appends the user's message for now (presentation-only,
      per STORY-004); wiring to the shared query pipeline is STORY-006.
      """

      messages: list[dict[str, str]] = [WELCOME_MESSAGE]
      input_text: str = ""

      def send(self):
          text = self.input_text.strip()
          if not text:
              return
          self.messages.append({"role": "user", "content": text})
          self.input_text = ""
  ```
- **Mirror**: `chat_ui/chat_ui/chat_ui.py:25-26` — same `rx.State` subclassing style used in the project so far.
- **Validate**: `python -c "import ast; ast.parse(open('chat_ui/chat_ui/state.py').read())"`

### Task 2: Build the chat components (bubble, list, input bar)

- **File**: `chat_ui/chat_ui/components/chat.py`
- **Action**: CREATE
- **Implement**:
  - `message_bubble(message: dict) -> rx.Component`: `rx.cond(message["role"] == "user", <right-aligned hstack: bubble box then avatar fallback="U">, <left-aligned hstack: avatar fallback="AI" then bubble box>)`. Bubble box: `rx.box(message["content"], background_color/color per role, padding, border_radius, max_width)`.
  - `message_list() -> rx.Component`: `rx.box(rx.foreach(ChatState.messages, message_bubble), display="flex", flex_direction="column", gap="3", overflow_y="auto", flex="1", width="100%", padding="4")` — a scrollable column that grows to fill available height.
  - `chat_input() -> rx.Component`: `rx.form(rx.hstack(rx.input(value=ChatState.input_text, on_change=ChatState.set_input_text, placeholder="Message...", width="100%"), rx.icon_button(rx.icon("send", size=18), type="submit"), width="100%"), on_submit=ChatState.send, reset_on_submit=True, width="100%")`.
  - Import `ChatState` from `chat_ui.state`.
- **Mirror**: styling conventions (spacing tokens `"3"`/`"4"`, `rx.vstack`/`rx.hstack` usage) already used in `chat_ui.py:31-48`'s welcome page.
- **Validate**: `python -c "import ast; ast.parse(open('chat_ui/chat_ui/components/chat.py').read())"`

### Task 3: Wire the components into `chat_ui.py`'s page

- **File**: `chat_ui/chat_ui/chat_ui.py`
- **Action**: UPDATE
- **Implement**: Remove the placeholder `class State(rx.State)` stub and the welcome-page body of `index()`. Import `message_list`, `chat_input` from `chat_ui.components.chat`. New `index()`:
  ```python
  def index() -> rx.Component:
      return rx.vstack(
          message_list(),
          chat_input(),
          height="100vh",
          width="100%",
          spacing="0",
      )
  ```
  Keep `app = rx.App(api_transformer=fastapi_app)`, `app.add_page(index)`, and the eager `init_db()` call exactly as STORY-003 left them.
- **Mirror**: `chat_ui/chat_ui/chat_ui.py:52-53` (unchanged `app`/`add_page` lines).
- **Validate**: `python -c "import ast; ast.parse(open('chat_ui/chat_ui/chat_ui.py').read())"`

### Task 4: Manual UI walkthrough (Reflex dev server)

- **File**: N/A (validation only)
- **Action**: N/A
- **Implement**: Run `reflex run` (dev mode) from `chat_ui/`, open the served URL, confirm the welcome assistant bubble renders on the left with an avatar, type a message, click send (or press Enter), confirm a new right-aligned user bubble with its own avatar appears and the input clears.
- **Mirror**: STORY-003 report's manual validation style (`reflex run --env prod` boot + route checks).
- **Validate**: Visual review against the Claude-like reference style (avatars, alignment, spacing) per PRD Section 12 Phase 3.

---

## End-to-End Tests

- [ ] `reflex run` boots without errors from `chat_ui/`
- [ ] Loading the served URL shows the seeded assistant bubble (left-aligned, avatar) and an input bar with a send control
- [ ] Typing text and submitting (click or Enter) appends a right-aligned user bubble with its own avatar; input box clears
- [ ] No backend/pipeline call occurs on send (purely local state append) — confirmed by code inspection of `ChatState.send()`
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

1. **Stale stub comment**: `state.py`'s current docstring ("Stub — ChatState is added in STORY-006") is superseded by this story per the dependency chain (STORY-004 blocks STORY-005 blocks STORY-006). This plan creates `ChatState` now with presentation-only `send()`; STORY-006 extends the same class/method to call `run_query(...)` instead of creating it fresh.
2. **No assistant reply on send**: matches the story's AC2 literally ("a new user-aligned bubble appears... no backend call yet") — the seeded welcome message is the only assistant-side bubble until STORY-006 wires real responses. This is intentional, not a gap.
3. **Reflex skill plugin absent**: `chat_ui/AGENTS.md` asks for `reflex-docs`/`setup-python-env`/`reflex-process-management` Claude Code plugins before touching Reflex code; they are not installed in this environment. Mitigated by verifying every component API used in this plan directly against the installed `reflex==0.9.6.post1` package source rather than guessing from training-data memory. `/implement` should do the same for any component not already verified here.
4. **Manual validation only**: per the story's own ACs and PRD Section 12 Phase 3, this story's validation is a manual UI walkthrough + visual review, not new automated tests — consistent with STORY-004 being presentation-only.

---

## Acceptance Criteria

(Copied from story STORY-004)

- [ ] Given the chat page loads, when rendered, then it shows a message list area and an input bar with a send button/action, styled to approximate Claude's chat layout (avatars, alternating bubble alignment for user vs. assistant messages).
- [ ] Given a user types text and sends it, when the static component handles the interaction, then a new user-aligned bubble appears in the message list (no backend call yet).
- [ ] Given the component structure in PRD Section 6, when implemented, then it lives in `chat_ui/chat_ui/components/chat.py` as message bubble + input bar components, consumed by `chat_ui/chat_ui/chat_ui.py`.
- [ ] Given a manual UI walkthrough, when a message is sent, then a user bubble renders and a visual review confirms it approximates the Claude-like reference style.
- [ ] Given this story is presentation-only, when PRD-001's existing test suite runs, then it continues to pass unmodified.
- [ ] All tasks completed.
- [ ] Follows existing patterns.
