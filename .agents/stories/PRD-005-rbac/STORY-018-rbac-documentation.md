---
id: STORY-018
prd: PRD-005
slug: rbac-documentation
title: README, .env.example, and roadmap updates for RBAC
type: technical
priority: medium
complexity: small
phase: "Phase 4 — Endpoint permissions, docs, rollout"
status: done
labels: [docs]
epic_branch: epic/PRD-005-rbac
plan: .agents/plans/PRD-005-rbac/completed/STORY-018-rbac-documentation.plan.md
report: .agents/reports/PRD-005-rbac/STORY-018-rbac-documentation.report.md
commit: 540fced
depends_on: [STORY-016, STORY-017]
blocks: []
skills: []
created: 2026-08-28
updated: 2026-08-29
---

# STORY-018: README, .env.example, and roadmap updates for RBAC

## Description

As an operator, I want README and `.env.example` to document authentication, roles, and the bootstrap procedure, so that a deployment can be upgraded without reading the source.

## Acceptance Criteria

- [ ] Given the README Features table, when read, then RBAC is listed alongside the existing capabilities
- [ ] Given the Environment Variables section, when read, then every `RBAC_*` variable and `MODEL_ALLOWLIST` is documented with its default
- [ ] Given the API Reference, when read, then the bearer-token requirement and the `401` / `403` / `200`-`BLOCKED` split are documented for `/query`, `/audit`, and `/stats`
- [ ] Given the Roadmap, when read, then "Role-based access control (RBAC)" has moved from Planned to Shipped
- [ ] Given Troubleshooting, when read, then it covers the unseeded-startup failure and the `401` vs `403` distinction
- [ ] Given `.env.example`, when compared to `Settings`, then it matches field for field

## Technical Notes

- Mirrors PRD-003's STORY-012 rollout story in shape and scope.
- Document explicitly that `ADMIN_TOKEN` is now a break-glass credential rather than the primary auth mechanism, and give the one-time bootstrap sequence plus the `RBAC_ENABLED=false` migration path.
- The README's "Action policy rules" section names RBAC as its natural pairing — update that cross-reference so it points at shipped behavior rather than planned work.

## Dependencies

- **Blocked by**: STORY-016, STORY-017
- **Blocks**: None

## PRD Reference

Source: [`PRD-005/PRD.md`](../../PRDs/PRD-005-rbac/PRD.md) — sections 9, 12 (Phase 4), 13
