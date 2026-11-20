---
story: STORY-003
prd: PRD-022
plan: .agents/plans/PRD-022-provider-fallback-and-native-adapters/completed/STORY-003-audit-columns-and-request-id.plan.md
epic_branch: epic/PRD-022-provider-fallback-and-native-adapters
commit: pending
status: COMPLETE
completed: 2026-11-20
---

# Implementation Report — STORY-003: audit columns, request_id, /audit filter

**Plan**: `.agents/plans/PRD-022-provider-fallback-and-native-adapters/completed/STORY-003-audit-columns-and-request-id.plan.md`
**Epic Branch**: `epic/PRD-022-provider-fallback-and-native-adapters`
**Commit**: `pending`

## Summary

Seven nullable columns (`request_id`, `attempt`, `route_model`, `fallback_reason`, `skipped_providers`, `cache_read_tokens`, `cache_write_tokens`) are appended last to `audit_logs` in the CREATE, `AUDIT_LOGS_ADDED_COLUMNS`, the `AuditLog` dataclass (before `id`), the insert SQL (49 placeholders), `_row_to_audit_log` and `_SUMMARY_SQL`'s `json_object`. `run_conversation` mints one uuid4 `request_id` as its first statement and threads it through all 11 pipeline `log_query` sites (`_deny` takes it as a required keyword-only parameter). The step-7 failure row, the output-redaction failure row and the success row write `attempt=1`, `route_model=model`; the success row also copies `cache_read_tokens` / `cache_write_tokens` from the result. `GET /audit` returns the seven fields and accepts an exact-match `?request_id=`. No chain, no `/stats` change.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | DDL, `AUDIT_LOGS_ADDED_COLUMNS`, `AuditLog` fields | `app/db/models.py` | done |
| 2 | insert SQL + values, row map, `_SUMMARY_SQL`, `_audit_filter`, two readers | `app/db/database.py` | done |
| 3 | seven optional params | `app/services/audit_logger.py` | done |
| 4 | `AuditQueryEntry` fields, projection, `?request_id=` | `app/models/schemas.py`, `app/routers/admin.py` | done |
| 5 | mint id, `_deny` kw-only, 11 sites, attempt/route_model, cache counts | `app/services/query_pipeline.py` | done |
| 6 | guard tests updated, each with a PRD-022 D10 comment | see Files Changed | done |
| 7 | new pipeline / endpoint tests | `tests/test_audit_request_id.py` | done |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | OK |
| Targeted tests | see the final handback (counts recorded there) |
| Full suite | GitHub CI on push (user decision) |

## Files Changed

App: `app/db/models.py`, `app/db/database.py`, `app/services/audit_logger.py`, `app/services/query_pipeline.py`, `app/models/schemas.py`, `app/routers/admin.py`.
Tests (updated): `tests/test_db.py`, `tests/test_db_resilience_write_id.py`, `tests/test_audit_characterization.py`, `tests/test_audit_router.py`, `tests/test_audit_logger.py`, `tests/test_migrate_to_turso_cli.py`, `tests/test_pii_redaction_integration.py`, `tests/test_schemas.py`, `tests/test_query_pipeline_audit_fields.py`.
Tests (new): `tests/test_audit_request_id.py`.

## Deviations from Plan

- Three pre-existing guards matched the substring `"ip"` in column or key names, which `skipped_providers` contains by accident (`sk-ip-ped`): `tests/test_db.py` (expected-columns test), `tests/test_audit_router.py::test_response_never_includes_ip_or_raw_text`, `tests/test_audit_logger.py::test_no_ip_or_location_field_in_logged_row`. Each now matches `"ip"` as a whole `_`-separated word (same intent: no IP-address field), with a comment citing PRD-022 D10.
- The PRD-021 positional asserts in `tests/test_db.py` (and the PRD-013, PRD-015 and PRD-020 ones of the same kind, plus two exact column counts `43 -> 50`) were re-anchored by seven, with comments; the orchestrator approved the PRD-021 ones. Their meaning is unchanged: the same columns in the same relative order, now followed by the PRD-022 block.
- `tests/e2e/test_local_model.py:60`: left unchanged. That tuple is a report-field list, not a column census.
- Success row reads the cache counts by direct attribute access (`openrouter_result.cache_read_tokens`); no suite fake returns a non-`UpstreamResult` there.
- `app/routers/query.py:168` (foreign-session refusal, the one `log_query` outside the pipeline) is unchanged: its row has `request_id` NULL by the public defaults.
- Docs (`docs/api.md`, `docs/features.md`) left for the docs story.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_audit_request_id.py` | one uuid4 per call and distinct across calls; pinned mint on a refusal; authorization and context-limit refusals (id, NULL attempt/route_model); step-7 failure, buffered and streamed success, output-redaction failure (attempt 1, requested model); cache counts copied / absent NULL / failure NULL; `fallback_reason` and `skipped_providers` NULL; `_deny` without `request_id` is a `TypeError`; `GET /audit?request_id=` |
| `tests/test_db.py` | `_PRD022_COLUMNS` block: both-places, order, init_db shape, old-DB convergence + no-op second boot, fresh DB without ALTER, round trip on both read shapes, exact-match filter |
| `tests/test_audit_router.py` | seven fields projected, exact match, own-scope AND, bound value, empty is 422 |
| `tests/test_audit_logger.py` | supplied / default |
| `tests/test_query_pipeline_audit_fields.py` | every pipeline `log_query` passes `request_id` |

## Acceptance Criteria

- [x] AC1 columns via `AUDIT_LOGS_ADDED_COLUMNS` and CREATE, old and fresh DB, buffered writer (`tests/test_db.py` PRD-022 block, `tests/test_db_resilience_write_id.py`, `tests/test_audit_journal.py`)
- [x] AC2 same uuid4 per call, never shared (`tests/test_audit_request_id.py`, `tests/test_query_pipeline_audit_fields.py`)
- [x] AC3 attempt=1 / route_model on step-7 rows, NULL before, cache counts (`tests/test_audit_request_id.py`)
- [x] AC4 `/audit` fields and `?request_id=` (`tests/test_audit_router.py`, `tests/test_pii_redaction_integration.py::test_audit_endpoint_contract_has_no_preview_fields`)
- [x] AC5 suite unchanged but for columns (guard edits listed above)
