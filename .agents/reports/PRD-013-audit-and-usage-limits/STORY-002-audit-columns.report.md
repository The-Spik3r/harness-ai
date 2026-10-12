---
story: STORY-002
prd: PRD-013
plan: .agents/plans/PRD-013-audit-and-usage-limits/completed/STORY-002-audit-columns.plan.md
epic_branch: epic/PRD-013-audit-and-usage-limits
commit: 3c61b53
status: COMPLETE
completed: 2026-10-12
---

# Implementation Report — STORY-002: Eight additive audit columns: convergence, AuditLog, writer and both read shapes

**Plan**: `.agents/plans/PRD-013-audit-and-usage-limits/completed/STORY-002-audit-columns.plan.md`
**Epic Branch**: `epic/PRD-013-audit-and-usage-limits`
**Commit**: `3c61b53` (plan commit: `d43055f`)

## Summary

`audit_logs` can now hold the ingress, size, token split, delivery flags, conversation key and usage-limit verdict of a request. Nothing sets a non-default value yet: `log_query` is untouched until STORY-005.

- **Schema.** `ingress`, `message_count`, `input_tokens`, `output_tokens`, `streamed`, `has_tool_calls`, `conversation_key` and `limit_exceeded` are declared after `profile` in both `CREATE_AUDIT_LOGS_TABLE` and `AUDIT_LOGS_ADDED_COLUMNS`. Six are nullable with no default. `streamed` and `has_tool_calls` are `INTEGER NOT NULL DEFAULT 0`. Each mapping entry has a comment giving its reason.
- **Convergence.** `init_db()`'s body and `_add_missing_columns` are unchanged. A pre-story database gains the eight columns through eight `ALTER`s, in mapping order, and no row is updated. No index was added.
- **Dataclass.** `AuditLog` has eight new fields before `id`, defaulting to `None` ×6 and `False` ×2.
- **Writer and both read shapes.** `insert_audit_log` writes 31 columns. `_row_to_audit_log` reads the eight back, with `bool(...)` on the two flags. The `json_object(...)` in `_SUMMARY_SQL` lists the eight keys, so `summary_snapshot().rows` equals `list_audit_logs()`.

**AC 5 was met with one exception, which the plan stated in advance (F-2).** The criterion says "no assertion changed". Three existing assertions pin the full list of audit columns or `AuditLog` fields, and each gained the eight names with a PRD-013 comment:

| Test | File | Change |
|---|---|---|
| `test_schema_has_no_ip_or_location_column` | `tests/test_db.py` | eight names added to the `expected` set |
| `test_audit_log_carries_session_id_without_breaking_construction` | `tests/test_db.py` | `names[-6:]` became `names[-14:]`, with the eight names before `"id"` |
| `test_dest_columns_match_the_ddl` | `tests/test_migrate_to_turso_cli.py` | eight names appended to the pinned list |

