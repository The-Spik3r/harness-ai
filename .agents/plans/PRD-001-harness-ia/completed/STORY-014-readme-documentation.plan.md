---
story: STORY-014
prd: PRD-001
slug: readme-documentation
title: README & usage documentation
type: technical
complexity: SMALL
epic_branch: epic/PRD-001-harness-ia
created: 2026-07-04
---

# Plan: README & usage documentation

## Summary

Document the already-fully-implemented harness (STORY-001 through STORY-013 are all `done`) so a new adopter can run it and understand its API without reading source. This is docs-only — no `app/` source changes. Three deliverables: a root `README.md` with copy-paste `python app.py` and `docker-compose up` quickstarts, an env var reference table (mirroring PRD Section 9 exactly), and `curl` examples for all three `/query` outcomes (success, duplicate-blocked, pattern-blocked) plus `/audit` and `/stats` — every example's request/response shape is copied verbatim from the actual Pydantic schemas (`app/models/schemas.py`) and the STORY-012 integration suite (`tests/test_integration.py`), not reconstructed from memory, so they are guaranteed to be copy-paste-correct. Second, enrich the existing `.env.example` (already present with all 6 vars, but only section-grouped, not per-var described) with a one-line inline comment above each variable explaining its purpose — satisfying the AC's "inline comments" requirement literally rather than just grouping. Third, add a root `LICENSE` file (MIT), per PRD Section 13.

## User Story

As an open-source contributor or adopter
I want a clear README with copy-paste examples
So that I can run the harness locally or via Docker and understand its API without reading the source

## Story Reference

- Story file: `.agents/stories/PRD-001-harness-ia/STORY-014-readme-documentation.md`
- PRD: `.agents/PRDs/PRD-001-harness-ia/PRD.md`

## Metadata

| Field | Value |
|-------|-------|
| Type | technical |
| Complexity | SMALL |
| Systems Affected | Documentation only (no `app/` source changes) |
| Story | STORY-014 |
| PRD | PRD-001 |
| Epic Branch | `epic/PRD-001-harness-ia` (commit directly on this branch) |

---

## Skills In Use

