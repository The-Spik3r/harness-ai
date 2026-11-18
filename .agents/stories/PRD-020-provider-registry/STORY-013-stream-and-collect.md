---
id: STORY-013
prd: PRD-020
slug: stream-and-collect
title: Adapter stream() with normalized events and pure collect()
type: feature
priority: medium
complexity: large
phase: "4 - Streaming interface, E2E, docs"
status: in-progress
labels: [backend, streaming]
epic_branch: epic/PRD-020-provider-registry
plan: .agents/plans/PRD-020-provider-registry/STORY-013-stream-and-collect.plan.md
report: null
commit: null
depends_on: [STORY-005, STORY-009]
blocks: [STORY-014]
skills: []
created: 2026-11-18
updated: 2026-11-18
---

# STORY-013: Adapter stream() with normalized events and pure collect()

## Description

As the author of PRD-021, I want the adapter to expose a tested `stream()` of normalized events and a pure `collect()` that reproduces `complete()`, so that real-time streaming can be built without rewriting the adapter.

## Acceptance Criteria

- [x] Given an `UpstreamRequest`, when `stream()` runs, then it sends `stream: true` and `stream_options: {include_usage: true}` and yields normalized events (`TextDelta`, `ToolCallDelta(index, id?, name?, arguments_fragment)`, `UsageReport`, `Finish`); `complete()` still sends no `stream` key.
- [x] Given the stub's SSE mode (F6: content in two deltas, each call's arguments in two fragments, a usage chunk when `include_usage` is set, then `[DONE]`), when a request with `"stream": true` is made, then the stub answers SSE and logs `stream=yes`; a request without it logs `stream=no` and is answered as today.
- [x] Given `collect(events)`, when applied, then it is pure and applies `complete()`'s exact rules: `content: null` with calls -> `""`, arguments as given and never parsed, duplicate call ids refused, and the D8 usage rule including `usage_estimated`.
- [x] Given every stub script in `tests/e2e/scripts/` and the suite's tool scripts, when run through both paths, then `collect(stream(r)) == complete(r)` as a property test for each reply rule.
- [x] Given a malformed stream (a non-JSON data line, a missing `[DONE]`, an arguments fragment for an unseen index), when parsed, then a non-retryable `UpstreamError` names the field, never a value.

## Technical Notes

- Adds to the STORY-005 package: `OpenAICompatibleAdapter.stream` and `upstream.collect` (section 6.4). Synchronous iterators (the pipeline runs on the dedicated executor, `app/services/pipeline_executor.py`); no production code calls `stream()` in this PRD, `call_upstream` still calls `complete()` only.
- `collect()` must reuse the parsing helpers that `complete()` uses (`_parse_tool_calls` at `app/services/openrouter_client.py:147-185` today, its D13 never-parse rule, and the content/usage rules at `:289-319`) rather than re-implementing them; move the shared logic, do not fork it.
- Orchestrator decision (STORY-009 verify): the D8 usage table now lives in `_resolve_usage(provider, label, data, content, calls, request)` in `app/services/upstream/openai_compatible.py`, and the estimator is the pure `usage_estimate.estimate_tokens(sent_messages, (content, tool_calls), chars_per_token, *, tools=None)`. `collect()` must go through `_resolve_usage` (a stream without a final usage chunk is "absent"), not a second copy of the table. `UpstreamResult.usage_estimated` defaults False.
- Stub SSE: add a `stream` branch to `_StubHandler.do_POST` (`scripts/stub_openrouter.py:438-`; today the stub never streams, header note `:63-64`), the log line `:465-469` gains `stream=yes|no` (presence only). Existing scripts: `tests/e2e/scripts/*.json` (aider, cline, continue, docker_smoke, example, openai_sdk, opencode, tool_loop).
- Property test location: `tests/test_upstream_stream_collect.py`, parametrized over the script files and the suite's inline tool scripts; compare `UpstreamResult` equality (response, tokens, split, finish_reason, tool_calls, usage_estimated).

## Dependencies

- **Blocked by**: STORY-005, STORY-009
- **Blocks**: STORY-014

## PRD Reference

Source: [`PRD-020/PRD.md`](../../PRDs/PRD-020-provider-registry/PRD.md) — Sections 4 (Adapter), 6.4, 7 F6, 9.2 T7; decisions D11
