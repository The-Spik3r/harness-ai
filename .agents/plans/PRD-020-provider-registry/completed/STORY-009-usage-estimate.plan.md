---
story: STORY-009
prd: PRD-020
slug: usage-estimate
title: Estimate usage when a provider reports none
type: NEW_CAPABILITY
complexity: medium
epic_branch: epic/PRD-020-provider-registry
created: 2026-11-18
---

# Plan: Estimate usage when a provider reports none

## Summary

A pure `usage_estimate.estimate_tokens` plus the D8 table applied inside `OpenAICompatibleAdapter.complete` (the `usage` block, `openai_compatible.py:192-201`). `UpstreamResult` gains `usage_estimated`. The pipeline only forwards the flag into the success audit rows (step 7b is untouched: a None split already lands in `unsplit_tokens`). `/v1` emits `harness.usage_estimated: true` only when true.

- Story: `.agents/stories/PRD-020-provider-registry/STORY-009-usage-estimate.md`
- PRD sections: 6.7, F5, 10 (`/v1/chat/completions`), D8, O7
- Systems: upstream adapter/types, new pure module, query_pipeline (2 log_query calls), v1 schema + translate, tests

## Design Decisions (orchestrator's binding points, plus the shapes this plan names)

- **`app/services/usage_estimate.py`**: imports `math`, `json` only; no settings, no `app` import (duck-typed on `.content`, `.tool_calls[*].arguments`). Signature `estimate_tokens(sent: Sequence[Message], received: tuple[str, Sequence[ToolCallSpec]], chars_per_token: float, *, tools: Optional[Sequence[Mapping]] = None) -> int` (annotate with `TYPE_CHECKING` imports or Protocols; no runtime import of `app`).
  - `sent`: the Messages actually sent upstream (`request.messages`); per message `len(content or "")` (None counts 0) + `len(c.arguments)` over `tool_calls`.
  - `received`: a 2-tuple `(content, tool_calls)` = `(response text, tuple[ToolCallSpec, ...])`. STORY-013 builds it from a collected stream; no dependency on `UpstreamResult`.
  - `tools`: the list sent (`ToolParams.tools`, `openai_compatible.py:128`), counted as `len(json.dumps(tools, sort_keys=True, ensure_ascii=False))` (default separators; stable key order; non-ASCII counted as characters like `len(content)`). None adds 0; an empty list is `[]` = 2 chars (it was sent).
  - `return ceil(sent_chars / cpt) + ceil(received_chars / cpt)`; `ValueError` if `cpt <= 0`.
