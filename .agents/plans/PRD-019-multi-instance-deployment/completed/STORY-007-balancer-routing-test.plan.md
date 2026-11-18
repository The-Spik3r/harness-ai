---
story: STORY-007
prd: PRD-019
slug: balancer-routing-test
title: Two-instance balancer test — harness, stickiness, limits, status table and 503 pass-through
type: NEW_CAPABILITY
complexity: large
epic_branch: epic/PRD-019-multi-instance-deployment
created: 2026-11-17
---

# Plan: Balancer routing test

## Summary

A reusable process stack (stub + two uvicorn instances + one Caddy running `deploy/lb/Caddyfile` with its upstream line replaced) in `tests/_balancer_stack.py`, a test-only instance launcher `tests/_lb_instance.py` (request counters and breaker hooks, never in `app/`), and `tests/test_two_instance_balancer.py` with the five ACs. STORY-008 imports the same stack and starts its own for the kill case.

- Story: `.agents/stories/PRD-019-multi-instance-deployment/STORY-007-balancer-routing-test.md`
- PRD sections used: §7 F3, §10, §11, D8, D9, §15 "Verified (STORY-004)"; STORY-004 report Findings; STORY-008 story (`STORY-008-balancer-drain-kill-long-calls.md`)
- Systems affected: tests only. `tests/test_two_instance_smoke.py` gets a docstring pointer at most.

## Design Decisions

