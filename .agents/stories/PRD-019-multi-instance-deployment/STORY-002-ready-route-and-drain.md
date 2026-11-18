---
id: STORY-002
prd: PRD-019
slug: ready-route-and-drain
title: GET /ready with the drain flag, routed through the in-container Caddy
type: feature
priority: high
complexity: medium
phase: "1 - Probes"
status: todo
labels: [backend, api, caddy]
epic_branch: epic/PRD-019-multi-instance-deployment
plan: null
report: null
commit: null
depends_on: [STORY-001]
blocks: [STORY-005, STORY-007]
skills: []
created: 2026-11-17
updated: 2026-11-17
---

# STORY-002: `GET /ready` and the drain flag

## Description

As a platform operator, I want an unauthenticated readiness endpoint that turns 503 while a drain file exists or the database is unusable, so that a balancer and a restart script can take an instance out of rotation before it is stopped.

## Acceptance Criteria

- [ ] Given a ready instance, when `GET /ready` is called with no auth, then it returns 200 `{"status": "ready", "breaker": "closed"}` with `Cache-Control: no-store`.
- [ ] Given the file named by `DRAIN_FILE` exists, when `GET /ready` is called, then it returns 503 `{"status": "not_ready", "reason": "draining"}` with no database or breaker read beyond `os.path.exists`; every other route (`/health`, `/query`, `/v1/*`) behaves exactly as without the file; removing the file restores 200.
- [ ] Given `check_ready()` reports `breaker_open` / `database_unreachable` / `database_auth`, when `GET /ready` is called, then it returns the matching Section 10 body (with `"breaker": "open" | "half_open"` and a `Retry-After` header only on `breaker_open`), and no body carries an endpoint or error text.
- [ ] Given `GET /health`, when called, then it is byte-identical to today's response and the existing `tests/test_main.py` `/health` cases pass unmodified.
- [ ] Given the in-container `Caddyfile`, when parsed by `tests/test_caddyfile_routes.py`, then `/ready` is an exact token in `@backend_routes` and in `EXPECTED_MATCHER` (comment citing PRD-019), and `tests/test_route_reservations.py` asserts `/ready` is a harness route that collides with no Reflex reserved route.

## Technical Notes

- `app/main.py:39-41` has `/health` (sync). `/ready` is also a sync route (anyio threadpool, PRD Section 6.3) so the pipeline executor (`app/routers/query.py:44-52`) cannot starve it.
- Order of checks (F1): drain file → breaker → own `SELECT 1`; each short-circuits.
- `Caddyfile:5` matcher; `tests/test_caddyfile_routes.py:30-45` restates it (restated-list pattern).
- Tests in `tests/test_main.py` (new `/ready` cases; use `tmp_path` for `DRAIN_FILE` and monkeypatch `check_ready` for the 503 classes — STORY-001 already tests the classifier itself).

## Dependencies

- **Blocked by**: STORY-001
- **Blocks**: STORY-005, STORY-007

## PRD Reference

Source: [`PRD-019/PRD.md`](../../PRDs/PRD-019-multi-instance-deployment/PRD.md) — Sections 4, 6.3, 7 F1–F2, 10; decisions D3, D4
