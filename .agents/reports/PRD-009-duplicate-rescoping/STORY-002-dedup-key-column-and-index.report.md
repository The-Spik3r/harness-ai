---
story: STORY-002
prd: PRD-009
plan: .agents/plans/PRD-009-duplicate-rescoping/completed/STORY-002-dedup-key-column-and-index.plan.md
epic_branch: epic/PRD-009-duplicate-rescoping
commit: c8b303b
status: COMPLETE
completed: 2026-09-16
---

# Implementation Report — STORY-002: audit_logs.dedup_key column and idx_audit_logs_dedup, converged by init_db() and round-tripped by AuditLog

**Plan**: `.agents/plans/PRD-009-duplicate-rescoping/completed/STORY-002-dedup-key-column-and-index.plan.md`
**Epic Branch**: `epic/PRD-009-duplicate-rescoping`
**Commit**: `c8b303b`

## Summary

`audit_logs` now has a nullable `dedup_key TEXT` column, declared in both `CREATE_AUDIT_LOGS_TABLE` and `AUDIT_LOGS_ADDED_COLUMNS`. It also has a non-unique index, `idx_audit_logs_dedup ON audit_logs(user_id, dedup_key, timestamp)`. `init_db()` creates that index on the line right after `_add_missing_columns(conn)`, inside the same `_session()` block. `AuditLog.dedup_key` is written by `insert_audit_log` and read back by `_row_to_audit_log` on both read paths: the `SELECT *` row, and the `json_object(...)` in `_SUMMARY_SQL`.

`_add_missing_columns` and `_is_duplicate_column` were not modified. New tests show they already handle the column on a pre-PRD database and under a forced race between two instances. Nothing writes a real key yet (STORY-006), and `AuditQueryEntry` has no new field (D5).

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Declare column (CREATE + ADDED_COLUMNS), index DDL, `AuditLog.dedup_key` | `app/db/models.py` | ✅ |
| 2 | Execute index after `_add_missing_columns` in the single bootstrap block; docstring | `app/db/database.py` | ✅ |
| 3 | `insert_audit_log` (20/20/20), `_row_to_audit_log`, `_SUMMARY_SQL` json_object | `app/db/database.py` | ✅ |
| 4 | Extend the three exact-set pins with PRD-009 citations | `tests/test_db.py`, `tests/test_migrate_to_turso_cli.py` | ✅ |
| 5 | Constant-level tests (column, index, dataclass) | `tests/test_db.py` | ✅ |
| 6 | Round trip on get / list / summary_snapshot | `tests/test_db.py` | ✅ |
| 7 | Built index + column order, nullable column, EXPLAIN plan | `tests/test_db.py` | ✅ |
| 8 | Pre-PRD-009 fixture, migration, ALTER-before-index ordering, no-ALTER tuple, PRD-008 docstring notes | `tests/test_db.py` | ✅ |
| 9 | Forced two-instance race on the `dedup_key` ALTER (3/3 runs green) | `tests/test_db.py` | ✅ |
| 10 | Untouched surfaces verified + boundary suites + full suite | none edited | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ |
| Frontend lint | N/A (no frontend change; repo has no linter) |
| Baseline before changes (`test_db.py` + `test_migrate_to_turso_cli.py`) | ✅ 173 passed |
| Same modules after changes | ✅ 185 passed |
| Boundary suites (`test_audit_router`, `test_stats_router`, `test_pii_redaction_integration`, `test_admin_models`, `test_history_off_integration`, `test_migrate_to_turso_cli`, `test_two_instance_smoke`) | ✅ 86 passed (with `PYTHONUTF8=1`, see Deviations) |
| Full suite (`PYTHONUTF8=1 pytest tests/ -q`) | ✅ 1873 passed, 25 skipped, 1 environment error (see Deviations); that file re-ran 17/17 green |
| Mutation check: index moved above `_add_missing_columns` | ✅ caught (3 new tests fail) |
| Mutation check: `dedup_key` dropped from `_SUMMARY_SQL` | ✅ caught (both batched-read tests fail) |
| Untouched-surface diff (`app/models/schemas.py`, `app/routers`, `app/services`, `scripts`, pinned router/integration suites) | ✅ empty |
| E2E | ✅ 8/8 |

### E2E checklist

