---
story: STORY-011
prd: PRD-015
plan: .agents/plans/PRD-015-openai-compatible-endpoint/completed/STORY-011-fault-mapping-and-retry-semantics.plan.md
epic_branch: epic/PRD-015-openai-compatible-endpoint
commit: a8ac6de
status: COMPLETE
completed: 2026-10-23
---

# Implementation Report — STORY-011: Upstream and internal fault mapping with deliberate retry semantics

**Plan**: `.agents/plans/PRD-015-openai-compatible-endpoint/completed/STORY-011-fault-mapping-and-retry-semantics.plan.md`
**Epic Branch**: `epic/PRD-015-openai-compatible-endpoint`
**Commit**: `a8ac6de`

## Summary

Before this story, an exception escaping `run_conversation` on `/v1` reached Starlette as a plain-text 500 with no OpenAI shape and no retry signal. Now each of the four pipeline faults maps to its PRD Section 7.5 row:

| Fault | Status | `code` | Retry signal |
|---|---|---|---|
| `OpenRouterError(retryable=True)`: timeout, connect error, upstream 5xx or 429 | 502 | `upstream_unavailable` | No `x-should-retry` header, so the SDK's status rule retries it |
| `OpenRouterError(retryable=False)`: upstream 4xx, unexpected shape, null content, missing key | 502 | `upstream_error` | `x-should-retry: false` |
| `DuplicateCheckError`, `UsageLimitError` | 500 | `internal_error` | No header (retryable) |
| `PiiRedactorError`, input or output | 500 | `redaction_failed` | `x-should-retry: false` |

The mapping table (`_FAULTS`) and `translate_fault(code, message)` live in the pure `v1_translate` module. The router's `_fault_code(exc)` turns the exception into its code. `V1Error.retryable` (default False) decides the header in `_from_v1_error`, so every verdict keeps its behaviour. `error.message` is `str(exc)`, the same text as `/query`'s `detail`. Each fault logs user id and code at WARNING, never the message.

The pipeline already writes `/query`'s rows for every fault, so `query_pipeline` is unchanged. The tests prove the audit side.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Fault codes, `_FAULTS`, `translate_fault`, `V1Error.retryable` | `app/services/v1_translate.py` | ✅ |
| 2 | Unit tests: each fault row, unknown code, only transient faults retry, schema fit, no verdict retryable | `tests/test_v1_translate_result.py` | ✅ |
| 3 | Router: `_PIPELINE_FAULTS`, `_fault_code`, the except around `run_in_pipeline`, retry header, WARNING log, `INTERNAL_ERROR` constant | `app/routers/v1.py` | ✅ |
| 4 | HTTP tests per fault: upstream over `httpx.MockTransport` through the real `call_openrouter`, storage, input/output redaction | `tests/test_v1_errors.py` | ✅ |
| 5 | Audit parity with `/query`, retry-then-answer, `session_id=None`, fault log line | `tests/test_v1_errors.py` | ✅ |
| 6 | Regression sweep: targeted, `-m "not db"`, full suite | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ |
| Frontend lint | n/a (no frontend in this repo) |
| `test_is_pure` (v1_translate imports unchanged) | ✅ |
| Targeted sweep (v1 translate / errors / router / isolation; query router / outcomes; duplicate scope) | ✅ 675 + 77 + 73 passed |
| `-m "not db"` (`HARNESS_TEST_LIBSQL_URL=http://127.0.0.1:9`, Docker-free) | ✅ 3,395 passed / 26 skipped (95.8 s) |
| Full suite (throwaway libSQL `:8086`) | ✅ 4,773 passed / 27 skipped (321.5 s), no flakes, 0 `libsql verdict` lines |
| Post-suite rerun: `test_v1_errors.py` + handoff guards (multiturn, pii integration, audit fields) | ✅ 158 passed |
| Mutation check: new tests against the pre-story `v1.py` | ✅ 20 of 21 new HTTP tests fail. The `session_id=None` test passes, as expected: it was already true |
| E2E (live uvicorn `:8765`, libSQL `:8087`, `openai` SDK) | ✅ 4/4 |

### E2E results

