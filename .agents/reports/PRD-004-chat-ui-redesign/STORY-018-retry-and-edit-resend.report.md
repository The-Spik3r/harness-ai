---
story: STORY-018
prd: PRD-004
plan: .agents/plans/PRD-004-chat-ui-redesign/completed/STORY-018-retry-and-edit-resend.plan.md
epic_branch: epic/PRD-004-chat-ui-redesign
commit: null
status: COMPLETE
completed: 2026-08-25
---

# Implementation Report — STORY-018: Retry on error cards and edit-and-resend on duplicate cards

**Plan**: `.agents/plans/PRD-004-chat-ui-redesign/completed/STORY-018-retry-and-edit-resend.plan.md`
**Epic Branch**: `epic/PRD-004-chat-ui-redesign`

## Summary

Implemented retry action on upstream and internal error cards (re-submitting the original prompt unchanged via the shared `send()` / `_do_send()` code path) and edit-and-resend action on duplicate cards (repopulating the composer with the original prompt and focusing the input without auto-sending), respecting the in-flight `pending` guard and using the stored `prompt` field on messages.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Add `id="chat_input"` to input component for programmatic focus | `chat_ui/chat_ui/components/chat.py` | ✅ |
| 2 | Add Retry button to error cards and Edit-and-resend button to duplicate cards | `chat_ui/chat_ui/components/bubbles.py` | ✅ |
| 3 | Implement recovery event handlers (`retry_message`, `edit_and_resend`) and shared pipeline in `ChatState` | `chat_ui/chat_ui/state.py` | ✅ |
| 4 | Add unit tests for retry and edit-and-resend recovery actions | `tests/test_chat_state.py` | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Test suite (`pytest`) | ✅ (231 passed) |
| Retry message test | ✅ |
| Edit and resend test | ✅ |
| Pending guard test | ✅ |

## Files Changed

| File | Action | Purpose |
|------|--------|---------|
| `chat_ui/chat_ui/components/chat.py` | UPDATE | Added `id="chat_input"` to input component |
| `chat_ui/chat_ui/components/bubbles.py` | UPDATE | Added Retry button and Edit-and-resend button with appropriate styling and copy |
| `chat_ui/chat_ui/state.py` | UPDATE | Implemented `retry_message`, `edit_and_resend`, and shared `_do_send` pipeline |
| `tests/test_chat_state.py` | UPDATE | Added unit tests verifying retry resubmission, composer repopulation/focus, and pending guard |
| `.agents/stories/PRD-004-chat-ui-redesign/STORY-018-retry-and-edit-resend.md` | UPDATE | Marked as done |
| `.agents/PRDs/PRD-004-chat-ui-redesign/index.md` | UPDATE | Updated story status and progress |

## Deviations from Plan

None. Implementation matched the plan precisely.

## Tests Written

- `test_retry_message_resubmits_prompt`: Asserts that triggering `retry_message` re-submits the original prompt unchanged through the pipeline and produces the expected success bubble.
- `test_edit_and_resend_repopulates_composer`: Asserts that triggering `edit_and_resend` repopulates `input_text` with the original prompt without auto-sending.
- `test_recovery_actions_ignored_when_pending`: Asserts that when `pending` is `True`, both `retry_message` and `edit_and_resend` are safely ignored.

## Acceptance Criteria

- [x] Given an `upstream_error` or `internal_error` card, when its Retry action is used, then the original prompt is re-submitted unchanged through the same `send()` path, producing a new bubble for whatever outcome results.
- [x] Given a `duplicate` card, when its "Edit and resend" action is used, then the composer is repopulated with the original prompt and focused, without sending anything automatically.
- [x] Given `pending` is `True`, when a Retry or edit-and-resend action is triggered, then it is ignored — the single in-flight guard applies to recovery actions too.
- [x] Given the duplicate card, when the edit-and-resend action is shown, then it is paired with copy stating the text must change to go through, so resending the identical prompt is not silently invited into a block loop (Risk 4).
- [x] Given any recovery action, when it runs, then it uses the `prompt` field stored on the message — no re-derivation from rendered bubble text.
- [x] All existing tests pass.
