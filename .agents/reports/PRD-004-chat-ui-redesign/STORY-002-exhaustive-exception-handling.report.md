---
story: STORY-002
prd: PRD-004
plan: .agents/plans/PRD-004-chat-ui-redesign/completed/STORY-002-exhaustive-exception-handling.plan.md
epic_branch: epic/PRD-004-chat-ui-redesign
commit: 59899ca
status: COMPLETE
completed: 2026-08-21
---

# Implementation Report — STORY-002: Exhaustive except arms in send(): PiiRedactorError + catch-all

**Plan**: `.agents/plans/PRD-004-chat-ui-redesign/completed/STORY-002-exhaustive-exception-handling.plan.md`
**Epic Branch**: `epic/PRD-004-chat-ui-redesign`
**Commit**: `59899ca`

## Summary

Extended `ChatState.send()` error handling to catch `PiiRedactorError` and added a catch-all `except Exception` arm, ensuring every exception path terminates in a visible system error bubble and no message is silently dropped. Added comprehensive regression tests in `tests/test_chat_state.py`.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Import `PiiRedactorError` and extend except arms in `send()` | `chat_ui/chat_ui/state.py` | ✅ |
| 2 | Add regression tests for `PiiRedactorError` and unexpected exceptions | `tests/test_chat_state.py` | ✅ |
| 3 | Run verification test suite | Test suite | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | ✅ |
| Frontend lint / test | ✅ |
| Tests | ✅ (203 passed) |
| E2E / Unit Tests | ✅ |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `chat_ui/chat_ui/state.py` | UPDATE | +10/-2 |
| `tests/test_chat_state.py` | UPDATE | +35/-0 |
| `tests/test_pii_redaction_integration.py` | UPDATE | +0/-1 |

## Deviations from Plan

None.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_chat_state.py` | `test_chat_state_send_pii_redactor_error_appends_system_bubble`, `test_chat_state_send_unexpected_exception_appends_system_bubble` |

## Acceptance Criteria

- [x] Given `run_query(...)` raises `PiiRedactorError`, when `send()` handles it, then a bubble carrying the exception text is appended instead of nothing being appended at all.
- [x] Given `run_query(...)` raises an arbitrary unexpected exception, when `send()` handles it, then a bubble is still appended — a catch-all `except Exception` arm guarantees no path ends without a bubble.
- [x] Given `DuplicateCheckError` or `OpenRouterError`, when either is raised, then a bubble is still appended as today — no regression on the two arms that already exist.
- [x] Given a test forcing each of the four exception paths, when it asserts on `state.messages`, then the message count grew by exactly one bubble in every case.
- [x] Given `app/`, when the diff is inspected, then no file under it is modified.
