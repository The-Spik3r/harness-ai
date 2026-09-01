---
id: STORY-019
prd: PRD-006
slug: quality-floor-and-critique
title: "Quality floor pass: keyboard, focus, narrow viewport — and a design self-critique"
type: enhancement
priority: medium
complexity: medium
phase: "4 - Hardening"
status: done
labels: [ui, accessibility, design, admin]
epic_branch: epic/PRD-006-admin-console
plan: .agents/plans/PRD-006-admin-console/completed/STORY-019-quality-floor-and-critique.plan.md
report: .agents/reports/PRD-006-admin-console/STORY-019-quality-floor-and-critique.report.md
commit: 7cd66b4
depends_on: [STORY-017]
blocks: [STORY-020]
skills: [frontend-design, reflex-process-management]
created: 2026-08-28
updated: 2026-08-31
---

# STORY-019: Quality floor pass: keyboard, focus, narrow viewport — and a design self-critique

## Description

As a compliance admin, I want the console usable on a narrow screen and from the keyboard, and stripped of anything that does not serve the register's one job, so that the surface meets its quality bar without announcing it (PRD Section 11, quality indicators).

## Acceptance Criteria

- [ ] Given a keyboard-only user, when they traverse the gate, the view switch, the filters, the sort controls, the row disclosures, refresh and sign out, then every control is reachable in a sensible order with visible focus.
- [ ] Given a narrow viewport, when either page renders, then the layout holds — no horizontal page scroll — and the table scrolls within its own container.
- [ ] Given `prefers-reduced-motion: reduce`, when the console is used, then nothing animates, including the loading indicator.
- [ ] Given the register with a hundred rows loaded, when it is viewed, then the stamp margin reads as a scannable stripe and the numeric columns align down the full window — PRD Section 6.1's stated purpose is met on screen, not just in the code.
- [ ] Given a self-critique pass against Section 6.1, when it is complete, then at least one accessory that does not serve the register's one job has been identified and cut, and the cut is recorded in the story's report.
- [ ] Given the summary, when it is reviewed, then it carries no card, no fill and no accent colour, and the blocked figures read as a subset of the total by their indentation alone.
- [ ] Given the chat surface, when it is opened after this pass, then it is unchanged — no shared component or token was altered to serve the console.

## Technical Notes

- The **frontend-design** skill, verbatim: "Build to a quality floor without announcing it: responsive down to mobile, visible keyboard focus, reduced motion respected." And: "Consider Chanel's advice: before leaving the house, take a look in the mirror and remove one accessory."
- PRD Section 12 Phase 4 makes the critique a deliverable: "a self-critique pass against Section 6.1 — per the **frontend-design** skill's 'take one last look and remove one accessory' — with anything that does not serve the register's one job cut."
- The skill also, verbatim: "Critique your own work as you build, taking screenshots if your environment supports it – a picture is worth 1000 tokens." Screenshot the register at a hundred rows and at a narrow viewport; the stripe either reads or it does not.
- Per `chat_ui/AGENTS.md`, verbatim: "When you need to compile, run, reload, or debug a Reflex application, follow the **reflex-process-management** skill for the correct sequence and error investigation steps." This story runs the app repeatedly — follow it for every restart.
- Seed a hundred rows across all four verdicts before judging the stripe; a five-row test database cannot show whether the signature works.
- Any fix here must stay inside `chat_ui/` and resolve from [theme.py](../../../chat_ui/chat_ui/theme.py). If a fix would require a new token, add it there ([[STORY-007]]'s rule), not inline.

## Dependencies

- **Blocked by**: STORY-017
- **Blocks**: STORY-020

## PRD Reference

Source: [`PRD-006/PRD.md`](../../PRDs/PRD-006-admin-console/PRD.md) — Section 4 (design & copy), Section 6.1, Section 11 (quality indicators), Section 12 Phase 4
