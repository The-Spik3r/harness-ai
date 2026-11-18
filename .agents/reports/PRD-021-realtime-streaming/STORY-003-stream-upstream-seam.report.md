---
story: STORY-003
prd: PRD-021
plan: .agents/plans/PRD-021-realtime-streaming/completed/STORY-003-stream-upstream-seam.plan.md
epic_branch: epic/PRD-021-realtime-streaming
commit: a91252a
status: COMPLETE
completed: 2026-11-18
---

# Implementation Report - STORY-003: stream_upstream seam, ReasoningDelta and collect()'s usage override

## Summary

Added `ReasoningDelta`, the opt-in `reasoning` flag in `parse_events` and `stream()`, the stream-end-without-`Finish` error (PRD-021 F2), `collect(usage_missing=...)`, and `stream_upstream()` sharing a private `_resolve_call` with `call_upstream`. Only `app/services/upstream/` changed; `call_upstream` behaviour and messages are unchanged.

## Validation

| Check | Result |
|-------|--------|
| Backend import | OK |
| Targeted tests (seam, stream_collect, adapter, prd020_legacy_fixtures, query_pipeline_routing, untouched_app, stub_openrouter, provider_routing) | 331 passed |
| tests/test_openrouter_client.py | 127 passed |
| E2E (stream_upstream against stub, file-mode registry) | `test_stream_upstream_against_the_stub_collects_to_the_stub_answer` passed |
| Full suite | GitHub CI on push (user decision) |

## Deviations from Plan

- Plan conflict 1 (`{"content": "x", "finish_reason": None}` diverging in the property test) did not materialise: the stub always emits a finish chunk, so the property test passes unchanged. The divergence is covered by its own test (`test_null_finish_chunk_stream_raises_while_complete_would_answer`).
- Conflict 2 tests were fixed by appending a `finish_reason: "stop"` chunk with PRD-021 F2 comments (5 tests: blank-lines, empty-choices usage, payload_keys, owned-client full read, injected client).

## Tests Written

`tests/test_stream_upstream_seam.py` (34 tests): AC1-AC5, fixture replays, empty-content parity, `_USAGE_MODES` pinned to the registry, eager errors, key choice, legacy never maps reasoning.

## Acceptance Criteria

- [x] AC1 ReasoningDelta frozen, in union, exported
- [x] AC2 opt-in reasoning, fixture replay
- [x] AC3 collect ignores reasoning; property test passes
- [x] AC4 usage_missing override
- [x] AC5 stream_upstream, eager errors, no-Finish non-retryable error
