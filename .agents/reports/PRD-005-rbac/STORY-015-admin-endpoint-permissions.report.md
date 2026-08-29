---
story: STORY-015
prd: PRD-005
plan: .agents/plans/PRD-005-rbac/completed/STORY-015-admin-endpoint-permissions.plan.md
epic_branch: epic/PRD-005-rbac
commit: PENDING
status: COMPLETE
completed: 2026-08-28
---

# Implementation Report — STORY-015: /audit scoping and /stats gating by permission

**Plan**: `.agents/plans/PRD-005-rbac/completed/STORY-015-admin-endpoint-permissions.plan.md`
**Epic Branch**: `epic/PRD-005-rbac`
**Commit**: `PENDING`

## Summary

`/audit` and `/stats` were both gated by the same all-or-nothing `dependencies=[Depends(require_admin_token)]` inherited from PRD-001. This story moves each onto the RBAC primitives STORY-012 built.

`/stats` now declares `dependencies=[Depends(require_permission(PERMISSION_STATS_READ))]`; its handler body is byte-for-byte unchanged, so the response shape is untouched.

`/audit` resolves the caller as a parameter via `Depends(require_identity)` and makes the scoping decision inside the handler, because a router `Depends` cannot express "either of two permissions grants". It calls `authorize(identity, PERMISSION_AUDIT_READ_ALL)` first — success means `scope_user_id = None`, i.e. today's full-visibility behavior — and on `PermissionDenied` falls back to `authorize(identity, PERMISSION_AUDIT_READ_OWN)`, which scopes to `identity.user_id`. Only when both raise does the handler return `403`. Because `authorize()` returns early when `RBAC_ENABLED=false`, the first check always passes under the documented escape hatch and the endpoint keeps returning everything.

Scoping happens in SQL, not in Python: `count_audit_logs()` and `list_audit_logs()` gained an optional `user_id` keyword that switches to a parametrized `WHERE user_id = ?` branch. With the default `user_id=None` both reproduce today's exact query, so every existing caller is unaffected — including `/stats`'s own unscoped `count_audit_logs()`.

`AuditQueryEntry` gained `role` and `denied_permission`, populated straight off the `AuditLog` the router already holds. `_row_to_audit_log()` had round-tripped both columns since STORY-009; this story is the display half. Both default to `None` so pre-RBAC rows with `NULL` serialize cleanly.

`require_admin_token` is now used by no route in the codebase. It is intentionally left in place in `app/middleware/auth.py` (still directly exercised by `tests/test_admin_auth.py`): PRD Section 4 keeps `ADMIN_TOKEN` as a break-glass credential that `identity.resolve()` maps to the `admin` role, and `admin` holds every permission these two endpoints check — so `ADMIN_TOKEN` keeps working end to end through `require_identity`/`require_permission`, verified by E2E step 2 below.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | `list_audit_logs`/`count_audit_logs` gain optional per-user scoping | `app/db/database.py` | ✅ |
| 2 | `AuditQueryEntry` gains `role` and `denied_permission` | `app/models/schemas.py` | ✅ |
| 3 | `/audit` → `require_identity` + scoping; `/stats` → `require_permission` | `app/routers/admin.py` | ✅ |
| 4 | Scoping, 403-on-neither, and field-serialization tests | `tests/test_audit_router.py` | ✅ |
| 5 | 403-without-`stats:read` and 200-with-`stats:read` tests | `tests/test_stats_router.py` | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| `python -c "import app.routers.admin; from app.main import app"` | ✅ |
| `tests/test_audit_router.py`, `tests/test_stats_router.py`, `tests/test_admin_auth.py`, `tests/test_db.py`, `tests/test_schemas.py`, `tests/test_pii_redaction_integration.py` | ✅ 111 passed |
| Full suite `pytest -q` | ✅ 386 passed |
| E2E | ✅ 7/7 (see below) |

