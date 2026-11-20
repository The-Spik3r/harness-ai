---
story: STORY-001
prd: PRD-022
plan: .agents/plans/PRD-022-provider-fallback-and-native-adapters/completed/STORY-001-foundations-spike.plan.md
epic_branch: epic/PRD-022-provider-fallback-and-native-adapters
commit: dff6bb9
status: COMPLETE
completed: 2026-11-20
---

# Implementation Report — STORY-001: Foundations spike

**Plan**: `.agents/plans/PRD-022-provider-fallback-and-native-adapters/completed/STORY-001-foundations-spike.plan.md`
**Epic Branch**: `epic/PRD-022-provider-fallback-and-native-adapters`
**Commit**: `dff6bb9`

## Summary

Pinned `anthropic==2.11.0` (installed in `.venv`), added `tests/test_prd022_spike_anthropic_sdk.py` (offline, localhost stubs only) and recorded the findings below. No file under `app/` changed. Every SDK fact was read from the venv install (`.venv/Lib/site-packages/anthropic/`, paths below relative to it) or observed by the test.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Install + exact pin | `requirements.txt` | done |
| 2 | Breaker verified read-only (O10) | `app/services/circuit_breaker.py` (unchanged) | done |
| 3 | Redirect probe | `tests/test_prd022_spike_anthropic_sdk.py` | done |
| 4 | Wire-format facts | this report + test | done |
| 5 | Committed offline test | `tests/test_prd022_spike_anthropic_sdk.py` | done |
| 6 | Divergence list | this report | done |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | OK |
| Targeted tests: `test_prd022_spike_anthropic_sdk.py`, `test_circuit_breaker.py`, `test_untouched_app.py` | 61 passed, 0 failed, 0 skipped |
| E2E | n/a (spike; the redirect tests cross real localhost sockets) |
| Full suite | GitHub CI on push (user decision) |

## AC1: breaker (O10 already done)

All present in `app/services/circuit_breaker.py`: `CircuitBreaker.__init__(name, failure_threshold, open_seconds, clock=time.monotonic, probe=None, on_transition=None)` `:109-118`; `before()` `:183` (raises `BreakerOpen`, `:78-81`); `record_success()` `:246`; `record_failure(failure_class: str)` `:259`; `force_open(seconds)` `:281`; `status()` `:294` returning `BreakerStatus` `:62`. `probe=None` is live-trial half-open: the first caller after the window gets `_probing=True` and returns, others get `BreakerOpen(name, 1)`, and a trial that never reports is replaced after `open_seconds` (`:205-210`). The clock is injected. Nothing is missing from the PRD's list; `on_transition` is an extra. No extraction needed.

Caveats for STORY-010 (observed in the test):
- `record_failure` has no per-call open time; it opens for the constructor's `open_seconds` (`:259-278`). The 429 rule `max(retry_after, 10)` must use `force_open`.
- `force_open` on a closed breaker opens it (the transition is logged as class `forced`) but leaves `consecutive_failures == 0` and `last_failure_class is None`.
- `force_open` on an open breaker overwrites `_open_until = now + seconds` (`:289-291`), so it can **shorten** a window (300 s, then `force_open(10)` gives 10 s). STORY-010 must guard (extend only) or keep that rule in `health.py`.
- On an open breaker `record_failure` only records the class and never extends the window (`:272-276`).

## AC3: pin, HTTP dependency, redirects

- `anthropic==2.11.0` (latest on 2026-11-20), appended to `requirements.txt`. `pip show`: requires `anyio, docstring-parser, httpx2, jiter, opentelemetry-api, pydantic, sniffio, typing-extensions`; `httpx2` 2.16.0 requires `anyio, httpcore2, idna, truststore, typing-extensions`; `httpcore2` 2.16.0 requires `h11, truststore`. **The PRD's "1.x on httpx2" is stale: 2.11.0 is also on httpx2** (already in `.venv` via `openai`). It is a separate package from the harness's `httpx` 0.28.1 (PRD-020 client at `app/services/upstream/openai_compatible.py:110-115`); the test asserts `DefaultHttpxClient` is an `httpx2.Client` and not an `httpx.Client`.
- Dockerfile and CI install `requirements.txt`; nothing else to touch. Transitive deps are unpinned (precedent: presidio).

