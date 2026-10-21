---
id: STORY-013
prd: PRD-015
slug: buffered-sse
title: "Buffered SSE: commit on upstream start, keep-alive, chunk sequence, include_usage, post-commit error"
type: feature
priority: high
complexity: large
phase: "3 - Buffered SSE"
status: todo
labels: [backend, api, streaming]
epic_branch: epic/PRD-015-openai-compatible-endpoint
plan: null
report: null
commit: null
depends_on: [STORY-003, STORY-004, STORY-010, STORY-011]
blocks: [STORY-015, STORY-016, STORY-017, STORY-018]
skills: []
created: 2026-10-21
updated: 2026-10-21
---

# STORY-013: Buffered SSE: commit on upstream start, keep-alive, chunk sequence, include_usage, post-commit error

## Description

As an integrating developer whose client streams by default, I want `stream: true` to work, with the connection kept alive while the harness checks the full answer and with blocks still arriving as real 400/403 errors, so that I can use my client unchanged without the harness ever releasing unchecked output.

## Acceptance Criteria

- [ ] Given `stream: true` and a request the pipeline blocks or faults before the upstream call (every verdict in STORY-010, plus `DuplicateCheckError` / `UsageLimitError`), when it is sent, then the response is the same JSON error with the same status as without `stream`, not `text/event-stream`; the row has `streamed=1`.
- [ ] Given `stream: true` and an answered request, when it is read, then it is `200 text/event-stream` with `Cache-Control: no-cache` and `X-Accel-Buffering: no`, and its events are exactly: one chunk with `delta: {role: "assistant", content: <whole response>}`, one chunk with `delta: {}` and the `finish_reason`, a usage chunk with `choices: []` only when `stream_options.include_usage` is true, then `data: [DONE]`; every chunk's `id` is `chatcmpl-harness-{audit_id}`.
- [ ] Given an upstream stub that delays 3.5 s and `V1_SSE_KEEPALIVE_SECONDS=1`, when the stream is read, then at least three `: keep-alive` comment lines arrive before the first `data:` line, and none after it.
- [ ] Given an upstream failure or output-redaction failure after the upstream call started, when the stream is read, then it ends with one `data: {"error": {...}}` event (the STORY-011 object) and no `[DONE]`; the audit rows match the non-streaming case.
- [ ] Given a client that disconnects while the upstream call runs, when the pipeline finishes, then the success row is written and the tokens charged, and the event loop logs no unhandled exception; and given 20 concurrent streamed requests against a slow stub, `/health` answers within 200 ms throughout.

## Technical Notes

- New `app/services/v1_sse.py`. The commit rule is PRD Section 6.4: the router passes `run_conversation` a `call_openrouter` wrapper that sets a `threading.Event` (bridged to the loop with `loop.call_soon_threadsafe`) and records the `OpenRouterResult` (STORY-009's capture), then delegates. The wrapper forwards `params=` only when given (PRD-010 STORY-005: stubs have signature `(messages, model, api_key)`).
- `asyncio.wait({pipeline_future, upstream_started}, return_when=FIRST_COMPLETED)`. Pipeline first → the non-streaming response path. Event first → return `StreamingResponse` whose generator sends keep-alives every `settings.V1_SSE_KEEPALIVE_SECONDS` until the future resolves, then the chunks or the error event.
- `streamed=True` is passed to `run_conversation` from the request flag in both cases (PRD-013 Section 6.9). Note `_deny`'s comment: "a defaulted False would quietly mislabel a PRD-014 SSE refusal". That case is now real; assert it.
- No byte of content is written before the future resolves (PRD T8). The pipeline is not cancelled on disconnect: it runs on its executor thread to completion (PRD Section 7.6).
- `X-Harness-Audit-Id` is not sent on streamed responses (unknown at commit time).
- Concurrency assertion follows `tests/test_pipeline_concurrency.py` (PRD-010 STORY-014).
- Tests: `tests/test_v1_sse.py` with `httpx.AsyncClient` over ASGI and a slow/failing injected upstream; keep timing tolerances generous for Windows.
- Skills: none applicable.

## Dependencies

- **Blocked by**: STORY-003, STORY-004, STORY-010, STORY-011
- **Blocks**: STORY-015, STORY-016, STORY-017, STORY-018

## PRD Reference

Source: [`PRD-015-openai-compatible-endpoint/PRD.md`](../../PRDs/PRD-015-openai-compatible-endpoint/PRD.md) — sections 6.4, 7.6, 9.2 (T8), 11, 14 (Risks 1, 5, 6), 15 (D6, D8)
