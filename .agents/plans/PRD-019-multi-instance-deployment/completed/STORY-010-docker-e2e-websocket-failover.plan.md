---
story: STORY-010
prd: PRD-019
slug: docker-e2e-websocket-failover
title: Opt-in Docker E2E — websocket stickiness, kill and reconnect, rolling restart
type: NEW_CAPABILITY
complexity: medium
epic_branch: epic/PRD-019-multi-instance-deployment
created: 2026-11-17
---

# Plan: Docker E2E for the balanced stack

## Summary

An opt-in module `tests/e2e/test_lb_docker.py` runs the real image twice behind the shipped `docker-compose.lb.yml`, laid over by `tests/e2e/docker/compose.lb-e2e.yml` (project `harness-lb-e2e`, throwaway libSQL, a stub inside each instance container). It proves: websocket 101 with stickiness across reconnects, kill-and-failover with the cookie re-set, and `scripts/rolling_restart.sh` under a `POST /query` loop. `rolling_restart.sh` gains a repeatable `-f` and a `-p`, backward compatible.

- Story: `.agents/stories/PRD-019-multi-instance-deployment/STORY-010-docker-e2e-websocket-failover.md`
- PRD sections used: §5 (US 2-4), §6.1, §6.2, §11, D1, D7, D8; STORY-004 report (cookie findings, lines 45-60, 147)
- Systems affected: tests/e2e, `scripts/rolling_restart.sh` and its test. No `app/`, no `chat_ui/`; shipped compose and Caddyfile untouched.

## Design Decisions (orchestrator's binding points, plus what the code showed)

