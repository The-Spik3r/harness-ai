---
story: STORY-007
prd: PRD-001
plan: .agents/plans/PRD-001-harness-ia/completed/STORY-007-openrouter-client.plan.md
epic_branch: epic/PRD-001-harness-ia
commit: 6c80f25
status: COMPLETE
completed: 2026-07-04
---

# Implementation Report — STORY-007: OpenRouter API client wrapper

**Plan**: `.agents/plans/PRD-001-harness-ia/completed/STORY-007-openrouter-client.plan.md`
**Epic Branch**: `epic/PRD-001-harness-ia`
**Commit**: `6c80f25`

## Summary

Implemented `app/services/openrouter_client.py`, a thin synchronous wrapper around OpenRouter's chat-completion endpoint. `call_openrouter(prompt, model="gpt-4", api_key=None, client=None)` resolves the API key (per-request argument first, `settings.OPENROUTER_API_KEY` fallback), sends a single-user-message chat completion request, and returns an `OpenRouterResult` dataclass (`response`, `model_used`, `tokens_used`). All failure modes — missing key, network error, non-2xx status, malformed response body — are wrapped into one typed `OpenRouterError`, following the existing `DuplicateCheckError` convention. Testability is via an injectable `client` parameter; no new mocking dependency was added.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Create OpenRouterError, OpenRouterResult, call_openrouter | `app/services/openrouter_client.py` | ✅ |
| 2 | Create unit tests via injectable fake HTTP client | `tests/test_openrouter_client.py` | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`app.main`) | ✅ |
| Module import (`openrouter_client`) | ✅ |
| Tests | ✅ (9 new / 45 total passed) |
| E2E | ✅ (4/4 acceptance-criteria checks) |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/services/openrouter_client.py` | CREATE | +63 |
| `tests/test_openrouter_client.py` | CREATE | +99 |

## Deviations from Plan

None. Implementation matches the plan exactly, including the design decisions (sync `httpx.Client`, single `OpenRouterError` class, injectable `client` param, no new dependency, 30s fixed timeout).

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_openrouter_client.py` | `test_success_returns_response_model_and_tokens`, `test_default_model_used_when_omitted`, `test_per_request_api_key_overrides_env`, `test_falls_back_to_env_key_when_not_provided`, `test_missing_key_raises_config_error`, `test_network_error_raises_openrouter_error`, `test_non_2xx_status_raises_openrouter_error`, `test_malformed_response_body_raises_openrouter_error`, `test_api_key_never_appears_in_error_message` |

## Acceptance Criteria

- [x] Given a prompt and a model name, when the client calls OpenRouter, then it returns the model's text response and token usage.
- [x] Given no `model` is specified upstream, when the client is invoked, then it defaults to `"gpt-4"` per PRD Section 10.
- [x] Given a per-request `openrouter_api_key` is provided, when the client calls OpenRouter, then it uses that key instead of the `OPENROUTER_API_KEY` env var; given neither is provided, then it raises a clear configuration error.
- [x] Given OpenRouter returns an error or times out, when the client is invoked, then it surfaces a typed error (not a raw exception) so the caller can log `success=false` with an `error_message`.
