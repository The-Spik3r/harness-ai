---
id: STORY-006
prd: PRD-015
slug: parameter-classification-and-tools-refusal
title: "Parameter classification: forward, ignore-and-record, reject; the explicit tools refusal"
type: feature
priority: high
complexity: medium
phase: "1 - Foundations"
status: todo
labels: [backend, api, translation, security]
epic_branch: epic/PRD-015-openai-compatible-endpoint
plan: null
report: null
commit: null
depends_on: [STORY-001, STORY-004, STORY-005]
blocks: [STORY-009]
skills: []
created: 2026-10-21
updated: 2026-10-21
---

# STORY-006: Parameter classification: forward, ignore-and-record, reject; the explicit tools refusal

## Description

As an integrating developer, I want every parameter my client sends either honoured, ignored with a record, or refused by name, so that I am never silently given a different answer than I asked for, and the upstream request never carries more than the harness allows.

## Acceptance Criteria

- [ ] Given `temperature`, `top_p`, `max_tokens` and `stop` within range, when `translate_request` runs, then they become a `GenerationParams`; out of range is `V1RequestError(code="invalid_parameter", param=<name>)`; `max_completion_tokens` alone becomes `max_tokens`, and both present with different values is `invalid_parameter`.
- [ ] Given `n=2`, `logprobs=true`, `top_logprobs=3`, `response_format={"type":"json_object"}` or `json_schema`, or `modalities=["text","audio"]`, when it runs, then `code="unsupported_parameter"` with `param` set; given `n=1`, `logprobs=false`, `response_format={"type":"text"}` or `modalities=["text"]`, then each is accepted and none is recorded as ignored.
- [ ] Given non-empty `tools`, `functions`, `tool_choice` other than `"none"`, or `function_call`, when it runs, then `code="tools_not_supported"`; given `tools: []`, `tools: null` or `tool_choice: "none"`, then the request is accepted.
- [ ] Given `seed`, `user`, `presence_penalty`, `logit_bias`, `metadata`, `profile`, `ingress`, `openrouter_api_key` and an unknown key, plus `stream_options={"include_usage": true, "foo": 1}`, when it runs, then `ignored_params` is the sorted comma-joined names including `stream_options.foo` (values never appear), `include_usage` is `True`, and with nothing ignored it is `None`.
- [ ] Given a test over the classification table, when it runs, then the forwarded set equals `GenerationParams`' fields plus `max_completion_tokens`; and given a full request through `run_conversation` with an `httpx.MockTransport`, the upstream body's keys are still exactly STORY-001's set (PRD T5).

## Technical Notes

- In `app/services/v1_translate.py`: one table with three parts (`FORWARDED`, `REJECTED_UNLESS_DEFAULT` with each key's accepted defaults, everything else ignored), as PRD Section 7.3 says. `translate_request(body: ChatCompletionRequest) -> V1Call` returns messages, `GenerationParams`, model, stream, include_usage and `ignored_params` (`Optional[str]`).
- Feed forwarded keys through `GenerationParams.from_mapping` (PRD-010's "PRD-014's entry point"; this PRD, see the PRD's numbering note) and map `UnsupportedParameterError` to `invalid_parameter` with the key as `param`.
- `ignored_params` merges the names from STORY-005 (`messages[].name`) with top-level and `stream_options.<key>` names, each listed once.
- T4: `profile` and `ingress` in a body are ordinary ignored keys; the test proves it.
- Tests: extend `tests/test_v1_translate_request.py`; the upstream-body test reuses STORY-001's capture helper and needs `temp_db`.
- Skills: none applicable.

## Dependencies

- **Blocked by**: STORY-001, STORY-004, STORY-005
- **Blocks**: STORY-009

## PRD Reference

Source: [`PRD-015-openai-compatible-endpoint/PRD.md`](../../PRDs/PRD-015-openai-compatible-endpoint/PRD.md) — sections 7.1, 7.3, 9.2 (T4, T5), 15 (D3)
