---
id: STORY-004
prd: PRD-017
slug: upstream-tool-calls
title: "Upstream client: ToolParams, tool message serialization, tool_calls parsing"
type: feature
priority: high
complexity: medium
phase: "2 - The pipeline accepts tools"
status: done
labels: [backend, upstream]
epic_branch: epic/PRD-017-tool-calling
plan: .agents/plans/PRD-017-tool-calling/completed/STORY-004-upstream-tool-calls.plan.md
report: .agents/reports/PRD-017-tool-calling/STORY-004-upstream-tool-calls.report.md
commit: 1f81ec5
depends_on: [STORY-003]
blocks: [STORY-008, STORY-014]
skills: []
created: 2026-11-15
updated: 2026-11-15
---

# STORY-004: Upstream client: ToolParams, tool message serialization, tool_calls parsing

## Description

As the PRD-017 implementer, I want `call_openrouter` to forward a tool request, send tool history, and return the model's tool calls, so that the pipeline has calls to decide.

## Acceptance Criteria

- [ ] Given `ToolParams(tools=[...], tool_choice="auto", parallel_tool_calls=False)` passed as `call_openrouter(..., tools=tp)`, when the request is sent, then the payload carries `tools`, `tool_choice` and `parallel_tool_calls` exactly as given (a `None` field is not sent); without `tools=`, the payload is byte-identical to today's (asserted against a recorded payload).
- [ ] Given messages with an assistant `tool_calls` turn and a `tool` turn, when serialized, then the assistant turn is `{"role": "assistant", "content": null, "tool_calls": [{"id", "type": "function", "function": {"name", "arguments"}}]}` when its content is `""` (the content string otherwise) and the tool turn is `{"role": "tool", "tool_call_id", "content"}`; tool-free messages serialize exactly as today; `arguments` is the same string object's value, unparsed.
- [ ] Given an upstream response with `message.content: null` and `tool_calls`, when the request sent `tools=`, then `OpenRouterResult.response == ""`, `.tool_calls` holds `ToolCallSpec`s in order with byte-identical arguments, and `.finish_reason == "tool_calls"`; with text content and calls, both are kept.
- [ ] Given an upstream `tool_calls` response to a request that sent **no** `tools=`, when parsed, then `OpenRouterError` is raised with today's message ending `; tool calls are not supported (PRD-017)` (D18); `/query` and the chat UI are unaffected.
- [ ] Given a malformed `tool_calls` entry (not a list, missing `function.name`, non-string `arguments`), when parsed, then `OpenRouterError("OpenRouter returned an unexpected response shape: ...")` naming the field, not retryable.

## Technical Notes

- `app/services/openrouter_client.py`: payload at `:250-258` (`{"role", "content"}` only), parsing at `:276-291`, `OpenRouterResult` at `:215-227` (add `tool_calls: tuple[ToolCallSpec, ...] = ()` last, with a default, the PRD-013/PRD-015 precedent).
- `ToolParams` is a new frozen dataclass here, **not** fields on `GenerationParams` (PRD-010 T5; `GenerationParams.from_mapping` must still refuse `tools`). Shape validation of `tools` is the translator's (STORY-008); this class only carries values.
- `tools=` is keyword-only and passed only when set, like `params=` — the suite's stubs with signature `(messages, model, api_key)` must keep working. The router's `_Upstream.__call__` forwards `**kwargs` already (`app/routers/v1.py:132-136`).
- PRD-016's runtime-string test at `tests/test_openrouter_client.py:326-339` stays as is for the no-tools path.
- Tests: `tests/test_openrouter_client.py`.
- Skills: none applicable. No UI.

## Dependencies

- **Blocked by**: STORY-003
- **Blocks**: STORY-008, STORY-014

## PRD Reference

Source: [`PRD-017-tool-calling/PRD.md`](../../PRDs/PRD-017-tool-calling/PRD.md) — sections 4 (Upstream), 7 (F5), 10 (Internal API), 15 (D11, D18)
