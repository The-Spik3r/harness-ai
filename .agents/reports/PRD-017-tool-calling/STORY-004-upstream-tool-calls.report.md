---
story: STORY-004
prd: PRD-017
plan: .agents/plans/PRD-017-tool-calling/completed/STORY-004-upstream-tool-calls.plan.md
epic_branch: epic/PRD-017-tool-calling
commit: pending
status: COMPLETE
completed: 2026-11-15
---

# Implementation Report — STORY-004: Upstream client: ToolParams, tool message serialization, tool_calls parsing

**Plan**: `.agents/plans/PRD-017-tool-calling/completed/STORY-004-upstream-tool-calls.plan.md`
**Epic Branch**: `epic/PRD-017-tool-calling`
**Commit**: `pending`

## Summary

`app/services/openrouter_client.py` now forwards a tool request (`ToolParams`, keyword-only `tools=`), serializes tool history through one `_wire_message` helper, and parses `choices[0].message.tool_calls` into `ToolCallSpec`s only when `tools=` was passed (D18). `OpenRouterResult.tool_calls` is appended last with a default. Plan decisions (a)-(f) and the duplicate-id check are implemented as written.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | `ToolParams`, `OpenRouterResult.tool_calls` | `app/services/openrouter_client.py` | done |
| 2 | `_wire_message` serializer | `app/services/openrouter_client.py` | done |
| 3 | keyword-only `tools=` into payload | `app/services/openrouter_client.py` | done |
| 4 | `_parse_tool_calls` and the gated call site | `app/services/openrouter_client.py` | done |
| 5 | docstring on `call_openrouter` | `app/services/openrouter_client.py` | done |
| 6 | tests | `tests/test_openrouter_client.py` | done |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| Frontend lint | n/a (no frontend) |
| Targeted tests (openrouter_client, untouched_app, v1_router, query_outcomes_regression) | 161 passed, 0 failed, 0 skipped |
| `tests/test_openrouter_client.py` alone | 127 passed |
| Full suite | deferred to orchestrator (user decision) |
| E2E | plan's E2E is the targeted run above; no live upstream call |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/services/openrouter_client.py` | UPDATE | +108/-2 |
| `tests/test_openrouter_client.py` | UPDATE | +316/-2 |
| `.agents/stories/.../STORY-008-...md` | UPDATE | +1 (orchestrator note, staged with this story) |

## Deviations from Plan

None. Two small notes: the field-order pin was edited with a PRD-017 comment (test not renamed); the `(messages, model, api_key)` stub compatibility is covered by the existing suite and `test_v1_router.py`, which passed.

## Tests Written

New section `PRD-017 STORY-004` in `tests/test_openrouter_client.py`: payload exactness, four `tool_choice` forms, None fields not sent, recorded-literal payload without tools, keyword-only, `from_mapping` still refuses `tools`, assistant/tool serialization, byte-for-byte arguments, null content with calls, type absent/null, usage on tool-call response, tools-sent no-calls/null/[] cases, D18 exact message without `tools=`, 17 malformed-shape cases, no value in messages.

## Acceptance Criteria

- [x] ToolParams reach the payload as given; without `tools=` payload byte-identical (`test_tool_params_reach_the_payload_exactly_as_given`, `test_without_tools_the_payload_is_byte_identical_to_a_recorded_one`)
- [x] Serialization of assistant/tool turns, tool-free unchanged, arguments unparsed (`test_assistant_tool_call_turn_*`, `test_tool_turn_*`, `test_arguments_string_is_sent_byte_for_byte`)
- [x] null content + calls with `tools=` gives `""`, ordered calls, `finish_reason` (`test_null_content_with_calls_parses_to_empty_response_and_ordered_calls`, `test_text_with_calls_keeps_both`)
- [x] No `tools=`: D18 error unchanged (`test_tool_calls_without_tools_sent_keep_the_d18_error_exactly`, existing tests, `/query` regression green)
- [x] Malformed entries: non-retryable shape error naming the field (`test_malformed_tool_calls_are_a_non_retryable_shape_error`)
