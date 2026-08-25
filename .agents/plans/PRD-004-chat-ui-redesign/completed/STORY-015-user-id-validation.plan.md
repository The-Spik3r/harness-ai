---
story: STORY-015
prd: PRD-004
slug: user-id-validation
title: "Inline validation error on empty user_id submit"
type: ENHANCEMENT
complexity: SMALL
epic_branch: epic/PRD-004-chat-ui-redesign
created: 2026-08-25
---

# Plan: Inline validation error on empty user_id submit

## Summary

Implement inline validation error on empty or whitespace-only `user_id` submissions in `ChatState.submit_user_id()`, sourcing the error message from `copy.py` and rendering it visibly in `user_id_prompt()`. This replaces the silent return on empty input and unifies validation across initial entry and the header's change-user action.

## User Story

As an end user, I want an empty user ID submission to tell me what is wrong, so that the form does not silently do nothing and leave me stuck at the door.

## Story Reference

- Story file: `.agents/stories/PRD-004-chat-ui-redesign/STORY-015-user-id-validation.md`
- PRD: `.agents/PRDs/PRD-004-chat-ui-redesign/PRD.md`

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT |
| Complexity | SMALL |
| Systems Affected | `chat_ui/chat_ui/copy.py`, `chat_ui/chat_ui/state.py`, `chat_ui/chat_ui/components/chat.py`, `tests/test_chat_state.py` |
| Story | STORY-015 |
| PRD | PRD-004 |
| Epic Branch | `epic/PRD-004-chat-ui-redesign` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| reflex-docs | Reflex state, event handlers, and conditional component rendering | Tasks 2, 3 |

---

## Patterns to Follow

### Naming
```python
// SOURCE: chat_ui/chat_ui/state.py:26-28
    user_id: str = ""
    user_id_input: str = ""
    pending: bool = False
```

### Error Handling / Validation
```python
// SOURCE: chat_ui/chat_ui/state.py:42-46
    @rx.event
    def submit_user_id(self):
        text = self.user_id_input.strip()
        if not text:
            return
        self.user_id = text
```

### Tests
```python
// SOURCE: tests/test_chat_state.py:460-471
def test_chat_state_empty_and_reset_user_id():
    state = ChatState(_reflex_internal_init=True)
    ...
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `chat_ui/chat_ui/copy.py` | UPDATE | Add centralized `USER_ID_VALIDATION_ERROR` copy string |
| `chat_ui/chat_ui/state.py` | UPDATE | Add `user_id_error` state var, update `submit_user_id()` and `reset_user_id()` |
| `chat_ui/chat_ui/components/chat.py` | UPDATE | Render conditional inline validation error message in `user_id_prompt()` |
| `tests/test_chat_state.py` | UPDATE | Add unit tests for empty/whitespace validation, error clearing, and reset |

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Add user ID validation copy to `copy.py`

- **File**: `chat_ui/chat_ui/copy.py`
- **Action**: UPDATE
- **Implement**: Add `USER_ID_VALIDATION_ERROR = "Please enter a user ID to continue"` under Session / User ID Entry section.
- **Mirror**: `chat_ui/chat_ui/copy.py:8-11`
- **Validate**: `python -c "from chat_ui.chat_ui.copy import USER_ID_VALIDATION_ERROR; print(USER_ID_VALIDATION_ERROR)"`

### Task 2: Add `user_id_error` and update `submit_user_id` / `reset_user_id` in `state.py`

- **File**: `chat_ui/chat_ui/state.py`
- **Action**: UPDATE
- **Implement**: Add `user_id_error: str = ""` state variable. In `submit_user_id()`, if `not text`, set `self.user_id_error = USER_ID_VALIDATION_ERROR` and return. Otherwise, set `self.user_id_error = ""` and `self.user_id = text`. In `reset_user_id()`, also reset `self.user_id_error = ""`.
- **Mirror**: `chat_ui/chat_ui/state.py:25-28, 42-52`
- **Validate**: `pytest` passes

### Task 3: Render inline validation error in `user_id_prompt()`

- **File**: `chat_ui/chat_ui/components/chat.py`
- **Action**: UPDATE
- **Implement**: Import `USER_ID_VALIDATION_ERROR` from `chat_ui.copy`. Inside `user_id_prompt()`, add an `rx.cond(ChatState.user_id_error != "", rx.text(ChatState.user_id_error, color="red", size="2"), rx.fragment())` below the `rx.input`.
- **Mirror**: `chat_ui/chat_ui/components/chat.py:48-68`
- **Validate**: `pytest` passes

### Task 4: Add unit tests for validation behavior

- **File**: `tests/test_chat_state.py`
- **Action**: UPDATE
- **Implement**: Add unit tests: `test_chat_state_submit_empty_user_id_shows_error`, `test_chat_state_submit_valid_user_id_clears_error_and_sets_user_id`, `test_chat_state_reset_user_id_clears_error`.
- **Mirror**: `tests/test_chat_state.py:460-471`
- **Validate**: `pytest` passes successfully

---

## End-to-End Tests

- [ ] Start backend & frontend, load app → see `user_id` entry form.
- [ ] Submit empty or whitespace-only `user_id` → visible red validation error appears ("Please enter a user ID to continue").
- [ ] Submit valid `user_id` → error clears, session starts, header shows `user_id` and empty state / chat interface.
- [ ] Click "Change user" in header → returns to `user_id` prompt with cleared state.
- [ ] Submit empty again → same validation error appears.

---

## Validation

```bash
pytest
```

---

## Acceptance Criteria

- [ ] Given the `user_id` form, when it is submitted empty or whitespace-only, then a visible validation error appears next to the field, replacing the silent `return` at `state.py:41-43`.
- [ ] Given a visible validation error, when a valid `user_id` is then submitted, then the error clears and the session starts.
- [ ] Given the change-user action in the header (STORY-014), when an empty value is submitted there, then the same validation applies — one validation path, not two.
- [ ] Given the validation message, when read, then it comes from `copy.py` (STORY-007).
- [ ] All tasks completed
- [ ] Backend tests pass
- [ ] Follows existing patterns
