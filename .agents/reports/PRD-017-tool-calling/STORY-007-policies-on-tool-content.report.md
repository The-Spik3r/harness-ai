---
story: STORY-007
prd: PRD-017
plan: .agents/plans/PRD-017-tool-calling/completed/STORY-007-policies-on-tool-content.plan.md
epic_branch: epic/PRD-017-tool-calling
commit: pending
status: COMPLETE
completed: 2026-11-16
---

# Implementation Report — STORY-007: Steps 3, 5, 6 on tool content

## Summary

Step 3 counts `len(arguments)` of every call on top of content (D12, step 3 only). Step 6 rebuilds turns with `dataclasses.replace`, so `tool_calls` and `tool_call_id` reach upstream with byte-identical arguments (D13); before the fix the new tests failed. Step 5 needed no code change: `inspect` reads `content` only, now documented and tested. `_analyzable_characters` still counts content only. The test-only `_admit_tool_turns` bypass is retired with no assertion changed and no test renamed.

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| Tests (9 files) | 266 passed, 0 failed, 0 skipped |
| New tests fail on the old step-6 line | yes (2 failed), pass on the fix |
| grep for stale wording / bypass | empty |
| D17 regression files diff | empty |
| Full suite | deferred to orchestrator (user decision) |

## Deviations from Plan

None. Line numbers in `query_pipeline.py` differed slightly from the plan; edits were placed by content.

## Acceptance Criteria

- [x] AC1: `test_context_characters_count_tool_call_arguments`, `..._without_calls_are_the_content_sum`, `test_long_arguments_refuse_at_step_3`
- [x] AC2: `test_tool_turn_injection_flags_under_code`, `test_injection_in_history_arguments_is_not_inspected`, `test_inspect_reads_content_only`
- [x] AC3: `test_tool_content_redacted_arguments_byte_identical`, `test_tool_fields_survive_step_6_unchanged`
- [x] AC4: `test_analyzable_characters_counts_tool_content_never_arguments`, `test_huge_arguments_do_not_trip_the_redaction_limit`
- [x] AC5: comments and docstrings reworded in query_pipeline, pattern_detector, pii_policy, pii_redactor, and the pattern tests
