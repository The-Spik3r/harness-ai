---
id: STORY-008
prd: PRD-019
slug: balancer-drain-kill-long-calls
title: Balancer test — drain, kill, 100 s calls and SSE keep-alives through both Caddies
type: feature
priority: high
complexity: large
phase: "3 - Proof"
status: todo
labels: [tests, caddy, integration]
epic_branch: epic/PRD-019-multi-instance-deployment
plan: null
report: null
commit: null
depends_on: [STORY-007]
blocks: [STORY-010]
skills: []
created: 2026-11-17
updated: 2026-11-17
---

# STORY-008: Drain, kill and long calls through the balancer

## Description

As an operator and integrating developer, I want drain, instance death, slow completions and SSE keep-alives proven through the real balancer, so that restarts drop no request and long calls are not cut by a proxy timeout.

## Acceptance Criteria

- [ ] Given a request in flight on instance A (stub delay), when A's drain file is touched, then within `health_interval × 2` no new request reaches A, and the in-flight request completes with 200.
- [ ] Given instance A is killed (`SIGKILL` / `Popen.kill`), when requests continue, then they succeed through B within `lb_try_duration`, and no 5xx is seen after the first health interval.
- [ ] Given a 100 s stub delay, when non-streaming `/v1/chat/completions` and `POST /query` are sent through the balancer, then both return 200 (run concurrently, so the module pays ~100 s once).
- [ ] Given a 30 s stub delay, `V1_SSE_KEEPALIVE_SECONDS=10` and `Accept-Encoding: gzip`, when a streaming `/v1` call goes through the balancer **and** a per-instance Caddy running the repo's in-container `Caddyfile` (gzip on), then every `: keep-alive` arrives within 2 s of its interval and the final chunk arrives.
- [ ] Given the module, when it finishes, then every process is gone and the killed instance does not break later tests (fixture scope chosen so the kill case does not poison the STORY-007 cases).

## Technical Notes

- The "both Caddies" path: start a caddy with the repo `Caddyfile` in front of one uvicorn (`PORT`=front port, `BACKEND_INTERNAL_PORT`=uvicorn port; `/srv` absent is fine for API paths), and point the balancer at it. PRD-015 STORY-018 proved keep-alives through the in-container Caddy alone.
- `scripts/stub_openrouter.py` has `delay_seconds` rules.
- Order the slow and destructive cases so the module's wall time stays ~2–3 min in CI; mark the 100 s case so it can be deselected locally if a `slow` marker exists (grep `pytest.ini`/`pyproject` first).

## Dependencies

- **Blocked by**: STORY-007
- **Blocks**: STORY-010

## PRD Reference

Source: [`PRD-019/PRD.md`](../../PRDs/PRD-019-multi-instance-deployment/PRD.md) — Sections 5 (User Stories 4–6), 11 (Functional requirements 7–10); decisions D4, D6, D8