| Case (localhost, `max_retries=0`) | Observed |
|---|---|
| Default client, 307 to another port | **Followed.** `_DefaultHttpxClient` sets `follow_redirects=True` (`_base_client.py:1008`, also `:1765`, `:1823`). Second request carried **neither** `authorization` nor `x-api-key`; method POST |
| Default client, 302 to another port | Followed; second request GET, no credential header |
| Default client, 307 same origin | Followed; second request **kept** `Authorization: Bearer` |
| `http_client=anthropic.DefaultHttpxClient(follow_redirects=False)`, 307 / 302 | `APIStatusError` with `status_code` 307 / 302; second server saw 0 requests |

Why the key is dropped cross-origin: `httpx2/_client.py:524-533` (`_redirect_headers`) pops `Authorization` when `url.origin != request.url.origin`, except a direct http-to-https redirect (origin = scheme + host + port).

**Credential header divergence:** the SDK sends `Authorization: Bearer <key>` (`_client.py:369-378`, `_api_key_auth`), not `x-api-key`. Also `anthropic-version: 2026-10-21` (`_constants.py:7`).

**Recommendation:** D2's raw-`httpx` fallback is not needed. The key is not forwarded cross-origin even by default, and `DefaultHttpxClient(follow_redirects=False)` (exported by `anthropic`, so no `httpx2` import needed) removes the same-origin case too and matches PRD-020 D5. `AnthropicAdapter` must construct the client that way, with `max_retries=0` and an explicit timeout, and treat a 3xx as a non-retryable error as `openai_compatible.py:121-131` does (the Location is never quoted).

## AC4: wire facts (from the install, `anthropic/` relative)

| Fact | Source / evidence |
|---|---|
| SSE events: `message_start`, `message_delta`, `message_stop`, `content_block_start`, `content_block_delta`, `content_block_stop` (`ping` and `error` are handled by the stream class) | `types/raw_message_stream_event.py`; `_streaming.py`; test enumerates the six |
| Deltas: `text_delta`, `input_json_delta` (`partial_json: str`), `citations_delta`, `thinking_delta`, `signature_delta` | test |
| `content_block_start.content_block` includes `text`, `thinking`, `redacted_thinking`, `tool_use`, `server_tool_use` | `types/raw_content_block_start_event.py` (planner-read) |
| `stop_reason`: `end_turn, max_tokens, stop_sequence, tool_use, pause_turn, refusal, model_context_window_exceeded` (**7; PRD lists 6**; needs a mapping row, suggest `length`) | `types/stop_reason.py`; test |
| Usage: `input_tokens`, `output_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens` on both `Usage` and `MessageDeltaUsage` (also `output_tokens_details`); `message_start.message.usage` carries the input side; `message_delta.usage` is cumulative | `types/usage.py`, `types/message_delta_usage.py`; test |
| Thinking request: `{"type":"adaptive","display":"summarized"\|"omitted"}` exists; `enabled` (+ required `budget_tokens`, must be >= 1024 and < `max_tokens`), `disabled`, `between_tools` | `types/thinking_config_*_param.py` |
| `tool_choice`: `auto`, `any`, `tool`, `none`; `disable_parallel_tool_use` on `auto`/`any`/`tool`, not `none` | `types/tool_choice_*_param.py` |
| Top-level `cache_control` on `messages.create` | `types/message_create_params.py:129` |
| Exceptions: `AnthropicError > APIError > APIStatusError > BadRequestError 400, AuthenticationError 401, PermissionDeniedError 403, NotFoundError 404, RateLimitError 429, InternalServerError (ServiceUnavailableError 503, GatewayTimeoutError 504, OverloadedError 529)`; also 402/408/409/413/422/431/499 classes. `APIConnectionError > APITimeoutError` (**timeout is a connection error: catch it first**) | `_exceptions.py:43-259`; test hits each status over a real socket |
| `retry-after`: not a typed attribute; read `exc.response.headers.get("retry-after")` (`"7"` observed); `exc.status_code`, `exc.request_id` exist | test |
| `tool_use.id` is a plain `str` (`Required[str]`) with no pattern or length in the SDK | `types/tool_use_block_param.py:17` |

## Unverifiable offline, with the PRD's safe default

