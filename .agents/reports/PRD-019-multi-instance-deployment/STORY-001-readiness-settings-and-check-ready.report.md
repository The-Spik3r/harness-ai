---
story: STORY-001
prd: PRD-019
plan: .agents/plans/PRD-019-multi-instance-deployment/completed/STORY-001-readiness-settings-and-check-ready.plan.md
epic_branch: epic/PRD-019-multi-instance-deployment
commit: pending
status: COMPLETE
completed: 2026-11-17
---

# Implementation Report - STORY-001: Readiness settings and database.check_ready()

## Summary

`DRAIN_FILE` and `READY_DB_TIMEOUT_SECONDS` settings with validators, and a non-raising `database.check_ready() -> ReadyCheck`: breaker read in memory only, then one `SELECT 1` on a single-slot `ready-probe` executor under a deadline; a stuck probe is abandoned and blocks further submits. It never touches the breaker's mutating API.

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| Tests (test_db_check_ready, test_config, test_circuit_breaker, test_db_resilience_breaker, test_untouched_app) | 317 passed, 0 failed, 0 skipped |
| E2E (libSQL dev server happy path) | passed |
| Full suite | GitHub CI on push (user decision) |

## Files Changed

`app/config.py` (UPDATE), `app/db/database.py` (UPDATE), `tests/test_config.py` (UPDATE), `tests/test_db_resilience_breaker.py` (UPDATE), `tests/test_db_check_ready.py` (CREATE), story + index + plan/report.

## Deviations from Plan

- `tests/test_db_resilience_breaker.py::test_only_the_unit_of_work_consults_the_breaker` asserted the exact set of functions naming `_storage_breaker`; updated to include `check_ready` (comment cites PRD-019 D5). Not anticipated by the plan.
- Half-open test uses a probe-less breaker advanced with `before()` (a real half_open without a driver call) because `status()` alone never leaves `open`.
- Test stub exposes a `description` attribute so the real `_Cursor` wrapper works.
- Story AC1 is "absolute path, POSIX or Windows" (orchestrator decision), no longer a deviation.
- conftest's thread guards only track `audit-journal-drainer`; `ready-probe` is not flagged, and the tests reset the executor anyway.

## Tests Written

`tests/test_db_check_ready.py` (14 tests incl. one `db`), `tests/test_config.py` (PRD-019 STORY-001 section).

## Acceptance Criteria

- [x] AC1 settings + validators: test_config.py PRD-019 section
- [x] AC2 open/half_open -> breaker_open, retry >= 1, zero driver calls: three breaker tests
- [x] AC3 closed path, classification, never raises, no token in WARNING: closed/auth/never_raises/warning tests + libSQL test
- [x] AC4 stuck probe: deadline and second-call tests
- [x] AC5 breaker neutral: hundred-failures and open-with-success tests
