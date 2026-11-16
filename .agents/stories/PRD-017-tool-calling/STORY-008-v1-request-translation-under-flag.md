---
id: STORY-008
prd: PRD-017
slug: v1-request-translation-under-flag
title: "/v1 request translation under V1_TOOLS_ENABLED: tools, tool turns, shape rules, V1_TOOL_MODELS; passed through to step 7"
type: feature
priority: high
complexity: large
phase: "2 - The pipeline accepts tools"
status: in-progress
labels: [backend, api, v1]
epic_branch: epic/PRD-017-tool-calling
plan: .agents/plans/PRD-017-tool-calling/STORY-008-v1-request-translation-under-flag.plan.md
report: null
commit: null
depends_on: [STORY-001, STORY-002, STORY-004, STORY-005, STORY-006, STORY-007]
blocks: [STORY-010]
skills: []
created: 2026-11-15
updated: 2026-11-16
---

# STORY-008: /v1 request translation under V1_TOOLS_ENABLED: tools, tool turns, shape rules, V1_TOOL_MODELS; passed through to step 7

## Description

As an integrating developer, I want `/v1` to accept my agent's tool definitions and tool history when the operator has enabled tools, so that the request reaches the model with everything it needs, and to refuse clearly when tools are off or malformed.

## Acceptance Criteria

- [ ] Given `V1_TOOLS_ENABLED=false`, when any PRD-015 request (with or without tools) is sent, then the response is exactly PRD-015's: every existing `tools_not_supported` test in `tests/test_v1_translate_request.py` and `tests/test_v1_router.py` passes **unchanged**.
- [ ] Given the flag on, when a request carries `tools` (list of `{type: "function", function: {name, description?, parameters?, strict?}}`), `tool_choice` (`none | auto | required | {type: "function", function: {name}}`) and `parallel_tool_calls` (bool), then `V1Call.tools` is a `ToolParams` with the values as sent, and the router passes it to `run_conversation(..., tools=...)`, which passes it to `call_openrouter` at step 7 only when set; `functions` / `function_call` stay `tools_not_supported` (D10); `parallel_tool_calls` is no longer in `ignored_params` (D11).
- [ ] Given the flag on, when assistant `tool_calls` and `tool` turns arrive in `messages`, then they are normalized (STORY-003) and the D6 shape rules are checked with the shared helper (STORY-005); each violation and each malformed `tools` item / `tool_choice` (including a named function absent from `tools`) / non-bool `parallel_tool_calls` is a 400 whose `code` and `param` follow PRD-017 Section 10's table; the last turn may be `tool`.
- [ ] Given `V1_TOOL_MODELS` set and a `tools` request for a model outside it, when translated, then 400 `tools_not_supported`, `param: "tools"`, message `model is not enabled for tool calling (V1_TOOL_MODELS)` (D16); with the list empty, any permitted model passes.
- [ ] Given a full flag-on request through `TestClient` with a stub `call_openrouter` that returns text, when it runs, then the stub received the tools and the tool history byte-for-byte, and the response is a normal text completion (tool calls in a response are not released until STORY-010/011 — the result translator still reads `response` only).

## Technical Notes

- Orchestrator decision (STORY-005 plan): use the shared `conversation_shape_violation` helper only when the flag is on. With the flag off, the edge keeps its PRD-015 strings byte-identical: `the last message must be a user turn` (`v1_translate.py:238`, pinned by `tests/e2e/test_aider.py:443`) and `tool turns are not supported (PRD-017)`. D6 now has a fourth rule (the conversation contains a user turn); the edge maps every violation to 400 `invalid_messages`.
- Orchestrator decision (STORY-004 plan): with the flag on, `tools: []` (OpenCode's shape when history has calls but no tool is active) becomes `V1Call.tools = None` — nothing tool-related is forwarded, because some upstreams reject an empty `tools` array and none can return a call without one; tool history is still admitted. A `tool_choice` other than absent/`none` alongside `tools: []` is `invalid_parameter`. `call_openrouter(tools=ToolParams([]))` stays legal at the client level (STORY-004) but the translator never builds it.
- Orchestrator decision (STORY-003): the normalizer treats `tool_calls: null` and a null `tool_call_id` as absent (OpenAI SDK `model_dump()` echoes send them on text turns). With the flag on, the translator must do the same; with the flag off, PRD-015's key-presence refusal stays as it is.
- Orchestrator decision (STORY-002 plan): `V1_TOOL_MODELS` is a capability list, not a grant. Request-time check: when `settings.v1_tool_models_list` is non-empty, `model in v1_tool_models_list` for **every** caller (admin and RBAC-off included), without reading `identity.role`; empty means no extra check.
- Orchestrator note (STORY-001): Cline writes history `arguments` via `JSON.stringify` (whitespace may differ from the upstream's); forward whatever arrives, unchanged. Both clients send `content: null` on a tool-call-only assistant turn and neither sends `parallel_tool_calls`; OpenCode always sends `stream_options`.
- Orchestrator decision (STORY-001 plan): OpenCode 2.0.10 sends `tools: []` when the history has tool calls but no tool is active, never sends `parallel_tool_calls`, always `stream: true`, and writes assistant `content: null` with tool calls. With the flag on, `tools: []` plus tool history must be accepted (tool turns are admitted whenever the flag is on, not only when `tools` is non-empty); with the flag off, PRD-015 still treats `[]` as the default. Use STORY-001's survey note for the exact shapes.
- `app/services/v1_translate.py`: `REJECTED_UNLESS_DEFAULT` `:102-113` and `_check_rejected` `:248-251`; `translate_messages` `:190-240` (refusals at `:216-223`, last-turn check at `:235-239`); `translate_request` `:312-344`; `V1Call` `:153-167`. The flag is read in the **router** and passed to the pure translator as an argument (the translator reads no settings, module docstring) — or the plan proposes an equivalent that keeps purity.
- `test_forwarded_is_generation_params_plus_alias` guards `FORWARDED`; tools are not `FORWARDED` (not `GenerationParams`), so give them their own group and keep every key in exactly one group (PRD-015 Section 7.3). Update `tests/e2e/_live.py`'s mirrored sets and `tests/test_e2e_live.py` if the groups change.
- `app/routers/v1.py:287-302`: the `run_in_pipeline(run_conversation, ...)` call; `app/services/query_pipeline.py:251-278`: add `tools: Optional[ToolParams] = None` keyword-only, passed to `call_openrouter` at step 7 (`:669-677`) the way `params` is, only when set.
- Use the client request shapes recorded in STORY-001's survey note as fixtures (OpenCode, Cline).
- Messages never echo values (PRD-015 T6).
- Tests: `tests/test_v1_translate_request.py`, `tests/test_v1_router.py`, new `tests/test_v1_tools.py`.
- Skills: none applicable. No UI.

## Dependencies

- **Blocked by**: STORY-001, STORY-002, STORY-004, STORY-005, STORY-006, STORY-007
- **Blocks**: STORY-010

## PRD Reference

Source: [`PRD-017-tool-calling/PRD.md`](../../PRDs/PRD-017-tool-calling/PRD.md) — sections 4 (Request translation), 6.3, 6.7, 7 (F3), 10, 15 (D6, D10, D11, D16)
