---
story: STORY-012
prd: PRD-001
plan: .agents/plans/PRD-001-harness-ia/completed/STORY-012-integration-test-suite.plan.md
epic_branch: epic/PRD-001-harness-ia
commit: 44266dc
status: COMPLETE
completed: 2026-07-04
---

# Implementation Report — STORY-012: End-to-end integration test suite

**Plan**: `.agents/plans/PRD-001-harness-ia/completed/STORY-012-integration-test-suite.plan.md`
**Epic Branch**: `epic/PRD-001-harness-ia`
**Commit**: `44266dc`

## Summary

Added `tests/test_integration.py`, a cross-cutting end-to-end suite that drives the full `/query` → `/audit` → `/stats` surface through the real `TestClient`, mapped explicitly to PRD Section 5's three flows. No application source code was changed — this was a test-only story. The suite closes two coverage gaps the existing per-router test files left open: only one of the seven suspicious patterns was previously exercised through the live `/query` endpoint, and `/audit`/`/stats` were only ever verified against rows seeded directly into SQLite, never against rows produced by a real `/query` call.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Bootstrap, fixtures, helpers (`temp_db`, `_count_audit_rows`, `_fail_if_called`, `_fake_call_openrouter`) | `tests/test_integration.py` | ✅ |
| 2 | Happy-path test (PRD 5.1) | `tests/test_integration.py` | ✅ |
| 3 | Duplicate-blocked test (PRD 5.2) | `tests/test_integration.py` | ✅ |
| 4 | Suspicious-pattern test parametrized over all 7 `SUSPICIOUS_PATTERNS` (PRD 5.3) | `tests/test_integration.py` | ✅ |
| 5 | Combined `/audit` + `/stats` admin-auth coverage (missing/wrong/valid token) | `tests/test_integration.py` | ✅ |
| 6 | Cross-endpoint consistency check (real `/query` results reflected in `/audit` and `/stats`) | `tests/test_integration.py` | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`python -c "from app.main import app"`) | ✅ |
| New module imports (`python -c "import tests.test_integration"`) | ✅ |
| `pytest tests/test_integration.py -v` | ✅ (14 passed) |
| Full suite `pytest tests/ -v` | ✅ (97 passed — 83 baseline + 14 new, no regressions) |
| E2E checklist (plan's "End-to-End Tests" section) | ✅ (5/5) |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `tests/test_integration.py` | CREATE | +160 |

## Deviations from Plan

None. Implementation matches the plan exactly — all 6 tasks implemented as specified, no application source files touched.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_integration.py` | `test_happy_path_returns_success_and_logs_exactly_one_row`, `test_duplicate_query_blocked_and_openrouter_never_called`, `test_each_suspicious_pattern_blocked_and_openrouter_never_called` (×7, parametrized), `test_admin_route_rejects_missing_or_invalid_token` (×2, parametrized), `test_admin_route_accepts_valid_token` (×2, parametrized), `test_query_results_are_consistent_across_audit_and_stats` — 14 test cases total |

## Acceptance Criteria

- [x] Given the happy-path flow from PRD Section 5.1, when run as a test, then it asserts a `SUCCESS` response and exactly one new `audit_logs` row.
- [x] Given the duplicate-blocked flow from PRD Section 5.2, when run as a test, then it asserts OpenRouter is never called (mocked) and the `BLOCKED` duplicate shape is returned.
- [x] Given the suspicious-pattern flow from PRD Section 5.3, when run as a test, then it asserts OpenRouter is never called and the `BLOCKED` suspicious shape is returned, for each of the 7 patterns.
- [x] Given `/audit` and `/stats`, when tested with and without a valid admin token, then both the authorized and unauthorized paths are covered.
- [x] Given the full suite, when run in CI, then it passes without requiring a real OpenRouter API key (the client is mocked/stubbed).
