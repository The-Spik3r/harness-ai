---
story: STORY-014
prd: PRD-022
plan: .agents/plans/PRD-022-provider-fallback-and-native-adapters/completed/STORY-014-streaming-fallback-window.plan.md
epic_branch: epic/PRD-022-provider-fallback-and-native-adapters
commit: pending
status: COMPLETE
completed: 2026-11-20
---

# Implementation Report - STORY-014: Streaming fallback window

## Summary

The streamed branch of `run_conversation` is now the per-attempt closure `stream_attempt`.
With a chain, `chain.run` drives it (`released=lambda: released` read live,
`RequestNeeds.streaming=streamed_step`); without one it is called once with today's
arguments (no `timeout`). Per-attempt state (received buffers, gates, events, divergence
flag, phase) is created inside the closure; only the commit id, `released` and
`reasoning_sent` span attempts. The T6 charge moved to `_charge_received`, called from the
closure before the row. One row per attempt: `on_attempt_failed` writes `UpstreamError`
rows, the closure writes the gate `PiiRedactorError` row only when chained, the outer
`except` only when unchained. No `log_query(` site added (census: 11).

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| Targeted tests | 287 passed in total, 0 failed, 0 skipped (3 pytest runs, see below) |
| Full suite | GitHub CI on push (user decision) |

Runs: streaming + audit_realtime + routing 73 passed; chain_stream + chain + chain_runner +
pii_relaxation 119 passed; stream_upstream_seam + v1_realtime + untouched_app +
pii_redaction_integration 95 passed. PRD-021 streaming test files unmodified.

## Files Changed

| File | Action |
|------|--------|
| `app/services/query_pipeline.py` | UPDATE |
| `tests/test_query_pipeline_chain_stream.py` | CREATE (18 tests) |
| `tests/test_query_pipeline_chain.py` | UPDATE (one test rewritten) |
| `tests/test_pii_redaction_integration.py` | UPDATE (superseded name registered) |

## Deviations from Plan

- On a chain the streamed result's `model_used` is `candidate_route.model_id` (plan said
  `model`): the response must carry the answering id (D17), as the buffered attempt does;
  rows still carry the requested id. Unchained keeps `model`.
- `test_streamed_request_on_chained_model_stays_single_candidate` renamed to
  `test_streamed_request_on_chained_model_walks_the_chain` and now asserts exhaustion with
  `remote:capability` skip and one `attempt=None` row; old name registered in
  `_DELIBERATELY_SUPERSEDED_TESTS`.
- Test registry needs `capability_scoped: true` on the non-streaming chain entry (chain validation F3).

## Acceptance Criteria

- [x] AC1 fall back before release, one commit: `test_open_error_before_any_event_falls_back`, `test_events_then_error_before_release_falls_back_with_no_leak`, `test_v1_fallback_before_release_streams_the_answer_once`
- [x] AC2 post-release fault, charged row, SSE error: `test_fault_after_release_is_not_retried_and_is_charged_once`, `test_reasoning_release_closes_the_window_like_content`, `test_v1_fault_after_release_is_an_sse_error_and_one_attempt`
- [x] AC3 capability skip: `test_candidate_without_streaming_is_skipped_capability`
- [x] AC4 fresh state: `test_529_in_stream_falls_back_and_an_empty_delta_does_not_close_the_window`, the no-leak test, `test_gate_failure_*`
- [x] AC5 no chain: `test_no_chain_is_one_stream_call_with_todays_arguments` + unmodified PRD-021 files
