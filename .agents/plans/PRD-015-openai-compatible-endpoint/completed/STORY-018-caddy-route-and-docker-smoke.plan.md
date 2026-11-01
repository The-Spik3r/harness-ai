---
story: STORY-018
prd: PRD-015
slug: caddy-route-and-docker-smoke
title: "Caddy routes /v1/*; Docker smoke with keep-alive through Caddy"
type: ENHANCEMENT
complexity: MEDIUM
epic_branch: epic/PRD-015-openai-compatible-endpoint
created: 2026-10-30
---

# Plan: Caddy routes /v1/*; Docker smoke with keep-alive through Caddy

## Summary

Add `/v1/*` to the Caddyfile's `@backend_routes` matcher, pin the matcher with a Docker-free unit test that every harness route is matched, and prove the deployment works with a Docker smoke. The smoke is a new `e2e` module. It brings up the real image under a separate compose project, with a throwaway libSQL service and the stub upstream as a sidecar that shares the harness container's network namespace, so `OPENROUTER_BASE_URL=http://127.0.0.1:9100/v1` stays loopback and passes the settings validator unchanged. A probe runs **inside** the harness container, so Docker Desktop's port forwarding is out of the timing path. It sends the same requests to the backend port directly (`:8001`, the production `reflex run --backend-only` process) and to Caddy (`:$PORT`) and compares the answers. It times keep-alives through Caddy with `Accept-Encoding: gzip`, checks the Reflex routes, `/query` and `/v1/models`, and takes the PRD Risk 6 executor-concurrency measurement. One host-side request through the published port also proves the front door from outside. The plan starts with a spike: whether Caddy's `encode gzip` buffers `text/event-stream` in the installed Caddy decides whether the Caddyfile needs more than the one-token change.

## User Story

As a platform operator
I want `/v1` served through the same Caddy front door as `/query`, with streamed responses flushed rather than buffered
So that the endpoint works in the Docker deployment exactly as it does locally

## Story Reference

- Story file: `.agents/stories/PRD-015-openai-compatible-endpoint/STORY-018-caddy-route-and-docker-smoke.md`
- PRD: `.agents/PRDs/PRD-015-openai-compatible-endpoint/PRD.md` (Sections 6.1, 7.6, 11, 14 Risks 1 and 6)

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT (deployment config + test infrastructure) |
| Complexity | MEDIUM |
| Systems Affected | `Caddyfile`, Docker compose (override only), `tests/` (unit + e2e), stub scripts |
| Story | STORY-018 |
| PRD | PRD-015 |
| Epic Branch | `epic/PRD-015-openai-compatible-endpoint` (commit directly on this branch) |

Dependencies STORY-013 (`2b1773a`) and STORY-014 (`e6d9ab7`) are both `done`.

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | The story lists `skills: []`. The only skill in `.agents/skills/` is `frontend-design`, and no UI changes here | — |

---

## Decisions (resolved here, as the story asks)

**D-A: How the stub reaches the container.** A compose override service `stub` with `network_mode: "service:harness-ai"`, built from the same image. It runs `python scripts/stub_openrouter.py --host 127.0.0.1 --port 9100 --script tests/e2e/scripts/docker_smoke.json` inside the harness container's network namespace. The harness uses `OPENROUTER_BASE_URL=http://127.0.0.1:9100/v1`, which is loopback, so the `app/config.py:438-480` validator is unchanged. The image already contains `scripts/` and `tests/`, because `.dockerignore` excludes neither. Two alternatives were rejected:
- `host.docker.internal`: it is not loopback, so it would need the validator relaxed or `https` on the stub.
- Stub `network_mode: service:` the other way round: `harness-ai` would lose its `ports:` publish.

**D-B: The database.** A `libsql` service in the override, `ghcr.io/tursodatabase/libsql-server:latest` with `SQLD_NODE=primary` and **no published port**. The harness uses `DATABASE_URL=http://libsql:8080`. Plain `http://` needs no `TURSO_AUTH_TOKEN` (`app/config.py:395-406`). The smoke never touches the shared/throwaway dev DBs or `.env`'s `DATABASE_URL`. The service is torn down with `down -v`.

