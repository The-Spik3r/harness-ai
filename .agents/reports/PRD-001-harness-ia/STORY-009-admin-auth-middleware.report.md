---
story: STORY-009
prd: PRD-001
plan: .agents/plans/PRD-001-harness-ia/completed/STORY-009-admin-auth-middleware.plan.md
epic_branch: epic/PRD-001-harness-ia
commit: ad50787
status: COMPLETE
completed: 2026-07-04
---

# Implementation Report — STORY-009: Admin token authentication middleware

**Plan**: `.agents/plans/PRD-001-harness-ia/completed/STORY-009-admin-auth-middleware.plan.md`
**Epic Branch**: `epic/PRD-001-harness-ia`
**Commit**: `ad50787`

## Summary

Added `app/middleware/auth.py` with a `require_admin_token` FastAPI `Depends`-compatible dependency. It uses `HTTPBearer(auto_error=False)` to extract the `Authorization: Bearer <token>` header and `secrets.compare_digest` for a timing-safe comparison against `settings.ADMIN_TOKEN`. Both a missing header and a wrong token converge on the same `HTTPException(401, "Invalid or missing admin token")`, so the dependency can be applied to any route via `Depends(require_admin_token)` without per-route auth logic — ready for STORY-010 (`/audit`) and STORY-011 (`/stats`) to consume.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Create middleware package marker | `app/middleware/__init__.py` | ✅ |
| 2 | Create `require_admin_token` dependency | `app/middleware/auth.py` | ✅ |
| 3 | Create unit tests via throwaway two-route test app | `tests/test_admin_auth.py` | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`app.middleware.auth`) | ✅ |
| Backend import (`app.main`) | ✅ |
| Tests | ✅ (9 new / 61 total passed) |
| Server starts + `/health` returns 200 | ✅ |
| E2E (AC 1–4 exercised directly) | ✅ (4/4) |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/middleware/__init__.py` | CREATE | +0 |
| `app/middleware/auth.py` | CREATE | +17 |
| `tests/test_admin_auth.py` | CREATE | +95 |

## Deviations from Plan

None. Implementation matched the plan exactly.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_admin_auth.py` | `test_missing_authorization_header_rejected` (both routes), `test_incorrect_bearer_token_rejected` (both routes), `test_correct_bearer_token_allowed` (both routes), `test_non_bearer_scheme_rejected`, `test_same_dependency_protects_both_routes`, `test_token_compared_via_constant_time_check` |

## Acceptance Criteria

- [x] Given a request to an admin-gated route without an `Authorization` bearer header, when handled, then it is rejected with 401/403.
- [x] Given a request with an incorrect bearer value, when handled, then it is rejected with 401/403.
- [x] Given a request with a bearer value matching `ADMIN_TOKEN`, when handled, then it is allowed through to the route handler.
- [x] Given the dependency is reused, when applied to both `/audit` and `/stats`, then the same check logic is used (no duplicated auth code per route).
