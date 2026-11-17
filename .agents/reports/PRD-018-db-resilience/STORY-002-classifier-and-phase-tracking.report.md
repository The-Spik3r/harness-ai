---
story: STORY-002
prd: PRD-018
plan: .agents/plans/PRD-018-db-resilience/completed/STORY-002-classifier-and-phase-tracking.plan.md
epic_branch: epic/PRD-018-db-resilience
commit: pending
status: COMPLETE
completed: 2026-11-17
---

# Implementation Report — STORY-002: _classify(exc, phase), FailureClass and per-call phase tracking

**Plan**: `.agents/plans/PRD-018-db-resilience/completed/STORY-002-classifier-and-phase-tracking.plan.md`
**Epic Branch**: `epic/PRD-018-db-resilience`
**Commit**: `pending`

## Summary

`app/db/database.py` gains the closed `FailureClass` enum, the seven-name `Phase` vocabulary, `_mark_phase` / `_phase_of`, `_CONNECT_FAILURE` and a pure `_classify(exc, phase)`, placed directly after `_translated()`. `_Connection`, `_Cursor` and `get_connection()` label a driver `ValueError` with the failing call's name (an attribute on the driver's own exception, bare `raise`) so the phase is reachable from the `StorageError` through `__cause__`. `_translated()` (code and docstring), `_is_dead_stream()`, `_DEAD_STREAM` and `app/db/errors.py` are untouched. Nothing calls `_classify` yet (STORY-003).

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Vocabulary and phase helpers | `app/db/database.py` | done |
| 2 | `_classify` and `_CONNECT_FAILURE` | `app/db/database.py` | done |
| 3 | Phase recording in `_Cursor`, `_Connection` (`__exit__` routed through `commit()`/`rollback()`), `get_connection()` | `app/db/database.py` | done |
| 4 | New non-`db` test module | `tests/test_db_resilience_classify.py` | done |
| 5 | Targeted regression run | n/a | done |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| Frontend lint | n/a (no frontend) |
| New test module | 118 passed |
| Targeted regression (one pytest process) | 214 passed, 0 failed, 0 skipped, 211 deselected |
| E2E checklist | import OK; STORY-024 subset, `test_init_db_fails_fast...`, `test_duplicate_check_storage_failure_returns_500`, isolation harness and `test_untouched_app` pass unchanged; diff has no hunk inside `_translated()`; `_classify(` has no caller in `app/`, `chat_ui/`, `scripts/` |
| Full suite | GitHub CI on push (user decision) |

## Files Changed

| File | Action |
|------|--------|
| `app/db/database.py` | UPDATE |
| `tests/test_db_resilience_classify.py` | CREATE |
| `.agents/plans/PRD-018-db-resilience/completed/STORY-002-...plan.md` | archived |
| story / index files | UPDATE |

## Deviations from Plan

None from the plan. Orchestrator-accepted deviations from the story text, as written in the plan:

1. Plain `error sending request` is NOT `NOT_SENT`; only `tcp connect error` / `client error (Connect)` are (reqwest's prefix also covers a reset after the request was written).
2. `fetchmany` is a seventh phase.
3. Generic `SQLite error:` / `SQLITE_BUSY` stays `OUTCOME_UNKNOWN` (not `STATEMENT`).

Open for STORY-003: classify `exc.__context__` too when the phase is `rollback` and take the more pessimistic class (a test pins `__context__`).

## Tests Written

`tests/test_db_resilience_classify.py` (non-`db`): fixture table (spike rows with V1 applied plus strings quoted in `database.py` and `tests/`, each as raw `ValueError` and `StorageError`), AC 2 unrecognised-text and commit-only dead-stream tests, AC 3 statement tests at every phase, vocabulary, purity, same-object phase tests at every driver call, `_translated()` no-second-execute plus companions, `_phase_of` / `_mark_phase`.

## Acceptance Criteria

- [x] Table test over every verbatim string -> `test_classify_fixture_table`
- [x] Unrecognised `Hrana:` -> `OUTCOME_UNKNOWN`; dead stream on `commit` -> `NOT_SENT` -> `test_an_unrecognised_hrana_text_is_never_not_sent`, `test_only_commit_turns_a_dead_stream_into_not_sent`, `test_every_other_commit_failure_stays_outcome_unknown`
- [x] `IntegrityError` / `MissingRelationError` / duplicate column -> `STATEMENT` -> `test_statement_failures_are_statement_at_every_phase`
- [x] Phase recorded, same object re-raised, `_translated()` no second `execute` -> wrapper tests and `test_translated_reraises_without_a_second_execute`
- [x] Existing storage tests pass unchanged -> targeted run, 214 passed
