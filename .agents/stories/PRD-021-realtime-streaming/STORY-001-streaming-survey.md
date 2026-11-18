---
id: STORY-001
prd: PRD-021
slug: streaming-survey
title: Survey what providers stream and what clients display
type: spike
priority: high
complexity: medium
phase: "1 - Survey and seams"
status: done
labels: [spike, streaming, research]
epic_branch: epic/PRD-021-realtime-streaming
plan: .agents/plans/PRD-021-realtime-streaming/completed/STORY-001-streaming-survey.plan.md
report: .agents/reports/PRD-021-realtime-streaming/STORY-001-streaming-survey.report.md
commit: 48bfb48
depends_on: []
blocks: [STORY-003, STORY-014, STORY-015]
skills: []
created: 2026-11-18
updated: 2026-11-18
---

# STORY-001: Survey what providers stream and what clients display

## Description

As the implementer of PRD-021, I want recorded evidence of the streamed reasoning field and usage chunk each provider actually sends, and of which clients display `reasoning_content`, so that the adapter mapping (STORY-003) and the `/v1` field (D9, O5) are built on facts rather than assumptions.

## Acceptance Criteria

- [ ] Given the `OPENROUTER_API_KEY` in `.env`, when the survey script sends small streamed requests (`stream: true`, `stream_options.include_usage: true`) to OpenRouter for at least one reasoning model and one non-reasoning model, then the report records, per model, the reasoning delta field name (`delta.reasoning`, `delta.reasoning_content`, other, or none), whether reasoning arrives without an explicit reasoning request parameter, and whether a final usage chunk arrives
- [ ] Given the local OpenAI-compatible server at `http://localhost:1235/v1` (model `google/gemma-4-e4b`, the PRD-020 STORY-014 setup) is reachable, when the same probe runs against it, then the same facts are recorded; if it is not reachable, the report says so and the run does not fail
- [ ] Given the recorded responses, when they are saved as sanitized fixtures under `tests/fixtures/prd021_survey/` (no key, no auth header, content truncated to what the shape needs), then STORY-003 can replay them in a unit test without network
- [ ] Given OpenCode (installed globally), Cline and the OpenAI Python SDK, when the report is written, then it states for each, with the version and the source (code read, docs, or observed), whether it displays `reasoning_content`, `reasoning`, both or neither, and gives a verdict on O5 (emit `reasoning` beside `reasoning_content` only if a target client reads `reasoning` and not `reasoning_content`)
- [ ] Given the survey script, when it runs without `OPENROUTER_API_KEY` or network, then it exits cleanly with a message; it is a script under `scripts/`, not a test collected by the default suite

## Technical Notes

- User decision (orchestrator, 2026-11-18): live OpenRouter calls with the `.env` key are allowed (a few cents); keep the number of requests small (≤ 6) and `max_tokens` low.
- The key must never be printed, logged, or written to a fixture or report (PRD-020 T1/T6 discipline).
- The report goes to `.agents/reports/PRD-021-realtime-streaming/STORY-001-streaming-survey.report.md` and is the deliverable; the fixtures are the second deliverable.
- PRD "Not verified (recorded for STORY-001)" lists the exact questions. Reflex flush behaviour is NOT this story's (STORY-011 verifies it).
- PRD-020's SSE parser is `app/services/upstream/sse.py`; reuse it to parse, so the report says what the parser currently drops.

## Dependencies

- **Blocked by**: None
- **Blocks**: STORY-003, STORY-014, STORY-015

## PRD Reference

Source: [`PRD-021/PRD.md`](../../PRDs/PRD-021-realtime-streaming/PRD.md) — Sections 6.2, 8, 12 Phase 1, 15 "Not verified", O5
