---
story: STORY-003
prd: PRD-022
slug: audit-columns-and-request-id
title: PRD-022 audit columns, request_id on every row, attempt=1 on step-7 rows, /audit filter
type: ENHANCEMENT
complexity: medium
epic_branch: epic/PRD-022-provider-fallback-and-native-adapters
created: 2026-11-20
---

# Plan: audit columns, request_id, /audit filter

## Summary

Append seven nullable columns (`request_id`, `attempt`, `route_model`, `fallback_reason`, `skipped_providers`, `cache_read_tokens`, `cache_write_tokens`) to `audit_logs` through every place PRD-021 STORY-009's `streamed_realtime..completion_id` touched, mint one uuid4 `request_id` at the top of `run_conversation`, thread it through all 11 `log_query` sites (required keyword on `_deny`), set `attempt=1`/`route_model=model` on the three rows written at or after step 7, copy cache tokens on the success row, and add an exact-match `?request_id=` to `GET /audit` mirroring `?completion_id=`. No chain, no `/stats` change.

- Story: `.agents/stories/PRD-022-provider-fallback-and-native-adapters/STORY-003-audit-columns-and-request-id.md`
- PRD sections used: 6.7, F8, D10, Section 10 (`GET /audit`)
- Systems affected: `app/db`, `app/services/audit_logger.py`, `query_pipeline.py`, `app/models/schemas.py`, `app/routers/admin.py`, audit tests.

## Design Decisions (binding, from the orchestrator)

