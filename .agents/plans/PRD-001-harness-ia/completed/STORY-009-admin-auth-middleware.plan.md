---
story: STORY-009
prd: PRD-001
slug: admin-auth-middleware
title: Admin token authentication middleware
type: technical
complexity: small
epic_branch: epic/PRD-001-harness-ia
created: 2026-07-04
---

# Plan: Admin token authentication middleware

## Summary

Add `app/middleware/auth.py`, a FastAPI `Depends`-compatible dependency function `require_admin_token(...)` that gates admin-only routes behind a bearer token matching `settings.ADMIN_TOKEN`. Per the story's explicit technical note and PRD Section 6 ("Dependency injection via FastAPI `Depends` for DB sessions and admin-token verification"), this is implemented as a dependency, not raw ASGI middleware, so it can be applied per-route via `Depends(require_admin_token)` on `/audit` (STORY-010) and `/stats` (STORY-011) without either route duplicating the check. The dependency uses FastAPI's `HTTPBearer(auto_error=False)` security scheme to extract the `Authorization: Bearer <token>` header, and `secrets.compare_digest` for a timing-safe comparison against `settings.ADMIN_TOKEN`. Both "no header" and "wrong token" fail through the exact same branch and raise the same `HTTPException(401, "Invalid or missing admin token")` — a single generic message, matching the existing codebase's one-message-per-failure-mode style (`app/routers/query.py:21`) and avoiding leaking which failure mode occurred. Since `/audit` and `/stats` don't exist yet (STORY-010/011 are still `todo`), this story proves reusability (AC 4) with a small throwaway test app containing two routes that both apply `Depends(require_admin_token)`, rather than wiring into real endpoints that don't exist.

## User Story

As an admin
I want `/audit` and `/stats` protected by an admin token
So that only authorized staff can see even the hashed/truncated audit data

## Story Reference

- Story file: `.agents/stories/PRD-001-harness-ia/STORY-009-admin-auth-middleware.md`
- PRD: `.agents/PRDs/PRD-001-harness-ia/PRD.md`

## Metadata

| Field | Value |
|-------|-------|
| Type | technical |
| Complexity | small |
| Systems Affected | `app/middleware/` (new package) |
| Story | STORY-009 |
| PRD | PRD-001 |
| Epic Branch | `epic/PRD-001-harness-ia` (commit directly on this branch) |

---

## Skills In Use

None. `.agents/skills/` contains no `SKILL.md` files, and the story's `skills: []` frontmatter is empty — same situation as STORY-001 through STORY-008.

---

## Codebase State