- [x] `pytest tests/test_db.py -q` green, including every new `dedup` test
- [x] Fresh DB: `PRAGMA index_info(idx_audit_logs_dedup)` = `['user_id', 'dedup_key', 'timestamp']`; `dedup_key` TEXT, notnull 0, no default (standalone script)
- [x] Pre-PRD DB (20 columns, one row): column added, legacy row `dedup_key=None`, index present, new insert with `k2` round-trips (standalone script)
- [x] Steady state: second `init_db()` issued 0 `ALTER` (standalone script; also `test_init_db_issues_no_alter_when_schema_is_current`)
- [x] Race: two gated `init_db()` → no failures, one column, one index, 3/3 runs
- [x] `get_audit_log` → `k`; `list_audit_logs` and `summary_snapshot().rows` → `[None, 'k']`; `errors == {}` (standalone script)
- [x] `/audit` and `/stats` shape suites pass unmodified
- [x] Full suite green, apart from the single known libSQL flake, which passed on re-run

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/db/models.py` | UPDATE | +32/-4 |
| `app/db/database.py` | UPDATE | +16/-3 |
| `tests/test_db.py` | UPDATE | +357/-1 |
| `tests/test_migrate_to_turso_cli.py` | UPDATE | +2/-1 |
| `.agents/plans/PRD-009-duplicate-rescoping/completed/STORY-002-dedup-key-column-and-index.plan.md` | CREATE (archived) | +402 |

## Deviations from Plan

1. **The suite was run with `PYTHONUTF8=1`.** Without it, `tests/test_pii_redaction_integration.py::test_no_pre_epic_test_function_was_removed_or_renamed` fails on this Windows machine. The test calls `git show <epic base>:<path>`, and the subprocess decodes that output as cp1252, which raises `UnicodeDecodeError` on byte `0x9d`, so `_git()` returns `None`. The failure depends on the machine's locale, not on this change: the test reads the historic commit, not the working tree, and it passes under UTF-8 mode, which is what CI on Linux uses by default. I did not fix it here because it's outside this story's scope. It's worth a follow-up: pass `encoding="utf-8"` to `_git()`'s subprocess call.
2. **One fixture error in the full run.** `test_query_pipeline_session_passthrough.py::test_session_id_omitted_writes_null_on_every_arm[pattern-blocked]` errored in conftest's `_reset_database()` with Hrana `STREAM_EXPIRED`. That is the known libSQL dev-server visibility flake (one scattered failure, in a file this story doesn't touch). The file re-ran 17/17 green.
3. **Two extra mutation checks.** They weren't in the plan. I added them to show that the ordering test and the batched-read test really fail when the behavior they guard breaks.
4. **Header comment re-wrapped.** The history comment above `AUDIT_LOGS_ADDED_COLUMNS` in `models.py` was re-wrapped after the PRD-009 addition. Comment only.

Otherwise the implementation followed the plan, including the risk fallbacks, which weren't needed: `PRAGMA index_list`/`index_info` work over Hrana, and the planner picks `idx_audit_logs_dedup` without seeding.

Noted, not changed (out of scope, as in the plan): `scripts/migrate_to_turso.py::_audit_log_from_source` leaves both `session_id` and `dedup_key` out of its read-back `AuditLog`. Legacy SQLite sources never have either column, so both sides default to `None`.

`.env.example` needs no change for this story: it adds no setting.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_db.py` | `test_audit_logs_added_columns_carries_a_nullable_dedup_key`, `test_audit_logs_dedup_index_is_the_lookup_access_path`, `test_audit_log_carries_dedup_key_without_breaking_construction`, `test_dedup_key_defaults_to_none_when_not_supplied`, `test_dedup_key_round_trips`, `test_dedup_key_survives_the_batched_read`, `test_init_db_creates_the_dedup_index_with_its_columns_in_order`, `test_init_db_adds_a_nullable_dedup_key_column`, `test_dedup_lookup_shape_uses_the_dedup_index`, `test_init_db_migrates_a_pre_dedup_key_database`, `test_init_db_creates_the_dedup_index_after_adding_the_column`, `test_two_init_db_calls_racing_on_dedup_key_both_converge` (12 new) |
| `tests/test_db.py` (updated, cited) | `test_schema_has_no_ip_or_location_column`, `test_audit_log_carries_session_id_without_breaking_construction`, `test_init_db_issues_no_alter_when_schema_is_current` (DDL tuple); docstring notes on `_create_pre_chat_sessions_database` and `test_two_init_db_calls_racing_on_session_id_both_converge` |
| `tests/test_migrate_to_turso_cli.py` (updated, cited) | `test_dest_columns_match_the_ddl` |

## Acceptance Criteria

- [x] `dedup_key TEXT` in both `CREATE_AUDIT_LOGS_TABLE` and `AUDIT_LOGS_ADDED_COLUMNS` (nullable, no default); `CREATE_AUDIT_LOGS_DEDUP_INDEX` is `CREATE INDEX IF NOT EXISTS idx_audit_logs_dedup ON audit_logs(user_id, dedup_key, timestamp)`; `AuditLog.dedup_key: Optional[str] = None`; `test_every_added_column_is_also_declared_in_the_create` passes.
- [x] `init_db()` on a fresh and a pre-PRD database: the column exists, existing rows read `NULL`, and `PRAGMA index_list(audit_logs)` includes `idx_audit_logs_dedup` with columns `(user_id, dedup_key, timestamp)` in order. The index statement runs after `_add_missing_columns(conn)` in the same `_session()` block (asserted by statement order + connection count).
- [x] `test_init_db_issues_no_alter_when_schema_is_current` passes; two racing `init_db()` calls on the `dedup_key` ALTER converge (`test_two_init_db_calls_racing_on_dedup_key_both_converge`).
- [x] `insert_audit_log(AuditLog(..., dedup_key="k"))` reads back `"k"` through `get_audit_log` and `summary_snapshot().rows`; an entry without it reads `None`.
- [x] `GET /audit` / `GET /stats` shapes unchanged (`AuditQueryEntry` untouched, D5); `tests/test_stats_router.py` and `tests/test_audit_router.py` unmodified and green; full suite green apart from the environment notes above.
