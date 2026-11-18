---
story: STORY-009
prd: PRD-020
plan: .agents/plans/PRD-020-provider-registry/completed/STORY-009-usage-estimate.plan.md
epic_branch: epic/PRD-020-provider-registry
commit: pending
status: COMPLETE
completed: 2026-11-18
---

# Implementation Report - STORY-009: Estimate usage when a provider reports none

**Plan**: `.agents/plans/PRD-020-provider-registry/completed/STORY-009-usage-estimate.plan.md`
**Epic Branch**: `epic/PRD-020-provider-registry`
**Commit**: `pending`

## Summary

New pure `app/services/usage_estimate.py` (`estimate_tokens`, ceil per side, tools counted as sorted-key JSON). `OpenAICompatibleAdapter.complete` applies the D8 table through `_resolve_usage`; `UpstreamResult.usage_estimated` carries the flag. The pipeline forwards it to the two post-upstream success rows (step 7b untouched: a None split lands in `unsplit_tokens`). `/v1` emits `harness.usage_estimated: true` only when true. Legacy (`usage_missing: error`) keeps today's message texts; `null` or non-object usage now raises the same prefix with `'usage'` instead of a bare `TypeError`.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Pure estimate | `app/services/usage_estimate.py` | done |
| 2 | `usage_estimated` field | `app/services/upstream/types.py` | done |
| 3 | D8 table (`_resolve_usage`) | `app/services/upstream/openai_compatible.py` | done |
| 4 | Forward the flag to 2 rows | `app/services/query_pipeline.py` | done |
| 5 | Schema field + serializer, translate | `app/models/v1_schemas.py`, `app/services/v1_translate.py` | done |
| 6 | Tests | see below | done |
| 7 | Fix existing assertion | `tests/test_upstream_adapter.py` | done |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| Frontend lint | n/a |
| Targeted tests | 995 passed, 0 failed, 0 skipped |
| E2E (HTTP /query + /v1, null and reported usage) | pass (`test_http_bodies`) |
| Full suite | GitHub CI on push (user decision) |

## Deviations from Plan

- `tests/test_prd020_legacy_fixtures.py::test_success_result_fields_match_recorded` records `dataclasses.asdict(UpstreamResult)`, so the new field failed it. The fixture `results.json` is unedited; the test now pops `usage_estimated` (asserting it is False) before the byte comparison, with a PRD-020 STORY-009 comment. The orchestrator should confirm this is acceptable.
- Added an HTTP E2E test to `test_query_pipeline_usage_estimate.py` (plan listed it only as an E2E step).

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_usage_estimate.py` | table, key order, non-ASCII tools, None content, cpt <= 0, no mutation, purity |
| `tests/test_usage_estimate_adapter.py` | stub `usage: null`, D8 table x estimate/error, sum of splits, total unchanged, legacy messages, tools+cpt |
| `tests/test_query_pipeline_usage_estimate.py` | flagged row, unsplit charge, reported row, upstream-error row, HTTP bodies |
| `tests/test_v1_translate_result.py` | estimated body, reported body has no key |
| `tests/test_upstream_adapter.py` | modified `no_usage` assertion (D8) |
| `tests/test_prd020_legacy_fixtures.py` | modified (see deviations) |

## Acceptance Criteria

- [x] AC1 pure estimate (`test_estimate_table`, `test_is_pure`)
- [x] AC2 null usage + estimate: flag, no split, unsplit charge (`test_null_usage_estimates_against_stub`, `test_unsplit_tokens_grows_by_exactly_the_estimate`)
- [x] AC3 D8 table, both modes, legacy messages unchanged (`test_d8_table_estimate_mode`, `test_d8_table_error_mode_raises_todays_message`, `test_total_present_unchanged`)
- [x] AC4 audit row flagged / error row 0 (`test_row_is_flagged_with_null_split`, `test_upstream_error_row_not_flagged`)
- [x] AC5 `/v1` body (`test_estimated_usage_body`, `test_reported_usage_body_has_no_usage_estimated_key`, `test_http_bodies`)
