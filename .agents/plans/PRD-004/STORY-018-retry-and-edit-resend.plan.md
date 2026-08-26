---
story: STORY-018
prd: PRD-004
slug: retry-and-edit-resend
title: "Retry on error cards and edit-and-resend on duplicate cards"
type: ENHANCEMENT
complexity: MEDIUM
epic_branch: epic/PRD-004-chat-ui-redesign
created: 2026-08-25
---

# Plan: Retry on error cards and edit-and-resend on duplicate cards

## Summary

Implement retry action on upstream/internal error cards (re-submitting original prompt unchanged via `send()`) and edit-and-resend action on duplicate cards (repopulating and focusing the composer input), respecting the in-flight `pending` guard and using the stored `prompt` field on messages.

## User Story

As an end user, I want a way out of a blocked or failed message, so that a dead-end bubble is not the end of the conversation (PRD User Story 5, Section 2 "Every dead end has an exit").

## Story Reference

- Story file: `.agents/stories/PRD-004-chat-ui-redesign/STORY-018-retry-and-edit-resend.md`
- PRD: `.agents/PRDs/PRD-004/PRD.md`

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT |
| Complexity | MEDIUM |
| Systems Affected | `chat_ui` |
| Story | STORY-018 |
| PRD | PRD-004 |
| Epic Branch | `epic/PRD-004-chat-ui-redesign` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| `reflex-docs` | Reflex components, event handlers, and `rx.set_focus` | Tasks 1, 2, 3 |

---

## Patterns to Follow

### Naming
```
// SOURCE: chat_ui/chat_ui/state.py:64-75
@rx.event(background=True)
async def send(self):
```

### Error Handling
```
// SOURCE: chat_ui/chat_ui/state.py:97-118
except OpenRouterError as exc:
```

### Tests
```
// SOURCE: tests/test_chat_state.py:174-196
@pytest.mark.asyncio
async def test_chat_state_send_success_appends_user_then_assistant_bubble(temp_db, monkeypatch):
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `chat_ui/chat_ui/components/chat.py` | UPDATE | Add `id="chat_input"` to input component for programmatic focus |
| `chat_ui/chat_ui/components/bubbles.py` | UPDATE | Add Retry button to error cards (`upstream_error`, `internal_error`) and Edit-and-resend button to duplicate cards |
| `chat_ui/chat_ui/state.py` | UPDATE | Add `retry_message(prompt)` and `edit_and_resend(prompt)` event handlers with `pending` guard and stored `prompt` usage |
| `tests/test_chat_state.py` | UPDATE | Add unit tests for retry and edit-and-resend event handlers |

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Add `id` to Chat Input Component
- **File**: `chat_ui/chat_ui/components/chat.py`
- **Action**: UPDATE
- **Implement**: Add `id="chat_input"` to `rx.input` in `chat_input()` so `rx.set_focus("chat_input")` can target it.
- **Mirror**: `chat_ui/chat_ui/components/chat.py:85-91`
- **Validate**: `pytest` passes

### Task 2: Add Recovery Action Buttons to Error and Duplicate Bubbles
- **File**: `chat_ui/chat_ui/components/bubbles.py`
- **Action**: UPDATE
- **Implement**: 
  - In `render_upstream_error` and `render_internal_error`, add a Retry button (`rx.button(copy.RETRY_LABEL, on_click=ChatState.retry_message(message.prompt), size="1", ...)`)
  - In `render_duplicate`, add an Edit and resend button (`rx.button(copy.EDIT_AND_RESEND_LABEL, on_click=ChatState.edit_and_resend(message.prompt), size="1", ...)`) alongside `copy.DUPLICATE_CHANGE_NOTICE`.
- **Mirror**: `chat_ui/chat_ui/components/bubbles.py:184-236`
- **Validate**: `pytest` passes

### Task 3: Implement Recovery Event Handlers in ChatState
- **File**: `chat_ui/chat_ui/state.py`
- **Action**: UPDATE
- **Implement**:
  - Add `retry_message(self, prompt: str)`: checks `if self.pending: return`, sets `self.input_text = prompt`, and calls/returns `self.send()` (or re-runs send logic with stored prompt).
  - Add `edit_and_resend(self, prompt: str)`: checks `if self.pending: return`, sets `self.input_text = prompt`, and returns `rx.set_focus("chat_input")`.
- **Mirror**: `chat_ui/chat_ui/state.py:64-79`
- **Validate**: `pytest` passes

### Task 4: Add Unit Tests for Recovery Actions
- **File**: `tests/test_chat_state.py`
- **Action**: UPDATE
- **Implement**: Add unit tests verifying `retry_message` re-submits prompt through `send()` and respects `pending`, and `edit_and_resend` repopulates `input_text`, focuses input, and respects `pending`.
- **Mirror**: `tests/test_chat_state.py:174-210`
- **Validate**: `pytest` passes

---

## End-to-End Tests

- [ ] Trigger upstream/internal error, click Retry → re-submits original prompt unchanged via `send()`
- [ ] Trigger duplicate block, click "Edit and resend" → repopulates composer and focuses without sending, showing `DUPLICATE_CHANGE_NOTICE`
- [ ] Verify `pending` guard ignores recovery actions while request is in-flight
- [ ] Verify recovery actions use stored `prompt` field on message

---

## Validation

```bash
pytest
```

---

## Acceptance Criteria

- [ ] Given an `upstream_error` or `internal_error` card, when its Retry action is used, then the original prompt is re-submitted unchanged through the same `send()` path, producing a new bubble for whatever outcome results.
- [ ] Given a `duplicate` card, when its "Edit and resend" action is used, then the composer is repopulated with the original prompt and focused, without sending anything automatically.
- [ ] Given `pending` is `True`, when a Retry or edit-and-resend action is triggered, then it is ignored — the single in-flight guard from [[STORY-003]] applies to recovery actions too.
- [ ] Given the duplicate card, when the edit-and-resend action is shown, then it is paired with copy stating the text must change to go through, so resending the identical prompt is not silently invited into a block loop (Risk 4).
- [ ] Given any recovery action, when it runs, then it uses the `prompt` field stored on the message ([[STORY-005]]) — no re-derivation from rendered bubble text.
- [ ] All tasks completed
- [ ] Tests pass
