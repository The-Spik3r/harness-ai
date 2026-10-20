---
id: STORY-016
prd: PRD-013
slug: console-usage-table
title: "Admin console: Usage table"
type: feature
priority: medium
complexity: medium
phase: "4 - See it and prove it"
status: done
labels: [frontend, admin-console, limits, database]
epic_branch: epic/PRD-013-audit-and-usage-limits
plan: .agents/plans/PRD-013-audit-and-usage-limits/completed/STORY-016-console-usage-table.plan.md
report: .agents/reports/PRD-013-audit-and-usage-limits/STORY-016-console-usage-table.report.md
commit: 6308359
depends_on: [STORY-008, STORY-009, STORY-011, STORY-015]
blocks: [STORY-018]
skills: [frontend-design]
created: 2026-10-04
updated: 2026-10-19
---

# STORY-016: Admin console: Usage table

## Description

As a platform operator, I want one table showing what each user has used today against their limit, so that I can see who is near or over a budget without querying the database.

## Acceptance Criteria

- [ ] Given users who sent requests today, when the console loads, then the Usage table shows one row per such user with user, role, requests, input tokens, output tokens, budget, share of budget used and refusals today, and its caption states the window ("Today, UTC").
- [ ] Given a user with a per-user override, a user on the role default and a user whose budget is `unlimited`, when the table renders, then each shows its effective budget, and the unlimited row shows no share.
- [ ] Given nobody has sent anything today, when the table renders, then it shows "No one has sent anything today." and no empty grid.
- [ ] Given the usage read failing, when the console loads, then the failure is named under its own read label and the summary and Register still render; given `sign_out()`, then the usage rows are cleared.
- [ ] Given `usage_snapshot()`, when it is called, then it issues one statement, and the component contains no chart, no history control and no per-row action.

## Technical Notes

- `frontend-design`, verbatim: *"Structure is information. Structural devices, numbering, eyebrows, dividers, labels, should encode something true about the content, not decorate it."* This is why the view is a plain table with a stated window and no meters, sparklines or accent colours: the share is a number in a column.
- `frontend-design`, verbatim: *"Write from the end user's side of the screen. Name things by what people control and recognize, never by how the system is built."* and *"Treat failure and emptiness as moments for direction, not mood. Explain what went wrong and how to fix it, in the interface's voice rather than a person's. Errors don't apologize, and they are never vague about what happened."* The empty-state line and the caption follow these rules.
- Follow the existing register table and `theme.py`; no new visual direction (PRD Section 6.10, Risk 6). Scope is fixed: one table, today only.
- `app/db/database.py`: `usage_snapshot() -> list[...]`, one statement over `usage_daily` for `date('now')`, left-joined to `users` for role and overrides and to a grouped count of today's `audit_logs` rows with `limit_exceeded IS NOT NULL`. The break-glass `admin` has no `users` row: the join must keep it, with role `admin`.
- Effective limits are resolved in Python with `usage_limits.limits_for`, not in SQL, so the table and the gate cannot disagree.
- `admin_models.py`: a `UsageRow` projection with pre-formatted strings. `admin_state.py`: load it in `AdminState.load` with its own `READ_LABEL`, outside `summary_snapshot`. New `components/usage.py`, mounted from `admin_shell.py`.
- Refusals are counted from audit rows, so the gate needs no extra write (PRD Section 6.10).
- New file `tests/test_usage_view.py`.

## Dependencies

- **Blocked by**: STORY-008, STORY-009, STORY-011, STORY-015
- **Blocks**: STORY-018

## PRD Reference

Source: [`PRD-013-audit-and-usage-limits/PRD.md`](../../PRDs/PRD-013-audit-and-usage-limits/PRD.md) — sections 5 (story 3), 6.10, 7 (F16), 11 (Surfaces), 14 (Risk 6)