| Item | Safe default |
|---|---|
| `tool_use.id` format `^[a-zA-Z0-9_-]+$` (R5) is the API's rule, not the SDK's | ids pass through unchanged; a provider 400 is a clear non-fallback `upstream_error` |
| Thinking accepted without prior thinking history | send `thinking` only when the route is `reasoning`; a 400 is a non-fallback error |
| Summarized thinking non-empty on every model | treat empty reasoning as valid; never fail on it |
| OpenRouter 403 semantics (key vs. policy) | 403 never falls back (D8) |
| OpenAI SDK honouring `retry-after` on 502 | the harness's own client reads the header; no reliance on SDK behaviour |
| Gemini OpenAI-compat coverage | an `openai_compatible` provider with a catalogue-declared capability set; undeclared features are refused, not attempted |
| The real Anthropic API accepting `Authorization: Bearer <api key>` (the SDK sends it; the PRD says `x-api-key`) | use the SDK as is; if the live API rejects it that is a 401, a non-fallback auth error |

## Divergences from PRD-022 assumptions (each cite re-opened)

| PRD assumption | Built code | Consequence |
|---|---|---|
| `UpstreamError` has `kind`, `retry_after_seconds`, `fallback_eligible` | `upstream/types.py:15-35`: only `upstream_status`, `retryable` | STORY-002 adds keyword-only fields with defaults; `str(exc)` and the positional message unchanged |
| `ToolCallDelta(index, id, name, arguments_fragment)` | `types.py:78-84`: field is `arguments` | Anthropic adapter emits `arguments=<string>`; fix PRD wording |
| Cache fields on usage/result | `UsageReport` (`:88`) and `UpstreamResult` (`:36-60`, mutable dataclass) have none | Add Optional fields declared last with defaults (PRD-013/015 precedent) |
| `stream(request, api_key)` | `ProviderAdapter.stream(request, api_key, *, reasoning=False)` `types.py:121-125`; `stream_upstream` passes `reasoning=route.capabilities.reasoning` (`upstream/__init__.py:123-126`) | Anthropic adapter accepts `reasoning`; sends `thinking` only when true |
| Dispatch by `provider.type` | `upstream/__init__.py:100,123` hard-code `OpenAICompatibleAdapter`; registry `TYPES = ("openai_compatible",)` `provider_registry.py:49`, rejects others `:346-350`, constructs the type at `:396`, `:552` | STORY-003/004 add an adapter factory and widen the registry. `Capabilities` (`:88-95`) lacks `forced_tool_choice`/`sampling_params`; `CatalogModel` (`:98-106`) lacks `prompt_cache`/`default_max_tokens` |
| Chain resolves each candidate | `_resolve_call` (`upstream/__init__.py:59`) resolves itself; the pipeline authorizes once (`query_pipeline.py:540`) | The chain authorizes each candidate (D7) and calls the seam with that id; `resolve` runs again inside the seam |
| `_classify_http_error` reusable | `upstream/openai_compatible.py:54-64`, typed on `httpx.HTTPError` | Not usable for SDK exceptions (httpx2 hierarchy); the Anthropic adapter needs its own mapping and keeps the 3xx-is-error rule (`:121-131`) |
| `authorize_route` | `authz.py:227-246`: returns `Route`; raises `PermissionDenied(f"query:model:{model}")` for unknown and forbidden alike (T3); wildcard roles reach any resolvable model | Per-candidate `PermissionDenied` means "ineligible, skip"; identical text, no leakage |
| `_Upstream` / `_CommitSink` | `app/routers/v1.py:151` and `:185`: `_Upstream` stands in for `call_openrouter` and flips `called` on the first call | The chain calls the injected `call_openrouter` / `stream_upstream` params (`query_pipeline.py:446,451`) once per attempt; `called` flips on attempt 1 |
| Fault mapping | `v1.py` `_fault_code` `:290`; 4xx get `x-should-retry: false` (`:266-279`) | Exhaustion errors reuse this path; keep `retryable` semantics |
| Audit columns | `AUDIT_LOGS_ADDED_COLUMNS` is a dict name to DDL (`app/db/models.py:71`); provider columns `:162-164`; record fields `:559` | New columns: dict + record + `log_query` kwargs after `**_route_fields(route)`; field-order guard (`grep usage_estimated tests/`) |
| Stream step | `query_pipeline.py:1063` consumes `stream_upstream(...)`, `collect(` at `:1143` | The chain wraps this block per attempt |
| SDK `x-api-key`; "1.x on httpx2" | Wire header `Authorization: Bearer`; 2.11.0 on httpx2; default follows redirects | Amend PRD 6.5/8/9; adapter passes `DefaultHttpxClient(follow_redirects=False)` |
| 5 `stop_reason` values + `pause_turn` | 7 values incl. `model_context_window_exceeded` | Add a mapping row |

