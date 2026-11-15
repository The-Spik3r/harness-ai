---
id: STORY-019
prd: PRD-016
slug: admin-console-actions-view
title: "Admin console: the Actions view — recent decisions, deny first, filterable"
type: feature
priority: medium
complexity: medium
phase: "4 - Evidence"
status: done
labels: [frontend, admin, audit]
epic_branch: epic/PRD-016-action-policy-rules
plan: .agents/plans/PRD-016-action-policy-rules/completed/STORY-019-admin-console-actions-view.plan.md
report: .agents/reports/PRD-016-action-policy-rules/STORY-019-admin-console-actions-view.report.md
commit: pending
depends_on: [STORY-016]
blocks: [STORY-020]
skills: [frontend-design]
created: 2026-11-15
updated: 2026-11-15
---

# STORY-019: Admin console: the Actions view — recent decisions, deny first, filterable

## Description

As a security admin, I want an Actions view in the admin console that shows what agents tried to do and what the policy decided, so that I can find denied actions and measure flagged classes without querying the API.

## Acceptance Criteria

- [ ] Given an admin with `audit:read:all`, when they open the console, then a fourth view, **Actions**, sits in the view switch beside Register, Summary and Usage, and its route renders through `admin_page(...)` like the other three.
- [ ] Given recorded decisions, when the view opens, then it shows `deny` rows by default, with columns for time, user, role, tool, operation, target, rule, decision and the permission that allowed it; a control switches between deny, flag, allow and all, and the list follows it.
- [ ] Given no decisions for the selected filter, when the view renders, then it shows an empty state that says what the view will contain and why it is empty (nothing calls the engine until PRD-017), not a blank table.
- [ ] Given 500 rows, and given a phone-width viewport, when the view renders, then it stays usable (no horizontal page scroll, long targets truncate with the full text available), and keyboard focus is visible on the filter control.
- [ ] Given the existing admin tests, when the suite runs, then Register, Summary and Usage are unchanged and green.

## Technical Notes

- New `chat_ui/chat_ui/components/actions.py`; `VIEW_ACTIONS` in `components/admin_shell.py` beside `VIEW_REGISTER`/`VIEW_SUMMARY`/`VIEW_USAGE`; a route and `admin_actions_page()` in `chat_ui/chat_ui/chat_ui.py`; state and row model in `admin_state.py` / `admin_models.py`; copy in `admin_copy.py` (labels and empty state live there, as for the other views).
- Data from the same database functions `GET /audit/actions` uses (STORY-015/015), read the way the Usage view reads `usage_snapshot()`.
- Reuse the Register table's components and the existing theme; do not restyle the console.
- Skill rules (frontend-design), verbatim, that apply here:
  - "Build with the brief's real content and subject matter throughout." Render real rule ids, reasons and targets from the corpus in development; no placeholder rows.
  - "Where the brief pins down a visual direction, follow it exactly — the brief's own words always win". Here the existing admin shell and theme set the direction; the view joins them rather than starting a new visual language.
  - "Structure is information. Structural devices, numbering, eyebrows, dividers, labels, should encode something true about the content, not decorate it." The decision column carries the visual weight (deny first); there is no decorative numbering.
  - "Name things by what people control and recognize, never by how the system is built." Filter labels say "Denied", "Flagged", "Allowed", not `deny`/`flag`/`allow` enum values.
  - "Treat failure and emptiness as moments for direction, not mood. Explain what went wrong and how to fix it, in the interface's voice rather than a person's." The empty state names PRD-017 as what starts filling the view.
  - "Build to a quality floor without announcing it: responsive down to mobile, visible keyboard focus, reduced motion respected."
- Tests: component and state tests in the style of the Usage view's (PRD-013 STORY-016).

## Dependencies

- **Blocked by**: STORY-016
- **Blocks**: STORY-020

## PRD Reference

Source: [`PRD-016-action-policy-rules/PRD.md`](../../PRDs/PRD-016-action-policy-rules/PRD.md) — sections 4 (API and admin console), 7 (F11), 10 (Admin console · Actions), 11 (Quality indicators), 15 (Skills referenced)
