---
story: STORY-002
prd: PRD-001
slug: sqlite-audit-schema
title: SQLite connection & audit_logs schema
type: technical
complexity: small
epic_branch: epic/PRD-001-harness-ia
created: 2026-07-04
---

# Plan: SQLite connection & audit_logs schema

## Summary

Add the `app/db/` package that STORY-001 stubbed out in the directory tree: `models.py` defines the `audit_logs` table DDL and a typed `AuditLog` dataclass matching the PRD's data model exactly (no IP/location field, ever); `database.py` provides connection setup (parsed from `settings.DATABASE_URL`), an idempotent `init_db()` schema-creation function, and thin repository functions (`insert_audit_log`, `get_audit_log`) so no other module ever writes raw SQL. `app/main.py` is updated to call `init_db()` on startup via a FastAPI lifespan handler. Uses stdlib `sqlite3` — no new dependency — consistent with the PRD's "Simple over clever" principle and the story's explicit "sqlite3 stdlib or SQLAlchemy Core" choice.

## User Story

As a compliance officer
I want a persistent `audit_logs` table with the exact fields from the PRD's data model
So that every query can be fully audited without ever having a place to store an IP or location field

## Story Reference

- Story file: `.agents/stories/PRD-001-harness-ia/STORY-002-sqlite-audit-schema.md`
- PRD: `.agents/PRDs/PRD-001-harness-ia/PRD.md`

## Metadata

| Field | Value |
|-------|-------|
| Type | technical |
| Complexity | small |
| Systems Affected | database layer, app startup |
| Story | STORY-002 |
| PRD | PRD-001 |
| Epic Branch | `epic/PRD-001-harness-ia` (commit directly on this branch) |

---

## Skills In Use

None. `.agents/skills/` does not exist in this repo yet, and the story's `skills:` frontmatter field is empty — same situation as STORY-001.

---

## Codebase State

`app/` currently contains only `__init__.py`, `config.py` (typed `Settings` singleton, already exposes `DATABASE_URL: str = "sqlite:///harness_ai.db"`), and `main.py` (bare `FastAPI(title="Harness IA")` instance with a placeholder `GET /health` route, no lifespan/startup hook yet, and a comment block noting future routers). No `app/db/` package, no `app/models/` package, and no test beyond `tests/test_main.py` (health-check smoke test using `TestClient`) exist. This story is the first to touch persistence — the PRD's Section 6 directory tree (`app/db/database.py`, `app/db/models.py`) and Section 7/9 (data fields, `DATABASE_URL`) are the source of truth for conventions here; there is no prior `db/` code to mirror, but `app/config.py` and `app/main.py` set the naming/style precedent (typed, minimal, PRD-field-name-exact).

---

## Design Decisions

1. **stdlib `sqlite3`, not SQLAlchemy.** The story's Technical Notes explicitly permit either. Adding SQLAlchemy would be a new dependency for a single-table MVP; stdlib `sqlite3` satisfies every AC (idempotent `CREATE TABLE IF NOT EXISTS`, typed round-trip via a repository function) with zero new packages, matching the PRD's "Simple over clever" principle. `requirements.txt` is unchanged.

2. **`DATABASE_URL` parsing is minimal and explicit.** Only the `sqlite:///<path>` scheme (already the documented default and `.env.example` value) is supported. The path segment after the fixed `sqlite:///` prefix is passed directly to `sqlite3.connect()` — this also transparently supports `sqlite:///:memory:` for tests. Any other scheme raises `ValueError` at connection time rather than silently misbehaving (fail loud, per PRD Mission principle).

3. **Repository pattern: `database.py` is the only place SQL appears.** `init_db()`, `insert_audit_log()`, and `get_audit_log()` are the only functions that touch `sqlite3` directly. Later stories (STORY-004, STORY-006, STORY-010, STORY-011) call these functions instead of writing their own queries — per PRD Section 6 ("Repository pattern... isolating SQL from route/service logic").

4. **One connection per call, not a pooled/shared connection.** Each repository function opens a connection via a `with get_connection() as conn:` block and lets `sqlite3`'s context-manager commit/rollback handle transactions, then the connection closes. This is simplest-correct for SQLite's file-based, single-writer model at the PRD's stated scale (<50 concurrent users) and avoids cross-request shared-state bugs; a shared engine/session is exactly the kind of premature infrastructure the PRD's Risk #3 already accepts as an MVP tradeoff (documented Postgres migration path if needed later).

5. **`was_duplicate_blocked` and `success` are stored as `INTEGER` (0/1), exposed as `bool` in `AuditLog`.** SQLite has no native boolean type; the repository layer converts at the boundary (`int(x)` on insert, `bool(row[...])` on read) so every caller outside `database.py` only ever sees real Python `bool`s.

