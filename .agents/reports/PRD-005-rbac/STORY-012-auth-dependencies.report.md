---
story: STORY-012
prd: PRD-005
plan: .agents/plans/PRD-005-rbac/completed/STORY-012-auth-dependencies.plan.md
epic_branch: epic/PRD-005-rbac
commit: 0d0b800
status: COMPLETE
completed: 2026-08-28
---

# Implementation Report — STORY-012: require_identity and require_permission FastAPI dependencies

**Plan**: `.agents/plans/PRD-005-rbac/completed/STORY-012-auth-dependencies.plan.md`
**Epic Branch**: `epic/PRD-005-rbac`
**Commit**: PENDING

## Summary

Added `require_identity` and `require_permission(permission)` to `app/middleware/auth.py`, both built on the existing `HTTPBearer(auto_error=False)` scheme. `require_identity` resolves the bearer credential via `identity.resolve(...)` and raises `401` (`"Invalid or missing credential"`) on `None`. `require_permission(permission)` is a dependency factory: its inner function depends on `require_identity`, calls `authz.authorize(identity, permission)`, and maps `PermissionDenied` to `403` (`"Permission denied: {permission}"`), returning the resolved `Identity` so a future caller can inject it from the same `Depends(...)`. `require_admin_token` was reimplemented on top of `require_identity`, checking `identity.role == "admin"` instead of comparing the token directly — the `secrets.compare_digest` check against `ADMIN_TOKEN` still runs, now inside `identity.resolve()`, which keeps `tests/test_admin_auth.py` (including its constant-time-comparison monkeypatch test) passing unmodified.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Add `require_identity` | `app/middleware/auth.py` | ✅ |
| 2 | Add `require_permission(permission)`; reimplement `require_admin_token` | `app/middleware/auth.py` | ✅ |
| 3 | New dependency test file | `tests/test_auth_dependencies.py` | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| `python -c "import app.middleware.auth"` | ✅ |
| `python -c "from app.main import app"` (via `.venv`) | ✅ |
| `pytest tests/test_auth_dependencies.py` | ✅ (10 passed) |
| `pytest tests/test_admin_auth.py` | ✅ (9 passed, unmodified) |
| `pytest tests/test_auth_dependencies.py tests/test_admin_auth.py tests/test_authz.py tests/test_identity.py` | ✅ (73 passed) |
| `pytest tests/` (full repo, via `.venv`) | ✅ (300 passed, 71 pre-existing failures — identical count/set on baseline HEAD before this story; documented STORY-010/013/014 scope gap) |
| E2E | ✅ (3/3 — see below) |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/middleware/auth.py` | UPDATE | +23/-5 |
| `tests/test_auth_dependencies.py` | CREATE | +150 |

## Deviations from Plan

None. Implementation matches the plan's tasks, patterns, and file list exactly.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_auth_dependencies.py` | `test_require_identity_rejects_missing_credential`, `test_require_identity_rejects_invalid_credential`, `test_require_identity_rejects_non_bearer_scheme`, `test_require_identity_returns_resolved_identity_for_valid_credential`, `test_require_identity_resolves_admin_token`, `test_require_permission_rejects_identity_lacking_permission`, `test_require_permission_allows_identity_with_permission`, `test_require_permission_rejects_missing_credential_with_401_not_403`, `test_require_admin_token_still_authenticates_admin_token`, `test_require_admin_token_rejects_non_admin_identity` |

## End-to-End Verification

- [x] `pytest tests/test_auth_dependencies.py -q` — all green
- [x] `pytest tests/test_admin_auth.py -q` — passes unmodified
- [x] Manual: started `uvicorn app.main:app` locally; `GET /audit` and `GET /stats` with `Authorization: Bearer <ADMIN_TOKEN>` returned `200`, the same endpoint with a wrong token returned `401` — confirms `require_admin_token`'s reimplementation preserves external behavior with no router changes in this story

## Acceptance Criteria

- [x] Given no or an invalid bearer credential, when `require_identity` runs, then it raises `401` with `"Invalid or missing credential"`
- [x] Given a valid credential, when `require_identity` runs, then it returns the resolved `Identity`
- [x] Given an identity lacking the required permission, when `require_permission(p)` runs, then it raises `403` with `"Permission denied: {p}"`
- [x] Given the existing `ADMIN_TOKEN`, when sent to `/audit` or `/stats`, then it still authenticates as `admin` and `tests/test_admin_auth.py` passes unmodified
- [x] Given `require_admin_token` is reimplemented on top of the new dependencies, when exercised, then its externally observable behavior is unchanged
