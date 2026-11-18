---
id: PRD-019
slug: multi-instance-deployment
title: Multi-Instance Deployment — Load Balancer, Health Checks and Websocket Session Affinity
status: in-progress
base_branch: main
epic_branch: epic/PRD-019-multi-instance-deployment
created: 2026-11-16
updated: 2026-11-17
---

## 1. Executive Summary

PRD-007 made several instances able to share one Turso database, and `tests/test_two_instance_smoke.py` proves it with two real processes. The deployment topology was never built. [docs/deployment.md:39-44](../../../docs/deployment.md) says so in two bullets: there is **no load balancer or health-check configuration**, and there is **no Reflex websocket session affinity**, so "placing instances behind a round-robin balancer without sticky sessions is not a supported configuration today". It ends: "Treat multi-instance as *unblocked*, not *delivered*." [docs/roadmap.md:33](../../../docs/roadmap.md) lists affinity as an open resilience item.

What exists today is one container per deployment. Inside it, Caddy listens on `$PORT`, serves the static Reflex export from `/srv`, and proxies the `@backend_routes` matcher to `reflex run --backend-only` on `BACKEND_INTERNAL_PORT=8001` ([Caddyfile](../../../Caddyfile), [Dockerfile:70-87](../../../Dockerfile)). The only probe is `GET /health`, which returns `{"status": "ok"}` and checks nothing ([app/main.py:39-41](../../../app/main.py)). The chat UI keeps per-tab state in the Reflex state manager of the process holding the tab's websocket. That includes `ChatState._token`, the signed-in credential ([chat_ui/chat_ui/state.py:244](../../../chat_ui/chat_ui/state.py)). The pinned Reflex `0.9.6.post1` defaults to the **disk** state manager, which keeps that state in the container's own `.states/` directory. A tab that reconnects to a different instance arrives with no state and sees the sign-in gate.

This PRD ships the topology. It adds a balancer Caddy in front of N unchanged copies of the image, with cookie-based sticky sessions for the chat websocket (D1). It splits liveness (`/health`, unchanged) from a new readiness probe (`/ready`) that reflects database reachability and a drain flag (D3, D4). It sets timeouts that can carry a 120-second upstream call and a `/v1` keep-alive stream through two proxies (D6), and documents a rolling restart. A new two-instance smoke test sends `/query`, `/v1` and drain traffic through a real balancer process (D8). **MVP goal:** run `docker compose -f docker-compose.lb.yml up` with two instances. A chat stays on its instance across websocket reconnects. A drained instance stops receiving new requests within one health interval, without failing any in-flight request. A killed instance costs its chat users one sign-in, and their transcripts survive. A 30-second `/v1` stream delivers every keep-alive through both Caddies.

## 2. Mission

Make "several instances behind a balancer" a configuration the repository ships, tests and documents, not one an operator has to work out.

Core principles:

- **No new hard dependency.** The database is the only shared infrastructure today. Affinity is solved at the balancer, not by adding Redis (D1, D2).
- **Liveness is not readiness.** `/health` keeps its exact contract and checks nothing. `/ready` answers "can this instance serve a request now?", which in this system means "can it reach the database?" (D3).
- **Drain before kill.** The image stops with `SIGKILL` ([Dockerfile:76-78](../../../Dockerfile)), so a graceful shutdown cannot be relied on. An instance leaves the rotation first and is stopped afterwards (D4).
- **Say what the user sees.** Sticky sessions have a cost when an instance dies. This PRD states that cost (one sign-in, no lost transcript) and tests for it.
- **Single instance unchanged.** `docker-compose.yml`, the in-container Caddyfile's routing and the image's start command keep working exactly as now. The balancer is an addition.

## 3. Target Users

**Platform Operator.** Runs the harness for a team and wants a second instance for capacity and for restarts without downtime. Needs a compose file that works on the first run, probe endpoints an orchestrator can use, a restart procedure that drops no requests, and timeout numbers that come from the settings.

**Chat UI user.** Signs in with a token and chats. Should not notice that there are two instances, apart from one sign-in when the instance holding their tab dies. Their chats are in the database and reopen.

**Integrating Developer (`/v1`, `POST /query`).** Points an OpenAI SDK, Aider or OpenCode at the balancer. Needs long non-streaming calls (up to `OPENROUTER_TIMEOUT_SECONDS`) and buffered SSE streams to survive two proxy hops, and usage limits that hold across instances (already true, PRD-013).

