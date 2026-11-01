---
story: STORY-003
prd: PRD-015
plan: .agents/plans/PRD-015-openai-compatible-endpoint/completed/STORY-003-v1-settings.plan.md
epic_branch: epic/PRD-015-openai-compatible-endpoint
commit: 566b071
status: COMPLETE
completed: 2026-10-22
---

# Implementation Report — STORY-003: V1_ENABLED and V1_SSE_KEEPALIVE_SECONDS settings with startup validators

**Plan**: `.agents/plans/PRD-015-openai-compatible-endpoint/completed/STORY-003-v1-settings.plan.md`
**Epic Branch**: `epic/PRD-015-openai-compatible-endpoint`
**Commit**: `566b071`

## Summary

This story adds the two `/v1` settings from PRD Section 9.3 to `Settings`. They sit after `BREAK_GLASS_INGRESSES` under a PRD-015 section comment:

- **`V1_ENABLED: bool = True`** — a plain pydantic bool, so the string `"false"` parses to `False`. No validator. STORY-009 mounts the `/v1` router from it.
- **`V1_SSE_KEEPALIVE_SECONDS: float = 10.0`** — validated by `_validate_v1_sse_keepalive_seconds`, which follows `_validate_openrouter_timeout_seconds`. The check is written as `not 0 < value <= 60`, so NaN and infinity are rejected as well. The startup error names the setting, the value received, the range (`> 0 and <= 60`), what the setting controls, and `Example: V1_SSE_KEEPALIVE_SECONDS=10`. STORY-013 reads it.

Nothing reads either field yet. No setting chooses the `/v1` profile. `.env.example` is left to STORY-019.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Add `V1_ENABLED` and `V1_SSE_KEEPALIVE_SECONDS` fields | `app/config.py` | ✅ |
| 2 | Add `_validate_v1_sse_keepalive_seconds` | `app/config.py` | ✅ |
| 3 | Add the PRD-015 STORY-003 test block | `tests/test_config.py` | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ |
| Frontend lint | N/A (no frontend in this repo) |
| `tests/test_config.py` | ✅ 199 passed (185 existing, unchanged, plus 14 new) |
| `pytest -m "not db"` | ✅ 2,681 passed, 26 skipped |
| Full suite | ✅ 3,959 passed, 27 skipped, 1 failed, then passed on rerun (see below) |
| E2E | ✅ 4/4 |

The full-suite failure was `tests/test_query_pipeline_usage_limits.py::test_a_later_request_sees_tokens_today_increased_by_the_charge`. A commit hung for 15 s and ended in `STREAM_EXPIRED`, and the diagnostic printed `libsql verdict: likely infrastructure`. That is the known shared-DB flake. Rerunning the file gave 37/37 passed. The test reads none of the new settings.

### E2E

| Check | Result |
|-------|--------|
| `V1_SSE_KEEPALIVE_SECONDS=0 python -c "import app.config"` | ✅ exit 1, `V1_SSE_KEEPALIVE_SECONDS must be > 0 and <= 60, got 0.0. ... Example: V1_SSE_KEEPALIVE_SECONDS=10.` |
| `V1_SSE_KEEPALIVE_SECONDS=0.5` → `settings.V1_SSE_KEEPALIVE_SECONDS` | ✅ `0.5` |
| `V1_ENABLED=false` → `settings.V1_ENABLED` | ✅ `False` |
| `uvicorn app.main:app` with nothing set, then `GET /health` | ✅ `200 {"status":"ok"}` |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/config.py` | UPDATE | +30 |
| `tests/test_config.py` | UPDATE | +66 |

## Deviations from Plan

None.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_config.py` | `test_v1_settings_available_with_documented_defaults`; `test_v1_enabled_parses_the_string_false`; `test_v1_sse_keepalive_seconds_out_of_range_is_a_startup_error` ×7 (`0`, `-1`, `61`, `"0"`, `60.01`, `"nan"`, `"inf"`); `test_v1_sse_keepalive_seconds_accepts_the_range_bounds` ×3 (`0.5`, `60`, `"60"`); `test_no_setting_chooses_the_v1_profile` |

## Acceptance Criteria

- [x] Given nothing configured, when settings load, then `V1_ENABLED is True` and `V1_SSE_KEEPALIVE_SECONDS == 10`.
- [x] Given `V1_SSE_KEEPALIVE_SECONDS` of `0`, `-1` or `61`, when settings load, then startup fails with a message naming the setting, the value, the accepted range (`> 0` and `<= 60`) and an example; `0.5` and `60` are accepted.
- [x] Given `V1_ENABLED=false`, when settings load, then it parses as `False` (the router mount that reads it is STORY-009).
- [x] Given the existing config tests, when they run, then none changes.
