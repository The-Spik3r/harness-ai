---
story: STORY-010
prd: PRD-004
plan: .agents/plans/PRD-004-chat-ui-redesign/STORY-010-success-metadata-footer.plan.md
epic_branch: epic/PRD-004-chat-ui-redesign
commit: null
status: COMPLETE
completed: 2026-08-24
---

# Implementation Report — STORY-010: Assistant bubble footer with model_used, tokens_used and audit_id

**Plan**: `.agents/plans/PRD-004-chat-ui-redesign/STORY-010-success-metadata-footer.plan.md`
**Epic Branch**: `epic/PRD-004-chat-ui-redesign`

## Summary

Implemented a subdued metadata footer in successful assistant message bubbles displaying `model_used`, `tokens_used`, and `audit_id` (e.g., `gpt-4 · 45 tokens · #127`), using centralized copy templates from `chat_ui/copy.py`.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Add metadata footer to render_assistant | `chat_ui/chat_ui/components/bubbles.py` | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import / Python syntax | ✅ |
| Frontend lint / compile | ✅ |
| Tests | ✅ (217 passed) |
| E2E / Unit Verification | ✅ |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `chat_ui/chat_ui/components/bubbles.py` | UPDATE | +22/-1 |
| `tests/test_success_metadata_footer.py` | CREATE | +32 |

## Deviations from Plan

None.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_success_metadata_footer.py` | `test_footer_copy_constants`, `test_chat_message_metadata_fields` |

## Acceptance Criteria

- [x] Given a successful exchange, when the assistant bubble renders, then a subdued footer shows `model_used`, `tokens_used` and `audit_id`.
- [x] Given the footer, when rendered, then it is visually subdued relative to the response text and does not compete with it for attention.
- [x] Given a non-assistant message kind, when rendered, then no metadata footer appears.
- [x] Given `audit_id`, when displayed, then it matches the `audit_id` of the row `run_query(...)` wrote.
