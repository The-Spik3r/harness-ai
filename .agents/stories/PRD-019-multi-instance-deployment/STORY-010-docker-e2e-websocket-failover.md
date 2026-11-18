---
id: STORY-010
prd: PRD-019
slug: docker-e2e-websocket-failover
title: Opt-in Docker E2E — websocket stickiness, kill and reconnect, rolling restart
type: feature
priority: medium
complexity: medium
phase: "3 - Proof"
status: done
labels: [tests, e2e, docker]
epic_branch: epic/PRD-019-multi-instance-deployment
plan: .agents/plans/PRD-019-multi-instance-deployment/completed/STORY-010-docker-e2e-websocket-failover.plan.md
report: .agents/reports/PRD-019-multi-instance-deployment/STORY-010-docker-e2e-websocket-failover.report.md
commit: null
depends_on: [STORY-008, STORY-009]
blocks: [STORY-011]
skills: []
created: 2026-11-17
updated: 2026-11-18
---

# STORY-010: Docker E2E for the balanced stack

## Description

As a maintainer, I want an opt-in E2E that runs the real image twice behind the pinned balancer, so that the websocket path, stickiness and failover are proven where the Reflex backend actually runs.

## Acceptance Criteria

- [ ] Given `tests/e2e/test_lb_docker.py` with its own compose project (following `tests/e2e/test_docker_smoke.py` and `tests/e2e/docker/compose.smoke.yml`: throwaway libSQL, the stub in the instance's network namespace), when run without `--run-e2e`, then it skips; with it, the stack comes up via `service_healthy`.
- [ ] Given the stack, when a websocket upgrade to `/_event/?EIO=4&transport=websocket&token=…` goes through `lb` carrying the `harness_lb` cookie from a first `GET /`, then it returns 101 and reaches the cookie's instance (identified e.g. via container logs or an instance-identifying probe), repeatedly across reconnects.
- [ ] Given the cookie's instance is killed, when the client reconnects with the same cookie, then the upgrade succeeds on the other instance (and the cookie is re-set if STORY-004 found Caddy does so).
- [ ] Given `scripts/rolling_restart.sh` pointed at the E2E project, when run while a `POST /query` loop goes through `lb`, then the script exits 0 and no request in the loop fails.
- [ ] Given teardown, when the test ends (pass or fail), then `docker compose down -v` removes the project.

## Technical Notes

- The E2E compose may overlay or copy `docker-compose.lb.yml` for the test-only services (libSQL, stub); keep the shipped file unchanged. If the rolling-restart script needs a project name/file flag, STORY-009 provides `-f`; add `-p` if needed and note it.
- `websockets` comes with `uvicorn[standard]` (PRD Section 8); no new dependency.
- Port constraint D7 (Section 6.1): the balancer publishes the build-time `$PORT`.
- Not run in CI (opt-in). The implementer runs it locally if Docker is available and reports the result; if Docker is unavailable, say so plainly.

## Dependencies

- **Blocked by**: STORY-008, STORY-009
- **Blocks**: STORY-011

## PRD Reference

Source: [`PRD-019/PRD.md`](../../PRDs/PRD-019-multi-instance-deployment/PRD.md) — Sections 5 (User Stories 2–4), 6.2, 11 (E2E requirement); decisions D1, D7, D8
