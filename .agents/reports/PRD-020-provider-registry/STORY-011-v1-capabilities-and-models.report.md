---
story: STORY-011
prd: PRD-020
plan: .agents/plans/PRD-020-provider-registry/completed/STORY-011-v1-capabilities-and-models.plan.md
epic_branch: epic/PRD-020-provider-registry
commit: pending
status: COMPLETE
completed: 2026-11-18
---

# Implementation Report - STORY-011: /v1 tool capability from the registry and per-role GET /v1/models

## Summary

The router decides the file-mode tool capability via `authz.authorize_route` (pure; a `PermissionDenied` passes True so the pipeline's single denial answers, T3) and passes it to the translator as `tools_supported`. `GET /v1/models*` branch on `provider_registry.current().is_legacy`; file mode lists `visible_models(identity)` with a `harness` extension; legacy code and bytes are untouched.

## Files Changed

| File | Action |
|------|--------|
| `app/services/v1_translate.py` | UPDATE: `tools_supported`, `_TOOL_CAPABILITY_RULE` |
| `app/models/v1_schemas.py` | UPDATE: `ModelCapabilities`, `ModelHarness`, `ModelEntry.harness` + serializer dropping None |
| `app/routers/v1.py` | UPDATE: `_tools_supported`, `_registry_entry`, file-mode list/retrieve |
| `tests/test_v1_models_registry.py` | CREATE (7 tests) |
| `tests/test_v1_tools_registry.py` | CREATE (11 tests) |

## Validation

Import OK. Targeted run (test_v1_models_registry, test_v1_tools_registry, test_v1_models, test_v1_tools, test_v1_translate_request, test_v1_schemas, test_v1_router, test_prd020_legacy_fixtures, test_untouched_app): 1465 passed, 0 failed, 0 skipped. Full suite: GitHub CI on push (user decision).

## Deviations from Plan

None. No import cycle: `authz` is imported at module level in the router; `authorize_route` imports `provider_registry` lazily.

## Acceptance Criteria

- [x] AC1: `test_tools_false_model_is_refused`, `test_legacy_message_keeps_the_suffix`
- [x] AC2: `test_list_is_visible_models_in_order_with_harness`, `test_admin_sees_every_catalogued_model_and_no_passthrough`
- [x] AC3: `test_prd020_legacy_fixtures.py`, unchanged `test_v1_models.py`, `test_legacy_list_has_no_harness_key`
- [x] AC4: `test_retrieve_404_bodies_are_byte_equal`
- [x] AC5: `test_flag_off_in_file_mode`
- [x] T3: `test_t3_denials_are_byte_equal`
