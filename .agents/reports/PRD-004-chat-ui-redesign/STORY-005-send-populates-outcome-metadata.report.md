---
story: STORY-005
prd: PRD-004
plan: .agents/plans/PRD-004-chat-ui-redesign/completed/STORY-005-send-populates-outcome-metadata.plan.md
epic_branch: epic/PRD-004-chat-ui-redesign
commit: 1f7c642
status: COMPLETE
completed: 2026-08-21
---

# Implementation Report — STORY-005: send() populates every metadata field from each pipeline outcome

**Plan**: `.agents/plans/PRD-004-chat-ui-redesign/completed/STORY-005-send-populates-outcome-metadata.plan.md`
**Epic Branch**: `epic/PRD-004-chat-ui-redesign`
**Commit**: PENDING

## Summary

Populated every metadata field from each pipeline outcome onto appended `ChatMessage` instances in `ChatState.send()`, consuming all 6 response fields for success, preserving unformatted reasons and timestamps for duplicates, pattern detection for injections, and separating copy keys/labels from exception details.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Update `ChatState.send()` to populate all metadata fields across all outcomes | `chat_ui/chat_ui/state.py` | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | ✅ |
| Tests | ✅ (206 passed) |
| E2E / Structural tests | ✅ |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `chat_ui/chat_ui/state.py` | UPDATE | +45/-25 |
| `tests/test_chat_state.py` | UPDATE | +25/-30 |

## Deviations from Plan

None.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_chat_state.py` | `test_chat_state_send_success_appends_user_then_assistant_bubble`, `test_chat_state_send_duplicate_blocked_appends_system_bubble`, `test_chat_state_send_suspicious_blocked_appends_system_bubble`, `test_chat_state_send_pii_redactor_error_appends_system_bubble`, `test_chat_state_send_unexpected_exception_appends_system_bubble` |

## Acceptance Criteria

- [x] Given a `QuerySuccessResponse`, when the assistant message is appended, then `content == result.response`, `model_used`, `tokens_used`, `audit_id`, `pii_redacted` and `pii_entities` (from `pii_entities_masked`) all land on the message — 6 of 6 response fields consumed.
- [x] Given a `QueryBlockedDuplicateResponse`, when the duplicate message is appended, then `kind == "duplicate"`, `content == result.reason` (unformatted) and `first_query_at == result.first_query_at`.
- [x] Given a `QueryBlockedSuspiciousResponse`, when the injection message is appended, then `kind == "injection"`, `content == result.reason` and `pattern == result.pattern`.
- [x] Given any of the four exception paths, when the error message is appended, then `detail` carries exception text and `content` carries copy key/label.
- [x] Given every appended non-user message, `prompt` holds original prompt text.
