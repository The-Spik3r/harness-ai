---
story: STORY-006
prd: PRD-018
plan: .agents/plans/PRD-018-db-resilience/completed/STORY-006-ingress-503-mapping.plan.md
epic_branch: epic/PRD-018-db-resilience
commit: 60f2904
status: COMPLETE
completed: 2026-11-17
---

# Implementation Report — STORY-006: 503 + Retry-After on every HTTP ingress

**Plan**: `.agents/plans/PRD-018-db-resilience/completed/STORY-006-ingress-503-mapping.plan.md`
**Epic Branch**: `epic/PRD-018-db-resilience`
**Commit**: `60f2904`

## Summary

New pure `app/services/storage_faults.py` holds the one "caused by `StorageUnavailableError`" rule (`storage_unavailable_cause`, one level), `retry_after_headers` and the fixed copy. `require_identity` answers 503 `Storage unavailable` + `Retry-After` (never 401). `POST /query` maps a gate error (`ChatSessionError`, `DuplicateCheckError`, `UsageLimitError`) caused by an outage to 503 with fixed detail + `Retry-After`; other causes keep the 500. `/v1` gets a `storage_unavailable` fault (503, `api_error`, retryable, no `x-should-retry`, `Retry-After`) and `_HTTP_ERRORS[503]`. `ActionAuditError` stays `internal_error`.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Shared rule + copy | `app/services/storage_faults.py` | done |
| 2 | `require_identity` 503 | `app/middleware/auth.py` | done |
| 3 | `/query` gate arm | `app/routers/query.py` | done |
| 4 | `storage_unavailable` fault, `V1Error.retry_after_seconds` | `app/services/v1_translate.py` | done |
| 5 | `/v1` mapping, `Retry-After` | `app/routers/v1.py` | done |
| 6 | `_FAULTS` pins extended (PRD-018 D8 comments) | `tests/test_v1_translate_result.py` | done |
| 7 | Ingress tests | `tests/test_db_resilience_ingress.py` | done |
| 8 | Targeted regression run | (below) | done |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| Targeted tests | 1040 passed, 1 failed (environmental), 0 skipped |
| New + translate tests alone | 97 passed |
| Full suite | GitHub CI on push (user decision) |

The one failure, `tests/test_query_router.py::test_full_pipeline_latency_within_budget`, is the known environmental dev-server latency failure on an untouched HEAD; not changed.

Files run: test_db_resilience_ingress, test_v1_translate_result, test_v1_errors, test_v1_sse, test_v1_router, test_v1_query_isolation, test_v1_models, test_v1_tools, test_query_router, test_auth_dependencies, test_admin_auth, test_untouched_app.

## Deviations from Plan (accepted by the orchestrator)

- `"harness": null` stays in the `/v1` 503 body (existing error schema).
- `_HTTP_ERRORS` lives in `app/routers/v1.py`, not `v1_translate.py`.
- `/query`'s identity 503 detail is "Storage unavailable"; `/v1` substitutes the fixed Section 10 sentence for code `storage_unavailable`.
- No `Retry-After` on a post-commit SSE event (headers already sent; unreachable today).
- `/query` router logs one WARNING (code + retry_after, no exception text).

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_db_resilience_ingress.py` | helper unit tests; identity 503 (fake route, `/query`, `/v1` json+sse, `/v1/models`); break-glass resolves; `/query` gates via open breaker (usage, duplicate, session); budget-exhausted `Retry-After: 1` with no driver text; `/v1` gates json+sse; non-transient causes keep 500; `ActionAuditError` stays `internal_error`; `_fault_code`; post-commit SSE event |
| `tests/test_v1_translate_result.py` | `_FAULT_CASES` + 503 row, status/retryable pins extended, `retry_after_seconds` test |

## Acceptance Criteria

- [x] Identity outage is 503, never 401; break-glass resolves (`test_identity_outage_is_503_never_401`, `test_break_glass_still_resolves_with_the_breaker_open`)
- [x] `/query` gate outage 503 + fixed detail, zero upstream calls, no row; non-transient keeps 500 (`test_query_gate_outage_is_503_with_nothing_sent`, `test_non_transient_cause_keeps_the_query_500`, `test_duplicate_check_storage_failure_returns_500` unchanged)
- [x] `/v1` json/stream `storage_unavailable` + `Retry-After`, no `x-should-retry`, `_HTTP_ERRORS[503]` (`test_v1_gate_outage_is_503_storage_unavailable`, `test_identity_outage_on_v1_*`)
- [x] `Retry-After` = `retry_after_seconds`; no driver text (`test_*_budget_exhausted_retry_after_is_one_and_nothing_leaks`)
- [x] Breaker forced open: all three ingresses, upstream zero calls (T1)
- [x] Backend imports
