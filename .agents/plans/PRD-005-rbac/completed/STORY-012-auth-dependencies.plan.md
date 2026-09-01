---
story: STORY-012
prd: PRD-005
slug: auth-dependencies
title: require_identity and require_permission FastAPI dependencies
type: NEW_CAPABILITY
complexity: MEDIUM
epic_branch: epic/PRD-005-rbac
created: 2026-08-28
---

# Plan: require_identity and require_permission FastAPI dependencies

## Summary

`app/middleware/auth.py` today has one dependency, `require_admin_token`, which compares the bearer credential directly against `settings.ADMIN_TOKEN` and knows nothing about `Identity` or the permission matrix built in STORY-003/STORY-006. This story adds two new dependencies on the same `HTTPBearer(auto_error=False)` scheme already declared in the file: `require_identity`, which resolves the bearer credential via `identity.resolve(...)` and raises `401` on `None`, and `require_permission(permission)`, a dependency **factory** that depends on `require_identity` and additionally calls `authz.authorize(identity, permission)`, mapping `PermissionDenied` to `403`. `require_admin_token` is then reimplemented on top of `require_identity`, checking `identity.role == "admin"` instead of comparing tokens directly — `identity.resolve()` already runs the `secrets.compare_digest` check against `ADMIN_TOKEN` internally, so the constant-time-comparison property in the story's Technical Notes is preserved, and `tests/test_admin_auth.py` is left untouched and green. These dependencies are HTTP-layer defense in depth only: they gate `POST /query` (STORY-013) and `/audit`/`/stats` (STORY-015) but the pipeline's own `authorize()` call at `run_query()` step 0 (STORY-010) remains the authoritative control the chat UI's in-process ingress cannot bypass.

## User Story

As an integrating developer
I want dependencies that resolve an identity and assert a permission
So that every HTTP route shares one authentication path with consistent status codes

## Story Reference

- Story file: `.agents/stories/PRD-005-rbac/STORY-012-auth-dependencies.md`
- PRD: `.agents/PRDs/PRD-005-rbac/PRD.md`

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | MEDIUM |
| Systems Affected | `app/middleware/auth.py`, auth dependency test suite |
| Story | STORY-012 |
| PRD | PRD-005 |
| Epic Branch | `epic/PRD-005-rbac` (commit directly on this branch) |

---

## Skills In Use

None. `skills: []` in story frontmatter; `.agents/skills/` contains only `frontend-design`, which does not apply to this backend-only story.

---

## Patterns to Follow

### Existing HTTPBearer scheme + admin dependency (extend, do not duplicate)
```
// SOURCE: app/middleware/auth.py:1-19 (current file, in full)
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

### identity.resolve() contract (already returns None for every failure case alike)
```
// SOURCE: app/services/identity.py:46-62
def resolve(token: Optional[str]) -> Optional[Identity]:
    if not token:
        return None
    if secrets.compare_digest(token, settings.ADMIN_TOKEN):
        return Identity(user_id=_ADMIN_BREAK_GLASS_USER_ID, role=_ADMIN_ROLE)
    user = find_user_by_token_hash(hash_token(token))
    if user is None:
        return None
    return Identity(user_id=user.user_id, role=user.role)
```
The `secrets.compare_digest` call already lives inside `resolve()` — routing `require_admin_token` through `require_identity` keeps that constant-time comparison on the `ADMIN_TOKEN` path without re-implementing it in `auth.py`.

### authorize() / PermissionDenied contract
```
// SOURCE: app/services/authz.py:99-109
def authorize(identity: Identity, permission: str) -> None:
    if not settings.RBAC_ENABLED:
        return
    role_permissions = ROLE_PERMISSIONS.get(identity.role)
    if role_permissions is None or permission not in role_permissions:
        raise PermissionDenied(permission)
```
`PermissionDenied.permission` (app/services/authz.py:51-57) carries the permission name for the `403` message.

### Dependency-factory shape used elsewhere in the router layer
```
// SOURCE: app/routers/admin.py:21-25
@router.get(
    "/audit",
    response_model=AuditResponse,
    dependencies=[Depends(require_admin_token)],
)
```
`require_permission(p)` must return something usable the same way — `Depends(require_permission(PERMISSION_QUERY_SUBMIT))` — which means it is a **function that returns a dependency callable**, not a dependency itself.

### test_admin_auth.py's fake-app harness (do not modify; new tests mirror this shape)
```
// SOURCE: tests/test_admin_auth.py:1-30
os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")
...
_fake_app = FastAPI()

@_fake_app.get("/fake-audit", dependencies=[Depends(require_admin_token)])
def fake_audit() -> dict:
    return {"ok": True}

client = TestClient(_fake_app)
```

### temp_db fixture + insert_user (for tests needing a real non-admin identity)
```
// SOURCE: tests/test_identity.py:19-24, 30-33
@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path}")
    init_db()
    return db_path

