---
story: STORY-012
prd: PRD-018
plan: .agents/plans/PRD-018-db-resilience/completed/STORY-012-storage-status-and-admin-panel.plan.md
epic_branch: epic/PRD-018-db-resilience
commit: pending
status: COMPLETE
completed: 2026-11-17
---

# Implementation Report — STORY-012: GET /storage/status, counters and the admin Storage panel

**Plan**: `.agents/plans/PRD-018-db-resilience/completed/STORY-012-storage-status-and-admin-panel.plan.md`
**Epic Branch**: `epic/PRD-018-db-resilience`
**Commit**: `pending`

## Summary

New leaf module `app/db/storage_counters.py` (thread-safe, process-local). `CircuitBreaker` gained a generic `on_transition` hook; `database._new_storage_breaker()` uses it for `breaker_opens`. `_unit_of_work` counts `retries` / `exhausted`; `AuditJournal` counts appended / drained / torn tail and reports `headroom_bytes`. `database.storage_status()` reads memory only (no driver call, never `_client_lock`). `GET /storage/status` (`stats:read`) is registered in the router and the Caddyfile matcher. The admin console gets a Storage view (`/admin/storage`, fifth masthead peer). `usage_limits.charge` logs driver text through `_retry_detail`.

Orchestrator rulings applied (all 8 as proposed): (1) refused retries count in `exhausted`; (2) `draining` = drainer running AND breaker closed AND non-held-back entries > 0; (3) `headroom_bytes` = admission reserve (workers x 64 KiB); (4) `open`, `held_back_entries`, `held_back_files` kept; (5) leaf module; (6) `/admin/storage` fifth peer; (7) `_retry_detail(exc)` in the charge log; (8) `breaker_opens` counts every transition into open, re-opens included.

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| Targeted run 1 (24 files) | 1118 passed, 1 skipped, 4 failed (stale pins, fixed below) |
| Rerun of the 4 stale-pin files + test_query_pipeline_multiturn | 211 passed |
| Full suite | GitHub CI on push (user decision) |

## Deviations from Plan

- Copy constants for the keyed table heads are `STORAGE_COLUMN_*` (`COLUMN_OPERATION` already existed for the Actions view).
- Four pre-existing pinned tests updated (each with a PRD-018 STORY-012 comment): `test_admin_shell.py::test_view_keys_are_distinct` (4 -> 5), `test_db_resilience_retry.py` `_EXEMPT` gains `storage_status`, `test_db_resilience_breaker.py` (the single `CircuitBreaker(...)` now sits in `_new_storage_breaker`, gains `on_transition`; `storage_status` joins `_unit_of_work` as a `_storage_breaker` reader, as that test's docstring announced), plus `tests/test_copy.py` admin_copy census.
- `docs/api.md` untouched (STORY-014). Optional live console run not done; the page registers via the startup guard.

## Tests Written

`tests/test_storage_status.py` (24: shape, zero driver calls, client-lock held, endpoint 200/open/401, one test per counter, draining truth table, breaker purity); `tests/test_storage_view.py` (11); additive tests in `test_circuit_breaker.py`, `test_audit_journal.py`, `test_usage_limits.py`, `test_rbac.py` (role matrix for `/storage/status`).

## Acceptance Criteria

- [x] AC1 shape, in-memory only: `test_storage_status.py` shape + zero-call tests
- [x] AC2 `stats:read`, zero driver calls with the breaker open: endpoint tests, `test_rbac.py::test_storage_status_read_matrix`
- [x] AC3 breaker open -> 200 `state: "open"`, `/health` unchanged: `test_endpoint_answers_200_with_the_breaker_open`
- [x] AC4 panel reads `storage_status()` in-process: `test_storage_view.py`, `test_chat_ui_startup_guard.py`
- [x] AC5 each counter once per event: one test per counter
- [x] Charge-log redaction: `test_charge_logs_driver_text_only_through_the_redaction`; Caddyfile + `test_caddyfile_routes.py` updated
