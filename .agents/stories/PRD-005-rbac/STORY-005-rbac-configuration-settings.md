---
id: STORY-005
prd: PRD-005
slug: rbac-configuration-settings
title: RBAC configuration settings and env vars
type: technical
priority: high
complexity: small
phase: "Phase 2 — Authorization core"
status: done
labels: [backend, config]
epic_branch: epic/PRD-005-rbac
plan: .agents/plans/PRD-005-rbac/completed/STORY-005-rbac-configuration-settings.plan.md
report: .agents/reports/PRD-005-rbac/STORY-005-rbac-configuration-settings.report.md
commit: c2aca34
depends_on: []
blocks: [STORY-006, STORY-011, STORY-016]
skills: []
created: 2026-08-28
updated: 2026-08-28
---

# STORY-005: RBAC configuration settings and env vars

## Description

As an operator, I want RBAC exposed as environment variables, so that enforcement, the default role, the matrix file, and the model allowlist are per-deployment decisions rather than code changes.

## Acceptance Criteria

- [ ] Given `.env`, when `Settings` loads, then `RBAC_ENABLED` (bool, default `true`), `RBAC_DEFAULT_ROLE` (str, default `user`), `RBAC_ROLES_FILE` (str, default empty), and `MODEL_ALLOWLIST` (CSV str) are all available
- [ ] Given `MODEL_ALLOWLIST`, when read via a `model_allowlist_list` property, then it is parsed exactly the way `pii_entities_list` parses `PII_ENTITIES`
- [ ] Given none of the new variables are set, when the app starts, then the documented defaults apply and nothing raises
- [ ] Given `.env.example`, when read, then every new variable is present with an explanatory comment, matching `Settings` field for field

## Technical Notes

- `app/config.py` only. Follow the existing `PII_*` conventions, including the CSV-string-plus-property pattern — the codebase already established that a comma-separated env var is how a list is configured here.
- No new dependency: `pydantic-settings` already backs `Settings`.
- `RBAC_ENABLED` defaults to `true` (secure by default); the unseeded-startup guard that makes that default safe to ship is STORY-016.

## Dependencies

- **Blocked by**: None
- **Blocks**: STORY-006, STORY-011, STORY-016

## PRD Reference

Source: [`PRD-005/PRD.md`](../../PRDs/PRD-005-rbac/PRD.md) — section 9
