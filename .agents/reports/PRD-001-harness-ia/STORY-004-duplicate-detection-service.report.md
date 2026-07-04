---
story: STORY-004
prd: PRD-001
plan: .agents/plans/PRD-001-harness-ia/completed/STORY-004-duplicate-detection-service.plan.md
epic_branch: epic/PRD-001-harness-ia
commit: f4b431f
status: COMPLETE
completed: 2026-07-04
---

# Implementation Report — STORY-004: Duplicate detection service (24h exact-match)

**Plan**: `.agents/plans/PRD-001-harness-ia/completed/STORY-004-duplicate-detection-service.plan.md`
**Epic Branch**: `epic/PRD-001-harness-ia`
**Commit**: `f4b431f`

## Summary

Implemented `app/services/duplicate_checker.py`, the first module in the new `app/services/` package. It SHA256-hashes the raw prompt (no normalization) and looks up a matching hash within the last 24 hours via a new repository function `find_duplicate_timestamp` added to `app/db/database.py`. Returns a `DuplicateCheckResult(is_duplicate, first_query_at)` using the earliest matching row in the window as `first_query_at`. Unexpected DB errors (e.g. a missing `audit_logs` table) are wrapped and re-raised as `DuplicateCheckError` so the checker fails loud rather than silently treating a broken DB as "no duplicates."

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Add `find_duplicate_timestamp` repository function | `app/db/database.py` | ✅ |
| 2 | Create `app/services/` package marker | `app/services/__init__.py` | ✅ |
| 3 | Create duplicate checker service | `app/services/duplicate_checker.py` | ✅ |
| 4 | Create unit tests | `tests/test_duplicate_checker.py` | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ |
| New unit tests | ✅ (8 passed) |
| Full test suite | ✅ (21 passed) |
| E2E (plan's 4 scenarios: 2h-old duplicate, 25h-old non-duplicate, whitespace-hash difference, malformed-DB error) | ✅ (4/4) |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/db/database.py` | UPDATE | +12 |
| `app/services/__init__.py` | CREATE | +0 |
| `app/services/duplicate_checker.py` | CREATE | +36 |
| `tests/test_duplicate_checker.py` | CREATE | +120 |

## Deviations from Plan

None. Implementation matched the plan exactly, including function names, dataclass shape, and the fixed `%Y-%m-%dT%H:%M:%SZ` timestamp convention.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_duplicate_checker.py` | `test_no_duplicate_when_no_matching_row`, `test_duplicate_detected_within_24h`, `test_not_duplicate_when_older_than_24h`, `test_boundary_just_inside_24h`, `test_boundary_just_outside_24h`, `test_whitespace_difference_produces_different_hash_and_not_flagged`, `test_earliest_entry_returned_as_first_query_at`, `test_malformed_db_raises_duplicate_check_error` |

## Acceptance Criteria

- [x] Given a prompt hashed with SHA256, when the identical hash exists in `audit_logs` with a `timestamp` within the last 24 hours, then the checker returns a blocked result with the `first_query_at` of the original entry.
- [x] Given a prompt hashed with SHA256, when no matching hash exists in the last 24 hours (including when it exists but is older than 24h), then the checker returns "not a duplicate."
- [x] Given two prompts that differ by even a single character/whitespace, when hashed, then they produce different hashes and are never flagged as duplicates.
- [x] Given the checker runs, when called with an empty or malformed DB, then it fails safely (raises `DuplicateCheckError`) rather than silently treating everything as non-duplicate.
