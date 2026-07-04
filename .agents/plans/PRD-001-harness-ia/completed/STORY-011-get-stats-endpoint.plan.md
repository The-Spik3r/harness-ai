---
story: STORY-011
prd: PRD-001
slug: get-stats-endpoint
title: "GET /stats endpoint"
type: feature
complexity: medium
epic_branch: epic/PRD-001-harness-ia
created: 2026-07-04
---

# Plan: GET /stats endpoint

## Summary

Add `GET /stats`, an admin-only endpoint returning aggregate counters over `audit_logs` — `total_queries`, `blocked_duplicates`, `blocked_suspicious`, `unique_users`, `success_rate`, `top_models`, `top_users` — shaped exactly per PRD Section 10. The repository layer (`app/db/database.py`) gains six small aggregate functions (`count_blocked_duplicates`, `count_blocked_suspicious`, `count_unique_users`, `count_successful_queries`, `top_models`, `top_users`), each a single parametrized SQL aggregate, reusing the already-existing `count_audit_logs()` (STORY-010) for `total_queries`. The route is added to the existing `app/routers/admin.py` (created by STORY-010) alongside `/audit`, gated by the same `Depends(require_admin_token)` from STORY-009. `success_rate` percentage formatting and the zero-rows guard happen in the router, not the repository, mirroring STORY-010's precedent that response-shaping is an API concern. `app/main.py` needs no new `include_router` call (the admin router is already registered) — only removal of the now-fully-satisfied placeholder comment.

## User Story

As a security admin
I want an aggregate stats view
So that I can monitor system health and spot abuse trends without reading raw logs

## Story Reference

- Story file: `.agents/stories/PRD-001-harness-ia/STORY-011-get-stats-endpoint.md`
- PRD: `.agents/PRDs/PRD-001-harness-ia/PRD.md`

## Metadata

| Field | Value |
|-------|-------|
| Type | feature |
| Complexity | medium |
| Systems Affected | `app/db/database.py`, `app/routers/admin.py`, `app/main.py` |
| Story | STORY-011 |
| PRD | PRD-001 |
| Epic Branch | `epic/PRD-001-harness-ia` (commit directly on this branch) |

---

## Skills In Use

None. `.agents/skills/` contains no `SKILL.md` files, and the story's `skills: []` frontmatter is empty — same situation as STORY-001 through STORY-010.

---

## Codebase State

- `app/db/database.py:100-112` already has `count_audit_logs()` (`SELECT COUNT(*)`) and `list_audit_logs(limit)` (parametrized `ORDER BY ... LIMIT ?`) from STORY-010 — `total_queries` is exactly `count_audit_logs()`, no new query needed.
- `app/models/schemas.py:55-62` already defines `StatsResponse` (created ahead of schedule by STORY-003, matching PRD Section 10 exactly): `total_queries: int`, `blocked_duplicates: int`, `blocked_suspicious: int`, `unique_users: int`, `success_rate: str`, `top_models: List[str]`, `top_users: List[str]`. No schema changes needed — only wiring.
- `app/db/models.py:24-39` (`AuditLog`) has `was_duplicate_blocked: bool`, `suspicious_pattern: Optional[str]` (pattern name or `None`), `success: bool`, `model_used: Optional[str]`, `user_id: str` — every field needed for the six aggregates already exists in the schema; no migration required.
- `app/routers/admin.py` (STORY-010) already exists with the `/audit` route and its imports (`APIRouter`, `Depends`, `require_admin_token`). This story extends the same file/router object rather than creating a new one — `app/main.py` already calls `app.include_router(admin_router.router)` (`app/main.py:19`), so no new registration call is needed, only trimming the placeholder comment at `app/main.py:21-22`.
- `app/middleware/auth.py:12-18` (`require_admin_token`) is the same ready-made `Depends`-compatible dependency STORY-010 reused unmodified — applied identically here via `dependencies=[Depends(require_admin_token)]`.
- PRD Section 10's `/stats` example (`"top_models": ["gpt-4", "claude-3-sonnet"]`) shows a flat list of names ranked by count, not counts themselves, and doesn't specify how many entries — no other part of the codebase defines a "top N" convention, so this plan picks and documents `limit=5` as the default (see Design Decisions).
- `tests/test_audit_router.py:25-45` establishes the "reject before DB access" test pattern: monkeypatch the repository functions the route imports into `app.routers.admin` to raise `AssertionError` if called, then assert the auth-rejected response never triggered them. The `/stats` tests reuse this pattern against the new aggregate functions.

---

## Design Decisions

