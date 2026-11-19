---
id: STORY-010
prd: PRD-021
slug: v1-realtime-delivery
title: /v1 real-time SSE and reasoning_content
type: feature
priority: high
complexity: large
phase: "3 - Ingresses"
status: todo
labels: [backend, api, v1, streaming]
epic_branch: epic/PRD-021-realtime-streaming
plan: null
report: null
commit: null
depends_on: [STORY-004, STORY-009]
blocks: [STORY-014, STORY-015, STORY-016]
skills: []
created: 2026-11-18
updated: 2026-11-18
---

# STORY-010: /v1 real-time SSE and reasoning_content

## Description

As an integrating developer with `stream:realtime`, I want my OpenAI SDK stream to receive content as the model writes it, with tool calls still held and decided, so that I get first-token latency without a progress word ever landing in a file.

## Acceptance Criteria

- [ ] Given a role holding `stream:realtime` (switch on, streaming-capable model) and `stream: true`, when the request is committed, then the router passes a `QueueSink`, commits on `sink.committed`, and `v1_sse.realtime_events(...)` sends Section 6.6's sequence: role chunk at commit, keep-alives while nothing is releasable, content deltas (coalesced to at most one per `STREAM_COALESCE_MS` when no gate holds text, D21), held tool calls and denial notes after the last content, finish chunk last, optional usage chunk, `[DONE]`; every chunk's `id` is the `completion_id`; no chunk carries a `harness` object; `completion_events()` is untouched
- [ ] Given `reasoning:view`, when delivering, then real-time chunks carry `delta.reasoning_content` (both grants), and a non-streamed or buffered response carries `message.reasoning_content` / the role chunk's whole `reasoning_content`; without the grant the key is absent (not `null`), so every such body is byte-identical to today (`ChunkDelta.reasoning_content`, `AssistantMessage.reasoning_content`)
- [ ] Given a scripted `DROP TABLE` tool call in nine argument fragments with content before and after (stub, STORY-004), when streamed in real time, then no fragment substring appears in any chunk before the denial note, the note is a final content delta and `finish_reason` follows `tool_release` (T1); for every scripted stream the concatenated `content` equals the redacted model text plus the notes (T5)
- [ ] Given an upstream fault after commit, when streaming, then exactly one `error` event with today's codes is sent and no `[DONE]` (D16); given a client disconnect mid-stream, then the pipeline runs to completion and the row is written `success=1` (D15); a post-commit verdict keeps `_sse_events`' warning (T13)
- [ ] Given the switch off, or no grant, when the PRD-015 and PRD-017 `/v1` suites run unchanged, then they pass, and the upstream request is non-streamed (D22); an in-process OpenAI SDK stream accumulator test measures first-content latency within the stub's first-chunk delay + 100 ms p95 under `code` with the gate off

## Technical Notes

- `app/routers/v1.py:120-151` `_Upstream` commit signal; `:332-356` commit rule and `StreamingResponse`; `:273-278` post-commit verdict warning. `app/services/v1_sse.py:33` keep-alive, `:46-84`, `:96-108` `wait_for_commit`, `:125-141`. `app/models/v1_schemas.py:26-33` ids, `:210-213` `ChunkDelta`. `app/services/v1_translate.py:135,462-473` `include_usage`.
- **CRITICAL story** (client contract; T1/T5): the orchestrator supplies binding design points.
- The router's sink drops stage and phase events (T5): `/v1` renders keep-alives only.
- `v1_translate.py` is pure (AST purity test): it must not import the `upstream` package `__init__`.
- O5 follows STORY-001's verdict: emit `reasoning` beside `reasoning_content` only if STORY-001 found a target client that needs it.
- Orchestrator decision (STORY-001, O5): emit only `reasoning_content`; Cline (AI SDK) reads `reasoning_content ?? reasoning`, OpenCode's catalog uses `reasoning_content`, the OpenAI SDK displays neither. OpenRouter sends `: OPENROUTER PROCESSING` comments upstream; they are never forwarded.
- Orchestrator decision (STORY-008 impl, e63f658): the sink already receives gated content (remainder last) and gated reasoning; `/v1` must not redact again. A buffered request with the reasoning grant gets the whole redacted reasoning on the private `QuerySuccessResponse.reasoning` property (None without the grant). A gate fault raises `PiiRedactorError` from step 7, after the T6 charge and failure row.

## Dependencies

- **Blocked by**: STORY-004, STORY-009
- **Blocks**: STORY-014, STORY-015, STORY-016

## PRD Reference

Source: [`PRD-021/PRD.md`](../../PRDs/PRD-021-realtime-streaming/PRD.md) — Sections 6.3, 6.6, 10, F8, D5, D9, D10, D15, D16, D17, D21, D22, T1, T5, T13
