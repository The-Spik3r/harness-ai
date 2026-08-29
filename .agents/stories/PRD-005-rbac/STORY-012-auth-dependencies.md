---
id: STORY-012
prd: PRD-005
slug: auth-dependencies
title: require_identity and require_permission FastAPI dependencies
type: technical
priority: high
complexity: medium
phase: "Phase 3 — Pipeline and ingress wiring"
status: done
labels: [backend, api, security]
epic_branch: epic/PRD-005-rbac
plan: .agents/plans/PRD-005-rbac/completed/STORY-012-auth-dependencies.plan.md
report: .agents/reports/PRD-005-rbac/STORY-012-auth-dependencies.report.md
commit: PENDING
depends_on: [STORY-003, STORY-006]
blocks: [STORY-013, STORY-015]
skills: []
created: 2026-08-28
updated: 2026-08-28
---

# STORY-012: require_identity and require_permission FastAPI dependencies

## Description

As an integrating developer, I want dependencies that resolve an identity and assert a permission, so that every HTTP route shares one authentication path with consistent status codes.

## Acceptance Criteria

- [ ] Given no or an invalid bearer credential, when `require_identity` runs, then it raises `401` with `"Invalid or missing credential"`
- [ ] Given a valid credential, when `require_identity` runs, then it returns the resolved `Identity`
- [ ] Given an identity lacking the required permission, when `require_permission(p)` runs, then it raises `403` with `"Permission denied: {p}"`
- [ ] Given the existing `ADMIN_TOKEN`, when sent to `/audit` or `/stats`, then it still authenticates as `admin` and `tests/test_admin_auth.py` passes **unmodified**
- [ ] Given `require_admin_token` is reimplemented on top of the new dependencies, when exercised, then its externally observable behavior is unchanged

## Technical Notes

- `app/middleware/auth.py`, extending the existing `HTTPBearer(auto_error=False)` scheme rather than introducing a second one.
- Keep `secrets.compare_digest` on the `ADMIN_TOKEN` path — constant-time comparison is already the convention in this file.
- These dependencies are **defense in depth**, not the authoritative control for query traffic: the chat UI never reaches them, which is why the real check lives in the pipeline (STORY-010). Do not let this story's existence tempt a later change to move authorization back up into the router.
- The `401` vs `403` split is the explicit decision in PRD Section 9: `401` means the server does not know who you are; `403` means it knows and you may not.

## Dependencies

- **Blocked by**: STORY-003, STORY-006
- **Blocks**: STORY-013, STORY-015

## PRD Reference

Source: [`PRD-005/PRD.md`](../../PRDs/PRD-005-rbac/PRD.md) — sections 6 and 9
