# PRD-004: Chat UI Redesign — Full Pipeline Visibility & Error Handling — Story Board

**PRD**: [PRD.md](./PRD.md)
**Epic Branch**: `epic/PRD-004-chat-ui-redesign` (base: `main`)
**Status**: active

## Progress

10/19 stories done — 53%

## Stories

All stories commit on the epic branch `epic/PRD-004-chat-ui-redesign`. No per-story branches.

| ID | Title | Type | Status | Complexity | Plan | Commit | Report |
|----|-------|------|--------|------------|------|--------|--------|
| STORY-001 | Offload run_query(...) to a worker thread via asyncio.to_thread | bug | ✅ done | medium | [.agents/plans/PRD-004-chat-ui-redesign/completed/STORY-001-async-run-query-offload.plan.md](../../../.agents/plans/PRD-004-chat-ui-redesign/completed/STORY-001-async-run-query-offload.plan.md) | f7e482a | [.agents/reports/PRD-004-chat-ui-redesign/STORY-001-async-run-query-offload.report.md](../../../.agents/reports/PRD-004-chat-ui-redesign/STORY-001-async-run-query-offload.report.md) |
| STORY-002 | Exhaustive except arms in send(): PiiRedactorError + catch-all | bug | ✅ done | small | [.agents/plans/PRD-004-chat-ui-redesign/completed/STORY-002-exhaustive-exception-handling.plan.md](../../../.agents/plans/PRD-004-chat-ui-redesign/completed/STORY-002-exhaustive-exception-handling.plan.md) | 59899ca | [.agents/reports/PRD-004-chat-ui-redesign/STORY-002-exhaustive-exception-handling.report.md](../../../.agents/reports/PRD-004-chat-ui-redesign/STORY-002-exhaustive-exception-handling.report.md) |
| STORY-003 | pending state var with finally-reset and single in-flight send guard | technical | ✅ done | small | [.agents/plans/PRD-004-chat-ui-redesign/completed/STORY-003-pending-state-flag.plan.md](../../../.agents/plans/PRD-004-chat-ui-redesign/completed/STORY-003-pending-state-flag.plan.md) | 0e7bbfe | [.agents/reports/PRD-004-chat-ui-redesign/STORY-003-pending-state-flag.report.md](../../../.agents/reports/PRD-004-chat-ui-redesign/STORY-003-pending-state-flag.report.md) |
| STORY-004 | ChatMessage typed model replaces list[dict[str, str]] | technical | ✅ done | medium | [.agents/plans/PRD-004-chat-ui-redesign/STORY-004-chat-message-model.plan.md](../../../.agents/plans/PRD-004-chat-ui-redesign/STORY-004-chat-message-model.plan.md) | — | — |
| STORY-005 | send() populates every metadata field from each pipeline outcome | feature | ✅ done | medium | [.agents/plans/PRD-004-chat-ui-redesign/completed/STORY-005-send-populates-outcome-metadata.plan.md](../../../.agents/plans/PRD-004-chat-ui-redesign/completed/STORY-005-send-populates-outcome-metadata.plan.md) | 1f7c642 | [.agents/reports/PRD-004-chat-ui-redesign/STORY-005-send-populates-outcome-metadata.report.md](../../../.agents/reports/PRD-004-chat-ui-redesign/STORY-005-send-populates-outcome-metadata.report.md) |
| STORY-006 | Migrate test_chat_state.py to structural bubble assertions | technical | ⬜ todo | medium | — | — |
| STORY-007 | Centralize all user-facing copy in chat_ui/copy.py | technical | ⬜ todo | small | — | — |
| STORY-008 | Six bubble renderers dispatched by rx.match on kind | feature | ⬜ todo | large | — | — |
| STORY-009 | Informational PII badge on assistant bubbles | feature | ✅ done | small | [.agents/plans/PRD-004-chat-ui-redesign/completed/STORY-009-pii-badge.plan.md](../../../.agents/plans/PRD-004-chat-ui-redesign/completed/STORY-009-pii-badge.plan.md) | 1097700 | [.agents/reports/PRD-004-chat-ui-redesign/STORY-009-pii-badge.report.md](../../../.agents/reports/PRD-004-chat-ui-redesign/STORY-009-pii-badge.report.md) |
| STORY-010 | Assistant bubble footer with model_used, tokens_used and audit_id | feature | ⬜ todo | small | — | — |
| STORY-011 | Duplicate card: humanized relative time and 24h window release | feature | ✅ done | small | [.agents/plans/PRD-004-chat-ui-redesign/completed/STORY-011-duplicate-relative-time.plan.md](../../../.agents/plans/PRD-004-chat-ui-redesign/completed/STORY-011-duplicate-relative-time.plan.md) | 7489579 | [.agents/reports/PRD-004-chat-ui-redesign/STORY-011-duplicate-relative-time.report.md](../../../.agents/reports/PRD-004-chat-ui-redesign/STORY-011-duplicate-relative-time.report.md) |
| STORY-012 | Typing indicator and disabled composer while a request is in flight | feature | ✅ done | small | [.agents/plans/PRD-004-chat-ui-redesign/completed/STORY-012-pending-indicator-composer-lock.plan.md](../../../.agents/plans/PRD-004-chat-ui-redesign/completed/STORY-012-pending-indicator-composer-lock.plan.md) | — | [.agents/reports/PRD-004-chat-ui-redesign/STORY-012-pending-indicator-composer-lock.report.md](../../../.agents/reports/PRD-004-chat-ui-redesign/STORY-012-pending-indicator-composer-lock.report.md) |
| STORY-013 | Auto-scroll the message area to the newest message on append | enhancement | ⬜ todo | small | — | — |
| STORY-014 | Redesigned shell: header with session identity, and empty state | feature | ✅ done | medium | [.agents/plans/PRD-004-chat-ui-redesign/completed/STORY-014-shell-header-empty-state.plan.md](../../../.agents/plans/PRD-004-chat-ui-redesign/completed/STORY-014-shell-header-empty-state.plan.md) | 07f100e | [.agents/reports/PRD-004-chat-ui-redesign/STORY-014-shell-header-empty-state.report.md](../../../.agents/reports/PRD-004-chat-ui-redesign/STORY-014-shell-header-empty-state.report.md) |
| STORY-015 | Inline validation error on empty user_id submit | enhancement | ✅ done | small | [.agents/plans/PRD-004-chat-ui-redesign/completed/STORY-015-user-id-validation.plan.md](../../../.agents/plans/PRD-004-chat-ui-redesign/completed/STORY-015-user-id-validation.plan.md) | 950daa0 | [.agents/reports/PRD-004-chat-ui-redesign/STORY-015-user-id-validation.report.md](../../../.agents/reports/PRD-004-chat-ui-redesign/STORY-015-user-id-validation.report.md) |
| STORY-016 | Model selector driven by a curated allowlist in config.py | feature | ✅ done | medium | [.agents/plans/PRD-004-chat-ui-redesign/completed/STORY-016-model-selector-allowlist.plan.md](../../../.agents/plans/PRD-004-chat-ui-redesign/completed/STORY-016-model-selector-allowlist.plan.md) | b418c07 | [.agents/reports/PRD-004-chat-ui-redesign/STORY-016-model-selector-allowlist.report.md](../../../.agents/reports/PRD-004-chat-ui-redesign/STORY-016-model-selector-allowlist.report.md) |
| STORY-017 | Populate device from the browser User-Agent on chat sends | feature | ⬜ todo | small | — | — |
| STORY-018 | Retry on error cards and edit-and-resend on duplicate cards | feature | ⬜ todo | medium | — | — |
| STORY-019 | Six-outcome walkthrough and full-suite regression verification | technical | ⬜ todo | medium | — | — |

