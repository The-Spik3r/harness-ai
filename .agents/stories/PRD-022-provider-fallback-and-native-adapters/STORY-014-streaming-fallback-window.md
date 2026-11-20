---
id: STORY-014
prd: PRD-022
slug: streaming-fallback-window
title: Real-time streamed requests through the chain — fall back before release, never after
type: feature
priority: high
complexity: large
phase: "4 - Observability, streaming, docs"
status: todo
labels: [backend, pipeline, streaming]
epic_branch: epic/PRD-022-provider-fallback-and-native-adapters
plan: null
report: null
commit: null
depends_on: [STORY-012, STORY-013]
blocks: [STORY-017]
skills: []
created: 2026-11-20
updated: 2026-11-20
---

# STORY-014: Streaming fallback window

## Description

As a coding agent on a real-time `/v1` stream, I want a provider failure before any answer content reaches me to be retried on the next candidate inside the same SSE response, and a failure after it to end the stream with an error, so that failover never splices two providers' answers together.

## Acceptance Criteria

- [ ] Given a realtime request whose primary's stream fails (open error, or a mid-stream fault) before any `content()`/`reasoning()` sink call or released tool call, when the chain falls back, then the next candidate's events continue the **same** committed SSE response (one `committed`, one role chunk), its row is the success row, and the failed attempt has its own `success=0` row
- [ ] Given a fault after the first release, when it happens, then no further attempt is made, the client gets the stream's `error` event, and the attempt row records `success=0` with the usage that arrived (charged per PRD-021 T6)
- [ ] Given a candidate without `streaming` capability, when the request is realtime, then it is skipped as `capability`
- [ ] Given per-attempt state (received text/calls, gates, phases), when an attempt fails before release, then nothing from it leaks into the next attempt's result, gate or row (fresh state per attempt); progress phases may repeat `waiting`
- [ ] Given no chains file, when a realtime request runs, then `stream_upstream` is called once and every PRD-021 streaming test passes unmodified

## Technical Notes

- Orchestrator decision (STORY-008): the success row's `ignored_params` is `_merge_ignored_params(edge, result.dropped_params, route)` in `query_pipeline.py`; the realtime branch gets `dropped_params` from `upstream.dropped_params_for(route, request)`. With a chain, pass the *answering attempt's* route and request to both, never the primary's.

- Orchestrator decision (STORY-007): the Anthropic stream raises in-stream SSE `error` events as `UpstreamError` mapped by `error.type` (`overloaded_error` 529 / `api_error` 500 / `rate_limit_error` 429 retryable; auth/permission `misconfigured`; else 502 final), so a pre-release in-stream overload falls back like an HTTP 529. An empty refusal yields one `TextDelta("")` right before `UsageReport`/`Finish(content_filter)`: an empty `TextDelta` must not count as released content when closing the window. `message_stop` is not required once `message_delta` arrived. The adapter has no total stream deadline (only the SDK per-read timeout): the per-attempt timeout here is the only one for anthropic routes.

- `app/services/query_pipeline.py:1011-1150` streamed branch: `released` (`:1023`) is already the D9 signal; `committed` fires on the first event (`:1066-1068`) — PRD 6.6 says commit does not close the window.
- Release-of-tool-calls: PRD-021's `tool_release.py` decides when a tool call is released; treat that as closing the window too.
- Call `stream_upstream` per candidate through the existing injectable parameter (`run_conversation(..., stream_upstream=...)`, `:451`).
- Orchestrator decision (STORY-012): today `chained = len(req_chain.candidates) > 1 and not streamed_step` in `run_conversation`; the streamed branch stays single-candidate with a comment pointing here. The buffered chain's closures (`prepare` -> `_prepare_input`, `attempt`, `on_attempt_failed` -> `_log_failed_attempt`, the exhaustion/limit handling) are the pattern to reuse; `released` must become live. The routing census (`tests/test_query_pipeline_routing.py`) requires exactly 11 `log_query(` sites (the text counts, comments included) and `test_query_pipeline_pii_relaxation.py` pins `relaxed = route.relaxes_input()` text: reuse the row helpers, add no new site. A loaded chain always passes `timeout=` (the provider's timeout when no deadline is set).
- Orchestrator decision (STORY-013): the answer's provenance rides on `QuerySuccessResponse.answered_by` (private `AnsweredBy(provider, model, attempts)`, set at the pipeline's single success build); `translate_result` copies it into `harness.provider/attempts`. `X-Harness-Provider` and the `harness` fields are JSON-only: SSE headers go out at commit, so a stream (buffered or real-time) carries only the answering `model` in its chunks. `ChainExhausted` maps via `v1_translate.translate_exhausted(skipped, last_error, retry_after_seconds)` in `v1._outcome` (no attempt + only capability/forbidden/byok skips -> non-retryable `upstream_error`, O5); the real-time tail goes through `_outcome` too.

## Dependencies

- **Blocked by**: STORY-012, STORY-013
- **Blocks**: STORY-017

## PRD Reference

Source: [`PRD-022/PRD.md`](../../PRDs/PRD-022-provider-fallback-and-native-adapters/PRD.md) — Sections 6.6 (fallback window), D9, Section 11 streaming requirement
