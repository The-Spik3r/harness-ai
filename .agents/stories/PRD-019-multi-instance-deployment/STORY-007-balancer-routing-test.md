---
id: STORY-007
prd: PRD-019
slug: balancer-routing-test
title: Two-instance balancer test — harness, stickiness, limits, status table and 503 pass-through
type: feature
priority: high
complexity: large
phase: "3 - Proof"
status: done
labels: [tests, caddy, integration]
epic_branch: epic/PRD-019-multi-instance-deployment
plan: .agents/plans/PRD-019-multi-instance-deployment/completed/STORY-007-balancer-routing-test.plan.md
report: 
commit: ba1fbb2
depends_on: [STORY-002, STORY-005, STORY-006]
blocks: [STORY-008]
skills: []
created: 2026-11-17
updated: 2026-11-17
---

# STORY-007: Balancer routing test

## Description

As a maintainer, I want two real uvicorn instances, the stub upstream and a real Caddy running the shipped balancer file, so that stickiness, shared limits and the status contracts are proven through an actual hop.

## Acceptance Criteria

- [ ] Given `tests/test_two_instance_balancer.py`, when its module fixture starts, then two `uvicorn app.main:app` children (distinct ports, shared libSQL DB, `OPENROUTER_BASE_URL` → `scripts/stub_openrouter.py`) and one `caddy` running `deploy/lb/Caddyfile` with only the upstream addresses substituted are up; waits are deadline loops (no bare `sleep`); every child is killed and every port released on teardown, also on failure.
- [ ] Given twenty `POST /query` without a cookie (orchestrator decision: STORY-004 found cookie-less selection is random, so 20 makes a one-sided split a ~2e-6 event), when sent through the balancer, then both instances receive requests (counted per child, e.g. from each child's access log); ten carrying the `harness_lb` cookie from the first response all reach one instance.
- [ ] Given a user with a rate limit of 5, when 10 requests go through the balancer (spread across instances), then exactly 5 are admitted (PRD-013 T5 through a hop).
- [ ] Given the `/query` and `/v1` status table (success, 401, 422/400, 429, …), when replayed through the balancer and directly against an instance, then status, body and `Retry-After` match; an instance's PRD-018 503 (`StorageUnavailableError`, forced in that child) arrives byte-identical with its `Retry-After`, and the instance stays in rotation (it is still selected afterwards).
- [ ] Given both instances not ready (drain file in each), when `/v1/chat/completions` and `/query` are sent, then the balancer answers its own 503 with `Retry-After: 10` and the fixed bodies from STORY-005; `/health` and `/ready` through the balancer return their contracts while ready.

## Technical Notes

- D8: sibling module; do **not** modify `tests/test_two_instance_smoke.py` beyond a docstring pointer. Follow its `_INVARIANTS` style for deadline waits.
- Use the caddy helper from STORY-006 (skip/require semantics). Mark the module with the existing markers used for DB tests.
- Forcing a PRD-018 503 inside one child: an env/test hook only active in tests (check for an existing one from PRD-018 first, e.g. `force_open`), never a production route.
- Ports: pick free ports at runtime; on Windows, make sure caddy and uvicorn children are terminated (`Popen.kill` + wait).
- Keep the module's runtime reasonable (< ~2 min here); STORY-008 adds the slow cases to the same module.
- **Orchestrator decision (from STORY-004)**: the upstream override is a textual one-line replacement of `reverse_proxy harness-a:{$PORT} harness-b:{$PORT} {` (an `{$LB_UPSTREAMS:...}` default does not parse). Assert exactly one occurrence and that the rest is byte-identical. Give each `caddy run` child env `CADDY_ADMIN=localhost:<free port>` (default admin `:2019` collides) plus `PORT` and `LB_COOKIE_SECRET`. A no-healthy-upstream case takes about 5 s; cookie-less selection is random.

## Dependencies

- **Blocked by**: STORY-002, STORY-005, STORY-006
- **Blocks**: STORY-008

## PRD Reference

Source: [`PRD-019/PRD.md`](../../PRDs/PRD-019-multi-instance-deployment/PRD.md) — Sections 10, 11 (Functional requirements 4–6), 6.5; decisions D1, D8, D9
