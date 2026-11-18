---
story: STORY-007
prd: PRD-019
plan: .agents/plans/PRD-019-multi-instance-deployment/completed/STORY-007-balancer-routing-test.plan.md
epic_branch: epic/PRD-019-multi-instance-deployment
commit: ba1fbb2
status: COMPLETE
completed: 2026-11-17
---

# Implementation Report - STORY-007: Two-instance balancer test

## Summary
A reusable process stack (`tests/_balancer_stack.py`: stub + two uvicorn instances + Caddy running the shipped `deploy/lb/Caddyfile` with only its upstream line replaced), a test-only instance launcher (`tests/_lb_instance.py`: request counters, `/__test__/*`, frozen-clock breaker hook) and `tests/test_two_instance_balancer.py` (15 tests). Nothing under `app/` changed.

## Validation
| Check | Result |
|-------|--------|
| Backend import | OK |
| `test_two_instance_balancer.py` (CADDY_BIN + HARNESS_REQUIRE_CADDY=1), run 1 | 15 passed, 199.5 s |
| same, run 2 back to back | 15 passed, 189.5 s |
| After each run | no python/caddy process left, no test port listening |
| Forced failed start (instance given a relative DRAIN_FILE) | start() raised naming the child and log tail in 6 s; no child left |
| `test_lb_caddyfile.py`, `test_caddy_pin.py`, `test_db_resilience_breaker.py`, `test_db_resilience_retry.py`, `test_conftest_fixtures.py` | 217 passed |
| Full suite | GitHub CI on push (user decision) |

Forced-503 retry loop: needed 1 attempt in run 1 (the only run printing it); never needed a second locally.
Wall time is above the plan's 2 min target (about 3 min 10 s): per-test setup (init-db on both children plus resets) costs about 5 s per test, the 20-query test 32 s, the drain case 22 s.

## Deviations (all accepted by the orchestrator)
1. No 429: usage refusals are `200 BLOCKED` on `/query` and `403` on `/v1`; the limit rows use the token budget.
2. Success bodies compared after blanking `audit_id`, `audit_ref`, `id`, `created`; all other bodies byte for byte.
3. `kill_tree` and `port_closed_within` from `tests/e2e/_live.py` instead of `Popen.kill()`.
4. Children run with `RBAC_ENABLED=false` and `PII_REDACTION_ENABLED=false` (reasons in `_balancer_stack.py`).
5. Frozen-clock breaker so `Retry-After` is 10 on both calls.
6. `/__test__/init-db` per test; also resets breaker and counters.
7. `tests/test_two_instance_smoke.py` docstring pointer not added (optional).

## Acceptance Criteria
- [x] AC1 stack up with deadline waits and teardown: module fixture, `test_stack_is_up_and_the_probes_keep_their_contracts`, double run + process check
- [x] AC2 20 cookie-less reach both, cookie pins one: `test_twenty_cookieless_queries_...`
- [x] AC3 limit 5 of 10: `test_a_rate_limit_of_five_admits_five_of_ten_through_the_balancer`
- [x] AC4 status table and forced 503 byte-identical, stays in rotation: `test_status_table_matches_a_direct_call` (10 cases), `test_an_instance_503_arrives_byte_identical_and_it_stays_in_rotation`
- [x] AC5 balancer's own 503 with Retry-After 10 and application/json: `test_both_instances_not_ready_get_the_balancers_own_503`
