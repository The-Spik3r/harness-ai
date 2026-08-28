---
id: STORY-009
prd: PRD-004
slug: pii-badge
title: "Informational PII badge on assistant bubbles"
type: feature
priority: high
complexity: small
phase: "3 - Bubble redesign & PII badge"
status: done
labels: [ui, reflex, components, pii]
epic_branch: epic/PRD-004-chat-ui-redesign
plan: .agents/plans/PRD-004-chat-ui-redesign/completed/STORY-009-pii-badge.plan.md
report: .agents/reports/PRD-004-chat-ui-redesign/STORY-009-pii-badge.report.md
commit: 1097700
depends_on: [STORY-005, STORY-008]
blocks: [STORY-019]
skills: []
created: 2026-08-21
updated: 2026-08-21
---

# STORY-009: Informational PII badge on assistant bubbles

## Description

As an end user, I want to know when the harness masked personal data in my exchange, so that I understand why a response might read `<PERSON>` instead of a name (PRD User Story 3, Section 2 "Inform, don't obstruct").

## Acceptance Criteria

- [ ] Given an assistant message whose `pii_redacted` is `true`, when rendered, then a badge appears listing the entity types from `pii_entities` (e.g. "2 PII types masked in this exchange: PERSON, EMAIL_ADDRESS").
- [ ] Given an assistant message whose `pii_redacted` is `false`, when rendered, then no badge appears at all.
- [ ] Given the badge, when rendered, then it is quiet and inline — never a modal, never a confirmation step, never a gate on the conversation, and it never blocks sending (PRD Section 4, Out of Scope item 1).
- [ ] Given the badge copy, when read, then it describes the masking as covering the exchange, not the prompt alone (Risk 5).
- [ ] Given the badge, when rendered, then it shows entity *types* only — never detected values and never the raw text Presidio matched (PRD Section 9, "PII display guarantee").

## Technical Notes

- Renders inside the assistant bubble in `chat_ui/chat_ui/components/bubbles.py`; strings come from [[STORY-007]]'s `copy.py`; the data is already on the message from [[STORY-005]].
- Risk 2 mitigation, verbatim: "The badge is designed as a quiet inline element, not an alert: no color-coded alarm, no modal, no interruption. It is a factual annotation on the exchange." The default `PII_SCORE_THRESHOLD` of 0.35 is deliberately permissive, so the badge fires often — visual restraint is a requirement, not a preference.
- This consumes PRD-003 STORY-007's `pii_redacted` / `pii_entities_masked` fields and closes README "Known limitations (MVP)" item 4 (PRD Section 7, Section 15).
- Explicitly not in this story: showing the redacted prompt, or splitting input-side from output-side entities — both need backend changes and are Section 13 follow-ups.
- Per `chat_ui/AGENTS.md` (verbatim): "For anything about Reflex APIs — components, state management, events, styling, database, routing, authentication — use the **reflex-docs** skill rather than relying on memory. It carries current, version-accurate docs."
- Manual validation: send a prompt containing an email address and confirm the badge lists `EMAIL_ADDRESS` (PRD Section 12 Phase 3).

## Dependencies

- **Blocked by**: STORY-005, STORY-008
- **Blocks**: STORY-019

## PRD Reference

Source: [`PRD-004/PRD.md`](../../PRDs/PRD-004-chat-ui-redesign/PRD.md) — Section 4 (PII surfacing), Section 9, Section 12 Phase 3, User Story 3, Risks 2 and 5
