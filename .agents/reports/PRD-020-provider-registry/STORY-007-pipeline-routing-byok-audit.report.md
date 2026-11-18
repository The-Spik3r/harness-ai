---
story: STORY-007
prd: PRD-020
plan: .agents/plans/PRD-020-provider-registry/completed/STORY-007-pipeline-routing-byok-audit.plan.md
epic_branch: epic/PRD-020-provider-registry
commit: d3b6ec6
status: COMPLETE
completed: 2026-11-18
---

# Implementation Report - STORY-007: Pipeline step 2 routing, BYOK per provider and per-row provider audit

**Plan**: `.agents/plans/PRD-020-provider-registry/completed/STORY-007-pipeline-routing-byok-audit.plan.md`
**Epic Branch**: `epic/PRD-020-provider-registry`
**Commit**: `d3b6ec6`

## Summary

`run_conversation` resolves the route once at step 2 with `authorize_route` (same denial label and reason), refuses a caller key for a `byok: false` provider (`query:byok:<name>`, before 2b/2c: nothing sent, nothing charged), and stamps `provider` / `upstream_model` / `provider_trust` from the Route on every row written after step 2 (NULL on the submit, model and both BYOK denials). `model_used` stays the requested id. The upstream seam is unchanged.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Route at step 2, BYOK per provider, `_route_fields`, `_deny(route=)` | `app/services/query_pipeline.py` | done |
| 2 | `**_route_fields(route)` on the 10 direct `log_query` sites | `app/services/query_pipeline.py` | done |
| 3 | Repoint three step-order spies to `authorize_route` (approved) | `tests/test_query_pipeline_{break_glass,multiturn,usage_limits}.py` | done |
| 4 | New routing tests | `tests/test_query_pipeline_routing.py` | done |
| - | Stale comment names `authorize_route` | `app/services/v1_translate.py` | done |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| Targeted tests (one call, 13 files) | 354 passed, 0 failed, 0 skipped |
| Full suite | GitHub CI on push (user decision) |

## Deviations from Plan

- The plan counted 11 direct `log_query` sites and 12 calls; the file has 10 direct sites plus `_deny`'s, 11 calls. The source-guard test asserts 11.
- `_drive`'s duplicate arm seeds with a default model bound at import, so in file mode the duplicate arm has its own test (`test_duplicate_rows_carry_the_route`).
- The working tree also held uncommitted STORY-006 assertion fixes (`test_migrate_to_turso_cli.py`, `test_pii_redaction_integration.py`, `test_schemas.py`, `test_storage_status.py`); committed separately as a STORY-006 follow-up, not part of this story's diff.

## Tests Written

`tests/test_query_pipeline_routing.py` (36 cases): two stubs over `/query` and `/v1` (own key, wire model, other stub silent); BYOK refusal on `byok: false` (body, no upstream, no usage rows, NULL fields), BYOK sent on `byok: true`, no-`query:byok` caller keeps today's verdict; per-arm provider fields in legacy and file mode (all ARM_CASES), break-glass, usage limit, duplicate, upstream 5xx (model_used is the requested id); injected stub gets the original id; source guard.

## Acceptance Criteria

- [x] AC1 authorize_route, same label/reason, order tests green (authorization + three repointed order tests)
- [x] AC2 BYOK per provider (`test_byok_*`)
- [x] AC3 two stubs, own key (`test_two_stubs_*`)
- [x] AC4 per-row fields, NULL at/before step 2 (`test_row_provider_fields_*` + source guard)
- [x] AC5 injected stub signature (`test_injected_stub_*`)
