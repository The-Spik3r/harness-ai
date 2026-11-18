---
id: STORY-003
prd: PRD-021
slug: stream-upstream-seam
title: stream_upstream seam, ReasoningDelta and collect()'s usage override
type: feature
priority: high
complexity: medium
phase: "1 - Survey and seams"
status: todo
labels: [backend, streaming, upstream]
epic_branch: epic/PRD-021-realtime-streaming
plan: null
report: null
commit: null
depends_on: [STORY-001]
blocks: [STORY-006]
skills: []
created: 2026-11-18
updated: 2026-11-18
---

# STORY-003: stream_upstream seam, ReasoningDelta and collect()'s usage override

## Description

As the pipeline author, I want a `stream_upstream` function beside `call_upstream`, a `ReasoningDelta` event mapped from the provider's reasoning field, and a way to make `collect()` charge the estimate whatever the provider's `usage_missing` mode, so that step 7 can consume a stream with the same rules as `complete()`.

## Acceptance Criteria

- [ ] Given `app/services/upstream/types.py`, when imported, then `ReasoningDelta(text)` is a frozen dataclass in the `UpstreamEvent` union and is exported from the package
- [ ] Given a model whose `reasoning` capability is true, when the OpenAI-compatible adapter's `stream()` receives a chunk with the reasoning field(s) STORY-001 recorded, then it yields `ReasoningDelta`; for a model whose `reasoning` capability is false, the field is dropped (never mapped to text); a STORY-001 fixture replays this without network
- [ ] Given any event sequence, when `collect()` runs, then it ignores `ReasoningDelta` (reasoning never reaches `UpstreamResult.response`), and `collect(stream(r)) == complete(r)` still holds for the existing property tests
- [ ] Given `collect(..., usage_missing="estimate")` (keyword override) on a provider whose own mode is `error`, when the events have no `UsageReport`, then the result carries PRD-020's D8 estimate and `usage_estimated` is true; without the override, today's behaviour (raise for `error`) is unchanged
- [ ] Given `stream_upstream(messages, model, api_key=None, params=None, client=None, *, tools=None)`, when called, then it resolves the route and key exactly as `call_upstream` does (shared helper, no duplicated logic), returns the adapter's event iterator, and raises `UpstreamError` for no route or empty messages; a stream ending without `Finish` raises a non-retryable `UpstreamError` (F2)

## Technical Notes

- `app/services/upstream/__init__.py:56` `call_upstream`; factor the route/key resolution into one private helper both functions call.
- `app/services/upstream/collect.py:32` `collect(events, *, provider, request)`; `reply.py:68` `_resolve_usage` reads `provider.usage_missing` — the override must reach it without mutating the frozen `Provider` (e.g. pass the mode down, or `dataclasses.replace`).
- `app/services/upstream/sse.py` `_chunk_events` is where the reasoning field gets mapped; the adapter knows the model's capabilities via the route.
- The PRD's open choice "which field": accept every field STORY-001 observed; if STORY-001 is inconclusive, accept both `delta.reasoning` and `delta.reasoning_content` (Risk 3: an unknown field is dropped, never forwarded).
- Pure modules stay pure: `collect.py` imports no HTTP client and no settings; `v1_translate.py` must not import the package `__init__`.
- Legacy mode (no `PROVIDERS_FILE`) keeps `streaming=False`, `reasoning=False` for every model (user decision, see PRD D4 amendment); do not change `provider_registry`'s legacy capabilities.

## Dependencies

- **Blocked by**: STORY-001
- **Blocks**: STORY-006

## PRD Reference

Source: [`PRD-021/PRD.md`](../../PRDs/PRD-021-realtime-streaming/PRD.md) — Sections 6.2, F2, D4, D20
