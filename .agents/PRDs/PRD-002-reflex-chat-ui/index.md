# PRD-002: Harness IA - Embedded Chat UI (Reflex) — Story Board

**PRD**: [PRD.md](./PRD.md)
**Epic Branch**: `epic/PRD-002-reflex-chat-ui` (base: `epic/PRD-001-harness-ia`)
**Status**: active

## Progress

0/9 stories done — 0%

## Stories

All stories commit on the epic branch `epic/PRD-002-reflex-chat-ui`. No per-story branches.

| ID | Title | Type | Status | Complexity | Plan | Commit |
|----|-------|------|--------|------------|------|--------|
| STORY-001 | Extract run_query(...) shared pipeline function | technical | 🟡 in-progress | medium | [plan](../../plans/PRD-002-reflex-chat-ui/STORY-001-shared-query-pipeline-extraction.plan.md) | — |
| STORY-002 | Reflex project scaffolding & dependency setup | technical | ⬜ todo | small | — | — |
| STORY-003 | Mount existing FastAPI app into Reflex (single-port process) | technical | ⬜ todo | medium | — | — |
| STORY-004 | Claude-like chat UI components (static) | feature | ⬜ todo | medium | — | — |
| STORY-005 | Session user_id entry field | feature | ⬜ todo | small | — | — |
| STORY-006 | Wire ChatState.send() to the shared query pipeline | feature | ⬜ todo | medium | — | — |
| STORY-007 | Chat pipeline unit test suite | technical | ⬜ todo | medium | — | — |
| STORY-008 | Multi-stage Docker packaging for single-port image | technical | ⬜ todo | medium | — | — |
| STORY-009 | README chat UI quickstart documentation | technical | ⬜ todo | small | — | — |

## Status Icons
- ⬜ todo
- 🟡 in-progress
- ✅ done
- 🔴 blocked

## Dependencies

- STORY-002 blocked by STORY-001
- STORY-003 blocked by STORY-002
- STORY-004 blocked by STORY-003
- STORY-005 blocked by STORY-004
- STORY-006 blocked by STORY-001, STORY-005
- STORY-007 blocked by STORY-006
- STORY-008 blocked by STORY-007
- STORY-009 blocked by STORY-008
