---
id: STORY-006
prd: PRD-005
slug: authz-permission-matrix
title: authz service — permission constants, default role matrix, deny-by-default authorize()
type: feature
priority: high
complexity: medium
phase: "Phase 2 — Authorization core"
status: done
labels: [backend, security]
epic_branch: epic/PRD-005-rbac
plan: .agents/plans/PRD-005-rbac/completed/STORY-006-authz-permission-matrix.plan.md
report: .agents/reports/PRD-005-rbac/STORY-006-authz-permission-matrix.report.md
commit: 5d5281a
depends_on: [STORY-003, STORY-005]
blocks: [STORY-007, STORY-010, STORY-012]
skills: []
created: 2026-08-28
updated: 2026-08-28
---

# STORY-006: authz service — permission constants, default role matrix, deny-by-default authorize()

## Description

As a security admin, I want a data-driven role→permission matrix with a deny-by-default `authorize()`, so that access decisions live in one auditable table instead of conditionals scattered across the codebase.

## Acceptance Criteria

- [ ] Given the built-in matrix, when evaluated, then it matches PRD Section 7 exactly for `admin`, `auditor`, and `user` across `query:submit`, `query:byok`, `audit:read:all`, `audit:read:own`, and `stats:read`
- [ ] Given an identity whose role is not in the matrix, when `authorize()` runs, then it raises `PermissionDenied` — deny by default, never a fallback grant
- [ ] Given a permission absent from the role's grants, when `authorize()` runs, then it raises `PermissionDenied` carrying the permission name
- [ ] Given a granted permission, when `authorize()` runs, then it returns `None` and raises nothing
- [ ] Given `RBAC_ENABLED=false`, when `authorize()` runs, then it allows, and that bypass is a single explicit branch with its own test

## Technical Notes

- New `app/services/authz.py`, the only module the pipeline imports for authorization decisions — it hides where identity is stored from the code that makes decisions.
- Permission names are module constants; no string literals at call sites.
- `PermissionDenied(Exception)` carries `permission` so callers can report and audit it without re-deriving it.
- The matrix is a plain module-level dict — a policy table, not `if role == "admin"` branches. This is also the prerequisite shared with the roadmap's configurable pattern lists.
- Tests assert **every cell** of the matrix in both directions, grant and deny.

## Dependencies

- **Blocked by**: STORY-003, STORY-005
- **Blocks**: STORY-007, STORY-010, STORY-012

## PRD Reference

Source: [`PRD-005/PRD.md`](../../PRDs/PRD-005-rbac/PRD.md) — sections 6 and 7
