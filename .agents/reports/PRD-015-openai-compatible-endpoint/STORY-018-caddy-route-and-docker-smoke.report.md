---
story: STORY-018
prd: PRD-015
plan: .agents/plans/PRD-015-openai-compatible-endpoint/completed/STORY-018-caddy-route-and-docker-smoke.plan.md
epic_branch: epic/PRD-015-openai-compatible-endpoint
commit: c472495
status: COMPLETE
completed: 2026-10-30
---

# Implementation Report — STORY-018: Caddy routes /v1/*; Docker smoke with keep-alive through Caddy

**Plan**: `.agents/plans/PRD-015-openai-compatible-endpoint/completed/STORY-018-caddy-route-and-docker-smoke.plan.md`
**Epic Branch**: `epic/PRD-015-openai-compatible-endpoint`
**Commit**: `c472495`

## Summary

- **Caddyfile (AC 1).** `/v1/*` is appended to `@backend_routes`. `git diff main -- Caddyfile` is one changed line. `tests/test_caddyfile_routes.py` reads every route from `app.main.app` and fails if Caddy would send one to the static file server. It also pins the matcher list, and checks that the Reflex pages and the bare `/v1` stay static.
- **`encode gzip` does not buffer SSE (AC 3, PRD Risk 1).** The installed Caddy is **v2.11.7**. It gzips `text/event-stream` (`Content-Encoding: gzip` on the response) and still flushes every frame. Through Caddy, keep-alives arrived at **9.999 s, 20.0 s and 30.021 s** on a 30 s stub delay with `V1_SSE_KEEPALIVE_SECONDS=10`. From the backend port they arrived at 10.006 s, 20.013 s and 30.038 s. **No `encode` change was needed.**
- **Docker smoke (AC 2, AC 4).** `tests/e2e/test_docker_smoke.py` brings up the real image under its own compose project, using `tests/e2e/docker/compose.smoke.yml`:
  - a throwaway libSQL service;
  - the stub upstream inside the harness container's network namespace;
  - `PORT=8095`.

  An in-container probe found the following:
  - **Non-streaming and streaming `/v1/chat/completions` through Caddy equal the backend port.** The comparison covers status, content, `finish_reason`, `usage`, the event sequence and `[DONE]`.
  - **`/`, `/admin/audit`, `/ping`, `/health` and `/query` answer through Caddy.**
  - **`/v1/models` returns the allowlist.**
  - **The published port works from the host.**
- **Executor concurrency (PRD Risk 6).** With 2 × `PIPELINE_MAX_WORKERS` streamed requests, exactly `PIPELINE_MAX_WORKERS` of them commit at once, and the rest get no response headers until a worker frees. The figures are below.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Spike: does `encode gzip` buffer SSE in the installed Caddy? | scratchpad `spike.sh` (not committed) | ✅ no: one-token change only |
| 2 | Caddyfile route | `Caddyfile` | ✅ |
| 3 | Matcher-coverage unit test, plus mutation check | `tests/test_caddyfile_routes.py` | ✅ |
| 4 | Stub script for the smoke | `tests/e2e/scripts/docker_smoke.json` | ✅ |
| 5 | Compose override | `tests/e2e/docker/compose.smoke.yml` | ✅ (plus a `PORT` pin, see Deviations) |
| 6 | In-container probe | `tests/e2e/docker_smoke_probe.py` | ✅ |
| 7 | Smoke test module | `tests/e2e/test_docker_smoke.py` | ✅ 6/6 |
| 8 | Stub scripts README | `tests/e2e/scripts/README.md` | ✅ |
| — | Unit tests for the probe's parser, timer and verdict helpers | `tests/test_docker_smoke_probe.py` | ✅ (added, see Deviations) |

## Decisions (as recorded in the plan)