- **Where the harness lives**: `tests/_balancer_stack.py` (STORY-008 needs it too). The test module keeps fixtures, helpers and cases.
- **`Balancer` class** (`start()`, `stop()`; no context manager so a fixture owns it). Ctor kwargs for STORY-008: `script` (stub JSON dict, default one `default` reply), `instance_env` (extra child env, e.g. `V1_SSE_KEEPALIVE_SECONDS`), `tmp`. Attributes: `lb_base`; `instances[i]` with `.base`, `.port`, `.drain_file`, `.counters()`, `.reset_counters()`, `.force_breaker_open()`, `.reset_breaker()`, `.init_db()`; methods `drain(i)`, `undrain(i)`, `kill_instance(i)`. STORY-008 adds the per-instance "front Caddy" (repo `Caddyfile`, `BACKEND_INTERNAL_PORT`) by extending an `_upstream_port(i)` hook; not built here.
- **Child lifecycle.** Each child is a `Popen` with stdout+stderr to a log file under tmp (never a pipe that can fill), env pinned like `tests/test_two_instance_smoke.py:700-707` (`child_db_env(url)`, `TURSO_AUTH_TOKEN=""`, `PYTHONPATH`). Order: stub (`--port <free> --script <tmp json>`, wait for its `listening on` line in the log), both instances in parallel, wait each `/health` 200 then `/ready` 200, then caddy, wait `GET /ready` 200 through it. All waits are deadline loops polling a condition (instance boot 180 s: `tests/e2e/_live.py:276-290`), failing with `"<child> did not ...; log tail:\n<last 40 lines>"`. `start()` wraps itself in try/except that calls `stop()` and re-raises, so a failed start leaves nothing.
- **Kill needs more than `Popen.kill()` on Windows (deviation from point 1; state it in the report).** A venv `python.exe` is a launcher whose real interpreter is a child (`tests/e2e/_live.py:75-80`), so `kill()` leaves the real uvicorn holding its port and a DB client. Kill = `kill_tree` (`tests/e2e/_live.py:113-130`: `taskkill /F /T` on nt, `os.killpg` on POSIX, which needs `start_new_session=True` on the Popen), then `wait(timeout)` with `Popen.kill()` as fallback, then assert `port_closed_within(port, 10)`. Import both from `tests.e2e._live` (light: `httpx`, `pytest`, `tests.conftest`); copy them only if that import proves heavy. `kill_instance(i)` is the same call (STORY-008's SIGKILL case).
- **Caddyfile substitution**: read `deploy/lb/Caddyfile`, assert `text.count(_UPSTREAM_LINE) == 1` (constant restated from `tests/test_lb_caddyfile.py:49`), replace it with `reverse_proxy 127.0.0.1:<a> 127.0.0.1:<b> {`, assert the result differs from the original in that one line only, write LF to tmp, run `caddy run --config <f> --adapter caddyfile` with `caddy_env(lb_port, free_port())` (`tests/_caddy.py:48-60`; env `PORT`, `LB_COOKIE_SECRET`, `CADDY_ADMIN`), binary from `caddy_binary()` (`tests/_caddy.py:32`; skips locally, fails under `HARNESS_REQUIRE_CADDY=1`). Instances take `--port` directly; `PORT` is the balancer port.
- **Instance launcher** `tests/_lb_instance.py` (`python tests/_lb_instance.py --port N`, repo root on `sys.path`): imports `app.main.app`, then
  (a) `app.add_middleware(...)` with a pure-ASGI class: for `scope["type"] == "http"` and a path not under `/__test__/`, `counts[path] += 1`, then delegate (event loop is single-threaded, no lock);
  (b) routes under `/__test__/`: `GET counters`, `POST reset-counters`, `POST init-db` (`database.init_db()`), `POST breaker/open`, `POST breaker/reset`. `breaker/open` installs a **frozen-clock** breaker so `Retry-After` is identical for the direct and the balanced call (`_retry_after` is `ceil(open_until - now)`, `app/services/circuit_breaker.py:150`; a real clock can tick over between two sends): `database._storage_breaker = CircuitBreaker("storage", database._BREAKER_FAILURE_THRESHOLD, database._BREAKER_OPEN_SECONDS, clock=lambda: 0.0, probe=database._probe_fresh_client, on_transition=database._count_breaker_open)`, then `.force_open(10)` (`circuit_breaker.py:281`; 10 equals the shipped `_BREAKER_OPEN_SECONDS`). `breaker/reset` assigns `database._new_storage_breaker()` (`app/db/database.py:317`, as `tests/conftest.py:706-723` does per test). The module global is read at call time (`database.py:1234`).
  Then `uvicorn.run(app, host="127.0.0.1", port=N, log_level="warning")`. No census guard scans `tests/` helpers: the breaker/retry censuses read only `app/db/database.py` (`tests/test_db_resilience_breaker.py:91`, `test_db_resilience_retry.py:701`) and nothing under `app/` changes. Verify by running those two files.
- **Child env**: `DRAIN_FILE=<tmp>/drain-<i>` (absolute, `app/config.py:612`), `OPENROUTER_BASE_URL=http://127.0.0.1:<stub>/v1`, `OPENROUTER_API_KEY`, `ADMIN_TOKEN`, `AUDIT_BUFFER_DIR=<tmp>/audit-<i>` (the lifespan opens a journal, default `./var/audit-buffer`; `tests/conftest.py:746-757` isolates only the parent), `PII_REDACTION_ENABLED=false` (not under test; skips the Presidio boot, `app/services/pii_redactor.py:149`), `RBAC_ENABLED=false`. Why RBAC off: the module fixture starts before the first per-test reset, and the lifespan's `authz.check_bootstrap()` (`app/services/authz.py:137-152`) refuses an empty `users` table when RBAC is on. Authentication (401) is unaffected: RBAC only gates authorization (`authz.py:160`).
- **Schema reset**: conftest drops every table before each `db` test (`tests/conftest.py:628-700`); `database_url_factory` makes the module `db` (`conftest.py:122-124,889-912`). The DROP runs server-side, so each child's client stays valid. Restore per test with an autouse fixture that POSTs `/__test__/init-db` to both children (mirrors `fresh_schema`, `tests/test_two_instance_smoke.py:809-822`, which proved the pattern; the app also recovers a dead stream, `database.py:252`). The parent creates users with `insert_user(User(user_id=..., role="user", token_hash=hash_token(tok)))` (`:827-834`) and limits with `set_user_limits` (`database.py:2570`) in the test body (the test is `db`, so the parent's `settings.DATABASE_URL` is the endpoint). Prove it by running the module twice in a row.
- **Status contracts in reality: there is no 429.** `/query` answers a usage-limit refusal `200` + `status: BLOCKED` + `reason`/`limit`/`actual`/`maximum`/`resets_at` (`app/models/schemas.py:150-162`, D5), and `/v1` maps it to `403 permission_error` (`app/services/v1_translate.py:683-686`). The table asserts those. Use the **token budget** for the limit rows (`set_user_limits(user, token_budget_daily=1)` plus one burning success on a second user's budget, then refusals): `actual` is tokens used, stable across refusals, whereas the per-minute `actual` grows with every attempt. Model on `tests/test_two_instance_smoke.py:2105-2140`.
- **Comparison rule**: status and `Retry-After` exact; body bytes exact for every non-success case. Success bodies differ per call by design (`audit_id`, `audit_ref`; on `/v1` also `id`, `created`, `harness.audit_id`): parse JSON, blank that closed key set, compare the rest. Every send uses a unique prompt (the duplicate gate would otherwise turn the second into a 400 `DUPLICATE_REQUEST`).
- **Pinning**: `pin_cookie(i)` sends cookie-less `GET /health` through the balancer until `counters()` shows instance `i` got it (max 40 tries, then fail), returning `harness_lb=<hex>` from `Set-Cookie`. Send the cookie as an explicit header from a **fresh `httpx.Client(trust_env=False)` per request** (a jar would make "cookie-less" requests sticky). A 503 may carry two `Set-Cookie` lines (STORY-004 report (a)): parse, never assert exactly one.
- **Forced-503 race**: the shipped 5 s `/ready` probe sees an open breaker, so a probe inside the window would take A out of rotation. The window is a few ms, so loop up to 3 times: open A, send both calls with A's cookie, check A's `/query` and `/v1/chat/completions` counters grew (else reset and retry), compare with direct. After `breaker/reset`, wait (deadline 20 s) until a request with A's cookie increments A again ("stays in rotation").
- **Waits**: deadline loops only; the one clock wait is the minute-boundary margin before the rate test (copy `_fresh_rate_window`, `tests/test_two_instance_smoke.py:1964-1982`).

## Skills In Use

None (`.agents/skills` holds only `frontend-design`).

## Patterns to Follow

| Category | Source | What to mirror |
|----------|--------|----------------|
| Child env, URL | `tests/test_two_instance_smoke.py:700-707,786-806` | `child_db_env`, blank Turso token, module-scoped `database_url_factory` |
| Process lifecycle | `tests/e2e/_live.py:241-300` | stub start, `/health` deadline loop, stop, port released |
| Restated contract | `tests/test_lb_caddyfile.py:44-58` | 503 bodies and upstream line restated, not derived |

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `tests/_balancer_stack.py` | CREATE | `Balancer`, child wrappers, kill helper, deadline loops, log tails |
| `tests/_lb_instance.py` | CREATE | test-only launcher: counters, `/__test__/*`, uvicorn |
| `tests/test_two_instance_balancer.py` | CREATE | module fixture, per-test schema fixture, the cases |
| `tests/test_two_instance_smoke.py` | UPDATE (optional) | one docstring sentence pointing at the sibling module; nothing else |

## Tasks

### Task 1: `tests/_lb_instance.py`
- **Implement**: as in Design (middleware, `/__test__/*`, frozen-clock breaker, `uvicorn.run`). Never imported by `app/`.
- **Validate**: starts and answers `/health` and `/__test__/counters` (exercised by Task 3).

### Task 2: `tests/_balancer_stack.py`
- **Implement**: `Balancer` per Design; log-tail helper; one `_wait(condition, deadline, what, child)`; HTTP via `httpx` with `trust_env=False`; ports from `free_port()`. `stop()` is idempotent: caddy, then instances, then stub; every kill is attempted before any failure is raised.
- **Mirror**: `tests/e2e/_live.py:57-98,241-300`.

### Task 3: `tests/test_two_instance_balancer.py`
Module docstring: why a sibling (D8), the harness shape, the invariants (as `_INVARIANTS` at the bottom of the smoke file). Fixtures: module `balancer(database_url_factory, tmp_path_factory)` (starts, yields, stops in `finally`); autouse `fresh_schema(balancer)`; a `user` fixture. Cases, in this order (the drain case last, so its wait does not delay the others):
1. `test_stack_is_up_and_the_probes_keep_their_contracts` (AC1, AC5 tail): LB `/health` is `{"status":"ok"}`; LB `/ready` is `200 {"status":"ready","breaker":"closed"}` with `Cache-Control: no-store`.
2. `test_twenty_cookieless_queries_reach_both_instances_and_the_cookie_pins_one` (AC2): reset counters; 20 unique `/query`; both `/query` counts > 0, sum 20; cookie from the first response; 10 more with it: one instance +10, the other +0.
3. `test_a_rate_limit_of_five_admits_five_of_ten_through_the_balancer` (AC3): limit 5, margin wait, 10 requests alternating A and B cookies (deterministic split), exactly 5 `SUCCESS` and 5 refusals with `limit == "requests"`; each instance counted 5.
4. `test_status_table_matches_a_direct_call` (AC4, parametrized): `/query`: success, no token 401, bad token 401, empty body 422, budget refusal; `/v1/chat/completions`: success, no token 401, bad token 401, a 400 (empty `messages`; confirm which request yields 400 in `app/routers/v1.py` and its error handlers), budget refusal 403. Each goes to A directly and through the balancer with A's cookie, compared per the rule, and A's counter must have grown for the balanced send.
5. `test_an_instance_503_arrives_byte_identical_and_it_stays_in_rotation` (AC4): forced-503 loop, `/query` and `/v1/chat/completions`, `Retry-After: 10` equal; then reset and A is selected again.
6. `test_both_instances_not_ready_get_the_balancers_own_503` (AC5, last): touch both drain files; poll `GET /health` through the LB (deadline 40 s, each poll can take 5 s) until the body is `{"detail":"Service unavailable"}`; then `POST /query` and `POST /v1/chat/completions` give 503, `Retry-After: 10`, `Content-Type: application/json` (asserted live; STORY-005 left it to this story) and the exact bodies restated from `tests/test_lb_caddyfile.py:52-57`. `finally`: remove both files, poll LB `/ready` to 200 (deadline 30 s).
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_two_instance_balancer.py`

## End-to-End Tests

- [ ] The module is the E2E (real uvicorn x2, stub, caddy). Run it twice back to back (proves schema restore and port release); afterwards no `python`, `caddy` process or listening test port remains (`tasklist`, `netstat`).
- [ ] A forced failed start (scratch run, wrong stub script path) leaves no child behind; record the wall time (target < 2 min).

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
CADDY_BIN=<local caddy.exe, see brief> PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_two_instance_balancer.py tests/test_lb_caddyfile.py tests/test_caddy_pin.py tests/test_db_resilience_breaker.py tests/test_db_resilience_retry.py tests/test_conftest_fixtures.py
```
Add `tests/test_untouched_app.py` only if anything under `app/` changes (none planned).

## Acceptance Criteria → Tasks → Tests

| AC | Task(s) | Test that proves it |
|----|---------|---------------------|
| AC1 stack up, deadline waits, teardown | 2, 3 | module fixture + `test_stack_is_up_and_the_probes_keep_their_contracts`; E2E double run and process check |
| AC2 20 cookie-less reach both; cookie pins one | 1, 3 | `test_twenty_cookieless_queries_reach_both_instances_and_the_cookie_pins_one` |
| AC3 limit 5 of 10 | 3 | `test_a_rate_limit_of_five_admits_five_of_ten_through_the_balancer` |
| AC4 status table, forced 503, still selected | 1, 3 | `test_status_table_matches_a_direct_call`, `test_an_instance_503_arrives_byte_identical_and_it_stays_in_rotation` |
| AC5 balancer's own 503; probes while ready | 3 | `test_both_instances_not_ready_get_the_balancers_own_503`, `test_stack_is_up_...` |

Plus: all tasks completed, validation passes, follows existing patterns.
