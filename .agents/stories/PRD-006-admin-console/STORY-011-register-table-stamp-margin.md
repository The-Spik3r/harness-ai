---
id: STORY-011
prd: PRD-006
slug: register-table-stamp-margin
title: "register.py: the audit table, the verdict column and the stamp margin"
type: feature
priority: high
complexity: large
phase: "2 - The register"
status: todo
labels: [ui, reflex, component, design, admin]
epic_branch: epic/PRD-006-admin-console
plan: null
report: null
commit: null
depends_on: [STORY-001, STORY-002, STORY-004, STORY-007, STORY-008, STORY-009, STORY-010]
blocks: [STORY-012, STORY-013, STORY-014, STORY-018]
skills: [frontend-design, reflex-docs, reflex-process-management]
created: 2026-08-28
updated: 2026-08-28
---

# STORY-011: register.py: the audit table, the verdict column and the stamp margin

## Description

As a compliance admin, I want blocked traffic to stand out from cleared traffic at a glance, so that I can scan a hundred rows without reading a hundred rows (PRD Section 5, stories 1 and 2).

## Acceptance Criteria

- [ ] Given `chat_ui/chat_ui/components/register.py`, when `/admin/audit` renders authenticated, then it shows the 100 most recent rows, newest first, over the columns PRD Section 4 names: timestamp (relative + absolute), `user_id`, verdict, `model_used`, `tokens_used`, PII indicator, `device`, `audit_id`.
- [ ] Given the scope line, when it renders, then it states the cap against the true total — "100 most recent of 3,180" — using `count_audit_logs()` as the denominator, so the window is never mistaken for the whole record.
- [ ] Given a row of each verdict, when the register renders, then **held**, **denied** and **fault** each carry their own ink (`INK_HELD`, `INK_DENIED`, `INK_FAULT`) and **cleared** carries `INK_CLEAR` — no two verdicts share a treatment.
- [ ] Given the stamp margin, when a hundred rows are loaded, then it is a fixed-width left column carrying each non-cleared row's verdict as a solid mark in its ink, blank for cleared rows, resolving into a vertical stripe of exceptions.
- [ ] Given the register's type, when it renders, then `FONT_DATA` is the dominant face and the numeric columns align down the full window; `FONT_DISPLAY` sets the verdict tags and column heads; `FONT_BODY` appears only on the scope lines.
- [ ] Given the register, when its rendered output is inspected, then no `TINT_*` value and no colour outside the four verdict inks plus the ground tokens appears, and no card or fill is used.
- [ ] Given the table, when the viewport is short, then it scrolls **within its own container** rather than scrolling the page.
- [ ] Given a seeded database whose rows have populated previews, when the page renders, then neither preview string appears anywhere in the output.

## Technical Notes

- New file `chat_ui/chat_ui/components/register.py`. Verdict dispatch is `rx.match` over `AuditRow.verdict` — the same pattern PRD-004 STORY-008 used in [chat_ui/chat_ui/components/bubbles.py](../../../chat_ui/chat_ui/components/bubbles.py); read it before writing a second dispatch by hand.
- Components read fields, never compute. PRD Section 6: "`AuditRow` carries the verdict, the relative time and the formatted device string as plain fields, computed in `admin_formatting.py`. Components read fields; they do not compute."
- PRD Section 6.1 on the signature: "A narrow fixed column down the left edge of the register carrying nothing but the row's verdict as a solid mark in its ink. Cleared rows leave it blank. The result is that a hundred rows resolve into a vertical stripe of exceptions: finding the three denied entries is a glance at an edge, not a read of a table."
- PRD Section 6.1 on type: "**`FONT_DATA` (JetBrains Mono) becomes the dominant face**... Monospace is not a stylistic choice here — the columns are numeric and must align down a hundred rows for scanning to work at all."
- The **frontend-design** skill, verbatim: "Structural devices, numbering, eyebrows, dividers, labels, should encode something true about the content, not decorate it." PRD Section 6.1 answers the skill's numbered-marker caution directly: `#3180` "is the row's real `audit_id`, monotonic, and the exact string a user quotes out of the chat's success footer... It is a key, not a decoration."
- Risk 6: the KPI-cards-over-striped-table default is the strongest pull in this design space. No cards, no fills, no accent colour. The test that enforces it is [[STORY-018]].
- Per `chat_ui/AGENTS.md`, verbatim: "For anything about Reflex APIs — components, state management, events, styling, database, routing, authentication — use the **reflex-docs** skill rather than relying on memory." `rx.foreach` over `list[AuditRow]` and `rx.match` are the APIs to confirm. And: "When you need to compile, run, reload, or debug a Reflex application, follow the **reflex-process-management** skill for the correct sequence and error investigation steps."
- Validate against a seeded database with all four verdicts present, per PRD Section 12 Phase 2.

## Dependencies

- **Blocked by**: STORY-001, STORY-002, STORY-004, STORY-007, STORY-008, STORY-009, STORY-010
- **Blocks**: STORY-012, STORY-013, STORY-014, STORY-018

## PRD Reference

Source: [`PRD-006/PRD.md`](../../PRDs/PRD-006-admin-console/PRD.md) — Section 4 (register), Section 5 (stories 1, 2), Section 6.1 (colour, type, layout, signature), Section 12 Phase 2, Risk 6
