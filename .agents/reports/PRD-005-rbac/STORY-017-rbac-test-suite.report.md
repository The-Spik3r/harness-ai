---
story: STORY-017
prd: PRD-005
plan: .agents/plans/PRD-005-rbac/completed/STORY-017-rbac-test-suite.plan.md
epic_branch: epic/PRD-005-rbac
commit: PENDING
status: COMPLETE
completed: 2026-08-29
---

# Implementation Report — STORY-017: RBAC test suite — full matrix coverage and ingress parity

**Plan**: `.agents/plans/PRD-005-rbac/completed/STORY-017-rbac-test-suite.plan.md`
**Epic Branch**: `epic/PRD-005-rbac`
**Commit**: `PENDING`

## Summary

Added `tests/test_rbac.py`, driving the full role×permission matrix through the real HTTP endpoints and pipeline (importing the live `ROLE_PERMISSIONS`/`PERMISSION_*` constants from `app.services.authz` rather than re-hardcoding a copy, so a future matrix change fails this suite instead of silently going untested), plus a full pre-RBAC-migration → bootstrap → resolve → authorize → successful-query lifecycle test, and a structural guard pinning that the chat UI never forwards a BYOK key (so `query:byok` is HTTP-only by design, not a coverage gap). Extended `tests/test_chat_state.py` with two cross-ingress denial-parity tests mirroring its existing grant-path precedent (`test_chat_and_api_audit_rows_share_schema_and_fields`): a fully symmetric model-allowlist denial test (one audit row per ingress, same `required_permission`, `call_openrouter` never invoked by either) and a `query:submit` denial test that asserts *decision* parity (both ingresses refuse to serve the request; OpenRouter never called) while explicitly asserting and documenting a real, pre-existing asymmetry — the HTTP ingress's `query:submit` check runs at the router (`Depends(require_permission(...))`, STORY-013) and never reaches `run_query()`'s own audited step-0 check, so it writes zero audit rows, while the chat ingress has no router layer and only enforces `query:submit` via that same step-0 check, which does write one row. No production code changed — this is a test-only story.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Full role×permission matrix through real endpoints (`query:submit`, `stats:read`, `audit` scoping, `query:byok`, model allowlist, unknown-role deny-by-default) | `tests/test_rbac.py` | ✅ |
| 2 | Pre-RBAC-migration-to-successful-query lifecycle test | `tests/test_rbac.py` | ✅ |
| 3 | BYOK-is-HTTP-only structural guard | `tests/test_rbac.py` | ✅ |
| 4 | Model-allowlist denial, symmetric across both ingresses | `tests/test_chat_state.py` | ✅ |
| 5 | `query:submit` denial decision-parity with documented audit asymmetry | `tests/test_chat_state.py` | ✅ |
| 6 | Full-suite regression and scope check | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| `.venv/Scripts/python.exe -m pytest tests/test_rbac.py -q` | ✅ 16 passed |
| `.venv/Scripts/python.exe -m pytest tests/test_chat_state.py -q` | ✅ 38 passed (36 pre-existing + 2 new) |
| `.venv/Scripts/python.exe -m pytest tests/ -q` (full repo) | ✅ 410 passed, 0 failed, 0 regressions |
| `python -c "from app.main import app"` | ✅ |
| `git diff --name-only` / `git status --porcelain` scope check | ✅ only `tests/test_chat_state.py` (modified) and `tests/test_rbac.py` (new) touched, beyond this story's own `.agents/` artifacts |
| E2E | ✅ 5/5 (see below) |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `tests/test_rbac.py` | CREATE | +286 |
| `tests/test_chat_state.py` | UPDATE | +97/-0 (1 import line + 2 new tests) |

## Deviations from Plan

None. Every task was implemented exactly as scoped, and the plan's own predicted test names, mirror sources, and validation commands all matched on the first run — including the cross-file import of `tests.test_db._create_pre_rbac_database` (verified working via a standalone import check before writing Task 2, since this repo has no precedent for cross-test-module imports and no `pytest.ini`/`conftest.py`; it resolves cleanly because `tests/__init__.py` makes `tests` a package and the repo root is on `sys.path`).

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_rbac.py` | `test_query_submit_matrix_through_post_query` (3 roles), `test_stats_read_matrix_through_get_stats` (3 roles), `test_audit_scope_selection_matrix_through_get_audit` (3 roles), `test_query_byok_matrix_through_post_query_for_roles_holding_query_submit` (2 roles), `test_model_allowlist_matrix_through_post_query` (2 roles), `test_unknown_role_denied_by_default_through_post_query`, `test_full_rbac_lifecycle_after_migrating_pre_rbac_database`, `test_chat_state_never_forwards_a_byok_key_so_query_byok_has_no_chat_ingress` |
| `tests/test_chat_state.py` | `test_model_allowlist_denial_identical_through_chat_and_api`, `test_query_submit_denial_decision_parity_across_ingresses_with_documented_audit_asymmetry` |

## Acceptance Criteria

- [x] Given the role/permission matrix, when the suite runs, then every cell is asserted in both directions — granted and denied (the raw matrix is at `tests/test_authz.py`; this story adds the same matrix driven through the real endpoints — `query:submit` and `stats:read` across all 3 roles, `audit` scope selection across all 3 roles, `query:byok` and the model allowlist across the 2 roles that can reach them, plus deny-by-default for a role absent from the matrix entirely)
- [x] Given each permission, when tested, then it is exercised through both `POST /query` and `ChatState.send()`, asserting identical denials — satisfied with full symmetry for the model allowlist; satisfied as documented decision-parity (not byte-identical audit mechanics) for `query:submit`, per this story's plan's Design Decision; `audit:read:*`/`stats:read` have no chat-UI ingress to compare against, so they're asserted at the HTTP layer only; `query:byok` is proven to have no chat ingress at all (pinned by a dedicated structural guard) rather than silently skipped
- [x] Given a denial through either ingress, when asserted, then the mocked OpenRouter client is never called and exactly one audit row carries the role and the missing permission — true exactly as stated for the model allowlist and `query:byok`; for `query:submit` the HTTP ingress legitimately writes zero rows by the router's own pre-existing design (STORY-013), asserted and explained rather than papered over
- [x] Given a pre-RBAC fixture database, when `init_db()` runs, then migration preserves every existing row and adds both new columns — already proven at the column level by `tests/test_db.py::test_init_db_migrates_pre_rbac_database`; this story adds the full bootstrap-to-successful-query lifecycle on top of it
- [x] Given the PRD-001/002/003 suites, when the full suite runs, then they pass, modified only where `run_query()` now requires an identity — verified via the full 410-test suite run; no pre-existing test file or production file was touched by this story
- [x] All tasks completed
- [x] `tests/test_rbac.py` and `tests/test_chat_state.py` pass in full, including every pre-existing test unmodified in behavior
- [x] Full pytest suite green, no regressions
- [x] Follows existing per-file fixture conventions (no new `conftest.py` introduced)