Frontend lint is not applicable: this story touches no `chat_ui` code, and the repo has no `frontend/` directory.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/db/database.py` | UPDATE | +23/-7 |
| `app/models/schemas.py` | UPDATE | +2/-0 |
| `app/routers/admin.py` | UPDATE | +29/-11 |
| `tests/test_audit_router.py` | UPDATE | +86/-2 |
| `tests/test_stats_router.py` | UPDATE | +45/-2 |
| `tests/test_schemas.py` | UPDATE (deviation) | +2/-0 |
| `tests/test_pii_redaction_integration.py` | UPDATE (deviation) | +2/-0 |

## Deviations from Plan

Two files outside the plan's "Files to Change" list asserted on the exact `AuditQueryEntry` key set and so failed once Task 2 added two fields. Both were caught by running the full suite rather than only the plan's named targets, and both are pure contract-list updates — no behavior changed:

1. **`tests/test_schemas.py`** — `test_audit_response_shape()` compares a serialized `AuditResponse` against a literal dict. Added `"role": None, "denied_permission": None`.
2. **`tests/test_pii_redaction_integration.py`** — `test_audit_endpoint_contract_has_no_preview_fields()` asserts `sorted(entry) == [...]`, a guard that the audit contract exposes no raw-text or IP fields. Added `"denied_permission"` and `"role"` in sorted position; the guard's actual intent (no `prompt_preview` / `response_preview` / `response_hash`) is untouched.

No other deviations. All five plan tasks were implemented exactly as specified.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_audit_router.py` | `test_auditor_role_sees_every_row` (AC1 via a non-admin `audit:read:all` grant), `test_user_role_sees_only_own_rows_and_scoped_total` (AC2), `test_identity_lacking_both_audit_permissions_returns_403` (AC3, seeding `role="guest"` — absent from `ROLE_PERMISSIONS`, so `authorize()` denies by default without touching the matrix), `test_audit_entry_carries_role_and_denied_permission` (AC5, including the `NULL`→`None` case) |
| `tests/test_stats_router.py` | `test_identity_lacking_stats_read_returns_403_naming_permission` (AC4, 403 half), `test_auditor_role_reads_stats_with_unchanged_shape` (AC4, unchanged-shape half via a non-admin `stats:read` grant) |

Existing tests in both files were extended only where the `AuditQueryEntry` key set is asserted; no pre-existing test changed behavior.

## Acceptance Criteria

- [x] Given an identity with `audit:read:all`, when `GET /audit` is called, then every row is returned as today
- [x] Given an identity with only `audit:read:own`, when it is called, then only that user's rows are returned and `total` reflects the scoped count
- [x] Given an identity with neither permission, when it is called, then it returns `403`
- [x] Given `GET /stats` and an identity without `stats:read`, when it is called, then it returns `403`; with the permission, the response shape is unchanged
- [x] Given an audit entry, when serialized, then it carries `role` and `denied_permission`
- [x] All tasks completed
- [x] `tests/test_audit_router.py` and `tests/test_stats_router.py` pass in full, including all pre-existing tests unmodified in behavior
- [x] Follows existing `Depends(require_identity)` / `Depends(require_permission(...))` / `authorize()`/`PermissionDenied` patterns

## End-to-End Verification

Ran `uvicorn app.main:app --port 8123` against a throwaway SQLite DB seeded with `ana` (`user`), `reviewer` (`auditor`), and two audit rows — one owned by `ana` carrying `role="user"` / `denied_permission="query:byok"`, one owned by `bob` with both `NULL`.

1. ✅ `GET /health` → `200 {"status":"ok"}`
2. ✅ `GET /audit` with `ADMIN_TOKEN` → `200`, `total: 2`, both rows — break-glass credential still works through `require_identity`
3. ✅ `GET /audit` with `ana-token` (`user`, `audit:read:own` only) → `200`, `total: 1`, single row, `user_id: "ana"` — `total` is the scoped count, not 2
4. ✅ `GET /audit` with `auditor-token` (`audit:read:all`) → `200`, `total: 2`, both rows — non-admin full visibility
5. ✅ Every returned entry carries `role` and `denied_permission`: `ana`'s row → `"user"` / `"query:byok"`; `bob`'s row → `null` / `null`
6. ✅ `GET /stats` with `ana-token` → `403 {"detail":"Permission denied: stats:read"}`
7. ✅ `GET /stats` with `auditor-token` → `200`, all nine keys present and unchanged; `GET /audit` with no header → `401 {"detail":"Invalid or missing credential"}`
