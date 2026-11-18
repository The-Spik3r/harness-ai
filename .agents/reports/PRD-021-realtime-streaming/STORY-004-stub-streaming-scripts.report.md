---
story: STORY-004
prd: PRD-021
plan: .agents/plans/PRD-021-realtime-streaming/completed/STORY-004-stub-streaming-scripts.plan.md
epic_branch: epic/PRD-021-realtime-streaming
commit: pending
status: COMPLETE
completed: 2026-11-18
---

# Implementation Report - STORY-004: Stub upstream streams scripted replies with delays, reasoning and faults

**Plan**: `.agents/plans/PRD-021-realtime-streaming/completed/STORY-004-stub-streaming-scripts.plan.md`
**Epic Branch**: `epic/PRD-021-realtime-streaming`
**Commit**: `pending`

## Summary

`scripts/stub_openrouter.py` accepts `stream: {chunk_chars, delay_ms, reasoning, fail_after}` on a reply (PRD-021 F10). It is used only when the request has `stream: true`. Emission order: reasoning deltas (`delta.reasoning`), content deltas, tool-call fragments, finish chunk, usage chunk (when `include_usage`), `[DONE]`. A reply without a shape, or a request without `stream: true`, is answered as before.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | `StreamShape`, `Reply.stream`, `_parse_stream`, key sets | `scripts/stub_openrouter.py` | done |
| 2 | `_send_sse`: pieces helper, delta/tail split, `delay_ms`, `fail_after` | `scripts/stub_openrouter.py` | done |
| 3 | Module docstring paragraph (PRD-021 F10) | `scripts/stub_openrouter.py` | done |
| 4 | Tests | `tests/test_stub_openrouter.py` | done |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| Tests | 221 passed (test_stub_openrouter, test_upstream_adapter, test_upstream_stream_collect, test_stream_upstream_seam, test_untouched_app) |
| E2E | real stub over a socket through `stream_upstream` with a file-mode registry: 2/2 |

Full suite: GitHub CI on push (user decision).

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `scripts/stub_openrouter.py` | UPDATE | +98/-22 |
| `tests/test_stub_openrouter.py` | UPDATE | +203 |

## Deviations from Plan

- No `app/` change was needed. The orchestrator's contingency (wrap mid-stream `httpx.HTTPError` in `OpenAICompatibleAdapter.stream()`) was not triggered: with `fail_after`, the real stub through `stream_upstream` raised `UpstreamError` with `retryable is False`. The error comes from EOF with no `Finish` ("stream ended without a finish reason"), not from a transport error. `stream()` already maps `httpx.HTTPError` around the whole iteration, so no new seam test was added.
- Without a shape, empty content still emits one empty content delta (today's bytes); with a shape, empty content emits none. The plan said "no delta, as today", which was inaccurate for the no-shape case.
- The adapter always requests usage, so `stream_upstream` on a default reply yields `UsageReport` after `Finish`; the reasoning-order test filters it.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_stub_openrouter.py` | chunk_chars content + finish/usage/DONE; nine tool-arg fragments (72 chars, 8); delay_ms incl. first delta; reasoning before content; fail_after (K=2, K=0); stream_upstream maps reasoning; stream_upstream raises non-retryable UpstreamError after fail_after; log never carries content/reasoning; shape without stream request = same JSON; 10 parametrized bad shapes (default and rule); rejected reasoning never echoed |

## Acceptance Criteria

- [x] chunk_chars, finish, usage, `[DONE]` - `test_stream_chunk_chars_splits_content_and_ends_with_finish_usage_done`, `..._nine_fragments`
- [x] delay_ms incl. first chunk - `test_stream_delay_ms_spaces_every_delta_including_the_first`
- [x] reasoning before content - `test_stream_reasoning_deltas_precede_content`, `test_stream_upstream_maps_scripted_reasoning`
- [x] fail_after drops without finish/`[DONE]` - `test_stream_fail_after_drops_the_connection_without_finish`, `test_stream_upstream_raises_upstream_error_after_fail_after`
- [x] log has no content/reasoning; unchanged without shape - `test_stream_shape_never_reaches_the_log`, `test_shape_without_stream_request_answers_json_as_today`, existing SSE tests untouched and passing