## Status Icons
- ⬜ todo
- 🟡 in-progress
- ✅ done
- 🔴 blocked

## Phases

- **Phase 1 — Correctness foundation**: STORY-001, STORY-002, STORY-003
- **Phase 2 — Typed message model**: STORY-004, STORY-005, STORY-006
- **Phase 3 — Bubble redesign & PII badge**: STORY-007, STORY-008, STORY-009, STORY-010, STORY-011, STORY-012, STORY-013
- **Phase 4 — Shell, session, and recovery actions**: STORY-014, STORY-015, STORY-016, STORY-017, STORY-018, STORY-019

## Dependencies

- STORY-002 blocked by STORY-001
- STORY-003 blocked by STORY-001
- STORY-004 blocked by STORY-002
- STORY-005 blocked by STORY-004
- STORY-006 blocked by STORY-005
- STORY-007 blocked by nothing (can start any time in Phase 3)
- STORY-008 blocked by STORY-004, STORY-007
- STORY-009 blocked by STORY-005, STORY-008
- STORY-010 blocked by STORY-005, STORY-008
- STORY-011 blocked by STORY-005, STORY-007, STORY-008
- STORY-012 blocked by STORY-003, STORY-008
- STORY-013 blocked by STORY-008
- STORY-014 blocked by STORY-007, STORY-008
- STORY-015 blocked by STORY-014
- STORY-016 blocked by STORY-014
- STORY-017 blocked by STORY-001
- STORY-018 blocked by STORY-005, STORY-008, STORY-011
- STORY-019 blocked by STORY-006, STORY-009, STORY-010, STORY-011, STORY-012, STORY-013, STORY-015, STORY-016, STORY-017, STORY-018
