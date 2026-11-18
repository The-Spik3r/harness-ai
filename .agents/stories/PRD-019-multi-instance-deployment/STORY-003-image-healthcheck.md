---
id: STORY-003
prd: PRD-019
slug: image-healthcheck
title: Liveness HEALTHCHECK in the image (python urllib against /health)
type: technical
priority: medium
complexity: small
phase: "1 - Probes"
status: done
labels: [docker, infra]
epic_branch: epic/PRD-019-multi-instance-deployment
plan: .agents/plans/PRD-019-multi-instance-deployment/completed/STORY-003-image-healthcheck.plan.md
report: .agents/reports/PRD-019-multi-instance-deployment/STORY-003-image-healthcheck.report.md
commit: 95d9393
depends_on: []
blocks: [STORY-005]
skills: []
created: 2026-11-17
updated: 2026-11-17
---

# STORY-003: Image `HEALTHCHECK`

## Description

As a platform operator, I want the image to report liveness to Docker, so that the balancer can `depends_on: service_healthy` and an outage of the database never restart-loops a container.

## Acceptance Criteria

- [ ] Given the `Dockerfile`, when built, then it declares `HEALTHCHECK --interval=10s --timeout=3s --start-period=60s CMD python -c "..."` that calls `http://127.0.0.1:$PORT/health` with `urllib.request` and a 2 s timeout (no curl: it is purged at `Dockerfile:49`).
- [ ] Given the probe targets `/health` (liveness), when the database is unreachable at runtime, then the healthcheck still passes (it never calls `/ready`).
- [ ] Given a static test (no Docker), when it parses the `Dockerfile`, then it asserts exactly one `HEALTHCHECK`, the interval/timeout/start-period above, the `/health` path and the absence of `curl`/`/ready` in it.
- [ ] Given `docker-compose.yml` and the start command, when unchanged, then single-instance behaviour is unchanged (no new port, no new service).

## Technical Notes

- `Dockerfile:70-87`: `STOPSIGNAL SIGKILL`, Caddy then `reflex run --backend-only`. `PORT` is available in the runtime env.
- Shell-form quoting inside `HEALTHCHECK CMD` is fragile; prefer the exec form (`CMD ["python", "-c", "..."]`) if the quoting reads better, and keep the test aligned with the chosen form.
- Put the static test in a new `tests/test_dockerfile_healthcheck.py` (or an existing Dockerfile test module if one exists — grep first).
- `docker build` is a manual/CI validation; the story does not add a Docker build to CI.

## Dependencies

- **Blocked by**: None
- **Blocks**: STORY-005

## PRD Reference

Source: [`PRD-019/PRD.md`](../../PRDs/PRD-019-multi-instance-deployment/PRD.md) — Sections 4 (Balancer, last bullet), 7 F5; decision D3
