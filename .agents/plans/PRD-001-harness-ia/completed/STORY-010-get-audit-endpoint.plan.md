---
story: STORY-010
prd: PRD-001
slug: get-audit-endpoint
title: "GET /audit endpoint"
type: feature
complexity: medium
epic_branch: epic/PRD-001-harness-ia
created: 2026-07-04
---

# Plan: GET /audit endpoint

## Summary

Add `GET /audit`, an admin-only endpoint returning the total audit row count plus the last 100 `audit_logs` entries (newest first), shaped exactly per PRD Section 10. The repository layer (`app/db/database.py`) gains two read functions — `count_audit_logs()` and `list_audit_logs(limit=100)` — reusing the existing `sqlite3.Row` → `AuditLog` mapping already proven in `get_audit_log` (STORY-002). The route itself (`app/routers/admin.py`, new file) is a thin translation from `AuditLog` (internal, has hashes/previews/success/error fields) to `AuditQueryEntry` (external, already defined in `app/models/schemas.py` by STORY-003) — it is gated by `Depends(require_admin_token)` from STORY-009, reused unmodified. `app/main.py` registers the new router, replacing its STORY-010 placeholder comment.

## User Story

As a compliance officer
I want to see the last 100 logged queries via an admin-only endpoint
So that I can review activity without direct DB access

## Story Reference

- Story file: `.agents/stories/PRD-001-harness-ia/STORY-010-get-audit-endpoint.md`
- PRD: `.agents/PRDs/PRD-001-harness-ia/PRD.md`

## Metadata

| Field | Value |
|-------|-------|
| Type | feature |
| Complexity | medium |
| Systems Affected | `app/db/database.py`, `app/routers/` (new `admin.py`), `app/main.py` |
| Story | STORY-010 |
| PRD | PRD-001 |
| Epic Branch | `epic/PRD-001-harness-ia` (commit directly on this branch) |

---

## Skills In Use

None. `.agents/skills/` contains no `SKILL.md` files, and the story's `skills: []` frontmatter is empty — same situation as STORY-001 through STORY-009.

---

## Codebase State

- `app/db/database.py:71-93` (`get_audit_log`) already does the `sqlite3.Row` → `AuditLog` field-by-field mapping this story needs for a list of rows. Extracting that mapping into a private `_row_to_audit_log(row)` helper avoids duplicating the 13-field constructor call in the new `list_audit_logs`.
- `app/models/schemas.py:39-52` already defines `AuditQueryEntry` and `AuditResponse` (created ahead of schedule by STORY-003, matching PRD Section 10 exactly: `audit_id`, `user_id`, `timestamp`, `model`, `prompt_hash`, `was_duplicate_blocked`, `suspicious_pattern_detected`, `device`). No schema changes needed — only wiring.
- `AuditLog` (`app/db/models.py:24-39`) stores `suspicious_pattern: Optional[str]` (the pattern name, e.g. `"override"`), not a boolean. `AuditQueryEntry.suspicious_pattern_detected` is a `bool`. The router must convert: `suspicious_pattern_detected=log.suspicious_pattern is not None`. Likewise `AuditLog.model_used` maps to `AuditQueryEntry.model`.
- `app/middleware/auth.py:12-18` (`require_admin_token`) is a ready-made `Depends`-compatible dependency, proven reusable across routes by STORY-009's own tests. Applied here via `dependencies=[Depends(require_admin_token)]` on the route decorator — same idiom as any other FastAPI route-level dependency, no new pattern.
- `app/main.py:19-20` has the exact placeholder this story fills: `# Remaining routers registered by later stories: - app.routers.admin (GET /audit, GET /stats) -> STORY-010, STORY-011`. Since STORY-011 (`/stats`) is still `todo`, `app/routers/admin.py` is created fresh by this story (not present yet) and will be extended by STORY-011 later — this story only adds the `/audit` route to it.
- No pagination/ordering helper exists yet. `ORDER BY timestamp DESC LIMIT ?` (parametrized, matching the existing parametrized-query style in `find_duplicate_timestamp`, `app/db/database.py:57-68`) is the only ordering primitive needed — "last 100" per AC 1, "timestamp DESC" per the story's Technical Notes.
- `total` in `AuditResponse` is the **all-time row count** (PRD Section 10 example: `"total": 250` while `"queries"` holds only 100) — a separate `SELECT COUNT(*)` from the LIMIT 100 query, not `len(queries)`.

---

## Design Decisions

