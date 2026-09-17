---
id: STORY-005
prd: PRD-010
slug: generation-params-timeout-and-null-content
title: "GenerationParams allowlist, configurable timeout and explicit null-content error"
type: feature
priority: high
complexity: medium
phase: "1 - Model, settings, client"
status: todo
labels: [backend, openrouter, security]
epic_branch: epic/PRD-010-multi-turn-pipeline
plan: null
report: null
commit: null
depends_on: [STORY-002, STORY-004]
blocks: [STORY-007, STORY-016]
skills: []
created: 2026-09-17
updated: 2026-09-17
---

# STORY-005: GenerationParams allowlist, configurable timeout and explicit null-content error

## Description

As a compliance admin, I want generation parameters limited to a validated allowlist, the timeout to be configurable, and a content-less upstream reply to fail with a clear reason, so that multi-turn exposes no more upstream surface than needed and slow large contexts don't time out at 30 s.

## Acceptance Criteria

- [ ] Given [app/services/openrouter_client.py](../../../app/services/openrouter_client.py), when it is read, then it defines a frozen `GenerationParams(temperature, max_tokens, top_p, stop)` (all `Optional`, default `None`), `UnsupportedParameterError`, and `GenerationParams.from_mapping(raw)`. `call_openrouter` gains `params: Optional[GenerationParams] = None`, and the payload includes **only** the non-`None` fields.
- [ ] Given `from_mapping({"logit_bias": {}, "tools": [], "stream": True, "temperature": 0.2})`, when it is called, then it raises `UnsupportedParameterError` naming all three unsupported keys, sorted. Given `temperature=3`, `top_p=0`, `max_tokens=0`, or `stop` with five sequences or a non-str element, then each raises `UnsupportedParameterError` naming the field and its allowed range. All checks happen before any HTTP call (test with a client that fails if used).
- [ ] Given `params=None` and one user message, when the payload is recorded, then STORY-003's characterization assertion still holds byte for byte.
- [ ] Given `settings.OPENROUTER_TIMEOUT_SECONDS = 7.5` (monkeypatched) and no `client`, when `call_openrouter` builds its client, then `httpx.Client` is constructed with `timeout=7.5`. The module constant `_TIMEOUT_SECONDS` is removed, and STORY-003's `timeout=30.0` assertion is updated with a `# PRD-010 STORY-005: timeout from settings (default 120.0)` comment.
- [ ] Given an upstream 200 whose `choices[0].message.content` is `null`, when parsed, then `OpenRouterError` is raised with `"OpenRouter returned no text content (finish_reason=<value>)"`. If `message.tool_calls` is present, the message adds `"tool calls are not supported (PRD-016)"`. Through `POST /query` that maps to 502 (test), and the API key never appears in either message.

## Technical Notes

- Read the timeout **per call** (`settings.OPENROUTER_TIMEOUT_SECONDS`) rather than at import, so tests can monkeypatch it (PRD F3).
- Only the pipeline (STORY-007) will pass `params`. When it does, it passes `params=` **only when not `None`**, so the ~90 existing injected stubs with signature `(prompt, model, api_key)` keep working. State this in a comment at the call site when STORY-007 lands. This story adds no pipeline change.
- `bool` is a subclass of `int`: reject `max_tokens=True` explicitly.
- `stop` may be a `str` or a list of ≤ 4 `str`. Serialize it exactly as received.
- `from_mapping` is the entry PRD-014 will use. Nothing calls it in production here; the tests are its contract.
- Threat reasoning T5 (PRD 9.2): no ingress exposes params in this PRD.
- Skills: none applicable.

## Dependencies

- **Blocked by**: STORY-002, STORY-004
- **Blocks**: STORY-007, STORY-016

## PRD Reference

Source: [`PRD-010-multi-turn-pipeline/PRD.md`](../../PRDs/PRD-010-multi-turn-pipeline/PRD.md) — sections 4 (OpenRouter client), 7 (F3), 9.2 (T5, T8), 9.3, 10, 11
