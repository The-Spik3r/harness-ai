---
story: STORY-008
prd: PRD-019
plan: .agents/plans/PRD-019-multi-instance-deployment/completed/STORY-008-balancer-drain-kill-long-calls.plan.md
epic_branch: epic/PRD-019-multi-instance-deployment
commit: pending
status: COMPLETE
completed: 2026-11-17
---

# Implementation Report - STORY-008: Balancer drain, kill, long calls and SSE

## Summary
Three tests on three stacks, tests only (nothing under `app/` changed). `tests/_balancer_stack.py` gains `caddyfile_seconds()` (`HEALTH_INTERVAL_S`, `LB_TRY_DURATION_S` read from `deploy/lb/Caddyfile`), `Balancer.all_children()`, `Child.kill -> bool`, and `FrontedBalancer` (lb Caddy -> front Caddy running the repo `Caddyfile` -> uvicorn, via the `_upstream_port` hook). `tests/test_two_instance_balancer.py` gains the drain case on the module stack, the kill case on its own `Balancer`, the concurrent 100 s `/v1` + 100 s `/query` + 30 s gzip SSE case on a `FrontedBalancer`, and `_stop_and_assert_gone` in every stack's teardown.

## Validation
| Check | Result |
|-------|--------|
| Backend import | OK |
| `test_two_instance_balancer.py` + `test_lb_caddyfile.py` + `test_docker_smoke_probe.py`, one pytest call, CADDY_BIN set | 40 passed, 0 failed, 0 skipped, 407.75 s |
| After the run | no caddy or python process left |
| Full suite | GitHub CI on push (user decision) |

## Deviations
1. Drain: the "call still in flight" assertion sits right after the drain window closes (before the probes), not after them: the 15 probes take ~15 s, which is longer than the 25 s stub delay minus the 10 s window, so asserting after them was wrong (first local run).
2. `_INVARIANTS` "no asserted latency" reworded: the kill case (D4 `lb_try_duration`) and the keep-alive cadence (D6) assert timing by contract.
3. No `slow` marker exists in this repo; none added.
4. Module wall time ~6.8 min locally (plan estimated ~6).
5. `_timed_stream` keeps httpx's default `trust_env`; no proxy interfered here.

## Acceptance Criteria
- [x] AC1 drain: `test_a_request_in_flight_on_a_drained_instance_completes_and_nothing_new_reaches_it` (counter deltas: A +0, B +15; in-flight 200 SUCCESS)
- [x] AC2 kill: `test_killing_an_instance_fails_no_request_through_the_balancer` (every request 200, under lb_try_duration + 2 s)
- [x] AC3 100 s calls: `test_long_calls_and_sse_keepalives_through_both_caddies` (both 200, elapsed >= 95 s asserted so a non-firing delay rule cannot pass)
- [x] AC4 SSE: same test; `keepalive_problems(minimum=2)`, `content_type` event-stream, `done`, `content_encoding == "gzip"` (asserted, passed)
- [x] AC5 teardown: `_stop_and_assert_gone` in all three fixtures (children dead, ports closed; stop() does not raise after the kill)