**D-C: The compose project.** `docker compose -p harness-smoke -f docker-compose.yml -f tests/e2e/docker/compose.smoke.yml`, with `PORT=8095`. The existing `harness-ai-harness-ai-1` container (memory, 2026-10-22) is left alone. The base `docker-compose.yml` is **not** edited. Its `env_file: .env` still loads, and the override's `environment:` wins over every key the smoke depends on. The keys that could leak from `.env` are recorded in the report.

**D-D: Where the probe runs.** Inside the harness container, through `docker compose exec -T harness-ai python -m tests.e2e.docker_smoke_probe ...`. That is the in-network approach from `scripts/test-db-in-network.sh`, used from the start rather than as a fallback, because timing through Docker Desktop's forwarding is known to stall (PRD-014 STORY-006). "Against uvicorn directly" in AC 2 means `http://127.0.0.1:8001`, the backend process Caddy proxies to in production. The host-side `uvicorn app.main:app` comparison is already STORY-015's evidence. One extra host-side probe through `127.0.0.1:8095` proves the published port.

**D-E: The encode question.** Caddy's `reverse_proxy` already flushes immediately for `Content-Type: text/event-stream`, per Caddy's docs on `flush_interval`. So `flush_interval -1` would be a no-op, and the only possible buffer is `encode gzip`, which wraps the proxy's writer. Task 1 measures it. The fix, if needed, is an `encode` block whose `match` excludes `text/event-stream`, with a comment saying why. That is the one Caddyfile edit beyond the matcher that the story sanctions.

---

## Patterns to Follow

### Route enumeration (descend into `_IncludedRouter`)
```python
# SOURCE: tests/test_route_reservations.py:13-23
def _harness_route_paths():
    paths = set()
    for route in app.routes:
        if type(route).__name__ == "_IncludedRouter":
            paths.update(r.path for r in route.original_router.routes)
        elif hasattr(route, "path"):
            paths.add(route.path)
    return paths
```

### Reflex reserved routes (restated, not imported)
```python
# SOURCE: tests/test_route_reservations.py:9-10, tests/test_admin_shell.py:170-176
REFLEX_RESERVED_ROUTES = {"/ping", "/_event", "/_upload"}
```

### E2E module shape (gated, nonce, subprocess-only storage)
```python
# SOURCE: tests/e2e/test_openai_sdk.py:34-58
pytestmark = pytest.mark.e2e
NONCE = secrets.token_hex(4)
_RECIPE = ("docker run -d --name harness-libsql-e2e015 ... HARNESS_E2E_LIBSQL_URL=...")
```
And `tests/e2e/test_continue.py:128-140`: a required external tool is resolved from an env var, with `pytest.fail(recipe)` when it is missing, never whatever is on PATH. Here that tool is Docker plus `HARNESS_E2E_DOCKER=1`.

### Subprocess helpers
```python
# SOURCE: tests/e2e/_live.py:79-86, 115-123, 130-145
stop(proc, timeout); run_child(...); create_user(run, user_id, role) -> token  # token parsed from stdout, never printed
```
`create_user` takes a `run(*args)` callable, so it can wrap `docker compose run --rm --no-deps harness-ai python ...` unchanged.

### Stub script format
```json
// SOURCE: tests/e2e/scripts/example.json, tests/e2e/scripts/continue.json
{"contains": "please be slow", "delay_seconds": 5, "content": "..."}
```

### In-network docker recipe
```bash
# SOURCE: scripts/test-db-in-network.sh:39-47, 73-77
export MSYS_NO_PATHCONV=1      # Git Bash path rewriting off
docker compose build harness-ai; image="$(docker compose config --images harness-ai)"
```

