# PRD-008: Chat Sessions — Persisted, Per-Conversation Transcripts — Story Board

**PRD**: [PRD.md](./PRD.md)
**Epic Branch**: `epic/PRD-008-chat-sessions` (base: `main`)
**Status**: active

## Progress

2/22 stories done — 9%

## Stories

All stories commit on the epic branch `epic/PRD-008-chat-sessions`. No per-story branches.

| ID | Title | Type | Status | Complexity | Plan | Commit |
|----|-------|------|--------|------------|------|--------|
| STORY-001 | CHAT_HISTORY_ENABLED and CHAT_SESSION_LIMIT settings, with the off state documented as supported | technical | ✅ done | small | [plan](../../plans/PRD-008-chat-sessions/completed/STORY-001-chat-history-configuration.plan.md) | `8830745` |
| STORY-002 | chat_sessions and chat_messages DDL and dataclasses in app/db/models.py | feature | ✅ done | small | [plan](../../plans/PRD-008-chat-sessions/completed/STORY-002-chat-session-schema.plan.md) | `PENDING` |
| STORY-003 | init_db() creates both transcript tables and converges the audit_logs.session_id column | technical | ⬜ todo | small | — | — |
| STORY-004 | Six user-scoped chat_sessions functions in database.py, with delete as one transaction | feature | ⬜ todo | medium | — | — |
| STORY-005 | append_chat_message and list_chat_messages, ordered by id and scoped by owner | feature | ⬜ todo | medium | — | — |
| STORY-006 | app/services/chat_sessions.py: the ownership rule and the CHAT_HISTORY_ENABLED short-circuit in one place | feature | ⬜ todo | medium | — | — |
| STORY-007 | tests/test_session_ownership.py: the ownership rule asserted against signatures, not against memory | technical | ⬜ todo | small | — | — |
| STORY-008 | session_id on AuditLog, log_query and insert_audit_log | feature | ⬜ todo | small | — | — |
| STORY-009 | run_query threads session_id to all seven log_query call sites, blocked and failed included | feature | ⬜ todo | medium | — | — |
| STORY-010 | QueryRequest.session_id with UUID validation and a 403 on a foreign session | feature | ⬜ todo | medium | — | — |
| STORY-011 | AuditQueryEntry.session_id so GET /audit reports the conversation | feature | ⬜ todo | small | — | — |
| STORY-012 | ChatSessionSummary plus auto-title derivation and relative activity time in formatting.py | feature | ⬜ todo | small | — | — |
| STORY-013 | ChatState holds the session list, creates lazily on first send, and passes session_id to run_query | feature | ⬜ todo | large | — | — |
| STORY-014 | Persist each bubble after it is appended, touch the session, and degrade without losing the turn | feature | ⬜ todo | medium | — | — |
| STORY-015 | Restore a transcript on sign-in and on switch, rehydrating all seven bubble kinds | feature | ⬜ todo | large | — | — |
| STORY-016 | New chat, rename, delete, and a logout that clears state without deleting rows | feature | ⬜ todo | medium | — | — |
| STORY-017 | Rail tokens in theme.py and every rail string in copy.py, adding no new ink | technical | ⬜ todo | small | — | — |
| STORY-018 | session_rail.py: the spine as the active mark, three states, no fill and no pill | feature | ⬜ todo | large | — | — |
| STORY-019 | The rail in the shell: full-width masthead kept, collapse at a narrow viewport, one transition | feature | ⬜ todo | medium | — | — |
| STORY-020 | Palette-drift and contrast assertions so the sidebar default fails a test, not a review | technical | ⬜ todo | small | — | — |
| STORY-021 | Two instances serve one session, and CHAT_HISTORY_ENABLED=false writes nothing — proven, not assumed | technical | ⬜ todo | medium | — | — |
| STORY-022 | README and .env: document the persistence model the code actually has, including what is now at rest | technical | ⬜ todo | small | — | — |

## Status Icons
- ⬜ todo
- 🟡 in-progress
- ✅ done
- 🔴 blocked

## Phases

| Phase | Stories |
|---|---|
| 1 — Schema and store | STORY-001 … STORY-007 |
| 2 — Pipeline and API | STORY-008 … STORY-011 |
| 3 — State and restore | STORY-012 … STORY-016 |
| 4 — Surface and hardening | STORY-017 … STORY-022 |

## Dependencies

- STORY-003 blocked by STORY-002
- STORY-004 blocked by STORY-002, STORY-003
- STORY-005 blocked by STORY-002, STORY-003
- STORY-006 blocked by STORY-001, STORY-004, STORY-005
- STORY-007 blocked by STORY-004, STORY-005, STORY-006
- STORY-008 blocked by STORY-003
- STORY-009 blocked by STORY-008
- STORY-010 blocked by STORY-006, STORY-009
- STORY-011 blocked by STORY-008
- STORY-013 blocked by STORY-006, STORY-009, STORY-012
- STORY-014 blocked by STORY-013
- STORY-015 blocked by STORY-014
- STORY-016 blocked by STORY-013, STORY-015
- STORY-018 blocked by STORY-012, STORY-013, STORY-016, STORY-017
- STORY-019 blocked by STORY-018
- STORY-020 blocked by STORY-018, STORY-019
- STORY-021 blocked by STORY-007, STORY-010, STORY-015, STORY-016
- STORY-022 blocked by STORY-010, STORY-011, STORY-019, STORY-021

STORY-001, STORY-002, STORY-012 and STORY-017 have no blockers and can start immediately. STORY-008 through STORY-011 depend only on STORY-003, so Phase 2 can run in parallel with the rest of Phase 1 once the schema lands.
