---
id: STORY-001
prd: PRD-006
slug: audit-row-model
title: "AuditRow and SummaryFigure models — a projection with no preview fields"
type: technical
priority: high
complexity: small
phase: "1 - Access and data"
status: done
labels: [ui, reflex, model, admin]
epic_branch: epic/PRD-006-admin-console
plan: .agents/plans/PRD-006-admin-console/completed/STORY-001-audit-row-model.plan.md
report: .agents/reports/PRD-006-admin-console/STORY-001-audit-row-model.report.md
commit: 577a285
depends_on: []
blocks: [STORY-002, STORY-004, STORY-011]
skills: [reflex-docs]
created: 2026-08-28
updated: 2026-08-28
---

# STORY-001: AuditRow and SummaryFigure models — a projection with no preview fields

## Description

As an integrating developer, I want the register's row model to be an explicit projection of `AuditLog` that has no field for either preview, so that `prompt_preview` and `response_preview` are dropped at the boundary rather than being one binding away from the screen (PRD Section 6, Risk 2).

## Acceptance Criteria

- [ ] Given `chat_ui/chat_ui/admin_models.py`, when it is created, then it defines `AuditRow(rx.Base)` carrying every field the register renders: `audit_id`, `timestamp_absolute`, `timestamp_relative`, `user_id`, `verdict`, `model_used`, `tokens_used`, `pii_indicator`, `device_short`, `device_full`, `prompt_hash`, `error_message`, `pii_entities`, `pii_detected_input`, `pii_detected_output`, `suspicious_pattern`.
- [ ] Given `AuditRow`, when its fields are inspected, then it has **no** `prompt_preview` and **no** `response_preview` attribute, and a test asserts both are absent (Risk 2 mitigation).
- [ ] Given `admin_models.py`, when it is read, then it also defines `SummaryFigure(rx.Base)` with the fields the tally sheet needs — at minimum `label`, `value`, `scope`, and an optional `share` — so the summary renders figures rather than ad-hoc tuples.
- [ ] Given every field on both models, when constructed with no arguments, then each has a default, so a partially-populated row never raises at render time.
- [ ] Given `app/`, when `git diff main --stat` is inspected, then no file under it is modified.

## Technical Notes

- New file `chat_ui/chat_ui/admin_models.py`. Mirror the shape of the existing [chat_ui/chat_ui/models.py](../../../chat_ui/chat_ui/models.py) `ChatMessage` — same `rx.Base` subclassing, same all-fields-defaulted convention.
- The source row is `AuditLog` in [app/db/models.py:38-56](../../../app/db/models.py) (a `@dataclass`). Note `pii_entities` is stored as `Optional[str]` (TEXT), not a list — the projection is responsible for parsing it into `list[str]`; that parsing lives in [[STORY-002]].
- This story defines the models only. Populating them from `AuditLog` is [[STORY-002]] (derivation) and [[STORY-004]] (the read).
- Per `chat_ui/AGENTS.md`, verbatim: "For anything about Reflex APIs — components, state management, events, styling, database, routing, authentication — use the **reflex-docs** skill rather than relying on memory. It carries current, version-accurate docs." `rx.Base` field defaults and `rx.foreach` Var access over a typed model list are exactly the APIs to confirm there.
- PRD Section 6 / Risk 2, verbatim: "the row model (`AuditRow`) is a deliberate projection that has no field for either preview" — the absence *is* the mitigation, so do not add the fields "for completeness".

## Dependencies

- **Blocked by**: None
- **Blocks**: STORY-002, STORY-004, STORY-011

## PRD Reference

Source: [`PRD-006/PRD.md`](../../PRDs/PRD-006-admin-console/PRD.md) — Section 6 (derived-once row model), Section 9, Section 12 Phase 1, Risk 2
