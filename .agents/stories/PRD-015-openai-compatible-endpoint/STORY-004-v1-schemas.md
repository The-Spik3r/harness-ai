---
id: STORY-004
prd: PRD-015
slug: v1-schemas
title: "/v1 request, response, chunk and error schemas"
type: feature
priority: high
complexity: medium
phase: "1 - Foundations"
status: todo
labels: [backend, api, schemas]
epic_branch: epic/PRD-015-openai-compatible-endpoint
plan: null
report: null
commit: null
depends_on: []
blocks: [STORY-005, STORY-006, STORY-009, STORY-010, STORY-012, STORY-013]
skills: []
created: 2026-10-21
updated: 2026-10-21
---

# STORY-004: /v1 request, response, chunk and error schemas

## Description

As the `/v1` implementer, I want pydantic models for the Chat Completions request, the completion, the stream chunk, the model list and the error object, so that every later story builds and asserts against one definition of the wire shapes.

## Acceptance Criteria

- [ ] Given a request body with `model`, `messages`, `stream` and unknown keys such as `seed` and `profile`, when `ChatCompletionRequest` parses it, then the known fields are typed, the unknown keys are preserved (`extra="allow"`, readable via `model_extra`) and nothing is dropped.
- [ ] Given a body without `model` or without `messages`, or with `messages` not a list, when it parses, then validation fails; `messages` items stay raw mappings (the normalizer judges them, not pydantic).
- [ ] Given a `ChatCompletion` built with audit id 1842, when it is serialized, then it matches PRD Section 7.4's example field for field: `id == "chatcmpl-harness-1842"`, `object == "chat.completion"`, `choices[0]` with `index`, `message.role == "assistant"`, `logprobs: null` and `finish_reason`, a `usage` of three integers, and a `harness` object.
- [ ] Given a `ChatCompletionChunk`, a `ModelList` and an `ErrorResponse`, when serialized, then they match Sections 7.6, 7.7 and 7.5 respectively, including `choices: []` on the usage chunk and the `harness` object inside `error`.
- [ ] Given each example serialized to JSON, when the OpenAI Python SDK's own types validate it (`ChatCompletion.model_validate`, `ChatCompletionChunk.model_validate`), then it validates; the test is skipped when `openai` is not installed.

## Technical Notes

- New module `app/models/v1_schemas.py`. `app/models/schemas.py` is untouched: `/query`'s shapes do not move.
- `ChatCompletionRequest` declares only what Section 7.1 reads (`model`, `messages: list[Any]`, `stream: bool = False`, `stream_options`, the four forwarded parameters, `max_completion_tokens`, and the reject-unless-default keys as `Optional[Any]`), with `model_config = ConfigDict(extra="allow")`. Classification is STORY-006's; this story only guarantees nothing is lost at parse time.
- `ErrorDetail(message, type, param: Optional[str], code, harness: Optional[dict])` and `ErrorResponse(error)`. The `type` values are the four in Section 7.5.
- `harness` is an extension object on success and on error; the OpenAI SDK keeps unknown fields (PRD Section 7.4).
- The id derivation (`f"chatcmpl-harness-{audit_id}"`) lives in one helper here, so the body, the `X-Harness-Audit-Id` header and every chunk use the same function.
- Tests: `tests/test_v1_schemas.py`; no DB. The `openai` SDK is a test-only dependency introduced by STORY-015; guard its import with `pytest.importorskip`.
- Skills: none applicable.

## Dependencies

- **Blocked by**: None
- **Blocks**: STORY-005, STORY-006, STORY-009, STORY-010, STORY-012, STORY-013

## PRD Reference

Source: [`PRD-015-openai-compatible-endpoint/PRD.md`](../../PRDs/PRD-015-openai-compatible-endpoint/PRD.md) — sections 6.2, 7.1, 7.4, 7.5, 7.6, 7.7, 10
