---
story: STORY-013
prd: PRD-022
plan: .agents/plans/PRD-022-provider-fallback-and-native-adapters/completed/STORY-013-v1-response-surfaces.plan.md
epic_branch: epic/PRD-022-provider-fallback-and-native-adapters
commit: pending
status: COMPLETE
completed: 2026-11-20
---

# Implementation Report - STORY-013: /v1 response surfaces

## Summary

The pipeline sets a private `_answered_by` (`AnsweredBy(provider, model, attempts)`) on the only `QuerySuccessResponse(` it builds, so every real success carries it. `translate_result` copies it into `harness.provider` / `harness.attempts` (dropped when None); `_json_response` adds `X-Harness-Provider`. `translate_exhausted` (pure) classifies `ChainExhausted` from its attributes; the router calls it before the generic fault path. `/query` is untouched.

## Validation

| Check | Result |
|-------|--------|
| Backend import | OK |
| tests/test_v1_translate_result, v1_schemas, v1_translate_request, v1_sse, schemas, untouched_app | 822 passed |
| tests/test_query_pipeline_chain.py | 35 passed |
| test_v1_errors/test_v1_router/test_prd020_legacy_fixtures (-k upstream/fault/unavailable) | 37 passed, 55 deselected |
| Full suite | GitHub CI on push (user decision) |

## Deviations from Plan

- Accepted by the orchestrator: buffered SSE carries only the answering `model`; `X-Harness-Provider` and `harness.provider/attempts` are JSON-only (headers are committed before the answer exists).
- `query_pipeline.py` has exactly one `QuerySuccessResponse(` construction; it is guarded by `route is not None` (always set on a success).

## Acceptance Criteria

- [x] AC1 answering model / harness fields / header (JSON): `test_v1_answer_without_fallback...`, `test_v1_fallback_answer...`, `test_v1_buffered_sse_carries_the_answering_model`, unit provenance tests
- [x] AC2 502 `upstream_unavailable` + `Retry-After` (none when None): `test_v1_total_outage...`, `test_v1_exhaustion_without_retry_after...`, unit matrix
- [x] AC3 non-eligible keeps `upstream_error`; capability-only non-retryable naming the reason: `test_v1_capability_only_exhaustion...`, `test_v1_last_attempt_4xx...`
- [x] AC4 T10 / existing tests unmodified: `test_v1_exhaustion_never_leaks_the_upstream_text`; `/query` body: `test_query_success_body_has_no_provenance_keys`
