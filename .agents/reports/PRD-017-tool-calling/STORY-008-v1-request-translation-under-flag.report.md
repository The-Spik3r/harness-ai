---
story: STORY-008
prd: PRD-017
plan: .agents/plans/PRD-017-tool-calling/completed/STORY-008-v1-request-translation-under-flag.plan.md
epic_branch: epic/PRD-017-tool-calling
commit: pending
status: COMPLETE
completed: 2026-11-16
---

# Implementation Report - STORY-008: /v1 request translation under V1_TOOLS_ENABLED

**Plan**: `.agents/plans/PRD-017-tool-calling/completed/STORY-008-v1-request-translation-under-flag.plan.md`
**Epic Branch**: `epic/PRD-017-tool-calling`
**Commit**: `pending`

## Summary

With the flag on, the pure translator (`translate_request(body, *, tools_enabled, tool_models)`) admits `tools`, `tool_choice`, `parallel_tool_calls` and tool turns, validates their shape, checks D6 with the shared helper, and enforces V1_TOOL_MODELS (D16). `V1Call.tools` carries a `ToolParams`. The router reads the flag and list per request and passes `tools=call.tools` to `run_conversation`, which passes it to step 7 only when set. Flag off is PRD-015 byte for byte. Interim T1: upstream tool_calls are dropped (empty text completion, pinned by test).

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| Targeted tests (11 files, one call) | 1587 passed, 0 failed, 0 skipped |
| E2E (TestClient, flag on/off, streamed, interim T1) | in tests/test_v1_tools.py |
| Full suite | deferred to orchestrator (user decision) |

## Files Changed

`app/services/v1_translate.py`, `app/services/query_pipeline.py`, `app/routers/v1.py`, `app/config.py` (comment), `tests/test_v1_tools.py` (new), `tests/test_query_pipeline_tools.py`, `tests/test_query_pipeline_run_conversation.py`, `tests/test_v1_translate_request.py`.

## Deviations from Plan

None of substance. The two approved structural assertions were changed (V1Call field set, run_conversation signature), each with a PRD-017 comment. Q1-Q4 decisions applied as approved.

## Acceptance Criteria

- [x] AC1 flag off is PRD-015 (test_flag_off_refusals_are_prd_015_exactly, test_defaults_are_the_flag_off_behaviour, unedited existing suites)
- [x] AC2 ToolParams as sent, passed to step 7 only when set (test_tool_request_is_forwarded_as_sent, test_router_hands_tool_params_to_the_pipeline, test_query_pipeline_tools STORY-008 section)
- [x] AC3 tool turns, D6, malformed tools/tool_choice/parallel_tool_calls (test_v1_tools translator layer)
- [x] AC4 V1_TOOL_MODELS (test_model_outside_a_non_empty_list_is_refused, test_tool_model_list_holds_for_every_role)
- [x] AC5 full flag-on request byte for byte (test_full_flag_on_request_reaches_the_wire_byte_for_byte, interim T1 pins)
