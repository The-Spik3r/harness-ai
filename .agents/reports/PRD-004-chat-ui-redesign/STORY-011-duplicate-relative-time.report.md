---
story: STORY-011
prd: PRD-004
plan: .agents/plans/PRD-004-chat-ui-redesign/completed/STORY-011-duplicate-relative-time.plan.md
epic_branch: epic/PRD-004-chat-ui-redesign
commit: 7489579
status: COMPLETE
completed: 2026-08-24
---

# Implementation Report — STORY-011: Duplicate card — humanized relative time and 24h window release

**Plan**: `.agents/plans/PRD-004-chat-ui-redesign/completed/STORY-011-duplicate-relative-time.plan.md`
**Epic Branch**: `epic/PRD-004-chat-ui-redesign`
**Commit**: PENDING

## Summary

Implemented humanized relative time formatting, absolute timestamp display, 24-hour window release calculations, and Risk 4 change notices for duplicate cards in the chat UI, along with robust fallback handling for empty or unparseable timestamps ("No silent drops").

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Add duplicate copy templates | `chat_ui/chat_ui/copy.py` | ✅ |
| 2 | Implement humanized relative time, absolute timestamp, 24h release, and fallback | `chat_ui/chat_ui/components/bubbles.py` | ✅ |
| 3 | Add unit tests for duplicate formatting and edge cases | `tests/test_copy.py` | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | ✅ |
| Frontend lint / pytest | ✅ (219 passed) |
| E2E / Unit Tests | ✅ |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `chat_ui/chat_ui/copy.py` | UPDATE | +3/-0 |
| `chat_ui/chat_ui/components/bubbles.py` | UPDATE | +55/-20 |
| `tests/test_copy.py` | UPDATE | +32/-0 |

## Deviations from Plan

None.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_copy.py` | `test_duplicate_formatting_relative_and_window`, `test_duplicate_formatting_empty_and_unparseable_fallback` |

## Acceptance Criteria

- [x] Given a `duplicate` message with `first_query_at`, when rendered, then the card shows a humanized relative time plus the absolute timestamp — e.g. "Already sent 2 hours ago (2026-08-21T10:30:00Z)".
- [x] Given the same message, when rendered, then the card states when the 24-hour window releases, derived as `first_query_at` + 24 hours.
- [x] Given a `first_query_at` that is empty or unparseable, when rendered, then the card still renders with the raw value and no crash — an error in time formatting must not swallow the bubble ("No silent drops").
- [x] Given the duplicate card copy, when read, then it states that the text must change for a resend to go through (Risk 4).
