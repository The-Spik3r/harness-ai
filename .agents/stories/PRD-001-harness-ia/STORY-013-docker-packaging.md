---
id: STORY-013
prd: PRD-001
slug: docker-packaging
title: Docker & docker-compose packaging
type: technical
priority: medium
complexity: medium
phase: "5 - Docker & Documentation"
status: done
labels: [docker, infra]
epic_branch: epic/PRD-001-harness-ia
plan: .agents/plans/PRD-001-harness-ia/completed/STORY-013-docker-packaging.plan.md
report: .agents/reports/PRD-001-harness-ia/STORY-013-docker-packaging.report.md
commit: b7b939f
depends_on: [STORY-012]
blocks: [STORY-014]
skills: []
created: 2026-07-04
updated: 2026-07-04
---

# STORY-013: Docker & docker-compose packaging

## Description

As a devops engineer, I want the harness to run identically via Docker Compose or `python app.py`, so that local development and production deployment behave the same way (RF-15, RF-16).

## Acceptance Criteria

- [ ] Given a clean checkout with only Docker installed, when `docker-compose up` is run, then the API is reachable on the configured `PORT`/`HOST` and behaves identically to a local `python app.py` run (same endpoints, same responses).
- [ ] Given the `Dockerfile`, when built, then it produces a working image without requiring any manual post-build steps.
- [ ] Given `docker-compose.yml`, when started, then the SQLite DB persists across container restarts (mounted volume), so audit history isn't lost on redeploy.
- [ ] Given the full integration test suite from STORY-012, when run inside the container, then it passes exactly as it does locally.

## Technical Notes

- Add `Dockerfile` and `docker-compose.yml` at the project root per PRD Section 6/12 (Phase 5).
- Mount a volume for the SQLite file path derived from `DATABASE_URL` so data isn't lost between container recreations.
- Pass all env vars from PRD Section 9 through `docker-compose.yml`'s `environment:`/`env_file:`.

## Dependencies

- **Blocked by**: STORY-012
- **Blocks**: STORY-014

## PRD Reference

Source: [`PRD-001/PRD.md`](../../PRDs/PRD-001-harness-ia/PRD.md) — Section 5 (User Story 6), Section 12 (Phase 5), Section 2.5 (RF-15, RF-16 in source doc)
