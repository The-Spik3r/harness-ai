---
story: STORY-013
prd: PRD-001
slug: docker-packaging
title: Docker & docker-compose packaging
type: technical
complexity: MEDIUM
epic_branch: epic/PRD-001-harness-ia
created: 2026-07-04
---

# Plan: Docker & docker-compose packaging

## Summary

Package the existing FastAPI harness (already fully implemented and tested through STORY-012) so it runs identically inside Docker as it does via `python app.py` locally. This is packaging-only: no application source code changes. Add a `Dockerfile` that builds a Python 3.11 image, installs `requirements.txt`, copies the app, and runs `python app.py` as its `CMD` (the same entrypoint used locally, satisfying the "identical behavior" requirement by construction rather than duplicating startup logic). Add a `docker-compose.yml` that builds that image, loads configuration from the existing `.env` file (same env vars the app already reads via `app/config.py`'s `Settings`), maps the configured `PORT`, and mounts a named volume for the SQLite database file so audit history survives container recreation. Add a `.dockerignore` to keep secrets (`.env`), the venv, caches, and git metadata out of the image build context/layers.

## User Story

As a devops engineer
I want the harness to run identically via Docker Compose or `python app.py`
So that local development and production deployment behave the same way

## Story Reference

- Story file: `.agents/stories/PRD-001-harness-ia/STORY-013-docker-packaging.md`
- PRD: `.agents/PRDs/PRD-001-harness-ia/PRD.md`

## Metadata

| Field | Value |
|-------|-------|
| Type | technical |
| Complexity | MEDIUM |
| Systems Affected | Deployment/packaging only (no `app/` source changes) |
| Story | STORY-013 |
| PRD | PRD-001 |
| Epic Branch | `epic/PRD-001-harness-ia` (commit directly on this branch) |

---

## Skills In Use

No skills matched. `.agents/skills/` does not exist in this repo (confirmed via glob — consistent with the PRD's own Appendix note: "Skills referenced: None").

---

## Patterns to Follow

### Local entrypoint (must behave identically in Docker)
```
// SOURCE: app.py:1-6
import uvicorn

from app.config import settings

if __name__ == "__main__":
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT)
```
The Docker `CMD` must invoke this exact entrypoint (`python app.py`), not a separate `uvicorn app.main:app` CLI invocation, so there is exactly one startup path shared by both environments.

### Configuration (env-var driven, already complete)
```
// SOURCE: app/config.py:1-17
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    OPENROUTER_API_KEY: str
    ADMIN_TOKEN: str

    DATABASE_URL: str = "sqlite:///harness_ai.db"
    PORT: int = 8000
    HOST: str = "0.0.0.0"
    LOG_LEVEL: str = "INFO"
```
Pydantic-settings reads real environment variables ahead of the `.env` file fallback, so `docker-compose.yml`'s `env_file:`/`environment:` keys map 1:1 onto these fields with no code changes.

### SQLite path resolution (must stay relative — do not touch this code)
```
// SOURCE: app/db/database.py:7-14
_SQLITE_PREFIX = "sqlite:///"

def _db_path() -> str:
    url = settings.DATABASE_URL
    if not url.startswith(_SQLITE_PREFIX):
        raise ValueError(f"Unsupported DATABASE_URL scheme: {url}")
    return url[len(_SQLITE_PREFIX):]
```
`sqlite:///data/harness_ai.db` strips to the relative path `data/harness_ai.db`, resolved against the container's CWD (`/app`, set by `WORKDIR` in the Dockerfile) → `/app/data/harness_ai.db`. This is why the compose volume is mounted at `/app/data` and `DATABASE_URL` is overridden to point inside it — no changes to `database.py` needed.

### Existing env var reference (values to carry into compose, not duplicate)
```
// SOURCE: .env.example:1-16
OPENROUTER_API_KEY=your-openrouter-key-here
DATABASE_URL=sqlite:///harness_ai.db
PORT=8000
HOST=0.0.0.0
ADMIN_TOKEN=change-me
LOG_LEVEL=INFO
```

### Ignore-file convention already in repo
```
// SOURCE: .gitignore:1-7
__pycache__/
*.pyc
.venv/
venv/
.env
*.db
.pytest_cache/
```
`.dockerignore` mirrors this list (plus `.git/`, `.agents/`, `.claude/`) so the build context doesn't ship secrets, caches, or planning docs into the image.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `Dockerfile` | CREATE | Build a Python 3.11 image, install deps, run `python app.py` |
| `docker-compose.yml` | CREATE | Build + run the image, wire env vars, map port, mount SQLite volume |
| `.dockerignore` | CREATE | Exclude `.env`, venv, caches, git/agent metadata from build context |

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Add `.dockerignore`

- **File**: `.dockerignore`
- **Action**: CREATE
- **Implement**:
  ```
  .venv/
  venv/
  __pycache__/
  *.pyc
  .git/
  .env
  *.db
  .pytest_cache/
  .agents/
  .claude/
  ```
- **Mirror**: `.gitignore:1-7` — same exclusion list, extended with `.git/`, `.agents/`, `.claude/` since those are irrelevant to the runtime image and `.gitignore` doesn't need to exclude them (git already ignores itself).
- **Validate**: `cat .dockerignore` shows the file; no build yet to run.

### Task 2: Add `Dockerfile`

- **File**: `Dockerfile`
- **Action**: CREATE
- **Implement**:
  ```dockerfile
  FROM python:3.11-slim

  WORKDIR /app

  COPY requirements.txt .
  RUN pip install --no-cache-dir -r requirements.txt

  COPY . .

  EXPOSE 8000

  CMD ["python", "app.py"]
  ```
- **Mirror**: `app.py:1-6` for the `CMD` entrypoint; `requirements.txt` (already lists `fastapi`, `uvicorn[standard]`, `pydantic`, `pydantic-settings`, `httpx`, `python-dotenv`, `pytest`, `pytest-asyncio` — no changes needed there since `pytest`/`pytest-asyncio` being present means the STORY-012 suite can run inside the built image).
- **Validate**: `docker build -t harness-ai .` completes without error.

### Task 3: Add `docker-compose.yml`

- **File**: `docker-compose.yml`
- **Action**: CREATE
- **Implement**:
  ```yaml
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
- **Mirror**: `.env.example:1-16` for the variable set carried via `env_file:`; `app/db/database.py:7-14` for why `DATABASE_URL` is overridden to a path under the mounted volume (`environment:` takes precedence over `env_file:` for the same key in Compose, so this cleanly overrides just the DB path while every other var — `OPENROUTER_API_KEY`, `ADMIN_TOKEN`, `PORT`, `HOST`, `LOG_LEVEL` — still comes from `.env`).
- **Validate**: `docker-compose config` parses without error (validates YAML + variable interpolation).

### Task 4: Build and smoke-test the container

- **File**: N/A (verification step)
- **Action**: N/A
- **Implement**: Run the container against the real `.env` (already present in the repo root) and confirm parity with local behavior.
- **Mirror**: N/A — this is the AC-driven verification pass, not a code pattern.
- **Validate**:
  ```bash
  docker-compose up -d --build
  curl http://localhost:8000/health   # expect {"status":"ok"}
  docker-compose down
  docker-compose up -d                # start again without --build
  curl http://localhost:8000/health   # expect same response — confirms volume/image reuse works
  ```

### Task 5: Run the STORY-012 integration suite inside the container

- **File**: N/A (verification step)
- **Action**: N/A
- **Implement**: Confirm the full test suite (including `tests/test_integration.py` from STORY-012) passes inside the built image exactly as it does locally, per AC4.
- **Mirror**: `tests/test_integration.py:1-15` — same `TestClient`-based suite, no container-specific test code needed since it's fully self-contained (uses `tmp_path` fixtures and mocks `OpenRouterResult`, no real network/DB dependency beyond what's already in the image).
- **Validate**:
  ```bash
  docker-compose run --rm harness-ai pytest tests/ -v
  ```
  Expect the same pass count as the local run (97 passed, per STORY-012's report).

### Task 6: Verify volume persistence across container recreation

- **File**: N/A (verification step)
- **Action**: N/A
- **Implement**: Confirm the SQLite DB survives `docker-compose down && docker-compose up` (not just container restart) — proving the named volume, not just the container filesystem, is what's persisting the data.
- **Mirror**: N/A
- **Validate**:
  ```bash
  docker-compose up -d --build
  curl -X POST http://localhost:8000/query -H "Content-Type: application/json" \
    -d '{"user_id":"docker-test@example.com","prompt":"docker persistence check"}'
  docker-compose down            # removes the container, keeps the named volume
  docker-compose up -d
  curl -H "Authorization: Bearer <ADMIN_TOKEN from .env>" http://localhost:8000/audit \
    | grep "docker-test@example.com"   # entry still present -> volume persisted
  docker-compose down
  ```

---

## End-to-End Tests

- [ ] `docker-compose up -d --build` starts the API and `GET /health` returns `{"status":"ok"}` on the configured `PORT`
- [ ] `docker-compose run --rm harness-ai pytest tests/ -v` passes with the same count as the local `pytest tests/ -v` run
- [ ] A `POST /query` result written before `docker-compose down` is still retrievable via `GET /audit` after a fresh `docker-compose up` (proves volume persistence, not just container reuse)
- [ ] `docker build -t harness-ai .` succeeds with no manual post-build steps required

---

## Validation

```bash
docker build -t harness-ai .
docker-compose config
docker-compose up -d --build
curl http://localhost:8000/health
docker-compose run --rm harness-ai pytest tests/ -v
docker-compose down
```

---

## Acceptance Criteria

(Copied from story STORY-013)

- [ ] Given a clean checkout with only Docker installed, when `docker-compose up` is run, then the API is reachable on the configured `PORT`/`HOST` and behaves identically to a local `python app.py` run (same endpoints, same responses).
- [ ] Given the `Dockerfile`, when built, then it produces a working image without requiring any manual post-build steps.
- [ ] Given `docker-compose.yml`, when started, then the SQLite DB persists across container restarts (mounted volume), so audit history isn't lost on redeploy.
- [ ] Given the full integration test suite from STORY-012, when run inside the container, then it passes exactly as it does locally.
- [ ] All tasks completed
- [ ] Backend server starts without error (`docker-compose up`)
- [ ] Follows existing patterns (no changes to `app/` source, `python app.py` remains the single entrypoint)
