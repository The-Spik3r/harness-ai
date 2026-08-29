---
id: STORY-015
prd: PRD-005
slug: admin-endpoint-permissions
title: /audit scoping and /stats gating by permission
type: feature
priority: high
complexity: medium
phase: "Phase 4 — Endpoint permissions, docs, rollout"
status: done
labels: [backend, api]
epic_branch: epic/PRD-005-rbac
plan: .agents/plans/PRD-005-rbac/completed/STORY-015-admin-endpoint-permissions.plan.md
report: .agents/reports/PRD-005-rbac/STORY-015-admin-endpoint-permissions.report.md
commit: PENDING
depends_on: [STORY-012, STORY-009]
blocks: [STORY-017]
skills: []
created: 2026-08-28
updated: 2026-08-28
---

# STORY-015: /audit scoping and /stats gating by permission

## Description

As a compliance reviewer, I want `/audit` and `/stats` gated by permission with per-user scoping, so that read access can be granted without granting everything the shared token grants today.

## Acceptance Criteria

- [ ] Given an identity with `audit:read:all`, when `GET /audit` is called, then every row is returned as today
- [ ] Given an identity with only `audit:read:own`, when it is called, then only that user's rows are returned and `total` reflects the scoped count
- [ ] Given an identity with neither permission, when it is called, then it returns `403`
- [ ] Given `GET /stats` and an identity without `stats:read`, when it is called, then it returns `403`; with the permission, the response shape is unchanged
- [ ] Given an audit entry, when serialized, then it carries `role` and `denied_permission`

## Technical Notes

- `app/routers/admin.py` moves from `dependencies=[Depends(require_admin_token)]` to permission dependencies plus an injected `Identity` — the handler needs the identity itself, not just the gate, in order to scope the query.
- `list_audit_logs(limit, user_id=None)` gains the scoping parameter; scoping happens in SQL, not by fetching everything and filtering in Python.
- `AuditQueryEntry` gains the two new fields.
- Raw `prompt_preview`/`response_preview` stay unexposed — out of scope per PRD Section 4, and the reason a `pii:view_raw` permission is deferred rather than defined here.
- Tests: `tests/test_audit_router.py`, `tests/test_stats_router.py`.

## Dependencies

- **Blocked by**: STORY-012, STORY-009
- **Blocks**: STORY-017

## PRD Reference

Source: [`PRD-005/PRD.md`](../../PRDs/PRD-005-rbac/PRD.md) — sections 4, 7, 10
