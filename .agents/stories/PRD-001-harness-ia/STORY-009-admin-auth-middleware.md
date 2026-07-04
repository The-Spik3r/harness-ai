---
id: STORY-009
prd: PRD-001
slug: admin-auth-middleware
title: Admin token authentication middleware
type: technical
priority: medium
complexity: small
phase: "4 - Admin Endpoints & Testing"
status: done
labels: [backend, security]
epic_branch: epic/PRD-001-harness-ia
plan: .agents/plans/PRD-001-harness-ia/completed/STORY-009-admin-auth-middleware.plan.md
report: .agents/reports/PRD-001-harness-ia/STORY-009-admin-auth-middleware.report.md
commit: ad50787
depends_on: [STORY-001]
blocks: [STORY-010, STORY-011]
skills: []
created: 2026-07-04
updated: 2026-07-04
---

# STORY-009: Admin token authentication middleware

## Description

As an admin, I want `/audit` and `/stats` protected by an admin token, so that only authorized staff can see even the hashed/truncated audit data.

## Acceptance Criteria

- [ ] Given a request to an admin-gated route without an `Authorization` bearer header, when handled, then it is rejected with 401/403.
- [ ] Given a request with an incorrect bearer value, when handled, then it is rejected with 401/403.
- [ ] Given a request with a bearer value matching `ADMIN_TOKEN`, when handled, then it is allowed through to the route handler.
- [ ] Given the dependency is reused, when applied to both `/audit` and `/stats`, then the same check logic is used (no duplicated auth code per route).

## Technical Notes

- Implement `app/middleware/auth.py` per PRD Section 6, as a FastAPI dependency (`Depends`) rather than raw ASGI middleware, for easy per-route application.
- Compares against `settings.ADMIN_TOKEN` from STORY-001's config object.

## Dependencies

- **Blocked by**: STORY-001
- **Blocks**: STORY-010, STORY-011

## PRD Reference

Source: [`PRD-001/PRD.md`](../../PRDs/PRD-001-harness-ia/PRD.md) — Section 5 (User Story 7), Section 9 (Auth approach), Section 12 (Phase 4)