### SSE keep-alive contract being measured
```python
# SOURCE: app/services/v1_sse.py:32, 111-127
KEEPALIVE = ": keep-alive\n\n"
# "The first keep-alive comes one interval after commit." Headers go out at commit.
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `Caddyfile` | UPDATE | Add `/v1/*` to `@backend_routes`. Add the `encode` SSE exclusion only if Task 1 shows buffering. The file is **CRLF**: use the Edit tool |
| `tests/test_caddyfile_routes.py` | CREATE | Docker-free: every harness route and Reflex reserved route is matched, the static routes are not, and the matcher list is pinned |
| `tests/e2e/docker/compose.smoke.yml` | CREATE | Override: `libsql` service, `stub` sidecar (`network_mode: service:harness-ai`), harness env overrides |
| `tests/e2e/scripts/docker_smoke.json` | CREATE | Stub rules: quick answer, 30 s slow answer, 5 s concurrency answer, `/query` answer |
| `tests/e2e/docker_smoke_probe.py` | CREATE | Stdlib + httpx probe run inside the container. Emits one JSON object (direct-vs-Caddy comparison, keep-alive timings, route checks, concurrency numbers) |
| `tests/e2e/test_docker_smoke.py` | CREATE | `@pytest.mark.e2e` module: compose lifecycle, user bootstrap, runs the probe in-container plus one host-side check, asserts the ACs, writes `smoke.json` for the report |
| `tests/e2e/scripts/README.md` | UPDATE | One paragraph for `docker_smoke.json` and the run command |

No change under `app/`, to `docker-compose.yml`, to `Dockerfile` or to any pre-epic test. That last one matters because of the `_PRE_EPIC_UNTOUCHED_TESTS` byte pin (memory, STORY-009).

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: Spike: does `encode gzip` buffer SSE in the installed Caddy?

- **File**: none committed (scratchpad only)
- **Action**: MEASURE
- **Implement**:
  1. Start Docker Desktop if needed (`%LOCALAPPDATA%\Programs\DockerDesktop\Docker Desktop.exe`, then `until docker info`).
  2. Build: `docker compose -p harness-smoke build harness-ai`. Record `docker compose -p harness-smoke run --rm --no-deps --entrypoint caddy harness-ai version`. The Dockerfile installs Caddy unpinned from the cloudsmith `stable` repo, so the version is a fact of this build, not of the repo.
  3. With the Task 2/3 files drafted, bring the stack up with `/v1/*` already in the matcher. In-container, stream a 30 s stub request with `V1_SSE_KEEPALIVE_SECONDS=10` and `Accept-Encoding: gzip`, once through `:8001` and once through `:8095`. Timestamp each decoded `: keep-alive`, and record the `Content-Encoding` response header.
- **Decide**:
  - Keep-alives arrive through Caddy at about 10 s and 20 s (within 2 s) → the Caddyfile change is the matcher token only.
  - They arrive late or bunched at the end → replace `encode gzip` with an `encode { gzip; match { ... not header Content-Type text/event-stream* } }` block. Take the exact `match` syntax from Caddy's docs for the recorded version (context7 / caddyserver.com). Add a `#` comment naming PRD-015 Section 7.6 and this spike's measurement. Re-measure.
- **Validate**: the numbers and the Caddy version go in the report's spike section.

### Task 2: Caddyfile route

- **File**: `Caddyfile`
- **Action**: UPDATE (Edit tool, which keeps CRLF)
- **Implement**: `@backend_routes path /_event/* /ping /_upload /_upload/* /query /audit /stats /health /v1/*`, with `/v1/*` appended last. Make no other change unless Task 1 required the encode block. Caddy's `*` suffix wildcard spans slashes, so `/v1/models/openai/gpt-4o` matches. Do not add a bare `/v1` entry, because the app has no route there and it would stay a static 404, as it is today.
- **Validate**: `git diff main -- Caddyfile` shows one changed line (plus the encode block if Task 1 required it). `docker compose ... run --rm --no-deps --entrypoint caddy harness-ai validate --config /app/Caddyfile --adapter caddyfile` (with `PORT`/`BACKEND_INTERNAL_PORT` set) exits 0.

### Task 3: Unit test: the matcher covers every harness route

- **File**: `tests/test_caddyfile_routes.py`
- **Action**: CREATE
- **Implement** (no Docker, no storage, so it runs under `-m "not db"`; ASCII-only output):
  - Parse the single `@backend_routes path ...` line from `Caddyfile` (`read_text`, `splitlines()`, which handles CRLF). Assert the line appears exactly once.
  - `_caddy_path_matches(pattern, path)` implements the subset of Caddy path matching the file uses: an exact match, or a trailing `*` as a prefix match. Assert that no pattern uses another wildcard form, so a future `*` in the middle fails loudly instead of being mis-modelled.
  - **Every harness route is matched.** Take paths from `app.main.app` with the `_IncludedRouter` descent (mirror `tests/test_route_reservations.py:13-23`, restated). Concretize path params (`{model_id:path}` becomes `openai/gpt-4o`, and any other `{x}` becomes `x`). Exclude FastAPI's own `/openapi.json`, `/docs`, `/docs/oauth2-redirect` and `/redoc`, with a comment: they are not routed publicly today, and this story does not change that. Each remaining path must be matched. This includes `/v1/chat/completions`, `/v1/models` and `/v1/models/{id}`. A future router added without a Caddy entry fails here.
  - **Reflex reserved routes are matched**: `/ping`, `/_event/x`, `/_upload`, `/_upload/x`.
  - **Static routes are not**: `/`, `/admin/audit`, `/reports`, `/v1` (bare), `/v1x`.
  - **Pin**: the matcher's token tuple equals `("/_event/*", "/ping", "/_upload", "/_upload/*", "/query", "/audit", "/stats", "/health", "/v1/*")`. A docstring explains that this restates the list on purpose, as `tests/test_admin_shell.py:55-67` does.
  - Set `OPENROUTER_API_KEY` / `ADMIN_TOKEN` with `os.environ.setdefault` before `from app.main import app`, as `tests/test_route_reservations.py:1-7` does.
- **Mutation check**: temporarily drop `/v1/*` from the Caddyfile and confirm the coverage test fails and names `/v1/chat/completions`. Then restore it.
- **Validate**: `C:\Users\tobip\.venvs\harness-ai\Scripts\python.exe -m pytest tests/test_caddyfile_routes.py -v`

### Task 4: Stub script for the smoke

- **File**: `tests/e2e/scripts/docker_smoke.json`
- **Action**: CREATE
- **Implement**: rules, matched against the last user message, each with a distinct marker string. The duplicate checker spans `/v1` and `/query`, so every probe prompt also carries a per-request nonce.
  - `"SMOKE-SLOW"`: `delay_seconds: 30`, with fixed content (AC 3).
  - `"SMOKE-WAVE"`: `delay_seconds: 5` (concurrency measurement).
  - `"SMOKE-QUERY"`: fixed content for `/query`.
  - `default`: fixed content with fixed `usage`, so the direct-vs-Caddy comparison has a known answer.
- **Validate**: `python scripts/stub_openrouter.py --port 0 --script tests/e2e/scripts/docker_smoke.json` prints `listening on` (the script loads), then stop it.

### Task 5: Compose override

- **File**: `tests/e2e/docker/compose.smoke.yml`
- **Action**: CREATE
- **Implement**:
  - `libsql`: image `ghcr.io/tursodatabase/libsql-server:latest`, `environment: {SQLD_NODE: primary}`, no `ports`.
  - `harness-ai`: `image: harness-smoke-harness-ai:local` (tags the build so `stub` can reuse it), `depends_on: [libsql]`, `environment:` with these keys:
    - `DATABASE_URL=http://libsql:8080` and `TURSO_AUTH_TOKEN=`
    - `OPENROUTER_BASE_URL=http://127.0.0.1:9100/v1` and `OPENROUTER_API_KEY=smoke-stub-key`
    - `ADMIN_TOKEN=${HARNESS_SMOKE_ADMIN_TOKEN:?}` (the test generates it)
    - `MODEL_ALLOWLIST=openai/gpt-4o,anthropic/claude-3.5-sonnet`
    - `V1_SSE_KEEPALIVE_SECONDS=10` and `PIPELINE_MAX_WORKERS=${HARNESS_SMOKE_WORKERS:-4}`
    - `USAGE_REQUESTS_PER_MINUTE=*=600`, so the concurrency burst is not rate-limited
  - `stub`: `image: harness-smoke-harness-ai:local`, `pull_policy: never`, `network_mode: "service:harness-ai"`, `command: python scripts/stub_openrouter.py --host 127.0.0.1 --port 9100 --script tests/e2e/scripts/docker_smoke.json`. If compose tries to pull or build `stub` before `harness-ai` is tagged, use `build: {context: ../../..}` on `stub` instead, which costs nothing because of the layer cache, and record which one worked.
  - The header comment states D-A to D-C and the run command.
- **Validate**: `PORT=8095 HARNESS_SMOKE_ADMIN_TOKEN=x docker compose -p harness-smoke -f docker-compose.yml -f tests/e2e/docker/compose.smoke.yml config` renders without error. Then check that `stub` shows `network_mode: service:harness-ai`.

### Task 6: In-container probe

- **File**: `tests/e2e/docker_smoke_probe.py`
- **Action**: CREATE
- **Implement**: a module runnable as `python -m tests.e2e.docker_smoke_probe --token T --admin-token A --direct http://127.0.0.1:8001 --caddy http://127.0.0.1:$PORT --nonce N`. It uses httpx, which is already in `requirements.txt` (check that it is in the runtime image), and does no assertions: it prints one ASCII JSON object to stdout and never prints tokens.
  - **compare**: for `base in (direct, caddy)`:
    - non-streaming `POST /v1/chat/completions`: status, `object`, `choices[0].message.content`, `finish_reason`, `usage`, and whether `id` matches `chatcmpl-harness-\d+`
    - streaming: status, `content-type`, the parsed `data:` events with `id`/`created` normalised, and whether it ends in `[DONE]`
    - Prompts differ per base, through the nonce, because of the duplicate checker.
  - **keepalive**: through `caddy` only, with `Accept-Encoding: gzip`, stream a `SMOKE-SLOW` prompt. Record `t0` at response headers, then the time of each decoded `: keep-alive` and of the first `data:` (from `iter_bytes`, since httpx decodes gzip incrementally). Also record `content-encoding`. Repeat once against `direct` as the baseline.
  - **routes** through `caddy`:
    - `GET /`: status and content-type
    - `GET /admin/audit`: status (static `try_files`)
    - `GET /ping`: status and body (Reflex backend)
    - `GET /health`
    - `POST /query` with a `SMOKE-QUERY` prompt: status and `response`
    - `GET /v1/models`: the list of ids
  - **concurrency** (PRD Risk 6): send N streamed `SMOKE-WAVE` requests at once through `caddy`, using a thread pool or `asyncio.gather` with one `httpx.AsyncClient` and a high connection limit. N defaults to `2 * workers`, and `workers` is passed in. Record each request's time-to-headers and time-to-`[DONE]`, then the wall total.
- **Validate**: `python -m py_compile tests/e2e/docker_smoke_probe.py`. Exercised for real in Task 7.

### Task 7: The smoke test module

- **File**: `tests/e2e/test_docker_smoke.py`
- **Action**: CREATE
- **Implement**:
  - `pytestmark = pytest.mark.e2e`. It is also skipped with `pytest.fail(recipe)`-style guidance unless `HARNESS_E2E_DOCKER=1`, and `docker info` must succeed. Otherwise a plain `--run-e2e` run on a machine without Docker would fail. Mirror `test_continue.py:128-140`.
  - The module docstring maps tests to ACs (as `test_openai_sdk.py:1-32` does) and gives the run command:
    `HARNESS_E2E_DOCKER=1 python -m pytest tests/e2e/test_docker_smoke.py -m e2e --run-e2e -v -s`
  - **Module fixture `stack`**:
    1. Set `MSYS_NO_PATHCONV=1`, `PORT=8095`, `HARNESS_SMOKE_ADMIN_TOKEN=secrets.token_urlsafe(16)` and `HARNESS_SMOKE_WORKERS=4` in the compose child env.
    2. `compose build harness-ai`.
    3. `compose up -d libsql`.
    4. Retry `create_user` for up to 30 s, via `docker compose run --rm --no-deps harness-ai python scripts/manage_users.py create-user --user-id smoke-<nonce> --role user`. Do this before the harness starts, or startup fails with `RbacNotBootstrappedError`.
    5. `compose up -d harness-ai stub`.
    6. Wait for `GET http://127.0.0.1:8095/health` from the host, falling back to an in-container check if host forwarding stalls.
    - Teardown always runs `compose down -v` and prints `compose logs --no-color --tail 200` on failure. Every compose call uses `-p harness-smoke -f docker-compose.yml -f tests/e2e/docker/compose.smoke.yml`.
  - **Fixture `probe`**: `docker compose exec -T harness-ai python -m tests.e2e.docker_smoke_probe ...` with a timeout of about 180 s. It parses the JSON from the last stdout line and writes it to `<tmp>/smoke.json`, and the path is printed for the report.
  - **Tests**:
    - `test_v1_through_caddy_matches_the_backend` (AC 2): for both modes, the status, content, finish_reason, usage and event sequence through Caddy equal the direct ones. Streamed content-type is `text/event-stream` on both.
    - `test_keepalives_arrive_through_caddy_with_gzip_on` (AC 3): there are at least 2 keep-alives through Caddy. The k-th arrives at `k*10 +- 2` s after headers, and the first `data:` arrives after the last keep-alive. The `content-encoding` value is shown in the assertion message, so the report records whether gzip actually applied.
    - `test_reflex_routes_and_query_still_answer` (AC 4):
      - `/` is 200 `text/html`
      - `/admin/audit` is 200
      - `/ping` is 200
      - `/health` is `{"status":"ok"}`
      - `/query` is 200 with the stub's `SMOKE-QUERY` content
    - `test_v1_models_returns_the_allowlist` (AC 4): the ids equal the override's `MODEL_ALLOWLIST`, in order.
    - `test_published_port_answers_from_the_host`: one host-side `GET :8095/v1/models` and one streamed default request. This proves the front door outside the network. Mark the test `xfail(strict=False)` only if the Docker Desktop forwarding stall reproduces, and record that.
    - `test_executor_concurrency_measurement` (Risk 6, measurement): all N requests end in `[DONE]`. With N = 2 x workers and a 5 s stub delay, time-to-headers splits into two waves: about N/2 requests under 2 s and the rest at 5 s or more. The figures (p50/max time-to-headers per wave, the wall total) are printed for the report. The assertion is only the wave split, which is falsifiable: a non-queueing executor would put all N in wave 1.
  - Keep all output ASCII (cp1252 pipes, memory).
- **Validate**: run the command above. Expect 6 passed. It takes a few minutes, including the build (about 2 min cached).

### Task 8: Stub scripts README

- **File**: `tests/e2e/scripts/README.md`
- **Action**: UPDATE
- **Implement**: add `docker_smoke.json` to the intro list, as "(STORY-018)", and add one paragraph on what its rules are for. The Docker run command lives in the test module docstring. STORY-019 owns the top-level README.
- **Validate**: read it back.

---

## End-to-End Tests

- [ ] `pytest tests/test_caddyfile_routes.py -v` passes. With `/v1/*` removed it fails on `/v1/chat/completions`, and it passes again once restored.
- [ ] Spike (Task 1): Caddy version recorded, keep-alive arrival times through `:8001` and `:8095` with gzip requested, and the `Content-Encoding` seen.
- [ ] `HARNESS_E2E_DOCKER=1 python -m pytest tests/e2e/test_docker_smoke.py -m e2e --run-e2e -v -s` gives 6 passed, and `smoke.json` is saved for the report.
- [ ] `docker ps -a --filter name=harness-smoke` is empty afterwards (teardown worked). `harness-ai-harness-ai-1` and any `harness-libsql-*` containers are untouched.
- [ ] The concurrency figures (workers=4, N=8) are recorded in the report. Optionally rerun with `HARNESS_SMOKE_WORKERS=32` and N=40 to show the default, and record that too.

---

## Validation

```bash
cd "C:/Users/tobip/OneDrive/Documentos/prog/harness-ai"
PY="C:/Users/tobip/.venvs/harness-ai/Scripts/python.exe"
$PY -m pytest tests/test_caddyfile_routes.py tests/test_route_reservations.py tests/test_admin_shell.py -v
$PY -m pytest tests/ -m "not db" -q        # Docker-free, ~90 s
HARNESS_E2E_DOCKER=1 $PY -m pytest tests/e2e/test_docker_smoke.py -m e2e --run-e2e -v -s
# Full suite (handoff guards only a full run catches) on a throwaway libSQL :8086, under keep-awake:
HARNESS_TEST_LIBSQL_URL=http://127.0.0.1:8086 $PY -m pytest tests/ -q
git diff main -- Caddyfile              # one changed line (+ encode block only if Task 1 required it)
```

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| `encode gzip` buffers SSE in the installed Caddy | Task 1 measures it before anything else. The fix is an `encode` `match` excluding `text/event-stream`, with a comment. `flush_interval -1` is explicitly not the lever (D-E) |
| Caddy is unpinned in the Dockerfile, so a future `stable` could change encode behaviour | The smoke records `caddy version`. Pinning is out of scope; note it for STORY-019 or a follow-up |
| Reflex's backend (`reflex run --backend-only`, `api_transformer`) treats streaming differently from bare uvicorn | AC 2 compares Caddy against `:8001`, which is that exact process. Any difference from STORY-015's bare-uvicorn evidence shows up in the keep-alive baseline |
| Docker Desktop port forwarding stalls | Timing runs in-network (D-D). The host-side check is a single, separately named test |
| `.env` keys leak into the smoke container | The override sets every key the smoke depends on. The report lists the `.env` keys present (names only) |
| Duplicate checker refuses a repeated prompt across bases or reruns | Every prompt carries the run nonce plus a per-request suffix |
| RBAC bootstrap race (libsql not ready) | `create-user` retried for up to 30 s before `up harness-ai` |
| S3 sleep mid-run kills Docker Desktop | Run the full suite and the smoke under the keep-awake wrapper (`[uint32]2147483649`). If it is refused, run without it and say so |
| Image build cost (~2 min) on every run | The layer cache makes reruns cheap. Use `compose build` once per session |

---

## Acceptance Criteria

(Copied from story STORY-018)

- [ ] Given the `Caddyfile`, when it is read, then `@backend_routes` includes `/v1/*` and nothing else changed; a test asserts every harness route prefix (including `/v1`) is in the matcher.
- [ ] Given `docker compose up` with `OPENROUTER_BASE_URL` pointed at the stub, when `POST /v1/chat/completions` is sent to Caddy's port, non-streaming and streaming, then both answer as they do against `uvicorn` directly.
- [ ] Given a stub delay of 30 s and `V1_SSE_KEEPALIVE_SECONDS=10`, when a streamed request goes through Caddy with `encode gzip` in force, then the client receives each keep-alive within 2 s of its interval (Caddy does not buffer `text/event-stream`).
- [ ] Given the smoke, when it runs, then the Reflex routes and `/query` still answer through Caddy, and `/v1/models` returns the allowlist.
- [ ] Executor-concurrency measurement (PRD Risk 6) taken and recorded in the report
- [ ] All tasks completed
- [ ] `-m "not db"` and full suite green; no file under `app/` changed
- [ ] Follows existing patterns
