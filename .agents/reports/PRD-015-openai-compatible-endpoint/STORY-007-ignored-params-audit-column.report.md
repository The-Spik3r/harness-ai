---
story: STORY-007
prd: PRD-015
plan: .agents/plans/PRD-015-openai-compatible-endpoint/completed/STORY-007-ignored-params-audit-column.plan.md
epic_branch: epic/PRD-015-openai-compatible-endpoint
commit: 4100d89
status: COMPLETE
completed: 2026-10-23
---

# Implementation Report — STORY-007: audit_logs.ignored_params: column, writer, every pipeline arm and the /audit field

**Plan**: `.agents/plans/PRD-015-openai-compatible-endpoint/completed/STORY-007-ignored-params-audit-column.plan.md`
**Epic Branch**: `epic/PRD-015-openai-compatible-endpoint`
**Commit**: `4100d89`

## Summary

`audit_logs.ignored_params` is a nullable TEXT column. It is declared in `CREATE_AUDIT_LOGS_TABLE` and in `AUDIT_LOGS_ADDED_COLUMNS`, so `init_db()` converges an old database with one `ALTER` and backfills nothing. `AuditLog` carries the field just before `id`. `insert_audit_log` writes it, and `_row_to_audit_log` maps it on both read shapes: the row read and `summary_snapshot()`'s `json_object`.

The value reaches the row three ways:
- `log_query` takes it with a default of `None`.
- `_deny` requires it.
- `run_conversation` takes it keyword-only and passes it to all fourteen sites (four `_deny` calls, ten direct `log_query` calls).