6. **`init_db()` runs from a FastAPI `lifespan` handler in `app/main.py`, not a bare `@app.on_event("startup")`.** `lifespan` is the current non-deprecated FastAPI pattern and keeps `app/main.py`'s existing router-registration comment block intact — later stories (STORY-008, STORY-010/011) add routers the same way STORY-001 already documented.

7. **No `app/models/` package touched.** The PRD directory tree's `app/models/schemas.py` (Pydantic request/response models) belongs to STORY-003, which is a sibling dependency of STORY-004/006, not this story. This story only creates `app/db/`.

---

## Patterns to Follow

### Config access
```python
// SOURCE: app/config.py:1-16
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
    ...
    DATABASE_URL: str = "sqlite:///harness_ai.db"


settings = Settings()
```
`database.py` imports `from app.config import settings` and reads `settings.DATABASE_URL` — same singleton-import style already used across the codebase.

### App structure / comments
```python
// SOURCE: app/main.py:1-13
from fastapi import FastAPI

app = FastAPI(title="Harness IA")

# Routers are registered here by later stories:
#   - app.routers.query   (POST /query)          -> STORY-008
#   - app.routers.admin   (GET /audit, GET /stats) -> STORY-010, STORY-011


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
```
Keep the existing comment block; only add the `lifespan` wiring around it.

### Tests
```python
// SOURCE: tests/test_main.py:1-16
import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
```
New DB tests follow the same convention: set required env vars before importing `app.config`/`app.db`, use `pytest` plain `assert` style (no unittest classes).

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/db/__init__.py` | CREATE | Marks `app/db/` as a package |
| `app/db/models.py` | CREATE | `audit_logs` DDL constant + `AuditLog` dataclass (exact PRD field list, no IP/location) |
| `app/db/database.py` | CREATE | Connection setup from `DATABASE_URL`, `init_db()`, `insert_audit_log()`, `get_audit_log()` repository functions |
| `app/main.py` | UPDATE | Add `lifespan` handler that calls `init_db()` on startup |
| `tests/test_db.py` | CREATE | Schema idempotency, insert+read round trip, column-set/no-IP assertion |

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Create `app/db/__init__.py`

- **File**: `app/db/__init__.py`
- **Action**: CREATE
- **Implement**: Empty file — just marks `app/db/` as a package.
- **Mirror**: `app/__init__.py` (same empty-package-marker pattern from STORY-001).
- **Validate**: `python -c "import app.db"` succeeds from repo root.

### Task 2: Create `app/db/models.py`

- **File**: `app/db/models.py`
- **Action**: CREATE
- **Implement**: A `CREATE_AUDIT_LOGS_TABLE` SQL string using `CREATE TABLE IF NOT EXISTS audit_logs` with exactly these columns (per story AC 2 and PRD Section 7/9/10 field names):
  - `id INTEGER PRIMARY KEY AUTOINCREMENT`
  - `timestamp TEXT NOT NULL` (ISO-8601 UTC string)
  - `user_id TEXT NOT NULL`
  - `device TEXT`
  - `prompt_hash TEXT NOT NULL`
  - `prompt_preview TEXT`
  - `response_hash TEXT`
  - `response_preview TEXT`
  - `model_used TEXT`
  - `tokens_used INTEGER`
  - `was_duplicate_blocked INTEGER NOT NULL DEFAULT 0`
  - `suspicious_pattern TEXT`
  - `success INTEGER NOT NULL DEFAULT 1`
  - `error_message TEXT`

  Also define a `@dataclass` `AuditLog` with one field per column (`id: Optional[int] = None`, `was_duplicate_blocked: bool`, `success: bool`, rest `Optional[str]`/`Optional[int]` as appropriate) for typed construction/return values used by `database.py`.
- **Mirror**: PRD Section 7 (data model implied via Sections 9/10) — column names must match the story AC 2 list verbatim; explicitly no `ip_address`/`location` column of any kind.
- **Validate**: `python -c "from app.db.models import CREATE_AUDIT_LOGS_TABLE, AuditLog; print(AuditLog.__dataclass_fields__.keys())"` lists exactly the 13 non-`id` fields plus `id`.

### Task 3: Create `app/db/database.py`

- **File**: `app/db/database.py`
- **Action**: CREATE
- **Implement**:
  - `_db_path() -> str`: strips the `sqlite:///` prefix from `settings.DATABASE_URL`; raises `ValueError` for any other scheme.
  - `get_connection() -> sqlite3.Connection`: `sqlite3.connect(_db_path())` with `conn.row_factory = sqlite3.Row`.
  - `init_db() -> None`: opens a connection, executes `CREATE_AUDIT_LOGS_TABLE`, commits (via `with` context manager).
  - `insert_audit_log(entry: AuditLog) -> int`: parameterized `INSERT` of all 13 non-`id` fields (converting `bool` → `int` for `was_duplicate_blocked`/`success`), returns `cursor.lastrowid`.
  - `get_audit_log(audit_id: int) -> Optional[AuditLog]`: parameterized `SELECT * WHERE id = ?`, maps the `sqlite3.Row` back to an `AuditLog` (converting `int` → `bool` for the two boolean columns), returns `None` if no row found.