def test_resolve_returns_identity_for_valid_active_user(temp_db):
    insert_user(User(user_id="ana", role="user", token_hash=hash_token("plaintext-token")))
    assert resolve("plaintext-token") == Identity(user_id="ana", role="user")
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/middleware/auth.py` | UPDATE | Add `require_identity`; add `require_permission(permission)` factory; reimplement `require_admin_token` on top of `require_identity` |
| `tests/test_auth_dependencies.py` | CREATE | Tests for AC1 (`require_identity` 401 on no/invalid credential), AC2 (`require_identity` returns `Identity` on valid credential), AC3 (`require_permission` 403 on missing permission, carries the permission name), AC4/AC5 (`require_admin_token` reimplementation: `ADMIN_TOKEN` still authenticates as admin; a non-admin identity is rejected) |

Not touched in this story (explicitly deferred by the Technical Notes / story dependency graph):
- `app/routers/query.py` — STORY-013 wires `Depends(require_identity)` into `POST /query`
- `app/routers/admin.py` — STORY-015 moves `/audit`/`/stats` onto `require_permission(...)`; they keep using `require_admin_token` unchanged until then
- `tests/test_admin_auth.py` — must pass **unmodified** per AC4; not edited by this story

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Add `require_identity` to `app/middleware/auth.py`

- **File**: `app/middleware/auth.py`
- **Action**: UPDATE
- **Implement**:
  1. Add an import for the identity service and the `Identity` type:
     ```python
     from app.services.identity import Identity, resolve
     ```
  2. Add the new dependency, reusing the existing `_bearer_scheme`:
     ```python
     def require_identity(
         credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
     ) -> Identity:
         identity = resolve(credentials.credentials if credentials else None)
         if identity is None:
             raise HTTPException(status_code=401, detail="Invalid or missing credential")
         return identity
     ```
     Place it above `require_admin_token` (Task 2 makes `require_admin_token` depend on it, so it must be defined first in reading order).
- **Mirror**: `app/middleware/auth.py:12-18` (current `require_admin_token`) for the `Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme)` parameter shape; `app/services/identity.py:46-62` for what `resolve()` guarantees (`None` covers every failure case alike).
- **Validate**: `python -c "import app.middleware.auth"` succeeds.

### Task 2: Add `require_permission(permission)` and reimplement `require_admin_token`

- **File**: `app/middleware/auth.py`
- **Action**: UPDATE
- **Implement**:
  1. Add an import for the authorization service:
     ```python
     from app.services.authz import PermissionDenied, authorize
     ```
  2. Add the dependency factory, placed after `require_identity`:
     ```python
     def require_permission(permission: str):
         def _require_permission(identity: Identity = Depends(require_identity)) -> Identity:
             try:
                 authorize(identity, permission)
             except PermissionDenied:
                 raise HTTPException(
                     status_code=403, detail=f"Permission denied: {permission}"
                 )
             return identity

         return _require_permission
     ```
     Returning `identity` (not `None`) from the inner function lets a future caller (STORY-015) inject the resolved `Identity` from the same `Depends(require_permission(...))` call it uses to gate the route, without a second dependency.
  3. Replace the body of `require_admin_token` to depend on `require_identity` instead of comparing the token directly:
     ```python
     def require_admin_token(identity: Identity = Depends(require_identity)) -> None:
         if identity.role != "admin":
             raise HTTPException(status_code=401, detail="Invalid or missing admin token")
     ```
     Delete the now-unused `credentials`/`secrets.compare_digest` logic from this function — `secrets.compare_digest` still runs, but inside `identity.resolve()` via `require_identity`, not here. Keep the `import secrets` line only if `tests/test_admin_auth.py`'s `auth_module.secrets` reference needs it to resolve (it does: `secrets` is a module singleton, so `auth_module.secrets.compare_digest` and `identity_module.secrets.compare_digest` are the same object — the monkeypatch in `test_token_compared_via_constant_time_check` intercepts the call made inside `identity.py` even though it's triggered via `auth.py`'s `require_admin_token` → `require_identity` → `resolve()` chain). Do not remove the `import secrets` statement from `app/middleware/auth.py`.
- **Mirror**: `app/services/authz.py:99-109` for the `try/except PermissionDenied` → `HTTPException` shape; PRD Section 10's exact `401`/`403` body examples (`{"detail": "Invalid or missing credential"}`, `{"detail": "Permission denied: query:submit"}`) — both already match `HTTPException`'s default `{"detail": ...}` rendering, so no custom exception handler is needed.
- **Validate**: `python -c "import app.middleware.auth"` succeeds; `python -m pytest tests/test_admin_auth.py -q` passes unmodified (AC4).

### Task 3: New test file for the two dependencies

- **File**: `tests/test_auth_dependencies.py`
- **Action**: CREATE
- **Implement**: Follow the `_fake_app` + `TestClient` harness from `tests/test_admin_auth.py:1-29` (`os.environ.setdefault(...)` header, a throwaway `FastAPI()` instance, routes wired with `Depends(...)`) plus the `temp_db`/`insert_user` fixture from `tests/test_identity.py:19-24` for cases needing a real non-admin user. Cover:
  - `test_require_identity_rejects_missing_credential` (AC1): no `Authorization` header on a route gated by `Depends(require_identity)` → `401`, detail `"Invalid or missing credential"`.
  - `test_require_identity_rejects_invalid_credential` (AC1): `Authorization: Bearer not-a-real-token` → `401`.
  - `test_require_identity_rejects_non_bearer_scheme` (AC1): `Authorization: Basic ...` → `401` (mirrors `test_admin_auth.py`'s `test_non_bearer_scheme_rejected`).
  - `test_require_identity_returns_resolved_identity_for_valid_credential` (AC2): route handler returns the injected `Identity` as JSON (e.g. `{"user_id": identity.user_id, "role": identity.role}`); using `temp_db` + `insert_user(User(user_id="ana", role="user", token_hash=hash_token("tok")))`, assert the response body equals `{"user_id": "ana", "role": "user"}`.
  - `test_require_identity_resolves_admin_token` (AC2 sanity): same route, `Authorization: Bearer {settings.ADMIN_TOKEN}` → `{"user_id": "admin", "role": "admin"}`.
  - `test_require_permission_rejects_identity_lacking_permission` (AC3): route gated by `Depends(require_permission(PERMISSION_QUERY_BYOK))`; a `temp_db` user with role `"user"` (lacks `query:byok` per the matrix in `app/services/authz.py:40-43`) → `403`, detail `"Permission denied: query:byok"`.
  - `test_require_permission_allows_identity_with_permission` (AC3 sanity): same route with role `"admin"` (or the `ADMIN_TOKEN`) → `200`.
  - `test_require_permission_rejects_missing_credential` (AC1 composed with AC3): no header on the `require_permission`-gated route → `401`, not `403` — proves identity resolution runs before the permission check.
  - `test_require_admin_token_still_authenticates_admin_token` (AC4): `Authorization: Bearer {settings.ADMIN_TOKEN}` on a route gated by `Depends(require_admin_token)` → `200` (same assertion `test_admin_auth.py` already makes, duplicated here only to prove the reimplementation didn't regress it before running the full unmodified file).
  - `test_require_admin_token_rejects_non_admin_identity` (AC5): `temp_db` user with role `"user"` presented to a `require_admin_token`-gated route → rejected (`401`), proving a *valid* but non-admin identity is still refused, which `test_admin_auth.py` alone cannot exercise (it only ever sends the admin token or garbage).
  - Import `PERMISSION_QUERY_BYOK` from `app.services.authz`, `require_admin_token`, `require_identity`, `require_permission` from `app.middleware.auth`, `insert_user`, `init_db` from `app.db.database`, `User` from `app.db.models`, `hash_token` from `app.services.identity`, `settings` from `app.config`; use `os.environ.setdefault("OPENROUTER_API_KEY", "test-key")` and `os.environ.setdefault("ADMIN_TOKEN", "test-token")` at module top exactly as `tests/test_admin_auth.py` and `tests/test_identity.py` do.
- **Mirror**: `tests/test_admin_auth.py:1-30` (fake-app + client harness), `tests/test_identity.py:19-24` (`temp_db` fixture).
- **Validate**: `python -m pytest tests/test_auth_dependencies.py -q` — all new tests pass.

---

## End-to-End Tests

- [ ] `python -m pytest tests/test_auth_dependencies.py -q` — all green
- [ ] `python -m pytest tests/test_admin_auth.py -q` — passes **unmodified** (AC4)
- [ ] Manual: `curl -H "Authorization: Bearer <ADMIN_TOKEN>" http://localhost:8000/audit` still returns `200` (no router changes in this story, so `/audit` and `/stats` still use `require_admin_token`, now reimplemented)

---

## Validation

```bash
cd F:/AI/harness-ai
python -c "import app.middleware.auth"
python -m pytest tests/test_auth_dependencies.py tests/test_admin_auth.py tests/test_authz.py tests/test_identity.py -q
```

---

## Acceptance Criteria

(Copied from story `STORY-012`)

- [ ] Given no or an invalid bearer credential, when `require_identity` runs, then it raises `401` with `"Invalid or missing credential"`
- [ ] Given a valid credential, when `require_identity` runs, then it returns the resolved `Identity`
- [ ] Given an identity lacking the required permission, when `require_permission(p)` runs, then it raises `403` with `"Permission denied: {p}"`
- [ ] Given the existing `ADMIN_TOKEN`, when sent to `/audit` or `/stats`, then it still authenticates as `admin` and `tests/test_admin_auth.py` passes unmodified
- [ ] Given `require_admin_token` is reimplemented on top of the new dependencies, when exercised, then its externally observable behavior is unchanged
- [ ] All tasks completed
- [ ] `app/middleware/auth.py` imports cleanly and `tests/test_auth_dependencies.py`, `tests/test_admin_auth.py` pass
- [ ] Follows existing `HTTPBearer` / `Depends(...)` / constant-time-comparison patterns
