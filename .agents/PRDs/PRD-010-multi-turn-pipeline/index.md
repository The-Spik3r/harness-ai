# PRD-010-multi-turn-pipeline: Multi-turn Pipeline — Conversations In, Off the Shared Threadpool — Story Board

**PRD**: [PRD.md](./PRD.md)
**Epic Branch**: `epic/PRD-010-multi-turn-pipeline` (base: `main`)
**Status**: active

## Progress

13/18 stories done — 72%

## Stories

All stories commit on the epic branch `epic/PRD-010-multi-turn-pipeline`. No per-story branches.

| ID | Title | Type | Status | Complexity | Plan | Commit |
|----|-------|------|--------|------------|------|--------|
| STORY-001 | Message model, Role type and OpenAI content normalization | feature | ✅ done | medium | [plan](../../plans/PRD-010-multi-turn-pipeline/completed/STORY-001-message-model-and-normalization.plan.md) | `a41155f` |
| STORY-002 | Settings: upstream timeout, context limits and pipeline executor size | technical | ✅ done | small | [plan](../../plans/PRD-010-multi-turn-pipeline/completed/STORY-002-timeout-context-and-executor-settings.plan.md) | `6c7048e` |
| STORY-003 | Characterize today's OpenRouter request payload and /query upstream body | technical | ✅ done | small | [plan](../../plans/PRD-010-multi-turn-pipeline/completed/STORY-003-openrouter-payload-characterization.plan.md) | `1459475` |
| STORY-004 | call_openrouter takes a list of Messages; the pipeline passes one user message | enhancement | ✅ done | medium | [plan](../../plans/PRD-010-multi-turn-pipeline/completed/STORY-004-openrouter-client-sends-messages.plan.md) | `65451c1` |
| STORY-005 | GenerationParams allowlist, configurable timeout and explicit null-content error | feature | ✅ done | medium | [plan](../../plans/PRD-010-multi-turn-pipeline/completed/STORY-005-generation-params-timeout-and-null-content.plan.md) | `4914674` |
| STORY-006 | Dedicated pipeline executor; /query async with its body off the event loop; ChatState uses it | technical | ✅ done | medium | [plan](../../plans/PRD-010-multi-turn-pipeline/completed/STORY-006-dedicated-pipeline-executor.plan.md) | `d265843` |
| STORY-007 | run_conversation over messages; run_query becomes a one-message adapter | feature | ✅ done | large | [plan](../../plans/PRD-010-multi-turn-pipeline/completed/STORY-007-run-conversation-and-query-adapter.plan.md) | `0096e2e` |
| STORY-008 | Context-limit refusal: response model, audited pipeline arm, /query passthrough | feature | ✅ done | medium | [plan](../../plans/PRD-010-multi-turn-pipeline/completed/STORY-008-context-limit-refusal.plan.md) | `e4de634` |
| STORY-009 | Multi-turn pipeline invariants: check order, raw hashing, redaction, duplicate scope, no ingress | technical | ✅ done | medium | [plan](../../plans/PRD-010-multi-turn-pipeline/completed/STORY-009-multi-turn-pipeline-invariant-tests.plan.md) | `90f07f1` |
| STORY-010 | chat_messages.history_trimmed column, converged by init_db() | technical | ✅ done | small | [plan](../../plans/PRD-010-multi-turn-pipeline/completed/STORY-010-chat-messages-history-trimmed-column.plan.md) | `113633c` |
| STORY-011 | chat_history.assemble (answered exchanges only) and fit (drop oldest whole exchanges) | feature | ✅ done | medium | [plan](../../plans/PRD-010-multi-turn-pipeline/completed/STORY-011-chat-history-assemble-and-fit.plan.md) | `a3eccae` |
| STORY-012 | ChatState sends session history through run_conversation; flag-off path unchanged | feature | ✅ done | large | [plan](../../plans/PRD-010-multi-turn-pipeline/completed/STORY-012-chat-state-sends-history.plan.md) | `e5bf0e0` |
| STORY-013 | Chat UI: context_limit bubble and 'earlier exchanges not sent' footer note | feature | ✅ done | medium | [plan](../../plans/PRD-010-multi-turn-pipeline/completed/STORY-013-context-limit-bubble-and-trimmed-note.plan.md) | `36b6088` |
| STORY-014 | Concurrency: blocked upstream calls do not stall /health, /query or the chat | technical | ⬜ todo | medium | — | — |
| STORY-015 | Measure added per-send latency of history assembly and per-turn redaction at 20 exchanges | spike | ⬜ todo | small | — | — |
| STORY-016 | Seven-outcome /query regression and chat UI regression on the finished epic | technical | ⬜ todo | medium | — | — |
| STORY-017 | Two-instance smoke: a multi-turn chat continued across instances | technical | ⬜ todo | medium | — | — |
| STORY-018 | README: multi-turn context shipped, limits and trade-offs; .env.example settings | technical | ⬜ todo | small | — | — |

## Status Icons
- ⬜ todo
- 🟡 in-progress
- ✅ done
- 🔴 blocked

## Dependencies

- STORY-004 blocked by STORY-001, STORY-003
- STORY-005 blocked by STORY-002, STORY-004
- STORY-006 blocked by STORY-002
- STORY-007 blocked by STORY-001, STORY-004, STORY-005
- STORY-008 blocked by STORY-002, STORY-007
- STORY-009 blocked by STORY-007, STORY-008
- STORY-011 blocked by STORY-001
- STORY-012 blocked by STORY-006, STORY-007, STORY-010, STORY-011
- STORY-013 blocked by STORY-008, STORY-012
- STORY-014 blocked by STORY-006, STORY-012
- STORY-015 blocked by STORY-012
- STORY-016 blocked by STORY-005, STORY-008, STORY-009, STORY-013
- STORY-017 blocked by STORY-012
- STORY-018 blocked by STORY-014, STORY-015, STORY-016, STORY-017
