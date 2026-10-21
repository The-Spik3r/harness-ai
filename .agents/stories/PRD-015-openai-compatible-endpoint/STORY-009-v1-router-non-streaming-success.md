---
id: STORY-009
prd: PRD-015
slug: v1-router-non-streaming-success
title: "POST /v1/chat/completions: router, identity, device header and non-streaming success"
type: feature
priority: high
complexity: large
phase: "2 - Non-streaming endpoint"
status: todo
labels: [backend, api, router]
epic_branch: epic/PRD-015-openai-compatible-endpoint
plan: null
report: null
commit: null
depends_on: [STORY-002, STORY-003, STORY-004, STORY-005, STORY-006, STORY-007]
blocks: [STORY-010, STORY-012]
skills: []
created: 2026-10-21
updated: 2026-10-21
---

# STORY-009: POST /v1/chat/completions: router, identity, device header and non-streaming success

## Description

As an integrating developer, I want to send a Chat Completions request with my harness token and get a standard `chat.completion` back, so that my existing OpenAI-shaped code works by changing the base URL and key.

## Acceptance Criteria

- [ ] Given a `user`-role token, an allowlisted model and a clean conversation, when `POST /v1/chat/completions` is sent without `stream`, then the response is 200 with the Section 7.4 shape: `id == f"chatcmpl-harness-{audit_id}"`, `model` as requested, the upstream `finish_reason` (or `"stop"` when it was `None`), `usage` from the upstream split (0 for a missing split, total as reported), `harness.audit_id`, and an `X-Harness-Audit-Id` header with the same id.
- [ ] Given that request, when the audit is read, then exactly one row was written, with `ingress='v1'`, `profile='code'`, `streamed=0`, `session_id` NULL, `message_count == len(messages)`, `ignored_params` as translated, and `device` from `X-Harness-Device`.
- [ ] Given an `X-Harness-Device` value over 128 characters or with a non-printable character, when sent, then 400 with `code="invalid_header"` and no row; given the header absent, then `device` is NULL; given a body `user` field, then it is not the device and not the identity.
- [ ] Given `V1_ENABLED=false`, when the app starts, then `/v1/chat/completions` returns 404 and `/query` is unaffected; given it on, then `tests/test_route_reservations.py` still passes and also asserts the `/v1` paths are present.
- [ ] Given the pipeline body, when the request runs, then it runs on the dedicated pipeline executor thread, never the event loop or anyio's threadpool (the assertion `tests/test_query_router.py` makes for `/query`).

## Technical Notes

- New `app/routers/v1.py`, included in `app/main.py` when `settings.V1_ENABLED`. Dependency `require_permission(PERMISSION_QUERY_SUBMIT)` as `/query` uses.
- The one call site: `run_in_pipeline(run_conversation, identity, messages, device, model, None, params, call_openrouter=call_openrouter, profile="code", ingress="v1", streamed=False, ignored_params=...)`. The literal `"code"` and `"v1"` are the point (PRD-011 Section 6.6, PRD-013 Section 6.9); the call-site scan in `tests/test_query_pipeline_audit_fields.py` must see this file and pass.
- Import `call_openrouter` by name into `app/routers/v1.py` so tests replace `app.routers.v1.call_openrouter`, the binding rule used for `app.routers.query.call_openrouter`.
- `openrouter_api_key` is always `None`: BYOK is out (PRD Section 4).
- Success translation (`QuerySuccessResponse` + the upstream `finish_reason` and token split → `ChatCompletion`) lives in `v1_translate.translate_result`, pure. `QuerySuccessResponse` does not carry `finish_reason` or the split today: carry them from the pipeline without changing `/query`'s body. Options to weigh in the plan: (a) the router's `call_openrouter` wrapper captures the `OpenRouterResult` (STORY-013 needs a wrapper anyway); (b) extra fields excluded from `/query`'s serialization. Prefer (a): the pipeline does not change. STORY-001's isolation test proves `/query`'s body did not move.
- In this story a non-success result may return a placeholder 501; STORY-010 replaces it. Do not ship the epic in between.
- Tests: `tests/test_v1_router.py` with `TestClient`, `temp_db`, an injected upstream stub.
- Skills: none applicable.

## Dependencies

- **Blocked by**: STORY-002, STORY-003, STORY-004, STORY-005, STORY-006, STORY-007
- **Blocks**: STORY-010, STORY-012

## PRD Reference

Source: [`PRD-015-openai-compatible-endpoint/PRD.md`](../../PRDs/PRD-015-openai-compatible-endpoint/PRD.md) — sections 6.1, 6.3, 7.2, 7.4, 10, 11 (SDK non-streaming)
