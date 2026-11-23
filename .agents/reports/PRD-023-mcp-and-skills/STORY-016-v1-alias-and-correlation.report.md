---
story: STORY-016
prd: PRD-023
plan: .agents/plans/PRD-023-mcp-and-skills/completed/STORY-016-v1-alias-and-correlation.plan.md
epic_branch: epic/PRD-023-mcp-and-skills
commit: pending
status: COMPLETE
completed: 2026-11-23
---

# Implementation Report - STORY-016: `/v1` alias resolution and gateway correlation

## Summary

`action_policy.resolve_v1_alias` (pure) and `evaluate_all(..., aliases=AliasInput)` decide a raw `/v1` alias name under the MCP mapping; the decision keeps the raw name and carries `mcp_server`. Step 7c builds `aliases` through `query_pipeline._alias_input` (None with MCP off or no prefixes; config only, no DB read). `action_audit._row_of` stamps `mcp_server` and the canonical hash on an alias row (surface stays `v1`). The gateway's pre-forward insert is now one `INSERT ... SELECT` (`database.insert_mcp_decision_linked`) that claims the newest linkable `/v1` row atomically; `_correlate` is removed.

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| Tests (`-m "not db"`: test_v1_alias, test_action_policy, test_action_audit, test_mcp_audit, test_mcp_gateway, test_mcp_correlation, test_untouched_app, test_db_resilience_retry, test_query_pipeline_tools) | 338 passed, 95 deselected |
| SQL probe (stdlib sqlite 3.49.1, real `action_decisions` DDL) | link, reuse, window and no-candidate scenarios behave as the db tests expect |
| db tests (correlation, step-7c both paths, census) | CI only (Docker down) |
| Full suite | GitHub CI on push (user decision) |

## Deviations from Plan

- Accepted by the orchestrator: hash computed in `_row_of` (not stored on the decision); new `insert_mcp_decision_linked`, census 44 -> 45.
- `mcp_gateway._now` already exists (monotonic clock for the catalogue cache), so the correlation clock is `_link_clock`.
- `query_pipeline._alias_input` factored out of step 7c so the off/no-prefix cases test without a database.
- `tests/test_action_policy.py::test_action_decision_shape` gained `mcp_server` (commented, STORY-016).
- Step 7c calls `evaluate_all(calls, identity)` unchanged when there are no aliases (existing spies keep their signature).

## Acceptance Criteria

- [x] AC1 alias deny/allow + row columns: `test_drop_table_alias_is_denied_sql_ddl_and_keeps_the_raw_name`, `test_select_alias_is_released_and_the_row_carries_the_alias_columns`
- [x] AC2 two prefixes / none / off: `test_two_resolving_prefixes_are_tool_malformed`, `test_unresolved_invisible_and_hashed_names_are_todays_decision`, `test_mcp_disabled_passes_no_aliases_and_never_reads_mcp_config`
- [x] AC3 correlation, window, reuse, concurrency: `tests/test_mcp_correlation.py` (db, CI)
- [x] AC4 no DB read, both paths: `test_alias_resolution_adds_no_database_read`, `test_alias_call_is_decided_under_the_mcp_mapping_on_the_buffered_and_realtime_paths` (db, CI)
