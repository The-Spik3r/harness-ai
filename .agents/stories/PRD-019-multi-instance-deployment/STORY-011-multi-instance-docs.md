---
id: STORY-011
prd: PRD-019
slug: multi-instance-docs
title: Docs — multi-instance deployment, settings, roadmap tick; PRD close-out
type: technical
priority: medium
complexity: small
phase: "4 - Docs"
status: done
labels: [docs]
epic_branch: epic/PRD-019-multi-instance-deployment
plan: .agents/plans/PRD-019-multi-instance-deployment/completed/STORY-011-multi-instance-docs.plan.md
report: .agents/reports/PRD-019-multi-instance-deployment/STORY-011-multi-instance-docs.report.md
commit: 9633f67
depends_on: [STORY-010]
blocks: []
skills: []
created: 2026-11-17
updated: 2026-11-17
---

# STORY-011: Multi-instance docs

## Description

As a platform operator, I want the deployment docs to describe the shipped topology, probes, timeouts, rolling restart and failover cost, so that I can run and reason about several instances without reading the code.

## Acceptance Criteria

- [ ] Given `docs/deployment.md` "Multiple instances", when rewritten, then it has: the topology diagram, the start command, the affinity trade-off and what the user sees on failover (one sign-in, transcripts kept, in-flight answer lost), the probe table, the timeout invariant (every hop > `OPENROUTER_TIMEOUT_SECONDS` + 30 s) with numbers for a third-party balancer, the rolling restart, TLS/port constraint (D7), and the unsupported combinations (`REFLEX_REDIS_URL` set, `--scale`, IP-hash affinity). The "unblocked, not delivered" note is gone.
- [ ] Given `docs/configuration.md` and `.env.example`, when updated, then `DRAIN_FILE`, `READY_DB_TIMEOUT_SECONDS` and `LB_COOKIE_SECRET` are documented with defaults and validation, and `REFLEX_REDIS_URL` is documented as "leave unset".
- [ ] Given `docs/roadmap.md:33`, `README.md`, when updated, then the affinity item is ticked and the README links the new section.
- [ ] Given a docs test or check (existing docs-consistency tests if any; otherwise a grep in the report), when run, then every setting named in the new docs exists in `app/config.py` or `docker-compose.lb.yml`.
- [ ] Given this is the last story, when done, then the PRD frontmatter is `status: done` and the board shows 100%.

## Technical Notes

- Current text: `docs/deployment.md:39-44`.
- Use the real numbers and names from STORY-004/005 (Caddy version, cookie name, error status) — not the PRD's draft values if they changed.
- Mention the `tests/test_two_instance_smoke.py` docstring pointer only if STORY-007 added it.

## Dependencies

- **Blocked by**: STORY-010
- **Blocks**: None

## PRD Reference

Source: [`PRD-019/PRD.md`](../../PRDs/PRD-019-multi-instance-deployment/PRD.md) — Sections 4 (Documentation), 7 F7, 12 Phase 4
