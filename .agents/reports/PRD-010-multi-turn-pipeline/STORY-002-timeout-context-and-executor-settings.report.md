---
story: STORY-002
prd: PRD-010
plan: .agents/plans/PRD-010-multi-turn-pipeline/completed/STORY-002-timeout-context-and-executor-settings.plan.md
epic_branch: epic/PRD-010-multi-turn-pipeline
commit: 6c7048e
status: COMPLETE
completed: 2026-09-17
---

# Implementation Report — STORY-002: Settings: upstream timeout, context limits and pipeline executor size

**Plan**: `.agents/plans/PRD-010-multi-turn-pipeline/completed/STORY-002-timeout-context-and-executor-settings.plan.md`
**Epic Branch**: `epic/PRD-010-multi-turn-pipeline`
**Commit**: `6c7048e`

## Summary

Added four new `Settings` fields to `app/config.py` — `OPENROUTER_TIMEOUT_SECONDS: float = 120.0`, `CONTEXT_MAX_MESSAGES: int = 100`, `CONTEXT_MAX_CHARACTERS: int = 200_000`, `PIPELINE_MAX_WORKERS: int = 32` — grouped under a `# Multi-turn pipeline (PRD-010)` comment, with each field's own comment naming the story that will consume it (STORY-005, STORY-008, STORY-006). Two startup validators enforce safe values in the `_validate_chat_session_limit` style: one for the timeout (`> 0`) and one shared `field_validator` over the three integer fields (`≥ 1`), keyed by `info.field_name` against a module-level description map so the message names what each setting controls. `tests/test_config.py` gained a defaults test and parametrized invalid-value tests for all four settings. No production code reads these settings yet, and `.env.example` was left untouched, as the story specifies (STORY-018's scope).

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Add the four settings fields, grouped and commented | `app/config.py` | ✅ |
| 2 | Add startup validators for the four new fields | `app/config.py` | ✅ |
| 3 | Tests — defaults and parametrized invalid values | `tests/test_config.py` | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| `python -c "from app.config import Settings; Settings(..., OPENROUTER_TIMEOUT_SECONDS=0)"` raises `ValidationError` naming the setting | ✅ |
| `pytest tests/test_config.py -v` | ✅ 52 passed |
| Full suite `pytest tests/` (containerized, Python 3.11) | ✅ 2015 passed, 41 skipped, 0 failed |

The local machine's Python (3.14) has no prebuilt wheel for the pinned `libsql==0.1.11`, so the suite was run the way the README documents for exactly this situation: build the project's Docker image (`python:3.11`) and run `docker-compose run --rm -e HARNESS_TEST_LIBSQL_URL=... -e DATABASE_URL=... -e TURSO_AUTH_TOKEN= harness-ai pytest tests/ ...` against a local libSQL dev server container (`ghcr.io/tursodatabase/libsql-server`), started per `tests/conftest.py`'s own instructions.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/config.py` | UPDATE | +33 |
| `tests/test_config.py` | UPDATE | +79 |

## Deviations from Plan

None. Implementation matched the plan's tasks exactly, including the module-level `_PIPELINE_LIMIT_DESCRIPTIONS` constant and the shared `field_validator` signature using `info.field_name`.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_config.py` | `test_multiturn_pipeline_settings_available_with_documented_defaults`, `test_openrouter_timeout_seconds_at_or_below_zero_is_a_startup_error` (parametrized: `0, 0.0, -1, "0"`), `test_a_pipeline_size_setting_below_one_is_a_startup_error` (parametrized over all three integer fields × `0, -1, "0"`), `test_pipeline_size_settings_accept_the_boundary_value_of_one`, `test_settings_construct_without_the_multiturn_pipeline_vars` |

## Acceptance Criteria

- [x] Given `app/config.py`, when `Settings` is read, then it has `OPENROUTER_TIMEOUT_SECONDS: float = 120.0`, `CONTEXT_MAX_MESSAGES: int = 100`, `CONTEXT_MAX_CHARACTERS: int = 200_000` and `PIPELINE_MAX_WORKERS: int = 32`, grouped under a `# Multi-turn pipeline (PRD-010)` comment.
- [x] Given `OPENROUTER_TIMEOUT_SECONDS=0` or a negative value, when `Settings()` is constructed, then it raises a validation error naming the setting, the value received, and that it is the upstream request timeout in seconds.
- [x] Given `CONTEXT_MAX_MESSAGES=0`, `CONTEXT_MAX_CHARACTERS=0` or `PIPELINE_MAX_WORKERS=0` (and negatives), when `Settings()` is constructed, then each raises a validation error naming the setting and what it controls, in the `_validate_chat_session_limit` style. Parametrized tests in `tests/test_config.py` cover each.
- [x] Given no environment overrides, when `Settings()` is constructed, then the four defaults above hold (test).
- [x] Given the full test suite, when this story lands, then it is green. No code reads the new settings yet, and each field's comment names the story that consumes it (STORY-005, STORY-006, STORY-008).
