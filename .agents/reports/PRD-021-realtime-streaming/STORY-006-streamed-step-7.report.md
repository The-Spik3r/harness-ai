---
story: STORY-006
prd: PRD-021
plan: .agents/plans/PRD-021-realtime-streaming/completed/STORY-006-streamed-step-7.plan.md
epic_branch: epic/PRD-021-realtime-streaming
commit: pending
status: COMPLETE
completed: 2026-11-18
---

# Implementation Report — STORY-006: Streamed step 7 with phases, held tool calls and real-time charging

## Summary

Step 7 of `run_conversation` gains a streamed arm, taken only when `visibility.upstream_streamed`: it iterates the injectable `stream_upstream=`, signals `committed` once on the first event, emits `waiting` and then phase changes via the new pure `stream_assembly.phase_of`, forwards non-empty text (and reasoning, with both grants) raw to the sink at two marked gate seams, holds every `ToolCallDelta`, and builds the `UpstreamResult` with `collect()` so steps 7b/7c/8 are unchanged. A buffered call with a sink commits on entry. A mid-stream `UpstreamError` after something was released charges the PRD-020 D8 estimate of everything received before the failure row. `OpenAICompatibleAdapter.stream()` enforces one total deadline (D20). `sink=None` is today's path.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | pure `phase_of` | `app/services/stream_assembly.py` | done |
| 2 | total stream deadline | `app/services/upstream/openai_compatible.py` | done |
| 3-4 | `stream_upstream=` kwarg, locals, step 7 arms, T6 charge | `app/services/query_pipeline.py` | done |
| 5 | tests | `tests/test_stream_assembly.py`, `tests/test_query_pipeline_streaming.py`, `tests/test_upstream_adapter.py` | done |

## Validation Results

| Check | Result |
|---|---|
| Backend import | OK |
| Tests | 115 passed, 0 failed (stream_assembly, query_pipeline_streaming, upstream_adapter, query_pipeline_delivery, query_pipeline_run_conversation, untouched_app) + 44 passed test_upstream_stream_collect |

Full suite: GitHub CI on push (user decision). Existing tests updated with PRD-021 comments: delivery matrix and queue-sink test (content and phase/committed now flow), run_conversation signature (gains `stream_upstream`).

## Deviations from Plan

- `model_used` on the streamed result is reset to the requested id (`dataclasses.replace(..., model_used=model)`), as `call_upstream` does (PRD-020 D13). The plan did not mention it; a test caught it.
- T6 estimate (orchestrator correction): counts all non-empty text and reasoning plus every held tool call, passed to `estimate_tokens` as `ToolCallSpec`s built per index from the fragments. `estimate_tokens` counts a call by its `arguments` only, so names add nothing.
- The plan's `released_text` list became `received_text` (everything received) plus a `released` flag.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_stream_assembly.py` | `phase_of` rules, empty/nameless events, kind mapping, change-only, never returns text, purity (AST) |
| `tests/test_query_pipeline_streaming.py` | commit once/rt id, buffered commit on entry, no commit on early fault, sink=None, phases, content order, reasoning grants, no fragment reaches a sink, 7c over collect, usage modes, mid-stream charge before failure row, nothing charged before release, held calls raise the estimate, BYOK not charged, total deadline end to end |
| `tests/test_upstream_adapter.py` | `test_stream_total_deadline_bounds_whole_stream` |

## Acceptance Criteria

- [x] AC1 commit and id (`test_committed_once_on_first_event_with_rt_id`, `test_buffered_commits_on_entry`, `test_no_commit_when_iterator_raises_first`, `test_sink_none_is_todays_path`)
- [x] AC2 phases (`test_stream_assembly.py`, `test_waiting_then_changes_only`)
- [x] AC3 forwarding and held calls (`test_content_in_order_skips_empty`, `test_reasoning_only_with_both_grants`, `test_no_tool_fragment_reaches_any_sink_method`, `test_7c_runs_over_collect_calls`)
- [x] AC4 usage mode (`test_realtime_missing_usage_is_estimated_on_error_provider`, `test_progress_only_error_provider_still_raises`)
- [x] AC5 mid-stream fault (`test_fault_after_release_charges_estimate_before_failure_row`, `test_fault_before_release_charges_nothing`, `test_fault_counts_everything_received_including_held_calls_and_reasoning`)
- [x] D20 (`test_stream_total_deadline_bounds_whole_stream`, `test_total_deadline_through_the_default_stream_upstream`)
