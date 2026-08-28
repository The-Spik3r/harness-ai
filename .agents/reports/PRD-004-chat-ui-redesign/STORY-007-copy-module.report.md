---
story: STORY-007
prd: PRD-004
plan: .agents/plans/PRD-004-chat-ui-redesign/completed/STORY-007-copy-module.plan.md
epic_branch: epic/PRD-004-chat-ui-redesign
commit: 2d89467
status: COMPLETE
completed: 2026-08-21
---

# Implementation Report — STORY-007: Centralize all user-facing copy in chat_ui/copy.py

**Plan**: `.agents/plans/PRD-004-chat-ui-redesign/completed/STORY-007-copy-module.plan.md`
**Epic Branch**: `epic/PRD-004-chat-ui-redesign`
**Commit**: `2d89467`

## Summary

Created the centralized `chat_ui/chat_ui/copy.py` module holding all user-facing copy, templates, labels, and risk mitigations (Risk 4 duplicate warning, Risk 5 PII exchange phrasing, Risk 7 OpenRouter upstream error naming) across the chat UI.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Create centralized copy module | `chat_ui/chat_ui/copy.py` | ✅ |
| 2 | Write comprehensive unit tests for copy module | `tests/test_copy.py` | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Python module import | ✅ |
| Tests | ✅ (213 passed, 0 failed) |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `chat_ui/chat_ui/copy.py` | CREATE | +35 |
| `tests/test_copy.py` | CREATE | +55 |

## Deviations from Plan

None. Implementation matched the plan exactly.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_copy.py` | `test_copy_constants_exist_and_not_empty`, `test_risk_5_pii_exchange_phrasing`, `test_risk_4_duplicate_change_notice`, `test_risk_7_upstream_error_naming`, `test_footer_formatting_constants` |

## Acceptance Criteria

- [x] Given `chat_ui/chat_ui/copy.py`, when it is created, then it holds every user-facing string the chat renders: the six bubble labels, the PII badge template, the footer separators, the retry and edit-and-resend labels, the empty state, the composer placeholder and the `user_id` prompt and validation messages.
- [x] Given the PII badge copy, when read, then it says the masking applies to the exchange (e.g. "masked in this exchange"), never wording that implies only the user's prompt (Risk 5).
- [x] Given the duplicate-bubble copy, when read, then it states that the text must change for the resend to go through (Risk 4).
- [x] All tasks completed.
