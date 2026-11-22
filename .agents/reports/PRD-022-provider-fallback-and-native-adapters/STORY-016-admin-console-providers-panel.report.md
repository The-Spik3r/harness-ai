---
story: STORY-016
prd: PRD-022
plan: .agents/plans/PRD-022-provider-fallback-and-native-adapters/completed/STORY-016-admin-console-providers-panel.plan.md
epic_branch: epic/PRD-022-provider-fallback-and-native-adapters
commit: pending
status: COMPLETE
completed: 2026-11-20
---

# Implementation Report - STORY-016: Admin console Providers panel and attempt column

## Summary

Sixth console view `/admin/providers` (Storage's twin: verdict in words, one block per provider, counters, failed and skipped keyed tables), filled in process by `AdminState.load()` from `health.providers_status()` with the registry's names. Register gains a `Try` (attempt) column after Provider, a `Request` disclosure line, and a request_id match in the free-text search (client-side over the loaded window of `REGISTER_ROW_LIMIT` rows). Gated exactly like Storage (admin-token gate, `authenticated` early return); no `app/` change, no new route, `_READS` untouched.

## Validation

| Check | Result |
|-------|--------|
| Backend import | OK |
| test_chat_ui_startup_guard.py (alone) | 15 passed |
| test_providers_view, test_storage_view, test_admin_palette, test_providers_status, test_untouched_app, test_usage_view, test_actions_view, test_admin_formatting, test_chat_ui_storage_failures, test_admin_state, test_admin_models, test_admin_shell, test_copy, test_caddyfile_routes | all pass |
| test_register.py | 2 failures, left unedited per orchestrator rule (below) |

## Deviations

- Two PRD-013/021 assertions in `tests/test_register.py` break and were NOT edited: `test_neither_preview_survives_the_projection` (its `_Log` stub needs `request_id = None` and `attempt = None`) and `test_the_provider_column_keeps_the_quality_floor` (`_MIN_WIDTH` pin `73.5rem` -> `77.75rem`).
- Additive census extensions (new names only): `tests/test_admin_shell.py`, `tests/test_copy.py`, `tests/test_caddyfile_routes.py`, `tests/test_admin_models.py` (`AUDIT_ROW_FIELDS`), and `test_view_keys_are_distinct` 5 -> 6.
- `FILTER_SEARCH_PLACEHOLDER` unchanged (clipping at phone width, as for ingress).

## Acceptance Criteria

- [x] AC1 panel in process beside Storage: `tests/test_providers_view.py`, `test_admin_shell.py`
- [x] AC2 attempt column, provider kept, request_id filter: new tests in `tests/test_register.py`, `:791` 11 -> 12
- [x] AC3 theme and startup guard: `test_chat_ui_startup_guard.py`, `test_admin_palette.py`, `test_copy.py`
- [x] AC4 same gate as Storage: `test_an_unauthenticated_load_leaves_the_providers_view_empty`
