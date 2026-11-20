---
story: STORY-005
prd: PRD-022
plan: .agents/plans/PRD-022-provider-fallback-and-native-adapters/completed/STORY-005-anthropic-adapter-complete.plan.md
epic_branch: epic/PRD-022-provider-fallback-and-native-adapters
commit: pending
status: COMPLETE
completed: 2026-11-20
---

# Implementation Report — STORY-005: AnthropicAdapter.complete()

## Summary

New `app/services/upstream/anthropic.py`: pure `build_request`, `dropped_params`, `map_response`, SDK error mapping (`_sdk_error`), `_open_sdk_client` and `AnthropicAdapter` (`complete()` real, `stream()` raises `incompatible`, STORY-007). Registered in `_ADAPTER_FACTORIES`, replacing `_anthropic_unavailable`. `UpstreamResult.dropped_params` and `UpstreamRequest.model` added (both defaulted, last). Orchestrator corrections applied: thinking + forced `tool_choice` is `incompatible` before the network; an empty user turn keeps its empty text block.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Two defaulted fields | `app/services/upstream/types.py` | done |
| 2-3 | Mapping, errors, adapter | `app/services/upstream/anthropic.py` | done |
| 4 | Register, `model=route.model` at both seam sites, export | `app/services/upstream/__init__.py` | done |
| 5 | STORY-004 dispatch test replaced | `tests/test_stream_upstream_seam.py`, `tests/test_pii_redaction_integration.py` | done |
| 6 | Adapter tests | `tests/test_anthropic_adapter.py` | done |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| Targeted tests (anthropic adapter, seam, upstream adapter/error fields/collect, spike, v1_translate_request, untouched_app, pii integration, legacy fixtures, openrouter client) | 1056 passed + 127 (openrouter client rerun after fix); 0 failed after fixes |
| Full suite | GitHub CI on push (user decision) |

## Deviations from Plan

- Adding `UpstreamResult.dropped_params` broke three field-order/recorded-field guards, updated with PRD-022 STORY-005 comments following the STORY-002 precedent: `tests/test_upstream_error_fields.py::test_result_and_usage_defaults`, `tests/test_prd020_legacy_fixtures.py::test_success_result_fields_match_recorded` (pops the new field like the other new ones; recorded bytes unchanged), `tests/test_openrouter_client.py::test_the_split_fields_are_declared_last_and_in_order`.
- The plan's large-`max_tokens` test was reworked into a real call against the loopback stub (the SDK guard is skipped when a timeout is explicit).
- `complete()` raises the mapped error `from None` (the SDK exception text can quote the body, T10), and an owned client with no key raises `misconfigured` without building a client.

## Tests Written

`tests/test_anthropic_adapter.py` (81 tests): request rows, T9 allowlist subset and exact set, incompatible cases (including thinking + forced choice), response mapping, stop reasons, usage/cache sums, dropped params, SDK error table, retry-after, key/body never in errors, client construction (patched and real), close semantics, `stream()` incompatible, two loopback real-SDK tests.

## Acceptance Criteria

- [x] AC1 request table + allowlist
- [x] AC2 incompatible before the network
- [x] AC3 response mapping, tokens, shape errors
- [x] AC4 SDK error mapping, label, no key
- [x] AC5 dropped params, cache_control, construction, no network
