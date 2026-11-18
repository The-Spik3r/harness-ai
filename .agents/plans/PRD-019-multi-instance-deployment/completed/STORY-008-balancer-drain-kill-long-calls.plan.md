---
story: STORY-008
prd: PRD-019
slug: balancer-drain-kill-long-calls
title: Balancer test — drain, kill, 100 s calls and SSE keep-alives through both Caddies
type: NEW_CAPABILITY
complexity: large
epic_branch: epic/PRD-019-multi-instance-deployment
created: 2026-11-17
---

# Plan: Drain, kill and long calls through the balancer

## Summary

Extend `tests/test_two_instance_balancer.py` (STORY-007) with three tests on three stacks, all built on `tests/_balancer_stack.py`: DRAIN on the existing module `balancer`; the 100 s calls and the SSE keep-alive case on a new `FrontedBalancer` (a front Caddy running the repo `Caddyfile` per instance); KILL on its own plain `Balancer`. No application code changes. The harness gains `FrontedBalancer`, Caddyfile-derived timing constants, an `all_children()` helper and a stop-then-assert-gone helper.

- Story: `.agents/stories/PRD-019-multi-instance-deployment/STORY-008-balancer-drain-kill-long-calls.md` (AC text lives there)
- PRD sections used: §5 (4-6), §11 (7-10), D4, D6, D8, F2/F3, "Verified (STORY-004)"
- Systems affected: `tests/` only. `docker-compose.lb.yml`, `rolling_restart.sh` and Docker E2E (STORY-009/010) are untouched.

## Design Decisions (binding, from the orchestrator)