1. **Reuse `count_audit_logs()` for `total_queries`.** It already exists (STORY-010) and is exactly "all rows in `audit_logs`" — the same definition PRD Section 10's `/stats` example implies (`"total_queries": 250` counting every logged attempt, success or blocked). No new query.
2. **Six new small aggregate functions, not one `get_stats()` blob.** Mirrors STORY-010's own precedent ("two new repository functions, not one") — each aggregate (`count_blocked_duplicates`, `count_blocked_suspicious`, `count_unique_users`, `count_successful_queries`, `top_models`, `top_users`) is a single independently-testable SQL statement, matching the PRD's "Repository pattern... isolating SQL from route/service logic" (PRD Section 6).
3. **`top_models` / `top_users` default to `limit=5`.** PRD Section 10's example shows only 2 entries and specifies no count. Rather than leaving this ambiguous, `limit=5` is picked as a sensible default (kept as a function parameter, not hardcoded, so it's trivially adjustable later) and documented here so intent is explicit rather than accidental.
4. **`success_rate` computed in the router, not the repository.** Percentage formatting (`"98.4%"`) is response-shaping, matching STORY-010's separation where the DB layer returns raw `AuditLog`/counts and the router builds the external Pydantic shape.
5. **Zero-rows guard: short-circuit `success_rate` to `"0.0%"` when `total_queries == 0`.** Avoids a `ZeroDivisionError`; `top_models`/`top_users` naturally return `[]` from an empty `GROUP BY` with no extra guard needed (AC 5).

---

## Patterns to Follow

### Simple COUNT(*) aggregate (existing, to extend with a WHERE clause)
```python
// SOURCE: app/db/database.py:100-103
def count_audit_logs() -> int:
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM audit_logs").fetchone()
        return row["n"]
```

### Parametrized query with LIMIT
```python
// SOURCE: app/db/database.py:106-112
def list_audit_logs(limit: int = 100) -> list[AuditLog]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [_row_to_audit_log(row) for row in rows]
```

### Admin route, gated, thin router-layer shaping
```python
// SOURCE: app/routers/admin.py:10-30 (existing /audit route)
@router.get(
    "/audit",
    response_model=AuditResponse,
    dependencies=[Depends(require_admin_token)],
)
def get_audit() -> AuditResponse:
    total = count_audit_logs()
    queries = [...]
    return AuditResponse(total=total, queries=queries)
```

### Test: reject-before-DB-access guard
```python
// SOURCE: tests/test_audit_router.py:25-35
def _fail_if_called(*args, **kwargs):
    raise AssertionError("repository function should not have been called")


def test_missing_admin_token_rejected_before_db_access(temp_db, monkeypatch):
    monkeypatch.setattr("app.routers.admin.list_audit_logs", _fail_if_called)
    monkeypatch.setattr("app.routers.admin.count_audit_logs", _fail_if_called)

    response = client.get("/audit")

    assert response.status_code in (401, 403)
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/db/database.py` | UPDATE | Add `count_blocked_duplicates`, `count_blocked_suspicious`, `count_unique_users`, `count_successful_queries`, `top_models`, `top_users` |
| `app/routers/admin.py` | UPDATE | Add `GET /stats` route, admin-gated, builds `StatsResponse` |
| `app/main.py` | UPDATE | Remove the now-fully-satisfied STORY-011 placeholder comment (no new `include_router` call needed) |
| `tests/test_db.py` | UPDATE | Unit tests for the six new aggregate functions |
| `tests/test_stats_router.py` | CREATE | Endpoint tests: happy path, zero-rows, auth rejection before aggregation |

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Add aggregate repository functions to `app/db/database.py`

- **File**: `app/db/database.py`
- **Action**: UPDATE
- **Implement**: Append after `list_audit_logs`:
  ```python
  def count_blocked_duplicates() -> int:
      with get_connection() as conn:
          row = conn.execute(
              "SELECT COUNT(*) AS n FROM audit_logs WHERE was_duplicate_blocked = 1"
          ).fetchone()
          return row["n"]


  def count_blocked_suspicious() -> int:
      with get_connection() as conn:
          row = conn.execute(
              "SELECT COUNT(*) AS n FROM audit_logs WHERE suspicious_pattern IS NOT NULL"
          ).fetchone()
          return row["n"]


  def count_unique_users() -> int:
      with get_connection() as conn:
          row = conn.execute(
              "SELECT COUNT(DISTINCT user_id) AS n FROM audit_logs"
          ).fetchone()
          return row["n"]


  def count_successful_queries() -> int:
      with get_connection() as conn:
          row = conn.execute(
              "SELECT COUNT(*) AS n FROM audit_logs WHERE success = 1"
          ).fetchone()
          return row["n"]


  def top_models(limit: int = 5) -> list[str]:
      with get_connection() as conn:
          rows = conn.execute(
              """
              SELECT model_used FROM audit_logs
              WHERE model_used IS NOT NULL
              GROUP BY model_used
              ORDER BY COUNT(*) DESC
              LIMIT ?
              """,
              (limit,),
          ).fetchall()
          return [row["model_used"] for row in rows]


  def top_users(limit: int = 5) -> list[str]:
      with get_connection() as conn:
          rows = conn.execute(
              """
              SELECT user_id FROM audit_logs
              GROUP BY user_id
              ORDER BY COUNT(*) DESC
              LIMIT ?
              """,
              (limit,),
          ).fetchall()
          return [row["user_id"] for row in rows]
  ```
