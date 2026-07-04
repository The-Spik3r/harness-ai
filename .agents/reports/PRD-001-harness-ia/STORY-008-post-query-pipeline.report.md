---
story: STORY-008
prd: PRD-001
plan: .agents/plans/PRD-001-harness-ia/completed/STORY-008-post-query-pipeline.plan.md
epic_branch: epic/PRD-001-harness-ia
commit: 8da10c0
status: COMPLETE
completed: 2026-07-04
---

# Implementation Report — STORY-008: POST /query endpoint — full interception pipeline

**Plan**: `.agents/plans/PRD-001-harness-ia/completed/STORY-008-post-query-pipeline.plan.md`
**Epic Branch**: `epic/PRD-001-harness-ia`
**Commit**: `8da10c0`

## Summary

Added `app/routers/query.py`, the first router in the codebase, implementing `POST /query`. It composes the four already-built services (STORY-004–007) in the exact 8-step order from PRD Section 6: reject empty/missing `user_id` → `check_duplicate` (hash + 24h lookup) → `detect_suspicious_pattern` → `call_openrouter` → `log_query` → respond. Wired into `app/main.py` via `include_router`. Blocked outcomes (duplicate/suspicious) return HTTP 200 with the documented `BLOCKED` body; OpenRouter failures are logged with `success=False`/`error_message` and surfaced as 502; duplicate-check DB failures propagate as an unhandled 500.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Create routers package marker | `app/routers/__init__.py` | ✅ |
| 2 | Implement pipeline route handler | `app/routers/query.py` | ✅ |
| 3 | Register router in the app | `app/main.py` | ✅ |
| 4 | Write pipeline test suite | `tests/test_query_router.py` | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`app.routers.query`) | ✅ |
| Backend import (`app.main`) + route list includes `/query` | ✅ |
| `GET /health` via TestClient | ✅ 200 `{"status": "ok"}` |
| Tests | ✅ 52 passed (7 new + 45 existing) |
| E2E | ✅ 7/7 (see below) |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/routers/__init__.py` | CREATE | +0 |
| `app/routers/query.py` | CREATE | +81 |
| `app/main.py` | UPDATE | +2/-2 |
| `tests/test_query_router.py` | CREATE | +178 |

## Deviations from Plan

None. Implementation matches the plan's Task 2 code block, Task 3 `main.py` diff, and Task 4 test list exactly (same 7 test names/behaviors).

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_query_router.py` | `test_missing_user_id_returns_422`, `test_empty_user_id_returns_400_before_any_side_effect`, `test_clean_prompt_success_returns_expected_shape_and_logs_row`, `test_duplicate_prompt_blocked_before_openrouter_call`, `test_suspicious_pattern_blocked_before_openrouter_call`, `test_openrouter_failure_logged_with_error_and_returns_502`, `test_full_pipeline_latency_within_budget` |

## Acceptance Criteria

- [x] Given a request missing `user_id`, when posted to `/query`, then it is rejected before any hashing/forwarding occurs (RF-14). — covered by `test_missing_user_id_returns_422` (422, 0 rows) and `test_empty_user_id_returns_400_before_any_side_effect` (400, 0 rows, OpenRouter never called).
- [x] Given a novel, clean prompt, when posted to `/query`, then the pipeline runs in order and returns the `SUCCESS` shape from PRD Section 10. — `test_clean_prompt_success_returns_expected_shape_and_logs_row`.
- [x] Given a prompt identical to one submitted within the last 24h, then OpenRouter is never called and the `BLOCKED` duplicate shape is returned. — `test_duplicate_prompt_blocked_before_openrouter_call`.
- [x] Given a prompt containing a suspicious pattern, then OpenRouter is never called and the `BLOCKED` suspicious-pattern shape is returned. — `test_suspicious_pattern_blocked_before_openrouter_call`.
- [x] Given any outcome (success or blocked), exactly one audit row is written. — verified in all four outcome tests via row-count assertions, plus the OpenRouter-failure case.
- [x] Given the full pipeline runs end-to-end, added latency (excluding upstream call) stays within the <500ms budget. — `test_full_pipeline_latency_within_budget` (stubbed OpenRouter call, asserts `< 0.5s`).
