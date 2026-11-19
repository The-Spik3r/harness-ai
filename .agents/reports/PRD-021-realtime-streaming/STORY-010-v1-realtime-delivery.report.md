---
story: STORY-010
prd: PRD-021
plan: .agents/plans/PRD-021-realtime-streaming/completed/STORY-010-v1-realtime-delivery.plan.md
epic_branch: epic/PRD-021-realtime-streaming
commit: pending
status: COMPLETE
completed: 2026-11-18
---

# Implementation Report - STORY-010: /v1 real-time SSE and reasoning_content

## Summary

`/v1` streams real time when the switch, the grant and the model capability allow it and `stream: true`; `reasoning_content` is added to chunks and bodies. Beyond the router: `Visibility.compute(streamed=)`, `QuerySuccessResponse._upstream_result`, `completion_events` role-chunk reasoning (all confirmed by the orchestrator). `_CommitSink(forward=False)` drops every put but the commit signal.

## Validation

| Check | Result |
|-------|--------|
| Backend import | OK |
| Targeted tests | 165 + 1601 + 71 passed (three sequential batches, 0 failed/skipped) |
| Full suite | GitHub CI on push (user decision) |

## Files

app/services/delivery.py, query_pipeline.py, v1_sse.py, v1_translate.py, app/models/schemas.py, v1_schemas.py, app/routers/v1.py, app/config.py (comment); tests/test_v1_realtime.py (new, 30 tests), additions to test_delivery.py, test_v1_schemas.py, test_v1_translate_result.py.

## Deviations

None from the plan. `realtime_events` also takes `include_usage` (the plan left it to the tail closure). The disconnect INFO line reads the commit id from the sink.

## Acceptance Criteria

- [x] AC1 sequence, ids, coalescing: test_v1_realtime.py (sequence_*, coalesce_*, burst drain)
- [x] AC2 reasoning_content: test_v1_schemas.py, test_v1_realtime.py reasoning tests
- [x] AC3 T1/T5: test_a_denied_call_never_leaks_its_fragments...
- [x] AC4 fault/disconnect/T13: fault, gate failure, disconnect, verdict warning tests
- [x] AC5 unchanged + latency: test_off_means_today_*, test_first_content_latency_p95...
