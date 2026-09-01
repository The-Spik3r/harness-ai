---
story: STORY-009
prd: PRD-005
plan: .agents/plans/PRD-005-rbac/completed/STORY-009-audit-rbac-columns.plan.md
epic_branch: epic/PRD-005-rbac
commit: 320d2d2
status: COMPLETE
completed: 2026-08-28
---

# Implementation Report — STORY-009: audit_logs gains role and denied_permission columns

**Plan**: `.agents/plans/PRD-005-rbac/completed/STORY-009-audit-rbac-columns.plan.md`
**Epic Branch**: `epic/PRD-005-rbac`
**Commit**: `320d2d2`

## Summary

Added nullable `role TEXT` and `denied_permission TEXT` columns to `audit_logs`, in both `CREATE_AUDIT_LOGS_TABLE` (fresh databases) and `AUDIT_LOGS_ADDED_COLUMNS` (existing ones, via the additive-migration mechanism hardened in STORY-001), so a denial from the future `authorize()` step can be recorded with the same rigor as a served request. Wired both fields through `AuditLog`, `insert_audit_log`, `_row_to_audit_log`, and two new optional keyword arguments on `log_query()`. No existing caller of `log_query()` passes positional arguments, so all six call sites in `app/services/query_pipeline.py` are untouched and behave identically.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Add `role`/`denied_permission` to `CREATE_AUDIT_LOGS_TABLE` and `AUDIT_LOGS_ADDED_COLUMNS` | `app/db/models.py` | ✅ |
| 2 | Add `role`/`denied_permission` fields to the `AuditLog` dataclass | `app/db/models.py` | ✅ |
| 3 | Wire both columns through `insert_audit_log` and `_row_to_audit_log` | `app/db/database.py` | ✅ |
| 4 | Add `role`/`denied_permission` keyword arguments to `log_query()` | `app/services/audit_logger.py` | ✅ |
| 5 | Extend the pinned-schema test to 19 columns | `tests/test_db.py` | ✅ |
| 6 | Add the pre-RBAC migration fixture and test (AC2) | `tests/test_db.py` | ✅ |
| 7 | Add round-trip/default tests at the `AuditLog`/`insert_audit_log` layer (AC1, AC3) | `tests/test_db.py` | ✅ |
| 8 | Add round-trip/default tests at the `log_query()` layer (AC3, AC4) | `tests/test_audit_logger.py` | ✅ |
| 9 | Full-suite regression and diff gate | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`python -c "from app.main import app"`) | ✅ |
| `tests/test_db.py` | ✅ 53 passed (50 existing + 3 new) |
| `tests/test_audit_logger.py` | ✅ 12 passed (10 existing + 2 new) |
| Full pytest suite | ✅ 347 passed (342 baseline + 5 new) |
| `git diff --name-only` (pre-commit) | ✅ exactly the 5 predicted production/test files |
| Migration against a real probe `.db` file, `init_db()` called twice | ✅ `19 1` (19 columns, 1 row preserved, idempotent) |
| `uvicorn app.main:app` starts | ✅ |
| `curl http://localhost:8000/health` | ✅ `{"status":"ok"}` |
| Repo-root `harness_ai.db` migrated in place via app lifespan | ✅ 19 columns, includes `role`/`denied_permission`, no duplicates |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/db/models.py` | UPDATE | +7/-1 |
| `app/db/database.py` | UPDATE | +6/-0 |
| `app/services/audit_logger.py` | UPDATE | +4/-0 |
| `tests/test_db.py` | UPDATE | +100/-0 |
| `tests/test_audit_logger.py` | UPDATE | +28/-0 |
| `.agents/plans/PRD-005-rbac/completed/STORY-009-audit-rbac-columns.plan.md` | CREATE (archived) | +736 |

## Deviations from Plan

None. Every task was implemented exactly as specified, and every predicted test count (53, 12, 347) matched actual results on the first run.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_db.py` | `test_schema_has_no_ip_or_location_column` (extended to 19 columns), `test_init_db_migrates_pre_rbac_database`, `test_role_and_denied_permission_default_to_none`, `test_role_and_denied_permission_round_trip` |
| `tests/test_audit_logger.py` | `test_role_and_denied_permission_persisted_when_supplied`, `test_role_and_denied_permission_default_to_none_when_omitted` |

## Acceptance Criteria

- [x] Given a fresh database, when `init_db()` runs, then `CREATE_AUDIT_LOGS_TABLE` includes `role TEXT` and `denied_permission TEXT`, both nullable so historical rows stay valid
- [x] Given a pre-RBAC database file, when `init_db()` runs, then both columns are added through `AUDIT_LOGS_ADDED_COLUMNS` and existing rows keep their data with `NULL` in the new fields
- [x] Given `log_query()` is called with `role` and `denied_permission`, when the row is read back, then both values round-trip through `_row_to_audit_log`
- [x] Given `log_query()` is called without them, when it runs, then behavior is identical to today and every existing caller and test is unmodified