- Column order, appended LAST everywhere (after PRD-021's `completion_id`; in the dataclass, before `id`): `request_id TEXT, attempt INTEGER, route_model TEXT, fallback_reason TEXT, skipped_providers TEXT, cache_read_tokens INTEGER, cache_write_tokens INTEGER`. All nullable, no default clause, no backfill, no CHECK.
- `request_id = str(uuid.uuid4())` minted once, first statement of `run_conversation` (`query_pipeline.py:439`, before `_validate_conversation` at :471). Step 0 writes no row (it raises), so placement only guarantees one id per call. Check `uuid` is imported in the module.
- `_deny` (`:363`) takes `request_id: str` as a **required keyword-only** parameter (behind a bare `*` after `route`). Public `log_query` keeps all seven new params optional (default None), placed after `completion_id` in the existing keyword-only block, before `journal_decisions`.
- `attempt=1`, `route_model=model` (the requested catalogue id) on rows written at/after step 7: the step-7 failure row, the success row, the output-redaction failure row. Rows before step 7: both NULL (kwargs omitted). `fallback_reason`/`skipped_providers` never passed. `cache_*_tokens` = `openrouter_result.cache_read_tokens` / `.cache_write_tokens` on the success row only (`UpstreamResult` fields exist, `upstream/types.py:130-131`); failure rows NULL.
- `GET /audit?request_id=<id>`: exact match, bound value, same RBAC/scoping/pagination; `Query(None, min_length=1, max_length=128)` like `completion_id` (`admin.py:44`). Do not touch `/stats` (STORY-015) or the chain.
- The journal serializes the `AuditLog` dataclass; the new fields have defaults, so pre-change journal entries replay. Confirm with `tests/test_audit_journal.py`.

## Skills In Use

None (`.agents/skills/` holds only `frontend-design`; no backend or audit skill applies).

## Patterns to Follow

| Category | Source | What to mirror |
|----------|--------|----------------|
| DDL + migration | `app/db/models.py:36-49` (CREATE ends `completion_id TEXT`, mind the comma), `:71-117` `AUDIT_LOGS_ADDED_COLUMNS` (ends `"completion_id": "TEXT"`) | add the 7 to both, same order, with a PRD-022 STORY-003 comment block like PRD-021's |
| Dataclass | `app/db/models.py:564-570` (PRD-021 fields, then `id`) | 7 `Optional[...] = None` fields between `completion_id` and `id` |
| Insert | `app/db/database.py:1573-1590` (column list + 42 `?`), `:1655-1690` values tuple | append 7 names, 7 `?` (49 total), 7 `entry.*` values, no `int()` coercion |
| Row map | `app/db/database.py:1795-1842` `_row_to_audit_log` | add `request_id=row["request_id"]` etc. |
| Register batch | `app/db/database.py:2269-2316` `_SUMMARY_SQL` `json_object(...)` | MUST add the 7 keys: `_row_to_audit_log` serves both read shapes, else `KeyError` |
| Filter | `app/db/database.py:1857-1900` `_audit_filter`, `count_audit_logs`, `list_audit_logs` | trailing defaulted `request_id: Optional[str] = None`; clause `request_id = ?` |
| log_query | `app/services/audit_logger.py:100-170` | 7 optional params, passed to `AuditLog(...)` |
| Schema | `app/models/schemas.py:293-308` (`completion_id` last in `AuditQueryEntry`) | 7 `Optional[...] = None` fields |
| Route | `app/routers/admin.py:104-114` | pass 7 fields through; `request_id` query param into `count_audit_logs` / `list_audit_logs` |
| Tests | `tests/test_audit_router.py:480-575` (`_seed`, exact-match, own-scope AND, bound-value, empty-422) | clone for `request_id` |

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/db/models.py` | UPDATE | DDL, `AUDIT_LOGS_ADDED_COLUMNS`, `AuditLog` |
| `app/db/database.py` | UPDATE | insert SQL + values, `_row_to_audit_log`, `_SUMMARY_SQL`, filter + two readers |
| `app/services/audit_logger.py` | UPDATE | 7 optional params |
| `app/services/query_pipeline.py` | UPDATE | mint id, `_deny` kw-only, 11 sites |
| `app/models/schemas.py` | UPDATE | `AuditQueryEntry` +7 |
| `app/routers/admin.py` | UPDATE | projection + `?request_id=` |
| `tests/test_audit_request_id.py` | CREATE | pipeline behaviour |
| guard tests (Task 6) | UPDATE | each change gets a comment citing PRD-022 D10 |

`app/routers/query.py:168` (foreign-session refusal, the only `log_query` outside the pipeline) stays unchanged: its row has `request_id` NULL by the public defaults. Mention in the report.

## `log_query(` call sites in `query_pipeline.py` (pre-edit line numbers)

All get `request_id=request_id`, added AFTER `**_route_fields(route),` (which stays first; guard `tests/test_query_pipeline_routing.py:403-408` checks 120 chars).

| Line | Arm | attempt | route_model |
|------|-----|---------|-------------|
| 416 | `_deny`; its 5 callers at 528, 542, 555, 567, 590 each add `request_id=request_id` | NULL | NULL |
| 641 | usage admission refusal (2c) | NULL | NULL |
| 717 | context / estimated-token limit | NULL | NULL |
| 755 | duplicate block | NULL | NULL |
| 816 | pattern block | NULL | NULL |
| 857 | pattern flag | NULL | NULL |
| 914 | redaction-limit refusal | NULL | NULL |
| 971 | input-redaction `PiiRedactorError` (before the upstream calls at 1063/1152) | NULL | NULL |
| 1180 | step-7 upstream failure row (`except` after the call at 1152) | 1 | `model` |
| 1285 | output-redaction `PiiRedactorError` (post-upstream) | 1 | `model` |
| 1337 | success row; also `cache_read_tokens` / `cache_write_tokens` from `openrouter_result` | 1 | `model` |

## Tasks

1. **models.py**: DDL, `AUDIT_LOGS_ADDED_COLUMNS`, `AuditLog` fields. Validate: `.venv/Scripts/python -c "from app.main import app; print('OK')"`.
2. **database.py**: insert SQL (49 `?`), values tuple, `_row_to_audit_log`, `_SUMMARY_SQL`, `_audit_filter` (+ docstring), `count_audit_logs`, `list_audit_logs`. No new public function and no new `get_connection`/`_session` caller, so the `tests/test_db_resilience_retry.py` census (`_EXPECTED_KINDS`, `len == 42`, caller sets) is unchanged; still run it.
3. **audit_logger.py**: params + pass-through.
4. **schemas.py** + **admin.py**: fields, projection, query param. RBAC block untouched.
5. **query_pipeline.py**: mint `request_id`; `_deny` kw-only; the 11 sites per the table; `attempt=1, route_model=model` at 1180/1285/1337; cache tokens at 1337. Step-7 call arguments unchanged.
6. **Guard tests** (grep of `usage_estimated` / `completion_id` across `tests/`; each edit commented `# PRD-022 STORY-003 (D10)`):
   - `tests/test_db.py`: `:1085-1105` expected column set (+7); `:2280-2291` `names[-25:]` becomes `names[-32:]` with the 7 before `"id"`; `:1937-1946` signature snapshot of `list_audit_logs` / `count_audit_logs` (+ `request_id: Optional[str] = None`); `:5439-5442` PRD-021 asserts `[-4:]` and `[-5]` become false once PRD-022 is appended: re-anchor them (`[-11:-7]`, `[-12]`), do not delete, comment why; add a `_PRD022_COLUMNS` block (both places, order, init_db shape, old-DB convergence) cloned from the PRD-021 one (`:5253-5560`); check the ALTER fixtures at `:3070-3075`, `:3340-3345`.
   - `tests/test_db_resilience_write_id.py`: `:236-241` ALTER list, `:312-323` column order (+7).
   - `tests/test_audit_characterization.py:118-129` (+7).
   - `tests/test_audit_router.py:105-118` field set (+7); new `request_id` filter tests.
   - `tests/test_audit_logger.py:405-466`: new `_PRD022_SUPPLIED` supplied/default tests.
   - `tests/test_migrate_to_turso_cli.py:170-186` DDL column list (+7).
   - `tests/test_pii_redaction_integration.py:190-250` `test_audit_endpoint_contract_has_no_preview_fields`: add in sorted order `attempt` (before `audit_id`), `cache_read_tokens`, `cache_write_tokens` (after `audit_id`), `fallback_reason`, `request_id`, `route_model`, `skipped_providers`; comment: ids, counts and labels, not prompt text. Keep the test name (no rename, no `_DELIBERATELY_SUPERSEDED_TESTS` entry).
   - `tests/test_schemas.py:~191-197` full-dump dict (+7 None).
   - `tests/test_query_pipeline_audit_fields.py:602-640`: site counts (12 / 11) unchanged; add a scan: every pipeline `log_query` passes `request_id`.
   - `tests/e2e/test_local_model.py:60` column tuple (e2e, not run; keep consistent).
   - Run only: `tests/test_audit_journal.py`, `tests/test_query_pipeline_routing.py`.
7. **New `tests/test_audit_request_id.py`** (harness of `tests/test_query_pipeline_audit_realtime.py`): one call's rows share one uuid4, two calls differ; a pre-step-7 refusal (duplicate block and a `_deny` arm) has `request_id`, NULL `attempt`/`route_model`; step-7 failure, success and output-redaction-failure rows have `attempt==1`, `route_model==model`; `fallback_reason`/`skipped_providers` NULL everywhere; success row copies stub `cache_*_tokens`, failure row and absent values are NULL; `_deny(...)` without `request_id` raises `TypeError`; `GET /audit?request_id=` through the real app.

## End-to-End Tests

- [ ] `TestClient(app)`: POST `/query` (stubbed upstream), `GET /audit` shows the seven fields, `GET /audit?request_id=<id>` returns only that request's rows; an `audit:read:own` caller asking for another user's id gets an empty list, not 403.
- [ ] An old database without the seven columns gains them through `init_db()`; a second `init_db()` is a no-op.

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_audit_request_id.py tests/test_audit_router.py tests/test_audit_logger.py tests/test_audit_characterization.py tests/test_schemas.py tests/test_query_pipeline_audit_fields.py tests/test_query_pipeline_routing.py tests/test_query_pipeline_audit_realtime.py tests/test_audit_journal.py tests/test_migrate_to_turso_cli.py tests/test_db_resilience_write_id.py tests/test_pii_redaction_integration.py tests/test_untouched_app.py
# DB-heavy, by -k only (test_db.py alone is ~12 min), separate call:
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_db.py -k "added_columns or audit_log or prd021 or prd022 or signature or column"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_db_resilience_retry.py -k "kinds or session or census"
```

## Acceptance Criteria -> Tasks -> Tests

| AC | Task(s) | Test that proves it |
|----|---------|---------------------|
| AC1 columns via ADDED_COLUMNS, fresh + old DB, buffered writer | 1, 2 | new `_PRD022_COLUMNS` tests in `tests/test_db.py`; `tests/test_db_resilience_write_id.py`; `tests/test_audit_journal.py` |
| AC2 same uuid4 per call, never shared | 5, 7 | `tests/test_audit_request_id.py` (one-call, two-calls, `_deny` TypeError) |
| AC3 attempt=1 / route_model on step-7 rows, NULL before, cache tokens | 5, 7 | `tests/test_audit_request_id.py` (failure, success, redaction-failure, pre-step-7) |
| AC4 `/audit` fields and `?request_id=` | 4, 7 | `tests/test_audit_router.py` request_id tests; `tests/test_pii_redaction_integration.py::test_audit_endpoint_contract_has_no_preview_fields` |
| AC5 suite unchanged but for columns | 6 | the guard files above, edited only for column lists |

## Risks

- `_row_to_audit_log` serves both read shapes: omitting the `_SUMMARY_SQL` keys breaks the `/stats` register read with `KeyError` (Task 2).
- `tests/test_db.py:5439-5442` (PRD-021 `[-4:]`, `[-5]`) breaks by design once PRD-022 is appended: re-anchor, with a comment (it is a PRD-021 test; the edit is positional only).
- Stubs returning non-`UpstreamResult` objects at the success row would lack `cache_*` attributes; the pipeline tests confirm.
- `docs/api.md` and `docs/features.md` mention `completion_id`; docs left to the docs story unless the orchestrator wants them here.