- **How the stub is reached.** The `stub` service has `network_mode: "service:harness-ai"` and runs from the same image (`harness-smoke-harness-ai:local`, `pull_policy: never`; this worked first time, so no `build:` fallback was needed). The harness reaches it at `OPENROUTER_BASE_URL=http://127.0.0.1:9100/v1`, which is loopback, so `app/config.py`'s validator is unchanged.
- **The database.** A `libsql` service (`ghcr.io/tursodatabase/libsql-server:latest`) with no published port, at `DATABASE_URL=http://libsql:8080`. No token is needed over plain `http://`. `down -v` removes it.
- **The compose project.** `-p harness-smoke`, port 8095. `docker-compose.yml` and the `Dockerfile` are unchanged. The existing `harness-ai-harness-ai-1` and `libsql` containers on this machine were not touched, and `docker ps -a --filter name=harness-smoke` was empty after every run.
- **Where the probe runs.** Inside the container (`docker compose exec -T -e SMOKE_TOKEN harness-ai python -m tests.e2e.docker_smoke_probe`). The token reaches the probe through the environment, never on a command line. "Directly" means `http://127.0.0.1:8001`, the `reflex run --backend-only` process that Caddy proxies to.

## Task 1 spike: Caddy and gzip on SSE

`docker compose ... run --rm --no-deps --entrypoint caddy harness-ai version` printed `v2.11.7 h1:yj0Y4fYZGPkSvibBJ1sTWE33xC0fxztVyXEW5iIdUT4=`. The Dockerfile installs Caddy unpinned from cloudsmith's `stable` repo, so this version belongs to this build, not to the repository.

Each stream used a 30 s stub delay with `V1_SSE_KEEPALIVE_SECONDS=10`. Times are seconds after the response headers.

| Target | `Accept-Encoding` | `Content-Encoding` | Keep-alives | First `data:` |
|---|---|---|---|---|
| Caddy `:8095` | gzip | **gzip** | 10.012, 20.020, 30.051 | 30.069 |
| Caddy `:8095` | identity | — | 10.011, 20.019, 30.050 | 30.069 |
| Backend `:8001` | gzip | — (the backend does not compress) | 10.010, 20.021, 30.052 | 30.070 |

The response headers arrived 0.08 s after the request, which is commit. Caddy's encoder compresses the stream, and it flushes each frame as soon as the proxy flushes it. Per Caddy's docs, the proxy does that by itself for `text/event-stream`, so `flush_interval -1` would have changed nothing. The fallback `encode` block was not needed, and the Caddyfile has no other change.

The spike also found a bug in the probe. The first count showed a fourth "keep-alive" at 30.07 s, because the stub's slow answer reads `...: keep-alives came through` and the probe was matching a bare `b": keep-alive"`. The probe now matches the server's whole frame, `": keep-alive\n\n"` (`app/services/v1_sse.py:32`). `tests/test_docker_smoke_probe.py` pins this: with the bare match the timer tests fail, which I checked by reverting the fix temporarily.

## Executor concurrency (PRD Risk 6)

These runs were through Caddy, in-network, with every request streamed, a 5 s stub delay (`SMOKE-WAVE`) and N = 2 × workers. "Headers" is the time to the response headers, which go out at commit.

| `PIPELINE_MAX_WORKERS` | N | Committed at once (headers) | Queued (headers) | Totals | Wall |
|---|---|---|---|---|---|
| 4 | 8 | 4 requests, 0.063–0.078 s | 4 requests, 5.180–5.182 s | 5.18 s ×4, 10.24–10.25 s ×4 | 10.26 s |
| 32 (default) | 64 | 32 requests, 0.151–0.755 s | 32 requests, 5.194–6.342 s | 5.19–6.30 s ×32, 10.23–11.62 s ×32 | 11.79 s |

(An earlier 4-worker run gave the same split: 0.039–0.073 s and 5.158–5.162 s, wall 10.23 s.)

