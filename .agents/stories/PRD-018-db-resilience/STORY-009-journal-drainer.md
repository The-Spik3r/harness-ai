---
id: STORY-009
prd: PRD-018
slug: journal-drainer
title: Journal drainer thread and lifespan wiring (FastAPI and Reflex)
type: technical
priority: high
complexity: medium
phase: "4 - Never lose a row"
status: done
labels: [backend, storage, chat-ui]
epic_branch: epic/PRD-018-db-resilience
plan: .agents/plans/PRD-018-db-resilience/completed/STORY-009-journal-drainer.plan.md
report: .agents/reports/PRD-018-db-resilience/STORY-009-journal-drainer.report.md
commit: null
depends_on: [STORY-005, STORY-008]
blocks: [STORY-010, STORY-011, STORY-012]
skills: []
created: 2026-11-17
updated: 2026-11-17
---

# STORY-009: Drain the journal exactly once

## Description

As a compliance admin, I want journaled rows drained into the database once it answers again, in order and exactly once, so that the audit trail has no hole and no duplicate after an outage.

## Acceptance Criteria

- [ ] Given a non-empty journal and a closed breaker, when the drainer runs, then it takes the oldest entry and runs one `_unit_of_work(IDEMPOTENT)` transaction: insert the audit row with `ON CONFLICT(write_id) DO NOTHING`, select its id by `write_id`, insert the decisions with that `audit_id` (`ON CONFLICT DO NOTHING`), commit, then advance the checkpoint and drop the row from the pending index. Decisions-only entries (`audit: null`, `audit_id` known) insert the decisions alone.
- [ ] Given a crash between drain commit and checkpoint (simulated by raising after commit and reloading the journal), when the drainer runs again, then the replay is a no-op and `SELECT COUNT(*) FROM audit_logs WHERE write_id = ?` is 1, and the drained row keeps its original `timestamp`.
- [ ] Given the breaker open or a drain failure, when the drainer ticks, then it does nothing while open, a drain failure feeds the breaker like any other operation, and the entry stays first in line. It yields between entries (Risk 7).
- [ ] Given `app/main.py`'s lifespan and `chat_ui/chat_ui/chat_ui.py`'s lifespan task (the two places `pipeline_executor.shutdown` is registered, `pipeline_executor.py:13-19`), when the app starts after a successful `init_db()`, then the journal is opened (unwritable directory → startup error naming `AUDIT_BUFFER_DIR`), orphaned journals are adopted, and the daemon drainer thread starts. On shutdown it stops. Nothing starts at import: a non-`db` test never meets the thread.
- [ ] Given each drain and each adoption, when it happens, then one structured log line is written (`journal drained write_id=… user_id=…`), and when the journal is fully drained it is compacted to zero bytes.

## Technical Notes

- The drainer can live in `app/db/audit_journal.py` or beside it. It calls a new `database` function (e.g. `drain_journal_entry(entry)`) that runs through `_unit_of_work`, so the SQL stays in `database.py`.
- `audit_id` of the decisions is resolved from the audit row's `write_id`, never from a cached id: a decisions-with-row entry has `audit_id: null` in the journal.
- New writes keep going straight to the database once it answers; they do not queue behind the backlog (D11). Consequence (documented in STORY-014): a drained row's `id` is later than rows written after it. `/audit` orders by `timestamp`.
- Startup order in both lifespans: `init_db()` first (D17: boot needs the database), then the journal open, adopt and drain thread.
- Tests: `tests/test_db_resilience_drain.py` (`db` for the transaction; drainer loop with a fake clock/event where possible). Use `PYTHONUTF8=1`. The kill-and-restart scenario can be a subprocess test or a simulated crash; choose the cheaper one that is honest.

## Dependencies

- **Blocked by**: STORY-005, STORY-008
- **Blocks**: STORY-010, STORY-011, STORY-012

## PRD Reference

Source: [`PRD-018-db-resilience/PRD.md`](../../PRDs/PRD-018-db-resilience/PRD.md) — sections 6.1, 6.8 (Drain), 11 (MVP: in-flight request across an outage), 12 (Phase 4), 14 (Risk 7), 15 (D11, D17)