1. **Stub inside each instance** (a recreated container brings its own; `compose.smoke.yml:11-14,59-66` shares a netns, which breaks on `--force-recreate`). The overlay sets `command: ["sh","-c", ...]` that backgrounds `python scripts/stub_openrouter.py --host 127.0.0.1 --port 9100 --script tests/e2e/scripts/docker_smoke.json >/tmp/stub.log 2>&1 &` and then runs the image CMD (`Dockerfile:92-95`) verbatim. `--script` is **required** (`scripts/stub_openrouter.py:540`); `docker_smoke.json` (default answer; its rules only match SMOKE-* prompts) is the file to use and is already in the image (the smoke uses it). Escape `$` as `$$` in the YAML (`${BACKEND_INTERNAL_PORT}`, `${HOST:-0.0.0.0}` are read inside the container). Restating the CMD can drift, so Task 4 asserts the overlay command ends with the Dockerfile CMD text. `OPENROUTER_BASE_URL=http://127.0.0.1:9100/v1` stays loopback (`app/config.py:97`).
2. **Overlay mechanics.** `docker compose -p harness-lb-e2e -f docker-compose.lb.yml -f tests/e2e/docker/compose.lb-e2e.yml`. For `harness-a` and `harness-b` (a YAML anchor inside the overlay; the shipped file is not touched): `image: harness-lb-e2e:local`, `pull_policy: never`, `build: !reset null` (so `up --force-recreate` never rebuilds), `env_file: !reset []` (no developer `.env`), the `command` above, and an `environment` mapping (merges by key with the base list, `docker-compose.lb.yml:28-30`): `DATABASE_URL: http://libsql:8080`, `TURSO_AUTH_TOKEN: ""`, `OPENROUTER_BASE_URL`, `OPENROUTER_API_KEY: e2e-stub-key`, `ADMIN_TOKEN: ${HARNESS_LB_E2E_ADMIN_TOKEN:?...}`, `MODEL_ALLOWLIST: openai/gpt-4o`, `USAGE_REQUESTS_PER_MINUTE: "*=6000"` (the loop), `PIPELINE_MAX_WORKERS: "4"`. Add `libsql` as in `compose.smoke.yml:25-28`, and `depends_on: [libsql]` on both instances. `lb` keeps the shipped pinned image and Caddyfile mount. The implementer verifies `!reset`/`!override`, and that `config` succeeds when no `.env` exists, with `docker compose ... config --quiet` (exit code only; never print `config` output, it can hold secrets). If `build: !reset null` is rejected, try `!reset {}`.
3. **Port (D7).** Build the image once with the default `PORT=8000` and set `PORT=8000` explicitly in the subprocess env (a developer's shell `PORT` must not leak). The overlay remaps **only the host side**: `lb.ports: !override ["127.0.0.1:${HARNESS_LB_E2E_PORT:?...}:8000"]`. Why this keeps D7: the constraint exists because the *browser* derives the websocket URL from the baked `REFLEX_API_URL` port (PRD §6.1, `Dockerfile:36`). The E2E client builds its own URLs, so the baked port is never exercised, while in-network `lb` and instances keep one `$PORT` (8000, as in the shipped file). No rebuild per run, no clash with a developer stack on 8000, loopback bind only. The host port comes from `_live.free_port()` (`tests/e2e/_live.py:66`).
4. **Instance identification, not log scraping.** Reflex runs Granian at a low log level and the in-container `Caddyfile:7` has no access log, so logs would not show the `/_event` upgrade. Use the kernel's view: while the test client holds the websocket open, count ESTABLISHED sockets whose **local** port is 8001 (`BACKEND_INTERNAL_PORT`) from `/proc/net/tcp` inside each container (`docker compose exec -T <svc> python -c ...`; hex port `1F41`, state `01`). The Caddy-to-backend leg of a proxied websocket is one such connection for its lifetime. Helper `_backend_conns(svc)`; take a baseline just before connecting; "the instance serving the socket" is the one whose count rises by 1 within a deadline loop (10 s, poll 0.5 s) while the other stays at baseline. If keep-alive connections make that noisy, assert `>= base+1` on the pinned side and `== base` on the other. Identity is the service name, which is also what `kill` needs.
5. **Cookie facts (STORY-004 report:46-60,147).** `harness_lb=<64 hex>`, `Path=/; HttpOnly; SameSite=Lax`, no `Secure`; cookie-less requests spread randomly; a valid cookie is replayed with no new `Set-Cookie`; a dead pinned upstream gives a 0.25 s dial retry and the survivor answers with a NEW `Set-Cookie`. AC3 asserts that re-set (new value differs from the old). Get the first cookie from `GET /` through `lb`. Websocket: `ws://127.0.0.1:<host port>/_event/?EIO=4&transport=websocket&token=<uuid4>` with `additional_headers={"Cookie": "harness_lb=..."}`, `websockets.asyncio.client.connect(..., open_timeout=15)` under `asyncio.run`; assert the handshake `response.status_code == 101` (`websockets` ships with `uvicorn[standard]`, `requirements.txt:2`). One unique token per connection.
6. **Failover reconnect.** `docker compose kill -s SIGKILL <pinned>`, then retry the upgrade with the old cookie in a deadline loop (20 s): assert 101, the other instance's backend count rises, and a plain `GET /` with the old cookie returns a `Set-Cookie` that differs from the old one. Then `up -d --no-deps <svc>` and wait for `/ready` 200 through exec, because `rolling_restart.sh` refuses to start when an instance is not ready (exit 2).
7. **Rolling restart under load.** Run the script with `-f docker-compose.lb.yml -f tests/e2e/docker/compose.lb-e2e.yml -p harness-lb-e2e`, `DRAIN_SECONDS=3`, cwd = repo root, the same env. Value justified: the stub answers `/query` in milliseconds, so the drain window only has to exceed the longest call; 3 s is margin. The script sleeps `health_interval*2 + DRAIN` = 5*2+3 = 13 s per instance (interval parsed from `deploy/lb/Caddyfile`, `rolling_restart.sh:103`). Two replacement boots (spaCy, image start period 60 s) dominate; expect 2-3 min. A loop thread posts `/query` through `lb` every ~0.2 s with a unique prompt (`SMOKE-QUERY <nonce>-<n>`; the duplicate checker spans requests, `tests/e2e/docker_smoke_probe.py:20`) and the user's Bearer token (as `docker_smoke_probe.py:184-188`), records `(offset, status or exception)`, stops via `threading.Event` once the script exits. Assert script rc 0, every status 200 (message lists the first failures with status and time), and at least ~50 calls were made (a silently dead loop must not pass).

## Skills In Use

None apply (`.agents/skills/` holds only `frontend-design`; story `skills: []`).

## Patterns to Follow

| Category | Source | What to mirror |
|----------|--------|----------------|
| Opt-in module + teardown | `tests/e2e/test_docker_smoke.py:48-50,81-127` | `pytestmark = pytest.mark.e2e`; `HARNESS_E2E_DOCKER=1` and `docker info` guard; module fixture with `down -v` in `finally`, logs saved to tmp first; `_compose` helper; `MSYS_NO_PATHCONV=1` |
| Skip without `--run-e2e` | `tests/conftest.py:193-228` | automatic via the marker |
| User bootstrap | `test_docker_smoke.py:96-118`, `tests/e2e/_live.py:186` | create the user with `compose run --rm --no-deps -T harness-a python scripts/manage_users.py ...` before the instances start (RBAC bootstrap), retried 30 s while libsql starts; args after the service replace the overlay `command` |
| Overlay header comments | `tests/e2e/docker/compose.smoke.yml:1-22` | one comment per decision |
| Script static and shim tests | `tests/test_rolling_restart_script.py:92-147,149-190` | text assertions; fake `docker` shim logging to `calls.log` |

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `tests/e2e/docker/compose.lb-e2e.yml` | CREATE | overlay (Design 1-3) |
| `tests/e2e/test_lb_docker.py` | CREATE | the E2E |
| `scripts/rolling_restart.sh` | UPDATE | repeatable `-f`, new `-p` |
| `tests/test_rolling_restart_script.py` | UPDATE | static + shim tests for both flags |
| `tests/test_lb_e2e_overlay.py` | CREATE | no-Docker guard (runs in CI): overlay parses, instances share the local image, `env_file` reset, command tail equals the Dockerfile CMD, shipped `docker-compose.lb.yml` carries no test-only keys. Use text assertions unless PyYAML is already a dependency |

## Tasks (in order)

### Task 1: `rolling_restart.sh` flags
- **File**: `scripts/rolling_restart.sh` (`FILE=` :59, `usage`/`parse_args` :68-82, header usage :16-19)
- **Implement**: replace `FILE` with `FILES=()` (default to `"$ROOT/docker-compose.lb.yml"` when no `-f` is given, so no-flag and single `-f` behave as now) and `PROJECT=""`. `-f` appends; `-p` sets (a repeated `-p` or a missing value is a usage error, exit 1). `COMPOSE=(docker compose)`, then `-p "$PROJECT"` when set, then each `-f`. Update the usage text and header (every file reaches `docker compose`; relative paths resolve from the caller's cwd).
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_rolling_restart_script.py`

### Task 2: script tests
- **File**: `tests/test_rolling_restart_script.py`
- **Implement**: the shim's `if [ "$1" = "-f" ]; then shift 2; fi` (:150) skips one pair: make it loop over `-f X` and `-p X`. New tests: two `-f` plus `-p proj` reach every logged compose call as `-p proj -f a -f b`; `-p` without a value and a repeated `-p` exit 1; no flags still targets `docker-compose.lb.yml`; static test that usage/header mention `-p`. The existing assertion at :274 stays valid; add a comment citing PRD-019 STORY-010 where touched.
- **Validate**: same pytest.

### Task 3: overlay and E2E module
- **Files**: `tests/e2e/docker/compose.lb-e2e.yml`, `tests/e2e/test_lb_docker.py`
- **Fixture** `stack` (module): skip unless `HARNESS_E2E_DOCKER=1`; `docker info` check; env = `{**os.environ, MSYS_NO_PATHCONV: "1", PORT: "8000", HARNESS_LB_E2E_PORT: <free>, LB_COOKIE_SECRET: token_hex(16), HARNESS_LB_E2E_ADMIN_TOKEN: <random>}`. In `try`: `down -v --remove-orphans` (leftovers), `docker build -t harness-lb-e2e:local .` (cwd repo, timeout 1800), `up -d libsql`, create user, `up -d --wait --wait-timeout 300` (`service_healthy`), then poll `GET /ready` through `lb` until 200 (240 s deadline; the balancer's first health check can take up to 5 s). In `finally`: save `logs --no-color --tail 300` to tmp and print the path (never print env or `config`), then `down -v --remove-orphans` with `check=False`, then list `ps -aq` and `docker volume ls -q --filter name=harness-lb-e2e` and print a warning if either is non-empty. Every subprocess has a timeout, every wait a monotonic deadline.
- **Tests, in file order** (state flows between them; say so in the module docstring):
  1. `test_stack_comes_up_healthy` (AC1): both instances healthy, `lb` `/health` and `/ready` 200 from the host.
  2. `test_websocket_upgrade_is_sticky_across_reconnects` (AC2): one `GET /` for the cookie; three sequential connects (101, identify per Design 4, close), plus a fourth held open while a second connect lands on the same instance. All identical.
  3. `test_failover_to_the_other_instance_and_cookie_reset` (AC3): Design 6.
  4. `test_rolling_restart_script_under_query_loop` (AC4): Design 7; afterwards both instances `/ready` 200.
- **Mirror**: `tests/e2e/test_docker_smoke.py:62-127`.
- **Validate** (Docker, ~8 min with the build): `HARNESS_E2E_DOCKER=1 PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/e2e/test_lb_docker.py -m e2e --run-e2e -v -s`. Without the flags it is collected and skipped.

### Task 4: static overlay guard
- **File**: `tests/test_lb_e2e_overlay.py`, checks as listed in Files to Change.

## End-to-End Tests
- [ ] Task 3's four tests against the real image (Docker 29.7.2 / Compose 5.5.1 are available locally).
- [ ] Afterwards `docker ps -a --filter name=harness-lb-e2e` and `docker volume ls --filter name=harness-lb-e2e` are empty (AC5); `harness-libsql-dev` and other projects untouched.
- [ ] `docker compose -p harness-lb-e2e -f docker-compose.lb.yml -f tests/e2e/docker/compose.lb-e2e.yml config --quiet` exits 0 with the env vars set, with and without a `.env`.

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_rolling_restart_script.py tests/test_lb_e2e_overlay.py tests/e2e/test_lb_docker.py
```
No `app/` file is touched, so `test_untouched_app.py` is not needed. Run the Docker E2E separately with the flags above; one pytest at a time.

## Acceptance Criteria → Tasks → Tests

| AC | Task(s) | Test that proves it |
|----|---------|---------------------|
| AC1 own project, skip without `--run-e2e`, `service_healthy` | 3, 4 | `test_stack_comes_up_healthy`; marker skip; `tests/test_lb_e2e_overlay.py` |
| AC2 101 and same instance across reconnects | 3 | `test_websocket_upgrade_is_sticky_across_reconnects` |
| AC3 kill, reconnect on the other, cookie re-set | 3 | `test_failover_to_the_other_instance_and_cookie_reset` |
| AC4 rolling restart rc 0, no loop failure | 1, 2, 3 | `test_rolling_restart_script_under_query_loop`; flag tests in `tests/test_rolling_restart_script.py` |
| AC5 `down -v` on teardown | 3 | fixture `finally` plus its leftovers check |

## Risks
- `!reset`/`!override` and the no-`.env` case: verify with `config --quiet` first; keep the overlay minimal.
- `/proc/net/tcp` counts may be noisy (Caddy keep-alives): baseline diff plus deadline loop (Design 4).
- Reflex may check `Origin` on the upgrade: if refused, send `Origin: http://127.0.0.1:<port>`.
- Boot time (spaCy) dominates; deadlines are 240-300 s; total about 8 min, opt-in only.
