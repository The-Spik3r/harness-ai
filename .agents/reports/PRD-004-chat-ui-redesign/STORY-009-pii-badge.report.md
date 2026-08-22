---
story: STORY-009
prd: PRD-004
plan: .agents/plans/PRD-004-chat-ui-redesign/completed/STORY-009-pii-badge.plan.md
epic_branch: epic/PRD-004-chat-ui-redesign
commit: PENDING
status: COMPLETE
completed: 2026-08-21
---

# Implementation Report — STORY-009: Informational PII badge on assistant bubbles

**Plan**: `.agents/plans/PRD-004-chat-ui-redesign/completed/STORY-009-pii-badge.plan.md`
**Epic Branch**: `epic/PRD-004-chat-ui-redesign`

## Summary

Implemented an informational, quiet inline PII badge in assistant message bubbles when `pii_redacted` is true, listing the masked entity types using centralized copy templates from `chat_ui/copy.py`.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Add PII badge to render_assistant | `chat_ui/chat_ui/components/bubbles.py` | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import / Python syntax | ✅ |
| Frontend lint / compile | ✅ |
| Tests | ✅ (215 passed) |
| E2E / Unit Verification | ✅ |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `chat_ui/chat_ui/components/bubbles.py` | UPDATE | +24/-1 |
| `tests/test_pii_badge.py` | CREATE | +35 |

## Deviations from Plan

None.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_pii_badge.py` | `test_pii_badge_copy_templates`, `test_chat_message_pii_fields` |

## Acceptance Criteria

- [x] Given an assistant message whose `pii_redacted` is `true`, when rendered, then a badge appears listing the entity types from `pii_entities`.
- [x] Given an assistant message whose `pii_redacted` is `false`, when rendered, then no badge appears at all.
- [x] Given the badge, when rendered, then it is quiet and inline — never a modal, never a confirmation step, never a gate.
- [x] Given the badge copy, when read, then it describes masking as covering the exchange.
- [x] Given the badge, when rendered, then it shows entity types only.
