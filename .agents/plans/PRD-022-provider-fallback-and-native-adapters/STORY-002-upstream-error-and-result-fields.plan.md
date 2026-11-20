---
story: STORY-002
prd: PRD-022
slug: upstream-error-and-result-fields
title: UpstreamError kind/provider/retry_after + fallback_eligible, ChainExhausted, cache fields on results
type: ENHANCEMENT
complexity: medium
epic_branch: epic/PRD-022-provider-fallback-and-native-adapters
created: 2026-11-20
---

# Plan: UpstreamError extension, ChainExhausted, cache fields on results

## Summary

Additive, behaviour-neutral extension of `app/services/upstream/types.py`: `UpstreamError` gains keyword-only `provider`, `kind` (validated against a closed tuple), `retry_after_seconds` and a read-only `fallback_eligible`; `ChainExhausted` subclasses it; `UsageReport`/`UpstreamResult` gain defaulted cache/reasoning fields. The OpenAI-compatible adapter (and the shape-error sites it reaches) tag `kind`/`provider` where errors are already built; no message, status or `retryable` changes. No producer sets the cache fields yet.

- Story: `.agents/stories/PRD-022-provider-fallback-and-native-adapters/STORY-002-upstream-error-and-result-fields.md`
- PRD sections used: 6.2, F1, F7, D11, Section 4 "Errors and result"
- Systems affected: `app/services/upstream/` only. `/v1` (`app/routers/v1.py:290-306`, `_fault_code` uses `isinstance(exc, OpenRouterError)` + `.retryable`) needs NO change; verified by reading.

## Design Decisions (binding, from orchestrator)

- `UpstreamError.__init__(self, message, *, upstream_status=None, retryable=False, provider=None, kind=None, retry_after_seconds=None)`. Only `message` is positional, so `str(exc)` is unchanged (`types.py:26-35`).
- Module-level `UPSTREAM_ERROR_KINDS = ("timeout","transport","status","shape","refusal","incompatible","misconfigured","exhausted")`; `kind` outside it (None allowed) raises `ValueError` naming the bad value and the tuple.
- `fallback_eligible` read-only `@property`: `self.retryable or self.kind == "misconfigured"` (PRD 6.2). 401 stays `retryable=False`.
- `ChainExhausted(UpstreamError)` in `types.py`: `__init__(self, skipped=(), *, last_error=None, retry_after_seconds=None)`; calls `super().__init__("all providers unavailable", upstream_status=None, retryable=True, provider=None, kind="exhausted", retry_after_seconds=...)`; attrs `skipped: tuple[tuple[str, str], ...]` (coerce with `tuple(tuple(p) for p in skipped)`), `last_error: Optional[UpstreamError]`. Exported from `upstream/__init__.py` (import + `__all__`); aliased nowhere else. `v1_translate.py` is untouched.
- Result fields: `UsageReport` + `cache_read_tokens: Optional[int]=None`, `cache_write_tokens: Optional[int]=None` (last, after `total_tokens`, `types.py:98`). `UpstreamResult` + those two + `reasoning_blocks: int = 0`, declared last (after `usage_estimated`, `types.py:59`). `collect()` copies the cache pair from the usage it already selects.
- Classification (OpenAI-compatible): timeout->`timeout`, other transport->`transport`, 5xx/429/other 4xx->`status`, 401->`misconfigured`, malformed/shape->`shape`; `provider=provider.name`. 429 parses the `retry-after` header: digits-only integer seconds, `max(1, n)`; HTTP-date/invalid/absent -> None. Errors before a provider is known keep `kind=None` (empty messages, no route); a missing configured key is `kind="misconfigured"`, `provider=provider.name`.
- No change to any message, status or `retryable` value; existing tests pass unmodified.

## Skills In Use

None apply (`.agents/skills/` holds only `frontend-design`; story `skills: []`).

## Patterns to Follow

