---
id: STORY-011
prd: PRD-004
slug: duplicate-relative-time
title: "Duplicate card: humanized relative time and 24h window release"
type: feature
priority: medium
complexity: small
phase: "3 - Bubble redesign & PII badge"
status: done
labels: [ui, reflex, components]
epic_branch: epic/PRD-004-chat-ui-redesign
plan: .agents/plans/PRD-004-chat-ui-redesign/completed/STORY-011-duplicate-relative-time.plan.md
report: .agents/reports/PRD-004-chat-ui-redesign/STORY-011-duplicate-relative-time.report.md
commit: 7489579
depends_on: [STORY-005, STORY-007, STORY-008]
blocks: [STORY-018, STORY-019]
skills: []
created: 2026-08-21
updated: 2026-08-24
---

# STORY-011: Duplicate card — humanized relative time and 24h window release

## Description

As an end user, I want a duplicate block to tell me when I first sent the message and when the block lifts, so that "you already asked this" is actionable rather than a bare rejection (PRD User Story 2, Section 4).

## Acceptance Criteria

- [ ] Given a `duplicate` message with `first_query_at`, when rendered, then the card shows a humanized relative time plus the absolute timestamp — e.g. "Already sent 2 hours ago (2026-08-21T10:30:00Z)".
- [ ] Given the same message, when rendered, then the card states when the 24-hour window releases, derived as `first_query_at` + 24 hours.
- [ ] Given a `first_query_at` that is empty or unparseable, when rendered, then the card still renders with the raw value and no crash — an error in time formatting must not swallow the bubble ("No silent drops").
- [ ] Given the duplicate card copy, when read, then it states that the text must change for a resend to go through (Risk 4).

## Technical Notes

- Formatting lives in the rendering layer or in a computed var — state keeps `first_query_at` as the raw string from the pipeline ([[STORY-005]]), so the migrated tests stay structural (Risk 1).
- The 24-hour figure comes from the pipeline's own reason string, "Duplicate query within 24 hours" (`app/services/query_pipeline.py`, `QueryBlockedDuplicateResponse.reason`); do not re-derive or reconfigure the window in the UI, and do not read the backend's dedup settings.
- Strings and the relative-time template come from [[STORY-007]]'s `copy.py`.
- Risk 4 context: the duplicate check hashes the prompt with no `user_id` filter, so another user's identical prompt blocks yours — "A real product issue, but a backend/product decision, tracked in Section 13". The copy must not promise per-user behavior the backend does not have.
- The "Edit and resend" button that pairs with this copy is [[STORY-018]].
- Manual validation: seed a duplicate in the DB (as `tests/test_chat_state.py::_seed_duplicate` does) and confirm the rendered relative time (PRD Section 12 Phase 3).
- Per `chat_ui/AGENTS.md` (verbatim): "For anything about Reflex APIs — components, state management, events, styling, database, routing, authentication — use the **reflex-docs** skill rather than relying on memory. It carries current, version-accurate docs."

## Dependencies

- **Blocked by**: STORY-005, STORY-007, STORY-008
- **Blocks**: STORY-018, STORY-019

## PRD Reference

Source: [`PRD-004/PRD.md`](../../PRDs/PRD-004-chat-ui-redesign/PRD.md) — Section 4 (Message model & rendering), Section 10, Section 12 Phase 3, User Story 2, Risk 4
