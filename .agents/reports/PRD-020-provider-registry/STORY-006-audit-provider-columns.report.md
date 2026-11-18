---
story: STORY-006
prd: PRD-020
plan: .agents/plans/PRD-020-provider-registry/completed/STORY-006-audit-provider-columns.plan.md
epic_branch: epic/PRD-020-provider-registry
commit: 581f7af
status: COMPLETE
completed: 2026-11-18
---

# Implementation Report - STORY-006: Five provider columns on the audit table and log_query

**Plan**: `.agents/plans/PRD-020-provider-registry/completed/STORY-006-audit-provider-columns.plan.md`
**Epic Branch**: `epic/PRD-020-provider-registry`
**Commit**: `581f7af`

## Summary

`audit_logs` gains `provider`, `upstream_model`, `provider_trust` (TEXT, nullable) and `pii_input_relaxed`, `usage_estimated` (INTEGER NOT NULL DEFAULT 0), declared in both `CREATE_AUDIT_LOGS_TABLE` and `AUDIT_LOGS_ADDED_COLUMNS` after `write_id` (orchestrator note 1). They are carried through `AuditLog`, `insert_audit_log` (33 -> 38 columns), `_row_to_audit_log`, `_SUMMARY_SQL`, `log_query` (before `journal_decisions`), `AuditQueryEntry` and `GET /audit`. No caller passes them yet (STORY-007): every row stores NULL/NULL/NULL/0/0. No new `database.py` function, so the resilience census is untouched.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Schema constants + dataclass fields | `app/db/models.py` | done |
| 2 | INSERT, tuple, row mapper, summary JSON | `app/db/database.py` | done |
| 3 | `log_query` params | `app/services/audit_logger.py` | done |
| 4 | API model + projection | `app/models/schemas.py`, `app/routers/admin.py` | done |
| 5 | Tests + closed-set edits | `tests/test_db.py`, `test_audit_logger.py`, `test_audit_router.py`, `test_audit_characterization.py`, `test_db_resilience_write_id.py` | done |

## Validation Results

Full suite: GitHub CI on push (user decision). `from app.main import app` prints OK.

| Run | Files | Result |
|-----|-------|--------|
| 1 | test_audit_logger, test_audit_router, test_audit_characterization | 79 passed |
| 2 | test_db_resilience_retry (unmodified, census proof), test_db_resilience_write_id, test_untouched_app | 206 passed (after fixing two test_db_resilience_write_id assertions, below) |
| 3 | test_audit_stats_prd013, test_audit_journal | 49 passed, 1 skipped |
| 4 | test_db.py | 252 passed, 2 failed (two more closed-set assertions); after fixing them the 17 related tests re-run green (`-k "carries_the_prd013 or ignored_params_in_both or prd020 or prd015 or prd013_columns"`). test_db.py was not re-run in full after the 2-assertion fix (12 min). |

E2E (plan): GET /audit over `log_query`-written rows with and without the five (new test in test_audit_router.py, run 1); old-DB convergence, second `init_db()` a no-op (new test in test_db.py, run 4). Both covered by automated tests.

## Files Changed

| File | Action |
|------|--------|
| `app/db/models.py` | UPDATE |
| `app/db/database.py` | UPDATE |
| `app/services/audit_logger.py` | UPDATE |
| `app/models/schemas.py` | UPDATE |
| `app/routers/admin.py` | UPDATE |
| `tests/test_db.py` | UPDATE (new tests + closed-set edits) |
| `tests/test_audit_logger.py` | UPDATE |
| `tests/test_audit_router.py` | UPDATE |
| `tests/test_audit_characterization.py` | UPDATE |
| `tests/test_db_resilience_write_id.py` | UPDATE |

## Deviations from Plan

The plan listed five closed-set assertions; more existing assertions depended on the exact column tail, each edited with a PRD-020 STORY-006 (D13) comment and nothing weakened:
- `tests/test_db.py`: both migration ALTER lists (pre-PRD-013, pre-PRD-015) gain the five ALTERs; `len(columns) == 34` -> 39 (twice); `names[-11:]` -> `names[-16:]` in the PRD-013 construction test; `[-2]` -> `[-7]` for `ignored_params` in the PRD-015 both-places test.
- `tests/test_db_resilience_write_id.py`: the pre-PRD-018 fixture helper `_without_write_id` now strips everything from `write_id` to the table close (so the legacy table lacks the five too), the ALTER list expects the five, and `fields(AuditLog)[-2:]` became `[-7:]`.
- No fixtures under `tests/fixtures/prd020_legacy/` touched. `test_db_resilience_retry.py` unmodified and green.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_db.py` | both-places (parametrized x5), declared-last order, fresh-schema shape (x5), old-DB convergence, round trip on both read shapes incl. raw `_SUMMARY_SQL` and `summary_snapshot` |
| `tests/test_audit_logger.py` | supplied, omitted |
| `tests/test_audit_router.py` | `/audit` passthrough (set row + default row) |

## Acceptance Criteria

- [x] AC1 fresh DB + old-DB convergence (test_db.py new tests)
- [x] AC2 round trip with/without args (test_db.py, test_audit_logger.py)
- [x] AC3 summary keys, no KeyError (test_db.py round-trip test)
- [x] AC4 GET /audit passthrough (test_audit_router.py)
- [x] AC5 census unchanged (test_db_resilience_retry.py green, unmodified)