`app/config.py:8` already defines `ADMIN_TOKEN: str` as a required field on the pydantic `Settings` class, loaded from `.env`/environment at `Settings()` construction time (`app/config.py:16`). Every existing test file bootstraps `ADMIN_TOKEN` before importing `app.config` via `os.environ.setdefault("ADMIN_TOKEN", "test-token")` (`tests/test_query_router.py:1-4`, and identically in `tests/test_openrouter_client.py` per STORY-007's plan) — the new test file must do the same, and can override the value per-test with `monkeypatch.setattr(settings, "ADMIN_TOKEN", ...)` (the same mechanism used for `DATABASE_URL` in `tests/test_query_router.py:27` and `OPENROUTER_API_KEY` in STORY-007).

No `app/middleware/` directory exists yet — `app/main.py:19-20` has an explicit placeholder comment: `# Remaining routers registered by later stories: - app.routers.admin (GET /audit, GET /stats) -> STORY-010, STORY-011`. This story creates the first file under `app/middleware/`; it does not touch `app/main.py` or create `app/routers/admin.py` — those are STORY-010/011's job. `app/routers/admin.py` doesn't exist, so AC 4 (dependency reused across `/audit` and `/stats`) cannot be demonstrated on real routes yet; it's demonstrated via a small in-test FastAPI app with two routes.

`app/routers/query.py:21,26,70` is the only existing precedent for raising `HTTPException`: always `HTTPException(status_code=<int>, detail=<str>)`, no custom headers, no custom exception classes for HTTP-layer errors (custom exceptions like `DuplicateCheckError`/`OpenRouterError` exist only in the service layer, per STORY-004/007, and get translated to `HTTPException` at the router boundary). `require_admin_token` follows this same convention directly — it raises `HTTPException` itself since it *is* the boundary (a dependency, not a service function), so no new exception class is needed.

No `fastapi.security` usage exists anywhere in the codebase yet; this is the first use of `HTTPBearer`. `requirements.txt` needs no changes — `HTTPBearer` ships with `fastapi`, already a dependency.

---

## Design Decisions

1. **`Depends`-based dependency, not ASGI middleware.** The story's Technical Notes and PRD Section 6 both explicitly call for a FastAPI dependency "for easy per-route application" — global ASGI middleware would protect *every* route (including `/query` and `/health`, which must stay open) and would need internal path-based branching to exempt them, which is more complex than a `Depends` that's simply omitted from those routes.

2. **`HTTPBearer(auto_error=False)` + manual check, not `auto_error=True`.** With `auto_error=True`, FastAPI's `HTTPBearer` raises its own `403 Forbidden` on a missing header but gives no hook to unify that with the "wrong token" case, which must also fail. Using `auto_error=False` (credentials become `None` when absent) lets both failure modes — missing header and wrong token — converge on one `raise HTTPException(401, ...)` call, matching AC 1 and AC 2's identical "rejected with 401/403" wording via a single code path instead of two.

3. **`secrets.compare_digest` for the token comparison**, not `==`. Not called out explicitly in the AC text, but this story is labeled `security`, and a static shared-secret comparison (PRD Section 9 risk #4 already flags `ADMIN_TOKEN` as "a weak auth model if leaked") is the canonical case for a timing-safe comparison — it's a one-line stdlib call, not new complexity.

4. **One generic error message for both failure modes** (`"Invalid or missing admin token"`), not two distinct messages. Distinguishing "you sent nothing" from "you sent the wrong thing" in the response body would let an attacker probe whether a token format is even being checked; a single message costs nothing functionally since both cases are already handled by the same status code per the ACs.

5. **No wiring into `/audit` or `/stats`, no change to `app/main.py`.** Those routes don't exist yet (STORY-010/011, still `todo`). This story's scope, per its own title and AC 4's phrasing ("when applied to both... the same check logic is used"), is the reusable dependency itself; AC 4 is validated with a throwaway two-route test app, not real endpoints.

---

## Patterns to Follow

### HTTPException at the boundary (status_code + detail only)
```python
// SOURCE: app/routers/query.py:20-21
if not request.user_id.strip():
    raise HTTPException(status_code=400, detail="user_id is required")
```
`require_admin_token` raises `HTTPException(status_code=401, detail="Invalid or missing admin token")` the same way — no custom exception class, since the dependency itself sits at the HTTP boundary.

### Settings access (read at call time, mockable via monkeypatch)
```python
// SOURCE: app/config.py:1-16
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    ...
    ADMIN_TOKEN: str

settings = Settings()
```
`require_admin_token` does `from app.config import settings` at module level and reads `settings.ADMIN_TOKEN` inside the function body (not captured at import time), so tests can `monkeypatch.setattr(settings, "ADMIN_TOKEN", ...)`.

### Tests: env-var bootstrap (every test file repeats this before importing `app.config`)
```python
// SOURCE: tests/test_query_router.py:1-4
import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")
```
`tests/test_admin_auth.py` opens with the same two lines.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/middleware/__init__.py` | CREATE | Empty package marker (mirrors `app/services/__init__.py`) |
| `app/middleware/auth.py` | CREATE | `require_admin_token` FastAPI dependency — bearer-token check against `settings.ADMIN_TOKEN` |
| `tests/test_admin_auth.py` | CREATE | Unit tests for the dependency via a throwaway two-route test app |

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Create `app/middleware/__init__.py`

- **File**: `app/middleware/__init__.py`
- **Action**: CREATE
- **Implement**: Empty file (package marker only).
- **Mirror**: `app/services/__init__.py` (empty).
- **Validate**: `python -c "import app.middleware"` succeeds.

### Task 2: Create `app/middleware/auth.py`

- **File**: `app/middleware/auth.py`
- **Action**: CREATE
- **Implement**:
  ```python
  import secrets
  from typing import Optional

  from fastapi import Depends, HTTPException
  from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

  from app.config import settings

  _bearer_scheme = HTTPBearer(auto_error=False)


  def require_admin_token(
      credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
  ) -> None:
      if credentials is None or not secrets.compare_digest(
          credentials.credentials, settings.ADMIN_TOKEN
      ):
          raise HTTPException(status_code=401, detail="Invalid or missing admin token")
  ```
- **Mirror**: `app/routers/query.py:1,20-21` (`HTTPException(status_code=..., detail=...)` style); `app/config.py:8,16` (`settings.ADMIN_TOKEN` read contract).
- **Validate**: `python -c "from app.middleware.auth import require_admin_token"` succeeds.

### Task 3: Create `tests/test_admin_auth.py`

- **File**: `tests/test_admin_auth.py`
- **Action**: CREATE
- **Implement**: Env-var bootstrap (mirror `tests/test_query_router.py:1-4`). Build a small local `FastAPI()` test app with two routes — `@app.get("/fake-audit")` and `@app.get("/fake-stats")` — both declared with `dependencies=[Depends(require_admin_token)]`, to exercise AC 4 (same dependency, two routes, no duplicated check code) without depending on STORY-010/011's real routers. Wrap it in a `TestClient`. Tests, parametrized over both routes where noted:
  1. `test_missing_authorization_header_rejected` — `client.get("/fake-audit")` with no headers → `response.status_code in (401, 403)` (AC 1).
  2. `test_incorrect_bearer_token_rejected` — `client.get("/fake-audit", headers={"Authorization": "Bearer wrong-token"})` → `response.status_code in (401, 403)` (AC 2).
  3. `test_correct_bearer_token_allowed` — `client.get("/fake-audit", headers={"Authorization": "Bearer test-token"})` → `response.status_code == 200` (AC 3).
  4. `test_non_bearer_scheme_rejected` — `client.get("/fake-audit", headers={"Authorization": "Basic dGVzdC10b2tlbg=="})` → rejected (401/403), confirming only `Bearer` scheme is accepted.
  5. `test_same_dependency_protects_both_routes` — call both `/fake-audit` and `/fake-stats` with no header, and again with the correct token; assert both reject without it and both allow with it, proving one dependency function gates both routes (AC 4).
  6. `test_token_compared_via_constant_time_check` — `monkeypatch` `app.middleware.auth.secrets.compare_digest` to a wrapper that records it was called, call with the correct token, assert the wrapper was invoked (confirms Design Decision 3 isn't silently dropped in a refactor).
- **Mirror**: `tests/test_query_router.py:1-19` (env bootstrap, `TestClient` construction); `tests/test_query_router.py:56-62` (status-code assertion style).
- **Validate**: `pytest tests/test_admin_auth.py -v` — all tests pass.

---

## End-to-End Tests

- [ ] Request to a `Depends(require_admin_token)`-gated route with no `Authorization` header → 401/403 (AC 1)
- [ ] Request with an incorrect bearer value → 401/403 (AC 2)
- [ ] Request with `Authorization: Bearer <ADMIN_TOKEN value>` → allowed through (AC 3)
- [ ] Two independent routes both using `Depends(require_admin_token)` behave identically under all of the above, with zero duplicated check logic (AC 4)
- [ ] `pytest tests/ -v` (full existing suite + new file) passes green

---

## Validation

```bash
pytest tests/test_admin_auth.py -v
pytest tests/ -v
python -c "from app.middleware.auth import require_admin_token"
```

---

## Acceptance Criteria

(Copied from story STORY-009)

- [ ] Given a request to an admin-gated route without an `Authorization` bearer header, when handled, then it is rejected with 401/403.
- [ ] Given a request with an incorrect bearer value, when handled, then it is rejected with 401/403.
- [ ] Given a request with a bearer value matching `ADMIN_TOKEN`, when handled, then it is allowed through to the route handler.
- [ ] Given the dependency is reused, when applied to both `/audit` and `/stats`, then the same check logic is used (no duplicated auth code per route).
- [ ] All tasks completed
- [ ] Frontend lint passes — N/A, no frontend in this MVP; substitute `pytest tests/ -v` passes
- [ ] Backend server starts without error
- [ ] Follows existing patterns (`Depends`-based dependency, `HTTPException(status_code, detail)` at the boundary, `settings` read at call time)
