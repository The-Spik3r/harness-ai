---
story: STORY-005
prd: PRD-005
plan: .agents/plans/PRD-005-rbac/completed/STORY-005-rbac-configuration-settings.plan.md
epic_branch: epic/PRD-005-rbac
commit: c2aca34
status: COMPLETE
completed: 2026-08-28
---

# Implementation Report — STORY-005: RBAC configuration settings and env vars

**Plan**: `.agents/plans/PRD-005-rbac/completed/STORY-005-rbac-configuration-settings.plan.md`
**Epic Branch**: `epic/PRD-005-rbac`
**Commit**: `c2aca34`

## Summary

Completed the `RBAC_*` env-var group in `app/config.py` that STORY-004 started (it had already added `RBAC_DEFAULT_ROLE`). Added `RBAC_ENABLED` (bool, default `true`), `RBAC_ROLES_FILE` (str, default `""`), and `MODEL_ALLOWLIST` (CSV str, default the four PRD-listed models), plus a `model_allowlist_list` property that parses `MODEL_ALLOWLIST` using the identical split/strip/filter logic `pii_entities_list` already uses for `PII_ENTITIES`. Documented all four RBAC fields in `.env.example` with explanatory comments, in `Settings` field order. This is a pure configuration surface — no existing code path reads these fields yet; that is STORY-006, STORY-007, and STORY-011's job.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Verify baseline (branch, existing fields, 306 passing) | — | ✅ |
| 2 | Add `RBAC_ENABLED`, `RBAC_ROLES_FILE`, `MODEL_ALLOWLIST` + `model_allowlist_list` property | `app/config.py` | ✅ |
| 3 | Document the three new variables (plus pre-existing `RBAC_DEFAULT_ROLE`, not yet in this file) | `.env.example` | ✅ |
| 4 | Write `tests/test_config.py` — AC1–AC4 coverage | `tests/test_config.py` | ✅ |
| 5 | Full-suite regression and diff gate | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ |
| `tests/test_config.py` | ✅ (6 passed) |
| Full suite | ✅ (312 passed, up from 306) |
| E2E — boot with no `RBAC_*`/`MODEL_ALLOWLIST` env vars set | ✅ |
| E2E — `test_manage_users_cli.py` + `test_pii_redactor.py` unaffected | ✅ (18 passed) |
| Frontend lint | N/A — no npm frontend; UI is Reflex (Python) and untouched by this story |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/config.py` | UPDATE | +6/-1 |
| `.env.example` | UPDATE | +11 |
| `tests/test_config.py` | CREATE | +68 |
| `.agents/plans/PRD-005-rbac/completed/STORY-005-rbac-configuration-settings.plan.md` | CREATE (archived plan) | +393 |

## Deviations from Plan

None. Implementation matched the plan exactly, including the field ordering, property shape, `.env.example` comment format, and all six planned test cases.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_config.py` | `test_rbac_settings_available_with_documented_defaults`, `test_model_allowlist_list_parses_like_pii_entities_list`, `test_model_allowlist_list_default_matches_prd_default_models`, `test_settings_construct_without_new_env_vars`, `test_env_example_documents_every_new_rbac_var_with_a_comment`, `test_env_example_rbac_vars_appear_in_settings_field_order` |

## Acceptance Criteria

- [x] Given `.env`, when `Settings` loads, then `RBAC_ENABLED` (bool, default `true`), `RBAC_DEFAULT_ROLE` (str, default `user`), `RBAC_ROLES_FILE` (str, default empty), and `MODEL_ALLOWLIST` (CSV str) are all available
- [x] Given `MODEL_ALLOWLIST`, when read via a `model_allowlist_list` property, then it is parsed exactly the way `pii_entities_list` parses `PII_ENTITIES`
- [x] Given none of the new variables are set, when the app starts, then the documented defaults apply and nothing raises
- [x] Given `.env.example`, when read, then every new variable is present with an explanatory comment, matching `Settings` field for field
