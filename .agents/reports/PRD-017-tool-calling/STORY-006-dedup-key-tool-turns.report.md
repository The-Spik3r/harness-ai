---
story: STORY-006
prd: PRD-017
plan: .agents/plans/PRD-017-tool-calling/completed/STORY-006-dedup-key-tool-turns.plan.md
epic_branch: epic/PRD-017-tool-calling
commit: pending
status: COMPLETE
completed: 2026-11-15
---

# Implementation Report — STORY-006: dedup_key over tool turns

## Summary

`dedup_key` keys tool turns (PRD-017 D4, Section 6.4). Tool-free conversations take the unchanged PRD-009 path (keys pinned as literals, re-confirmed against the unmodified code first). Tool-shaped ones anchor on the last user turn, put every turn in the prefix with the anchor's slot as null, and frame calls and tool turns. Refusals match step 0's D6 rules. The `_keyed` stub in `tests/test_query_pipeline_tools.py` is gone.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 0 | Re-confirm six tool-free pins before editing | (script) | done |
| 1 | Tool-shaped framing, `tool` role, refusals | `app/services/duplicate_checker.py` | done |
| 2 | Unit tests (AC1-AC5) | `tests/test_dedup_key.py` | done |
| 3 | Register superseded test name | `tests/test_pii_redaction_integration.py` | done |
| 4 | Pipeline tests | `tests/test_query_pipeline_dedup_key.py` | done |
| 5 | Drop `_keyed` stub | `tests/test_query_pipeline_tools.py` | done |
| 6 | Targeted run | - | done |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| Tests (7 files) | 145 passed, 1 failed on first run (test bug: blocked response has no audit_id), fixed; the two dedup files rerun: 58 passed. Net 146 passed, 0 failed, 0 skipped |
| Full suite | deferred to orchestrator (user decision) |

## Deviations from Plan

- The duplicate-arm assertion in `test_npm_test_twice_is_not_held_but_a_resend_is` reads the newest audit row, since `QueryBlockedDuplicateResponse` has no `audit_id`.
- The `_keyed`-removal rewrote the module docstring as planned.

## Acceptance Criteria

- [x] AC1 pins: `test_tool_free_keys_are_pinned_from_prd_009`, `test_message_instances_key_like_role_content_turns`
- [x] AC2 framing: `test_tool_shaped_key_is_the_section_6_4_formula` and siblings
- [x] AC3 anchor position: `test_anchor_position_is_marked`, forgery test
- [x] AC4 loop and resend: unit and pipeline tests
- [x] AC5 step 1 keys tool turns: `test_tool_conversation_row_carries_the_tool_shaped_key`, `test_tool_turns_are_keyed_not_refused`
