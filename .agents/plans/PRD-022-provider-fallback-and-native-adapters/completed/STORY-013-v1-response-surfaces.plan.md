---
story: STORY-013
prd: PRD-022
slug: v1-response-surfaces
title: /v1 surfaces — answering model, harness.provider/attempts, X-Harness-Provider, exhaustion with retry-after
type: ENHANCEMENT
complexity: medium
epic_branch: epic/PRD-022-provider-fallback-and-native-adapters
created: 2026-11-20
---

# Plan: /v1 response surfaces

## Summary

The pipeline attaches the answer's provenance (provider name, answering catalogue id, calls made) to `QuerySuccessResponse` as a private, never-serialized attribute, like `_tool_outcome` / `_upstream_result`. `translate_result` copies it into two new optional `harness` fields; `_json_response` adds `X-Harness-Provider`. `ChainExhausted` is classified by a small pure helper in `v1_translate.py` from the exception's attributes only; the router calls it before the generic `_fault_code` path. `/query` is untouched.

- Story: `.agents/stories/PRD-022-provider-fallback-and-native-adapters/STORY-013-v1-response-surfaces.md`
- PRD sections used: F7, F10, Section 10, D12, D17, O5, T10, User story 4
- Systems affected: `app/models/schemas.py`, `app/models/v1_schemas.py`, `app/services/query_pipeline.py`, `app/services/v1_translate.py`, `app/routers/v1.py`

## Design Decisions

- **Transport (binding)**: private attribute on `QuerySuccessResponse` (`schemas.py:100-124` pattern), set at `query_pipeline.py:1749-1766` next to `_upstream_result`. Provenance type: a small frozen dataclass `AnsweredBy(provider: str, model: str, attempts: int)` defined in `app/models/schemas.py` (imports nothing from `app`). No new `QuerySuccessResponse` field, so `/query`'s body and OpenAPI do not move; a test asserts it. Chained: `route.provider.name`, `chain_outcome.route.model_id`, `chain_outcome.attempt` (`route` is already rebound to `chain_outcome.route` at `query_pipeline.py:1352`). No chain: `route.provider.name`, the requested `model`, `1`. Guard `route is not None`. `v1_translate.py` already imports `app.models.schemas`, so it needs no new import and stays free of `app.services.upstream` `__init__` (`test_is_pure`, `tests/test_v1_translate_request.py:~318`, guards it).
- **The model already answers (verified; report to orchestrator)**: `call_upstream` makes `model_used` the id it was called with (`upstream/__init__.py:145-146`), and the chain's `attempt` passes `candidate_route.model_id` (`query_pipeline.py:1262-1275`). So `QuerySuccessResponse.model_used` (`:1753`) is already the answering id on a chained request (`test_model_used_response_vs_audit`, `tests/test_query_pipeline_chain.py:254`), `translate_result` already sets `model=result.model_used`, and the buffered-SSE chunks take `completion.model` (`v1_sse.py:~75`). So `/v1` `model` and `/query` `model_used` carry the answering id with no change; this story only pins it with a `/v1` test.
- **`harness` fields**: `HarnessCompletionInfo` (`v1_schemas.py:180-208`) gains `provider: Optional[str] = None` and `attempts: Optional[int] = None`; the wrap serializer (`:200-207`) drops each when None, so direct constructions in `test_v1_sse/realtime/tools/schemas` keep their bodies. `translate_result` sets both from the attribute; a success built without one (a stub) omits them. Every real success, with or without fallback, carries both.
- **Header**: `X-Harness-Provider: <provider>` added in `_json_response` (`v1.py:366-376`) from `outcome.harness.provider` when not None. **Not possible on SSE**: a stream's headers go out at commit, before the answer exists (`v1.py:~558`: "No X-Harness-Audit-Id: the row does not exist yet"), and the chunks carry no `harness` object. So buffered-SSE gets the answering `model` only; the header and `harness` are JSON-only. This deviates from AC1's wording; the implementer states it in the report. The real-time path is untouched (STORY-014).
- **Exhaustion helper (pure, in `v1_translate.py`)**: `translate_exhausted(skipped, last_error, retry_after_seconds) -> V1Error`, taking plain values (no import of the exception type):
  - (a) `last_error is None`, `skipped` non-empty and every reason in `{"capability","forbidden","byok"}` -> `translate_fault(UPSTREAM_ERROR, msg)` (502 `api_error`, `retryable=False`; the router already adds `x-should-retry: false`). `msg` = fixed prefix + the sorted distinct reasons joined by ", " (closed words only, O5; never a provider name or `str(last_error)`).
  - (b) anything else -> `translate_fault(UPSTREAM_UNAVAILABLE, "all providers unavailable", retry_after_seconds=...)`; `_from_v1_error` (`v1.py:187-202`) already emits `Retry-After` only when not None, and no `x-should-retry` for a retryable fault.
  - Edge cases: `retry_after_seconds=None` -> no header; mixed skips (`capability`+`open`) -> (b); empty `skipped` with `last_error None` -> (b); an attempt ran (`last_error` set) with only capability skips -> (b).
