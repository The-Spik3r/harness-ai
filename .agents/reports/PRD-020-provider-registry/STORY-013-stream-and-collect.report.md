---
story: STORY-013
prd: PRD-020
plan: .agents/plans/PRD-020-provider-registry/completed/STORY-013-stream-and-collect.plan.md
epic_branch: epic/PRD-020-provider-registry
commit: pending
status: COMPLETE
completed: 2026-11-18
---

# Implementation Report — STORY-013: Adapter stream() with normalized events and pure collect()

**Plan**: `.agents/plans/PRD-020-provider-registry/completed/STORY-013-stream-and-collect.plan.md`
**Epic Branch**: `epic/PRD-020-provider-registry`
**Commit**: `pending`

## Summary

`complete()` was split into shared pieces (`_headers`, `_payload`, `_open_client`, `_raise_for_response`, `_http_error`, and `result_from_reply`). `stream()` is a lazy sync generator over a pure SSE parser (`sse.py`) that yields frozen-dataclass events. `collect(events, *, provider, request)` folds the events into a reply dict shaped like the non-stream body and calls `result_from_reply`, so both paths share one set of rules and message texts. The stub answers SSE when the body carries `"stream": true`. No production caller of `stream()`; `call_upstream` is untouched.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Event types, `ProviderAdapter.stream` | `app/services/upstream/types.py` | done |
| 2 | Helpers moved, `result_from_reply` | `app/services/upstream/reply.py` | done |
| 3 | `complete()` on shared helpers | `app/services/upstream/openai_compatible.py` | done |
| 4 | SSE parser | `app/services/upstream/sse.py` | done |
| 5 | Pure `collect` | `app/services/upstream/collect.py` | done |
| 6 | `stream()` | `app/services/upstream/openai_compatible.py` | done |
| 7 | Exports | `app/services/upstream/__init__.py` | done |
| 8 | Stub SSE, `stream=yes\|no` log | `scripts/stub_openrouter.py` | done |
| 9 | Tests | `tests/test_upstream_stream_collect.py`, `tests/test_stub_openrouter.py` | done |
| 10 | PRD 6.4 amendment | `.agents/PRDs/PRD-020-provider-registry/PRD.md` | done |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| Tests (targeted, one pytest process) | 364 passed, 0 failed, 0 skipped |
| E2E (real stub on a free port, both paths) | covered by the property test |
| Full suite | GitHub CI on push (user decision) |

Targeted files: `test_upstream_stream_collect.py`, `test_stub_openrouter.py`, `test_upstream_adapter.py`, `test_openrouter_client.py`, `test_usage_estimate.py`, `test_usage_estimate_adapter.py`, `test_query_pipeline_usage_estimate.py`, `test_prd020_legacy_fixtures.py`, `test_e2e_cline_script.py`, `test_e2e_opencode_script.py`, `test_untouched_app.py`. Existing `complete()` tests and the legacy fixtures pass unmodified.

## Deviations from Plan

- Per the orchestrator: `_token_count`, `_parse_tool_calls`, `_resolve_usage` and the new `result_from_reply` live in the pure `upstream/reply.py`, not in `openai_compatible.py` (design point 2's file placement), so `collect` imports no httpx. `openai_compatible.py` re-imports the names. `reply.py` and `collect.py` import `Provider` only under `TYPE_CHECKING` (the registry imports `settings`).
- PRD 6.4 and the In Scope bullet amended: `collect(events, *, provider, request)`.
- Duplicate call ids cannot be scripted in the stub (it refuses them), so that rule is proved by a direct `collect` unit test, not by the script property.
- Property test uses a shared injected `httpx.Client` and two stubs fed the same request order (generated `call_<n>` ids stay in step); building a client per call took ~30 s per run.
- The stub sets `disable_nagle_algorithm = True` (one small write per SSE frame). It did not change timing here; kept as harmless.

## Known divergence (flagged, not a stub case)

A real provider sending `total_tokens: null` with `usage_missing: error`: `complete()` returns the raw None, `collect` treats null as absent and raises "'total_tokens'". Documented in `collect`'s docstring.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_upstream_stream_collect.py` | `test_collect_of_stream_equals_complete` (67 replies x legacy/estimate x with/without tools: every e2e script rule, cline/opencode `render_script`, inline edge cases, fail/redirect), collect assembly/D8/D13/duplicate id/unknown event, 12 malformed-stream cases, HTTP and redirect classification, mid-stream transport error, comment/blank-line handling, laziness, `test_payload_keys`, AST purity of `collect.py`/`reply.py`/`sse.py`, close behaviour (owned vs injected client, early close, error) |
| `tests/test_stub_openrouter.py` | `test_stream_log_field`, `test_sse_body_shape`, usage chunk only with `include_usage`, two fragments per tool call, non-stream unchanged, streaming failure and no header value logged |

## Acceptance Criteria

- [x] AC1 `stream()` sends both keys and yields events; `complete()` no `stream` key (`test_payload_keys`)
- [x] AC2 stub SSE + `stream=yes|no` (`test_stream_log_field`, `test_sse_body_shape`)
- [x] AC3 `collect` pure and applies `complete()`'s rules and D8 (AST purity test, collect unit tests, property)
- [x] AC4 `collect(stream(r)) == complete(r)` (`test_collect_of_stream_equals_complete`)
- [x] AC5 malformed streams (`test_malformed_stream_names_the_field_and_is_not_retryable`)
