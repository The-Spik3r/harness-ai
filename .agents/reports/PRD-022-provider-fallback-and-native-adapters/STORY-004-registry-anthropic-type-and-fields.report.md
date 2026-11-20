---
story: STORY-004
prd: PRD-022
plan: .agents/plans/PRD-022-provider-fallback-and-native-adapters/completed/STORY-004-registry-anthropic-type-and-fields.plan.md
epic_branch: epic/PRD-022-provider-fallback-and-native-adapters
commit: 324c142
status: COMPLETE
completed: 2026-11-20
---

# Implementation Report — STORY-004: Registry type anthropic and catalogue fields

## Summary

`TYPES` gains `anthropic`; capabilities gain `forced_tool_choice` / `sampling_params`; models gain `default_max_tokens` and `prompt_cache` (all defaulted, so legacy and openai_compatible are unchanged). The hard-coded `type="openai_compatible"` in `_parse_provider` now uses the parsed type. `passthrough: true` and a missing `default_max_tokens` are refused for anthropic. `upstream/__init__.py` dispatches adapters by provider type; the `anthropic` entry raises `UpstreamError(kind="incompatible")` until STORY-005.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Vocabulary, dataclasses, parsers, type rules | `app/services/provider_registry.py` | done |
| 2 | `_ADAPTER_FACTORIES` / `_build_adapter`, anthropic stub | `app/services/upstream/__init__.py` | done |
| 3 | Registry and seam tests | `tests/test_provider_registry.py`, `tests/test_stream_upstream_seam.py` | done |
| 4 | Example comment | `examples/providers.yaml` | done |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| Targeted tests (registry, routing, seam, adapter, untouched_app, providers_docs) | 256 passed, 0 failed, 0 skipped |
| Full suite | GitHub CI on push (user decision) |

## Deviations from Plan

- The unknown-type `_BAD` row is split into three rows (message, plus one per type name) because `_choice` prints the allowed set via `_allowed`; both names are asserted separately instead of one guessed fragment.
- Also ran `tests/test_providers_docs.py` (touches `examples/providers.yaml`).

## Tests Written

Registry: `_BAD` rows (unknown type names the set, missing/invalid `default_max_tokens`, bad `prompt_cache`, anthropic passthrough); anthropic loads with all fields and is frozen; names-test; mixed registry; openai_compatible defaults. Seam: `call_upstream` / `stream_upstream` anthropic `incompatible` (not retryable, not fallback-eligible, no prompt text); keyless anthropic is `misconfigured`; openai_compatible factory built once per call with `(provider, client)`.

## Acceptance Criteria

- [x] AC1 type anthropic accepted; unknown type names the allowed set
- [x] AC2 new fields parse, frozen, invalid values refused
- [x] AC3 missing `default_max_tokens` names file/provider/model/rule; passthrough refused; `usage_missing` accepted
- [x] AC4 dispatch by type; anthropic `incompatible`; openai_compatible unchanged
- [x] AC5 legacy defaults
