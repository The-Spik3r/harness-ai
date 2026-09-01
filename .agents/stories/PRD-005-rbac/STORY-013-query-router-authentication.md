---
id: STORY-013
prd: PRD-005
slug: query-router-authentication
title: POST /query bearer authentication and status-code mapping
type: feature
priority: high
complexity: medium
phase: "Phase 3 — Pipeline and ingress wiring"
status: done
labels: [backend, api, security]
epic_branch: epic/PRD-005-rbac
plan: .agents/plans/PRD-005-rbac/completed/STORY-013-query-router-authentication.plan.md
report: .agents/reports/PRD-005-rbac/STORY-013-query-router-authentication.report.md
commit: 7f84803
depends_on: [STORY-010, STORY-011, STORY-012]
blocks: [STORY-017]
skills: []
created: 2026-08-28
updated: 2026-08-28
---

# STORY-013: POST /query bearer authentication and status-code mapping

## Description

As an integrating developer, I want `POST /query` to authenticate via a bearer token and map each outcome to the documented status code, so that the endpoint has a predictable auth contract.

## Acceptance Criteria

- [ ] Given no `Authorization` header, when `POST /query` is called, then it returns `401` and no audit row is written
- [ ] Given a valid credential whose role lacks `query:submit`, when it is called, then it returns `403` naming the permission
- [ ] Given a body `user_id` different from the authenticated user, when it is called, then it returns `403` rather than silently overriding it
- [ ] Given a body `user_id` that matches or is absent, when it is called, then the request proceeds and the audited user id comes from the credential
- [ ] Given a policy refusal (model outside the allowlist, or BYOK without permission), when it is called, then it returns `200` with `status: "BLOCKED"` and `required_permission`

## Technical Notes

- `app/routers/query.py`: `Depends(require_identity)` supplies the `Identity` handed to `run_query()`.
- `QueryRequest.user_id` becomes `Optional[str]` and is documented as deprecated — accepted for backward compatibility, never trusted as identity.
- The three-way split (`401` / `403` / `200` + `BLOCKED`) is PRD Section 9: endpoint-level denials are transport errors, content-level policy refusals stay in-band so the chat UI can render them as bubbles.
- The existing `DuplicateCheckError` / `PiiRedactorError` / `OpenRouterError` handlers are untouched.
- Tests: `tests/test_query_router.py`.

## Dependencies

- **Blocked by**: STORY-010, STORY-011, STORY-012
- **Blocks**: STORY-017

## PRD Reference

Source: [`PRD-005/PRD.md`](../../PRDs/PRD-005-rbac/PRD.md) — sections 9 and 10
