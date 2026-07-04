---
story: STORY-001
prd: PRD-001
slug: project-scaffolding
title: Project scaffolding & configuration loading
type: technical
complexity: small
epic_branch: epic/PRD-001-harness-ia
created: 2026-07-04
---

# Plan: Project scaffolding & configuration loading

## Summary

Stand up the bootable FastAPI skeleton the rest of PRD-001 builds on: a root `app.py` entrypoint runnable via `python app.py`, an `app/` package with `main.py` (FastAPI instance + router-registration placeholder) and `config.py` (typed, env-driven `Settings`), plus `requirements.txt`, `.env.example`, and `.gitignore`. No business routes or logic — this is pure scaffolding per the story's explicit scope.

## User Story

As an integrating developer
I want a bootable FastAPI project skeleton with environment-variable-driven configuration
So that every later story has a consistent app entrypoint and settings object to build on

## Story Reference

- Story file: `.agents/stories/PRD-001-harness-ia/STORY-001-project-scaffolding.md`
- PRD: `.agents/PRDs/PRD-001-harness-ia/PRD.md`

## Metadata

| Field | Value |
|-------|-------|
| Type | technical |
| Complexity | small |
| Systems Affected | app bootstrap, configuration |
| Story | STORY-001 |
| PRD | PRD-001 |
| Epic Branch | `epic/PRD-001-harness-ia` (commit directly on this branch) |

---

## Skills In Use

None. `.agents/skills/` does not exist yet in this repo, and the story's `skills:` frontmatter field is empty — consistent with the PRD Appendix note ("Skills referenced: None — `.agents/skills/` did not exist at the time this PRD was generated").

---

## Codebase State (why there's no "Patterns to Follow" section)

This is a greenfield repo: only `.agents/` (planning artifacts) and `.git/` exist. There is no `app/`, no `requirements.txt`, no existing Python code of any kind to mirror. The PRD's Section 6 (directory structure) and Section 8/9 (stack, env vars) are the only source of truth for conventions — every later story (STORY-002 onward) will mirror what this story establishes, not the other way around.

---

## Design Decisions

1. **Root `app.py` + `app/` package coexisting.** The story's AC requires `python app.py` to start the server, while the PRD's directory tree nests the app code under `app/`. These don't conflict: when Python runs `app.py` directly, it becomes `__main__`, not a module named `app` — so `app.py` can safely do `from app.main import app` and `import app.config` without shadowing. This is a common, safe layout (same pattern used by many Flask/FastAPI scaffolds).

2. **`pydantic-settings` added to `requirements.txt`.** The story's indicative `requirements.txt` (copied from PRD Section 8) lists only `pydantic`, not `pydantic-settings`. In Pydantic v2, `BaseSettings` was split out into the separate `pydantic-settings` package — plain `pydantic` no longer includes it. To get typed attributes, `.env` loading, and fail-fast validation (AC 2 and AC 3) without hand-rolling `os.getenv` parsing, this plan adds `pydantic-settings` as a required dependency alongside the ones the story lists. This is a minimal, necessary correction, not scope creep — the story's own AC ("fails fast with a clear error only if a required var is missing," "typed attributes") is what `pydantic-settings`'s `BaseSettings` provides out of the box.

