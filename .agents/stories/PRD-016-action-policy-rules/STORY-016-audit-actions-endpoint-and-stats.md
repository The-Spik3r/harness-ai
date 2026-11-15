---
id: STORY-016
prd: PRD-016
slug: audit-actions-endpoint-and-stats
title: GET /audit/actions with audit scoping, and the three action counts on /stats
type: feature
priority: medium
complexity: small
phase: "4 - Evidence"
status: done
labels: [backend, api, audit, rbac]
epic_branch: epic/PRD-016-action-policy-rules
plan: .agents/plans/PRD-016-action-policy-rules/completed/STORY-016-audit-actions-endpoint-and-stats.plan.md
report: .agents/reports/PRD-016-action-policy-rules/STORY-016-audit-actions-endpoint-and-stats.report.md
commit: pending
depends_on: [STORY-015]
blocks: [STORY-019]
skills: []
created: 2026-11-15
updated: 2026-11-15
---

# STORY-016: GET /audit/actions with audit scoping, and the three action counts on /stats

## Description

As a security admin, I want to read recent action decisions over the API, filtered by decision and scoped by my audit permission, so that denied actions can be reviewed and exported like the rest of the audit.

## Acceptance Criteria

- [ ] Given an identity with `audit:read:all`, when it calls `GET /audit/actions`, then every user's rows are returned newest first; with only `audit:read:own`, then only its own; with neither, then 403 with `Permission denied: audit:read:own`, matching `GET /audit`.
- [ ] Given `?decision=deny&limit=1`, when called, then one `deny` row is returned; `limit` outside 1–500 or an unknown `decision` → 422.
- [ ] Given a row, when returned, then the entry has exactly the fields of the PRD Section 10 example and **not** `arguments_preview` or `arguments_hash`; `classifications` is a list of objects.
- [ ] Given recorded decisions, when `GET /stats` is called, then it includes `actions_denied`, `actions_flagged`, `actions_allowed`, each 0 on an empty table, and every existing `/stats` field and assertion is unchanged.

## Technical Notes

- `app/routers/admin.py`: new route next to `get_audit`, copying its two-step `authorize` scoping; `/stats` reads `count_action_decisions()`.
- `app/models/schemas.py`: `ActionDecisionEntry`, `ActionsResponse`; `StatsResponse` gains three ints with default 0.
- `reason` IS a stored column (orchestrator decision, STORY-014/015 plans; PRD 6.10 amended): return it as stored, do not rebuild it.
- Tests: new `tests/test_admin_actions.py`; extend the `/stats` tests.
- Skills: none applicable. No UI.

## Dependencies

- **Blocked by**: STORY-015
- **Blocks**: STORY-019

## PRD Reference

Source: [`PRD-016-action-policy-rules/PRD.md`](../../PRDs/PRD-016-action-policy-rules/PRD.md) — sections 4 (API and admin console), 7 (F11), 9.1, 10
