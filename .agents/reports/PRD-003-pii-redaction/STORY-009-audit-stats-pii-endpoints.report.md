---
story: STORY-009
prd: PRD-003
plan: .agents/plans/PRD-003-pii-redaction/completed/STORY-009-audit-stats-pii-endpoints.plan.md
epic_branch: epic/PRD-003-pii-redaction
commit: fc4804f
status: COMPLETE
completed: 2026-08-02
---

# Implementation Report — STORY-009: GET /audit and GET /stats — PII telemetry fields

**Plan**: `.agents/plans/PRD-003-pii-redaction/completed/STORY-009-audit-stats-pii-endpoints.plan.md`
**Epic Branch**: `epic/PRD-003-pii-redaction`
**Commit**: `fc4804f`

## Summary

`GET /audit` now returns `pii_detected_input`, `pii_detected_output`, and `pii_entities` per row; `GET /stats` gains `pii_detected_queries` and `top_pii_entities` aggregates. Two new query helpers (`count_pii_detected_queries`, `top_pii_entities`) were added to `app/db/database.py`. No change to how telemetry is written — [[STORY-004]] already writes it on every query; this story only reads it back out through the admin API.

`top_pii_entities` counts individual entity types across rows, not comma-joined strings as opaque buckets — a single audit row can carry `"EMAIL_ADDRESS,PERSON"`, and `GROUP BY` on that raw column would fragment identical entity sets that happen to be joined in a different order. It fetches raw rows and tallies per-entity in Python instead.

## Scope Decision: `prompt_preview` excluded from `/audit`

