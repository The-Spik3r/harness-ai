# PRD-019-multi-instance-deployment: Multi-Instance Deployment — Load Balancer, Health Checks and Websocket Session Affinity — Story Board

**PRD**: [PRD.md](./PRD.md)
**Epic Branch**: `epic/PRD-019-multi-instance-deployment` (base: `main`)
**Status**: active

## Progress

1/11 stories done — 9%

## Stories

All stories commit on the epic branch `epic/PRD-019-multi-instance-deployment`. No per-story branches.

| ID | Title | Type | Status | Complexity | Plan | Commit |
|----|-------|------|--------|------------|------|--------|
| STORY-001 | Readiness settings and database.check_ready() — a bounded, breaker-neutral SELECT 1 | feature | ✅ done | medium | [plan](../../plans/PRD-019-multi-instance-deployment/completed/STORY-001-readiness-settings-and-check-ready.plan.md) | `9682fcb` |
| STORY-002 | GET /ready with the drain flag, routed through the in-container Caddy | feature | 🟡 in-progress | medium | [plan](../../plans/PRD-019-multi-instance-deployment/STORY-002-ready-route-and-drain.plan.md) | — |
| STORY-003 | Liveness HEALTHCHECK in the image (python urllib against /health) | technical | ⬜ todo | small | — | — |
| STORY-004 | Spike — verify Caddy cookie policy, health, error and retry behaviour against a pinned Caddy | spike | ⬜ todo | small | — | — |
| STORY-005 | Balancer Caddyfile, docker-compose.lb.yml and the static balancer test | feature | ⬜ todo | medium | — | — |
| STORY-006 | CI installs a pinned Caddy binary; a shared caddy test helper with HARNESS_REQUIRE_CADDY | technical | ⬜ todo | small | — | — |
| STORY-007 | Two-instance balancer test — harness, stickiness, limits, status table and 503 pass-through | feature | ⬜ todo | large | — | — |
| STORY-008 | Balancer test — drain, kill, 100 s calls and SSE keep-alives through both Caddies | feature | ⬜ todo | large | — | — |
| STORY-009 | scripts/rolling_restart.sh — drain, wait, recreate, wait ready, one instance at a time | feature | ⬜ todo | medium | — | — |
| STORY-010 | Opt-in Docker E2E — websocket stickiness, kill and reconnect, rolling restart | feature | ⬜ todo | medium | — | — |
| STORY-011 | Docs — multi-instance deployment, settings, roadmap tick; PRD close-out | technical | ⬜ todo | small | — | — |

## Status Icons
- ⬜ todo
- 🟡 in-progress
- ✅ done
- 🔴 blocked

## Dependencies

- STORY-002 blocked by STORY-001
- STORY-005 blocked by STORY-002, STORY-003, STORY-004
- STORY-006 blocked by STORY-005
- STORY-007 blocked by STORY-002, STORY-005, STORY-006
- STORY-008 blocked by STORY-007
- STORY-009 blocked by STORY-005
- STORY-010 blocked by STORY-008, STORY-009
- STORY-011 blocked by STORY-010
