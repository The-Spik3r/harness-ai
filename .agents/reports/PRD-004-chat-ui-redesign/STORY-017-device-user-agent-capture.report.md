---
story: STORY-017
prd: PRD-004
plan: .agents/plans/PRD-004-chat-ui-redesign/completed/STORY-017-device-user-agent-capture.plan.md
epic_branch: epic/PRD-004-chat-ui-redesign
commit: null
status: COMPLETE
completed: 2026-08-25
---

# Implementation Report — STORY-017: Populate device from the browser User-Agent on chat sends

**Plan**: `.agents/plans/PRD-004-chat-ui-redesign/completed/STORY-017-device-user-agent-capture.plan.md`
**Epic Branch**: `epic/PRD-004-chat-ui-redesign`

## Summary

Captured the browser User-Agent from Reflex request headers (`self.router.headers.raw_headers`) during chat message submission in `ChatState.send()`, passing it as the `device` parameter to `run_query(...)` instead of hardcoded `None`, ensuring chat-originated audit rows record the device while gracefully falling back to `None` when unavailable.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Extract User-Agent in `ChatState.send()` and pass to `run_query(...)` | `chat_ui/chat_ui/state.py` | ✅ |
| 2 | Add unit tests verifying User-Agent capture and fallback to `None` | `tests/test_chat_state.py` | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Test suite (`pytest`) | ✅ (228 passed) |
| Device capture test | ✅ |
| Fallback test | ✅ |

## Files Changed

| File | Action | Purpose |
|------|--------|-------|
| `chat_ui/chat_ui/state.py` | UPDATE | Extract browser User-Agent from `self.router.headers.raw_headers` and pass to `run_query(...)` |
| `tests/test_chat_state.py` | UPDATE | Added unit tests for User-Agent capture and fallback |
| `.agents/stories/PRD-004-chat-ui-redesign/STORY-017-device-user-agent-capture.md` | UPDATE | Marked as done |
| `.agents/PRDs/PRD-004-chat-ui-redesign/index.md` | UPDATE | Updated story status to done and progress to 58% |

## Deviations from Plan

None. Implementation matched the plan precisely.

## Tests Written

- `test_chat_state_send_populates_device_from_router_headers`: Asserts that when `self.router.headers.raw_headers` provides a user-agent, it is correctly passed to `run_query(...)`.
- `test_chat_state_send_device_fallback_when_headers_missing`: Asserts that when the router or headers are unavailable, `device` falls back to `None` and message send succeeds without error.

## Acceptance Criteria

- [x] Given a message sent from the chat, when `run_query(...)` is called, then `device` carries the browser User-Agent instead of `None`.
- [x] Given that message, when its audit row is inspected, then `device` is non-null.
- [x] Given the value written, when compared against an API-originated row, then it occupies the same column and `QueryRequest.device` contract — no schema change.
- [x] Given a session where the User-Agent is unavailable, when a message is sent, then `device` falls back to `None` and send succeeds.
- [x] All existing tests pass.
