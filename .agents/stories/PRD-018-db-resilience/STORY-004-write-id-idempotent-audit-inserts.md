---
id: STORY-004
prd: PRD-018
slug: write-id-idempotent-audit-inserts
title: write_id columns, unique indexes, idempotent insert_audit_log and insert_action_decisions
type: technical
priority: high
complexity: medium
phase: "2 - Retry safely"
status: done
labels: [backend, storage, schema]
epic_branch: epic/PRD-018-db-resilience
plan: .agents/plans/PRD-018-db-resilience/completed/STORY-004-write-id-idempotent-audit-inserts.plan.md
report: .agents/reports/PRD-018-db-resilience/STORY-004-write-id-idempotent-audit-inserts.report.md
commit: 6c5ee59
depends_on: [STORY-003]
blocks: [STORY-008, STORY-010]
skills: []
created: 2026-11-17
updated: 2026-11-17
---

# STORY-004: Idempotent audit writes by write_id

## Description

As a compliance admin, I want every audit row and action decision to carry a client-minted `write_id` with a unique index, so that a retried or drained write lands exactly once even when the first attempt did commit.

## Acceptance Criteria

- [ ] Given an existing database, when `init_db()` runs, then `audit_logs.write_id TEXT` and `action_decisions.write_id TEXT` exist (nullable, no default, no backfill) through `_add_missing_columns()`, with `idx_audit_logs_write_id` and `idx_action_decisions_write_id` `UNIQUE` indexes. `action_decisions` becomes the fourth table on the added-columns path. Pre-PRD rows read `NULL`, and two `NULL` rows coexist. Re-running `init_db()` is a no-op.
- [ ] Given `AuditLog` and `ActionDecisionRow`, when constructed positionally as today, then they still work: each gains a trailing defaulted `write_id: Optional[str] = None`.
- [ ] Given `insert_audit_log(entry)` with a `write_id`, when it runs twice with the same entry (or a `_FaultyClient` raises `OUTCOME_UNKNOWN` **after** forwarding the first `INSERT`), then exactly one row exists (`SELECT COUNT(*) ... WHERE write_id = ?` is 1) and both calls return that row's `id`, read back with `SELECT id ... WHERE write_id = ?` in the same transaction (`ON CONFLICT(write_id) DO NOTHING`, no `RETURNING`).
- [ ] Given `insert_action_decisions(rows)` whose rows carry `write_id = "<batch uuid>:<index>"`, when a `DEAD_STREAM` hits row *k* of the batch, then the whole block is replayed from row 1 and exactly N rows exist afterwards, with ids returned in input order. `ON CONFLICT ... DO NOTHING` on this driver is verified by a `db` test (PRD Section 6.4 assumption).
- [ ] Given `log_query` and `action_audit.record`, when they build entries, then `log_query` mints `write_id = uuid4().hex` (or `str(uuid4())`, one convention for the whole PRD) alongside the single `timestamp` stamp, and `record()` mints one batch uuid per call. `log_query` still returns `int` in this story (STORY-010 changes it). An `insert_audit_log` / `insert_action_decisions` call whose rows lack a `write_id` (tests, scripts) keeps today's plain insert and runs as `NON_IDEMPOTENT` (no retry after `OUTCOME_UNKNOWN`), and a test pins that.

## Technical Notes

- `app/db/models.py`: `AUDIT_LOGS_ADDED_COLUMNS` gains `"write_id": "TEXT"`. New `ACTION_DECISIONS_ADDED_COLUMNS`. Index DDL constants beside `CREATE_AUDIT_LOGS_DEDUP_INDEX`.
- `app/db/database.py` `init_db()` (`:645-745`): the index goes on the line after `_add_missing_columns(conn, "audit_logs", ...)`, for the reason given at `:673-679`. The `action_decisions` pass goes after `CREATE_ACTION_DECISIONS_TABLE`, for the reason at `:681-692`.
- Kind: after this story, `insert_audit_log` and `insert_action_decisions` are `IDEMPOTENT` **only when every row has a `write_id`**. Without one (legacy callers), a retry after `OUTCOME_UNKNOWN` would duplicate a row, so the kind is chosen per call from the entry (Orchestrator decision at story creation).
- `app/services/audit_logger.py:73-107` and `app/services/action_audit.py:174`.
- Check every test or guard that enumerates `AuditLog` / `ActionDecisionRow` fields or the `audit_logs` columns (schema census tests, `_row_to_audit_log`, `_row_to_action_decision_row`, `/audit` JSON shape). Decide whether `write_id` is exposed in `/audit` output. Default: not exposed in API responses in this story (STORY-010 exposes `audit_ref`). Register in a census with a comment citing PRD-018 D4.
- Tests: `tests/test_db_resilience_write_id.py` (`db`), plus the existing `tests/test_db.py` migration tests.
- Orchestrator decision (STORY-003 plan): STORY-003 registers `insert_audit_log` and `insert_action_decisions` as `NON_IDEMPOTENT` in its name → kind table and AST pin test. This story flips them to IDEMPOTENT-when-`write_id`-present, updating that table and pin test (`tests/test_db_resilience_retry.py`). The `_FaultyClient` harness is `tests/db_faults.py` plus the `faulty_db` fixture in `tests/conftest.py`.

## Dependencies

- **Blocked by**: STORY-003
- **Blocks**: STORY-008, STORY-010

## PRD Reference

Source: [`PRD-018-db-resilience/PRD.md`](../../PRDs/PRD-018-db-resilience/PRD.md) — sections 4 (Idempotent audit writes), 6.3 (#6, #8, #9), 6.4, 7 (F3), 15 (D4)