`run_query`, `/query`'s foreign-session refusal and the chat UI pass nothing, so their rows read NULL. `GET /audit` returns the value unchanged; `/stats` is unchanged. No caller sets a non-NULL value yet; the `/v1` router does that in STORY-009.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Column, migration entry, dataclass field | `app/db/models.py` | ✅ |
| 2 | Writer, row mapper, summary `json_object` key | `app/db/database.py` | ✅ |
| 3 | `log_query(..., ignored_params=None)` | `app/services/audit_logger.py` | ✅ |
| 4 | Required on `_deny`; keyword-only on `run_conversation`; passed to all 14 sites | `app/services/query_pipeline.py` | ✅ |
| 5 | `AuditQueryEntry.ignored_params`; `/audit` passthrough | `app/models/schemas.py`, `app/routers/admin.py` | ✅ |
| 6 | Added the field to `FIELDS_ADDED_SINCE` | `tests/test_audit_characterization.py` | ✅ |
| 7 | DB tests: shape, migration, round trip, summary path | `tests/test_db.py` | ✅ |
| 8 | Per-arm tests, `_deny` `TypeError`, both call-site scans, signature | 5 pipeline test modules | ✅ |
| 9 | `/audit` key set and values; a real `/query` row | `tests/test_audit_router.py` | ✅ |
| 10 | Full regression | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ |
| Frontend lint | N/A (no frontend in this repo; no UI change) |
| Targeted tests (Tasks 6-9) | ✅ 278 + 248 + 42 passed |
| Mutation check (one arm's `ignored_params=` removed) | ✅ caught by the per-arm test, the AST scan and the source scan; source restored |
| Full suite, first run | ❌ 3 failed / 4,648 passed / 27 skipped (three more hand-written shape lists; see Deviations) |
| Full suite, after fix | ✅ 4,651 passed / 27 skipped, 285 s, on throwaway libSQL `:8086` under the keep-awake wrapper |
| E2E | ✅ 5/5 (one with the documented 502 environment limit, see below) |

### E2E (throwaway libSQL on `:8087`, uvicorn on `:8765`)

1. **Fresh DB**: `init_db()` → 33 columns; `ignored_params` = (`TEXT`, notnull 0, default NULL). uvicorn boots and `/health` returns 200. ✅
2. **Old DB**: I dropped the column and seeded a legacy row, leaving 32 columns. The app's first boot added it (33 columns, every row NULL); the second boot was a no-op (33 columns, `/health` 200). ✅
3. **`POST /query`**: against the live server it returned **502**, because OpenRouter answers `401 Unauthorized` from this machine (known environment limit). Its upstream-error row is on `/audit` with `"ignored_params": null`. The success path, run in-process with `call_openrouter` replaced against the same DB, returned **200 SUCCESS**, and that row also reads `null`. ✅
4. **`GET /stats`**: 200, the same 12 figures. ✅
5. **A `/v1`-shaped row**: `run_conversation(..., ingress="v1", ignored_params="seed,user")` → the live `/audit` shows `"ignored_params": "seed,user"` on the `v1` row and `null` on the `query` rows. ✅

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/db/models.py` | UPDATE | +17/-2 |
| `app/db/database.py` | UPDATE | +10/-3 |
| `app/services/audit_logger.py` | UPDATE | +11/-0 |
| `app/services/query_pipeline.py` | UPDATE | +26/-3 |
| `app/models/schemas.py` | UPDATE | +5/-0 |
| `app/routers/admin.py` | UPDATE | +2/-0 |
| `tests/test_db.py` | UPDATE | +173/-10 |
| `tests/test_query_pipeline_audit_fields.py` | UPDATE | +91/-1 |
| `tests/test_audit_router.py` | UPDATE | +58/-0 |
| `tests/test_query_pipeline_break_glass.py` | UPDATE | +22/-2 |
| `tests/test_query_pipeline_usage_limits.py` | UPDATE | +19/-0 |
| `tests/test_query_pipeline_pii_profiles.py` | UPDATE | +12/-0 |
| `tests/test_query_pipeline_run_conversation.py` | UPDATE | +5/-0 |
| `tests/test_audit_characterization.py` | UPDATE | +2/-0 |
| `tests/test_migrate_to_turso_cli.py` | UPDATE | +2/-0 |
| `tests/test_pii_redaction_integration.py` | UPDATE | +2/-0 |
| `tests/test_schemas.py` | UPDATE | +2/-0 |

## Deviations from Plan

1. **Four more `test_db.py` assertions needed the new name.** The plan listed only the column set (`:1089`) and the dataclass tail (`:2262`). The ones it missed:
   - `test_the_prd013_columns_are_declared_last_and_in_order`: `[-8:]` became `[-9:-1]`.
   - `test_init_db_migrates_a_pre_prd013_database`: one more `ALTER`, and 32 columns became 33.
   - `test_audit_log_carries_the_prd013_fields_without_breaking_construction`: `names[-9:]` became `names[-10:]`.
   - The plan's two named assertions were updated as listed.

   All were name additions; no values changed.
2. **Three more modules list the audit shape by hand, and the plan didn't name them.** The first full run found them; each gained the name:
   - `tests/test_migrate_to_turso_cli.py::test_dest_columns_match_the_ddl`
   - `tests/test_pii_redaction_integration.py::test_audit_endpoint_contract_has_no_preview_fields`
   - `tests/test_schemas.py::test_audit_response_shape`
3. **The pre-PRD-015 migration fixture is a literal 32-column table.** I wrote it as a literal (`_create_pre_prd015_database`) instead of reusing a pre-PRD-013 helper, so the migration test exercises exactly one column in flight.
4. **Most of the `/query` and chat NULL coverage is in existing tests.** `/query` (success, block, foreign-session refusal) and both chat branches already ran through the real code in `test_query_pipeline_audit_fields.py`, so those tests gained `ignored_params is None` assertions instead of new harnesses. `test_audit_router.py` also gained a real `/query` → `/audit` test, as the plan said.
5. **E2E 3 used two paths.** A live upstream success isn't possible on this machine, so the live check produced a 502 upstream-error row and the 200 success was proven in-process (the documented recipe).

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_db.py` | `test_audit_logs_declares_ignored_params_in_both_places_last`, `test_init_db_creates_ignored_params_as_nullable_text`, `test_init_db_migrates_a_pre_prd015_database`, `test_ignored_params_round_trips_and_defaults_to_none`, `test_summary_snapshot_carries_ignored_params` |
| `tests/test_query_pipeline_audit_fields.py` | `test_each_arm_records_ignored_params` (×12 arms), `test_each_arm_without_ignored_params_records_null` (×12), `test_deny_without_ignored_params_is_a_type_error`, `test_deny_requires_each_new_field_with_no_default[ignored_params]`, `test_every_pipeline_log_query_call_passes_ignored_params`; NULL assertions on the `/query` and chat tests |
| `tests/test_query_pipeline_pii_profiles.py` | `test_every_log_query_call_site_in_the_pipeline_passes_ignored_params` |
| `tests/test_query_pipeline_break_glass.py` | `test_the_refusal_row_records_ignored_params[passed/omitted]` |
| `tests/test_query_pipeline_usage_limits.py` | `test_the_refusal_row_records_ignored_params[passed/omitted]` |
| `tests/test_audit_router.py` | `test_audit_entry_carries_ignored_params`, `test_a_query_row_reads_null_ignored_params_on_audit` |
| `tests/test_query_pipeline_run_conversation.py` | signature: `ignored_params` keyword-only, default `None` |

## Acceptance Criteria

- [x] Given an existing database without the column, when `init_db()` runs, then `audit_logs.ignored_params` exists as nullable TEXT, existing rows read NULL, and a second `init_db()` is a no-op.
- [x] Given `run_conversation(..., ignored_params="seed,user")`, every one of the fourteen arms writes `"seed,user"`; given the keyword omitted, every row carries NULL.
- [x] Given `_deny` called without `ignored_params`, it raises `TypeError`.
- [x] Given `GET /audit`, a row with the column set returns it; `/query` and chat rows return `null`; every existing `/audit` and `/stats` assertion is unchanged in value.
- [x] Both call-site scans require `ignored_params` on every direct `log_query` call inside `run_conversation`.
