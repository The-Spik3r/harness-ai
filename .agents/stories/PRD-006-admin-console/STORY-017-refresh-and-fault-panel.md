---
id: STORY-017
prd: PRD-006
slug: refresh-and-fault-panel
title: "Manual refresh with a last-refreshed stamp, and a fault panel with retry on both pages"
type: feature
priority: high
complexity: medium
phase: "4 - Hardening"
status: done
labels: [ui, component, resilience, admin]
epic_branch: epic/PRD-006-admin-console
plan: .agents/plans/PRD-006-admin-console/completed/STORY-017-refresh-and-fault-panel.plan.md
report: .agents/reports/PRD-006-admin-console/STORY-017-refresh-and-fault-panel.report.md
commit: null
depends_on: [STORY-004, STORY-008, STORY-011, STORY-015]
blocks: [STORY-019, STORY-020]
skills: [frontend-design, reflex-docs]
created: 2026-08-28
updated: 2026-08-31
---

# STORY-017: Manual refresh with a last-refreshed stamp, and a fault panel with retry on both pages

## Description

As a compliance admin, I want a deliberate refresh and a visible fault when a read fails, so that the console never shows me stale data as fresh or a failure as an empty table (PRD Section 4, data access & failure handling).

## Acceptance Criteria

- [ ] Given either admin page, when it renders authenticated, then it carries a **Refresh** control and a last-refreshed stamp reading **Refreshed {time}** — the same verb across the control and the line.
- [ ] Given a refresh in flight, when the page is observed, then the refresh control is locked for its duration and a loading indicator is shown.
- [ ] Given a read that raises, when the page renders, then a fault panel names the read that failed and offers a retry, and the previously loaded rows and figures are left untouched rather than cleared.
- [ ] Given the fault panel's retry, when it is used and the read succeeds, then the panel clears, the data updates and the refreshed stamp advances.
- [ ] Given the fault panel, when its copy is read, then it names what happened without apologizing and without vagueness.
- [ ] Given the loading indicator, when `prefers-reduced-motion: reduce` is set, then it does not animate — it is the console's sole moving element.
- [ ] Given both pages, when the fault path is exercised on each, then each renders the panel independently.
- [ ] Given the console, when it is left open, then it never auto-refreshes, polls, or pushes — refresh is only ever a deliberate action.

## Technical Notes

- The state this renders from — `loading`, `error`, `last_refreshed` — is [[STORY-004]]. This story is the surface and the retry event.
- PRD Section 4: "A failed read renders a fault panel naming what failed — never a silently empty table" and "Catch-all `except Exception` on every read path, matching PRD-004's 'no silent drops' invariant."
- The **frontend-design** skill, verbatim: "Errors don't apologize, and they are never vague about what happened." And: "An action keeps the same name through the whole flow, so the button that says 'Publish' produces a toast that says 'Published.'" PRD Section 6.1 applies it directly: "the control labeled **Refresh** produces the line **Refreshed 14:22:07**."
- PRD Section 6.1 on motion: "Effectively none, and deliberately... `prefers-reduced-motion` is respected for the loading indicator, which is the sole moving element." The skill's caution, verbatim: "extra animation contributes to the feeling that the design is AI-generated."
- PRD Section 4 out of scope: "Auto-refresh, polling, or push updates — refresh is a deliberate action." Do not add an interval.
- Per `chat_ui/AGENTS.md`, verbatim: "For anything about Reflex APIs — components, state management, events, styling, database, routing, authentication — use the **reflex-docs** skill rather than relying on memory. It carries current, version-accurate docs." Confirm how to disable a control from a state var and how `prefers-reduced-motion` is best expressed through the existing `GLOBAL_CSS` in [theme.py](../../../chat_ui/chat_ui/theme.py).
- Validate by forcing a read to raise, per PRD Section 12 Phase 4: "a read forced to raise renders the fault panel and recovers on retry."

## Dependencies

- **Blocked by**: STORY-004, STORY-008, STORY-011, STORY-015
- **Blocks**: STORY-019, STORY-020

## PRD Reference

Source: [`PRD-006/PRD.md`](../../PRDs/PRD-006-admin-console/PRD.md) — Section 4 (data access & failure handling), Section 6.1 (copy, motion), Section 7, Section 12 Phase 4