The story's AC1 text says the new fields go "alongside the existing unchanged `prompt_preview` field" — but `AuditQueryEntry` has never included `prompt_preview`, and the pre-existing PRD-001 test `test_response_never_includes_ip_or_raw_text` (`tests/test_audit_router.py`) explicitly asserts it's absent from the HTTP response. The story's own Technical Notes only list `pii_detected_input`/`pii_detected_output`/`pii_entities` as fields to add — no `prompt_preview` mention. Per the plan's Design Note 1, this story adds only the three PII telemetry fields and leaves `prompt_preview` exposure untouched; the guard test was left unmodified and still passes. Flagged here as a deviation from the AC's literal wording, not silently resolved.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Extend response schemas | `app/models/schemas.py` | ✅ |
| 2 | Add `count_pii_detected_queries()` / `top_pii_entities()` | `app/db/database.py` | ✅ |
| 3 | Wire new fields into `get_audit()` / `get_stats()` | `app/routers/admin.py` | ✅ |
| 4 | Unit tests for the two new query helpers | `tests/test_db.py` | ✅ |
| 5 | Extend `/audit` router tests | `tests/test_audit_router.py` | ✅ |
| 6 | Extend `/stats` router tests | `tests/test_stats_router.py` | ✅ |
| 7 | Full-suite regression + scope check | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ |
| Frontend lint | N/A — no npm frontend in this repo (Reflex/Python project) |
| Tests | ✅ 180 passed (175 baseline + 5 new) |
| E2E | ✅ (see below) |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/models/schemas.py` | UPDATE | +5 |
| `app/db/database.py` | UPDATE | +26 |
| `app/routers/admin.py` | UPDATE | +7 |
| `tests/test_db.py` | UPDATE | +94 |
| `tests/test_audit_router.py` | UPDATE | +40 |
| `tests/test_stats_router.py` | UPDATE | +43 |
| `tests/test_schemas.py` | UPDATE | +5 (deviation, see below) |

## Deviations from Plan

1. **`tests/test_schemas.py` required updates the plan did not anticipate.** Task 7's full-suite regression run surfaced 2 failures: `test_audit_response_shape` and `test_stats_response_shape` assert `AuditResponse.model_dump()` / `StatsResponse.model_dump()` against literal dict fixtures that predate this story's new fields. Fixed by adding the three new default-valued fields (`pii_detected_input: False`, `pii_detected_output: False`, `pii_entities: []`) to the `test_audit_response_shape` expected dict, and `pii_detected_queries: 0`, `top_pii_entities: []` to `test_stats_response_shape`'s. This is the same pattern [[STORY-007]] already used for `QuerySuccessResponse`'s shape test. No plan file was updated to reflect this — noted here per the Golden Rule (fix immediately, document the deviation) rather than silently expanding the plan's Files to Change table after the fact.
2. **E2E PII-flagged row was inserted directly via `insert_audit_log`, not through a live `POST /query`.** No real `OPENROUTER_API_KEY` is available in this environment, and `query_pipeline.py`'s `OpenRouterError` branch (line 72-81) does not currently pass `pii_detected_input`/`pii_entities` to `log_query` even when input redaction already succeeded before the OpenRouter call failed — so a failed live call would not have produced a PII-flagged row anyway. This is pre-existing pipeline behavior from [[STORY-005]]/[[STORY-006]], out of scope for this story (`query_pipeline.py` was not touched — confirmed absent from `git diff --stat` for this commit). Inserted a probe row directly against the running server's SQLite file instead, verified via `curl` against `/audit` and `/stats`, then deleted the probe rows (2 rows: the PII probe and the earlier failed-`POST /query` audit row from testing the live OpenRouter path) to leave `harness_ai.db` as found. `harness_ai.db` is not git-tracked, so no cleanup commit was needed.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_db.py` | `test_count_pii_detected_queries_counts_input_or_output`, `test_top_pii_entities_ranked_by_frequency_desc`, `test_top_pii_entities_respects_limit` (+ extended `test_aggregates_on_empty_db_return_zero_or_empty`) |
| `tests/test_audit_router.py` | `test_pii_telemetry_fields_reflect_audit_log_values` (+ extended `test_valid_token_returns_expected_shape`'s key-set assertion) |
| `tests/test_stats_router.py` | `test_pii_detected_queries_and_top_pii_entities_reflect_flagged_rows` (+ extended `test_valid_token_returns_expected_shape_and_values` and `test_zero_rows_returns_zeroed_stats_without_error`) |
| `tests/test_schemas.py` | No new functions; `test_audit_response_shape` and `test_stats_response_shape` extended (Deviation 1) |

## E2E Verification

- `python -c "from app.main import app; print('ok')"` → `ok`
- `uvicorn app.main:app --port 8010` → started cleanly; `curl http://localhost:8010/health` → `{"status":"ok"}`
- Inserted a probe row via `insert_audit_log` with `pii_detected_input=True`, `pii_detected_output=True`, `pii_entities="EMAIL_ADDRESS,PERSON"`
- `curl -H "Authorization: Bearer $ADMIN_TOKEN" http://localhost:8010/audit` → the probe row's entry included `"pii_detected_input": true, "pii_detected_output": true, "pii_entities": ["EMAIL_ADDRESS", "PERSON"]`
- `curl -H "Authorization: Bearer $ADMIN_TOKEN" http://localhost:8010/stats` → `"pii_detected_queries":1,"top_pii_entities":["EMAIL_ADDRESS","PERSON"]`
- `curl http://localhost:8010/audit` (no auth header) → `401` — unauthenticated access still rejected, no new surface added
- Probe rows deleted from `harness_ai.db` after verification; server process terminated

## Acceptance Criteria

- [x] Given `GET /audit` (admin token required, unchanged auth), when called, then each entry includes `pii_detected_input`, `pii_detected_output`, and `pii_entities` — `prompt_preview` intentionally excluded, see Scope Decision above
- [x] Given `GET /stats` (admin token required), when called, then the response includes `pii_detected_queries` and `top_pii_entities`
- [x] Given no query has ever triggered PII detection, when `GET /stats` is called, then `pii_detected_queries` is `0` and `top_pii_entities` is `[]`
- [x] Given the existing `tests/test_audit_router.py` and `tests/test_stats_router.py`, when run, then they still pass, extended with assertions for the new fields
