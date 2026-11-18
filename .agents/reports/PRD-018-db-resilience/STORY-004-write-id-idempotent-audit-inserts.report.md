---
story: STORY-004
prd: PRD-018
plan: .agents/plans/PRD-018-db-resilience/completed/STORY-004-write-id-idempotent-audit-inserts.plan.md
epic_branch: epic/PRD-018-db-resilience
commit: 6c5ee59
status: COMPLETE
completed: 2026-11-17
---

# Implementation Report — STORY-004: write_id columns, unique indexes, idempotent audit inserts

**Plan**: `.agents/plans/PRD-018-db-resilience/completed/STORY-004-write-id-idempotent-audit-inserts.plan.md`
**Epic Branch**: `epic/PRD-018-db-resilience`
**Commit**: `6c5ee59`

## Summary

`audit_logs` and `action_decisions` gain a nullable `write_id TEXT` (no default, no backfill) with a UNIQUE index each, added through `_add_missing_columns()` (`action_decisions` is now the fourth table on that path). `AuditLog` and `ActionDecisionRow` gain `write_id: Optional[str] = None` before `id`. A keyed row is written with `INSERT ... ON CONFLICT(write_id) DO NOTHING RETURNING id`; only when `RETURNING` yields no row (a replay) does one `SELECT id ... WHERE write_id = ?` run on the same connection. `lastrowid` is never read on the keyed path. The statement kind is per call: `_keyed_kind([...])` is `IDEMPOTENT` only when every row has a key, else `NON_IDEMPOTENT`, and the AST pin accepts that exact expression for the two inserts only. `log_query` mints `uuid4().hex` through `audit_logger._new_write_id()` and still returns `int`; `record()` keys row *i* as `"<fresh batch hex>:<i>"`. `write_id` is mapped on both read shapes and exposed on no API response.

## Orchestrator decisions applied

1. **Healthy path adds no round trip (PRD Section 11).** Keyed path uses `RETURNING id` first and `SELECT id` only on a conflict, replacing the plan's "SELECT after every keyed insert". PRD 6.4's "SELECT rather than RETURNING" is cited and reversed in the docstrings of `_keyed_row_id`, `insert_audit_log` and `insert_action_decisions`. Verified on the live driver by `test_returning_with_do_nothing_on_this_driver` (first insert returns the id; the conflicting replay returns no row, in the same transaction and after commit; the SELECT fallback returns the original id) and by two round-trip tests that count the SELECTs.
2. **Open question 3:** STORY-010 keys decisions by the audit `write_id`; this story keeps `<fresh batch hex>:<i>`.
3. **Plan deviations 1 and 2 accepted:** `write_id` before `id` in both dataclasses; the unkeyed insert carries `write_id` NULL with no `ON CONFLICT`.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Schema constants, two UNIQUE indexes, `ACTION_DECISIONS_ADDED_COLUMNS`, dataclass fields | `app/db/models.py` | done |
| 2 | `init_db()` passes and indexes | `app/db/database.py` | done |
| 3 | `_keyed_kind`, `_keyed_row_id`, `_insert_audit_row`, `_insert_action_decision_rows`, both inserts | `app/db/database.py` | done |
| 4 | Both mappers and `_SUMMARY_SQL` key | `app/db/database.py` | done |
| 5 | `_new_write_id()`, `log_query` and `record()` minting | `app/services/audit_logger.py`, `app/services/action_audit.py` | done |
| 6 | Census re-registrations and the per-call kind pin | 6 existing test files | done |
| 7 | New db test module | `tests/test_db_resilience_write_id.py` | done |
| 8 | Targeted regression runs | n/a | done |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | OK |
| Frontend lint | n/a (no frontend) |
| `tests/test_db_resilience_write_id.py` + `tests/test_db_resilience_retry.py` | 197 passed |
| faults, action_audit, audit_logger, audit_characterization, history_off, migrate_to_turso_cli, admin_actions, untouched_app, pii_redaction_integration | 212 passed, 0 failed, 0 skipped |
| `tests/test_db.py -k "<plan subset>"` | 133 passed, 108 deselected |
| Full suite | GitHub CI on push (user decision) |
| E2E | index_list unique=1 on both tables, 32-hex `write_id` on a `log_query` row, `<hex>:0..N-1` on a `record()` batch: covered by db tests, all pass |

## Files Changed

| File | Action |
|------|--------|
| `app/db/models.py` | UPDATE |
| `app/db/database.py` | UPDATE (`_translated()` untouched; CRLF preserved) |
| `app/services/audit_logger.py` | UPDATE |
| `app/services/action_audit.py` | UPDATE |
| `tests/test_db_resilience_write_id.py` | CREATE (31 tests) |
| `tests/test_db_resilience_retry.py` | UPDATE (`_PER_CALL_KIND`, +6 tests) |
| `tests/test_db.py`, `tests/test_action_audit.py`, `tests/test_audit_characterization.py`, `tests/test_history_off_integration.py`, `tests/test_migrate_to_turso_cli.py` | UPDATE (census registrations, each commented PRD-018 STORY-004 D4) |
| `.agents/stories/PRD-018-db-resilience/STORY-010-...md` | orchestrator edit, committed unchanged |

## Deviations from Plan

- RETURNING-first instead of SELECT-always (orchestrator decision 1).
- Helper `_keyed_row_id(conn, table, cursor, write_id)` shared by both writers (the plan had the SELECT inline in each).
- `_ON_WRITE_ID_CONFLICT` now includes `RETURNING id`.
- Added tests beyond the plan: healthy path issues no SELECT, a replay issues exactly one, fail-closed when no row can be read back, both read shapes map `write_id`.
- No change to `scripts/migrate_to_turso.py`: it defaults a column absent from the source (write_id reads NULL on both sides).

## Acceptance Criteria

- [x] AC 1: schema and migration (`test_a_fresh_database_has_the_write_id_column_as_nullable_text`, `test_the_write_id_index_is_unique_on_the_one_column`, `test_init_db_migrates_a_pre_prd018_database`, ordering and NULL-coexistence tests)
- [x] AC 2: defaulted `write_id` (`test_existing_constructions_still_work_and_default_write_id_to_none`)
- [x] AC 3: keyed audit insert lands once with the same id (three AC 3 tests, incl. landed commit and lost execute answer)
- [x] AC 4: keyed batch replays from row 1; ON CONFLICT verified on the driver (`test_a_dead_stream_on_row_k_replays_the_keyed_batch_from_row_one`, landed-batch test, `test_returning_with_do_nothing_on_this_driver`)
- [x] AC 5: minting and unkeyed path (`test_log_query_mints_a_hex_write_id_and_still_returns_int`, `test_record_keys_its_rows_batch_colon_index`, two unkeyed refused-replay tests, per-call kind pin in `test_db_resilience_retry.py`)
