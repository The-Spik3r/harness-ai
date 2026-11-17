---
story: STORY-009
prd: PRD-018
plan: .agents/plans/PRD-018-db-resilience/completed/STORY-009-journal-drainer.plan.md
epic_branch: epic/PRD-018-db-resilience
commit: pending
status: COMPLETE
completed: 2026-11-17
---

# Implementation Report - STORY-009: Journal drainer thread and lifespan wiring

## Summary

`database.drain_journal_entry(audit, decisions, *, audit_id=None)` runs one keyed `IDEMPOTENT` unit per journal entry (audit row by `write_id`, decisions rebuilt with the resolved audit id, original timestamp kept). New `app/db/journal_drainer.py` holds `drain_once` (closed `DrainOutcome` vocabulary), the loop `_run`, and reference-counted `start`/`stop`, `running`, `held_back`. Both lifespans (`app/main.py`, `chat_ui/chat_ui/chat_ui.py`) start it after `init_db()` and stop it after the pipeline executor. conftest isolates `AUDIT_BUFFER_DIR` per test and fails any leak of a journal or drainer thread.

Orchestrator rulings (also in the module docstring):
1. D-2: with a non-empty journal and a breaker that is not closed, the drainer calls `before()` itself, so an idle instance recovers through the breaker's single probe.
2. D-3: `StorageUnavailableError` stops the pass with the entry kept first; any other exception holds the entry back for the process lifetime (`held_back()`, one ERROR with the class name only; never deleted or marked drained).
3. D-4: reference-counted start/stop.
4. Stalled shutdown: 5 s join, WARNING, then close.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | `drain_journal_entry` | `app/db/database.py` | done |
| 2 | Kind table 41 -> 42 | `tests/test_db_resilience_retry.py` | done |
| 3 | Drainer module | `app/db/journal_drainer.py` | done |
| 4 | FastAPI lifespan | `app/main.py` | done |
| 5 | Reflex lifespan task | `chat_ui/chat_ui/chat_ui.py` | done |
| 6 | Isolation + leak guard | `tests/conftest.py` | done |
| 7 | 21 tests | `tests/test_db_resilience_drain.py` | done |
| 8 | Chat UI probe | `tests/test_chat_ui_startup_guard.py` | done |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| Tests (one pytest process: drain, retry, audit_journal, main, chat_ui_startup_guard, pattern_default_config_regression, conftest_fixtures, db_resilience_faults, untouched_app, measure_v1_latency) | 328 passed, 1 skipped |
| New file alone | 21 passed |
| Full suite | GitHub CI on push (user decision) |

## Deviations from Plan

None of substance. Added `tests/test_measure_v1_latency.py` to the targeted run (it enters the lifespan). The plan's conftest "second check" for non-db tests was folded into the leak branch.

## Tests Written

`tests/test_db_resilience_drain.py`: empty journal, FIFO + compaction + log lines, decisions-only, breaker window running, elapsed window probe, failed probe, unavailable, held back (no driver text in logs), loop yield/idle waits, loop survives a crash, no start at import (subprocess), drain rows + original timestamp, decisions-only db, replay no-op, crash between commit and checkpoint, failure feeds breaker, statement failure does not feed breaker and rolls back, lifespan adopts and drains, unwritable dir names AUDIT_BUFFER_DIR, two starts share one thread, init_db/journal/executor order. Also the chat UI probe test and the kind-table entry.

## Acceptance Criteria

- [x] Drain transaction per entry (tests #2, db drain tests)
- [x] Crash between commit and checkpoint is a no-op, timestamp kept
- [x] Breaker open / failure feeds breaker / entry stays first / yields
- [x] Lifespans open, adopt, start, stop; nothing at import
- [x] Structured log line per drain; compaction to zero bytes
