---
story: STORY-008
prd: PRD-022
plan: .agents/plans/PRD-022-provider-fallback-and-native-adapters/completed/STORY-008-anthropic-primary-end-to-end.plan.md
epic_branch: epic/PRD-022-provider-fallback-and-native-adapters
commit: pending
status: COMPLETE
completed: 2026-11-20
---

# Implementation Report — STORY-008: Anthropic as a primary through the pipeline

## Summary

Two pipeline gaps closed, everything else verified by integration tests against the STORY-006 stub.
`dropped_params_for(route, request)` (public, `app/services/upstream/__init__.py`) dispatches by provider type, so `query_pipeline.py` never branches on it. The realtime branch calls it after `collect()`. The success row's `ignored_params` is `_merge_ignored_params(edge, dropped, route)`. The realtime `UpstreamRequest` now passes `route.model`.

## Validation

| Check | Result |
|-------|--------|
| Backend import | OK |
| Targeted tests | 140 passed, 0 failed, 0 skipped (new file 16; routing, streaming, audit_realtime, v1_realtime, prd020_legacy_fixtures, untouched_app) |
| E2E (buffered /v1 tool loop; realtime SSE, both through the stub) | pass |
| Full suite | GitHub CI on push (user decision) |

## Files Changed

| File | Action |
|------|--------|
| `app/services/upstream/__init__.py` | UPDATE: `dropped_params_for` |
| `app/services/query_pipeline.py` | UPDATE: import, `_merge_ignored_params`, `model=` on the realtime request, realtime `dropped_params`, success-row `ignored_params` |
| `tests/test_anthropic_primary_pipeline.py` | CREATE (16 tests) |

## Deviations from Plan

- Helper takes `route` (not a provider name) and returns the edge value when `route` is None, so injected stubs never dereference it. Orchestrator correction applied (no type branch in the pipeline).
- Tool-loop test grants `action:shell.exec` to the user role: `npm test` is unlisted under the built-in policy and would otherwise be denied before release. The decisions are still compared with the `oai` control.
- Duplicate-query detection (24 h) forced unique prompts in the tests.
- No stub change was needed; no existing test changed.

## Acceptance Criteria

- [x] AC1 tool loop, `evaluate_all`, canonical arguments: `test_v1_tool_loop_through_an_anthropic_primary`
- [x] AC2 `temperature@<provider>` on the success row: `test_temperature_is_recorded_as_ignored_on_the_success_row`, `test_an_error_row_keeps_only_the_edge_ignored_params`, `test_realtime_records_dropped_params_and_cache_usage`
- [x] AC3 cache columns, prompt total, charge: `test_cache_usage_lands_on_the_row_and_charge_gets_the_full_prompt`
- [x] AC4 refusal row: `test_refusal_is_content_filter_one_success_row_attempt_one`, `test_realtime_refusal_is_a_success_row_content_filter`
- [x] AC5 realtime reasoning gates: `test_realtime_reasoning_with_and_without_reasoning_view`
- [x] Guards: `test_every_upstream_request_in_app_passes_the_model`, `test_dropped_params_for_dispatches_on_the_provider_type`, `test_merge_ignored_params*`