- **`UpstreamResult.usage_estimated: bool = False`**, last field (`upstream/types.py`, after `tool_calls`), commented like its siblings (default keeps old construction working).
- **D8 in `complete`**, replacing the try block at `openai_compatible.py:192-201`; reads `provider.usage_missing` and `provider.estimate_chars_per_token` (`provider_registry.py:123-124`). `usage` is "absent" when the key is missing, `null`, or not a `Mapping`. A total is "present" when `"total_tokens"` is in the object.

  | case | `error` (legacy) | `estimate` |
  |---|---|---|
  | total present | today, raw value, `_token_count` splits (byte-identical) | total valid per `_token_count`: same; a junk total (None, str, bool, <0) counts as no total |
  | no total, both splits `_token_count`-valid | raise | total = sum, splits kept, `usage_estimated=False` |
  | no total, 0 or 1 valid split; or usage absent/null/non-object | raise | estimate, splits None, `usage_estimated=True` (a lone split is discarded: D8 says split NULL) |

  Legacy raise text is `f"{label} returned an unexpected response shape: {x}"` (today's, `:196-198`) with `x` = `'usage'` when the key is missing (today's `KeyError` text) and `'total_tokens'` when the object lacks it (today's text). New in legacy: `null`/non-object usage (today a bare `TypeError` at `:194`) raises the same message with `'usage'`; this wording is chosen by the plan.
- **Pipeline**: success rows only, `usage_estimated=openrouter_result.usage_estimated` in the output-redaction-error arm (`query_pipeline.py:934-943`) and the success arm (`:980-989`). Upstream-error and pre-upstream rows keep the default 0. Step 7b (`:884-890`) unchanged. Do not touch the `**_route_fields(route),` or `pii_input_relaxed=relaxed,` lines (source guards in `tests/test_query_pipeline_routing.py` and `tests/test_query_pipeline_pii_relaxation.py`); add the kwarg on its own line after `output_tokens=`.
- **`/v1` serialization mechanism**: exclude-if-False inside the existing wrap serializer. `HarnessCompletionInfo` (`v1_schemas.py:175`) gains `usage_estimated: bool = False` after `actions`; `_drop_absent_actions` (`v1_schemas.py:192-197`) also does `if not data.get("usage_estimated"): data.pop("usage_estimated", None)`. The object is built at `v1_translate.py:652-658` and serialized wherever the completion is dumped, through that serializer. Reported bodies stay byte-identical; when true the key is last in `harness`. `translate_result` passes `usage_estimated=upstream.usage_estimated` (`upstream` is `upstream.result`, `routers/v1.py:296`). `usage` already reports `0/0/total` for a None split (`v1_translate.py:625-626`, `:647-651`).
- The pipeline never estimates; `call_openrouter`/`call_upstream` signatures unchanged (D12).

## Skills In Use

None (`.agents/skills/` holds only `frontend-design`).

## Patterns to Follow

| Category | Source | Mirror |
|---|---|---|
| Pure module + purity AST test | `tests/test_v1_translate_request.py::test_is_pure` | import allow-list test for `usage_estimate` |
| Adapter tests | `tests/test_upstream_adapter.py:35-55` (`_FakeClient`, `_response(body=)`), `:263-270` (`_local`) | absent / non-object usage via `_FakeClient`; `null` via the stub (`scripts/stub_openrouter.py:40`, `tests/test_stub_openrouter.py:764`). The stub always emits `total_tokens` (default sum), so "no total" cases use `_FakeClient` bodies |
| File-mode registry | `tests/_providers.py:40-50`; YAML at `tests/test_query_pipeline_routing.py:100-125` | add `usage_missing: error\|estimate` to the YAML |
| Charge assertions | `tests/test_query_pipeline_usage_limits.py:147-170` (`_unsplit_answer`, `_today`) | `unsplit_tokens` delta |
| Pipeline file-mode | `tests/test_query_pipeline_pii_relaxation.py:1-60` | imports, autouse fixtures, `_audit_rows_since` |
| `/v1` body | `tests/test_v1_translate_result.py:60-100` (`_success`, `_upstream`, `_dump`) | estimated vs reported dump |

## Files to Change

| File | Action | Purpose |
|---|---|---|
| `app/services/usage_estimate.py` | CREATE | pure `estimate_tokens` |
| `app/services/upstream/types.py` | UPDATE | `usage_estimated` field |
| `app/services/upstream/openai_compatible.py` | UPDATE | D8 table in `complete` |
| `app/services/query_pipeline.py` | UPDATE | forward the flag to the two post-upstream rows |
| `app/models/v1_schemas.py` | UPDATE | field + serializer drop-if-False |
| `app/services/v1_translate.py` | UPDATE | pass the flag (`:652-658`) |
| `tests/test_usage_estimate.py` | CREATE | pure table tests + purity |
| `tests/test_usage_estimate_adapter.py` | CREATE | adapter D8 table, both `usage_missing` values |
| `tests/test_query_pipeline_usage_estimate.py` | CREATE | pipeline charge + audit row |
| `tests/test_v1_translate_result.py` | UPDATE | estimated and reported bodies |
| `tests/test_upstream_adapter.py` | UPDATE | `:267-270` (see risks) |

## Tasks

1. **Create `usage_estimate.py`** per Design Decisions. Docstring cites PRD-020 6.7 / D8 / O7, in the style of `upstream/types.py:1-7`. Validate: `tests/test_usage_estimate.py`.
2. **`UpstreamResult.usage_estimated`** (`types.py`, last field, default False).
3. **Adapter**: module helper `_resolve_usage(provider, label, data, content, calls, request) -> tuple[int, Optional[int], Optional[int], bool]` called in place of `:192-201`. `usage_missing == "error"` keeps today's code path bit for bit for dict usages. Estimate mode calls `estimate_tokens(request.messages, (content, calls), provider.estimate_chars_per_token, tools=tools.tools if tools else None)` (content is already `""` for call-only replies, `:178-179`). Import `usage_estimate` at module top (pure, no cycle). Pass `usage_estimated` into the returned `UpstreamResult` (`:206-214`).
4. **Pipeline**: add `usage_estimated=openrouter_result.usage_estimated,` after `output_tokens=` in the two log_query calls. `log_query` already accepts it (`database.py:1584`, entry field `models.py:547`).
5. **`/v1`**: schema field + serializer (`v1_schemas.py:175-197`); `translate_result` kwarg.
6. **Tests** per the AC table. Pure cases: ascii, empty strings (`[]`/`""` -> 0), None content, multi-byte (counts chars), history `tool_calls` arguments, response tool_calls, tools present/absent/empty list, dict key order irrelevant, cpt 4 vs 3 vs 2.5 with ceil per side (5 sent + 5 received at 4 = 2+2, not 3), `cpt<=0` raises, inputs not mutated, AST import allow-list `{math, json}` plus `typing`/`__future__`.
7. **Fix existing test** `test_upstream_adapter.py:267-270` (see risks).

## End-to-End Tests

- [ ] File-mode YAML (stub on a free port, `usage_missing: estimate`, `"usage": null` reply), `TestClient` on `POST /query` and `POST /v1/chat/completions`: `/query` body unchanged; audit row `usage_estimated=1`, split NULL, `tokens_used` = estimate; `/v1` body has `usage` 0/0/N and `harness.usage_estimated: true`.
- [ ] Same with reported usage: no `usage_estimated` key anywhere in the body.
- [ ] `tests/test_prd020_legacy_fixtures.py` stays green, unedited.

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_usage_estimate.py tests/test_usage_estimate_adapter.py tests/test_query_pipeline_usage_estimate.py tests/test_v1_translate_result.py tests/test_v1_schemas.py tests/test_upstream_adapter.py tests/test_query_pipeline_routing.py tests/test_query_pipeline_pii_relaxation.py tests/test_query_pipeline_usage_limits.py tests/test_prd020_legacy_fixtures.py tests/test_untouched_app.py
```

## Acceptance Criteria -> Tasks -> Tests

| AC | Task | Test |
|---|---|---|
| AC1 pure estimate, ceil per side, tools, empties | 1 | `test_usage_estimate.py::test_estimate_table`, `::test_is_pure` |
| AC2 `usage:null` + estimate: flag, no split, `unsplit_tokens` += estimate | 3, 4 | `test_usage_estimate_adapter.py::test_null_usage_estimates_against_stub`; `test_query_pipeline_usage_estimate.py::test_unsplit_tokens_grows_by_exactly_the_estimate` |
| AC3 D8 table, both modes, legacy message unchanged | 3 | `test_usage_estimate_adapter.py::test_d8_table` (absent, null, non-object, no total + both splits, no total + one split, junk total; x `estimate`/`error`), `::test_total_present_unchanged` |
| AC4 row `usage_estimated=1`, tokens = estimate, split NULL (0 on error/pre-upstream rows) | 4 | `test_query_pipeline_usage_estimate.py::test_row_is_flagged_with_null_split`, `::test_upstream_error_row_not_flagged` |
| AC5 `/v1` `0/0/estimate` + `harness.usage_estimated` only when true | 5 | `test_v1_translate_result.py::test_estimated_usage_body`, `::test_reported_usage_body_has_no_usage_estimated_key` (byte-equal to today's dump) |

## Risks / notes

- `tests/test_upstream_adapter.py:267-270` asserts a missing `usage` raises under a file-mode default provider; the file default is now `estimate` (PRD 6.7), so that call estimates. Change the assertion to expect an estimated result, with a comment citing PRD-020 D8 (STORY-009), and keep the raise case in the new adapter test with `usage_missing: error`. Not a rename: no `_DELIBERATELY_SUPERSEDED_TESTS` entry.
- A junk (non-int) `total_tokens` is validated only in estimate mode; legacy keeps the raw value (D1).
- The legacy text for `null`/non-object usage is the plan's choice (`'usage'`); the story fixes only the key-missing texts.
- The stub cannot omit `usage` or `total_tokens`; hence `_FakeClient` for those cases.
- Out of scope: STORY-010 (D9 max_context), STORY-013 (streaming usage chunk).
