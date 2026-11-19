---
id: STORY-006
prd: PRD-021
slug: streamed-step-7
title: Streamed step 7 with phases, held tool calls and real-time charging
type: feature
priority: high
complexity: large
phase: "2 - Pipeline"
status: in-progress
labels: [backend, pipeline, streaming, usage]
epic_branch: epic/PRD-021-realtime-streaming
plan: .agents/plans/PRD-021-realtime-streaming/STORY-006-streamed-step-7.plan.md
report: null
commit: null
depends_on: [STORY-003, STORY-005]
blocks: [STORY-008]
skills: []
created: 2026-11-18
updated: 2026-11-18
---

# STORY-006: Streamed step 7 with phases, held tool calls and real-time charging

## Description

As an integrating developer, I want the pipeline to consume the upstream as a stream when visibility says so, forwarding text to the sink while holding tool calls, so that I get latency without losing the action policy or the token budget.

## Acceptance Criteria

- [ ] Given `visibility.upstream_streamed`, when step 7 runs, then it iterates the injectable `stream_upstream=` (default `upstream.stream_upstream`), keeps every event in order, calls `sink.committed(completion_id)` on the first event (`completion_id = "chatcmpl-harness-rt-<uuid4 hex>"`, D17), and after the iterator ends builds the `UpstreamResult` with PRD-020's `collect()`; otherwise step 7 is today's `call_upstream` path, and `sink.committed` is called on entry when a sink is present
- [ ] Given `app/services/stream_assembly.py` (new, pure), when `phase_of(event, previous)` is called, then first `ReasoningDelta` → `thinking`, first `TextDelta` → `writing`, first named `ToolCallDelta` → `preparing_action` with the mapped `OperationKind` (or None when unmapped), and `None` when the phase does not change; step 7 emits `waiting` on entry and each change via `sink.phase` whenever a sink is present
- [ ] Given `visibility.realtime`, when `TextDelta`s arrive, then `sink.content` receives the text in order (raw for now; STORY-008 inserts the gates); `ReasoningDelta` reaches `sink.reasoning` only when `visibility.reasoning ∧ visibility.realtime`; no `ToolCallDelta` fragment is ever passed to any sink method (T1, D6), and step 7c runs today's code over `collect()`'s calls
- [ ] Given a real-time request whose stream ends without `UsageReport`, when step 7b charges, then `collect(..., usage_missing="estimate")` is used whatever the provider's mode and the charge is the D8 estimate (`usage_estimated`); a buffered or non-realtime streamed request keeps the provider's mode (an `error` provider still raises today's `UpstreamError`)
- [ ] Given a mid-stream `UpstreamError`, when anything had been released to the sink, then the D8 estimate of what was sent and received is charged before the failure row is written (`success=0`); when nothing was released, nothing is charged (today's rule, `query_pipeline.py:786-793`) (T6)

## Technical Notes

- Step 7 `query_pipeline.py:750-784`, 7b `:786-811`, 7c `:813-839`. `call_openrouter=` injection at `:315` is the pattern for `stream_upstream=`.
- **CRITICAL story**: the orchestrator supplies binding design points to the planner.
- The event loop runs on the pipeline thread (synchronous iterator); the sink never blocks it.
- `OperationKind` mapping: `app/services/action_classifiers/__init__.py:31`; phases carry no text (T4).
- Audit columns are STORY-009; this story keeps `completion_id` and the flags on a local/result object for STORY-008/009 to persist. Do not add DB columns here.
- One total deadline: the provider's `timeout_seconds` bounds the whole stream (D20). If `httpx`'s timeout is per-read, enforce the total in `stream_upstream`/the adapter loop and test it with the stub's `delay_ms`.
- Orchestrator decision (STORY-001 findings): `phase_of` must not treat an empty `TextDelta` as `writing` (if STORY-003 has not removed them at the parser); a reasoning model can spend the whole `max_tokens` on reasoning and end with `finish_reason: length` and empty content.

## Dependencies

- **Blocked by**: STORY-003, STORY-005
- **Blocks**: STORY-008

## PRD Reference

Source: [`PRD-021/PRD.md`](../../PRDs/PRD-021-realtime-streaming/PRD.md) — Sections 6.1, 6.2 (Consuming the stream, Usage, Errors), F2, F4, F6, D4, D6, D13, D17, D20, T1, T6
