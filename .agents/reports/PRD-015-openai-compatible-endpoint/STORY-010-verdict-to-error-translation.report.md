---
story: STORY-010
prd: PRD-015
plan: .agents/plans/PRD-015-openai-compatible-endpoint/completed/STORY-010-verdict-to-error-translation.plan.md
epic_branch: epic/PRD-015-openai-compatible-endpoint
commit: 0cd544c
status: COMPLETE
completed: 2026-10-23
---

# Implementation Report — STORY-010: Verdicts to OpenAI error objects; /v1-scoped 400/401/403 handlers; /query isolation

**Plan**: `.agents/plans/PRD-015-openai-compatible-endpoint/completed/STORY-010-verdict-to-error-translation.plan.md`
**Epic Branch**: `epic/PRD-015-openai-compatible-endpoint`
**Commit**: `0cd544c`

## Summary

`v1_translate.translate_verdict` is pure. It maps each blocked `QueryPipelineResult` member to its PRD Section 7.5 status, `type` and `code`. It uses one table (`_VERDICTS`) keyed on the response type and refines the code in two cases: `limit == "redaction_characters"`, and `required_permission` starting with `query:model:` or equal to `ingress:break_glass`. The message is the reason plus its details. `harness` is every response field except `status`. Content verdicts are 400 and policy verdicts are 403; none is 429 or 5xx.

The router now returns that verdict where STORY-009 returned a 501 placeholder. `_error` adds `x-should-retry: false` to every 4xx. `install_error_handlers` registers app-level handlers for Starlette's `HTTPException` and FastAPI's `RequestValidationError`. They return the OpenAI shape only under `/v1/` and delegate to FastAPI's defaults on every other path. They are installed only when `V1_ENABLED` is on.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Pure verdict translation (constants, `V1Error`, `_VERDICTS`, `translate_verdict`) | `app/services/v1_translate.py` | ✅ |
| 2 | Unit tests for every verdict cell, a completeness test over the union, no 429/5xx | `tests/test_v1_translate_result.py` | ✅ |
| 3 | Router: verdict response, `x-should-retry` on 4xx, INFO log on `V1RequestError` | `app/routers/v1.py` | ✅ |
| 4 | Path-scoped `HTTPException` / `RequestValidationError` handlers, `install_error_handlers` | `app/routers/v1.py` | ✅ |
| 5 | Wire the handlers inside the `V1_ENABLED` block | `app/main.py` | ✅ |
| 6 | Rewrite the blocked-result placeholder test | `tests/test_v1_router.py` | ✅ |
| 7 | Per-verdict and shape-refusal HTTP tests | `tests/test_v1_errors.py` | ✅ |
| 8 | The `/v1` half of the isolation test (append-only) | `tests/test_v1_query_isolation.py` | ✅ |
| 9 | Regression sweep: targeted, `-m "not db"`, full suite | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ |
| Frontend lint | n/a (no frontend in this repo) |
| Targeted sweep (v1 + query router/outcomes/audit-fields/break-glass/multiturn) | ✅ 921 passed |
| `-m "not db"` | ✅ 3,387 passed / 26 skipped (85.8 s) |
| Full suite (throwaway libSQL `:8086`) | ✅ 4,744 passed / 27 skipped (322 s), no flakes |
| E2E (live uvicorn `:8765`, libSQL `:8087`, `openai` SDK) | ✅ 6/6 |

### E2E results