**PRD-018 (database resilience, done, merged in #27).** Landed before this PRD. It adds one process-local breaker (`closed | open | half_open`), `StorageUnavailableError` and 503 + `Retry-After` on every ingress. `/ready` reads that breaker through `database.storage_status()`, never adds to its failure count, and keeps the 503s it produces intact on their way through the balancer (D5, D9).

## 4. MVP Scope

### In Scope

**Readiness and liveness (`app/main.py`, `app/db/database.py`)**
- [ ] `GET /health` unchanged: `{"status": "ok"}`, no I/O (D3)
- [ ] `GET /ready`: 200 `{"status": "ready", "breaker": "closed"}`; 503 `{"status": "not_ready", "reason": "draining" | "breaker_open" | "database_unreachable" | "database_auth"}`. `Retry-After` is set on `breaker_open` (D3, D5)
- [ ] `database.check_ready()`, a runtime twin of `check_database_reachable()`. It reads `storage_status().breaker.state` first and sends its own `SELECT 1` only while the breaker is `closed`. The statement runs outside `_unit_of_work`: it is never retried, it is never a breaker sample, and a success never closes the breaker. At most one probe is in flight per process. The function returns a classification and raises nothing (D5)
- [ ] Drain flag: `/ready` returns 503 `draining` while the file named by `DRAIN_FILE` exists. Every other route is unaffected (D4)
- [ ] `/ready` added to the in-container Caddyfile's `@backend_routes` and to `EXPECTED_MATCHER` in `tests/test_caddyfile_routes.py`. The reserved-route test learns it

**Balancer (`deploy/lb/Caddyfile`, `docker-compose.lb.yml`)**
- [ ] Caddy balancer listening on `$PORT`, proxying every path to two named instance services (D2, D7)
- [ ] `lb_policy cookie` with a secret from `LB_COOKIE_SECRET` (D1)
- [ ] Active health checks on `/ready` (interval 5 s, timeout 3 s), plus passive health. A request on a dead upstream is retried on another for `lb_try_duration` (D4)
- [ ] Timeouts derived from `OPENROUTER_TIMEOUT_SECONDS`. No `encode` at the balancer (D6)
- [ ] An instance's 503s pass through unchanged, `Retry-After` included. Passive health has no `unhealthy_status`, so PRD-018's 503s never mark an instance down. Requests are not replayed on another upstream once they have been sent (D9)
- [ ] With no healthy upstream, the balancer itself answers 503 with `Retry-After: 10` and a fixed body: an OpenAI error object on `/v1/*`, `{"detail": …}` elsewhere. The front door keeps PRD-018 D8's contract even when every instance is out of rotation (D9)
- [ ] Both instances mount one shared named volume for PRD-018's `AUDIT_BUFFER_DIR`, so a killed or recreated instance's journal is adopted (PRD-018 Section 6.8)
- [ ] Instances publish no ports. The balancer is the only published service
- [ ] `HEALTHCHECK` in the image, using `python -c` and `urllib` against `/health` (the slim image has no curl, [Dockerfile:49](../../../Dockerfile)). The balancer `depends_on` instances `service_healthy`

**Rolling restart**
- [ ] `scripts/rolling_restart.sh`: for each instance, set the drain flag, wait for removal plus the drain window, recreate, wait for `/ready` 200, then move to the next instance (D4)

**Tests**
- [ ] `tests/test_lb_caddyfile.py` (no Docker, no storage): asserts the policy, health URI, timeouts against the settings default, the upstream list against the compose services, and that the balancer has no `encode`
- [ ] `tests/test_two_instance_balancer.py`: two `uvicorn app.main:app` processes, the stub upstream and a real `caddy` process (D8)
- [ ] Docker E2E (opt-in): the compose stack, a websocket upgrade through the balancer, stickiness by cookie, a kill and a reconnect (D8)
- [ ] CI installs a pinned Caddy binary so the balancer test runs and does not skip (D8)

**Documentation**
- [ ] `docs/deployment.md` "Multiple instances" rewritten: topology, affinity trade-off, probes, timeouts, rolling restart, what the user sees on failover. The "unblocked, not delivered" note is removed
- [ ] `docs/roadmap.md:33` ticked. README links the new section. `docs/configuration.md` and `.env.example` gain `DRAIN_FILE`, `READY_DB_TIMEOUT_SECONDS` and `LB_COOKIE_SECRET`

### Out of Scope

- [ ] Moving Reflex state to Redis (`StateManagerRedis`). Reflex supports it. This PRD does not adopt it (D1); see Section 13
- [ ] Provider fallback (roadmap item; separate PRD)
- [ ] Autoscaling, Kubernetes manifests, Helm, cloud load balancers (ALB, GCLB). The timeout invariant in D6 is documented so they can be configured later
- [ ] TLS termination at the balancer. Documented as the operator's choice; the shipped file is plain HTTP like today's
- [ ] Dynamic upstream discovery (`docker compose --scale`, Caddy `dynamic a`) (D7)
- [ ] Graceful `SIGTERM` handling in the Reflex process (D4)
- [ ] Config-drift detection between instances (Risk 4)
- [ ] Anything PRD-018 owns: retries, breaker and audit buffering

## 5. User Stories

1. **As an operator, I want one command to start two instances behind a balancer, so that I get capacity and restarts without downtime.**
   *Example:* `LB_COOKIE_SECRET=… docker compose -f docker-compose.lb.yml up -d --build` starts `harness-a`, `harness-b` and `lb`. `curl :8000/health` returns `{"status":"ok"}`, and `curl :8000/ready` returns `{"status":"ready"}`.

2. **As a chat user, I want my conversation to stay put while I use it, so that the UI does not sign me out between messages.**
   *Example:* the first `GET /` sets `harness_lb`. Every `/_event/` websocket reconnect from that tab carries the cookie and reaches `harness-a`, and the state that holds `_token` is still there.

3. **As a chat user whose instance died, I want to sign in once and find my chats, so that a crash costs me a moment, not my work.**
   *Example:* `harness-a` is killed. The tab's socket reconnects, Caddy picks `harness-b`, and `harness-b` has no state for the tab's token, so the sign-in gate renders. After sign-in, `login()` loads the session list and opens the most recent chat ([state.py:322-335](../../../chat_ui/chat_ui/state.py)). An answer that was in flight on `harness-a` is lost unless its pipeline had already written the transcript row.

4. **As an operator, I want to restart instances one at a time without failing requests, so that a deploy is not an incident.**
   *Example:* `scripts/rolling_restart.sh` touches `/tmp/harness-drain` in `harness-a`. Its `/ready` turns 503 `draining`, and the balancer stops routing new requests to it within 5 s. A `POST /query` already running on it completes. After the drain window the script recreates the container, waits for `/ready` 200, then does the same for `harness-b`.

5. **As an integrating developer, I want a slow non-streaming `/v1` call to come back through the balancer, so that a 100-second completion is not cut at 60.**
   *Example:* the stub delays 100 s. The response arrives, because no proxy timeout on the path is shorter than `OPENROUTER_TIMEOUT_SECONDS` + 30 s.

6. **As an integrating developer, I want a streaming `/v1` call to keep its keep-alives through two proxies, so that my client does not time out on a long answer.**
   *Example:* with a 30 s stub delay and `V1_SSE_KEEPALIVE_SECONDS=10`, three `: keep-alive` lines arrive through `lb` and then the in-container Caddy, each within 2 s of its interval.

7. **As an operator, I want an instance that cannot reach the database taken out of rotation, so that its users get a working instance instead of `503`s.**
   *Example:* `harness-b`'s path to the database fails. Its breaker opens after five failed operations (PRD-018 D6), and `/ready` returns 503 `breaker_open` with `Retry-After`. The balancer sends everything to `harness-a`, and requests already on `harness-b` get PRD-018's 503 + `Retry-After` unchanged. `/health` on `harness-b` still returns 200, so nothing restarts it in a loop. When the breaker's half-open probe succeeds, `/ready` turns 200 and `harness-b` rejoins. If the database is down for every instance, the balancer answers 503 + `Retry-After` itself (D9).

## 6. Core Architecture & Patterns

### 6.1 Topology (D2)

```
client ──► lb (caddy:2.x, :$PORT, lb_policy cookie, health_uri /ready)
             ├──► harness-a:$PORT  [in-container Caddy ─► reflex backend :8001]
             └──► harness-b:$PORT  [in-container Caddy ─► reflex backend :8001]
                                         └──── both ──► Turso / libSQL (shared)
```

The balancer proxies **every path** to an instance, the static pages included. It does no path routing. The in-container Caddy keeps that job, so `tests/test_caddyfile_routes.py` stays the one place where routing is checked. The balancer runs the official `caddy` image pinned to a version, not a rebuild of the harness image.

**Port constraint (D7).** The frontend is exported with `REFLEX_API_URL=http://localhost:${PORT}` ([Dockerfile:36](../../../Dockerfile)). Reflex's `getBackendURL` swaps `localhost` for `window.location.hostname`, but it keeps the port unless the page is served over `https:`, in which case it clears the port (`reflex_base/.templates/web/utils/state.js:99-122`). **Over plain HTTP, the balancer must therefore publish the same `$PORT` the image was built with.** Otherwise the websocket bypasses the balancer, or misses it entirely. Behind TLS on 443 the constraint disappears.

### 6.2 Where per-tab state lives, and why affinity matters (D1)

Verified in the installed `reflex==0.9.6.post1` (`.venv/Lib/site-packages`):

- `reflex_base/config.py:237`: `state_manager_mode` defaults to `DISK`. `reflex/istate/manager/disk.py:37` (`StateManagerDisk`) keeps state in memory and writes it, debounced (`REFLEX_STATE_MANAGER_DISK_DEBOUNCE_SECONDS`, default 2.0 s), under `REFLEX_STATES_WORKDIR` (default `.states`). That directory is per container. `chat_ui/rxconfig.py` sets no state option.
- The browser's Reflex token lives in `sessionStorage`, one per tab (`state.js:86-89`). The client reconnects by itself, sending `token` in the query string, and rehydrates (`state.js:599-660`). `App.on_connect` links the token to the new socket id (`reflex/app.py:1626-1640`).
- The transport is websocket only, with upgrades off (`reflex/app.py:540-552`, `config.transport` default `"websocket"`). An open connection is a single TCP stream and is pinned for its lifetime by construction. **Affinity matters only on reconnect**: network blips, laptop sleep, the server's ping timeout (`Ping.INTERVAL=25`, `TIMEOUT=120`), a balancer reload, an instance death.
- **Out-of-process state is supported.** `StateManagerRedis` (`reflex/istate/manager/redis.py:87`) and `RedisTokenManager` (`reflex/utils/token_manager.py:175`) exist. `emit_update` forwards a delta for a socket held by another instance through a Redis "lost and found" key (`reflex/app.py:1676-1697`). Setting `REFLEX_REDIS_URL` alone switches the manager to Redis (`reflex/istate/manager/__init__.py:66-70`), and `redis>=6.4,<8.0` is already a Reflex dependency (installed: 7.4.1).

What a reconnect to a different instance means today: no state for the token, so `user_id == ""` and the sign-in gate renders. `_token` is a backend var, and no signed-in state survives a lost state ([state.py:322-327](../../../chat_ui/chat_ui/state.py)). Transcripts are in `chat_sessions` / `chat_messages` and reload on sign-in.

### 6.3 Probes (D3, D4, D5)

| Probe | Path | Checks | Used by |
|---|---|---|---|
| Liveness | `/health` (unchanged) | nothing; process answers HTTP through the in-container Caddy | Docker `HEALTHCHECK`, `depends_on: service_healthy` |
| Readiness | `/ready` (new) | drain file absent; PRD-018 breaker `closed` (`storage_status()`, no DB call); then this route's own `SELECT 1` within `READY_DB_TIMEOUT_SECONDS` | balancer active health check, rolling restart script |
| Storage detail | `/storage/status` (PRD-018 D16, `stats:read`) | breaker, journal, counters; no DB call | operators; not the balancer (it needs a token) |

Both are sync FastAPI routes on anyio's threadpool. The pipeline uses its own executor ([app/routers/query.py:44-52](../../../app/routers/query.py)), so a saturated pipeline does not starve the probes. Neither probe takes authentication, and neither body names the endpoint or carries error text. `/ready` is reached through the in-container Caddy, so a 200 also proves that Caddy and the backend in that container are both up.

### 6.4 Directory structure (files touched)

```
app/main.py                         # + GET /ready
app/db/database.py                  # + check_ready() -> classification
app/config.py                       # + DRAIN_FILE, READY_DB_TIMEOUT_SECONDS (validated)
Caddyfile                           # /ready added to @backend_routes
Dockerfile                          # + HEALTHCHECK (python urllib → /health)
deploy/lb/Caddyfile                 # new: the balancer
docker-compose.lb.yml               # new: harness-a, harness-b, lb
scripts/rolling_restart.sh          # new
tests/test_main.py                  # /ready cases
tests/test_caddyfile_routes.py      # EXPECTED_MATCHER + "/ready"
tests/test_route_reservations.py    # /ready reserved
tests/test_lb_caddyfile.py          # new, no Docker
tests/test_two_instance_balancer.py # new, real caddy + 2 uvicorn
tests/e2e/test_lb_docker.py         # new, opt-in
.github/workflows/ci.yml            # pinned caddy install
docs/deployment.md, docs/configuration.md, docs/roadmap.md, README.md, .env.example
```

### 6.5 Patterns followed

- Restated-list tests, as in `tests/test_caddyfile_routes.py:30-45`: the expected balancer directives are written out in the test, not derived from the file.
- Boot-time checks stay boot-time. `check_database_reachable()` ([app/db/database.py:567-589](../../../app/db/database.py)) still guards startup, and `check_ready()` is its non-raising runtime twin, not a replacement.
- Opt-in Docker E2E with its own compose project, following `tests/e2e/test_docker_smoke.py` and `tests/e2e/docker/compose.smoke.yml`: a throwaway libSQL, and the stub in the instance's network namespace so `OPENROUTER_BASE_URL` stays loopback.

## 7. Tools/Features

### F1 — `/ready`
The checks run in this order, and each one short-circuits the rest:
1. **Drain file.** Its presence means `draining`. There is no I/O beyond `os.path.exists`.
2. **PRD-018 breaker.** `database.storage_status().breaker.state` is read, with no database call (PRD-018 D16). `open` or `half_open` means `breaker_open`, with `Retry-After` equal to the breaker's `retry_after_seconds` (minimum 1). Half-open counts as not ready, because PRD-018 lets exactly one statement through while the breaker probes, and `/ready` must not add a second.
3. **Own `SELECT 1`**, sent only while the breaker is `closed`, with a deadline of `READY_DB_TIMEOUT_SECONDS` (default 2.0, > 0, ≤ 10).
   - It runs outside `_unit_of_work`, like the D17 boot check. It is never retried, it is never counted as a breaker failure, and a success never closes or resets the breaker. Only the half-open probe moves the breaker (PRD-018 D6).
   - Without this rule, N instances probing every 5 s would make the probe rate decide the breaker.
   - The libsql client is sync, so the deadline is enforced by running the statement on a single-slot executor and abandoning the future. While an earlier probe is still stuck, for example behind a stalled shared client (PRD-018 Section 6.6), the route reports `database_unreachable` without starting another.
   - Failures are classified with `_classify_startup_failure`: `DatabaseAuthError` gives `database_auth`, everything else gives `database_unreachable`. The detail goes to the log at `WARNING`, with no token.

### F2 — Drain
`DRAIN_FILE` (default `/tmp/harness-drain`). `/ready` checks for it on every call. Draining changes nothing else: requests that reach the instance are still served, because in-flight work and sticky websockets must finish. Removing the file returns the instance to rotation.

### F3 — Balancer Caddyfile
`deploy/lb/Caddyfile`, approximately:

```
:{$PORT}
reverse_proxy harness-a:{$PORT} harness-b:{$PORT} {
	lb_policy cookie harness_lb {$LB_COOKIE_SECRET}
	lb_try_duration 5s
	health_uri /ready
	health_interval 5s
	health_timeout 3s
	health_status 200
	fail_duration 30s
	transport http {
		dial_timeout 3s
		response_header_timeout 150s
	}
	stream_close_delay 5m
}
handle_errors 502 503 {
	header Retry-After 10
	@v1 path /v1/*
	respond @v1 `{"error":{"message":"Service unavailable; the request was not sent to the model.","type":"api_error","param":null,"code":"service_unavailable"}}` 503
	respond `{"detail":"Service unavailable"}` 503
}
```

`handle_errors` fires for errors the balancer raises: no healthy upstream (503 after `lb_try_duration`, about 5 s) and a failed dial, and also a connection an instance breaks after receiving the request (Caddy raises 502, rewritten to this 503, never replayed). A 503 returned by an instance is a proxied response, so it passes through untouched with its own `Retry-After` (D9); verified in STORY-004. `response_header_timeout` expiry is a **504 with an empty body** that `handle_errors 502 503` does not catch (open point for STORY-005: add 504, or accept it). The `/v1` body's "the request was not sent to the model" is false for the mid-flight break, which has already reached an instance. `Retry-After: 10` is PRD-018's `_BREAKER_OPEN_SECONDS`.

Verified against Caddy 2.11.7 (STORY-004): every directive above is accepted as written. The cookie is `harness_lb=<64 hex, HMAC-SHA-256 of the upstream>; Path=/; HttpOnly; SameSite=Lax` (no `Secure`, session cookie), re-set when the pinned upstream is unhealthy or dead, and an empty `LB_COOKIE_SECRET` is silently accepted (compose's `${LB_COOKIE_SECRET:?}` is the only guard). Upstream override for tests: an env default does not parse (`{$X:a:{$PORT} b:{$PORT}}` stops at the first `}`), so the test replaces the one line `reverse_proxy harness-a:{$PORT} harness-b:{$PORT} {` textually and asserts everything else is byte-identical. Parallel `caddy run` processes collide on the admin port `localhost:2019`; set env `CADDY_ADMIN=localhost:<free port>` per process.

`response_header_timeout` is `OPENROUTER_TIMEOUT_SECONDS` (120) + 30 s (D6). `stream_close_delay` keeps websockets open across a balancer config reload instead of dropping every chat at once. The final directive set is pinned by `tests/test_lb_caddyfile.py`.

### F4 — `docker-compose.lb.yml`
Standalone, not an overlay. Compose cannot remove the `ports:` that `docker-compose.yml` publishes, short of `!reset` (D7). `harness-a` and `harness-b` share one YAML anchor: same build, same `env_file: .env`, same `PORT`, no `ports`, and the same named volume at PRD-018's `AUDIT_BUFFER_DIR`. Each process locks its own journal file, so sharing the volume is safe. It also means a journal left behind by an instance that was killed during a rolling restart is adopted by its sibling or by its replacement (PRD-018 Section 6.8, "Ownership and multi-instance"). `lb` publishes `${PORT}:${PORT}`, gets `LB_COOKIE_SECRET` (required, `${LB_COOKIE_SECRET:?}`), and `depends_on` both instances with `condition: service_healthy`.

### F5 — Image `HEALTHCHECK`
`HEALTHCHECK --interval=10s --timeout=3s --start-period=60s CMD python -c "import urllib.request,os;urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/health',timeout=2)"`. The probe is liveness, not readiness, so a database outage never marks a container unhealthy (D3). The start period covers spaCy model load and `init_db()`.

### F6 — Rolling restart
`scripts/rolling_restart.sh [-f docker-compose.lb.yml]`, one instance at a time:
1. `docker compose exec <svc> touch $DRAIN_FILE`
2. Wait until the instance's own `/ready` is 503. This is checked inside the container, because instances publish no port.
3. Sleep `health_interval × 2 + DRAIN_SECONDS`. `DRAIN_SECONDS` defaults to `OPENROUTER_TIMEOUT_SECONDS + 10`, so every in-flight `/query`, chat send and `/v1` call can finish.
4. `docker compose up -d --force-recreate --no-deps <svc>`. A recreated container starts without the drain file.
5. Wait for `/ready` 200, then continue with the next instance. Boot is unchanged by PRD-018 D17, so a replacement that cannot reach the database exits instead of coming up. The script stops there and leaves the remaining instance serving.

A non-empty audit journal does not block the stop. The entries are fsynced on the shared volume and are adopted and drained (PRD-018 D11).

The script refuses to start if any instance is not ready, so it never drains the last healthy one.

### F7 — Docs
`docs/deployment.md` "Multiple instances" becomes: topology diagram, start command, the affinity trade-off and what the user sees (Section 6.2, User Story 3), the probe table, the timeout invariant (D6) with numbers for a third-party balancer, the rolling restart, and the unsupported combinations (`REFLEX_REDIS_URL` set, `--scale`, IP-hash affinity).

## 8. Technology Stack

| Component | Version | Note |
|---|---|---|
| Reflex | `0.9.6.post1` (`requirements.txt`, `chat_ui/requirements.txt`) | disk state manager, websocket-only transport; unchanged |
| Caddy (in image) | unpinned, Cloudsmith `stable` apt repo ([Dockerfile:44-50](../../../Dockerfile)) | unchanged by this PRD (Risk 5) |
| Caddy (balancer) | official `caddy:2.11.7` image, pinned by digest `sha256:36c24ad91a7ff7bc4c87fe22bfa8df3c4b18da0773d73fc12ee2c52b98c0bb7e` | new; same binary version (`v2.11.7`) pinned in CI; its Linux tarball SHA-256 `727b91701a392de6ebc5027509f548bf39979e5216340d0faed8fa5e69c84f8b` goes in STORY-006's workflow (STORY-004) |
| FastAPI / uvicorn[standard] | as in `requirements.txt` | uvicorn runs the instances in `test_two_instance_balancer.py`; `websockets` (from `[standard]`) drives the E2E upgrade check |
| libSQL dev server | CI service, pinned by digest (`ci.yml`) | shared by both instances in tests |

No new Python dependency.

## 9. Security & Configuration

### 9.1 Authentication & authorization
Unchanged. Every instance resolves identity from the shared `users` table on every request. `/ready`, like `/health`, is unauthenticated and returns a status word and a fixed reason enum only.

### 9.2 Threat reasoning

| # | Threat | Answer |
|---|---|---|
| T1 | Sticky cookie leaks internal topology | Caddy's cookie value is an HMAC of the upstream under `LB_COOKIE_SECRET`. The secret is required, so the value is not a guessable hash of `harness-a:8000` |
| T2 | Client forges the cookie to pin itself to one instance | It can choose an instance, nothing more. Limits, duplicates and identity are in the shared database (PRD-013), so a pinned client gets no extra quota |
| T3 | `/ready` used to probe the database, or to drive the breaker | At most one bounded `SELECT 1` in flight per process, and none while the breaker is not `closed`. Never a breaker sample. The body has a reason enum only: no endpoint and no error text. Breaker detail stays behind `stats:read` on `/storage/status` |
| T7 | Sticky routing and PRD-018 T4 (a resend to another instance escapes the journal overlay) | The cookie keeps a chat tab's resends on one instance, which narrows T4 for the UI. `/query` and `/v1` clients without the cookie are round-robined, so T4's residual stands for them, as PRD-018 accepts |
| T4 | Drain file used as a denial-of-service lever | Writing it needs a shell in the container |
| T5 | Credential at rest in per-tab state | Already true today: the disk manager writes `ChatState._token` under `.states/` in the container. Not widened by this PRD. Redis would widen it to a network store (D1, Section 13) |
| T6 | A proxy hop logs bearer tokens | Neither Caddy logs request headers by default. The balancer Caddyfile enables no access log; documented |

### 9.3 Configuration

| Setting | Default | Validation | Read by |
|---|---|---|---|
| `DRAIN_FILE` | `/tmp/harness-drain` | non-empty absolute path | `/ready` |
| `READY_DB_TIMEOUT_SECONDS` | `2.0` | `> 0`, `≤ 10`, `<` balancer `health_timeout` | `check_ready()` |
| `LB_COOKIE_SECRET` | none (required by `docker-compose.lb.yml`) | compose `:?` | balancer only; never read by `app/` |

`REFLEX_REDIS_URL` stays unset, and the docs say so: setting it silently switches Reflex to Redis (Section 6.2).

### 9.4 Out of scope (security)
TLS at the balancer, mTLS between the balancer and instances, and network policy. The instances' published ports disappear in the balanced stack, which is the only network change.

## 10. API Specification

`GET /ready` takes no authentication.

```
200 {"status": "ready", "breaker": "closed"}
503 {"status": "not_ready", "reason": "draining"}
503 {"status": "not_ready", "reason": "breaker_open", "breaker": "open" | "half_open"}   + Retry-After: <s>
503 {"status": "not_ready", "reason": "database_unreachable"}
503 {"status": "not_ready", "reason": "database_auth"}
```

`Cache-Control: no-store`. These 503s belong to the probe only. They are not the ingress 503s of PRD-018 D8, which keep their own bodies and `Retry-After`. Through the balancer, the only new status is the balancer's own 503 when no upstream is healthy (D9). `/health` is byte-identical to today's. No other route changes. Through the balancer, every existing route keeps its contract: `tests/test_two_instance_balancer.py` replays the `/query` and `/v1` status table through `lb` and compares it with a direct call.

## 11. Success Criteria

### MVP definition
The compose stack runs two instances behind the balancer. Stickiness, drain, failover and long calls each have a passing test. `docs/deployment.md` no longer says "unblocked, not delivered".

### Functional requirements
- [ ] `/health` unchanged (existing `tests/test_main.py` cases pass unmodified)
- [ ] `/ready` returns each Section 10 status as specified, and returns within `READY_DB_TIMEOUT_SECONDS` + 0.5 s against a blackholed endpoint
- [ ] With the breaker forced `open` or `half_open` (PRD-018's injected clock), `/ready` sends no driver call. A hundred `/ready` failures leave `consecutive_failures` unchanged, and a `/ready` success does not close an open breaker
- [ ] Through the balancer, an instance's PRD-018 503 arrives byte-identical with its `Retry-After`, and the instance stays in rotation until its `/ready` says otherwise. With both instances not ready, `/v1` gets the balancer's 503 OpenAI error object with `Retry-After: 10`
- [ ] Through a real balancer, ten alternating `POST /query` requests without a cookie reach both instances (counted from each uvicorn child's access log). The same ten with the cookie all reach one
- [ ] A rate limit of 5 admits exactly 5 of 10 requests through the balancer (PRD-013 T5, again through a hop)
- [ ] Drain: within `health_interval × 2` of touching the file, no new request reaches the drained instance. A request started before the drain completes with 200
- [ ] Kill (`SIGKILL`) of one instance: subsequent requests succeed through the other within `lb_try_duration`; no 5xx after the first health interval
- [ ] `/v1` streaming, 30 s stub delay, gzip requested: every keep-alive arrives through both Caddies within 2 s of its interval
- [ ] `/v1` non-streaming and `POST /query` with a 100 s stub delay return 200 through the balancer
- [ ] E2E: a websocket upgrade to `/_event/?EIO=4&transport=websocket&token=…` through `lb` returns 101 and reaches the cookie's instance. After that instance is killed, the reconnect reaches the other instance
- [ ] `tests/test_caddyfile_routes.py` and `tests/test_lb_caddyfile.py` pass without Docker or storage

### Quality indicators
- The balancer test runs in CI and does not skip there: `HARNESS_REQUIRE_CADDY=1` turns a missing binary into a failure
- No `sleep` that a condition could replace. Waits are loops with a deadline, in the style of `tests/test_two_instance_smoke.py`'s `_INVARIANTS`
- The existing smoke suite is untouched apart from a docstring pointer

## 12. Implementation Phases

### Phase 1 — Probes (Stories 1–3)
`DRAIN_FILE` and `READY_DB_TIMEOUT_SECONDS` settings; `check_ready()`; `GET /ready`; Caddyfile matcher plus the route tests; image `HEALTHCHECK`. *Validation:* unit tests against the libSQL CI service and a blackholed URL; `docker build` passes.

### Phase 2 — Balancer (Stories 4–6: STORY-004 spike, STORY-005 Caddyfile + compose, STORY-006 CI Caddy)
`deploy/lb/Caddyfile`; `docker-compose.lb.yml`; `tests/test_lb_caddyfile.py`; CI installs pinned Caddy. *Validation:* the static test passes; `docker compose -f docker-compose.lb.yml config` is valid.

### Phase 3 — Proof (Stories 7–10: STORY-007 routing, STORY-008 drain/kill/long calls, STORY-009 rolling restart, STORY-010 Docker E2E)
`tests/test_two_instance_balancer.py` (stickiness, limits, drain, kill, long calls, SSE); Docker E2E for the websocket and failover; `scripts/rolling_restart.sh`, exercised by the E2E. *Validation:* CI green; E2E green locally with `--run-e2e`.

### Phase 4 — Docs (Story 11)
`docs/deployment.md`, `docs/configuration.md`, `docs/roadmap.md`, README, `.env.example`. *Validation:* every setting named in the docs exists in `app/config.py` or the compose file.

## 13. Future Considerations

- **Redis state manager.** It removes the failover sign-in and makes affinity unnecessary, because any instance can serve any tab and `RedisTokenManager` forwards deltas. Adopt it when either of these happens: a sign-in per failover becomes unacceptable, or a Redis already exists in the target environment. It needs its own threat review, because `_token` would sit in Redis for `redis_token_expiration` (default 3600 s).
- Kubernetes manifests: `/health` maps to `livenessProbe`, `/ready` to `readinessProbe`, the drain flag to a `preStop` hook, and stickiness to ingress cookie affinity.
- Autoscaling and dynamic upstreams (Caddy `dynamic a` with `--scale`).
- A config fingerprint on `/ready`, so instances started with different policy files are detected (Risk 4).
- Graceful `SIGTERM` in the image once Reflex handles it, which would make the drain window shorter.

## 14. Risks & Mitigations

| # | Risk | Likelihood / Impact | Mitigation |
|---|---|---|---|
| 1 | **Fleet-wide database outage opens every breaker**, so every instance leaves rotation and clients get the balancer's 503 instead of PRD-018's ingress 503s | Medium / Medium | The balancer's `handle_errors` keeps the 503 + `Retry-After` contract with fixed bodies (D9). What is lost: PRD-018's specific `storage_unavailable` code and text. Instances rejoin within one health interval of their half-open probe succeeding. OD2 offers the alternative |
| 2 | **Failover costs a sign-in and any in-flight chat answer** | Medium / Low | Stated in the docs and the UI-facing story. Transcripts persist. Redis is the documented upgrade path (Section 13) |
| 3 | **A third-party balancer's idle timeout (often 60 s) cuts long non-streaming calls** | High / Medium | Timeout invariant in D6, with numbers. `/v1` streaming is already covered by keep-alives |
| 4 | **Instances run with different policy files or `.env`**, so the answer depends on which instance a request hits | Medium / High | One YAML anchor and one `env_file` in `docker-compose.lb.yml`. A config fingerprint is future work |
| 5 | **Unpinned in-image Caddy and pinned balancer Caddy drift** in websocket or flush behaviour | Low / Medium | The E2E runs the real image behind the pinned balancer; pinning the in-image Caddy is noted as follow-up |
| 6 | **Caddy cookie-policy details** (attributes, fallback on an unhealthy upstream) differ from this PRD's assumptions | Medium / Medium | **Verified in STORY-004 against Caddy 2.11.7.** Fallback and re-set work as assumed; differences: no `Secure` attribute, an empty secret is accepted silently, and a header timeout is an empty 504 outside `handle_errors` (see F3) |

## 15. Appendix

### Decisions

| # | Question | Decision |
|---|---|---|
| D1 | Affinity: balancer stickiness or out-of-process Reflex state | **Sticky cookie at the balancer; Reflex stays on the disk state manager.** Redis is supported by Reflex 0.9.6.post1 (Section 6.2) but would add a second hard infrastructure dependency and move the user's credential into a network store. With websocket-only transport, stickiness only has to cover reconnects. The cost, a sign-in after an instance dies with transcripts intact, is stated and tested. Cookie over IP hash: IP hash collapses NAT'd teams onto one instance and breaks on mobile IP changes |
| D2 | Topology | **A separate pinned Caddy balancer in front of unchanged images**, keeping the in-container Caddy. Single-instance behaviour and `tests/test_caddyfile_routes.py` stay as they are, and Caddy is already the repo's proxy |
| D3 | What the probes check | **`/health` = liveness, unchanged, no I/O (PRD-018 D16 keeps it so). `/ready` = drain flag + PRD-018 breaker state + one bounded `SELECT 1`.** The database is a hard dependency of every request, so an instance that cannot reach it is not ready. Docker `HEALTHCHECK` uses liveness, so an outage never restart-loops a container |
| D4 | Draining | **A drain file that flips `/ready` to 503; stop only after the drain window.** The image stops with `SIGKILL` (Dockerfile:76-78) because Reflex does not handle `SIGTERM` reliably, so drain has to happen before the stop signal. File, not an endpoint: no new network surface |
| D5 | Readiness and PRD-018's breaker | **`/ready` reads `database.storage_status().breaker.state` (PRD-018 D6, D16): `open` or `half_open` → 503 `breaker_open` + `Retry-After`, with no driver call. Only while `closed` does it send its own `SELECT 1`.** That statement runs outside `_unit_of_work`, like D17's boot check. It is never retried, it is never counted as a breaker failure, a success never closes the breaker, and at most one is in flight per process. Two reasons. Probe traffic must not decide the breaker. And PRD-018's half-open state admits one statement, which `/ready` must not double |
| D9 | Status codes through the balancer (PRD-018 D8) | **Pass instance 503s through untouched; answer "no healthy upstream" with the balancer's own 503 + `Retry-After: 10`.** Passive health ignores status codes (no `unhealthy_status`), so a `StorageUnavailableError` 503 never marks an instance down; only `/ready` does. A request already sent is never replayed on another upstream, because `/query` admission and the charge are `NON_IDEMPOTENT` (PRD-018 Section 6.3). The balancer's `/v1` body is an OpenAI error object with code `service_unavailable`, not `storage_unavailable`: at the balancer, the cause can be a database outage, every instance dead, or every instance draining |
| D6 | Timeouts | **Invariant: every hop's response/idle timeout > `OPENROUTER_TIMEOUT_SECONDS` + 30 s** (150 s by default), because `POST /query` and non-streaming `/v1` send no byte until the pipeline finishes. SSE needs no special timeout: `wait_for_commit` sends headers once the upstream starts ([app/routers/v1.py:332-356](../../../app/routers/v1.py)) and keep-alives follow every `V1_SSE_KEEPALIVE_SECONDS`. No `encode` at the balancer; the in-container Caddy already gzips, and keep-alives through it are proven (PRD-015 STORY-018) |
| D7 | Instance naming and ports | **Two named services, no `--scale`; the balancer publishes the build-time `$PORT`.** Named upstreams give the cookie a stable target and the tests determinism. The port follows from Reflex's `getBackendURL` (Section 6.1). Standalone compose file, because an overlay cannot drop the base file's `ports` without `!reset` |
| D8 | How the smoke test goes through the balancer | **A sibling module, `tests/test_two_instance_balancer.py`, with real uvicorn instances, the stub upstream and a real `caddy` process, run in CI with a pinned Caddy; plus an opt-in Docker E2E for the websocket.** The existing smoke file's harness is pipe-driven `TestClient` with no ports and a no-timeouts invariant. Putting HTTP into it would break what makes it deterministic. The websocket needs the Reflex backend and the image, which is E2E territory |

### Open decisions (proposed default)

- **OD1 — Adopt Redis now instead of stickiness?** Proposed default: **no** (D1). Revisit if a sign-in per failover is unacceptable to the user.
- **OD2 — Should readiness reflect the database at all?** Proposed default: **yes** (D3, D5). PRD-018 Section 10 argues the other way for `/health`: a balancer should not empty its pool during an outage, because the instances still answer 503 + `Retry-After` correctly. PRD-018 Section 13 also proposes a readiness probe that stops routing to an instance whose breaker is open. The alternative is readiness gated only on drain and `database_auth` (a per-instance configuration fault), with the breaker state reported in a 200 body. That keeps PRD-018's exact `storage_unavailable` bodies during a fleet-wide outage, but it keeps routing to an instance whose own path to the database is broken.
- **OD6 — The balancer's `/v1` error code when no upstream is healthy.** Proposed default: **`service_unavailable`** (D9). The alternative is to reuse PRD-018's `storage_unavailable`, which is more specific for the usual cause but wrong when every instance is dead or draining.
- **OD3 — Drain via file or via an admin endpoint (`POST /admin/drain`, `ADMIN_TOKEN`)?** Proposed default: **file** (D4).
- **OD4 — Sibling test module or an extension of `test_two_instance_smoke.py`?** Proposed default: **sibling** (D8). The brief said "extend"; the sibling extends the coverage, not the file.
- **OD5 — Pin the in-image Caddy in this PRD?** Proposed default: **no**, follow-up (Risk 5).

### Evidence (verified against `main` @ `2253871`)
- `app/main.py:39-41`: `/health` returns `{"status": "ok"}`, no I/O.
- `Caddyfile:3-8`: `encode gzip`; `@backend_routes` list; `tests/test_caddyfile_routes.py:33-45` restates it.
- `Dockerfile:36,74`: `REFLEX_API_URL=http://localhost:${PORT}`; `:49` curl purged; `:78` `STOPSIGNAL SIGKILL`; `:85-87` Caddy and then `reflex run --backend-only`.
- `docker-compose.yml`: one service, publishes `${PORT}`, `env_file: .env`, no healthcheck, no volume.
- `app/config.py:240` `OPENROUTER_TIMEOUT_SECONDS=120.0`; `:374` `V1_SSE_KEEPALIVE_SECONDS=10.0`; no Redis, drain or readiness setting exists.
- `app/services/v1_sse.py:128-142`: keep-alive loop; `app/routers/v1.py:345-356`: `StreamingResponse` with `X-Accel-Buffering: no`.
- `chat_ui/rxconfig.py`: no `state_manager_mode`, no `redis_url`.
- Reflex internals: as cited in Section 6.2 (installed package under `.venv/Lib/site-packages`). Reflex also serves `/_health` (db and redis status, `reflex/app.py:1546`). It is not in `@backend_routes`, so it is unreachable through Caddy, and this PRD does not use it.
- `tests/test_two_instance_smoke.py`: `subprocess.Popen` children speaking JSON over pipes via `TestClient`; no HTTP ports.
- `scripts/stub_openrouter.py`: `delay_seconds` rules and `GET /health`, used for the long-call tests.

### Verified (STORY-004, Caddy 2.11.7)
- `lb_policy cookie`: `Set-Cookie: harness_lb=<64 hex>; Path=/; HttpOnly; SameSite=Lax`; no re-set on a valid cookie; garbage cookie ignored and re-set; pinned upstream unhealthy or dead: another upstream answers (0.25 s for a dead one, one health interval for an unready one) with a new cookie.
- No healthy upstream: **503** (not 502) after 5.01 s (`lb_try_duration`); `handle_errors 502 503` catches it with `Retry-After: 10` and the fixed bodies, and `@v1 path /v1/*` sees the original path. A proxied instance 503 passes through byte-identical (`Retry-After: 7` kept) and the instance stays in rotation.
- Retry: with no `retry_match`, a POST that reached an instance is never replayed (instance drops the connection: 503 from `handle_errors`, other instance got 0 requests; header timeout: 504, other instance 0). GET is retried. Dial failures are retried for any method.
- `stream_close_delay`, `lb_try_duration`, `health_*`, `fail_duration`, `transport http {dial_timeout response_header_timeout}` and `handle_errors 502 503` are all accepted (`caddy validate`, `caddy adapt`).

### Not verified
- That the disk state manager's pickle includes backend vars such as `_token`: read from code only (`reflex/state.py:2051-2072` `__getstate__` copies `__dict__`, so backend vars are included), not run. T5 holds either way for the in-memory copy.
- Websocket pass-through and `stream_close_delay` on a config reload (only the directive's acceptance was checked); the Docker image as a balancer upstream (only `caddy version` was run in the image).

### Related documents
- PRD-002 (Reflex chat UI): single-port Caddy layout, the `@backend_routes` matcher
- PRD-007 (Turso migration): shared database, concurrent `init_db()`, `check_database_reachable()`, the two-instance smoke
- PRD-008 (chat sessions): transcripts in the database, which is why failover loses no chat
- PRD-013 (usage limits): limits shared across instances
- PRD-015 (OpenAI-compatible endpoint): buffered SSE, keep-alives, the Docker smoke and probe
- [PRD-018](../PRD-018-db-resilience/PRD.md) (database resilience, **done**): D6 (process-local breaker, half-open `SELECT 1`), D7 (`StorageUnavailableError`), D8 (503 + `Retry-After` on every ingress), D16 (`/storage/status`, `/health` unchanged), D17 (boot unchanged). Consumed by D3, D5 and D9 and by the journal volume in F4

### Dependencies
- Depends on: PRD-007 (done) and PRD-018 (done, merged in #27). It needs `database.storage_status()` and the breaker states, the shared `AUDIT_BUFFER_DIR` volume and PRD-018's ingress 503s.
- Blocks: none.

**Skills referenced:** none
