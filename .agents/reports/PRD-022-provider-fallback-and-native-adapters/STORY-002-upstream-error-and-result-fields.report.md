---
story: STORY-002
prd: PRD-022
plan: .agents/plans/PRD-022-provider-fallback-and-native-adapters/completed/STORY-002-upstream-error-and-result-fields.plan.md
epic_branch: epic/PRD-022-provider-fallback-and-native-adapters
commit: cab7b16
status: COMPLETE
completed: 2026-11-20
---

# Implementation Report — STORY-002: UpstreamError kind/provider/retry_after, ChainExhausted, cache fields

**Plan**: `.agents/plans/PRD-022-provider-fallback-and-native-adapters/completed/STORY-002-upstream-error-and-result-fields.plan.md`
**Epic Branch**: `epic/PRD-022-provider-fallback-and-native-adapters`
**Commit**: `cab7b16`

## Summary

`UpstreamError` gained keyword-only `provider`, `kind` (closed `UPSTREAM_ERROR_KINDS`, validated), `retry_after_seconds` and a read-only `fallback_eligible`. `ChainExhausted` subclasses it and is exported from `app.services.upstream`. `UsageReport` and `UpstreamResult` gained defaulted cache/reasoning fields; `collect()` copies the cache pair. The OpenAI-compatible adapter tags every error it builds; shape errors are tagged at the `result_from_reply` boundary and around the stream parse loop. No message, status or `retryable` value changed.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | kinds, UpstreamError fields, ChainExhausted, tag_shape, result fields | `app/services/upstream/types.py` | done |
| 2 | shape tagging at the reply boundary | `app/services/upstream/reply.py` | done |
| 3 | kind/provider/retry-after classification | `app/services/upstream/openai_compatible.py` | done |
| 4 | export, missing-key `misconfigured` | `app/services/upstream/__init__.py` | done |
| 5 | cache pair copied in `collect()` | `app/services/upstream/collect.py` | done |
| 6 | tests | `tests/test_upstream_error_fields.py` | done |

## Deviations from Plan

Two pre-existing field-list guards had to be extended for the new result fields (additive, following the PRD-020 STORY-009 precedent, each with a PRD-022 comment): `tests/test_openrouter_client.py::test_the_split_fields_are_declared_last_and_in_order` and `tests/test_prd020_legacy_fixtures.py::test_success_result_fields_match_recorded` (pops the three new defaults before comparing with the recorded legacy bytes). Recorded fixtures are unchanged. `reply.result_from_reply` was split into a wrapper plus `_result_from_reply` to tag shape errors.

## Acceptance Criteria

- [x] AC1 defaults, `str`, alias, `/v1` mapping intact
- [x] AC2 vocabulary and `fallback_eligible`
- [x] AC3 adapter kind/provider/retry-after (complete and stream)
- [x] AC4 `ChainExhausted`
- [x] AC5 result fields and collect copy