## Recommendations for STORY-002..017

- STORY-002: extend `UpstreamError` / `UpstreamResult` / `UsageReport` additively (defaults, keyword-only); pure `v1_translate.py` still imports only `upstream.params` / `upstream.types`.
- STORY-003: adapter factory keyed on `provider.type`; `AnthropicAdapter` with `anthropic.Anthropic(api_key=..., base_url=..., max_retries=0, timeout=..., http_client=anthropic.DefaultHttpxClient(follow_redirects=False))`; catch `APITimeoutError` before `APIConnectionError`, then `APIStatusError` subclasses by status; read `retry-after` from `exc.response.headers`; map all 7 stop reasons; accept `reasoning=`; emit `ToolCallDelta.arguments` as the whole string. Never put `str(exc)` or response bodies into messages (T10).
- STORY-004: widen `TYPES` and the registry validators; add `Capabilities` / `CatalogModel` fields.
- STORY-010: use `force_open(max(retry_after, 10))` guarded so it only extends; reuse `CircuitBreaker(probe=None)`; test with an injected clock.
- Chain stories: authorize per candidate, call the seam once per attempt, no retry after the first sink release.

## PRD amendments handed to the orchestrator

1. 6.5/8/9: wire credential is `Authorization: Bearer`, not `x-api-key`; SDK 2.11.0 runs on httpx2 (not "1.x"); redirects are followed by default, so require `DefaultHttpxClient(follow_redirects=False)`; D2's raw-`httpx` fallback is unnecessary.
2. 6.6: `ToolCallDelta.arguments`, not `arguments_fragment`.
3. 6.5: add `model_context_window_exceeded` to the stop-reason table.
4. F1/D11: state that `UpstreamError` fields are new (STORY-002), not existing.
5. O10: mark done (PRD-018); record the `force_open` shorten-window caveat.

## Files Changed

| File | Action |
|---|---|
| `requirements.txt` | UPDATE (+1: `anthropic==2.11.0`) |
| `tests/test_prd022_spike_anthropic_sdk.py` | CREATE |
| this report | CREATE |
| story, index, plan (archived) | UPDATE / MOVE |

## Deviations from Plan

- Planner said `force_open` on a closed breaker "sets class `forced`"; observed: only the transition log line says `class=forced`; `last_failure_class` stays `None`. The test asserts the observed value.
- Planner's exception list was a subset; the SDK also has 402/408/409/413/422/431/499 classes.
- `httpx2` in `.venv` is 2.16.0 (planner's scratch run saw 2.16.2); `_redirect_headers` is at `httpx2/_client.py:524-533` here. Behaviour identical.

## Tests Written

`tests/test_prd022_spike_anthropic_sdk.py`: pin matches `requirements.txt`; `max_retries=0` + timeout accepted; httpx2 vs httpx; default client redirects 307/302 cross-origin; same-origin keeps key; no-redirect client 307/302; Authorization Bearer header; exception hierarchy over 9 statuses; timeout-is-connection-error; retry-after through response headers; wire vocabulary literals; breaker API shape; force_open caveats.

## Acceptance Criteria

- [x] AC1 breaker confirmed with file:line; O10 done (`test_breaker_api_shape_for_prd022`, `test_force_open_can_shorten_an_open_window_and_leaves_no_failure_count`)
- [x] AC2 divergence list (above)
- [x] AC3 pin, HTTP dependency, redirect proof (`test_sdk_is_importable_at_the_pinned_version`, redirect tests); raw-httpx fallback not needed
- [x] AC4 wire facts (`test_wire_vocabulary_literals`, `test_exception_hierarchy_and_status_codes`, `test_rate_limit_error_exposes_retry_after_through_response_headers`)
- [x] AC5 committed offline test, localhost only
