---
story: STORY-014
prd: PRD-004
plan: .agents/plans/PRD-004-chat-ui-redesign/completed/STORY-014-shell-header-empty-state.plan.md
epic_branch: epic/PRD-004-chat-ui-redesign
commit: null
status: COMPLETE
completed: 2026-08-24
---

# Implementation Report — STORY-014: Redesigned shell — header with session identity, and empty state

**Plan**: `.agents/plans/PRD-004-chat-ui-redesign/completed/STORY-014-shell-header-empty-state.plan.md`
**Epic Branch**: `epic/PRD-004-chat-ui-redesign`
**Commit**: null

## Summary

Implemented the redesigned application shell (`chat_ui/chat_ui/components/shell.py`) which includes:
- A beautiful header showing the Harness AI brand, Enterprise Guardrail badge, session `user_id`, a "Change user" button, and a model selector placeholder slot.
- A fully designed and modern empty state replacing the hardcoded `WELCOME_MESSAGE` dict, which highlights the active PII Masking, Prompt Injection Defense, and 24h Query Deduplication features.
- Dynamic layout composition in `chat_ui.py` so that when `messages` is empty, the empty state is displayed, and when messages are present, the scrollable `message_list` is rendered.
- Added a `reset_user_id` event handler to `ChatState` which clears `user_id` and input so users can switch session identity without requiring a page reload.
- Updated both `test_copy.py` and `test_chat_state.py` to assert the presence of these new components, correct copy text centralisation, and the user reset state logic.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Create header and empty state components | `chat_ui/chat_ui/components/shell.py` | ✅ |
| 2 | Update copy constants with centralisation | `chat_ui/chat_ui/copy.py` | ✅ |
| 3 | Remove welcome message and add reset event | `chat_ui/chat_ui/state.py` | ✅ |
| 4 | Compose shell layout under index page | `chat_ui/chat_ui/chat_ui.py` | ✅ |
| 5 | Verify and add unit tests | `tests/` | ✅ |

## Validation Results

| Check | Result |
|-------|-------|
| Backend import | ✅ |
| Frontend lint | ✅ |
| Tests | ✅ (220 passed) |
| E2E | ✅ |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `chat_ui/chat_ui/components/shell.py` | CREATE | +129 |
| `chat_ui/chat_ui/copy.py` | UPDATE | +13/-1 |
| `chat_ui/chat_ui/state.py` | UPDATE | +24/-28 |
| `chat_ui/chat_ui/chat_ui.py` | UPDATE | +11/-11 |
| `tests/test_copy.py` | UPDATE | +23/-5 |
| `tests/test_chat_state.py` | UPDATE | +13/-2 |

## Deviations from Plan

None.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_copy.py` | `test_copy_constants_exist_and_not_empty` expanded to verify new copy strings |
| `tests/test_chat_state.py` | `test_chat_state_empty_and_reset_user_id` to verify empty start state and user reset event handler |

## Acceptance Criteria

- [x] Given `chat_ui/chat_ui/components/shell.py`, when it is created, then it provides the header (harness identity, session `user_id`, slot for the model selector) and the empty state, and `chat_ui/chat_ui.py` composes header → message area → composer.
- [x] Given an active session, when the header renders, then the current `user_id` is visible and there is an action to change it without reloading the page.
- [x] Given the change-user action, when used, then the session `user_id` is replaced and subsequent sends pass the new value to `run_query(...)`.
- [x] Given a conversation with no messages, when the page renders, then a designed empty state is shown and the hardcoded `WELCOME_MESSAGE` dict at `state.py:8-11` is gone — the app no longer fakes an assistant turn that the pipeline never produced.
- [x] Given every string in the shell, when grepped, then it comes from `copy.py`.