| Check | Outcome |
|-------|---------|
| `OPENROUTER_BASE_URL=http://127.0.0.1:9/v1` (closed port), POST `/v1/chat/completions` | 502 `upstream_unavailable`, no `x-should-retry`, message `OpenRouter request failed: [WinError 10061] ...`; 1 row with `success=false`, `ingress=v1`, `profile=code`, `streamed=false` |
| `OPENROUTER_API_KEY=` (empty), POST `/v1/chat/completions` | 502 `upstream_error`, `x-should-retry: false`; 1 row with `success=false` |
| Both starts, POST `/query` | 502 `{"detail": "..."}` with the same text, no OpenAI shape, no header, 1 row; unchanged |
| `openai.OpenAI(max_retries=2)` smoke | Closed port: `InternalServerError` 502 `upstream_unavailable` after **3** attempts (3 rows). Empty key: `InternalServerError` 502 `upstream_error` after **1** attempt (1 row), so the SDK honours `x-should-retry: false` on a 5xx. STORY-015 still owns the verification against the pinned SDK version |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/services/v1_translate.py` | UPDATE | +49/-3 |
| `app/routers/v1.py` | UPDATE | +63/-18 |
| `tests/test_v1_translate_result.py` | UPDATE | +64/-3 |
| `tests/test_v1_errors.py` | UPDATE | +419/-2 |
| `.agents/plans/.../completed/STORY-011-fault-mapping-and-retry-semantics.plan.md` | CREATE (archived) | +434 |

## Deviations from Plan

1. **`_fault_code` raises `TypeError` for an exception outside `_PIPELINE_FAULTS`.** The plan returned a code for each of the four types and did not say what happens otherwise. The branch is unreachable from the route, because the `except` clause only catches `_PIPELINE_FAULTS`. It is there so that STORY-013's reuse cannot silently mislabel a new exception. `translate_verdict` and `translate_fault` fail the same way. Two storage-free unit tests cover the mapping and the refusal (`test_fault_code_per_pipeline_fault`, `test_fault_code_refuses_an_unmapped_exception`).
2. **The E2E probe reads the audit rows from the E2E database directly, not through `/audit`.** `AuditQueryEntry` projects neither `success` nor `error_message`, and those are the fields the E2E checks.
3. **E2E process cleanup.** Stopping the backgrounded `bash serve.sh` left its uvicorn child holding `:8765`, so the second start failed to bind. I found the orphan by port, confirmed its command line, and stopped it. Each later server was stopped by PID. No effect on results.

Otherwise the implementation matched the plan, including design decisions 1–6.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_v1_translate_result.py` | `test_fault_maps_to_the_section_7_5_row` (×4), `test_unknown_fault_is_a_type_error`, `test_every_fault_is_a_5xx_and_only_transient_ones_retry`, `test_every_fault_type_fits_the_error_schema`, `test_no_verdict_is_retryable` |
| `tests/test_v1_errors.py` | `test_fault_code_per_pipeline_fault` (×5), `test_fault_code_refuses_an_unmapped_exception`, `test_retryable_upstream_fault_is_502_upstream_unavailable` (5xx, 429, connect, timeout), `test_deterministic_upstream_fault_is_502_upstream_error` (4xx, malformed, null-content), `test_missing_upstream_key_is_502_upstream_error`, `test_storage_fault_is_500_internal_error_retryable` (duplicate-lookup, usage-gate), `test_input_redaction_fault_is_500_redaction_failed`, `test_output_redaction_fault_is_500_redaction_failed`, `test_fault_rows_match_query_s` (×6), `test_retryable_upstream_failure_then_retry_is_answered_not_duplicate`, `test_run_conversation_gets_no_session`, `test_fault_logs_user_and_code_only` |

35 new tests: 8 in `test_v1_translate_result.py`, 27 in `test_v1_errors.py`.

## Acceptance Criteria

- [x] Given `OpenRouterError(retryable=True)` (timeout, connect, upstream 5xx, upstream 429), when it reaches the `/v1` route, then 502 `api_error` / `upstream_unavailable` without `x-should-retry: false`; given `retryable=False` (upstream 4xx, malformed shape, null content, missing key), then 502 `upstream_error` with `x-should-retry: false`.
- [x] Given `DuplicateCheckError` or `UsageLimitError`, when raised, then 500 `internal_error`, retryable; given `PiiRedactorError` (input or output), then 500 `redaction_failed` with `x-should-retry: false`.
- [x] Given each fault, when the audit is read, then the rows are exactly what `/query` writes for the same fault today (one `success=False` row for upstream and redaction errors; none for a failed duplicate lookup or usage gate), with `ingress='v1'`.
- [x] Given an upstream error message, when it becomes `error.message`, then it is the client's `OpenRouterError` text and never contains the provider's response body.
- [x] Given a retryable upstream failure retried once by a client and then answered, when the audit is read, then the failed attempt is `success=False` and the retry is not held as a duplicate (PRD-009 Section 6.3).
- [x] All tasks completed
- [x] `-m "not db"` suite passes; ASCII-only test output
- [x] `/query` bodies unchanged (`tests/test_v1_query_isolation.py` passes unmodified)
- [x] Follows existing patterns
