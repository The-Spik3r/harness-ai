---
story: STORY-005
prd: PRD-010
plan: .agents/plans/PRD-010-multi-turn-pipeline/completed/STORY-005-generation-params-timeout-and-null-content.plan.md
epic_branch: epic/PRD-010-multi-turn-pipeline
commit: 4914674
status: COMPLETE
completed: 2026-09-17
---

# Implementation Report — STORY-005: GenerationParams allowlist, configurable timeout and explicit null-content error

**Plan**: `.agents/plans/PRD-010-multi-turn-pipeline/completed/STORY-005-generation-params-timeout-and-null-content.plan.md`
**Epic Branch**: `epic/PRD-010-multi-turn-pipeline`
**Commit**: `4914674`

## Summary

`app/services/openrouter_client.py` gained a frozen `GenerationParams(temperature, max_tokens, top_p, stop)` dataclass whose `__post_init__` range-validates every field and raises `UnsupportedParameterError` (bool explicitly rejected for `max_tokens`, since `bool` subclasses `int`), plus `GenerationParams.from_mapping(raw)` — PRD-014's future entry point — which rejects any key outside the four-field allowlist, naming every unsupported key sorted. `call_openrouter` gained `params: Optional[GenerationParams] = None`; only non-`None` fields reach the payload, so `params=None` (every current caller) still produces today's exact byte-identical payload. The module constant `_TIMEOUT_SECONDS = 30.0` was removed; the default `httpx.Client` now reads `settings.OPENROUTER_TIMEOUT_SECONDS` inside the function body, so it can be monkeypatched per call. A `choices[0].message.content is None` response now raises an explicit `OpenRouterError("OpenRouter returned no text content (finish_reason=<value>)")`, naming PRD-016 when `tool_calls` is present, instead of falling through to an unrelated "unexpected response shape" `KeyError`. Neither message ever contains the resolved API key. The router's existing generic `OpenRouterError` → 502 mapping needed no code change; one new test pins that this specific error shape still maps to 502.

This story touched only the client — `query_pipeline.py` and `app/routers/query.py` are unchanged, matching the story's Technical Notes ("This story adds no pipeline change").

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | `GenerationParams`, `UnsupportedParameterError`, `from_mapping` added | `app/services/openrouter_client.py` | ✅ |
| 2 | `call_openrouter` gains `params`; timeout from settings; explicit null-content error | `app/services/openrouter_client.py` | ✅ |
| 3 | Updated STORY-003 timeout characterization test with required comment; added monkeypatched-timeout test (AC4) | `tests/test_openrouter_client.py` | ✅ |
| 4 | Added `GenerationParams`/`from_mapping`/`UnsupportedParameterError` tests (allowlist, ranges, before-any-HTTP-call, params-in-payload) | `tests/test_openrouter_client.py` | ✅ |
| 5 | Added null-content tests (plain, with `tool_calls`, without `tool_calls`, api-key-absence) | `tests/test_openrouter_client.py` | ✅ |
| 6 | Added router-level 502 mapping test for the null-content error shape | `tests/test_query_router.py` | ✅ |
| 7 | Full suite validated green | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`app.main`, `openrouter_client`) | ✅ |
| `tests/test_openrouter_client.py` | ✅ (30 passed) |
| `tests/test_query_router.py` | ✅ (38 passed) |
| Full suite (`pytest -q`) | ✅ (2052 passed, 25 skipped, 1 unrelated infra error — see Deviations) |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/services/openrouter_client.py` | UPDATE | +99/-7 |
| `tests/test_openrouter_client.py` | UPDATE | +153/-3 |
| `tests/test_query_router.py` | UPDATE | +18 |
| `.agents/plans/PRD-010-multi-turn-pipeline/completed/STORY-005-generation-params-timeout-and-null-content.plan.md` | CREATE (archived) | +495 |

## Deviations from Plan

None in the implementation itself — all 7 tasks landed exactly as planned.

One infra note surfaced during full-suite validation, unrelated to this story's code: the first full run showed 4 failed + 5 errors, all confined to `tests/test_two_instance_smoke.py` (session listing, transcript read-back, ownership checks — none touching `openrouter_client.py`). This matched the repo's documented libSQL dev-server staleness pattern (PRD-010 Section 11: "mass fixture errors mean restart the container, not bisect code"). Restarting the local `harness-libsql-dev` Docker container and re-running `test_two_instance_smoke.py` alone: 10/10 passed. A second full-suite run then showed 2052 passed with a single remaining error — a `SQLITE_BUSY` ("database is locked") failure in a concurrent two-instance test, a known limitation of the local dev server under concurrent access, not a regression from this story. This story's own tests (`test_openrouter_client.py`, `test_query_router.py`) were green in both runs.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_openrouter_client.py` | `test_timeout_setting_is_read_per_call_not_cached_at_import`, `test_from_mapping_rejects_unsupported_keys_named_and_sorted`, `test_from_mapping_builds_only_allowed_fields`, `test_out_of_range_params_raise_naming_field_and_range` (parametrized: temperature=3, top_p=0, max_tokens=0, max_tokens=True, stop with 5 sequences, stop with a non-str element), `test_invalid_params_raise_before_any_http_call`, `test_params_only_non_none_fields_reach_the_payload`, `test_params_none_leaves_payload_byte_identical_to_story_003`, `test_null_content_raises_with_finish_reason`, `test_null_content_with_tool_calls_names_prd_016`, `test_null_content_without_tool_calls_omits_prd_016_note`, `test_null_content_error_never_contains_api_key` |
| `tests/test_query_router.py` | `test_null_content_openrouter_error_maps_to_502` |

## Acceptance Criteria

- [x] `openrouter_client.py` defines a frozen `GenerationParams(temperature, max_tokens, top_p, stop)` (all `Optional`, default `None`), `UnsupportedParameterError`, and `GenerationParams.from_mapping(raw)`; `call_openrouter` gains `params: Optional[GenerationParams] = None`, payload includes only non-`None` fields
- [x] `from_mapping({"logit_bias": {}, "tools": [], "stream": True, "temperature": 0.2})` raises `UnsupportedParameterError` naming all three unsupported keys, sorted; `temperature=3`, `top_p=0`, `max_tokens=0`/`True`, or `stop` with 5 sequences or a non-`str` element each raise before any HTTP call
- [x] `params=None` with one user message keeps STORY-003's characterization assertion byte for byte
- [x] `settings.OPENROUTER_TIMEOUT_SECONDS` (monkeypatched) drives the default `httpx.Client`'s `timeout=`; `_TIMEOUT_SECONDS` constant removed; STORY-003's assertion updated with the required comment
- [x] `content is None` raises `OpenRouterError("OpenRouter returned no text content (finish_reason=<value>)")`, naming tool calls (PRD-016) when present; maps to 502 through `POST /query`; API key never appears in either message
- [x] All tasks completed
- [x] Full suite passes (this story's scope green; one unrelated, documented infra flake — see Deviations)
- [x] Follows existing patterns