| Check | Outcome |
|-------|---------|
| Injection prompt via `openai.OpenAI(max_retries=2)` | `BadRequestError`, status 400, `code=suspicious_pattern`, **exactly 1** audit row (`ingress=v1`), so the SDK did not retry |
| Wrong API key | `AuthenticationError`, 401 `invalid_api_key`, 0 rows |
| `ADMIN_TOKEN` as the API key (AC 2) | `PermissionDeniedError`, `break_glass_not_permitted`, 1 row with `denied_permission=ingress:break_glass`, `ingress=v1` |
| `POST /query` with no bearer | `{"detail":"Invalid or missing credential"}`, unchanged |
| `POST /v1/chat/completions` with a non-JSON body and a bearer | 400 `invalid_request`, `x-should-retry: false` |
| `GET /v1/nope` | 404 in OpenAI shape, `code=not_found` |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/services/v1_translate.py` | UPDATE | +135/-5 |
| `app/routers/v1.py` | UPDATE | +143/-10 |
| `app/main.py` | UPDATE | +3/-1 |
| `tests/test_v1_errors.py` | CREATE | +480 |
| `tests/test_v1_translate_result.py` | UPDATE | +174/-4 |
| `tests/test_v1_query_isolation.py` | UPDATE | +84/-1 |
| `tests/test_v1_router.py` | UPDATE | +13/-9 |

## Deviations from Plan

- **The plan's chat-UI risk named the wrong framework.** It said NiceGUI might register its own 404 handler. The chat UI is Reflex: `rx.App(api_transformer=fastapi_app)` mounts `app.main.app` as a sub-app at the root. The sub-app's own exception middleware handles its exceptions, and `request.url.path` keeps the full `/v1/...` path, so the handlers behave the same there. No change was needed.
- **The isolation test docstring changed by one sentence.** "Only the no-bearer test…" became "Only the no-bearer tests…", and a paragraph was added naming the `/v1` half. No STORY-001 pin (assertion) was touched; `git diff` shows that docstring line as the only removal.
- **More shape-refusal tests than planned.** Besides those in the plan, `test_v1_errors.py` pins a schema failure for a missing `model` and for an empty body, checks that the 405 keeps its `Allow` header after the `x-should-retry` merge, and checks that a 404 outside `/v1` keeps FastAPI's body with no retry header.
- **The usage `requests` verdict is forced by seeding the current minute's window** (`window_requests=1`, rate `*=1`), not by sending two requests. That is the same lever as outcome 8 and needs one fewer request.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_v1_translate_result.py` | `test_verdict_maps_to_the_section_7_5_row` (11 cells: duplicate, suspicious, context messages/characters, redaction, forbidden query:submit/query:byok/query:model/break-glass, usage requests/tokens); `test_harness_is_every_field_but_status`; `test_every_blocked_member_has_a_verdict`; `test_no_verdict_is_retryable_by_status`; `test_success_has_no_verdict`; `test_every_verdict_type_fits_the_error_schema` |
| `tests/test_v1_errors.py` | One HTTP test per verdict through the real pipeline (duplicate, suspicious, context messages, context characters, redaction, model, break-glass with row, token budget, request rate); pipeline `query:submit` via a replaced `run_conversation`; 401 no bearer / unknown bearer; 403 auditor; 400 non-JSON; 400 schema failures (4 params); `V1RequestError` (`n: 2`); 405 with `Allow`; `/v1/nope` 404; outside-`/v1` 404 untouched; T9 log tests for the request refusal, validation refusal and dependency refusal; T6 canary absent from every body and log |
| `tests/test_v1_query_isolation.py` | `/v1` 401 without a bearer (no DB), 401 unknown bearer, 403 auditor, 400 empty body, and one app answering both shapes in a `/query` → `/v1` → `/query` sequence |
| `tests/test_v1_router.py` | `test_blocked_result_is_translated_verdict` (replaces `test_placeholder_blocked_result_is_501`) |

## Acceptance Criteria

- [x] Every pipeline verdict listed in AC 1 has exactly the PRD 7.5 status, `type` and `code`; `error.harness` carries every field of the pipeline response (except the constant `status`, design decision 3); `error.message` is the reason plus its details.
- [x] `ADMIN_TOKEN` as the bearer gives 403 `break_glass_not_permitted` and the PRD-013 refusal row with `denied_permission='ingress:break_glass'` and `ingress='v1'` (test and live E2E).
- [x] No bearer, an invalid bearer, no `query:submit`, a non-JSON body, a schema failure and a `V1RequestError` all return the error object (401 `invalid_api_key` / 403 `permission_denied` / 400 `invalid_request` or the translation code) with `param` where known, and no audit row.
- [x] Every `/v1` 4xx carries `x-should-retry: false`; no `/v1` verdict is 429 or 5xx.
- [x] `tests/test_v1_query_isolation.py`: every `/query` body is unchanged, and the new `/v1` half passes.
- [x] All tasks completed
- [x] The backend imports and the server starts without error
- [x] Follows existing patterns (pure translator, the single `_error` helper, whole-body test pins)
