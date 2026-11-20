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

- `app/services/query_pipeline.py:1011-1150` streamed branch: `released` (`:1023`) is already the D9 signal; `committed` fires on the first event (`:1066-1068`) — PRD 6.6 says commit does not close the window.
- Release-of-tool-calls: PRD-021's `tool_release.py` decides when a tool call is released; treat that as closing the window too.
- Call `stream_upstream` per candidate through the existing injectable parameter (`run_conversation(..., stream_upstream=...)`, `:451`).

## Dependencies

- **Blocked by**: STORY-012, STORY-013
- **Blocks**: STORY-017

## PRD Reference

Source: [`PRD-022/PRD.md`](../../PRDs/PRD-022-provider-fallback-and-native-adapters/PRD.md) — Sections 6.6 (fallback window), D9, Section 11 streaming requirement
