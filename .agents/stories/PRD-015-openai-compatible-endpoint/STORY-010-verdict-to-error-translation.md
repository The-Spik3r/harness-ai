---
id: STORY-010
prd: PRD-015
slug: verdict-to-error-translation
title: "Verdicts to OpenAI error objects; /v1-scoped 400/401/403 handlers; /query isolation"
type: feature
priority: high
complexity: large
phase: "2 - Non-streaming endpoint"
status: todo
labels: [backend, api, errors]
epic_branch: epic/PRD-015-openai-compatible-endpoint
plan: null
report: null
commit: null
depends_on: [STORY-001, STORY-004, STORY-009]
blocks: [STORY-011, STORY-012, STORY-013]
skills: []
created: 2026-10-21
updated: 2026-10-21
---

# STORY-010: Verdicts to OpenAI error objects; /v1-scoped 400/401/403 handlers; /query isolation

## Description

As an integrating developer, I want every harness verdict to arrive as an ordinary OpenAI error with a status my client does not retry and a code that names the reason, so that my tool shows me what happened instead of looping.

## Acceptance Criteria

- [ ] Given each pipeline verdict (duplicate; suspicious; context limit `messages` and `characters`; `redaction_characters`; forbidden for `query:submit`, `query:model:*`, `ingress:break_glass`; usage limit `requests` and `tokens`), when it is the result of a `/v1` request, then the status, `type` and `code` are exactly those in PRD Section 7.5, `error.harness` carries every field of the pipeline response, and `error.message` is the reason plus its details.
- [ ] Given `ADMIN_TOKEN` as the bearer, when `POST /v1/chat/completions` is sent, then 403 `break_glass_not_permitted` and the PRD-013 refusal row with `denied_permission='ingress:break_glass'` and `ingress='v1'`.
- [ ] Given no bearer, an invalid bearer, an identity without `query:submit`, a non-JSON body, a body failing schema validation, or a `V1RequestError` from STORY-005/006, when sent to `/v1/*`, then the response is the error object (401 `invalid_api_key` / 403 `permission_denied` / 400 `invalid_request` or the translation code) with `param` where known, and no audit row.
- [ ] Given every 4xx response from `/v1`, when its headers are read, then `x-should-retry: false` is present; and no `/v1` verdict is ever 429 or 5xx.
- [ ] Given `tests/test_v1_query_isolation.py` from STORY-001, when it runs after this story's handlers are registered, then every `/query` body is unchanged, and its new `/v1` half passes.

## Technical Notes

- Verdict mapping is a pure function in `v1_translate` keyed on the response type and, for forbidden, on `required_permission` (`query:model:` prefix, `ingress:break_glass`, else `permission_denied`). One table; a test iterates over `QueryPipelineResult`'s members so a future member without a mapping fails.
- 401/403 from `require_identity` / `require_permission` and FastAPI's `RequestValidationError` are `HTTPException`s raised before the route body. Register app-level handlers for `HTTPException` and `RequestValidationError` that return the OpenAI shape **only when `request.url.path` starts with `/v1/`**, and otherwise delegate to `fastapi.exception_handlers.http_exception_handler` / `request_validation_exception_handler`. That delegation is what STORY-001's test protects (PRD Risk 4).
- `context_length_exceeded` is OpenAI's own code; keep the spelling (PRD Section 7.5).
- Messages never echo content (T6). The pattern is returned, as on `/query`.
- Shape refusals are logged at INFO with the user id and `code` only (PRD T9).
- Tests: `tests/test_v1_errors.py` per verdict (reuse the pipeline fixtures from `tests/test_query_outcomes_regression.py` to force each outcome); extend `tests/test_v1_query_isolation.py`.
- Skills: none applicable.

## Dependencies

- **Blocked by**: STORY-001, STORY-004, STORY-009
- **Blocks**: STORY-011, STORY-012, STORY-013

## PRD Reference

Source: [`PRD-015-openai-compatible-endpoint/PRD.md`](../../PRDs/PRD-015-openai-compatible-endpoint/PRD.md) — sections 7.2, 7.5, 9.1, 9.2 (T6, T7, T9), 11, 14 (Risk 4), 15 (D2, D5)