- **Mirror**: `app/config.py`'s singleton-import style (`from app.config import settings`); PRD Section 6 Repository pattern (no other module issues raw SQL).
- **Validate**: `python -c "from app.db.database import init_db, insert_audit_log, get_audit_log; from app.db.models import AuditLog; import os; os.environ['DATABASE_URL']='sqlite:///:memory:'"` — see Task 5 for full round-trip validation (single in-process `:memory:` connection needed, exercised via the test suite, not this one-liner, since a fresh connection per call yields an empty `:memory:` DB each time).

### Task 4: Update `app/main.py`

- **File**: `app/main.py`
- **Action**: UPDATE
- **Implement**: Wrap the existing `FastAPI(...)` construction with an `@asynccontextmanager async def lifespan(app: FastAPI)` that calls `init_db()` before `yield`, and pass `lifespan=lifespan` to `FastAPI(title="Harness IA", lifespan=lifespan)`. Keep the existing router-registration comment block and `/health` route untouched.
- **Mirror**: `app/main.py:1-13` (STORY-001) — additive change only, preserves existing structure/comments.
- **Validate**: `uvicorn app.main:app --reload` starts without error and creates the SQLite file at the configured `DATABASE_URL` path (default `harness_ai.db` in repo root) on first run; `curl http://localhost:8000/health` still returns `{"status":"ok"}`.

### Task 5: Create `tests/test_db.py`

- **File**: `tests/test_db.py`
- **Action**: CREATE
- **Implement**: Using `pytest`'s `tmp_path` fixture and `monkeypatch` (or direct `settings.DATABASE_URL` override before import), point `DATABASE_URL` at a temp file (e.g. `sqlite:///{tmp_path}/test.db`) so each test run gets an isolated DB file. Tests:
  1. `test_init_db_creates_table` — call `init_db()` twice in a row against the same path; assert no exception and that `audit_logs` exists (query `sqlite_master`).
  2. `test_insert_and_read_round_trip` — build an `AuditLog` with sample data for all 13 fields, call `insert_audit_log`, then `get_audit_log(returned_id)`, assert every field matches (including bool fields staying `bool`).
  3. `test_schema_has_no_ip_or_location_column` — introspect `PRAGMA table_info(audit_logs)` (or `sqlite_master.sql`) and assert no column name contains `ip` or `location`, and that the exact 14-column set (including `id`) from story AC 2 is present.
- **Mirror**: `tests/test_main.py:1-16` — env-var setup before import, plain `assert` pytest style, no unittest classes.
- **Validate**: `pytest tests/test_db.py -v` passes.

---

## End-to-End Tests

- [ ] Fresh checkout with `DATABASE_URL=sqlite:///harness_ai.db`, run `python app.py` (or `uvicorn app.main:app`) → `harness_ai.db` file is created in the repo root and contains an `audit_logs` table (AC 1)
- [ ] `PRAGMA table_info(audit_logs)` (via `sqlite3` CLI or test) shows exactly the 14 columns from story AC 2, no `ip`/`location` column (AC 2)
- [ ] Insert a row via `insert_audit_log`, read it back via `get_audit_log` → all fields intact, including boolean fields (AC 3)
- [ ] Stop and restart the app against the same existing `harness_ai.db` file → no error, no duplicate/second `audit_logs` table, existing rows still readable (AC 4)
- [ ] `pytest tests/` (full suite, including existing `test_main.py`) passes green

---

## Validation

```bash
python -c "from app.db.database import init_db; init_db()"
uvicorn app.main:app --reload &
curl http://localhost:8000/health
pytest tests/ -v
```

---

## Acceptance Criteria

(Copied from story STORY-002)

- [ ] Given `DATABASE_URL` (e.g. `sqlite:///harness_ai.db`), when the app starts, then `db/database.py` creates the SQLite file and `audit_logs` table if they don't already exist.
- [ ] Given the `audit_logs` schema, when inspected, then it has exactly these columns: `id` (PK, autoincrement), `timestamp` (UTC datetime), `user_id`, `device`, `prompt_hash`, `prompt_preview`, `response_hash`, `response_preview`, `model_used`, `tokens_used`, `was_duplicate_blocked`, `suspicious_pattern`, `success`, `error_message` — and no IP/location column of any kind.
- [ ] Given a test DB session, when a row is inserted via the repository function, then it can be read back with all fields intact.
- [ ] Given the app restarts against an existing DB file, then no schema is duplicated or errors thrown (idempotent creation).
- [ ] All tasks completed
- [ ] Frontend lint passes — N/A, no frontend in this MVP; substitute `pytest tests/ -v` passes
- [ ] Backend server starts without error
- [ ] Follows existing patterns (`app/config.py` singleton-import style, `app/main.py` structure, Repository pattern per PRD Section 6)