**Finding.** A request that finds no free worker gets no response bytes until a running pipeline finishes. Before commit it has no response yet, so no keep-alive protects it either. Every pipeline holds its worker for the whole upstream call, so a queued streamed client waits up to one full upstream latency with nothing on the wire. With real upstream calls of tens of seconds that wait is long. A client whose first-byte timeout is shorter than that latency fails. The exposure is the same as `/query`'s, as PRD Risk 6 says, and `PIPELINE_MAX_WORKERS` is the lever. Nothing failed here. All 72 measured requests ended in `[DONE]`. At 32 workers the pre-commit steps for 32 simultaneous requests took up to 0.76 s, the PII analyzer included. This is worth a line in STORY-019's README section on operating `/v1`.

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | ✅ (`tests/test_caddyfile_routes.py` imports `app.main.app`; the image starts and answers `/health`) |
| Frontend lint | n/a (no frontend change) |
| New unit tests | ✅ 17 passed (`test_caddyfile_routes.py` 6, `test_docker_smoke_probe.py` 11) |
| Mutation: `/v1/*` removed from the Caddyfile | ✅ 2 failed: the pin, and coverage naming `/v1/chat/completions`, `/v1/models`, `/v1/models/{model_id:path}`. File restored byte for byte (`cmp`) |
| Mutation: bare keep-alive match | ✅ 3 failed (the two timer tests, and the parser test that builds its frames from the same constant). Restored, `cmp` clean |
| `-m "not db"` (`HARNESS_TEST_LIBSQL_URL=http://127.0.0.1:9`) | ✅ 3,508 passed / 62 skipped, 93 s |
| Full suite (throwaway libSQL `:8086`, keep-awake wrapper) | ✅ **4,932 passed / 63 skipped**, 347 s, no flakes |
| Docker smoke | ✅ 6/6 (78 s with a cached build) |
| Smoke at 32 workers (`-k concurrency`) | ✅ 1/1 |
| `git diff main -- Caddyfile` | one changed line |
| Files under `app/` changed | none |

## End-to-end run

```bash
HARNESS_E2E_DOCKER=1 python -m pytest tests/e2e/test_docker_smoke.py -m e2e --run-e2e -v -s
# test_v1_through_caddy_matches_the_backend          PASSED
# test_keepalives_arrive_through_caddy_with_gzip_on  PASSED
# test_reflex_routes_and_query_still_answer          PASSED
# test_v1_models_returns_the_allowlist               PASSED
# test_published_port_answers_from_the_host          PASSED
# test_executor_concurrency_measurement              PASSED
# 6 passed in 78.49s
HARNESS_SMOKE_WORKERS=32 HARNESS_E2E_DOCKER=1 python -m pytest tests/e2e/test_docker_smoke.py -m e2e --run-e2e -v -s -k concurrency
# 1 passed, 5 deselected in 55.62s
```

Probe results from the passing run (abridged):

- `/`: 200 `text/html`.
- `/admin/audit`: 308 to `/admin/audit/`, then 200 `text/html`.
- `/ping`: 200 `"pong"`.
- `/health`: 200 `{"status":"ok"}`.
- `/query`: 200 `harness smoke query answer: query still works`.
- `/v1/models`: 200 `["openai/gpt-4o", "anthropic/claude-3.5-sonnet"]`.
- Keep-alives:

  | Target | Keep-alives (s) | `data:` (s) | `Content-Encoding` |
  |---|---|---|---|
  | `caddy_gzip` | 9.999, 20.0, 30.021 | 30.048 | gzip |
  | `caddy_identity` | 10.0, 20.001, 30.022 | — | — |
  | `direct_gzip` | 10.006, 20.013, 30.038 | — | — |

The host-side check through Docker Desktop's published port passed on every run. The forwarding stall from PRD-014 STORY-006 did not reproduce, so no `xfail` was added.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `Caddyfile` | UPDATE | +1/-1 |
| `tests/test_caddyfile_routes.py` | CREATE | +146 |
| `tests/test_docker_smoke_probe.py` | CREATE | +159 |
| `tests/e2e/docker/compose.smoke.yml` | CREATE | +57 |
| `tests/e2e/docker_smoke_probe.py` | CREATE | +302 |
| `tests/e2e/test_docker_smoke.py` | CREATE | +256 |
| `tests/e2e/scripts/docker_smoke.json` | CREATE | +29 |
| `tests/e2e/scripts/README.md` | UPDATE | +7/-1 |
| `.agents/plans/.../completed/STORY-018-...plan.md` | CREATE (archived) | +323 |

## Deviations from Plan