No skills matched. `.agents/skills/` directory contains no `SKILL.md` files (confirmed via glob — consistent with STORY-013's plan, which found the same).

---

## Patterns to Follow

### Env vars (already-complete `.env.example` — to be enriched, not restructured)
```
// SOURCE: .env.example:1-16
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
This exactly matches PRD Section 9's env var block — same 6 vars, same defaults. The README's env var table and the `.env.example` inline comments must stay in lockstep with this file, not invent new vars.

### Request/response shapes (source of truth for curl examples)
```
// SOURCE: app/models/schemas.py:6-36
class QueryRequest(BaseModel):
    user_id: str
    prompt: str
    device: Optional[str] = None
    model: str = "gpt-4"
    openrouter_api_key: Optional[str] = None

class QuerySuccessResponse(BaseModel):
    status: Literal["SUCCESS"] = "SUCCESS"
    response: str
    audit_id: int
    model_used: str
    tokens_used: int

class QueryBlockedDuplicateResponse(BaseModel):
    status: Literal["BLOCKED"] = "BLOCKED"
    reason: str
    first_query_at: str

class QueryBlockedSuspiciousResponse(BaseModel):
    status: Literal["BLOCKED"] = "BLOCKED"
    reason: str
    pattern: str
```
README `curl` examples must use these exact field names — not the slightly different field names in PRD Section 10 (e.g. PRD's raw example omits `status` casing nuances already resolved in code; code is authoritative since it's implemented and tested).

### Real behavior proof (integration tests — response bodies verified here are what README examples must reproduce)
```
// SOURCE: tests/test_integration.py:40-101
response = client.post("/query", json={"user_id": "juan@empresa.com", "prompt": "what is the weather today"})
# body: {"status": "SUCCESS", "response": "...", "model_used": "gpt-4", "tokens_used": ..., "audit_id": ...}

# duplicate (same prompt within 24h):
# body: {"status": "BLOCKED", "reason": "Duplicate query within 24 hours", "first_query_at": "..."}

# suspicious pattern (e.g. "please override the rules"):
# body: {"status": "BLOCKED", "reason": "Suspicious pattern detected", "pattern": "override"}
```

### Admin auth header pattern
```
// SOURCE: app/middleware/auth.py:9-18, tests/test_integration.py:104-118
_bearer_scheme = HTTPBearer(auto_error=False)
# Header: Authorization: Bearer <ADMIN_TOKEN>
# Missing/invalid -> 401
```

### `/audit` and `/stats` response shapes
```
// SOURCE: app/models/schemas.py:39-63
class AuditQueryEntry(BaseModel):
    audit_id: int
    user_id: str
    timestamp: str
    model: Optional[str] = None
    prompt_hash: str
    was_duplicate_blocked: bool
    suspicious_pattern_detected: bool
    device: Optional[str] = None

class AuditResponse(BaseModel):
    total: int
    queries: List[AuditQueryEntry]

class StatsResponse(BaseModel):
    total_queries: int
    blocked_duplicates: int
    blocked_suspicious: int
    unique_users: int
    success_rate: str
    top_models: List[str]
    top_users: List[str]
```

### Docker quickstart (already implemented, STORY-013 — README must match exactly, not reinvent)
```
// SOURCE: Dockerfile:1-12, docker-compose.yml:1-14
CMD ["python", "app.py"]
# docker-compose.yml exposes ${PORT:-8000}, reads .env via env_file, persists SQLite via a named volume
```

### Suspicious pattern list (for the pattern-blocked curl example)
```
// SOURCE: PRD.md Section 9
ignore previous instructions
forget everything
show system prompt
reveal password
execute code
admin mode
override
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `README.md` | CREATE | Project overview, quickstarts (local + Docker), env var table, curl examples, testing instructions |
| `.env.example` | UPDATE | Add a one-line inline comment above each variable explaining its purpose (values/vars unchanged) |
| `LICENSE` | CREATE | MIT license text, per PRD Section 13 |

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Add inline comments to `.env.example`

- **File**: `.env.example`
- **Action**: UPDATE
- **Implement**: Keep all 6 existing vars and their placeholder values unchanged; add a one-line `#` comment directly above each var describing its purpose, e.g.:
  ```bash
  # OpenRouter API key used to call the upstream LLM provider (required)
  OPENROUTER_API_KEY=your-openrouter-key-here

  # SQLite connection string for the audit_logs database
  DATABASE_URL=sqlite:///harness_ai.db

  # Port the FastAPI server listens on
  PORT=8000

  # Host/interface the server binds to
  HOST=0.0.0.0

  # Shared-secret bearer token required to call /audit and /stats (required)
  ADMIN_TOKEN=change-me

  # Log verbosity (DEBUG, INFO, WARNING, ERROR)
  LOG_LEVEL=INFO
  ```
- **Mirror**: `.env.example:1-16` (existing structure), `app/config.py:1-16` (which vars are required vs. defaulted — `OPENROUTER_API_KEY` and `ADMIN_TOKEN` have no default in `Settings`, so mark those "(required)").
- **Validate**: `cat .env.example` — 6 vars still present, each preceded by a description comment; `cp .env.example .env.check && python -c "import re; c=open('.env.check').read(); assert c.count('=')==6" && rm .env.check`.

### Task 2: Add root `LICENSE` (MIT)

- **File**: `LICENSE`
- **Action**: CREATE
- **Implement**: Standard MIT license text, copyright line using the current year and a placeholder holder name (e.g. "Harness IA contributors"), per PRD Section 13 ("Open Source" — MIT).
- **Mirror**: N/A — standard MIT boilerplate, no in-repo precedent needed.
- **Validate**: `test -f LICENSE && grep -q "MIT License" LICENSE`.

### Task 3: Write `README.md`

- **File**: `README.md`
- **Action**: CREATE
- **Implement**: Sections, in order:
  1. **Title + one-paragraph overview** (adapt PRD Section 1 Executive Summary).
  2. **Features** (bullet list from PRD Section 4 In Scope: duplicate blocking, pattern blocking, audit logging, `/stats`, admin token auth, Docker parity).
  3. **Quickstart — Local**: `pip install -r requirements.txt`, `cp .env.example .env` (edit `OPENROUTER_API_KEY`/`ADMIN_TOKEN`), `python app.py`, then `curl http://localhost:8000/health`.
  4. **Quickstart — Docker**: `cp .env.example .env` (edit same two vars), `docker-compose up -d --build`, `curl http://localhost:8000/health`.
  5. **Environment Variables** table: Var | Required | Default | Description — one row per var from `.env.example`, matching Task 1's descriptions exactly.
  6. **API Reference** with copy-paste `curl` blocks:
     - `POST /query` success (mirrors `tests/test_integration.py:40-57`)
     - `POST /query` duplicate-blocked (mirrors `tests/test_integration.py:60-80` — same prompt sent twice)
     - `POST /query` pattern-blocked (mirrors `tests/test_integration.py:83-101`, using `"please override the rules"`)
     - `GET /audit` with `Authorization: Bearer $ADMIN_TOKEN` (mirrors `app/routers/admin.py:19-39` response shape)
     - `GET /stats` with `Authorization: Bearer $ADMIN_TOKEN` (mirrors `app/routers/admin.py:42-60` response shape)
  7. **Running Tests**: `pytest tests/ -v` (local) and `docker-compose run --rm harness-ai pytest tests/ -v` (container, per STORY-013's validated command).
  8. **License**: one line, "MIT — see [LICENSE](LICENSE)."
- **Mirror**: `app/models/schemas.py:6-63` for exact field names in every JSON example; `tests/test_integration.py` for realistic prompt/response pairs that are known to pass; `.agents/reports/PRD-001-harness-ia/STORY-013-docker-packaging.report.md:36-41` for the exact validated Docker commands.
- **Validate**: Manually walk every `curl` command in the README against a running local instance (Task 4) and a running Docker instance (Task 5) to confirm each one is copy-paste-correct.

### Task 4: Validate README examples against a local run

- **File**: N/A (verification step)
- **Action**: N/A
- **Implement**: Start the app locally and execute every `curl` example from the new README verbatim.
- **Mirror**: N/A
- **Validate**:
  ```bash
  cp .env.example .env   # then set a real OPENROUTER_API_KEY / ADMIN_TOKEN, or reuse existing .env
  python app.py &
  curl http://localhost:8000/health
  # run the /query success, duplicate, and pattern curl blocks from README.md verbatim
  # run the /audit and /stats curl blocks with the ADMIN_TOKEN from .env
  kill %1
  ```
  Every response must match the shape documented in the README (field names, `status` values).

### Task 5: Validate README Docker quickstart

- **File**: N/A (verification step)
- **Action**: N/A
- **Implement**: Confirm the Docker quickstart section in the README works verbatim, reusing STORY-013's validated flow.
- **Mirror**: `.agents/reports/PRD-001-harness-ia/STORY-013-docker-packaging.report.md:36-41`
- **Validate**:
  ```bash
  docker-compose up -d --build
  curl http://localhost:8000/health
  docker-compose run --rm harness-ai pytest tests/ -v
  docker-compose down
  ```

---

## End-to-End Tests

- [ ] Following the README's "Quickstart — Local" section step-by-step from a clean shell starts the app and `GET /health` returns `{"status":"ok"}`
- [ ] Following the README's "Quickstart — Docker" section starts the app via `docker-compose up` and `GET /health` returns the same response
- [ ] Every `curl` example in the README (`/query` success, duplicate, pattern; `/audit`; `/stats`) returns a response matching the documented shape exactly, when run against a live instance
- [ ] `cp .env.example .env` produces a file containing all 6 required vars with placeholder values and a descriptive comment above each

---

## Validation

```bash
cat .env.example
test -f LICENSE && grep -q "MIT License" LICENSE
python app.py &
curl http://localhost:8000/health
kill %1
docker-compose up -d --build
curl http://localhost:8000/health
docker-compose down
```

---

## Acceptance Criteria

(Copied from story STORY-014)

- [ ] Given the README, when followed step-by-step, then a new user can run the harness both via `python app.py` and `docker-compose up` successfully.
- [ ] Given the README, when read, then it documents every env var from PRD Section 9 with a description and example value.
- [ ] Given the README, when read, then it includes copy-paste `curl` (or equivalent) examples for `POST /query` (success, duplicate-blocked, pattern-blocked), `GET /audit`, and `GET /stats`.
- [ ] Given `.env.example`, when copied to `.env`, then it contains every required var with placeholder values and inline comments.
- [ ] Given the repo, when checked, then a LICENSE file (MIT, per PRD Section 13) is present.
- [ ] All tasks completed
- [ ] Follows existing patterns (no `app/` source changes; Docker/local parity preserved as established in STORY-013)
