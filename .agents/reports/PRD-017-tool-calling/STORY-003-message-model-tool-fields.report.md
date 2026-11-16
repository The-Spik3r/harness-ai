---
story: STORY-003
prd: PRD-017
plan: .agents/plans/PRD-017-tool-calling/completed/STORY-003-message-model-tool-fields.plan.md
epic_branch: epic/PRD-017-tool-calling
commit: a68762c
status: COMPLETE
completed: 2026-11-15
---

# Implementation Report - STORY-003: ToolCallSpec, Message.tool_calls / tool_call_id, and the normalizer

**Plan**: `.agents/plans/PRD-017-tool-calling/completed/STORY-003-message-model-tool-fields.plan.md`
**Epic Branch**: `epic/PRD-017-tool-calling`
**Commit**: `a68762c`

## Summary

`app/models/messages.py` gains a frozen `ToolCallSpec(id, name, arguments)` and two trailing defaulted `Message` fields (`tool_calls`, `tool_call_id`). `normalize_message` now accepts `tool_calls` on assistant turns and requires `tool_call_id` on tool turns, checking shape only; errors name the location and rule, never a value. `arguments` is carried as the exact input string (D13).

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Model, `_normalize_tool_calls`, normalizer checks, comment rewording | `app/models/messages.py` | done |
| 2 | Tests (replaced refusal cases, new accept/refuse/canary/alignment tests) | `tests/test_messages.py` | done |
| 3 | Targeted regression run | - | done |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| Frontend lint | n/a (no frontend) |
| Targeted tests | 1420 passed, 0 failed, 0 skipped |
| E2E | n/a: no HTTP change; `/v1` router/translate tests green and unedited |

Targeted set: test_messages, test_v1_translate_request, test_v1_router, test_action_adapters, test_dedup_key, test_pii_redaction_integration, test_untouched_app, test_query_outcomes_regression, test_chat_outcomes_regression.
Full suite: deferred to orchestrator (user decision).

## Deviations from Plan

- Orchestrator override of DD1: `tool_calls: null` on any role is absent (`()`); `tool_call_id: null` on a non-tool role is absent. Non-null `tool_calls` on a non-assistant role (including `[]`), non-null `tool_call_id` on a non-tool role, and `tool_call_id: null` on a tool turn are still refused. Stated in the `normalize_message` docstring.
- Role comment reworded to PRD-017.
- No test function renamed or removed; `_DELIBERATELY_SUPERSEDED_TESTS` unchanged.

## Tests Written

`tests/test_messages.py`: `test_tool_call_spec_is_frozen_with_the_specified_fields`, `test_tool_call_spec_fields_match_action_adapters_tool_call`, `test_normalizes_tool_shape` (18 cases incl. client shapes and null-as-absent), `test_arguments_are_carried_byte_for_byte`, `test_refuses_tool_shape` (27 cases), `test_tool_shape_error_names_message_index`, `test_normalize_messages_accepts_a_client_tool_loop`; canary test extended with 6 tool-shape cases.

## Acceptance Criteria

- [x] AC1 (model fields, legacy construction, purity)
- [x] AC2 (null content + tool_calls; `[]` gives `()`; byte-identical arguments)
- [x] AC3 (tool turn string / text parts)
- [x] AC4 (location + rule, no values)
- [x] AC5 (old refusals replaced with PRD-017 D5 comments; fields match `ToolCall`)
