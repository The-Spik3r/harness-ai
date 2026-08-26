---
story: STORY-012
prd: PRD-004
plan: .agents/plans/PRD-004-chat-ui-redesign/completed/STORY-012-pending-indicator-composer-lock.plan.md
epic_branch: epic/PRD-004-chat-ui-redesign
commit: PENDING
status: COMPLETE
completed: 2026-08-24
---

# Implementation Report — STORY-012: Typing indicator and disabled composer while a request is in flight

**Plan**: `.agents/plans/PRD-004-chat-ui-redesign/completed/STORY-012-pending-indicator-composer-lock.plan.md`
**Epic Branch**: `epic/PRD-004-chat-ui-redesign`
**Commit**: PENDING

## Summary

Implemented a visual typing/loading indicator (`render_pending_indicator()`) visible at the end of the message list when `ChatState.pending` is `True`, and locked/disabled both the text input and send button in the composer form when a request is in flight. Both automatically reset/re-enable when the request finishes on any success or error outcome.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Add pending indicator copy | `chat_ui/chat_ui/copy.py` | ✅ |
| 2 | Implement pending indicator renderer | `chat_ui/chat_ui/components/bubbles.py` | ✅ |
| 3 | Render pending indicator in message list | `chat_ui/chat_ui/components/chat.py` | ✅ |
| 4 | Disable composer during pending state | `chat_ui/chat_ui/components/chat.py` | ✅ |
| 5 | Verify tests and build | `tests/test_chat_state.py` | ✅ (219 passed) |

## Validation Results

| Check | Result |
|-------|--------|
| pytest | ✅ (219 passed) |
| Async pending state reset | ✅ Verified by `test_chat_state_pending_resets_on_all_outcomes` and `test_chat_state_concurrent_send_guard` |

## Files Changed

| File | Action | Purpose |
|------|--------|---------|
| `chat_ui/chat_ui/copy.py` | UPDATE | Add pending indicator copy |
| `chat_ui/chat_ui/components/bubbles.py` | UPDATE | Add `render_pending_indicator()` |
| `chat_ui/chat_ui/components/chat.py` | UPDATE | Render pending indicator in message list & lock input during pending |

## Deviations from Plan

None.

## Tests Written

The existing test cases `test_chat_state_pending_resets_on_all_outcomes` and `test_chat_state_concurrent_send_guard` directly cover the backend behavior of the `pending` flag lifecycle across all outcome paths.

## Acceptance Criteria

- [x] Given `ChatState.pending` is `True`, when the message area renders, then a typing/loading indicator is visible at the end of the list.
- [x] Given `ChatState.pending` is `True`, when the composer renders, then both the text input and the send button are disabled.
- [x] Given a request that ends in any of the six outcomes, when its bubble is appended, then the indicator disappears and the composer re-enables.
- [x] Given the indicator, when a slow `run_query(...)` is in flight, then it animates.
