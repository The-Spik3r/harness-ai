---
story: STORY-005
prd: PRD-021
plan: .agents/plans/PRD-021-realtime-streaming/completed/STORY-005-delivery-sink-and-visibility.plan.md
epic_branch: epic/PRD-021-realtime-streaming
commit: pending
status: COMPLETE
completed: 2026-11-18
---

# Implementation Report — STORY-005: DeliverySink, step 2d visibility and stage events

## Summary

New pure module `app/services/delivery.py` (vocabularies, event dataclasses, `DeliverySink`, `Visibility`, `QueueSink`) and a trailing keyword-only `sink=None` on `run_conversation`. With a sink, the pipeline wraps it in a fault-swallowing `_SafeSink`, emits config-only stage events, and computes `Visibility` after step 2c into a local. With `sink=None` nothing is computed. `content`/`reasoning`/`phase`/`committed` are defined, never called.

## Files Changed

| File | Action |
|------|--------|
| `app/services/delivery.py` | CREATE |
| `app/services/query_pipeline.py` | UPDATE (`_SafeSink`, `sink=`, stages, step 2d) |
| `tests/test_delivery.py` | CREATE |
| `tests/test_query_pipeline_delivery.py` | CREATE |
| `tests/test_query_pipeline_run_conversation.py` | UPDATE (signature gains `sink`) |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| Tests | 181 passed, 0 failed, 0 skipped (test_delivery, test_query_pipeline_delivery, _run_conversation, _usage_limits, _audit_fields, test_untouched_app) |
| E2E | QueueSink via `run_in_pipeline` on a real loop: stage events in order (test). `/query` unchanged: covered by existing pipeline/untouched-app suites |

Full suite: GitHub CI on push (user decision).

## Deviations from Plan

None. Python 3.12: `asyncio.Queue()` created in `QueueSink.__init__` off-loop works.

## Acceptance Criteria

- [x] AC1 pure module, protocol, vocabularies, Visibility, QueueSink: tests/test_delivery.py
- [x] AC2 `sink=None` computes nothing: test_no_sink_computes_nothing...; signature test
- [x] AC3 step 2d after 2c, never on refusal, holds() (T8): refusal tests, RBAC-off test, matrix
- [x] AC4 config-only stage events: ordered-list tests, T10 test
- [x] AC5 content/reasoning never called: matrix test
- [x] Sink-fault isolation: test_a_failing_sink_changes_nothing_and_logs_once