- **Mirror**: `count_audit_logs` (`app/db/database.py:100-103`) for the `COUNT(*)` shape; `list_audit_logs` (`app/db/database.py:106-112`) for the parametrized `GROUP BY ... ORDER BY ... LIMIT ?` shape.
- **Validate**: `python -c "from app.db.database import count_blocked_duplicates, count_blocked_suspicious, count_unique_users, count_successful_queries, top_models, top_users"` succeeds.

### Task 2: Add unit tests for the new aggregate functions

- **File**: `tests/test_db.py`
- **Action**: UPDATE
- **Implement**: Add tests (reusing the existing `temp_db` fixture and `AuditLog`/`insert_audit_log` imports; add the six new names to the existing `from app.db.database import (...)` block):
  1. `test_count_blocked_duplicates_counts_only_flagged_rows` — insert 2 rows with `was_duplicate_blocked=True` and 1 with `False`, assert `count_blocked_duplicates() == 2`.
  2. `test_count_blocked_suspicious_counts_only_flagged_rows` — insert 2 rows with `suspicious_pattern="override"` and 1 with `suspicious_pattern=None`, assert `count_blocked_suspicious() == 2`.
  3. `test_count_unique_users_deduplicates` — insert 3 rows, two with `user_id="a"` and one with `user_id="b"`, assert `count_unique_users() == 2`.
  4. `test_count_successful_queries_counts_only_success_true` — insert 2 rows with `success=True` and 1 with `success=False`, assert `count_successful_queries() == 2`.
  5. `test_top_models_ranked_by_count_desc` — insert 3 rows for `model_used="gpt-4"`, 1 for `"claude-3-sonnet"`, assert `top_models() == ["gpt-4", "claude-3-sonnet"]`.
  6. `test_top_models_respects_limit` — insert 3 distinct models with descending counts (3, 2, 1), call `top_models(limit=2)`, assert `len(...) == 2` and order is the two highest-count models.
  7. `test_top_users_ranked_by_count_desc` — insert 3 rows for `user_id="a"`, 1 for `user_id="b"`, assert `top_users() == ["a", "b"]`.
  8. `test_aggregates_on_empty_db_return_zero_or_empty` — on a fresh `temp_db`, assert `count_blocked_duplicates() == 0`, `count_blocked_suspicious() == 0`, `count_unique_users() == 0`, `count_successful_queries() == 0`, `top_models() == []`, `top_users() == []` (AC 5).
- **Mirror**: `test_count_audit_logs_reflects_inserted_rows` (`tests/test_db.py:109-119`) and `test_list_audit_logs_orders_newest_first` (`tests/test_db.py:122-139`) for insert-then-assert style.
- **Validate**: `pytest tests/test_db.py -v` — all tests (existing + new) pass.

### Task 3: Add `GET /stats` to `app/routers/admin.py`

- **File**: `app/routers/admin.py`
- **Action**: UPDATE
- **Implement**: Extend the existing import block and append a new route to the same `router`:
  ```python
  from app.db.database import (
      count_audit_logs,
      count_blocked_duplicates,
      count_blocked_suspicious,
      count_successful_queries,
      count_unique_users,
      list_audit_logs,
      top_models,
      top_users,
  )
  from app.middleware.auth import require_admin_token
  from app.models.schemas import AuditQueryEntry, AuditResponse, StatsResponse
  ```
  ```python
  @router.get(
      "/stats",
      response_model=StatsResponse,
      dependencies=[Depends(require_admin_token)],
  )
  def get_stats() -> StatsResponse:
      total = count_audit_logs()
      successful = count_successful_queries()
      success_rate = f"{(successful / total * 100):.1f}%" if total > 0 else "0.0%"

      return StatsResponse(
          total_queries=total,
          blocked_duplicates=count_blocked_duplicates(),
          blocked_suspicious=count_blocked_suspicious(),
          unique_users=count_unique_users(),
          success_rate=success_rate,
          top_models=top_models(),
          top_users=top_users(),
      )
  ```
- **Mirror**: the existing `get_audit()` handler in the same file (`app/routers/admin.py:15-30`) for route-gating and thin-shaping style.
- **Validate**: `python -c "from app.routers.admin import router"` succeeds.