1. **Three stacks.** (a) Module `balancer` hosts DRAIN only (pin with `_pin_cookie`, `test_two_instance_balancer.py:168`; `undrain` A and wait until back in rotation in a `finally`). (b) `FrontedBalancer(Balancer)` hosts the 100 s calls + SSE. (c) A plain `Balancer` for KILL, own fixture, never shared.
2. **Wall time.** In the fronted stack the non-streaming `/v1` (100 s), `POST /query` (100 s) and 30 s streaming calls run concurrently in threads, each asserted separately (module pays ~100 s once). **No `slow` marker exists**: there is no `pytest.ini`/`pyproject.toml`; markers are registered in `tests/conftest.py:185-188` (benchmark, e2e, chaos, db only). Do not invent one; the story's "mark if a slow marker exists" is a no-op. Client timeout 180 s (> D6's 150 s, finite); thread `join(200)`.
3. **Drain.** Deadline = `HEALTH_INTERVAL_S * 2` (5 s x 2 = 10 s), read from `deploy/lb/Caddyfile` (`health_interval 5s`) by one helper, measured from the file touch. After it: cookieless requests and a cookie pinned to A never reach A; the in-flight request completes 200 and was still in flight at the touch (stub delay 25 s; A's `/query` counter shows it started).
4. **Kill.** `Balancer.kill_instance(0)` (tree kill); requests keep coming for `HEALTH_INTERVAL_S + 5` s; every one is 200 with latency < `LB_TRY_DURATION_S + 2` s (strictly stronger than "no 5xx after the first interval"). Dial failures are retried for any method (PRD "Verified (STORY-004)"), so GET `/health` and POST `/query` are both safe; nothing is in flight at the kill.
5. **SSE.** `Accept-Encoding: gzip`, lb -> front caddy (gzip on) -> uvicorn. Reuse `tests/e2e/docker_smoke_probe.py:_timed_stream` (107-139) and `keepalive_problems` (238-262): `iter_bytes` decodes gzip incrementally, so each frame is timed when the encoder flushes it; t0 = response headers (the k-th keep-alive is due k x interval after commit, `app/services/v1_sse.py:96` `wait_for_commit`). It matches the whole frame `: keep-alive\n\n`, not a substring. Same constants as `tests/e2e/test_docker_smoke.py:56-57` (10 s, tolerance 2 s) and `minimum=2` (the one at 30 s races the answer, `test_docker_smoke.py:200-201`).
6. **Teardown AC.** After each extra stack stops: every child dead, port closed (`Child.kill` returns `port_closed_within`, `_balancer_stack.py:81-91`); the dead instance in the kill stack must not make `stop()` raise.

## Skills In Use

None apply (`.agents/skills/` holds only `frontend-design`; no UI).

## Patterns to Follow

| Category | Source | What to mirror |
|----------|--------|----------------|
| Fixtures | `test_two_instance_balancer.py:83-98` | `database_url_factory` + `tmp_path_factory.mktemp`, `try: start(); yield; finally: stop()` |
| Per-test state | `test_two_instance_balancer.py:101-109` | children need `init_db()` / `reset_counters()` after conftest's per-test schema drop |
| Cleanup in `finally` | `test_two_instance_balancer.py:395-417` | drain/undrain + `wait_until` back to ready; comments cite PRD-019 |
| Hook | `_balancer_stack.py:186-189` | `_upstream_port(index)` docstring already names STORY-008 |
| Stop | `_balancer_stack.py:297-314` | kill every child, collect failures, raise once |
| Request helper | `test_two_instance_balancer.py:130-148` | `_send` (fresh client, `trust_env=False`; 60 s timeout, so add a `timeout` parameter or a `_send_long`) |
| Docstring | module header | PRD ids, numbered deviations, `_INVARIANTS` tuple at the bottom (update it) |

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `tests/_balancer_stack.py` | UPDATE | `caddyfile_seconds()`, `HEALTH_INTERVAL_S`, `LB_TRY_DURATION_S`; `Child.kill` annotation `-> bool`; `Balancer.all_children()`; `FrontedBalancer`; `ROOT_CADDYFILE` |
| `tests/test_two_instance_balancer.py` | UPDATE | module `balancer` script gains a drain rule; two fixtures; helpers; three tests; docstring + `_INVARIANTS` |

## Tasks

### Task 1: Timing constants from the Caddyfile

- **File**: `tests/_balancer_stack.py`
- **Implement**: `caddyfile_seconds(directive) -> float` reads `deploy/lb/Caddyfile` with `re.search(rf"^\s*{directive}\s+(\d+)s\s*$", text, re.M)` and asserts exactly one match, naming file and directive (`health_interval 5s`, `lb_try_duration 5s`). Module constants `HEALTH_INTERVAL_S`, `LB_TRY_DURATION_S`. Tests import them; no literal 5/10 for these in test code. `DRAIN_DEADLINE_S = HEALTH_INTERVAL_S * 2` lives in the test module.
- **Validate**: `.venv/Scripts/python -c "from tests._balancer_stack import HEALTH_INTERVAL_S as h; print(h)"` prints 5.0

### Task 2: `Balancer.all_children()`, `Child.kill` annotation

- **File**: `tests/_balancer_stack.py`
- **Implement**: `all_children()` returns `[caddy, *instance children, stub]` that exist (the list `stop()` builds at line 303, factored out so `FrontedBalancer` extends it with the fronts). Fix `Child.kill`'s `-> None` (line 81) to `-> bool`; behaviour unchanged. A second `kill()` on a dead child is safe: `_handle.close()` is idempotent, `kill_tree` swallows a missing PID (`tests/e2e/_live.py:120-126`), the port is already closed.
- **Validate**: covered by Task 5.

### Task 3: `FrontedBalancer`

- **File**: `tests/_balancer_stack.py`
- **Implement**: `class FrontedBalancer(Balancer)` with `self.fronts: list` set in `__init__` before any child starts. `_upstream_port(index)`: `front = free_port()`; start `Child(f"front-{'ab'[index]}", [caddy_binary(), "run", "--config", str(ROOT_CADDYFILE), "--adapter", "caddyfile"], caddy_env(front, free_port(), BACKEND_INTERNAL_PORT=str(self.instances[index].port)), self.tmp / f"front-{index}.log", front)`; append to `self.fronts`; `wait_until(lambda: _status(f"http://127.0.0.1:{front}/ready") == 200, 30, "front caddy answering /ready 200", child)` (a 200 proves the instance behind it too); return `front`. `ROOT_CADDYFILE = REPO_ROOT / "Caddyfile"`; `/srv` absent is fine for API paths (the file routes `/ready`, `/query`, `/v1/*` to the backend, lines 5-8, and has `encode gzip` at line 3 and no timeouts, so D6 holds).
  `_upstream_port` runs once per index in `_start` (`_balancer_stack.py:261-262`) after the instances are healthy, so the base needs no change. `all_children()` = base + fronts. `stop()`: kill the fronts first with the same collect-failures loop, set `self.fronts = []`, then call `super().stop()` inside `try/except AssertionError`, and raise once with both failure lists merged. It must stay idempotent and kill everything when one kill raises: `start()`'s failure path calls it (`:178-184`) with `fronts` possibly half-built.
- **Validate**: Task 5 (the long-call test proves the front is in the path through `Content-Encoding: gzip`).

### Task 4: Module fixture script and helpers

- **File**: `tests/test_two_instance_balancer.py`
- **Implement**:
  - `balancer` fixture passes `script={"rules": [{"contains": "drain-slow", "delay_seconds": 25, "content": "ok"}], **DEFAULT_SCRIPT}` (matched only by a prompt with the tag; STORY-007 prompts are unaffected). 25 s > touch (~1 s) + `DRAIN_DEADLINE_S` + probe time (~3 s).
  - `_stop_and_assert_gone(stack)`: `children = stack.all_children(); stack.stop()`, then for each child `assert not c.alive() and port_closed_within(c.port, 5), c.name`. Use it in both new fixtures' `finally` and in the existing `balancer` fixture's `finally` (AC5 "every process is gone").
  - `_prepare(stack)`: for each instance `init_db(); reset_counters()`, after conftest's autouse drop (same reason as `fresh_schema`, `:101-109`).
  - Unique prompts carry the stub tag (`_unique("slow-100")`, `:125`). `contains` matches the last user message; confirm in `stub.log` that `rule=0 delay=100` appears (risk 2).
- **Mirror**: `test_two_instance_balancer.py:83-109`, `:125-148`.

### Task 5: The three tests

- **File**: `tests/test_two_instance_balancer.py`
- **Fixtures** (function scope, each its own stack and tmp dir): `fronted` = `FrontedBalancer(database_url_factory("two_instance_balancer_fronted"), tmp_path_factory.mktemp("fronted"), script={"rules": [{"contains": "slow-100", "delay_seconds": 100, "content": "late"}, {"contains": "slow-30", "delay_seconds": 30, "content": "late"}], **DEFAULT_SCRIPT}, instance_env={"V1_SSE_KEEPALIVE_SECONDS": "10"})`; `killable` = plain `Balancer`. Both: start, `_prepare`, yield, `_stop_and_assert_gone` in `finally`. All stacks share the one libSQL database (`conftest.py:889-905`: the factory returns the same endpoint), so each test inserts its user after the per-test reset.
- **Tests** (append after the last case; update `_INVARIANTS`):
  1. `test_a_request_in_flight_on_a_drained_instance_completes_and_nothing_new_reaches_it(balancer, user)`: `cookie = _pin_cookie(balancer, 0)`; a thread posts `/query` (prompt `drain-slow ...`, that cookie); `wait_until` A's `/query` counter is 1; `t_touch = time.monotonic(); balancer.drain(0)`; deadline loop until `time.monotonic() >= t_touch + DRAIN_DEADLINE_S`; then 10 cookieless and 5 A-pinned `/query` requests, all 200; assert A's `/query` count is still 1 (the in-flight one), B's is 15; assert the thread is still running (it overlapped), then join: 200 and `status == "SUCCESS"`. `finally`: `undrain(0)`, join, `wait_until` a cookieless `GET /health` reaches A again (30 s; the 40-try `_pin_cookie` loop is too fast to outlast a 5 s health tick).
  2. `test_killing_an_instance_fails_no_request_through_the_balancer(killable)`: insert user; `cookie_a = _pin_cookie(killable, 0)`; `killable.kill_instance(0)`; for `HEALTH_INTERVAL_S + 5` s alternate `GET /health` and `POST /query` (unique prompt), the first three with the A cookie; each must be 200 with latency < `LB_TRY_DURATION_S + 2`; collect failures (kind, status, latency) into one message. End: B's `/query` count equals the number of POSTs. Fixture teardown proves `stop()` does not raise with a dead instance.
  3. `test_long_calls_and_sse_keepalives_through_both_caddies(fronted)`: insert user; three threads, each with `httpx.Client(trust_env=False, timeout=180)`: non-streaming `/v1/chat/completions` (`slow-100`), `POST /query` (`slow-100`), and `_timed_stream(fronted.lb_base, token, "slow-30 ...", "gzip")` (`from tests.e2e.docker_smoke_probe import _timed_stream, keepalive_problems`, as `tests/test_docker_smoke_probe.py:22` imports the module). Join all (200 s), keep each result or exception, then assert separately: (a) `/v1` 200 and `choices[0].message.content == "late"`; (b) `/query` 200 and `status == "SUCCESS"`; (c) `not keepalive_problems(timing, 10.0, 2.0, minimum=2)` (constants `_KEEPALIVE_S`, `_TOLERANCE_S`, commented with `test_docker_smoke.py:56-57`), content type `text/event-stream`, `timing["done"]`, and `timing["content_encoding"] == "gzip"` so the gzip hop is proven, not assumed (risk 1). No latency ceiling (`_INVARIANTS`).
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_two_instance_balancer.py` (one pytest at a time).

## End-to-End Tests

- [ ] The three tests are the E2E: two real Caddy layers, real uvicorn, stub. Expected module time: STORY-007's ~3 min local / ~2.5 min CI, plus ~25 s (kill stack boot) + ~130 s (fronted boot + 100 s) + ~30 s (drain) = **about 6 min local, 5 min CI**. That is over the checkpoint's 2-3 min note and unavoidable with a 100 s call; the three slow calls are one concurrent batch.
- [ ] After the run: no `caddy`/`python` child of the test remains (`tasklist`), no background task left.

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_two_instance_balancer.py tests/test_lb_caddyfile.py tests/test_docker_smoke_probe.py
```
`test_lb_caddyfile.py` pins the Caddyfile that Task 1 reads; `test_docker_smoke_probe.py` guards the probe whose helpers are imported. `app/` is untouched (no `test_untouched_app.py`); nothing renamed or removed (no `_DELIBERATELY_SUPERSEDED_TESTS`). Full suite: GitHub CI.

## Acceptance Criteria -> Tasks -> Tests

| AC | Task(s) | Test that proves it |
|----|---------|---------------------|
| AC1 drain: no new request in `health_interval x 2`, in-flight 200 | 1, 4, 5 | `test_a_request_in_flight_on_a_drained_instance_completes_and_nothing_new_reaches_it` |
| AC2 kill: succeed via B within `lb_try_duration`, no 5xx | 1, 5 | `test_killing_an_instance_fails_no_request_through_the_balancer` |
| AC3 100 s `/v1` and `/query` 200, concurrent | 3, 5 | `test_long_calls_and_sse_keepalives_through_both_caddies` (a, b) |
| AC4 SSE keep-alives via both Caddies, gzip | 3, 5 | same test (c) |
| AC5 nothing left, kill does not poison | 2, 3, 4 | `_stop_and_assert_gone` in all three fixtures' teardown |

## Risks and open points

1. **Does Caddy's `encode gzip` compress `text/event-stream`?** Not verified: the docker smoke test records but never asserts `content_encoding`. If the first run shows none, keep the timing asserts, make the gzip assert informational, and tell the orchestrator that "gzip on" is then the Caddyfile's claim, not an observed fact.
2. **Stub tag reaching the stub**: the pipeline may wrap the prompt; if `stub.log` shows `rule=default delay=0`, match by `regex` instead.
3. **Per-test DB reset and several live stacks** share one database. Tests run sequentially; `init_db` each stack after the drop. If `/query` returns 401 for the inserted user, call `insert_user` after `_prepare`.
4. **Windows**: `kill_instance` relies on `taskkill /T` (venv launcher child holds the port, `_balancer_stack.py` header). `stop()` re-kills a dead PID: expected silent.
5. **Wall time** (above) exceeds the checkpoint note; sharing a stack for kill was ruled out by design point 1(c).
6. Drain detection = active health tick (5 s) + up to 3 s `health_timeout`: 10 s leaves 2 s margin. A flake there is a real finding; do not widen the deadline.
