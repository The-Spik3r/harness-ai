---
id: STORY-014
prd: PRD-006
slug: three-empty-states
title: "Three distinct register states: nothing recorded, nothing matching, rows shown"
type: feature
priority: medium
complexity: small
phase: "2 - The register"
status: done
labels: [ui, component, copy, admin]
epic_branch: epic/PRD-006-admin-console
plan: .agents/plans/PRD-006-admin-console/completed/STORY-014-three-empty-states.plan.md
report: .agents/reports/PRD-006-admin-console/STORY-014-three-empty-states.report.md
commit: 3fe5dda
depends_on: [STORY-005, STORY-008, STORY-011, STORY-013]
blocks: []
skills: [frontend-design]
created: 2026-08-28
updated: 2026-08-31
---

# STORY-014: Three distinct register states: nothing recorded, nothing matching, rows shown

## Description

As a compliance admin, I want an empty register to tell me whether nothing was recorded or nothing matched my filter, so that a blank table is never ambiguous (PRD Section 4, register).

## Acceptance Criteria

- [ ] Given a database with no audit rows at all, when the register renders, then it shows a "nothing recorded" state that says the record is empty — distinct in wording from the no-matches state.
- [ ] Given rows loaded but a filter that matches none of them, when the register renders, then it names the filter that produced the empty result and offers to clear it, and the clear action restores the full window.
- [ ] Given rows that match, when the register renders, then the table is shown and neither empty state appears.
- [ ] Given a failed read, when the register renders, then the fault panel is shown ([[STORY-017]]) rather than either empty state — an error is never presented as emptiness.
- [ ] Given all three states, when their copy is grepped, then every string resolves from `admin_copy`.
- [ ] Given the empty states, when they render, then they use the register's existing type and rules — no illustration, no card, no accent colour.

## Technical Notes

- PRD Section 4: "Three distinct states: no rows recorded at all, rows recorded but none matching the filter, and rows shown." The three-way condition is over `rows` (loaded) vs. `visible_rows` (filtered) from [[STORY-005]] — an empty `visible_rows` with a non-empty `rows` is the no-matches case.
- The **frontend-design** skill, verbatim: "Treat failure and emptiness as moments for direction, not mood... An empty screen is an invitation to act."
- PRD Section 6.1: "the no-matches state names the filter that produced it and offers to clear it."
- Order the render conditions so the error case is checked before the empty cases; otherwise a failed read that leaves `rows` empty renders as "nothing recorded", which is the exact misreading PRD Section 4 forbids.
- The chat's [empty_state()](../../../chat_ui/chat_ui/components/shell.py) (PRD-004 STORY-014) is the tonal precedent — read it, but do not reuse the component: PRD Section 4 requires that "no admin page renders a chat component."

## Dependencies

- **Blocked by**: STORY-005, STORY-008, STORY-011, STORY-013
- **Blocks**: None

## PRD Reference

Source: [`PRD-006/PRD.md`](../../PRDs/PRD-006-admin-console/PRD.md) — Section 4 (register), Section 6.1 (copy), Section 12 Phase 2
