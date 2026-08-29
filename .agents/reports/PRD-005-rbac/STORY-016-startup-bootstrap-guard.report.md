---
story: STORY-016
prd: PRD-005
plan: .agents/plans/PRD-005-rbac/completed/STORY-016-startup-bootstrap-guard.plan.md
epic_branch: epic/PRD-005-rbac
commit: PENDING
status: COMPLETE
completed: 2026-08-29
---

# Implementation Report — STORY-016: Fail-fast startup guard when RBAC is enabled with no seeded users

**Plan**: `.agents/plans/PRD-005-rbac/completed/STORY-016-startup-bootstrap-guard.plan.md`
**Epic Branch**: `epic/PRD-005-rbac`
**Commit**: `PENDING`

## Summary

Added `authz.check_bootstrap()`, a zero-arg startup guard mirroring the exact `authz.load()`/`AuthzConfigError` idiom already established for `RBAC_ROLES_FILE` (STORY-007): it raises `RbacNotBootstrappedError` when `RBAC_ENABLED=true` and `count_active_users() == 0`, naming the exact `scripts/manage_users.py create-user` command to fix it. The guard checks the `users` table directly rather than trusting `ADMIN_TOKEN` presence, because `identity.resolve()` synthesizes a break-glass `admin` identity from `ADMIN_TOKEN` without ever reading that table — so break-glass alone can never satisfy bootstrap (AC5). It is wired into both `app/main.py`'s `lifespan` (called synchronously, left uncaught, so Starlette/Uvicorn treats it as a fatal startup failure) and `chat_ui/chat_ui/chat_ui.py`'s `app.register_lifespan_task(...)`, since Reflex's `api_transformer` mounts the FastAPI app under an outer Starlette app whose own lifespan runs instead of `app.main`'s — the same duplication `init_db()`, `pii_redactor.load()`, and `authz.load()` already require.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Add `RbacNotBootstrappedError` and `check_bootstrap()` | `app/services/authz.py` | ✅ |
| 2 | Call `authz.check_bootstrap()` in `lifespan`, after `authz.load()` | `app/main.py` | ✅ |
| 3 | Register `authz.check_bootstrap` as a chat UI lifespan task, after `authz.load` | `chat_ui/chat_ui/chat_ui.py` | ✅ |
| 4 | Guard behavior tests across RBAC_ENABLED, active-user count, ADMIN_TOKEN-alone | `tests/test_main.py` | ✅ |
| 5 | Chat UI entry-point wiring + behavior tests (subprocess probe) | `tests/test_chat_ui_startup_guard.py` | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| `python -c "from app.services.authz import check_bootstrap, RbacNotBootstrappedError"` | ✅ |
| `python -c "import app.main"` | ✅ |
| `python -m pytest tests/test_main.py -q` | ✅ (9 passed) |
| `python -m pytest tests/test_chat_ui_startup_guard.py -q` | ✅ (2 passed) |
| `python -m pytest tests/ -q` (full suite) | ✅ (392 passed) |
| Manual: `RBAC_ENABLED=true` + empty DB via `uvicorn app.main:app` | ✅ exits, names `scripts/manage_users.py create-user` |
| Manual: seed one user via CLI, then boot | ✅ `/health` → 200 |
| Manual: `RBAC_ENABLED=false` + empty DB, boot | ✅ `/health` → 200 (escape hatch preserved) |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/services/authz.py` | UPDATE | +26/-0 |
| `app/main.py` | UPDATE | +1/-0 |
| `chat_ui/chat_ui/chat_ui.py` | UPDATE | +5/-0 |
| `tests/test_main.py` | UPDATE | +55/-0 |
| `tests/test_chat_ui_startup_guard.py` | CREATE | +76 |

## Deviations from Plan

- **`tests/test_main.py`'s pre-existing PII-lifespan tests and the roles-file test now monkeypatch `RBAC_ENABLED=False`.** These tests use `with TestClient(app):` against the real dev `DATABASE_URL` (`sqlite:///harness_ai.db`), which has no seeded active users. Once `authz.check_bootstrap()` was wired into the lifespan, those four pre-existing tests (`test_lifespan_loads_pii_analyzer_before_serving_requests`, `test_lifespan_does_not_reload_analyzer_on_first_request`, `test_lifespan_skips_analyzer_when_redaction_disabled`, `test_lifespan_loads_roles_file_before_serving_requests`) started failing with `RbacNotBootstrappedError`, since they are unrelated to RBAC bootstrap and never seeded a user. Fixed by disabling `RBAC_ENABLED` for the scope of those tests (via the shared `_small_model_and_reset` fixture and one inline `monkeypatch.setattr` call) — this was not called out in the plan, which only anticipated the guard's own new tests, not its interaction with pre-existing lifespan tests against the shared dev database.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_main.py` | `test_lifespan_fails_fast_when_rbac_enabled_and_no_active_users`, `test_lifespan_boots_when_rbac_enabled_and_one_active_user`, `test_lifespan_skips_guard_when_rbac_disabled`, `test_lifespan_fails_fast_even_with_only_admin_token_configured` |
| `tests/test_chat_ui_startup_guard.py` | `test_check_bootstrap_registered_as_chat_ui_lifespan_task`, `test_check_bootstrap_raises_against_empty_users_table` |

## Acceptance Criteria

- [x] Given `RBAC_ENABLED=true` and zero active users, when the app starts, then it exits with a message naming `scripts/manage_users.py create-user`
- [x] Given `RBAC_ENABLED=true` and at least one active user, when it starts, then it boots normally
- [x] Given `RBAC_ENABLED=false`, when it starts, then the guard does not run and PRD-001 behavior is preserved exactly
- [x] Given the chat UI entry point, when it starts, then the same guard runs there too
- [x] Given only `ADMIN_TOKEN` is configured and no users are seeded, when it starts, then the guard still fails — break-glass is not a substitute for bootstrap
