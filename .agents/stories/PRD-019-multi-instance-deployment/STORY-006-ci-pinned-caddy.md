---
id: STORY-006
prd: PRD-019
slug: ci-pinned-caddy
title: CI installs a pinned Caddy binary; a shared caddy test helper with HARNESS_REQUIRE_CADDY
type: technical
priority: high
complexity: small
phase: "2 - Balancer"
status: todo
labels: [ci, tests, caddy]
epic_branch: epic/PRD-019-multi-instance-deployment
plan: null
report: null
commit: null
depends_on: [STORY-005]
blocks: [STORY-007]
skills: []
created: 2026-11-17
updated: 2026-11-17
---

# STORY-006: Pinned Caddy in CI

## Description

As a maintainer, I want CI to install the same Caddy version the balancer image pins and to fail (not skip) when it is missing, so that the balancer tests really run on every push.

## Acceptance Criteria

- [ ] Given `.github/workflows/ci.yml`, when the job runs, then it downloads the Caddy release pinned in STORY-004, verifies its SHA-256, puts it on `PATH`, and sets `HARNESS_REQUIRE_CADDY=1` for the test step.
- [ ] Given a test helper (e.g. `tests/_caddy.py`), when a test asks for the caddy binary, then it returns the path (from `PATH` or `CADDY_BIN`), skips with a clear reason when absent, and fails instead when `HARNESS_REQUIRE_CADDY=1`.
- [ ] Given the helper, when `caddy version` runs, then a test asserts the version equals the pinned one (in CI), so the balancer image and the CI binary cannot drift silently.
- [ ] Given the helper, when used to validate `deploy/lb/Caddyfile` (`caddy validate --adapter caddyfile` with the required env set), then it passes in CI; locally without caddy it skips.

## Technical Notes

- One pin, two places: the compose image digest and the CI binary. Consider one constant the test reads (e.g. in the test helper) and the static test (STORY-005) asserting the compose tag matches.
- Keep the CI change minimal; do not restructure existing steps (`ci.yml` has the libSQL service pinned by digest at `ci.yml:27`).
- This push is the first one with `HARNESS_REQUIRE_CADDY=1`: read its CI run before STORY-007 is planned.

## Dependencies

- **Blocked by**: STORY-005
- **Blocks**: STORY-007

## PRD Reference

Source: [`PRD-019/PRD.md`](../../PRDs/PRD-019-multi-instance-deployment/PRD.md) — Sections 4 (Tests), 8, 11 (Quality indicators); decision D8