1. **Two new repository functions, not one.** `count_audit_logs()` (all-time count) and `list_audit_logs(limit=100)` (bounded, ordered) are separate queries because `total` and `len(queries)` diverge once there are more than 100 rows (AC 1 requires both the true total and a capped list).
2. **Extract `_row_to_audit_log(row)` from `get_audit_log`.** `get_audit_log` and the new `list_audit_logs` both need the same `sqlite3.Row` → `AuditLog` mapping; duplicating a 13-argument constructor call across two functions is the kind of drift that breaks silently when a column is added later. This is a small, in-scope refactor of code this story directly touches — not a speculative cleanup elsewhere.
3. **Route-level `dependencies=[Depends(require_admin_token)]`, not a function parameter.** The dependency returns `None` and is used purely for its side effect (raising on failure); declaring it in `dependencies=[...]` rather than as a handler argument matches how STORY-009's own test app applied it (`tests/test_admin_auth.py:19,24`) and keeps the handler signature free of an unused parameter.
4. **Router-layer mapping from `AuditLog` to `AuditQueryEntry`, not a repository-layer one.** The repository (`app/db/database.py`) deals in the internal `AuditLog` dataclass (used elsewhere for full round-trips, e.g. `get_audit_log` in `query.py`'s error-path test). The external, privacy-filtered shape (`AuditQueryEntry` — no hash of response, no preview, no success/error fields) is a router/API concern, matching the existing separation where `app/routers/query.py` builds `QuerySuccessResponse`/`QueryBlocked*Response` itself rather than pushing response-shaping into the DB layer.

---

## Patterns to Follow

### Parametrized query with ORDER BY / LIMIT
```python
// SOURCE: app/db/database.py:57-68
def find_duplicate_timestamp(prompt_hash: str, since: str) -> Optional[str]:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT timestamp FROM audit_logs
            WHERE prompt_hash = ? AND timestamp >= ?
            ORDER BY timestamp ASC
            LIMIT 1
            """,
            (prompt_hash, since),
        ).fetchone()
        return row["timestamp"] if row is not None else None
```

### Row -> AuditLog mapping (to be extracted into a shared helper)
```python
// SOURCE: app/db/database.py:71-93
def get_audit_log(audit_id: int) -> Optional[AuditLog]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM audit_logs WHERE id = ?", (audit_id,)
        ).fetchone()
        if row is None:
            return None
        return AuditLog(
            id=row["id"],
            timestamp=row["timestamp"],
            ...
        )
```

### Route-level admin gating
```python
// SOURCE: tests/test_admin_auth.py:19-21
@_fake_app.get("/fake-audit", dependencies=[Depends(require_admin_token)])
def fake_audit() -> dict:
    return {"ok": True}
```

### HTTPException at the boundary (no new custom exceptions needed here — no failure path exists in this route beyond auth, already handled by the dependency)
```python
// SOURCE: app/routers/query.py:20-21
if not request.user_id.strip():
    raise HTTPException(status_code=400, detail="user_id is required")
```

### Tests: env bootstrap + temp_db fixture + TestClient(app)
```python
// SOURCE: tests/test_query_router.py:1-29
import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db.database import get_connection, init_db, insert_audit_log
from app.main import app

client = TestClient(app)


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path}")
    init_db()
    return db_path
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/db/database.py` | UPDATE | Extract `_row_to_audit_log`; add `count_audit_logs()` and `list_audit_logs(limit=100)` |
| `app/routers/admin.py` | CREATE | `GET /audit` route, admin-gated, maps `AuditLog` → `AuditQueryEntry` |
| `app/main.py` | UPDATE | Register the admin router; trim the STORY-010 half of the placeholder comment |
| `tests/test_db.py` | UPDATE | Unit tests for `count_audit_logs` / `list_audit_logs` |
| `tests/test_audit_router.py` | CREATE | Endpoint tests: happy path, fewer-than-100, auth rejection before DB access, no-IP/no-raw-text shape check |

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Extract `_row_to_audit_log` helper in `app/db/database.py`

- **File**: `app/db/database.py`
- **Action**: UPDATE
- **Implement**: Add a private function:
  ```python
  def _row_to_audit_log(row: sqlite3.Row) -> AuditLog:
      return AuditLog(
          id=row["id"],
          timestamp=row["timestamp"],
          user_id=row["user_id"],
          device=row["device"],
          prompt_hash=row["prompt_hash"],
          prompt_preview=row["prompt_preview"],
          response_hash=row["response_hash"],
          response_preview=row["response_preview"],
          model_used=row["model_used"],
          tokens_used=row["tokens_used"],
          was_duplicate_blocked=bool(row["was_duplicate_blocked"]),
          suspicious_pattern=row["suspicious_pattern"],
          success=bool(row["success"]),
          error_message=row["error_message"],
      )
  ```
  Then rewrite `get_audit_log` to call it:
  ```python
  def get_audit_log(audit_id: int) -> Optional[AuditLog]:
      with get_connection() as conn:
          row = conn.execute(
              "SELECT * FROM audit_logs WHERE id = ?", (audit_id,)
          ).fetchone()
          if row is None:
              return None
          return _row_to_audit_log(row)
  ```
- **Mirror**: existing `get_audit_log` body (`app/db/database.py:71-93`) — behavior must be byte-identical, this is a pure extraction.
- **Validate**: `pytest tests/test_db.py -v` — all existing tests still pass unchanged.

### Task 2: Add `count_audit_logs` and `list_audit_logs` to `app/db/database.py`

- **File**: `app/db/database.py`
- **Action**: UPDATE
- **Implement**:
  ```python
  def count_audit_logs() -> int:
      with get_connection() as conn:
          row = conn.execute("SELECT COUNT(*) AS n FROM audit_logs").fetchone()
          return row["n"]


  def list_audit_logs(limit: int = 100) -> list[AuditLog]:
      with get_connection() as conn:
          rows = conn.execute(
              "SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT ?",
              (limit,),
          ).fetchall()
          return [_row_to_audit_log(row) for row in rows]
  ```
  Add `import sqlite3` is already present at the top of the file; no new imports needed beyond what's already there.
- **Mirror**: `find_duplicate_timestamp` (`app/db/database.py:57-68`) for the parametrized `ORDER BY ... LIMIT ?` shape; `_count_audit_rows` test helper (`tests/test_query_router.py:32-35`) for the `COUNT(*)` shape.
- **Validate**: `python -c "from app.db.database import count_audit_logs, list_audit_logs"` succeeds.

### Task 3: Add unit tests for the new repository functions

- **File**: `tests/test_db.py`
- **Action**: UPDATE
- **Implement**: Add tests (reusing the existing `temp_db` fixture and `AuditLog`/`insert_audit_log` imports already in the file):
  1. `test_count_audit_logs_empty_returns_zero` — on a fresh `temp_db`, `count_audit_logs() == 0`.
  2. `test_count_audit_logs_reflects_inserted_rows` — insert 3 entries, assert `count_audit_logs() == 3`.
  3. `test_list_audit_logs_orders_newest_first` — insert 3 entries with distinct timestamps out of order, assert `list_audit_logs()` returns them sorted by `timestamp` descending.
  4. `test_list_audit_logs_respects_limit` — insert 3 entries, call `list_audit_logs(limit=2)`, assert `len(...) == 2` and they are the 2 newest.
  5. `test_list_audit_logs_fewer_than_limit_returns_all` — insert 2 entries, call `list_audit_logs(limit=100)`, assert `len(...) == 2` (AC 2).
- **Mirror**: `test_insert_and_read_round_trip` (`tests/test_db.py:33-67`) for `AuditLog`/`insert_audit_log` usage; `temp_db` fixture (`tests/test_db.py:15-20`).
- **Validate**: `pytest tests/test_db.py -v` — all tests (existing + new) pass.

### Task 4: Create `app/routers/admin.py` with `GET /audit`

- **File**: `app/routers/admin.py`
- **Action**: CREATE
- **Implement**:
  ```python
  from fastapi import APIRouter, Depends

  from app.db.database import count_audit_logs, list_audit_logs
  from app.middleware.auth import require_admin_token
  from app.models.schemas import AuditQueryEntry, AuditResponse

  router = APIRouter()


  @router.get(
      "/audit",
      response_model=AuditResponse,
      dependencies=[Depends(require_admin_token)],
  )
  def get_audit() -> AuditResponse:
      total = count_audit_logs()
      queries = [
          AuditQueryEntry(
              audit_id=log.id,
              user_id=log.user_id,
              timestamp=log.timestamp,
              model=log.model_used,
              prompt_hash=log.prompt_hash,
              was_duplicate_blocked=log.was_duplicate_blocked,
              suspicious_pattern_detected=log.suspicious_pattern is not None,
              device=log.device,
          )
          for log in list_audit_logs(limit=100)
      ]
      return AuditResponse(total=total, queries=queries)
  ```
- **Mirror**: `app/routers/query.py:1,15` (`APIRouter()` construction, plain-function handler style); `tests/test_admin_auth.py:19-21` (`dependencies=[Depends(require_admin_token)]` route gating).
- **Validate**: `python -c "from app.routers.admin import router"` succeeds.

### Task 5: Register the admin router in `app/main.py`

- **File**: `app/main.py`
- **Action**: UPDATE
- **Implement**: Add `from app.routers import admin as admin_router` alongside the existing `query` import, call `app.include_router(admin_router.router)` after the query router, and update the trailing comment to drop the STORY-010 half:
  ```python
  from app.db.database import init_db
  from app.routers import admin as admin_router
  from app.routers import query as query_router

  ...

  app.include_router(query_router.router)
  app.include_router(admin_router.router)

  # Remaining routers registered by later stories:
  #   - app.routers.admin GET /stats -> STORY-011
  ```
- **Mirror**: existing `app.include_router(query_router.router)` line (`app/main.py:17`).
- **Validate**: `python -c "from app.main import app; print([r.path for r in app.routes])"` includes `/audit`.

### Task 6: Create `tests/test_audit_router.py`

- **File**: `tests/test_audit_router.py`
- **Action**: CREATE
- **Implement**: Env bootstrap identical to other test files, `temp_db` fixture, `TestClient(app)`. Tests:
  1. `test_missing_admin_token_rejected_before_db_access` — monkeypatch `app.routers.admin.list_audit_logs`/`count_audit_logs` to raise `AssertionError` if called; `client.get("/audit")` with no header → `status_code in (401, 403)` (AC 3).
  2. `test_incorrect_admin_token_rejected` — same monkeypatch guard; `client.get("/audit", headers={"Authorization": "Bearer wrong"})` → rejected (AC 3).
  3. `test_valid_token_returns_expected_shape` — seed 2 rows via `insert_audit_log` (one with `suspicious_pattern="override"`, one with `was_duplicate_blocked=True`), call with `Authorization: Bearer {settings.ADMIN_TOKEN}`, assert `response.status_code == 200` and body matches `{"total": 2, "queries": [...]}` with each entry's keys being exactly `audit_id, user_id, timestamp, model, prompt_hash, was_duplicate_blocked, suspicious_pattern_detected, device` (AC 1), newest-first order.
  4. `test_fewer_than_100_rows_returns_all_without_error` — seed 3 rows, assert `len(body["queries"]) == 3` and `body["total"] == 3` (AC 2).
  5. `test_response_never_includes_ip_or_raw_text` — seed a row, call endpoint, assert no key in any entry contains `"ip"` (case-insensitive) and that no full untruncated prompt/response text field is present — only `prompt_hash` (AC 4).
- **Mirror**: `tests/test_query_router.py:1-29` (bootstrap, fixture, `TestClient`); `tests/test_admin_auth.py:41-46` (bearer-header rejection assertions); `tests/test_db.py:74-95` (no-IP schema assertion style, adapted to response JSON keys).
- **Validate**: `pytest tests/test_audit_router.py -v` — all tests pass.

---

## End-to-End Tests

- [ ] `GET /audit` with a valid admin bearer token returns 200 with `{"total": N, "queries": [...]}` matching PRD Section 10's shape exactly
- [ ] `GET /audit` with fewer than 100 rows in the DB returns all rows, no error
- [ ] `GET /audit` with no/invalid admin token returns 401/403 without touching the DB (verified via monkeypatch guard on the repository functions)
- [ ] Response body, at any row count, never contains an IP field, a raw (non-hashed) prompt, or a raw (non-hashed) response
- [ ] `pytest tests/ -v` (full suite including new/updated files) passes green

---

## Validation

```bash
pytest tests/ -v
python -c "from app.main import app; print([r.path for r in app.routes])"
```

---

## Acceptance Criteria

(Copied from story STORY-010)

- [ ] Given a valid admin token, when `GET /audit` is called, then it returns the total count and the last 100 entries matching PRD Section 10's shape exactly (`audit_id`, `user_id`, `timestamp`, `model`, `prompt_hash`, `was_duplicate_blocked`, `suspicious_pattern_detected`, `device`).
- [ ] Given fewer than 100 rows exist, when `GET /audit` is called, then it returns all existing rows without error.
- [ ] Given an invalid/missing admin token, when `GET /audit` is called, then it is rejected (via STORY-009's middleware) before touching the DB.
- [ ] Given the response payload, when inspected, then it never includes an IP field, a full (non-hashed) prompt, or a full (non-hashed) response.
- [ ] All tasks completed
- [ ] Frontend lint passes — N/A, no frontend in this MVP; substitute `pytest tests/ -v` passes
- [ ] Backend server starts without error
- [ ] Follows existing patterns