3. **Only `OPENROUTER_API_KEY` and `ADMIN_TOKEN` are required (no default).** Per PRD Section 9, `DATABASE_URL`, `PORT`, `HOST`, and `LOG_LEVEL` all have documented defaults. `OPENROUTER_API_KEY` has no sensible default (explicitly called out in the story's AC as the fail-fast example). `ADMIN_TOKEN` also has no safe default — a shipped default would silently disable the admin gate STORY-009 depends on — so it is required too, matching the "required var... missing" fail-fast behavior the AC describes generically.

4. **`app/main.py` gets a placeholder `/health` route only.** The story explicitly says "no routes with real logic yet." A trivial health check satisfies PRD Section 12 Phase 1 validation ("service starts locally, health check responds") without pre-building STORY-008's `/query` pipeline.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app.py` | CREATE | Root entrypoint — `python app.py` starts uvicorn on `settings.HOST`/`settings.PORT` |
| `app/__init__.py` | CREATE | Makes `app/` a Python package |
| `app/main.py` | CREATE | FastAPI app instance, placeholder `/health` route, router-registration comment for later stories |
| `app/config.py` | CREATE | Pydantic `Settings` (via `pydantic-settings`) loading all PRD Section 9 env vars, typed, with `.env` support |
| `requirements.txt` | CREATE | Pinned dependency list per PRD Section 8 + `pydantic-settings` |
| `.env.example` | CREATE | Documents all six env vars with the defaults/placeholders from PRD Section 9 |
| `.gitignore` | CREATE | Excludes `.env`, `__pycache__/`, `*.db`, `.venv/` so secrets and local DB files are never committed |
| `tests/__init__.py` | CREATE | Makes `tests/` a package (needed by `pytest`/later stories) |
| `tests/test_main.py` | CREATE | Smoke test: app imports, `/health` returns 200 — proves the skeleton boots under `pytest` too |

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Create `requirements.txt`

- **File**: `requirements.txt`
- **Action**: CREATE
- **Implement**: List dependencies per PRD Section 8 plus `pydantic-settings` (see Design Decision 2):
  ```
  fastapi
  uvicorn[standard]
  pydantic
  pydantic-settings
  httpx
  python-dotenv
  pytest
  pytest-asyncio
  ```
- **Validate**: `pip install -r requirements.txt` in a clean virtualenv completes with no errors.

### Task 2: Create `.env.example`

- **File**: `.env.example`
- **Action**: CREATE
- **Implement**: Document all six PRD Section 9 vars with comments, using placeholder/default values (no real secrets):
  ```
  # OpenRouter
  OPENROUTER_API_KEY=your-openrouter-key-here

  # Database
  DATABASE_URL=sqlite:///harness_ai.db

  # Server
  PORT=8000
  HOST=0.0.0.0

  # Security
  ADMIN_TOKEN=change-me

  # Logging
  LOG_LEVEL=INFO
  ```
- **Validate**: Visual diff against PRD Section 9 — all six vars present, no IP/location var introduced.

### Task 3: Create `.gitignore`

- **File**: `.gitignore`
- **Action**: CREATE
- **Implement**: Standard Python + project excludes:
  ```
  __pycache__/
  *.pyc
  .venv/
  venv/
  .env
  *.db
  .pytest_cache/
  ```
- **Validate**: `git status` after running the app locally shows no `.env`, `harness_ai.db`, or `__pycache__/` as untracked-to-be-added.

### Task 4: Create `app/__init__.py`

- **File**: `app/__init__.py`
- **Action**: CREATE
- **Implement**: Empty file — just marks `app/` as a package.
- **Validate**: `python -c "import app"` succeeds from repo root.

### Task 5: Create `app/config.py`

- **File**: `app/config.py`
- **Action**: CREATE
- **Implement**: A `pydantic_settings.BaseSettings` subclass named `Settings` exposing all six env vars as typed attributes, loading from `.env` via `SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")`. Required fields (no default): `OPENROUTER_API_KEY: str`, `ADMIN_TOKEN: str`. Fields with PRD-documented defaults: `DATABASE_URL: str = "sqlite:///harness_ai.db"`, `PORT: int = 8000`, `HOST: str = "0.0.0.0"`, `LOG_LEVEL: str = "INFO"`. Instantiate a module-level `settings = Settings()` singleton for import elsewhere (`from app.config import settings`).
- **Mirror**: PRD Section 9 (Environment variables block) — field names, types, and defaults must match exactly, since STORY-002/003/007/009 all import `settings` by these exact attribute names.
- **Validate**: `python -c "from app.config import settings; print(settings.PORT, settings.HOST)"` — with a `.env` present containing `OPENROUTER_API_KEY` and `ADMIN_TOKEN`, prints `8000 0.0.0.0`. Without those two vars set anywhere, the same command raises a `pydantic_core.ValidationError` naming the missing field(s) (fail-fast, AC 2).

### Task 6: Create `app/main.py`

- **File**: `app/main.py`
- **Action**: CREATE
- **Implement**: Instantiate `FastAPI(title="Harness IA")` as `app`. Add a single `GET /health` route returning `{"status": "ok"}` (placeholder proving the server runs — not part of the PRD API spec, just an operational smoke-check). Add a comment block noting where future routers (`query`, `admin`) will be `include_router`'d by later stories (STORY-008, STORY-010/011) — no actual imports of routers that don't exist yet.
- **Mirror**: PRD Section 6 directory structure (`app/main.py` — "FastAPI app, route registration") and Section 12 Phase 1 validation ("health check responds").
- **Validate**: `cd` to repo root, `uvicorn app.main:app --reload` starts without error; `curl http://localhost:8000/health` returns `{"status":"ok"}`.

### Task 7: Create root `app.py`

- **File**: `app.py`
- **Action**: CREATE
- **Implement**:
  ```python
  import uvicorn

  from app.config import settings

  if __name__ == "__main__":
      uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT)
  ```
- **Mirror**: Story AC 1 ("when I run `python app.py`, then a FastAPI app starts on `HOST`/`PORT` from env vars") and Design Decision 1 (root script + package coexistence is safe under `__main__`).
- **Validate**: `python app.py` (with `.env` populated) starts uvicorn bound to the configured `HOST`/`PORT`; `curl http://localhost:8000/health` returns `{"status":"ok"}`.

### Task 8: Create `tests/__init__.py` and `tests/test_main.py`

- **File**: `tests/__init__.py`, `tests/test_main.py`
- **Action**: CREATE
- **Implement**: `tests/__init__.py` empty. `tests/test_main.py` uses `fastapi.testclient.TestClient` against `app.main.app` to assert `GET /health` returns `200` and `{"status": "ok"}`. Set required env vars (`OPENROUTER_API_KEY`, `ADMIN_TOKEN`) at the top of the test module (or via a `conftest.py` fixture) so config loads without needing a real `.env` file in CI.
- **Validate**: `pytest tests/test_main.py -v` passes.

---

## End-to-End Tests

- [ ] Fresh clone → `pip install -r requirements.txt` → no missing-dependency errors (AC 4)
- [ ] `.env` populated per `.env.example` → `python app.py` → server starts on configured `HOST`/`PORT` (AC 1)
- [ ] Remove `OPENROUTER_API_KEY` from env/`.env` → app start (`python app.py` or `from app.config import settings`) fails fast with a clear validation error naming the missing field (AC 2)
- [ ] `from app.config import settings` from any module exposes all six typed attributes: `OPENROUTER_API_KEY`, `DATABASE_URL`, `PORT`, `HOST`, `ADMIN_TOKEN`, `LOG_LEVEL` (AC 3)
- [ ] `GET /health` returns 200 whether served via `uvicorn app.main:app` or `python app.py`
- [ ] `pytest` runs the smoke test suite green

---

## Validation

```bash
pip install -r requirements.txt
python -c "from app.config import settings; print(settings.PORT, settings.HOST)"
uvicorn app.main:app --reload &
curl http://localhost:8000/health
pytest tests/ -v
```

---

## Acceptance Criteria

(Copied from story STORY-001)

- [ ] Given a fresh checkout, when I run `python app.py`, then a FastAPI app starts on `HOST`/`PORT` from env vars (defaulting per Section 9 of the PRD).
- [ ] Given no `.env` file, when the app starts, then it fails fast with a clear error only if a required var (e.g. `OPENROUTER_API_KEY`) is missing — optional vars fall back to documented defaults.
- [ ] Given the `config.py` settings object, when imported from any module, then all env vars from PRD Section 9 (`OPENROUTER_API_KEY`, `DATABASE_URL`, `PORT`, `HOST`, `ADMIN_TOKEN`, `LOG_LEVEL`) are exposed as typed attributes.
- [ ] Given `requirements.txt`, when installed in a clean virtualenv, then the app starts with no missing-dependency errors.
- [ ] All tasks completed
- [ ] `python app.py` starts without error
- [ ] Follows PRD Section 6/8/9 conventions (only source of patterns available at this stage of the project)
