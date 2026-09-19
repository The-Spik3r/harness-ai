---
id: STORY-004
prd: PRD-010
slug: openrouter-client-sends-messages
title: "call_openrouter takes a list of Messages; the pipeline passes one user message"
type: enhancement
priority: high
complexity: medium
phase: "1 - Model, settings, client"
status: done
labels: [backend, openrouter]
epic_branch: epic/PRD-010-multi-turn-pipeline
plan: .agents/plans/PRD-010-multi-turn-pipeline/completed/STORY-004-openrouter-client-sends-messages.plan.md
report: .agents/reports/PRD-010-multi-turn-pipeline/STORY-004-openrouter-client-sends-messages.report.md
commit: 65451c1
depends_on: [STORY-001, STORY-003]
blocks: [STORY-005, STORY-007]
skills: []
created: 2026-09-17
updated: 2026-09-17
---

# STORY-004: call_openrouter takes a list of Messages; the pipeline passes one user message

## Description

As the multi-turn pipeline, I want the OpenRouter client to send the conversation I give it rather than wrapping one string, so that history can reach the model without a second client.

## Acceptance Criteria

- [ ] Given [app/services/openrouter_client.py](../../../app/services/openrouter_client.py), when it is read, then the signature is `call_openrouter(messages: Sequence[Message], model: str = _DEFAULT_MODEL, api_key: Optional[str] = None, client: Optional[httpx.Client] = None)`, and the payload is `{"model": model, "messages": [{"role": m.role, "content": m.content} for m in messages]}`.
- [ ] Given `run_query` in [app/services/query_pipeline.py](../../../app/services/query_pipeline.py), when it reaches the upstream call, then it passes `[Message("user", redacted_prompt)]`, and STORY-003's characterization tests (client and `/query`) pass with the input argument adapted (`[Message("user", "hello")]`) and **no change to the payload assertion**.
- [ ] Given a four-message list `[system, user, assistant, user]`, when `call_openrouter` is called with a fake client, then the recorded `json["messages"]` preserves order, roles and content exactly.
- [ ] Given an empty `messages` list, when `call_openrouter` is called, then it raises `OpenRouterError` before any HTTP call. Structural rules beyond non-empty are the pipeline's (STORY-007).
- [ ] Given every test that injects a fake `call_openrouter` (for example [tests/test_chat_state.py](../../../tests/test_chat_state.py), [tests/test_query_pipeline_session_passthrough.py](../../../tests/test_query_pipeline_session_passthrough.py), [tests/test_pii_dedup_isolation.py](../../../tests/test_pii_dedup_isolation.py)), when the suite runs, then it is green. Only stubs that **read** their first argument as a string are updated, each with a `# PRD-010 STORY-004: upstream now receives list[Message]` comment. No outcome assertion changes.

## Technical Notes

- Roughly 90 injected-stub sites across about 17 test files take `(prompt, model="gpt-4", api_key=None)`. Most ignore `prompt`, so a positional list works unchanged. Grep for stubs that use the value (`prompt.upper()`, `assert prompt ==`, `seen.append(prompt)`) and update only those. `tests/test_pii_dedup_isolation.py` asserts the upstream receives **redacted** text; adapt it to read `messages[-1].content`.
- Keep `OpenRouterResult` unchanged. `null` content handling is STORY-005.
- Do not add `params` or change the timeout in this story (STORY-005). A small diff keeps the signature change reviewable on its own.
- `_DEFAULT_MODEL` stays. The router and `QueryRequest.model` default are untouched.
- Import `Message` from `app.models.messages`. The client depends on the model, never the reverse.
- Skills: none applicable.

## Dependencies

- **Blocked by**: STORY-001, STORY-003
- **Blocks**: STORY-005, STORY-007

## PRD Reference

Source: [`PRD-010-multi-turn-pipeline/PRD.md`](../../PRDs/PRD-010-multi-turn-pipeline/PRD.md) — sections 4 (OpenRouter client), 7 (F3), 10, 12 (Phase 1), 14 (Risk 1)
