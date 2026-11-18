---
story: STORY-005
prd: PRD-019
plan: .agents/plans/PRD-019-multi-instance-deployment/completed/STORY-005-balancer-caddyfile-and-compose.plan.md
epic_branch: epic/PRD-019-multi-instance-deployment
commit: pending
status: COMPLETE
completed: 2026-11-17
---

# Implementation Report - STORY-005: Balancer Caddyfile, docker-compose.lb.yml and the static balancer test

## Summary

Added `deploy/lb/Caddyfile` (PRD F3 directive set, `handle_errors 502 503 504`), the standalone `docker-compose.lb.yml` (PRD F4, `name: harness-ai-lb`, digest-pinned `caddy:2.11.7`) and `tests/test_lb_caddyfile.py` (static contract). No pre-existing file was touched.

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| `tests/test_lb_caddyfile.py` + `tests/test_caddyfile_routes.py`, no CADDY_BIN | 16 passed, 1 skipped (caddy validate) |
| Same, with CADDY_BIN (Caddy 2.11.7 for Windows) | 17 passed, 0 skipped |
| `caddy validate --config deploy/lb/Caddyfile --adapter caddyfile` (PORT=8000, LB_COOKIE_SECRET=x, CADDY_ADMIN=localhost:23019) | rc 0, "Valid configuration" (DNS/health info lines for harness-a/b expected) |
| `docker compose -f docker-compose.lb.yml config`, secret set | rc 0; instances identical, no ports; lb has the digest image, 8000:8000, both depends_on service_healthy; PORT=9000 renders 9000 everywhere |
| Same, secret unset | rc 1: `required variable LB_COOKIE_SECRET is missing a value: set LB_COOKIE_SECRET, for example from openssl rand -hex 32` |
| Full suite | GitHub CI on push (user decision) |

## Files Changed

| File | Action |
|------|--------|
| `deploy/lb/Caddyfile` | CREATE |
| `docker-compose.lb.yml` | CREATE |
| `tests/test_lb_caddyfile.py` | CREATE (11 tests) |

## Deviations from Plan

- The `:?` message in compose is quoted and reads "set LB_COOKIE_SECRET, for example from openssl rand -hex 32": the plan's "(for example: openssl ...)" contains `: ` and YAML parsed the list item as a map (`docker compose config` rejected it).
- Compose `config` output on this machine prints `.env` secrets; none are recorded here.
- No explicit Content-Type header (as planned); STORY-007 asserts it live.

## Tests Written

`tests/test_lb_caddyfile.py`: affinity policy and site address; literal upstream line; health directives; timeouts (header timeout = OPENROUTER default + 30, from the model) and stream_close_delay; READY_DB_TIMEOUT_SECONDS < health_timeout; forbidden directives; handle_errors codes, Retry-After and both exact bodies; compose instances vs upstreams and ports; shared definition and journal volume (also equal to docker-compose.yml's); lb service (digest, mount, required secret, service_healthy, project name); optional `caddy validate`.

## Acceptance Criteria

- [x] AC1 Caddyfile directive set validates (tests 1-6, caddy validate test, manual validate)
- [x] AC2 handle_errors 503 + Retry-After + bodies (handle_errors test)
- [x] AC3 compose valid with secret, fails without (compose tests; manual config both ways)
- [x] AC4 static test with restated lists, no Docker/storage
- [x] AC5 single instance unchanged (`docker-compose.yml`, `Caddyfile` untouched; test_caddyfile_routes passes)
