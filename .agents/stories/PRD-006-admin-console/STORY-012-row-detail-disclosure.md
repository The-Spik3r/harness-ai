---
id: STORY-012
prd: PRD-006
slug: row-detail-disclosure
title: "Row detail disclosure: error_message, prompt_hash, PII entities, full User-Agent, pattern"
type: feature
priority: high
complexity: medium
phase: "2 - The register"
status: done
labels: [ui, reflex, component, admin]
epic_branch: epic/PRD-006-admin-console
plan: .agents/plans/PRD-006-admin-console/completed/STORY-012-row-detail-disclosure.plan.md
report: .agents/reports/PRD-006-admin-console/STORY-012-row-detail-disclosure.report.md
commit: null
depends_on: [STORY-008, STORY-011]
blocks: [STORY-018]
skills: [frontend-design, reflex-docs]
created: 2026-08-28
updated: 2026-08-31
---

# STORY-012: Row detail disclosure: error_message, prompt_hash, PII entities, full User-Agent, pattern

## Description

As a compliance admin, I want to see which queries failed and why, so that an outage or a broken redactor is visible in the record instead of hiding behind `/audit`'s projection (PRD Section 5, story 3).

## Acceptance Criteria

- [ ] Given any register row, when its disclosure is opened, then it shows `prompt_hash`, `error_message`, the PII entity types, the full User-Agent string and `suspicious_pattern`.
- [ ] Given a row marked **fault**, when it is expanded, then its `error_message` is rendered in full — a value `GET /audit` does not return at all.
- [ ] Given a row marked **denied**, when it is expanded, then the actual `suspicious_pattern` is shown, not the flattened boolean `AuditQueryEntry` exposes.
- [ ] Given a row with PII, when it is expanded, then `pii_detected_input` and `pii_detected_output` are shown **split**, having been shown combined as a single indicator in the row.
- [ ] Given a row with no error and no pattern, when it is expanded, then the empty fields are stated as absent rather than rendering blank cells.
- [ ] Given the disclosure, when it renders, then it exposes no `prompt_preview` and no `response_preview`.
- [ ] Given a keyboard user, when they reach a row's disclosure control, then it is focusable with visible focus and operable without a pointer.
- [ ] Given many rows, when several disclosures are opened, then each row's open state is independent and closing one does not close the others.

## Technical Notes

- Lives in `chat_ui/chat_ui/components/register.py` alongside [[STORY-011]]'s table.
- PRD Section 10's projection table is the specification for what moves in-row vs. on-disclosure: `device` is "truncated in-row, full on disclosure"; `pii_entities` are "entity types on disclosure"; `suspicious_pattern` gives "verdict **denied**, pattern on disclosure".
- PRD Section 9 on `error_message`: "shown to an authenticated admin only. These are the same exception strings PRD-004 already shows to end users in the chat's error bubbles, so surfacing them behind a token gate is a narrower disclosure than the one already shipped." No sanitizing is required, and none should be invented.
- Per-row open state over an `rx.foreach` has a specific Reflex idiom — per `chat_ui/AGENTS.md`, verbatim: "For anything about Reflex APIs — components, state management, events, styling, database, routing, authentication — use the **reflex-docs** skill rather than relying on memory. It carries current, version-accurate docs." Confirm it there rather than reaching for a component-local `useState` equivalent.
- The **frontend-design** skill, verbatim: "Let each element do exactly one job. A label labels, an example demonstrates, and nothing quietly does double duty." The disclosure carries evidence; it is not a second summary of the row.
- Keep the disclosure inside the register's existing type and rule system — no card, no fill (Risk 6).

## Dependencies

- **Blocked by**: STORY-008, STORY-011
- **Blocks**: STORY-018

## PRD Reference

Source: [`PRD-006/PRD.md`](../../PRDs/PRD-006-admin-console/PRD.md) — Section 4 (register), Section 5 (story 3), Section 7, Section 9, Section 10