No other existing assertion changed. In `tests/test_audit_characterization.py` the diff against `126f0da` is one changed line (`FIELDS_ADDED_SINCE`, the module's stated extension point) plus additions. The four files PRD Section 11 freezes by name are untouched.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 0 | Preflight: Docker Desktop and `harness-libsql-dev` started, branch confirmed, plan commit `d43055f`, baseline taken | — | ✅ |
| 1 | Eight columns in the `CREATE` and the mapping with comments; eight `AuditLog` fields | `app/db/models.py` | ✅ |
| 2 | Writer (23 → 31 columns), mapper, `json_object`, `init_db()` docstring paragraph | `app/db/database.py` | ✅ |
| 3 | Three pinned inventories extended | `tests/test_db.py`, `tests/test_migrate_to_turso_cli.py` | ✅ |
| 4 | `FIELDS_ADDED_SINCE`; `test_no_arm_sets_these_prd013_fields` ×12 | `tests/test_audit_characterization.py` | ✅ |
| 5 | PRD-013 STORY-002 section, 22 cases, and the `_create_pre_prd013_database` fixture | `tests/test_db.py` | ✅ |
| 6 | Seven bite checks | — | ✅ |
| 7 | Full suite, diff checks, commit `3c61b53` | — | ✅ |
| 8 | This report | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ OK |
| Frontend lint | N/A. The UI is Reflex (Python) and was not changed |
| Baseline full suite, before any change | ✅ 3357 passed, 27 skipped |
| `pytest tests/test_db.py -k prd013` | ✅ 22 passed |
| `pytest tests/test_db.py` | ✅ 218 passed |
| `pytest tests/test_audit_characterization.py` | ✅ 39 passed (27 + 12) |
| `test_migrate_to_turso_cli`, `test_two_instance_smoke`, `test_init_db_issues_no_alter_when_schema_is_current` | ✅ 36 passed; the no-`ALTER` test is unedited (AC 3) |
| Full suite, first run | ⚠️ 3390 passed, 27 skipped, 1 failed (see note) |
| Full suite, second run | ✅ 3391 passed, 27 skipped. This is the baseline plus 34 |
| Frozen files (`test_query_outcomes_regression`, `test_chat_outcomes_regression`, `test_duplicate_scope`, `test_pii_characterization`) | ✅ no diff against `main` |
| E2E | ✅ 9/9 |

**About the one failure in the first full run.** `tests/test_query_session_id.py::test_the_403_row_records_no_profile_and_the_owned_send_records_chat` failed with `StorageError: ... tcp connect error ... (os error 10060)`, a connection timeout to the local libSQL server. It is not an assertion failure. The module passed 3 of 3 runs in isolation, and the second full run was green.

**The two values the plan could not measure both held against libSQL.** `PRAGMA table_info` reports `dflt_value` as `0` for the two flags (compared with `str(...) == "0"`), and a raw `SELECT` of a pre-story row returns the integer `0` for both.

## E2E Results

Run against the local libSQL dev server with a dummy OpenRouter key and a throwaway admin token. No real credentials were used.

| # | Check | Result |
|---|-------|--------|
| 1 | `pytest tests/test_db.py -k prd013` | ✅ 22 passed |
| 2 | Characterization module and its diff against `126f0da` | ✅ 39 passed; one changed line plus additions |
| 3 | `test_init_db_issues_no_alter_when_schema_is_current`, unedited | ✅ |
| 4 | Convergence by hand: a 24-column `audit_logs` with 3 rows, then `uvicorn app.main:app` | ✅ 32 columns, each new one once. All 3 rows read `NULL` ×6 and `0` ×2. A second `init_db()` behind a statement spy issued 11 statements and no `ALTER` |
| 5 | `GET /health` after that boot | ✅ 200 `{"status":"ok"}` |
| 6 | `GET /audit` and `GET /stats` | ✅ 200 each. `/audit` entries have the same 17 keys as before and none of the eight new fields. `/stats` has its nine figures |
| 6b | Admin console (`reflex run --env prod --single-port`), signed in, with a fourth row inserted carrying non-default values in the new fields | ✅ The Register lists all 4 rows and the Summary shows every figure (4 recorded, 1 held, 3 distinct users). No read error. This is the batched read with the 64-argument `json_object` |
| 7 | `test_migrate_to_turso_cli` and `test_two_instance_smoke` | ✅ |
| 8 | Bite checks | ✅ 7/7 (below) |
| 9 | Full suite equals baseline plus 34 | ✅ 3391 |

## Bite checks (Task 6)

Each was a temporary edit applied by a script that restored the file in a `finally` block. `git status` afterwards showed only the five story files.

| # | Temporary change | Tests that failed |
|---|---|---|
| 1 | `_SUMMARY_SQL`: drop the `'streamed', streamed` pair | `test_prd013_fields_survive_the_batched_read` only. The round-trip test passed, which is the batched-path-only failure the story describes |
| 2 | `insert_audit_log`: swap the `streamed` and `has_tool_calls` values | round trip, batched read, pre-PRD-013 migration |
| 3 | `insert_audit_log`: swap the `input_tokens` and `output_tokens` values | round trip, batched read, pre-PRD-013 migration |
| 4 | `_row_to_audit_log`: drop `bool(...)` from `streamed` | round trip, batched read, pre-PRD-013 migration |
| 5 | `AUDIT_LOGS_ADDED_COLUMNS`: remove `limit_exceeded` | its AC 1 case, the order test, pre-PRD-013 migration |
| 6 | `CREATE_AUDIT_LOGS_TABLE`: remove `conversation_key` | `test_every_added_column_is_also_declared_in_the_create`, its AC 1 case, the order test |
| 7 | `AUDIT_LOGS_ADDED_COLUMNS`: `streamed` as `INTEGER NOT NULL` | `test_added_columns_declaring_not_null_also_declare_a_default`, its AC 1 case, pre-PRD-013 migration |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/db/models.py` | UPDATE | +62/-4 |
| `app/db/database.py` | UPDATE | +35/-3 |
| `tests/test_db.py` | UPDATE | +339/-3 |
| `tests/test_audit_characterization.py` | UPDATE | +36/-1 |
| `tests/test_migrate_to_turso_cli.py` | UPDATE | +3/-0 |
| `.agents/plans/PRD-013-audit-and-usage-limits/completed/STORY-002-audit-columns.plan.md` | MOVE (archived) | 0 |
| `.agents/reports/PRD-013-audit-and-usage-limits/STORY-002-audit-columns.report.md` | CREATE | this file |

## Deviations from Plan

1. **The baseline was 3357 passed, not 3355.** It was fully green in one run, so the target became 3391.
2. **The pre-PRD-013 migration test does not call `monkeypatch.undo()`.** The plan's step 5 did. `undo()` would also revert the fixtures' `DATABASE_URL` patch. The test reads through the module's own `get_connection` instead, which the recording proxy never wrapped.
3. **The characterization module's docstring gained two lines, not a sentence inside the existing paragraph.** That keeps the diff to additions plus the one `FIELDS_ADDED_SINCE` line.
4. **Bite checks 2, 3, 4, 5 and 7 failed more tests than the plan named.** The migration test also inserts and reads back a full row, and the order test also reads the mapping. Every test the plan named did fail.
5. **E2E 6b inserted a fourth row with non-default values** before opening the console, so the batched read was exercised with real values and not only defaults.
6. **E2E side effect reverted.** `reflex run` rewrote `chat_ui/reflex.lock/package.json` and created `chat_ui/reflex.lock/package-lock.json`. The first was restored with `git restore` and the second deleted. Neither is in the commit.
7. **The second full-suite run** was added because of the connection timeout in the first.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_db.py` | `test_audit_logs_declares_each_prd013_column_in_both_places` ×8; `test_the_prd013_columns_are_declared_last_and_in_order`; `test_init_db_creates_each_prd013_column_with_its_shape` ×8; `test_init_db_migrates_a_pre_prd013_database`; `test_prd013_fields_default_when_not_supplied`; `test_prd013_fields_round_trip`; `test_prd013_fields_survive_the_batched_read`; `test_audit_log_carries_the_prd013_fields_without_breaking_construction` (plus the `_create_pre_prd013_database` fixture) |
| `tests/test_audit_characterization.py` | `test_no_arm_sets_these_prd013_fields` ×12, one per arm |

## For later stories

- **STORY-005**: `insert_audit_log` and both read shapes already carry all eight fields, so only `log_query` and the pipeline arms need to pass them. `_UNSET_THROUGH_DRIVE` in the characterization module pins six fields at their defaults on every arm and deliberately leaves out `message_count` and `conversation_key`. The per-arm assertions for those two are this story's to add.
- **STORY-006**: `AuditQueryEntry` and `GET /audit` do not expose the fields yet. `/stats` has no token aggregates.
- **STORY-011**: `limit_exceeded` exists and round-trips. `find_duplicate_timestamp` has no predicate on it yet.
- **STORY-018**: `scripts/migrate_to_turso.py::_audit_log_from_source` builds an `AuditLog` from the first 19 fields only. It already omitted `session_id` through `profile`, and now omits these eight too. A source file with non-default values in any of them would fail the script's read-back check. The script was not changed here.

## Observations (recorded, not fixed)

- `_Row`'s docstring in `app/db/database.py` says `_row_to_audit_log()` has "20 named reads". It now has 32. The count has been stale since PRD-008.

## Acceptance Criteria

- [x] Given `app/db/models.py`, when it is read, then the eight columns are each declared in both `CREATE_AUDIT_LOGS_TABLE` and `AUDIT_LOGS_ADDED_COLUMNS`.
- [x] Given a database created before this story with existing rows, when `init_db()` runs, then all eight columns exist, existing rows read `NULL` for the six nullable ones and `0` for `streamed` and `has_tool_calls`, and no row is updated.
- [x] Given a database already at the current schema, when `init_db()` runs, then no `ALTER` is issued (`test_init_db_issues_no_alter_when_schema_is_current` still passes, unedited).
- [x] Given an `AuditLog` with all eight fields set, when it is written by `insert_audit_log` and read back by `get_audit_log` and by `summary_snapshot().rows`, then both return the same eight values, with the two flags as `bool`.
- [x] Given the full suite, when it runs, then STORY-001's characterization and every existing test pass. **The only existing assertions changed are the three pinned column and field inventories named above.**
- [x] All tasks completed
- [x] Backend imports and the server starts without error
- [x] Follows existing patterns
