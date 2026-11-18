---
id: STORY-004
prd: PRD-021
slug: stub-streaming-scripts
title: Stub upstream streams scripted replies with delays, reasoning and faults
type: technical
priority: medium
complexity: small
phase: "1 - Survey and seams"
status: todo
labels: [testing, stub, streaming]
epic_branch: epic/PRD-021-realtime-streaming
plan: null
report: null
commit: null
depends_on: []
blocks: [STORY-010, STORY-014, STORY-015]
skills: []
created: 2026-11-18
updated: 2026-11-18
---

# STORY-004: Stub upstream streams scripted replies with delays, reasoning and faults

## Description

As a test author, I want the stub upstream to stream a reply in a scripted shape (chunk size, delays, reasoning, a mid-stream failure), so that latency, reasoning and fault behaviour can be tested end to end without a real provider.

## Acceptance Criteria

- [ ] Given a reply with `stream: {chunk_chars: N}`, when a request with `stream: true` arrives, then the content is sent in deltas of at most N characters, ending with `finish_reason`, a usage chunk (when `include_usage`) and `[DONE]`
- [ ] Given `stream: {delay_ms: D}`, when streaming, then each delta is sent at least D ms after the previous one (first-chunk delay included), measurable by a test client
- [ ] Given `stream: {reasoning: "…"}`, when streaming, then reasoning deltas (in the field STORY-001 recorded for OpenRouter; `delta.reasoning` if inconclusive) precede the content deltas
- [ ] Given `stream: {fail_after: K}`, when streaming, then the stub sends K deltas and then drops the connection without `finish_reason` or `[DONE]`
- [ ] Given any of the above, when the stub logs the request, then the log line never contains content or reasoning text; a reply without `stream:`, or a request without `stream: true`, is answered exactly as today (existing stub tests unchanged)

## Technical Notes

- `scripts/stub_openrouter.py:65-69` documents PRD-020 STORY-013's SSE mode; `_send_sse` at `:473`; request handling `:572-607`. Extend, do not fork.
- Tool-call fragments: keep PRD-020's two-fragment arguments; allow `chunk_chars` to split arguments too, so STORY-010 can script a `DROP TABLE` call in nine fragments (T1).
- Free ports at runtime; works on Windows and Linux.

## Dependencies

- **Blocked by**: None
- **Blocks**: STORY-010, STORY-014, STORY-015

## PRD Reference

Source: [`PRD-021/PRD.md`](../../PRDs/PRD-021-realtime-streaming/PRD.md) — Sections 4 (Stub upstream), F10
