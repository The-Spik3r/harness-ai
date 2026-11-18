---
story: STORY-002
prd: PRD-020
plan: .agents/plans/PRD-020-provider-registry/completed/STORY-002-providers-file-settings.plan.md
epic_branch: epic/PRD-020-provider-registry
commit: 6586c45
status: COMPLETE
completed: 2026-11-18
---

# Implementation Report - STORY-002: PROVIDERS_FILE setting and the conditional OPENROUTER_API_KEY requirement

## Summary

`app/config.py`: `PROVIDERS_FILE: str = ""`, `OPENROUTER_API_KEY` now defaults to `""`, and two model validators placed before `_validate_v1_tool_models` (key required without a file, PRD-020 D1; `V1_TOOL_MODELS` forbidden in file mode, D6). The file is never opened.

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| Tests (test_config, chat_ui_startup_guard, untouched_app, openrouter_client, prd020_legacy_fixtures) | 421 passed, 0 failed, 0 skipped |
| Full suite | GitHub CI on push (user decision) |

## Files Changed

`app/config.py`, `tests/test_config.py` (8 test functions, 10 cases), `tests/test_chat_ui_startup_guard.py` (one env line).

## Deviations from Plan

None. No pre-existing assertion changed. The optional subprocess E2E was inconclusive locally (a `.env` file supplies the key); the unit tests cover both modes.

## Acceptance Criteria

- [x] AC1 `test_no_file_and_no_key_is_a_startup_error_naming_the_key`, `..._empty_string_key_...`
- [x] AC2 `test_providers_file_set_and_no_key_constructs`
- [x] AC3 `test_providers_file_with_v1_tool_models_is_a_startup_error`, `..._blank_..._passes`
- [x] AC4 whole `tests/test_config.py` green unchanged
- [x] AC5 `test_providers_file_is_not_read_by_settings`
