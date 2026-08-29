---
story: STORY-011
prd: PRD-005
plan: .agents/plans/PRD-005-rbac/completed/STORY-011-model-allowlist-and-byok.plan.md
epic_branch: epic/PRD-005-rbac
commit: PENDING
status: COMPLETE
completed: 2026-08-28
---

# Implementation Report — STORY-011: Server-side model allowlist and BYOK as a privilege

**Plan**: `.agents/plans/PRD-005-rbac/completed/STORY-011-model-allowlist-and-byok.plan.md`
**Epic Branch**: `epic/PRD-005-rbac`
**Commit**: PENDING

## Summary

Added two deny-by-default checks to `run_query()`'s step-0 block, both evaluated after `query:submit` and before `check_duplicate()`: a new `authorize_model(identity, model)` in `app/services/authz.py` (roles in `MODEL_ALLOWLIST_WILDCARD_ROLES` — `{"admin"}` — may request any model; every other role is checked against `settings.model_allowlist_list`), and reuse of the existing `authorize(identity, PERMISSION_QUERY_BYOK)` guarded by `openrouter_api_key is not None`. The repeated log-and-return denial shape (log_query + QueryBlockedForbiddenResponse) was extracted into a `_deny()` helper used by all three checks, refactoring STORY-010's `query:submit` block without changing its behavior.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Add `MODEL_ALLOWLIST_WILDCARD_ROLES` + `authorize_model()` | `app/services/authz.py` | ✅ |
| 2 | Wire model + BYOK checks into `run_query()`'s step 0, extract `_deny()` | `app/services/query_pipeline.py` | ✅ |
| 3 | `authorize_model()` tests | `tests/test_authz.py` | ✅ |
| 4 | Model + BYOK denial tests | `tests/test_query_pipeline_authorization.py` | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| `python -c "import app.services.authz"` | ✅ |
| `python -c "import app.services.query_pipeline"` | ✅ |
| `pytest tests/test_authz.py` | ✅ (32 passed) |
| `pytest tests/test_query_pipeline_authorization.py` | ✅ (10 passed) |
| `pytest tests/test_authz.py tests/test_query_pipeline_authorization.py tests/test_chat_state.py tests/test_pii_dedup_isolation.py tests/test_config.py tests/test_schemas.py tests/test_audit_logger.py` | ✅ (105 passed, 17 pre-existing failures — identical count/set on baseline HEAD, STORY-013/014 scope) |
| `pytest tests/` (full repo) | ✅ (290 passed, 71 pre-existing failures — identical count on baseline HEAD before this story) |
| E2E | ✅ (3/3 — see below) |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/services/authz.py` | UPDATE | +21/-0 |
| `app/services/query_pipeline.py` | UPDATE | +25/-12 |
| `tests/test_authz.py` | UPDATE | +34/-1 |
| `tests/test_query_pipeline_authorization.py` | UPDATE | +117/-1 |

## Deviations from Plan

None. Implementation matches the plan's tasks, patterns, and file list exactly.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_authz.py` | `test_admin_model_wildcard_allows_any_model`, `test_user_role_allows_models_in_allowlist`, `test_user_role_denies_model_outside_allowlist`, `test_rbac_disabled_bypasses_model_check` |
| `tests/test_query_pipeline_authorization.py` | `test_model_outside_allowlist_blocked_before_openrouter`, `test_admin_wildcard_model_reaches_openrouter`, `test_model_denial_writes_audit_row_with_role_and_permission`, `test_byok_without_permission_blocked_before_openrouter`, `test_byok_with_permission_uses_supplied_key`, `test_byok_denial_writes_audit_row_with_role_and_permission` |

## Acceptance Criteria

- [x] Given a role whose allowlist is `*`, when any model is requested, then it is allowed
- [x] Given a `user`-role caller requesting a model outside `MODEL_ALLOWLIST`, when `run_query()` runs, then it returns `QueryBlockedForbiddenResponse` with `required_permission="query:model:<model>"` and never calls OpenRouter
- [x] Given a request carrying `openrouter_api_key` from an identity without `query:byok`, when `run_query()` runs, then it is refused before the OpenRouter call
- [x] Given the same request from an identity holding `query:byok`, when it runs, then the supplied key is used exactly as today
- [x] Given either refusal, when it happens, then an audit row records the role and the missing permission
