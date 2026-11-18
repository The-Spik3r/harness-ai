---
story: STORY-002
prd: PRD-019
plan: .agents/plans/PRD-019-multi-instance-deployment/completed/STORY-002-ready-route-and-drain.plan.md
epic_branch: epic/PRD-019-multi-instance-deployment
commit: fa3e5dc
status: COMPLETE
completed: 2026-11-17
---

# Implementation Report - STORY-002: GET /ready with the drain flag

## Summary

Added sync `GET /ready` in `app/main.py`: drain file first (read per call), then `database.check_ready()`, mapped to the PRD Section 10 bodies with `Cache-Control: no-store` on every response and `Retry-After` only for `breaker_open`. `/ready` added to the Caddyfile `@backend_routes` matcher and the restated test lists. `/health` untouched.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | `/ready` route + imports | `app/main.py` | done |
| 2 | `/ready` in matcher | `Caddyfile` | done |
| 3 | Matcher + near-miss static paths | `tests/test_caddyfile_routes.py` | done |
| 4 | Reservation test | `tests/test_route_reservations.py` | done |
| 5 | `/ready` cases | `tests/test_main.py` | done |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| Tests (test_caddyfile_routes, test_route_reservations, test_main, test_untouched_app) | 53 passed, 0 failed, 0 skipped |
| E2E (TestClient, stubbed check_ready) | covered by Task 5 cases |

Full suite: GitHub CI on push (user decision).

## Deviations from Plan

None. The optional unstubbed DB E2E and the optional `_caddy_path_matches` assertion were not added.

## Tests Written

`tests/test_main.py`: ready 200, draining 503 (no check_ready call, removal restores), breaker_open (open/half_open), database_unreachable/auth, no-leak guard, drain leaves /health and /v1/models unchanged, drain file read at call time. `tests/test_route_reservations.py`: `test_ready_route_present_and_not_reserved`.

## Acceptance Criteria

- [x] AC1 ready 200 + no-store
- [x] AC2 drain 503, no check_ready, only /ready affected
- [x] AC3 breaker/db 503 bodies, headers, no leak
- [x] AC4 /health unchanged
- [x] AC5 Caddy matcher + reservations