- **Router**: in `_outcome` (`v1.py:~314-348`), before `translate_fault(code, str(exc))` at `:348`, add `if isinstance(exc, ChainExhausted): return translate_exhausted(exc.skipped, exc.last_error, exc.retry_after_seconds)`. Import `ChainExhausted` from `app.services.upstream.types` (the router is not a pure module). The log line keeps `code=` only. JSON, buffered-SSE error events and the real-time tail all go through `_outcome`, so they share the mapping.
- **Non-eligible last failure**: `chain.run` re-raises the original `UpstreamError` (`chain.py:~204`), so it is not `ChainExhausted` and keeps today's `upstream_error` + `x-should-retry: false`. Test only, no code.
- **T10**: only `kind`/status and the closed vocabulary reach a body or header. `translate_exhausted` takes `last_error` only to test `is None`, never `str(...)`. A test proves a secret-looking provider message never appears in body or headers.
- `/query` stays as is (502 `all providers unavailable`; `test_query_route_maps_exhausted_to_502`).

---

## Skills In Use

None (`skills: []`; `.agents/skills/` has nothing for `/v1` response mapping).

---

## Patterns to Follow

| Category | Source | What to mirror |
|----------|--------|----------------|
| Private attribute | `app/models/schemas.py:100-124`, set at `query_pipeline.py:1757-1766` | `PrivateAttr(default=None)` + read-only property |
| Optional harness key | `v1_schemas.py:200-207` | wrap serializer drops the absent key |
| Fault mapping | `v1_translate.py:760-790` (`_FAULTS`, `translate_fault`) | build `V1Error` through the table; the router adds the headers |
| Headers | `v1.py:187-202`, `:366-376` | `Retry-After` from `V1Error.retry_after_seconds`; success headers dict |
| Pure unit tests | `tests/test_v1_translate_result.py:94-168` | direct call, no DB |
| Pipeline + HTTP tests | `tests/test_query_pipeline_chain.py:115-180` (fixtures `chained`, `Upstream`, `_run`, `_HEADERS`), `:412-430` | TestClient on `/v1`, `v1_router.call_openrouter` stub, `_open_all()` |

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/models/schemas.py` | UPDATE | `AnsweredBy` dataclass; private `_answered_by` + `answered_by` property on `QuerySuccessResponse` |
| `app/models/v1_schemas.py` | UPDATE | `HarnessCompletionInfo.provider`, `.attempts` (dropped when None) |
| `app/services/query_pipeline.py` | UPDATE | set `success._answered_by` after the build (~`:1759`) |
| `app/services/v1_translate.py` | UPDATE | `translate_result` copies provenance; add `translate_exhausted` |
| `app/routers/v1.py` | UPDATE | route `ChainExhausted` through the helper; `X-Harness-Provider` in `_json_response` |
| `tests/test_v1_translate_result.py` | UPDATE | harness fields, absent-when-None, helper unit tests |
| `tests/test_query_pipeline_chain.py` | UPDATE | `/v1` end-to-end surfaces; `/query` body unchanged; T10 |

## Tasks

### Task 1: Provenance on the pipeline result
- **File**: `app/models/schemas.py`, `app/services/query_pipeline.py`
- **Implement**: frozen `AnsweredBy` + private attr/property; after `success = QuerySuccessResponse(...)` set `success._answered_by = AnsweredBy(route.provider.name, chain_outcome.route.model_id if chain_outcome else model, chain_outcome.attempt if chain_outcome else 1)`. Comment cites PRD-022 D17 / F10 and "private, never serialized".
- **Mirror**: `query_pipeline.py:1757-1766`
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_schemas.py`

### Task 2: Harness fields and translation
- **File**: `app/models/v1_schemas.py`, `app/services/v1_translate.py`
- **Implement**: the two optional fields with drop-when-None; `translate_result` passes `provider=`/`attempts=` from `result.answered_by` when set. Update the docstring ("`model` is the requested name" becomes "the answering id", D17).
- **Mirror**: `v1_schemas.py:200-207`
- **Validate**: `tests/test_v1_translate_result.py tests/test_v1_schemas.py`

