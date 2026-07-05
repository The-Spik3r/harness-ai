---
story: STORY-008
prd: PRD-002
slug: docker-single-port-packaging
title: "Multi-stage Docker packaging for single-port image"
type: technical
complexity: MEDIUM
epic_branch: epic/PRD-002-reflex-chat-ui        # all stories commit here, no per-story branch
created: 2026-07-05
---

# Plan: Multi-stage Docker packaging for single-port image

## Summary

Replace the current single-stage `Dockerfile` (`python:3.11-slim` running `python app.py`) with a two-stage build that (1) uses a Python+Node/Bun builder stage to run `reflex export --frontend-only --no-zip`, producing a static frontend bundle, then (2) ships a Python-only final stage that serves that static bundle *and* proxies Reflex's/the harness's dynamic routes to an internally-bound Reflex backend process, using Caddy as the single-port front door. This is the officially documented Reflex pattern for "single port, no Node/Bun in the final image" (`reflex-dev/reflex`'s `docker-example/production-one-port` reference), adapted to this repo: no Redis (single-instance app, PRD explicitly out-of-scope for multi-instance), and the Caddyfile's route matcher is extended to cover this repo's own routes (`/query`, `/audit`, `/stats`, `/health`) in addition to Reflex's reserved routes (`/_event`, `/ping`, `/_upload`), since our FastAPI app is mounted *inside* the Reflex ASGI app via `api_transformer` (STORY-003) rather than being a separate service.

Three non-obvious mechanics discovered during codebase exploration (not assumed from memory — verified against the installed `reflex==0.9.6.post1` source and the official Reflex GitHub example):

1. **`reflex run --env prod` (fullstack mode) always needs Node/Bun at runtime, even in single-port mode.** Reading `reflex/reflex.py::_run_prod` → `build.setup_frontend_prod` → `build.build()` shows that whenever Reflex runs with the frontend enabled, it unconditionally shells out to `bun run export` on every startup — there is no "skip if unchanged" cache check. STORY-003's own validation confirmed prod mode *does* collapse frontend+backend onto one port, but that convenience comes at the cost of requiring Bun at container start, which directly violates this story's AC5 ("no Node or Bun runtime present" in the final image). The only way to get single-port + zero Node/Bun at runtime is `--backend-only` mode plus a separate front door (Caddy) serving a *pre-exported* static bundle — exactly what Reflex's own `docker-example/production-one-port` does.
2. **Build-time import of `app.main` requires dummy secrets.** `chat_ui/chat_ui/chat_ui.py` does `from app.main import app as fastapi_app` at module scope, and `app/config.py::Settings` has no defaults for `OPENROUTER_API_KEY` / `ADMIN_TOKEN` — so *any* Reflex CLI command that imports the app (`reflex export` included) fails with a Pydantic validation error unless those two env vars are present. The builder stage must set placeholder values (never carried into the final image) purely so the import succeeds; real secrets still come from `docker-compose.yml`'s `env_file: .env` at runtime, unchanged.
3. **Moving Reflex's CWD to `chat_ui/` breaks the existing relative `DATABASE_URL`.** Reflex requires its process CWD to be the directory containing `rxconfig.py` (`chat_ui/`), but `docker-compose.yml`'s `DATABASE_URL: sqlite:///data/harness_ai.db` is a *relative* path that today resolves against the old `WORKDIR /app` (matching the `harness_data:/app/data` volume). Under the new CWD, `data/harness_ai.db` would resolve to `/app/chat_ui/data/harness_ai.db` instead, silently orphaning the persisted volume. Fix: change `docker-compose.yml` to the absolute-path form `sqlite:////app/data/harness_ai.db` (four slashes = absolute path in the SQLAlchemy/sqlite URL scheme), which resolves to the exact same on-disk location regardless of CWD.

## User Story

As a devops engineer
I want the chat UI and API packaged into one Docker image behind one port via a multi-stage build
So that `docker-compose up` keeps working exactly as it does today, with no new exposed ports or Node/Bun runtime shipped in the final image

## Story Reference

- Story file: `.agents/stories/PRD-002-reflex-chat-ui/STORY-008-docker-single-port-packaging.md`
- PRD: `.agents/PRDs/PRD-002-reflex-chat-ui/PRD.md`

## Metadata

| Field | Value |
|-------|-------|
| Type | technical |
| Complexity | MEDIUM |
| Systems Affected | `Dockerfile`, `docker-compose.yml`, `.dockerignore`, new `Caddyfile` |
| Story | STORY-008 |
| PRD | PRD-002 |
| Epic Branch | `epic/PRD-002-reflex-chat-ui` (commit directly on this branch) |

---

## Skills In Use

None. `story.skills: []`; `.agents/skills/` has no entries; no `SKILL.md` matches Docker/devops packaging. The Reflex-specific skills (`reflex-docs`, `reflex-process-management`) were consulted during exploration for CLI flag semantics but govern writing/running Reflex *app code*, not Docker packaging — not applicable to any task below.

---

## Patterns to Follow

### Existing single-stage Dockerfile (baseline to extend, not replace wholesale)
```dockerfile
// SOURCE: Dockerfile:1-12 (current)
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["python", "app.py"]
```

### Existing docker-compose.yml (extend, do not add services/ports)
```yaml
// SOURCE: docker-compose.yml:1-15 (current)
services:
  harness-ai:
    build: .
    ports:
      - "${PORT:-8000}:${PORT:-8000}"
    env_file:
      - .env
    environment:
      DATABASE_URL: sqlite:///data/harness_ai.db
    volumes:
      - harness_data:/app/data

volumes:
  harness_data:
```

### Official Reflex single-port-no-runtime reference (adapt, don't copy verbatim — drop Redis, add our routes)
```dockerfile
// SOURCE: github.com/reflex-dev/reflex, docker-example/production-one-port/Dockerfile (fetched this session)
FROM python:3.13 as builder
RUN python -m venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY rxconfig.py ./
RUN reflex init
COPY . .
ARG PORT API_URL
RUN REFLEX_API_URL=${API_URL:-http://localhost:$PORT} reflex export --loglevel debug --frontend-only --no-zip \
    && mv .web/build/client/* /srv/ && rm -rf .web

FROM python:3.13-slim
RUN apt-get update -y && apt-get install -y caddy redis-server && rm -rf /var/lib/apt/lists/*
ENV PATH="/app/.venv/bin:$PATH" PORT=$PORT REFLEX_API_URL=... REFLEX_REDIS_URL=redis://localhost
WORKDIR /app
COPY --from=builder /app /app
COPY --from=builder /srv /srv
STOPSIGNAL SIGKILL
EXPOSE $PORT
CMD caddy start && redis-server --daemonize yes && exec reflex run --env prod --backend-only
```

### Official Caddyfile (extend the `@backend_routes` matcher with this repo's own routes)
```
// SOURCE: github.com/reflex-dev/reflex, docker-example/production-one-port/Caddyfile (fetched this session)
:{$PORT}
encode gzip
@backend_routes path /_event/* /ping /_upload /_upload/*
handle @backend_routes {
    reverse_proxy localhost:8000
}
root * /srv
route {
    try_files {path} {path}/ /404.html
    file_server
}
```
Note: `/404.html` in `try_files` is intentional, not a typo — `reflex export`'s `build()` step (`reflex/utils/build.py`, `_duplicate_index_html_to_parent_directory` + the SPA-fallback copy right after) already copies the SPA entry point to `404.html` in the exported static output specifically so a reverse proxy can use it as the catch-all fallback.

### Reserved + harness routes that must reach the backend (do not let Caddy's static handler shadow these)
```python
// SOURCE: app/main.py:20-27 (harness routes) + PRD-002 Section 9 (Reflex-reserved routes, already verified non-colliding by tests/test_route_reservations.py from STORY-003)
app.include_router(query_router.router)   # POST /query
app.include_router(admin_router.router)   # GET /audit, GET /stats
@app.get("/health") ...                   # GET /health
# Reflex reserved (Section 9): /ping, /_event, /_upload
```

### CLI flags confirmed against the installed reflex==0.9.6.post1 (not assumed)
```
// SOURCE: `python -m reflex run --help`, and reflex/reflex.py:227-259 (_run_prod) this session
--env prod            # required for single-port collapse (frontend_port := backend_port := port)
--backend-only         # skips setup_frontend_prod()/build() entirely -> no Bun invoked
--backend-port INT     # reflex/reflex.py:456-457, envvar REFLEX_BACKEND_PORT
--backend-host TEXT
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `Caddyfile` | CREATE | Single-port front door: serves the pre-exported static frontend, reverse-proxies Reflex-reserved + harness API routes to the internal backend port |
| `Dockerfile` | UPDATE | Multi-stage: builder (Python + Node/Bun via `reflex init`/`reflex export`) discarded; final stage is Python-only + Caddy, runs `reflex run --env prod --backend-only` |
| `docker-compose.yml` | UPDATE | Pass `PORT` as a build arg (needed to bake `REFLEX_API_URL` and Caddy's listen port at image-build time); switch `DATABASE_URL` to an absolute path so it survives Reflex's CWD requirement (see mechanic 3 above) |
| `.dockerignore` | UPDATE | Exclude `chat_ui/`'s generated/dev artifacts (`.web/`, `.states/`, `__pycache__/`, `harness_ai.db`, `reflex.log`) and nested `.env` files (root pattern `.env` does not recurse into `chat_ui/.env`) so no build-time secret or stale local state leaks into the image |

No changes to `app/`, `chat_ui/chat_ui/*.py`, or `tests/` — this story is packaging-only, per its own scope and STORY-007's already-green test suite.

---

## Tasks

### Task 1: Add `Caddyfile` at repo root

- **File**: `Caddyfile`
- **Action**: CREATE
- **Implement**:
  ```
  :{$PORT}

  encode gzip

  @backend_routes path /_event/* /ping /_upload /_upload/* /query /audit /stats /health
  handle @backend_routes {
      reverse_proxy localhost:{$BACKEND_INTERNAL_PORT}
  }

  root * /srv
  route {
      try_files {path} {path}/ /404.html
      file_server
  }
  ```
  `PORT` is the externally-exposed port (same `${PORT:-8000}` the harness has always used). `BACKEND_INTERNAL_PORT` is a new container-internal-only port (fixed at `8001`, never exposed/mapped) that the Reflex backend process binds to; Caddy is the only process actually listening on `PORT`. This avoids a bind conflict between Caddy and the backend both wanting Reflex's historical default of 8000 when `PORT` is left at its default.
- **Mirror**: official Caddyfile pattern above, route matcher extended with this repo's four routes.
- **Validate**: `caddy validate --config Caddyfile --adapter caddyfile` (run inside the built image in Task 5; no local Caddy install required beforehand).

### Task 2: Rewrite `Dockerfile` as a multi-stage build

- **File**: `Dockerfile`
- **Action**: UPDATE
- **Implement**:
  ```dockerfile
  # ---- builder: compiles the static frontend only; discarded below ----
  FROM python:3.11 AS builder

  WORKDIR /app
  COPY requirements.txt .
  RUN pip install --no-cache-dir -r requirements.txt

  COPY . .

  # Build-time-only placeholders so importing app.main (triggered by `reflex
  # export`, which imports chat_ui.chat_ui to introspect the component tree)
  # doesn't fail Settings validation. Never present in the final stage.
  ENV OPENROUTER_API_KEY=build-placeholder \
      ADMIN_TOKEN=build-placeholder \
      DATABASE_URL=sqlite:///:memory:

  WORKDIR /app/chat_ui
  RUN reflex init

  ARG PORT=8000
  RUN REFLEX_API_URL=http://localhost:${PORT} reflex export --loglevel debug --frontend-only --no-zip \
      && mkdir -p /srv \
      && mv .web/build/client/* /srv/ \
      && rm -rf .web

  # ---- final: Python + Caddy only, no Node/Bun ----
  FROM python:3.11-slim

  RUN apt-get update && apt-get install -y --no-install-recommends \
        debian-keyring debian-archive-keyring apt-transport-https curl gnupg \
      && curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg \
      && curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list \
      && apt-get update && apt-get install -y caddy \
      && apt-get purge -y curl gnupg apt-transport-https && apt-get autoremove -y \
      && rm -rf /var/lib/apt/lists/*

  WORKDIR /app
  COPY requirements.txt .
  RUN pip install --no-cache-dir -r requirements.txt

  COPY . .
  COPY --from=builder /srv /srv
  COPY Caddyfile /app/Caddyfile

  ARG PORT=8000
  ENV PORT=${PORT} \
      BACKEND_INTERNAL_PORT=8001 \
      REFLEX_ENV=prod \
      REFLEX_API_URL=http://localhost:${PORT}

  # Reflex does not reliably handle SIGTERM for graceful shutdown; match the
  # upstream reference Dockerfile's stop signal.
  STOPSIGNAL SIGKILL

  EXPOSE ${PORT}

  WORKDIR /app/chat_ui
  CMD caddy start --config /app/Caddyfile --adapter caddyfile \
      && exec reflex run --env prod --backend-only \
             --backend-port ${BACKEND_INTERNAL_PORT} --backend-host ${HOST:-0.0.0.0}
  ```
  Notes for whoever implements this:
  - The final stage re-runs `pip install` (rather than copying a venv from the builder) so it stays independent of the builder's Python 3.11 *full* image having identical ABI to `python:3.11-slim` — simpler and matches this repo's existing single-stage pattern of installing directly into the system interpreter. This does mean `reflex`, `fastapi`, etc. are installed twice across stages (once for `reflex export`, once for the runtime); acceptable — it's a normal multi-stage build cost and keeps each stage self-contained.
  - `mv .web/build/client/*` assumes reflex 0.9.6.post1's export output lands at `.web/build/client/`. Confirm this exact path with `ls .web/build/` immediately after the first `reflex export` run in Task 5 — if the subpath differs, adjust the `mv` line accordingly before moving on.
  - `chat_ui/reflex.lock/{bun.lock,package.json}` (already git-tracked, per STORY-002) is picked up automatically by `reflex init`/`reflex export` — Reflex mirrors `reflex.lock/` into `.web` itself (confirmed in `reflex/utils/frontend_skeleton.py`); no manual copy step needed beyond the blanket `COPY . .`.
- **Mirror**: official `docker-example/production-one-port/Dockerfile`, adapted per the three mechanics in the Summary (no Redis, nested `chat_ui/` WORKDIR, placeholder build-time secrets, fixed internal backend port).
- **Validate**: `docker build -t harness-ai:test .` completes without error.

### Task 3: Update `docker-compose.yml`

- **File**: `docker-compose.yml`
- **Action**: UPDATE
- **Implement**:
  ```yaml
  services:
    harness-ai:
      build:
        context: .
        args:
          PORT: ${PORT:-8000}
      ports:
        - "${PORT:-8000}:${PORT:-8000}"
      env_file:
        - .env
      environment:
        DATABASE_URL: sqlite:////app/data/harness_ai.db
      volumes:
        - harness_data:/app/data

  volumes:
    harness_data:
  ```
  Only two changes from today: `build` gains a `context`/`args` block to pass `PORT` through to the Dockerfile's `ARG PORT` (needed to bake the correct `REFLEX_API_URL` and Caddy listen port at build time), and `DATABASE_URL` gains two extra leading slashes to become an absolute path (mechanic 3 in the Summary). Port count, service count, and the `harness_data` volume are all unchanged.
- **Mirror**: existing file structure verbatim aside from the two changes above.
- **Validate**: `docker-compose config` (parses without error, shows the resolved build args).

### Task 4: Update `.dockerignore`

- **File**: `.dockerignore`
- **Action**: UPDATE
- **Implement**: append these entries to the existing list:
  ```
  **/.env
  chat_ui/.web/
  chat_ui/.states/
  chat_ui/__pycache__/
  chat_ui/harness_ai.db
  chat_ui/reflex.log
  ```
  The existing bare `.env` entry only matches the repo-root `.env`, not `chat_ui/.env` (which currently holds a locally-generated OpenRouter key) — `**/.env` closes that gap. The rest exclude generated/dev-mode artifacts already present in this working tree (confirmed via `ls chat_ui/`) that must never be baked into a build layer.
- **Mirror**: `.dockerignore:1-8` (current entries, unchanged, only appending).
- **Validate**: `docker build -t harness-ai:test .` (Task 2's build) and confirm via `docker history` / build log that `chat_ui/.env` and `chat_ui/.web` are not staged into any layer.

### Task 5: Full single-port smoke validation (all ACs)

- **File**: N/A
- **Action**: validation only
- **Implement**: from a clean checkout state, run in order:
  1. `docker-compose up -d --build`
  2. `curl http://localhost:8000/health` → expect `{"status":"ok"}` (AC3)
  3. Open `http://localhost:8000/` in a browser → chat UI renders (AC3)
  4. `curl -X POST http://localhost:8000/query -H "Content-Type: application/json" -d '{"user_id":"smoke@test.com","prompt":"hello"}'` → reaches the pipeline (AC4)
  5. `curl -H "Authorization: Bearer $ADMIN_TOKEN" http://localhost:8000/audit` and `.../stats` → 200, shows the row from step 4 (AC4)
  6. `docker port <container>` → exactly one mapping, matching `PORT` (AC2)
  7. `docker exec <container> sh -c "which node bun || echo none-found"` → `none-found` (AC5)
  8. `docker exec <container> sh -c "ls /usr/lib | grep -i node || echo clean"` as a second no-Node check (AC5)
- **Mirror**: PRD Section 12 Phase 5 validation steps, verbatim.
- **Validate**: all 8 checks above pass.

### Task 6: Regression check — existing suite still passes inside the built image

- **File**: N/A
- **Action**: validation only
- **Implement**: `docker-compose run --rm harness-ai pytest tests/ -v` (per `README.md:167-170`'s already-documented pattern) — confirms STORY-001 through STORY-007's full suite (99 tests as of STORY-007) still passes unmodified when run from inside the new multi-stage image, not just on the host.
- **Mirror**: `README.md:159-170` ("Running Tests" section).
- **Validate**: all tests pass, 0 modified test files.

---

## End-to-End Tests

- [ ] `docker-compose up -d --build` succeeds from a clean checkout
- [ ] `curl http://localhost:8000/health` returns the existing healthy response
- [ ] Opening `http://localhost:8000/` in a browser shows the working chat UI, same port/process as `/health`
- [ ] `POST /query`, `GET /audit`, `GET /stats` behave exactly as PRD-001 specifies
- [ ] Exactly one port is exposed/mapped; no new service added to `docker-compose.yml`
- [ ] No Node/Bun binary present anywhere in the final image's filesystem
- [ ] `REFLEX_ENV=prod` is set and the app boots in single-port prod mode with no manual intervention
- [ ] `pytest tests/ -v` passes unmodified when run inside the built container

---

## Validation

```bash
docker-compose up -d --build
curl http://localhost:8000/health
curl -X POST http://localhost:8000/query -H "Content-Type: application/json" -d '{"user_id":"smoke@test.com","prompt":"hello"}'
docker-compose run --rm harness-ai pytest tests/ -v
```

---

## Acceptance Criteria

(Copied from story STORY-008)

- [ ] Given the updated `Dockerfile`, when built, then it uses a multi-stage build: a Node.js/Bun stage compiles the Reflex frontend's static assets, and the final runtime stage is Python-only (no Node/Bun binaries present in the final image). → Task 2, Task 5 (checks 7–8)
- [ ] Given `docker-compose up -d --build` is run from a clean checkout, when the container starts, then exactly one port is exposed (the existing `PORT` env var, unchanged from PRD-001) and no new service or port mapping is added to `docker-compose.yml`. → Task 3, Task 5 (check 6)
- [ ] Given the running container, when `curl http://localhost:8000/health` is called, then it returns the existing healthy response, and opening `http://localhost:8000/` in a browser shows the working chat UI — both against the same running process. → Task 5 (checks 2–3)
- [ ] Given the running container, when `POST /query`, `GET /audit`, and `GET /stats` are called, then they behave exactly as PRD-001 specifies, unchanged. → Task 5 (checks 4–5)
- [ ] Given the final built image, when its layers/filesystem are inspected, then no Node or Bun runtime is present — only the compiled static frontend assets and the Python runtime. → Task 5 (checks 7–8)
- [ ] Given `REFLEX_ENV=prod`, when the container runs, then it is set appropriately in the Dockerfile/compose so the app boots in single-port production mode without manual intervention. → Task 2 (`ENV REFLEX_ENV=prod` + CMD's `--env prod`)
- [ ] All tasks completed
- [ ] Frontend lint passes — N/A, no frontend source changes in this story
- [ ] Backend server starts without error — Task 5 (check 1)
- [ ] Follows existing patterns — Task 1–4 Mirror sections
