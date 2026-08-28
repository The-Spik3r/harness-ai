---
story: STORY-006
prd: PRD-005
plan: .agents/plans/PRD-005-rbac/completed/STORY-006-authz-permission-matrix.plan.md
epic_branch: epic/PRD-005-rbac
commit: 5d5281a
status: COMPLETE
completed: 2026-08-28
---

# Implementation Report — STORY-006: authz service — permission constants, default role matrix, deny-by-default authorize()

**Plan**: `.agents/plans/PRD-005-rbac/completed/STORY-006-authz-permission-matrix.plan.md`
**Epic Branch**: `epic/PRD-005-rbac`
**Commit**: `5d5281a`

## Summary

Added `app/services/authz.py`, a greenfield policy module: five permission-name string constants, the built-in `ROLE_PERMISSIONS` role→permission matrix for `admin`/`auditor`/`user` matching PRD-005 Section 7 exactly, a `PermissionDenied` exception carrying the denied permission name, and a deny-by-default `authorize(identity, permission)` function with a single explicit `RBAC_ENABLED=false` bypass branch. The module has no consumer yet — wiring `authorize()` into `query_pipeline.py` as step 0 is STORY-010, out of scope here. Full unit coverage added in `tests/test_authz.py` (22 tests), including a parametrized full-matrix check (every role × permission pair, both grant and deny directions).

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Create authz service (constants, matrix, `PermissionDenied`, `authorize()`) | `app/services/authz.py` | ✅ |
| 2 | Create full-coverage test suite | `tests/test_authz.py` | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Module import (`python -c "from app.services.authz import ..."`) | ✅ |
| `tests/test_authz.py` | ✅ (22 passed) |
| Full suite (`tests/` minus pre-existing environment gap, see Deviations) | ✅ (188 passed, 0 regressions) |
| E2E | ✅ (unit-level only; no HTTP/UI surface for this story, per plan) |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/services/authz.py` | CREATE | +57 |
| `tests/test_authz.py` | CREATE | +109 |

## Deviations from Plan

- **Pre-existing environment gap, not a regression**: `python -m pytest tests/ -v` fails to *collect* 10 test files (`test_audit_router.py`, `test_chat_state.py`, `test_integration.py`, `test_main.py`, `test_pii_dedup_isolation.py`, `test_pii_redaction_integration.py`, `test_pii_redactor.py`, `test_query_router.py`, `test_route_reservations.py`, `test_stats_router.py`) and fails 4 tests in `test_chat_components_import.py`, all with the identical root cause: `ModuleNotFoundError: No module named 'presidio_analyzer'`. This package (a PRD-003 dependency, listed in `requirements.txt`) is not installed in this dev environment. `authz.py` and `test_authz.py` neither import nor touch `pii_redactor.py` or anything that depends on it — confirmed by running the suite with those 10 files excluded via `--ignore`, which passed 188/188 including all 22 new tests, with the same 4 `test_chat_components_import.py` failures attributable solely to the same missing package. This is an environment-setup issue predating this story, not something STORY-006 introduced or is responsible for fixing.
- Everything else matched the plan as written; no other deviations.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_authz.py` | `test_matrix_cell_matches_prd_section_7` (15 parametrized cases, every role×permission cell, grant+deny), `test_admin_matrix_matches_prd_exactly`, `test_auditor_matrix_matches_prd_exactly`, `test_user_matrix_matches_prd_exactly`, `test_unknown_role_raises_permission_denied`, `test_denied_permission_carries_the_permission_name`, `test_granted_permission_returns_none`, `test_rbac_disabled_allows_even_an_unknown_role` |

## Acceptance Criteria

- [x] Given the built-in matrix, when evaluated, then it matches PRD Section 7 exactly for `admin`, `auditor`, and `user` across `query:submit`, `query:byok`, `audit:read:all`, `audit:read:own`, and `stats:read`
- [x] Given an identity whose role is not in the matrix, when `authorize()` runs, then it raises `PermissionDenied` — deny by default, never a fallback grant
- [x] Given a permission absent from the role's grants, when `authorize()` runs, then it raises `PermissionDenied` carrying the permission name
- [x] Given a granted permission, when `authorize()` runs, then it returns `None` and raises nothing
- [x] Given `RBAC_ENABLED=false`, when `authorize()` runs, then it allows, and that bypass is a single explicit branch with its own test
