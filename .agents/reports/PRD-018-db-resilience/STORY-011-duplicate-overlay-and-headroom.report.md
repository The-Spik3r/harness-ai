---
story: STORY-011
prd: PRD-018
plan: .agents/plans/PRD-018-db-resilience/completed/STORY-011-duplicate-overlay-and-headroom.plan.md
epic_branch: epic/PRD-018-db-resilience
commit: pending
status: COMPLETE
completed: 2026-11-17
---

# Implementation Report - STORY-011: Duplicate overlay and admission headroom

## Summary

Added the duplicate overlay (`audit_journal.pending_duplicate`, predicate `_is_prior_query`) consulted by `check_duplicate`, and the admission headroom check (`audit_journal.check_admission_headroom`, `AuditHeadroomError(AuditUnavailableError)`) at step 1c of `run_conversation`. The three STORY-010 ingress arms map the headroom refusal to 503 with the existing "not sent" copy.

Orchestrator rulings applied: R1 overlay read before the DB lookup, used only after a successful lookup that found nothing (PRD D12 amended); R2 subclass; R3 `Retry-After: 1`; R4 step 1c before step 2; R5 `_is_prior_query` in audit_journal with cross-reference comments.

## Files Changed

| File | Action |
|------|--------|
| `app/db/errors.py` | UPDATE: `AuditHeadroomError` |
| `app/db/audit_journal.py` | UPDATE: `_is_prior_query`, `pending_duplicate`, `check_admission_headroom`, docstring |
| `app/db/database.py` | UPDATE: cross-reference `#` comment only (no docstring, SQL untouched) |
| `app/services/duplicate_checker.py` | UPDATE: overlay (R1) |
| `app/services/query_pipeline.py` | UPDATE: step 1c |
| `app/routers/query.py`, `app/routers/v1.py`, `chat_ui/chat_ui/state.py` | UPDATE: pre-model copy for the subclass inside existing arms |
| `tests/test_db_resilience_overlay.py` | CREATE (11 tests, 2 `db`) |
| `tests/test_db_resilience_headroom.py` | CREATE (9 tests) |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| Targeted tests (overlay, headroom, audit_journal, duplicate_checker, release, drain, chat_ui storage failures + startup guard, pii_dedup_isolation, messages, untouched_app, pii_redaction_integration, ingress) | 385 passed, 1 skipped |
| tests/test_db.py -k "find_duplicate_timestamp or dedup_lookup_shape or mark_audit_log_failed" | 4 passed |
| Full suite | GitHub CI on push (user decision) |

## Deviations from Plan

- Headroom test 8.7 asserts `state.messages[-1]` (the user bubble precedes the error bubble).
- The overlay test for the pipeline path pins the cutoff via a wrapper on `pending_duplicate` for non-pipeline tests only.
- Plan's `/query` foreign-session refusal remark (out of scope) unchanged.

## Acceptance Criteria

- [x] AC 1: `test_check_duplicate_holds_a_journaled_row_when_the_lookup_found_nothing`, `test_the_pipeline_blocks_a_resend_held_only_by_the_journal`
- [x] AC 2: `test_a_failed_lookup_still_fails_closed_...`, `test_the_database_answer_wins_...`, `test_a_row_drained_between_...` (R1 race)
- [x] AC 3: `test_overlay_and_sql_agree_on_every_excluded_row_shape` (SQL clause list, AST operand count, field sweep), `test_both_predicates_carry_a_cross_reference`
- [x] AC 4: headroom tests (pipeline, `/query`, `/v1` json/stream/tools, chat UI)
- [x] AC 5: `test_mark_drained_removes_the_row_from_the_overlay`, `test_a_drained_entry_leaves_the_overlay_and_the_database_holds_the_resend`
