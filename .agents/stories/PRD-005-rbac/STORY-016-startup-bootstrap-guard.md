---
id: STORY-016
prd: PRD-005
slug: startup-bootstrap-guard
title: Fail-fast startup guard when RBAC is enabled with no seeded users
type: technical
priority: high
complexity: small
phase: "Phase 4 — Endpoint permissions, docs, rollout"
status: done
labels: [backend, ops]
epic_branch: epic/PRD-005-rbac
plan: .agents/plans/PRD-005-rbac/completed/STORY-016-startup-bootstrap-guard.plan.md
report: .agents/reports/PRD-005-rbac/STORY-016-startup-bootstrap-guard.report.md
commit: 0580a98
depends_on: [STORY-002, STORY-004, STORY-005]
blocks: [STORY-018]
skills: []
created: 2026-08-28
updated: 2026-08-29
---

# STORY-016: Fail-fast startup guard when RBAC is enabled with no seeded users

## Description

As an operator upgrading an existing deployment, I want startup to fail with an actionable message when RBAC is on but no users exist, so that enabling it never leaves the service silently open or opaquely broken.

## Acceptance Criteria

- [ ] Given `RBAC_ENABLED=true` and zero active users, when the app starts, then it exits with a message naming `scripts/manage_users.py create-user`
- [ ] Given `RBAC_ENABLED=true` and at least one active user, when it starts, then it boots normally
- [ ] Given `RBAC_ENABLED=false`, when it starts, then the guard does not run and PRD-001 behavior is preserved exactly
- [ ] Given the chat UI entry point, when it starts, then the same guard runs there too
- [ ] Given only `ADMIN_TOKEN` is configured and no users are seeded, when it starts, then the guard still fails — break-glass is not a substitute for bootstrap

## Technical Notes

- The guard belongs in `app/main.py`'s `lifespan` **and** registered in `chat_ui/chat_ui/chat_ui.py`, the same duplication `init_db()` and `pii_redactor.load()` already require, because Reflex's `api_transformer` mounts the FastAPI app under an outer Starlette app whose own lifespan runs instead. A guard in only one place means one ingress boots unguarded.
- Failing fast is what makes `RBAC_ENABLED=true` safe as a default; the alternative is a service that returns `401` to every request with no explanation of why.
- Document `RBAC_ENABLED=false` as the supported migration escape hatch, not as a normal operating mode.

## Dependencies

- **Blocked by**: STORY-002, STORY-004, STORY-005
- **Blocks**: STORY-018

## PRD Reference

Source: [`PRD-005/PRD.md`](../../PRDs/PRD-005-rbac/PRD.md) — sections 9 and 14 (Risk 2)
