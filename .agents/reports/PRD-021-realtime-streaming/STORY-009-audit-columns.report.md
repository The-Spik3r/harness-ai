---
story: STORY-009
prd: PRD-021
plan: .agents/plans/PRD-021-realtime-streaming/completed/STORY-009-audit-columns.plan.md
epic_branch: epic/PRD-021-realtime-streaming
commit: pending
status: COMPLETE
completed: 2026-11-18
---

# Implementation Report — STORY-009: Four audit columns for real-time delivery

**Plan**: `.agents/plans/PRD-021-realtime-streaming/completed/STORY-009-audit-columns.plan.md`
**Epic Branch**: `epic/PRD-021-realtime-streaming`
**Commit**: `pending`

## Summary

`streamed_realtime`, `reasoning_shown`, `stream_redaction_divergence` (INTEGER NOT NULL DEFAULT 0) and `completion_id` (TEXT NULL) are appended after PRD-020's five columns in the CREATE DDL, `AUDIT_LOGS_ADDED_COLUMNS`, `AuditLog`, the INSERT (38 -> 42 columns), `_row_to_audit_log` and the `_SUMMARY_SQL` json_object. `log_query` takes `streamed_realtime` and `reasoning_shown` as required keyword-only arguments and the other two with defaults. Every row-writing arm of `run_conversation` and the router's foreign-session refusal passes them. No new `database.py` public function and no new connection caller (census untouched). Orchestrator decision (3.2): refusal rows at steps 3-6 write `streamed_realtime=False`, `completion_id=None`; `realtime_request` is persisted only on the step 7 failure, step 8 failure and success rows. `completion_id` is stored only when `realtime_request`. `reasoning_shown` = a non-empty reasoning text reached the sink (new local `reasoning_sent`) or a whole redacted reasoning was returned. One INFO line at the realtime commit (user, model, id).

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Schema: DDL, added columns, `AuditLog` | `app/db/models.py` | done |
| 2 | INSERT, values, row mapper, summary json_object | `app/db/database.py` | done |
| 3 | `log_query` keywords | `app/services/audit_logger.py` | done |
| 4 | `_deny` params, 5 callers, 10 direct arms, `realtime_request` moved to step 2d, `reasoning_sent`, INFO line | `app/services/query_pipeline.py` | done |
| 5 | Router foreign-session refusal | `app/routers/query.py` | done |
| 6 | Field-order guards, ALTER lists, direct `log_query` callers, new tests | tests | done |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| Targeted run (16 files, one pytest call) | 835 passed, 5 failed (stale tail-slice / column-count guards in `tests/test_db.py`, fixed) |
| Re-run of the 5 fixed guards (`test_db.py -k "prd013 or prd015 or ignored_params or prd020 or prd021 or columns"`) | 74 passed, 0 failed |
| Full suite | GitHub CI on push (user decision) |

The 16 files were: test_db, test_audit_characterization, test_audit_logger, test_migrate_to_turso_cli, test_db_resilience_write_id, test_db_resilience_release, test_db_resilience_retry, test_audit_router, test_query_pipeline_audit_fields, test_query_pipeline_audit_realtime, test_query_pipeline_streaming, test_query_pipeline_gates, test_query_pipeline_dedup_key, test_query_pipeline_pii_profiles, test_pii_redaction_integration, test_untouched_app. Skipped: 0.

## Files Changed

`app/db/models.py`, `app/db/database.py`, `app/services/audit_logger.py`, `app/services/query_pipeline.py`, `app/routers/query.py` (UPDATE); `tests/test_db.py`, `tests/test_audit_characterization.py`, `tests/test_audit_logger.py`, `tests/test_audit_router.py`, `tests/test_migrate_to_turso_cli.py`, `tests/test_db_resilience_write_id.py`, `tests/test_db_resilience_release.py`, `tests/test_query_pipeline_audit_fields.py` (UPDATE); `tests/test_query_pipeline_audit_realtime.py` (CREATE, 19 tests).

## Deviations from Plan

- Refusal arms at steps 3-6 write `False`/NULL (orchestrator's correction), not `realtime_request`.
- `tests/test_db.py` had more tail-slice guards than the plan listed (PRD-013 and PRD-015 tests: `[-15:-7]`, `names[-16:]`, `[-7]`, the `== 39` column counts); updated with PRD-021 comments.
- Source scan test counts 12 `log_query` sites (11 pipeline + 1 router) as before; no new site.
- Test files that spy `log_query(**kwargs)` and forward to the real one needed no change.

## Tests Written

- `tests/test_query_pipeline_audit_realtime.py`: realtime success row and id, reasoning grants, buffered with a sink, `sink=None`, reasoning returned whole, no reasoning, divergence and clean run, fault after release, fault before reasoning release, fault before any event, gate fault, step 8 failure (buffered and realtime), authorization denial, step 3 refusal, INFO line (canary, none when buffered), failing sink still succeeds and charges.
- `tests/test_db.py`: `_PRD021_*` (both lists, shape, upgrade ALTERs, fresh DB without ALTER, round trip on both read shapes).
- `tests/test_audit_logger.py`: round trip, defaults, `TypeError` for each required keyword.
- `tests/test_query_pipeline_audit_fields.py`: `_deny` required params, source scan of both keywords.

## Acceptance Criteria

- [x] AC1 four columns in both lists after PRD-020's five, on `AuditLog`
- [x] AC2 upgrade ALTERs them, old rows 0/NULL, fresh DB no ALTER
- [x] AC3 `_SUMMARY_SQL` and `_row_to_audit_log` carry them, parameter tuple unchanged
- [x] AC4 required keywords on every arm, success row values
- [x] AC5 INFO line without content; a failing sink still writes success and charges