1. **`PORT` is pinned in the override.** The plan did not foresee this. The rendered compose config showed that `.env` sets `PORT=8000`, and `env_file` beats the image's `ENV PORT`, so Caddy would have listened on 8000 inside while compose published 8095. The override now sets `PORT: ${PORT:-8000}`. **The base `docker-compose.yml` has the same latent mismatch whenever the shell's `PORT` and `.env`'s `PORT` differ.** I left it alone because it is out of scope; it is noted here for STORY-019.
2. **Keep-alive matching uses the whole frame.** The spike's false positive is described above.
3. **`/admin/audit` answers 308, then 200.** The plan expected a 200 from the first request. Caddy's `file_server` redirects the directory path to `/admin/audit/`, as it always has, and that is unrelated to this story. The probe records the first hop and the redirected result, and the test asserts that the redirect lands on a 200 HTML page. The first smoke run failed on this assertion alone; the rerun was 6/6.
4. **I added `tests/test_docker_smoke_probe.py`.** It was not in the plan. The smoke needs Docker and `--run-e2e`, so the logic behind its verdicts gets everyday coverage here: the SSE parser, the keep-alive timer, the window check and the wave split. The timer test runs against a local server that gzip-flushes each frame, as Caddy does. To make the verdicts testable, the probe gained two pure helpers, `keepalive_problems` and `split_waves`. The test module asserts on what they return. The probe itself still asserts nothing in the container.
5. **The keep-alive section runs its three timed streams in parallel**, which keeps the probe at about 30 s instead of 90 s. They do not compete: three pipelines use three of the four workers.
6. **Keys from `.env` that reach the smoke container** (names only, from `docker compose config`): `CHAT_HISTORY_ENABLED`, `CHAT_SESSION_LIMIT`, `HOST`, `LOG_LEVEL`, `PII_ENTITIES`, `PII_NLP_MODEL`, `PII_REDACTION_ENABLED`, `PII_SCORE_THRESHOLD`, `RBAC_DEFAULT_ROLE`, `RBAC_ENABLED`, `RBAC_ROLES_FILE`, `REPORTS_AGENTS_DIR`, `REPORTS_REPO_URL`, plus the secrets the override replaces. None of them changes what the smoke asserts.

## Findings (for STORY-019 and the PRD)

- PRD Section 7.6's claim that "Caddy's encoder flushes on SSE responses" holds for Caddy v2.11.7. The Dockerfile does not pin Caddy, so a future `stable` could change this. The smoke catches that, and pinning is a possible follow-up.
- PRD Risk 6: requests queued for a pipeline worker get no first byte, and therefore no keep-alive, until a worker frees. See the concurrency section.
- `docker-compose.yml` publishes the shell's `PORT` while Caddy listens on `.env`'s `PORT` (Deviation 1).

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_caddyfile_routes.py` | matcher pinned; only modelled wildcards; every harness route proxied (incl. three `/v1` routes); Reflex reserved routes proxied; static paths fall through; path-model semantics |
| `tests/test_docker_smoke_probe.py` | event parser normalises id/created and keeps `[DONE]`; non-harness id flagged; timer counts keep-alives and ignores answer text (gzip, identity); gzip frames decode whole; window check accepts on-time, flags late, bunched, too few / no data / no `[DONE]`, failed request; wave split |
| `tests/e2e/test_docker_smoke.py` | the six e2e tests listed under "End-to-end run" |

## Acceptance Criteria

- [x] Given the `Caddyfile`, when it is read, then `@backend_routes` includes `/v1/*` and nothing else changed; a test asserts every harness route prefix (including `/v1`) is in the matcher.
- [x] Given `docker compose up` with `OPENROUTER_BASE_URL` pointed at the stub, when `POST /v1/chat/completions` is sent to Caddy's port, non-streaming and streaming, then both answer as they do against `uvicorn` directly (the backend process on `:8001`).
- [x] Given a stub delay of 30 s and `V1_SSE_KEEPALIVE_SECONDS=10`, when a streamed request goes through Caddy with `encode gzip` in force, then the client receives each keep-alive within 2 s of its interval (actual: within 0.03 s; the response was gzip-encoded).
- [x] Given the smoke, when it runs, then the Reflex routes and `/query` still answer through Caddy, and `/v1/models` returns the allowlist.
- [x] Executor-concurrency measurement (PRD Risk 6) taken and recorded, at 4 and 32 workers.
- [x] All tasks completed.
- [x] `-m "not db"` and full suite green; no file under `app/` changed.
- [x] Follows existing patterns.
