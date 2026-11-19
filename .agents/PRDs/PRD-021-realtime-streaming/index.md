# PRD-021-realtime-streaming: Real-Time Streaming and Reasoning Visibility, Decided by the Admin — and Honest Progress Feedback When It Is Off — Story Board

**PRD**: [PRD.md](./PRD.md)
**Epic Branch**: `epic/PRD-021-realtime-streaming` (base: `main`)
**Status**: active

## Progress

15/16 stories done — 94%

## Stories

All stories commit on the epic branch `epic/PRD-021-realtime-streaming`. No per-story branches.

| ID | Title | Type | Status | Complexity | Plan | Commit |
|----|-------|------|--------|------------|------|--------|
| STORY-001 | Survey what providers stream and what clients display | spike | ✅ done | medium | [plan](../../plans/PRD-021-realtime-streaming/completed/STORY-001-streaming-survey.plan.md) | `48bfb48` |
| STORY-002 | Stream permissions and the STREAMING_ENABLED switch | feature | ✅ done | small | [plan](../../plans/PRD-021-realtime-streaming/completed/STORY-002-permissions-and-switch.plan.md) | `876f720` |
| STORY-003 | stream_upstream seam, ReasoningDelta and collect()'s usage override | feature | ✅ done | medium | [plan](../../plans/PRD-021-realtime-streaming/completed/STORY-003-stream-upstream-seam.plan.md) | `a91252a` |
| STORY-004 | Stub upstream streams scripted replies with delays, reasoning and faults | technical | ✅ done | small | [plan](../../plans/PRD-021-realtime-streaming/completed/STORY-004-stub-streaming-scripts.plan.md) | `f2d3b36` |
| STORY-005 | DeliverySink, step 2d visibility and stage events | feature | ✅ done | medium | [plan](../../plans/PRD-021-realtime-streaming/completed/STORY-005-delivery-sink-and-visibility.plan.md) | `139484b` |
| STORY-006 | Streamed step 7 with phases, held tool calls and real-time charging | feature | ✅ done | large | [plan](../../plans/PRD-021-realtime-streaming/completed/STORY-006-streamed-step-7.plan.md) | `0eb1fc1` |
| STORY-007 | Hold-back output gate and reasoning gate | feature | ✅ done | large | [plan](../../plans/PRD-021-realtime-streaming/completed/STORY-007-output-and-reasoning-gates.plan.md) | `d1e6fb0` |
| STORY-008 | Gates in the pipeline, final pass, divergence and reasoning result | feature | ✅ done | medium | [plan](../../plans/PRD-021-realtime-streaming/completed/STORY-008-gates-in-pipeline.plan.md) | `e63f658` |
| STORY-009 | Four audit columns for real-time delivery | feature | ✅ done | medium | [plan](../../plans/PRD-021-realtime-streaming/completed/STORY-009-audit-columns.plan.md) | `e87f3ad` |
| STORY-010 | /v1 real-time SSE and reasoning_content | feature | ✅ done | large | [plan](../../plans/PRD-021-realtime-streaming/completed/STORY-010-v1-realtime-delivery.plan.md) | `03b304d` |
| STORY-011 | Chat UI state consumes the pipeline's events | feature | ✅ done | medium | [plan](../../plans/PRD-021-realtime-streaming/completed/STORY-011-chat-state-consumer.plan.md) | `153c56f` |
| STORY-012 | Progress line, live answer and reasoning block in the chat UI | feature | ✅ done | medium | [plan](../../plans/PRD-021-realtime-streaming/completed/STORY-012-chat-progress-ui.plan.md) | `052afca` |
| STORY-013 | GET /audit real-time fields, completion_id filter and Register LIVE marker | feature | ✅ done | small | [plan](../../plans/PRD-021-realtime-streaming/completed/STORY-013-audit-api-and-register.plan.md) | `5313d70` |
| STORY-014 | OpenCode end-to-end on a real-time stream | technical | ✅ done | medium | [plan](../../plans/PRD-021-realtime-streaming/completed/STORY-014-opencode-realtime-e2e.plan.md) | `5eebd78` |
| STORY-015 | Cline end-to-end on a real-time stream | technical | ✅ done | small | [plan](../../plans/PRD-021-realtime-streaming/completed/STORY-015-cline-realtime-e2e.plan.md) | `499649b` |
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
