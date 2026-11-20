---
story: STORY-007
prd: PRD-022
plan: .agents/plans/PRD-022-provider-fallback-and-native-adapters/completed/STORY-007-anthropic-adapter-stream.plan.md
epic_branch: epic/PRD-022-provider-fallback-and-native-adapters
commit: 7347293
status: COMPLETE
completed: 2026-11-20
---

# Implementation Report - STORY-007: AnthropicAdapter.stream()

## Summary

`AnthropicAdapter.stream()` is real: a plain function that builds the request and checks the key at call time, then returns a generator that opens the SDK client and calls `messages.create(**body, stream=True)` on the first `next()`. Raw SSE events map to `TextDelta`, one buffered `ToolCallDelta` per tool block (emitted at `content_block_stop`, canonical JSON), `ReasoningDelta` (only with `reasoning=True`), then `UsageReport` + `Finish` at `message_delta`. The mapping rules of `map_response` and `_sdk_error` were factored into shared pure helpers (`_canonical_arguments`, `_finish_reason`, `_check_answer`, `_usage_counts`, `_timeout_error`, `_transport_error`); `complete()` behaves as before. `build_request` gained `reasoning=None` (None keeps the capability). In-stream SSE `error` events (APIStatusError with status 200) map by `error.type` through the pure `_in_stream_error`.

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| Targeted tests (stream, stream_stub, anthropic_adapter, stub_anthropic_mode, stream_upstream_seam, upstream_stream_collect, upstream_adapter, untouched_app) | 323 passed, 0 failed, 0 skipped |
| Superseded-test guard (`test_pii_redaction_integration.py -k "superseded or deliberately or removed"`) | 1 passed |
| E2E (real SDK + STORY-006 stub: property test; `stream_upstream` through the registry) | passed |
| Full suite | GitHub CI on push (user decision) |

## Files Changed

| File | Action |
|------|--------|
| `app/services/upstream/anthropic.py` | UPDATE (helpers, `reasoning` kw, `stream`, `_map_events`, `_in_stream_error`) |
| `tests/test_anthropic_stream.py` | CREATE (fake SDK: mapping, faults, in-stream errors, lifecycle) |
| `tests/test_anthropic_stream_stub.py` | CREATE (property test over 10 stub scripts, thinking, error parity) |
| `tests/test_anthropic_adapter.py` | UPDATE (placeholder test replaced) |
| `tests/test_stream_upstream_seam.py` | UPDATE (placeholder seam test replaced; `stub.servers` handle) |
| `tests/test_pii_redaction_integration.py` | UPDATE (`_DELIBERATELY_SUPERSEDED_TESTS`) |

## Deviations from Plan

- A second placeholder test, `test_stream_upstream_on_an_anthropic_model_is_incompatible_at_call_time` (STORY-005, `test_stream_upstream_seam.py`), asserted the removed behaviour; it is replaced by a stub-backed streaming test plus a keyless call-time test and registered as superseded alongside the plan's one.
- `message_stop` is not required: the stream is complete once `message_delta` was seen; a stream with no `message_delta` is `shape`.
- The stub cannot script an in-stream `event: error` (and was not extended), so `_in_stream_error` is covered with fake-SDK tests only.

## Known limitations

- `reasoning_blocks` is not carried through `collect()` (no event carries a count; PRD 6.6 ignores `ReasoningDelta`); the property test neutralizes it and `dropped_params`. `complete()` still counts it; no consumer outside the adapter.
- The total stream deadline is left to STORY-014; `timeout_seconds` is only the SDK per-read timeout.
- Malformed-fault stream is pinned to a closed set `{shape, transport}` (observed: `shape`).

## Acceptance Criteria

- [x] AC1 mapping, buffered canonical tool input, Finish + cache usage: `test_anthropic_stream.py` text / tool / parallel / usage cases
- [x] AC2 thinking on/off, no redacted/signature: thinking cases in `test_anthropic_stream.py`; `test_thinking_is_counted_by_complete_and_streamed_as_reasoning_only_when_asked`
- [x] AC3 `collect(stream) == complete` over stub scripts: `test_collect_of_the_stream_equals_complete` (10 scripts)
- [x] AC4 no stop / bad tool input / mid-stream SDK and in-stream errors: `test_no_stop_is_shape...`, tool-input and `_in_stream_error` cases, stub `fail_after`/faults
- [x] AC5 seam eager route/key errors, lazy network: `test_stream_upstream_on_an_anthropic_model_streams_through_the_adapter`, `..._refuses_a_keyless_route_at_call_time`, `test_stream_is_lazy_on_the_server`
