# PRD-021-realtime-streaming: Real-Time Streaming and Reasoning Visibility, Decided by the Admin — and Honest Progress Feedback When It Is Off — Story Board

**PRD**: [PRD.md](./PRD.md)
**Epic Branch**: `epic/PRD-021-realtime-streaming` (base: `main`)
**Status**: active

## Progress

2/16 stories done — 12%

## Stories

All stories commit on the epic branch `epic/PRD-021-realtime-streaming`. No per-story branches.

| ID | Title | Type | Status | Complexity | Plan | Commit |
|----|-------|------|--------|------------|------|--------|
| STORY-001 | Survey what providers stream and what clients display | spike | ✅ done | medium | [plan](../../plans/PRD-021-realtime-streaming/completed/STORY-001-streaming-survey.plan.md) | `48bfb48` |
| STORY-002 | Stream permissions and the STREAMING_ENABLED switch | feature | ✅ done | small | [plan](../../plans/PRD-021-realtime-streaming/completed/STORY-002-permissions-and-switch.plan.md) | `876f720` |
| STORY-003 | stream_upstream seam, ReasoningDelta and collect()'s usage override | feature | ⬜ todo | medium | — | — |
| STORY-004 | Stub upstream streams scripted replies with delays, reasoning and faults | technical | ⬜ todo | small | — | — |
| STORY-005 | DeliverySink, step 2d visibility and stage events | feature | ⬜ todo | medium | — | — |
| STORY-006 | Streamed step 7 with phases, held tool calls and real-time charging | feature | ⬜ todo | large | — | — |
| STORY-007 | Hold-back output gate and reasoning gate | feature | ⬜ todo | large | — | — |
| STORY-008 | Gates in the pipeline, final pass, divergence and reasoning result | feature | ⬜ todo | medium | — | — |
| STORY-009 | Four audit columns for real-time delivery | feature | ⬜ todo | medium | — | — |
| STORY-010 | /v1 real-time SSE and reasoning_content | feature | ⬜ todo | large | — | — |
| STORY-011 | Chat UI state consumes the pipeline's events | feature | ⬜ todo | medium | — | — |
| STORY-012 | Progress line, live answer and reasoning block in the chat UI | feature | ⬜ todo | medium | — | — |
| STORY-013 | GET /audit real-time fields, completion_id filter and Register LIVE marker | feature | ⬜ todo | small | — | — |
| STORY-014 | OpenCode end-to-end on a real-time stream | technical | ⬜ todo | medium | — | — |
| STORY-015 | Cline end-to-end on a real-time stream | technical | ⬜ todo | small | — | — |
| STORY-016 | Document real-time streaming, grants and progress feedback | enhancement | ⬜ todo | small | — | — |

## Status Icons
- ⬜ todo
- 🟡 in-progress
- ✅ done
- 🔴 blocked

## Dependencies

- STORY-003 blocked by STORY-001
- STORY-005 blocked by STORY-002
- STORY-006 blocked by STORY-003, STORY-005
- STORY-008 blocked by STORY-006, STORY-007
- STORY-009 blocked by STORY-008
- STORY-010 blocked by STORY-004, STORY-009
- STORY-011 blocked by STORY-009
- STORY-012 blocked by STORY-011
- STORY-013 blocked by STORY-009
- STORY-014 blocked by STORY-001, STORY-004, STORY-010
- STORY-015 blocked by STORY-001, STORY-004, STORY-010
- STORY-016 blocked by STORY-010, STORY-012, STORY-013, STORY-014, STORY-015
