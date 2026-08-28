---
story: STORY-012
prd: PRD-004
slug: pending-indicator-composer-lock
title: "Typing indicator and disabled composer while a request is in flight"
type: ENHANCEMENT
complexity: LOW
epic_branch: epic/PRD-004-chat-ui-redesign
created: 2026-08-24
---

# Plan: Typing indicator and disabled composer while a request is in flight

## Summary

Implement a visual typing/loading indicator at the end of the message list and lock/disable the composer (text input and send button) while `ChatState.pending` is True. Both automatically reset via `finally` on every outcome path.

## User Story

As an end user, I want visible feedback while the model is thinking, so that a 30-second OpenRouter call does not look like a frozen page.

## Story Reference

- Story file: `.agents/stories/PRD-004-chat-ui-redesign/STORY-012-pending-indicator-composer-lock.md`
- PRD: `.agents/PRDs/PRD-004-chat-ui-redesign/PRD.md`

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT |
| Complexity | LOW |
| Systems Affected | `chat_ui/` |
| Story | STORY-012 |
| PRD | PRD-004 |
| Epic Branch | `epic/PRD-004-chat-ui-redesign` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| reflex-docs | Reflex component APIs (`disabled`, `rx.spinner`, `rx.cond`) | Tasks 2, 3, 4 |
| reflex-process-management | Compiling / running / testing Reflex app | Task 5 |

---

## Patterns to Follow

### Naming
```
// SOURCE: chat_ui/chat_ui/components/chat.py:29-40
def message_list() -> rx.Component:
```

### Components
```
// SOURCE: chat_ui/chat_ui/components/bubbles.py:66-84
def render_assistant(message) -> rx.Component:
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `chat_ui/chat_ui/copy.py` | UPDATE | Add pending indicator copy |
| `chat_ui/chat_ui/components/bubbles.py` | UPDATE | Add `render_pending_indicator()` |
| `chat_ui/chat_ui/components/chat.py` | UPDATE | Render pending indicator in `message_list()`, disable input/button in `chat_input()` |

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Add pending indicator copy
- **File**: `chat_ui/chat_ui/copy.py`
- **Action**: UPDATE
- **Implement**: Add `PENDING_INDICATOR_TEXT = "Model is thinking..."`
- **Validate**: Python syntax check

### Task 2: Implement pending indicator renderer
- **File**: `chat_ui/chat_ui/components/bubbles.py`
- **Action**: UPDATE
- **Implement**: Create `render_pending_indicator()` using `rx.spinner()` and `rx.text()`, styled like assistant bubble.
- **Validate**: Python syntax check

### Task 3: Render pending indicator in message list
- **File**: `chat_ui/chat_ui/components/chat.py`
- **Action**: UPDATE
- **Implement**: Add `rx.cond(ChatState.pending, render_pending_indicator(), rx.fragment())` inside `message_list()` after `rx.foreach(ChatState.messages, message_bubble)`.
- **Validate**: Python syntax check

### Task 4: Disable composer during pending state
- **File**: `chat_ui/chat_ui/components/chat.py`
- **Action**: UPDATE
- **Implement**: Add `disabled=ChatState.pending` to `rx.input` and `rx.icon_button` in `chat_input()`.
- **Validate**: Python syntax check

### Task 5: Verify tests and build
- **File**: test suite (`tests/test_chat_state.py`)
- **Action**: VERIFY
- **Implement**: Run pytest to ensure all tests pass.
- **Validate**: `pytest` passes successfully.

---

## End-to-End Tests

- [ ] Given `ChatState.pending` is `True`, when the message area renders, then a typing/loading indicator is visible at the end of the list.
- [ ] Given `ChatState.pending` is `True`, when the composer renders, then both the text input and the send button are disabled.
- [ ] Given a request that ends in any of the six outcomes, when its bubble is appended, then the indicator disappears and the composer re-enables.

---

## Validation

```bash
pytest
```

---

## Acceptance Criteria

- [ ] Given `ChatState.pending` is `True`, when the message area renders, then a typing/loading indicator is visible at the end of the list.
- [ ] Given `ChatState.pending` is `True`, when the composer renders, then both the text input and the send button are disabled.
- [ ] Given a request that ends in any of the six outcomes, when its bubble is appended, then the indicator disappears and the composer re-enables.
- [ ] Given the indicator, when a slow `run_query(...)` is in flight, then it animates.
