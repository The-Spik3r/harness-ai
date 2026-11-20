---
story: STORY-012
prd: PRD-022
plan: .agents/plans/PRD-022-provider-fallback-and-native-adapters/completed/STORY-012-pipeline-chain-buffered.plan.md
epic_branch: epic/PRD-022-provider-fallback-and-native-adapters
commit: pending
status: COMPLETE
completed: 2026-11-20
---

# Implementation Report - STORY-012: Pipeline chain integration (buffered)

## Summary

`run_conversation` asks `chain_config.chain_for(model, ingress)` once. No chain, or a streamed step, keeps the PRD-020/021 single call. A chained buffered request runs `chain.run` with per-candidate `prepare` (redaction from the raw text, T3), `attempt`, `on_attempt_failed`, `permitted` (RBAC per fallback, D7). Rows: one per failed attempt (written before the next candidate), one exhaustion row when no attempt ran, and a success row from the answering attempt. Step 6's body is the pure `_prepare_input`. Orchestrator note 3.2 applied: no attempt run and primary skipped as `redaction_limit` keeps `QueryBlockedContextLimitResponse` and the limit row.

## Validation

| Check | Result |
|-------|--------|
| Backend import | OK |
| New tests (`tests/test_query_pipeline_chain.py`) | 24 passed |
| Other targeted files | see counts below |
| Full suite | GitHub CI on push (user decision) |

Targeted runs (libSQL is ~3 s per DB test here, so the set was narrowed and run sequentially):
- audit_fields + audit_realtime + routing: 123 passed, 1 failed (source-guard census 12 vs 11, caused by the substring `log_query(` in one of my comments; reworded, guard re-run: passed).
- break_glass + authorization: 38 passed.
- pii_relaxation, context_limit, run_conversation, usage_limits, tools, streaming, prd020_legacy_fixtures, untouched_app, chain_runner, pii_redaction_integration, query_router, v1_router, v1_realtime, v1_query_isolation, session_passthrough: 364 passed, 1 failed: `test_query_router.py::test_full_pipeline_latency_within_budget` (0.58 s > 0.5 s). It fails identically with `query_pipeline.py` stashed (slow local libSQL), so it is environmental.
- Not run (time): delivery, gates, multiturn, patterns, dedup_key, max_context_tokens, usage_estimate, pii_profiles, audit-fields rerun, v1_errors, v1_sse, v1_tools*, v1_translate*, v1_schemas, v1_models*.

## Files Changed

| File | Action |
|------|--------|
| `app/services/query_pipeline.py` | UPDATE (`_Prepared`, `_OverLimit`, `_prepare_input`, `_forces_tool`; local row helpers; chain branch; row fields) |
| `tests/test_query_pipeline_chain.py` | CREATE (24 tests) |

## Deviations from Plan

- The source guards need the literal `relaxed = route.relaxes_input()` once and `pii_input_relaxed=relaxed` five times, so the three step-6/7 row helpers take a keyword `relaxed` and `_prepare_input` names its local `skip_input`.
- A loaded chain always passes `timeout=` to attempts (the provider's timeout when no chain deadline is set), because `chain.run` with limits computes one. The no-chain path passes none.
- `test_byok_single_attempt_lists_byok_skips` is named `..._key_reaches_only_the_primary` (the failure row carries no skip list; the key assertion is what it proves).
- Known limitation as instructed: skips after the last attempt appear only in counters.

## Acceptance Criteria

- [x] AC1 no chain is PRD-020: `test_no_chain_is_prd020_path`, `test_no_chain_failure_row_is_attempt_one`, unmodified legacy files
- [x] AC2 fallback rows: `test_503_then_fallback_two_rows`, `test_failure_row_written_before_next_attempt`
- [x] AC3 per-route redaction and limits: `test_fallback_redacts_from_raw_for_the_receiving_route`, `test_candidate_over_code_limit_is_skipped`, `test_redaction_error_on_candidate_fails_closed`, plus the two 3.2 tests
- [x] AC4 exhaustion: `test_exhausted_without_attempt_writes_one_row`, `test_query_route_maps_exhausted_to_502`, `test_v1_route_maps_exhausted_to_upstream_unavailable`, `test_byok_single_attempt_key_reaches_only_the_primary`
- [x] AC5 usage and model_used: `test_admit_and_charge_once`, `test_model_used_response_vs_audit`, `test_success_row_lists_skips`, `test_resend_after_all_failed_is_answered`
- [x] Realtime single-candidate: `test_streamed_request_on_chained_model_stays_single_candidate`