| Category | Source | What to mirror |
|----------|--------|----------------|
| Defaulted trailing fields | `types.py:44-59` | A "PRD-0xx STORY-nnn ... Declared last with a default" comment per field; cite PRD-022 D11 |
| Classification | `openai_compatible.py:54-63` `_classify_http_error` | Keep the `(status, retryable)` signature; add a sibling `_classify_kind(exc)` instead of widening the tuple |
| Error build site | `openai_compatible.py:133-140` `_http_error` (static, takes `label`) | Take the `Provider` instead; callers at `:155`, `:212` |
| Redirect error | `openai_compatible.py:121-131` `_raise_for_response(resp, label)` | Needs `kind="status"`, `provider`: pass the provider (callers `:153`, `:196`) |
| Collect usage select | `collect.py:67-76` | Extend the `UsageReport` branch to also keep the cache pair |
| Adapter tests | `tests/test_upstream_adapter.py:39-57,254-275`; `tests/test_upstream_stream_collect.py:50-55,105-117,293-345` (`_provider()`, `_mock_client`, `_stream_events`, `_error_of`) | httpx MockTransport style, status/exception parametrization |
| /v1 mapping | `tests/test_v1_errors.py:628-629` | `(OpenRouterError(..., retryable=...), code)` rows |

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/upstream/types.py` | UPDATE | `UPSTREAM_ERROR_KINDS`, `UpstreamError` fields/property, `ChainExhausted`, `tag_shape` helper, result/usage fields |
| `app/services/upstream/__init__.py` | UPDATE | export `ChainExhausted`; tag the missing-key error (`:80`) |
| `app/services/upstream/openai_compatible.py` | UPDATE | `kind`/`provider`/`retry_after_seconds` on every error it builds; tag shape errors in `stream()` |
| `app/services/upstream/reply.py` | UPDATE | tag shape errors at the `result_from_reply` boundary |
| `app/services/upstream/collect.py` | UPDATE | keep and copy the cache pair |
| `tests/test_upstream_error_fields.py` | CREATE | all new tests; no pre-existing test modified |

## Tasks

### Task 1: types.py
- **Implement**: the tuple; `UpstreamError` (validate `kind` before assigning; docstring gains a PRD-022 D11 / 6.2 note: `kind` and status only, never body text, T10); `fallback_eligible` property; `ChainExhausted`; the new defaulted fields; helper `tag_shape(exc, provider_name)` (if `exc.kind is None`: set `kind="shape"`, `provider`; return exc).
- **Mirror**: `types.py:15-35`, `:44-59`
- **Validate**: `.venv/Scripts/python -c "from app.services.upstream.types import ChainExhausted"`

### Task 2: shape-error tagging
- **Why not per raise site**: shape errors are raised ~30 times in `reply.py:44-164` and `sse.py:47-120`, and `sse.parse_events` knows only `label`, not the provider.
- **Implement**: wrap the body of `reply.result_from_reply` in `try/except UpstreamError as exc: raise tag_shape(exc, provider.name)`. That covers `complete()` and `collect()` (collect calls it) and includes `reply.py:164` ("no text content") and the `usage`/`total_tokens` errors: deterministic, non-retryable response faults, `shape`. In `OpenAICompatibleAdapter.stream` wrap the `parse_events` loop and the no-finish raise (`:198-210`) the same way. In `complete()` tag the `resp.json()` error (`:160`). Do not alter messages or `__cause__`.

### Task 3: classification in openai_compatible.py
- **Implement**: `_classify_kind(exc)`: `HTTPStatusError` -> `misconfigured` for 401 else `status`; `httpx.TimeoutException` -> `timeout`; other `TransportError` -> `transport`; anything else None. `_retry_after_seconds(response)`: for 429 only, stripped header `isdigit()` -> `max(1, int(v))`, else None. `_http_error(exc, provider)` builds the message exactly as today (`provider.label`). The 3xx redirect error gets `kind="status"`, `provider=provider.name`, still `retryable=False`. The stream deadline `httpx.ReadTimeout` (`:200`) lands in `timeout` through the same path.

### Task 4: `__init__.py`
- Export `ChainExhausted`. In `_resolve_call` (`:80`) pass `kind="misconfigured", provider=provider.name`; leave `:64` and `:68` as they are (kind None).

### Task 5: collect.py
- In the `UsageReport` branch keep the cache pair of the selected (last) event; after `result_from_reply` return `dataclasses.replace(result, cache_read_tokens=..., cache_write_tokens=...)`. Do not put the cache pair in the `usage` dict (it feeds the D8 usage rules). `reply.py` stays free of cache fields until a producer exists.
- **Mirror**: `collect.py:67-76`, `:93`

### Task 6: tests (`tests/test_upstream_error_fields.py`, CREATE)
- `fallback_eligible` parametrized over every 6.2 row: timeout/transport/5xx/429 retryable -> True; misconfigured (retryable False) -> True; other 4xx, shape, refusal, incompatible -> False; exhausted -> True; kind None -> False.
- Defaults and unchanged `str`; bad kind -> `ValueError`; every kind in the tuple accepted; `fallback_eligible` read-only (`AttributeError`); `OpenRouterError is UpstreamError`.
- Adapter faults over `httpx.MockTransport` (copy the helpers), asserting `kind`, `provider == provider.name`, `retryable`, status, message unchanged and canary absent: ReadTimeout, ConnectError, 500/503, 429 with `retry-after: 7` -> 7, `0` -> 1, HTTP-date -> None, absent -> None, `retry-after` on a 500 -> None, 401 -> `misconfigured` with `retryable False`, 400/403/404/413/422 -> `status`, bad JSON and missing `choices` -> `shape`, 302 -> `status`. Stream path: 503, no finish, non-JSON chunk -> `shape`, deadline -> `timeout`.
- `call_upstream` with a provider file (pattern `test_upstream_adapter.py:306-325`): missing key -> `misconfigured` + provider name + eligible; unroutable model and empty messages -> `kind is None`, `provider is None`.
- `ChainExhausted`: message, kind, retryable, status/provider None, list `skipped` coerced to tuple of tuples, `last_error`, `retry_after_seconds`, `ChainExhausted()` defaults, `isinstance UpstreamError`, importable from `app.services.upstream`.
- Result fields: defaults and three-argument construction; `collect` copies the cache pair; a later `UsageReport` without it yields None; `reasoning_blocks == 0`.
- /v1: `_fault_code(ChainExhausted(...)) == "upstream_unavailable"`; `UpstreamError("x", kind="misconfigured")` -> `upstream_error` (mirror `test_v1_errors.py:628`).

## End-to-End Tests

- [ ] `/v1` fault mapping through the real app: existing `tests/test_v1_errors.py`, unmodified.
- [ ] No chat_ui change.

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_upstream_error_fields.py tests/test_upstream_adapter.py tests/test_upstream_stream_collect.py tests/test_stream_upstream_seam.py tests/test_prd020_legacy_fixtures.py tests/test_v1_translate_result.py tests/test_untouched_app.py
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_v1_errors.py -k "fault or unavailable or error"
```
Also grep `tests/` for `UsageReport(` / `UpstreamResult(` equality or `dataclasses.fields` guards and run the hits.

## Acceptance Criteria -> Tasks -> Tests

| AC | Task(s) | Test that proves it |
|----|---------|---------------------|
| AC1 defaults, `str`, alias, /v1 intact | 1 | defaults + `_fault_code` rows in `test_upstream_error_fields.py`; `test_v1_errors.py` unmodified |
| AC2 vocabulary + `fallback_eligible` | 1 | parametrized 6.2 table; bad-kind `ValueError` |
| AC3 adapter kind/provider/retry-after | 2, 3, 4 | adapter fault tests (complete + stream) |
| AC4 `ChainExhausted` | 1, 4 | `ChainExhausted` tests |
| AC5 result fields + collect copy | 1, 5 | result-field and collect tests; `test_upstream_stream_collect.py` unchanged |

## Risks

- Boundary tagging also labels "no text content" and the usage errors `shape`. They are non-retryable and deterministic, consistent with 6.2 (O4). The story says only "malformed body"; say so if a stricter reading is wanted.
- `tag_shape` assigns `kind` after construction, skipping validation; it uses a constant only.
