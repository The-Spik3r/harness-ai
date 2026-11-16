---
story: STORY-010
prd: PRD-017
plan: .agents/plans/PRD-017-tool-calling/completed/STORY-010-step-7c-action-evaluation.plan.md
epic_branch: epic/PRD-017-tool-calling
commit: pending
status: COMPLETE
completed: 2026-11-16
---

# Implementation Report - STORY-010: Step 7c, action evaluation and the decision audit

**Plan**: `.agents/plans/PRD-017-tool-calling/completed/STORY-010-step-7c-action-evaluation.plan.md`
**Epic Branch**: `epic/PRD-017-tool-calling`
**Commit**: `pending`

## Summary

`run_conversation` gains step 7c (after the 7b charge, before step 8): when the upstream returned calls, each `ToolCallSpec` becomes a `ToolCall` field for field, `action_policy.evaluate_all` decides them once, and `tool_release.apply_decisions` builds the `Release`. Denial notes are joined after output redaction (`content_with_notes`). The success row carries `has_tool_calls` per D19 (every pipeline row now does, via a required `_deny` keyword and the request half computed at step 1b). `action_audit.record(decisions, identity, audit_id=<row id>, session_id=...)` runs after the success row. A `StorageError` is logged (user and `audit_id` only), the row is marked `success=0 / error_message='action audit failed'` through the new `database.mark_audit_log_failed` (best effort, any failure is caught and logged at ERROR), and `ActionAuditError` is raised. `/v1` maps it to 500 `internal_error`, retryable, in both shapes. The Release and decisions ride on `QuerySuccessResponse` as a pydantic `PrivateAttr` (`tool_outcome` property), so `/query`'s body and OpenAPI are unchanged.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | `ToolOutcome(release, decisions)` | `app/services/tool_release.py` | done |
| 2 | Private `_tool_outcome` + `tool_outcome` property | `app/models/schemas.py` | done |
| 3 | `ActionAuditError`, `_has_tool_turns`, `has_tool_calls` on all rows, required `_deny` keyword | `app/services/query_pipeline.py` | done |
| 4 | Step 7c, notes join, `record()`, fail closed | `app/services/query_pipeline.py` | done |
| 4b | (orchestrator scope addition, D8) `mark_audit_log_failed` | `app/db/database.py`, `query_pipeline.py` | done |
| 5 | Router maps `ActionAuditError` | `app/routers/v1.py` | done |
| 6 | Docstrings of the engine and the audit | `app/services/action_policy.py`, `action_audit.py` | done |
| 7 | Interim T1 pins adjusted (named changes only) | `tests/test_v1_tools.py` | done |
| 8 | Pipeline tests | `tests/test_query_pipeline_tools.py` | done |
| 9 | Router tests | `tests/test_v1_tools.py` | done |
| 9b | `mark_audit_log_failed` unit tests | `tests/test_db.py` | done |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | OK |
| Targeted run (one call): `test_query_pipeline_tools`, `test_v1_tools`, `test_query_pipeline_audit_fields`, `test_query_outcomes_regression`, `test_schemas`, `test_tool_release`, `test_action_audit`, `test_db`, `test_v1_router`, `test_v1_errors`, `test_untouched_app` | 1273 passed, 0 failed, 0 skipped (23m41s) |
| E2E | automated: DROP TABLE through `/v1` (JSON and SSE), `record()` failure (JSON 500 and SSE error event), `/query` body and schema unchanged |
| Full suite | deferred to orchestrator (user decision) |

## Files Changed

| File | Action |
|------|--------|
| `app/services/query_pipeline.py` | UPDATE (step 7c, `ActionAuditError`, `_has_tool_turns`, `has_tool_calls` on all 11 `log_query` sites and `_deny`) |
| `app/services/tool_release.py` | UPDATE (`ToolOutcome`) |
| `app/models/schemas.py` | UPDATE (`PrivateAttr`, property) |
| `app/routers/v1.py` | UPDATE (`ActionAuditError` into `_PIPELINE_FAULTS` / `_fault_code`; docstrings) |
| `app/db/database.py` | UPDATE (`mark_audit_log_failed`) |
| `app/services/action_policy.py`, `app/services/action_audit.py` | UPDATE (docstrings only) |
| `tests/test_query_pipeline_tools.py`, `tests/test_v1_tools.py`, `tests/test_db.py` | UPDATE |
| `.agents/PRDs/PRD-017-tool-calling/PRD.md` | UPDATE (D8 amended by the orchestrator) |

## Deviations from Plan

- D8 scope addition by the orchestrator: `mark_audit_log_failed` (Risk 1 of the plan is closed, not just documented). Tests: record fails and update succeeds gives `success=0` and the same request is answered again (pipeline and router); both fail gives `ActionAuditError`, two ERROR lines, no decision rows.
- Plan Task 8.6 listed forbidden, duplicate, context-limit, flag, upstream-error and output-redaction-error arms: implemented as one parametrized test (first five) plus one for the output-redaction-error arm.
- The Task 7 interim pins changed exactly as named, plus an extra assertion in the dropped-call pins (one `deny` row; the streamed content equals the note).

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_query_pipeline_tools.py` | 7c order and field-for-field calls; outcome on the result; no calls means no 7c; record gets the row id and session; `has_tool_calls` success row (3) and every arm (5 + output-redaction error); `_deny` requires it; 11 `log_query` sites; `_has_tool_turns`; record failure (StorageError, IntegrityError); mark-failed retry not a duplicate; both fail still closed; output redaction content only; all denied; mixed/flag order |
| `tests/test_v1_tools.py` | allowed call decided not yet released (interim); DROP TABLE JSON/SSE; audit failure JSON 500 and SSE error event; retry after failure; `_fault_code`; router never reads `result.tool_calls`; `/query` body and schema ignore the outcome |
| `tests/test_db.py` | `mark_audit_log_failed` flips one row and frees the dedup window; unknown id no-op; typed `StorageError` |

## Acceptance Criteria

- [x] AC1: evaluate_all once after 7b, before step 8; Release and decisions on the result, `/query` unchanged (`test_7c_runs_after_the_charge_and_before_step_8`, `test_success_result_carries_the_outcome`, `test_query_body_and_schema_ignore_the_tool_outcome`)
- [x] AC2: `has_tool_calls` per D19; `record()` with the row id; no calls records nothing (`test_has_tool_calls_*`, `test_record_gets_the_success_rows_id_and_session`, `test_no_calls_means_no_7c`)
- [x] AC3: `StorageError` becomes `ActionAuditError`, ERROR log, 500 `internal_error` retryable, nothing released in both shapes (`test_record_storage_error_is_action_audit_error`, the two `test_action_audit_failure_*`, `test_fault_code_maps_action_audit_error`)
- [x] AC4: DROP TABLE via `/v1` leaves one `deny`/`sql.ddl` row with the request's `audit_id` (`test_drop_table_via_shell_is_denied_and_recorded_with_the_audit_id`, JSON and SSE)
- [x] AC5: only content redacted, notes after, released calls untouched (`test_output_redaction_covers_content_only_and_notes_follow`)
