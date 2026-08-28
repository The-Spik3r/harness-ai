---
id: STORY-015
prd: PRD-006
slug: summary-tally-sheet
title: "summary.py: nine StatsResponse figures as a ruled tally sheet with stated scopes"
type: feature
priority: high
complexity: large
phase: "3 - The summary"
status: todo
labels: [ui, reflex, component, design, admin]
epic_branch: epic/PRD-006-admin-console
plan: null
report: null
commit: null
depends_on: [STORY-002, STORY-004, STORY-007, STORY-008, STORY-009, STORY-010]
blocks: [STORY-016, STORY-018]
skills: [frontend-design, reflex-docs]
created: 2026-08-28
updated: 2026-08-28
---

# STORY-015: summary.py: nine StatsResponse figures as a ruled tally sheet with stated scopes

## Description

As a compliance admin, I want each figure to say what it counts and over what window, so that I do not report a blocked-inclusive completion rate as a user success rate (PRD Section 5, stories 6 and 7).

## Acceptance Criteria

- [ ] Given `chat_ui/chat_ui/components/summary.py`, when `/admin/stats` renders authenticated, then all nine `StatsResponse` figures appear: `total_queries`, `blocked_duplicates`, `blocked_suspicious`, `unique_users`, `success_rate`, `top_models`, `top_users`, `pii_detected_queries`, `top_pii_entities`.
- [ ] Given `blocked_duplicates` and `blocked_suspicious`, when the sheet renders, then they are **indented beneath** `total_queries`, and each is shown as a count *and* as a share of `total_queries`.
- [ ] Given the completion figure, when its label renders, then it says it counts rows the pipeline completed without raising, blocked rows included — it does not read as an answer rate or as "success rate".
- [ ] Given every figure, when it renders, then it carries its scope: all-time over the whole table, stated distinctly from the register's last-100 window.
- [ ] Given `pii_detected_queries` and `top_pii_entities`, when the sheet renders, then both are visible — PRD-003's telemetry rendered in a UI for the first time.
- [ ] Given `top_models` and `top_users`, when they render, then they are ranked lists with the "top 5" cut stated on the surface.
- [ ] Given the sheet, when its rendered output is inspected, then it contains no card, no fill and no accent colour — only rules, type and the ground tokens.
- [ ] Given a total of 0, when the sheet renders, then every share renders its placeholder rather than raising.
- [ ] Given `app/models/schemas.py`, when the diff is inspected, then `StatsResponse` is unchanged.

## Technical Notes

- New file `chat_ui/chat_ui/components/summary.py`, rendering `SummaryFigure` objects from [[STORY-001]] built out of [[STORY-004]]'s loaded counts. Build the figures in state or in `admin_formatting.py`, not in the component — the derived-once rule applies here too.
- PRD Section 6.1 pins the structure: "The figures are set as a ruled list, not a grid of cards. `blocked_duplicates` and `blocked_suspicious` are **indented beneath** `total_queries`, because they are a subset of it and indentation is the honest structural statement of that relationship — a card grid asserts that all four numbers are peers, which is false. The who/what facts (`unique_users`, `top_models`, `top_users`) sit in a separate ruled block... PII telemetry closes the sheet."
- The **frontend-design** skill, verbatim: "a big number with a small label, supporting stats, and a gradient accent is the template answer, only use if that's truly the best option." PRD Section 6.1 rules it out here: "the admin's question is never 'what is the total', it is 'which rows are not cleared'."
- The naming defect being fixed, from PRD Section 1: "`StatsResponse.success_rate` is computed as `count_successful_queries() / count_audit_logs()`, where `count_successful_queries()` counts `success = 1` — which includes every duplicate-blocked and every injection-blocked row, because the pipeline logs both as `success=True`." Fix the **label**, not the computation — [app/](../../../app) is out of scope, and a truthful metric is deferred to PRD Section 13.
- `format_share` comes from [[STORY-002]]; do not compute percentages in the component.
- Per `chat_ui/AGENTS.md`, verbatim: "For anything about Reflex APIs — components, state management, events, styling, database, routing, authentication — use the **reflex-docs** skill rather than relying on memory. It carries current, version-accurate docs."
- Risk 4: "A summary that says `3,180 queries` beside a register showing 100 rows reads as a contradiction" — the scope label on every figure is the mitigation, not an optional nicety.

## Dependencies

- **Blocked by**: STORY-002, STORY-004, STORY-007, STORY-008, STORY-009, STORY-010
- **Blocks**: STORY-016, STORY-018

## PRD Reference

Source: [`PRD-006/PRD.md`](../../PRDs/PRD-006-admin-console/PRD.md) — Section 1, Section 4 (summary), Section 5 (stories 6, 7), Section 6.1 (tally sheet), Section 12 Phase 3, Risk 4
