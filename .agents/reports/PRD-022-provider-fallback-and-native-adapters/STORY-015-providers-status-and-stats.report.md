---
story: STORY-015
prd: PRD-022
plan: .agents/plans/PRD-022-provider-fallback-and-native-adapters/completed/STORY-015-providers-status-and-stats.plan.md
epic_branch: epic/PRD-022-provider-fallback-and-native-adapters
commit: 688304a
status: COMPLETE
completed: 2026-11-20
---

# Implementation Report - STORY-015: GET /providers/status and the /stats fallback figures

## Summary

`GET /providers/status` (`stats:read`) renders `health.providers_status(names)` with names from the registry: no DB, no network, no message text. `/stats` gains `fallback_answers`, `failed_attempts` and `answers_by_provider` as three more columns of the one `_SUMMARY_SQL` statement (`SUMMARY_FIGURES` is now 16; the fifth `?` is the `answers_by_provider` LIMIT, last). Private standalone reads keep the census at 42.

## Deviations from Plan

- Orchestrator decision (a): `chat_ui/chat_ui/admin_state.py` `load()` now commits only the figures `_READS` names, because setting the three `/stats`-only figures raised `SetUndefinedStateVarError`. Test added for an error on a new figure.
- `since` is always a UTC string (PRD example shows null); breaker unchanged.
- Extra pinned tests extended: `test_db.py` (five `_SUMMARY_SQL` bind tuples, empty snapshot, 13 -> 16 statements), key-set pins in `test_stats_router.py`.

## Validation

- Import OK. Full suite: GitHub CI on push (user decision).
- 9-file set (providers_status, stats_router, audit_stats_prd013, provider_health, storage_status, actions_view, admin_state, storage_view, usage_view): 353 passed.
- `test_untouched_app.py` + `test_chat_ui_startup_guard.py`: 24 passed (alone). Combined with the 9 files in one process they failed 7-12 startup-guard probes ("probe crashed", empty output) while earlier overlapping runs of mine were alive; not reproducible alone. Environmental, flagged.
- `test_db.py -k "summary or snapshot or pattern_role or blocked_suspicious or provider or attempt"`: 31 passed; `-k "fields_survive_the_batched or fields_round_trip_on_both"`: 4 passed.
- `test_db_resilience_retry.py`: 168 passed. `test_pii_redaction_integration.py`: 16 passed.

## Acceptance Criteria

- [x] Shape, no I/O, 403: `test_providers_status.py` (full body, no db/network, requires stats:read)
- [x] 401 -> misconfigured ~300 s, no text: `test_a_401_force_open_reports_misconfigured_and_leaks_no_text`
- [x] `/stats` figures in one snapshot: `test_stats_router.py` new tests, `test_audit_stats_prd013.py` agreement test, one-round-trip test
- [x] Legacy provider closed: `test_legacy_deployment_lists_the_legacy_provider_closed`
