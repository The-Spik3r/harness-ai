---
story: STORY-010
prd: PRD-019
plan: .agents/plans/PRD-019-multi-instance-deployment/completed/STORY-010-docker-e2e-websocket-failover.plan.md
epic_branch: epic/PRD-019-multi-instance-deployment
commit: pending
status: COMPLETE
completed: 2026-11-18
---

# Implementation Report — STORY-010: Opt-in Docker E2E for the balanced stack

**Plan**: `.agents/plans/PRD-019-multi-instance-deployment/completed/STORY-010-docker-e2e-websocket-failover.plan.md`
**Epic Branch**: `epic/PRD-019-multi-instance-deployment`
**Commit**: `pending`

## Summary

`tests/e2e/test_lb_docker.py` runs the real image twice behind the shipped `docker-compose.lb.yml`, laid over by `tests/e2e/docker/compose.lb-e2e.yml` (project `harness-lb-e2e`, throwaway libSQL, a stub inside each instance container, `lb` published on a free loopback host port). It proves the websocket 101 and stickiness across reconnects, kill and failover with the cookie re-set, and `scripts/rolling_restart.sh` under a `POST /query` loop. `rolling_restart.sh` gained a repeatable `-f` and a `-p` (backward compatible).

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | repeatable `-f`, new `-p` | `scripts/rolling_restart.sh` | done |
| 2 | shim and flag tests | `tests/test_rolling_restart_script.py` | done |
| 3 | overlay and E2E module | `tests/e2e/docker/compose.lb-e2e.yml`, `tests/e2e/test_lb_docker.py` | done |
| 4 | static overlay guard | `tests/test_lb_e2e_overlay.py` | done |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| Targeted, no Docker (`test_rolling_restart_script`, `test_lb_e2e_overlay`, `test_lb_caddyfile`, E2E module without `--run-e2e`) | 40 passed, 5 skipped (the 4 E2E tests skip) |
| E2E, first run (cold image build) | 4 passed, 762 s |
| E2E, second run (image cached) | 4 passed, 350 s; query loop 75 calls, 0 failures |
| `docker compose ... config --quiet` | exit 0 with `.env` present and in a copy with no `.env` |
| Leftovers | no container, volume or network of `harness-lb-e2e`; `harness-libsql-dev` untouched; image `harness-lb-e2e:local` stays (like the smoke's local image) |
| Full suite | GitHub CI on push (user decision) |

## Deviations from Plan

- The instance identification used the plan's baseline-and-window approach (per-instance `(min, max)` over a 2 s window inside the container; the holder is the one whose held minimum exceeds its baseline maximum, exactly one). The Caddy keep-alive noise did not defeat it, so no fallback was needed.
- Reflex accepted the upgrade without an `Origin` header; none is sent (the test retries with `Origin` only if refused).
- Query-loop floor lowered to 30 calls (a call takes about 0.9 s through the stack, 70-75 calls ran).
- Leftovers are checked by compose project label rather than name filter.
- The `websockets` 17 `DeprecationWarning` for a held `connect()` is filtered in the module.

## Files Changed

CREATE `tests/e2e/docker/compose.lb-e2e.yml`, `tests/e2e/test_lb_docker.py`, `tests/test_lb_e2e_overlay.py`; UPDATE `scripts/rolling_restart.sh`, `tests/test_rolling_restart_script.py`.

## Acceptance Criteria

- [x] AC1 own project, skips without `--run-e2e`, `service_healthy`: `test_stack_comes_up_healthy`, `tests/test_lb_e2e_overlay.py`
- [x] AC2 101 and the same instance across reconnects: `test_websocket_upgrade_is_sticky_across_reconnects`
- [x] AC3 kill, upgrade on the other instance, cookie re-set: `test_failover_to_the_other_instance_and_cookie_reset`
- [x] AC4 script rc 0, no loop failure: `test_rolling_restart_script_under_query_loop`
- [x] AC5 `down -v` on teardown: `stack` fixture `finally`, verified empty afterwards
