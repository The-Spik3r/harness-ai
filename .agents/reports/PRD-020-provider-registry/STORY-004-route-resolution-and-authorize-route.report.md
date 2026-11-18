---
story: STORY-004
prd: PRD-020
plan: .agents/plans/PRD-020-provider-registry/completed/STORY-004-route-resolution-and-authorize-route.plan.md
epic_branch: epic/PRD-020-provider-registry
commit: acc101e
status: COMPLETE
completed: 2026-11-18
---

# Implementation Report - STORY-004: Route resolution, visible models and authorize_route

## Summary

`provider_registry.py` gains `Route` (frozen, no key field, `relaxes_input()` read at call time), `resolve`, `supports_tools` and `visible_models`. `authz.py` gains `sees_every_model`, `role_may_use` (one role rule shared by `authorize_route` and `visible_models`) and `authorize_route`; `authorize_model` delegates and still returns None. `authz` imports `provider_registry` inside `authorize_route` (circular import).

## Validation

| Check | Result |
|---|---|
| Backend import | OK |
| Targeted tests (test_provider_routing, test_provider_registry, test_authz, test_rbac, test_query_pipeline_authorization, test_query_pipeline_break_glass, test_chat_outcomes_regression, test_prd020_legacy_fixtures, test_untouched_app) | 337 passed, 0 failed, 0 skipped |
| Full suite | GitHub CI on push (user decision) |

## Files Changed

- UPDATE `app/services/authz.py`, `app/services/provider_registry.py`
- CREATE `tests/test_provider_routing.py` (legacy equivalence parametrized over role x RBAC x allowlist x model)

## Deviations

None. `tests/test_query_pipeline.py` does not exist; used `test_query_pipeline_authorization.py` and `test_query_pipeline_break_glass.py`.

## Risk 2 (for STORY-011)

A `V1_TOOL_MODELS` entry outside `MODEL_ALLOWLIST` is reachable only by monkeypatch (the Settings validator forbids it); there `supports_tools` (legacy) can differ from `v1_translate.py:529`. Grep of tests/: `test_v1_tools.py` sets `V1_TOOL_MODELS` to `_OTHER_MODEL` (anthropic/claude-3.5-sonnet) at lines 683 and 792; it is in the default MODEL_ALLOWLIST (config.py:218), so no existing test is in the differing state. Other sets are `""`.

## Acceptance Criteria

All covered by `tests/test_provider_routing.py` per the plan's AC table: resolve (AC1), effective roles and indistinguishable denials (AC2), wildcard and passthrough denial (AC3), RBAC off (AC4), relaxes_input / visible_models / supports_tools / purity (AC5), legacy equivalence.
