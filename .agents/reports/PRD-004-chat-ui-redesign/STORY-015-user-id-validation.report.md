---
story: STORY-015
prd: PRD-004
plan: .agents/plans/PRD-004-chat-ui-redesign/completed/STORY-015-user-id-validation.plan.md
epic_branch: epic/PRD-004-chat-ui-redesign
commit: PENDING
status: COMPLETE
completed: 2026-08-25
---

# Implementation Report — STORY-015: Inline validation error on empty user_id submit

**Plan**: `.agents/plans/PRD-004-chat-ui-redesign/completed/STORY-015-user-id-validation.plan.md`
**Epic Branch**: `epic/PRD-004-chat-ui-redesign`
**Commit**: PENDING

## Summary

Implemented inline validation error on empty or whitespace-only `user_id` submissions in `ChatState.submit_user_id()`, sourcing the error message from `copy.py` and rendering it conditionally in `user_id_prompt()`. Replaced the silent return on empty input with visible error handling, unifying validation across initial entry and the header's change-user action.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Add user ID validation copy | `chat_ui/chat_ui/copy.py` | ✅ |
| 2 | Add `user_id_error` state var and update submit/reset | `chat_ui/chat_ui/state.py` | ✅ |
| 3 | Render inline validation error in `user_id_prompt()` | `chat_ui/chat_ui/components/chat.py` | ✅ |
| 4 | Add unit tests for validation behavior | `tests/test_chat_state.py` | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend tests (`pytest`) | ✅ (223 passed) |
| Frontend / state logic | ✅ |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `chat_ui/chat_ui/copy.py` | UPDATE | +1 |
| `chat_ui/chat_ui/state.py` | UPDATE | +12/-3 |
| `chat_ui/chat_ui/components/chat.py` | UPDATE | +9/-4 |
| `tests/test_chat_state.py` | UPDATE | +35 |

## Deviations from Plan

None.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_chat_state.py` | `test_chat_state_submit_empty_or_whitespace_user_id_shows_error`, `test_chat_state_submit_valid_user_id_clears_error_and_sets_user`, `test_chat_state_reset_user_id_clears_error` |

## Acceptance Criteria

- [x] Given the `user_id` form, when it is submitted empty or whitespace-only, then a visible validation error appears next to the field, replacing the silent `return` at `state.py:41-43`.
- [x] Given a visible validation error, when a valid `user_id` is then submitted, then the error clears and the session starts.
- [x] Given the change-user action in the header (STORY-014), when an empty value is submitted there, then the same validation applies — one validation path, not two.
- [x] Given the validation message, when read, then it comes from `copy.py` (STORY-007).