### Task 4: Trim the placeholder comment in `app/main.py`

- **File**: `app/main.py`
- **Action**: UPDATE
- **Implement**: Remove the now-fully-satisfied comment block (lines 21-22):
  ```python
  # Remaining routers registered by later stories:
  #   - app.routers.admin   GET /stats -> STORY-011
  ```
  No new `include_router` call is needed — `app.include_router(admin_router.router)` (`app/main.py:19`) already registers both `/audit` and `/stats` since they share one `router` object.
- **Mirror**: n/a — deletion only.
- **Validate**: `python -c "from app.main import app; print([r.path for r in app.routes])"` includes `/stats`.

### Task 5: Create `tests/test_stats_router.py`

- **File**: `tests/test_stats_router.py`
- **Action**: CREATE
- **Implement**: Env bootstrap identical to `tests/test_audit_router.py`, `temp_db` fixture, `TestClient(app)`. Tests:
  1. `test_missing_admin_token_rejected_before_aggregation` — monkeypatch every aggregate function imported into `app.routers.admin` (`count_audit_logs`, `count_blocked_duplicates`, `count_blocked_suspicious`, `count_unique_users`, `count_successful_queries`, `top_models`, `top_users`) to `_fail_if_called`; `client.get("/stats")` with no header → `status_code in (401, 403)` (AC 4).
  2. `test_incorrect_admin_token_rejected` — same monkeypatch guard; `client.get("/stats", headers={"Authorization": "Bearer wrong"})` → rejected (AC 4).
  3. `test_valid_token_returns_expected_shape_and_values` — seed rows covering: 2 successful/non-blocked (`user_id="a"`, `model_used="gpt-4"`), 1 duplicate-blocked (`was_duplicate_blocked=True`, `success=False`), 1 suspicious-blocked (`suspicious_pattern="override"`, `success=False`), across 2 distinct users. Call with valid token, assert `status_code == 200`, `body.keys() == {"total_queries", "blocked_duplicates", "blocked_suspicious", "unique_users", "success_rate", "top_models", "top_users"}` (AC 1), assert exact counts, assert `success_rate == "50.0%"` (2 successful / 4 total) (AC 2), assert `top_models`/`top_users` are lists ordered by count descending (AC 3).
  4. `test_zero_rows_returns_zeroed_stats_without_error` — on an empty `temp_db`, call with valid token, assert `status_code == 200` and body == `{"total_queries": 0, "blocked_duplicates": 0, "blocked_suspicious": 0, "unique_users": 0, "success_rate": "0.0%", "top_models": [], "top_users": []}` (AC 5).
- **Mirror**: `tests/test_audit_router.py:1-45` (bootstrap, fixture, `TestClient`, `_fail_if_called` guard pattern).
- **Validate**: `pytest tests/test_stats_router.py -v` — all tests pass.

---

## End-to-End Tests

- [ ] `GET /stats` with a valid admin bearer token returns 200 with all seven fields matching PRD Section 10's shape exactly
- [ ] `success_rate` is computed as `(successful / total) * 100`, formatted as a one-decimal percentage string (e.g. `"98.4%"`)
- [ ] `top_models` / `top_users` are ordered by query count descending
- [ ] `GET /stats` with no/invalid admin token returns 401/403 without touching the DB (verified via monkeypatch guard on all repository functions)
- [ ] `GET /stats` against an empty `audit_logs` table returns zeroed/empty values with no error (no `ZeroDivisionError`)
- [ ] `pytest tests/ -v` (full suite including new/updated files) passes green

---

## Validation

```bash
pytest tests/ -v
python -c "from app.main import app; print([r.path for r in app.routes])"
```

---

## Acceptance Criteria

(Copied from story STORY-011)

- [ ] Given any amount of history in `audit_logs`, when `GET /stats` is called with a valid admin token, then it returns `total_queries`, `blocked_duplicates`, `blocked_suspicious`, `unique_users`, `success_rate`, `top_models`, `top_users` matching PRD Section 10's shape.
- [ ] Given `success_rate`, when computed, then it is `(successful queries / total queries) * 100`, formatted as a percentage string (e.g. `"98.4%"`).
- [ ] Given `top_models`/`top_users`, when computed, then they are ranked by query count, descending.
- [ ] Given an invalid/missing admin token, when `GET /stats` is called, then it is rejected before any aggregation query runs.
- [ ] Given zero rows exist in `audit_logs`, when `GET /stats` is called, then it returns zeroed/empty values without dividing by zero or erroring.
- [ ] All tasks completed
- [ ] Frontend lint passes — N/A, no frontend in this MVP; substitute `pytest tests/ -v` passes
- [ ] Backend server starts without error
- [ ] Follows existing patterns
