---
story: STORY-012
prd: PRD-017
plan: .agents/plans/PRD-017-tool-calling/completed/STORY-012-sse-tool-call-deltas.plan.md
epic_branch: epic/PRD-017-tool-calling
commit: 0865708
status: COMPLETE
completed: 2026-11-16
---

# Implementation Report - STORY-012: Buffered SSE tool_calls deltas in one burst

## Summary

`v1_sse.completion_events` now renders one chunk per released call between the role chunk and the finish chunk, each with the whole `arguments` string. `ChunkDelta` gained `tool_calls` and drops unset keys (DD-1), so the role chunk keeps `content: null` and the finish chunk stays `{}`. New `ChunkToolCall` model. Router untouched. The interim STORY-011 pin is replaced.

## Files Changed

| File | Action |
|------|--------|
| `app/models/v1_schemas.py` | UPDATE (ChunkToolCall, ChunkDelta.tool_calls, set-based dropping) |
| `app/services/v1_sse.py` | UPDATE (tool-call chunks) |
| `app/services/v1_translate.py` | UPDATE (docstring only) |
| `tests/test_v1_schemas.py` | UPDATE (4 tests appended) |
| `tests/test_v1_tools.py` | UPDATE (interim pin replaced; 8 test functions added) |
| `.agents/stories/.../STORY-016-e2e-opencode.md` | UPDATE (planner note: usage after finish is fine) |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| Targeted pytest (test_v1_tools, test_v1_schemas, test_v1_sse, test_v1_translate_result, test_pii_redaction_integration, test_untouched_app; -rs) | 885 passed, 0 failed, 0 skipped |
| `git diff HEAD -- tests/test_v1_sse.py` | empty (unedited) |
| E2E (in-process SDK accumulator) | passed, not skipped |

Full suite: deferred to orchestrator (user decision).

## Deviations from Plan

None. No `_DELIBERATELY_SUPERSEDED_TESTS` entry needed (the renamed test is new in this epic; the guard file passed).

## Acceptance Criteria

- [x] AC1: `test_completion_events_stream_two_released_calls` (both include_usage), `test_streamed_allowed_call_is_one_delta_then_finish_tool_calls`
- [x] AC2: `tests/test_v1_sse.py` unedited and green; `test_flag_on_text_only_stream_is_the_flag_off_stream` (byte check)
- [x] AC3: `test_sdk_accumulator_rebuilds_the_non_streamed_message`, `test_streamed_and_plain_tool_responses_accumulate_to_the_same_message` (ran, no skips)
- [x] AC4: `test_streamed_all_denied_is_the_note_then_stop_and_no_delta`; existing `test_action_audit_failure_after_stream_commit_is_the_error_event`