### Task 3: `translate_exhausted`
- **File**: `app/services/v1_translate.py`
- **Implement**: as in Design Decisions; pure, no logging, no settings.
- **Validate**: `tests/test_v1_translate_result.py -k exhausted`

### Task 4: Router wiring
- **File**: `app/routers/v1.py`
- **Implement**: the `ChainExhausted` branch in `_outcome`; `X-Harness-Provider` merged into `_json_response`'s headers (omitted when provider is None).
- **Validate**: `tests/test_query_pipeline_chain.py -k v1`

### Task 5: Tests
- **Unit** (`test_v1_translate_result.py`): provenance copied to `harness.provider/attempts`, `model` = `result.model_used`; both absent when no `_answered_by`; `translate_exhausted` matrix: (capability); (forbidden+byok); (capability+open) -> (b); `retry_after_seconds` None vs 27; empty skips; `last_error` set + capability skips -> (b); message holds only closed words (assert none of the input provider names appear); `V1Error` fields (`retryable`, `retry_after_seconds`).
- **HTTP** (`test_query_pipeline_chain.py`, fixtures `chained`, `Upstream`, `_503`, `_open_all`):
  1. no fallback: `model == "remote/m"`, `harness.provider == "remote"`, `attempts == 1`, header `X-Harness-Provider: remote`;
  2. fallback after one 503: `model == "other/m"`, `attempts == 2`, header `other`;
  3. buffered-SSE (`stream: true`): chunk `model == "other/m"`;
  4. all open: 502 `upstream_unavailable`, `Retry-After` a digit string, no `x-should-retry` (extend `:422`);
  5. `query_pipeline.chain.run` patched to raise `ChainExhausted([("remote","open")])`: no `retry-after`;
  6. patched `ChainExhausted([("other","capability")])`: 502 `upstream_error`, `x-should-retry: false`, message names `capability`;
  7. mixed skips -> `upstream_unavailable`;
  8. last-attempt 4xx (like `:262`) -> `upstream_error` + `x-should-retry: false`;
  9. T10: the upstream error text `sk-or-v1-CANARY` on every attempt (and as `last_error`) is in no body and no header value;
  10. `/query` success body keys equal today's set (`test_query_pipeline_tools.py:~660`), no `provider`/`attempts`;
  11. no-chain `/v1` success: `attempts == 1`; read the legacy route's real provider name before asserting it.
- **Mirror**: `tests/test_query_pipeline_chain.py:222-262, 412-430`

---

## End-to-End Tests

- [ ] `TestClient(app)` `/v1/chat/completions` through a two-candidate chain with a 503 primary: 200, `model`, `harness.provider/attempts`, `X-Harness-Provider`
- [ ] `/v1` total outage (all breakers open): 502 `upstream_unavailable` + `Retry-After`
- [ ] `/query` unchanged: success body keys and the 502 detail

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
# one pytest at a time (shared libSQL); each call after the previous one finishes
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_v1_translate_result.py tests/test_v1_schemas.py tests/test_v1_translate_request.py tests/test_v1_sse.py tests/test_schemas.py tests/test_untouched_app.py
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_query_pipeline_chain.py
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_v1_errors.py -k "upstream or fault or unavailable"
```
`tests/test_prd020_legacy_fixtures.py` only if a `/query` body assertion fails (the schema does not change).

## Acceptance Criteria -> Tasks -> Tests

| AC | Task(s) | Test that proves it |
|----|---------|---------------------|
| AC1 answering model, harness fields, header (JSON; SSE model only, see deviation) | 1, 2, 4 | HTTP (1)-(3), unit provenance tests |
| AC2 502 `upstream_unavailable` + `retry-after`, none when None | 3, 4 | HTTP (4), (5); unit matrix |
| AC3 non-eligible keeps `upstream_error`; no eligible candidate -> non-retryable naming the capability | 3, 4 | HTTP (6), (8); unit matrix |
| AC4 T10; existing tests unmodified | 3, 5 | HTTP (9); existing `/v1` files pass unmodified |

## Risks

- A test comparing a full `/v1` success `harness` dict by equality would break. A grep found none (only `audit_id`/`audit_ref` key reads); `test_builds_the_section_7_4_example` builds a result without `_answered_by`, so it stays unmodified.
- `/query` body/OpenAPI: private attribute only; guarded by test (10) and `test_prd020_legacy_fixtures.py`.
- Test (3): copy the setup of an existing buffered-SSE test (`tests/test_v1_sse.py` / `test_v1_router.py`) so the stream is buffered, not real-time.
