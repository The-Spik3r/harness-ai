---
id: STORY-002
prd: PRD-015
slug: openrouter-client-finish-reason-retryable-base-url
title: "OpenRouter client: finish_reason, upstream_status and retryable, OPENROUTER_BASE_URL"
type: feature
priority: high
complexity: medium
phase: "1 - Foundations"
status: todo
labels: [backend, upstream, config]
epic_branch: epic/PRD-015-openai-compatible-endpoint
plan: null
report: null
commit: null
depends_on: [STORY-001]
blocks: [STORY-009, STORY-011, STORY-014]
skills: []
created: 2026-10-21
updated: 2026-10-21
---

# STORY-002: OpenRouter client: finish_reason, upstream_status and retryable, OPENROUTER_BASE_URL

## Description

As the `/v1` implementer, I want the upstream client to report why a completion stopped and whether a failure is worth retrying, and to accept a configurable base URL, so that success and fault translation have the facts they need and E2E runs can use a local stub.

## Acceptance Criteria

- [ ] Given an upstream response with `choices[0].finish_reason` of `stop`, `length` or `content_filter`, when `call_openrouter` returns, then `OpenRouterResult.finish_reason` carries it; given the field absent or not a string, then it is `None`; three-argument `OpenRouterResult(...)` construction still works.
- [ ] Given each failure (timeout, connect error, upstream 500/503, upstream 429, upstream 400/401/404, malformed JSON, missing `choices`, null content, missing API key), when `call_openrouter` raises `OpenRouterError`, then `upstream_status` is the HTTP status or `None`, and `retryable` is `True` exactly for timeout, connect error, 5xx and 429; the message text of every existing failure is unchanged.
- [ ] Given `OPENROUTER_BASE_URL` unset, when a call is made, then the request URL is byte-identical to today's (`https://openrouter.ai/api/v1/chat/completions`) and STORY-001's characterization passes unchanged.
- [ ] Given `OPENROUTER_BASE_URL=http://127.0.0.1:9100/v1`, when a call is made, then it goes to `http://127.0.0.1:9100/v1/chat/completions`; given `http://example.com/v1`, `ftp://...` or an empty string, then settings fail at startup with a message naming the setting, the rule (`https`, or `http` on `127.0.0.1` / `localhost` / `::1`) and an example.
- [ ] Given the full suite, when it runs, then every existing `call_openrouter` stub (signature `(messages, model, api_key)`) and every existing test pass without change.

## Technical Notes

- `app/services/openrouter_client.py`: replace `_API_URL` with `f"{settings.OPENROUTER_BASE_URL.rstrip('/')}/chat/completions"`, read **per call**, for the reason `_context_limit_exceeded` gives (tests use `monkeypatch.setattr(settings, ...)`).
- `OpenRouterError.__init__(self, message, *, upstream_status=None, retryable=False)` keeps `str(exc)` identical, so audit `error_message` values and `/query`'s 502 `detail` do not move.
- Tell `httpx.TimeoutException` / `httpx.TransportError` (retryable, no status) apart from `httpx.HTTPStatusError` (status from `exc.response.status_code`). Shape and null-content failures are not retryable: the same request gets the same answer.
- `finish_reason` is declared after `output_tokens` with a default, following PRD-013 STORY-003's rule for `input_tokens`.
- `app/config.py`: new field with a `field_validator` in the style of `_validate_database_url` and the `_scheme_of` helper; add it to the setting-description map at the top of the module if that map lists every setting. The `.env.example` entry is written in STORY-019.
- PRD Section 9.2 T10: the validator is the mitigation for a setting that redirects the OpenRouter key. Its docstring says so.
- Tests: extend `tests/test_openrouter_client.py` and `tests/test_config.py`; no DB.
- Skills: none applicable.

## Dependencies

- **Blocked by**: STORY-001
- **Blocks**: STORY-009, STORY-011, STORY-014

## PRD Reference

Source: [`PRD-015-openai-compatible-endpoint/PRD.md`](../../PRDs/PRD-015-openai-compatible-endpoint/PRD.md) — sections 4 (Upstream client), 7.4, 7.5, 9.2 (T10), 9.3, 15 (D7, D10)
