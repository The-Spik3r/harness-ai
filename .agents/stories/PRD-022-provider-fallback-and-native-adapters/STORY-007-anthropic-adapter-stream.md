---
id: STORY-007
prd: PRD-022
slug: anthropic-adapter-stream
title: AnthropicAdapter.stream() — events, buffered tool input, ReasoningDelta, collect property
type: feature
priority: high
complexity: medium
phase: "2 - Anthropic native adapter"
status: todo
labels: [backend, upstream, anthropic, streaming]
epic_branch: epic/PRD-022-provider-fallback-and-native-adapters
plan: null
report: null
commit: null
depends_on: [STORY-005, STORY-006]
blocks: [STORY-008]
skills: []
created: 2026-11-20
updated: 2026-11-20
---

# STORY-007: AnthropicAdapter.stream()

## Description

As PRD-021's real-time pipeline, I want an Anthropic model to stream as PRD-020's normalized events, with summarized thinking as `ReasoningDelta`, so that `reasoning:view` and real-time delivery work for Anthropic models exactly as for OpenAI-compatible ones.

## Acceptance Criteria

- [ ] Given a Messages SSE stream, when `stream(request, key, *, reasoning=...)` iterates it, then `text_delta` → `TextDelta`; a `tool_use` block's `input_json_delta` fragments are buffered until `content_block_stop`, parsed, canonically serialized (same function as `complete()`), and emitted as **one** `ToolCallDelta(index, id, name, arguments=<whole string>)`; `message_delta` → `Finish` (mapped reason) and `UsageReport` with cache fields
- [ ] Given `reasoning=True` (the route's capability), when thinking deltas arrive, then each non-empty `thinking_delta` becomes `ReasoningDelta(text)` and the request asks for summarized thinking per STORY-001; with `reasoning=False` thinking is neither requested nor emitted; `redacted_thinking` and `signature_delta` are never emitted
- [ ] Given every stub script from STORY-006 (text, tools, parallel tools, thinking, refusal, cache usage), when replayed, then `collect(stream(r)) == complete(r)` (property test, no network beyond the local stub)
- [ ] Given a stream that ends without `message_stop`/`Finish`, an unparseable buffered tool input, or an SDK error mid-stream, when iterated, then a `UpstreamError` with the right `kind` (`shape` / `transport` / mapped status) is raised; nothing is invented
- [ ] Given `stream_upstream` on an anthropic route, when called, then route/key errors raise at call time and the network is touched on the first `next()` (PRD-021 seam contract)

## Technical Notes

- `app/services/upstream/anthropic.py` (STORY-005); `collect.py`; PRD-021's `ReasoningDelta` in `types.py:109`; the OpenAI-compatible `stream()` for structure (`openai_compatible.py`, `sse.py`).
- `ProviderAdapter.stream` signature as built: `stream(self, request, api_key, *, reasoning: bool = False)` (`types.py:118-125`).
- Release semantics (D9) are the pipeline's job (STORY-014); the adapter just yields events in arrival order.

## Dependencies

- **Blocked by**: STORY-005, STORY-006
- **Blocks**: STORY-008

## PRD Reference

Source: [`PRD-022/PRD.md`](../../PRDs/PRD-022-provider-fallback-and-native-adapters/PRD.md) — Sections 6.6, F2, D4, D14
