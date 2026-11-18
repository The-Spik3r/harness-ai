---
id: STORY-009
prd: PRD-019
slug: rolling-restart-script
title: scripts/rolling_restart.sh — drain, wait, recreate, wait ready, one instance at a time
type: feature
priority: medium
complexity: medium
phase: "3 - Proof"
status: todo
labels: [ops, docker, scripts]
epic_branch: epic/PRD-019-multi-instance-deployment
plan: null
report: null
commit: null
depends_on: [STORY-005]
blocks: [STORY-010]
skills: []
created: 2026-11-17
updated: 2026-11-17
---

# STORY-009: Rolling restart script

## Description

As a platform operator, I want a script that restarts the instances one at a time after draining each, so that a deploy fails no request and never drains the last healthy instance.

## Acceptance Criteria

- [ ] Given `scripts/rolling_restart.sh [-f docker-compose.lb.yml]`, when any instance's in-container `/ready` is not 200 at start, then it refuses to run and exits non-zero naming the instance.
- [ ] Given all instances ready, when it runs, then for each service in order it: touches `$DRAIN_FILE` via `docker compose exec`; waits (deadline loop) until that instance's own `/ready` is 503; sleeps `health_interval × 2 + DRAIN_SECONDS` (`DRAIN_SECONDS` defaults to `OPENROUTER_TIMEOUT_SECONDS + 10`, overridable by env); `docker compose up -d --force-recreate --no-deps <svc>`; waits until `/ready` is 200.
- [ ] Given a replacement that never becomes ready (e.g. it exits at boot), when the deadline passes, then the script stops with a non-zero exit and leaves the remaining instance untouched and serving.
- [ ] Given a static test (no Docker), when it inspects the script, then `bash -n` passes (skip if no bash), and the test asserts the service list matches `docker-compose.lb.yml`'s instance services, the readiness check runs inside the container with `python -c` + `urllib` (instances publish no port, no curl in the image), and `set -euo pipefail` is present.

## Technical Notes

- PRD F6. The image has `python` but no `curl` (`Dockerfile:49`).
- `DRAIN_FILE` default must match `app/config.py` (STORY-001); the test can assert that.
- A non-empty audit journal does not block the stop (PRD-018 D11) — no journal handling in the script.
- The live exercise of the script is in STORY-010's E2E.
- Ensure the file is committed with LF line endings and the executable bit (`git update-index --chmod=+x`); check `.gitattributes`.

## Dependencies

- **Blocked by**: STORY-005
- **Blocks**: STORY-010

## PRD Reference

Source: [`PRD-019/PRD.md`](../../PRDs/PRD-019-multi-instance-deployment/PRD.md) — Sections 5 (User Story 4), 7 F6; decision D4
