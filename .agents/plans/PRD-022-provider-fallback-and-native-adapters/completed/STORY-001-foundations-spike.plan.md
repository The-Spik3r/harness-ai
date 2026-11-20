---
story: STORY-001
prd: PRD-022
slug: foundations-spike
title: Spike — confirm built PRD-018/020/021 seams, pin the anthropic SDK, check redirects and the Messages wire format
type: ENHANCEMENT
complexity: medium
epic_branch: epic/PRD-022-provider-fallback-and-native-adapters
created: 2026-11-20
---

# Plan: Foundations spike

## Summary

A spike. Deliverables: (1) `requirements.txt` pin of `anthropic==2.11.0`, (2) `tests/test_prd022_spike_anthropic_sdk.py`, (3) the report `.agents/reports/PRD-022-provider-fallback-and-native-adapters/STORY-001-foundations-spike.report.md`. **No file under `app/` changes.** Every SDK fact below was already read by the planner from a scratch install (`pip install --target <scratchpad>/sdk anthropic==2.11.0`, not the venv); the implementer re-confirms them against the venv install and cites the paths in the report.

- Story: `.agents/stories/PRD-022-provider-fallback-and-native-adapters/STORY-001-foundations-spike.md`
- PRD sections used: 6.5 (Transport), 6.6 (bullets), 6.10, 8, 14 (R1/R5/R6), 15 "Not verified" / "Builds on PRD-020"
- Systems affected: `requirements.txt`, `tests/` only. Skills: none apply (`.agents/skills/` holds only `frontend-design`).

## Design Decisions (binding, from the orchestrator)

- No app code. O10 is done by PRD-018; verify, do not change `circuit_breaker.py`.
- SDK: newest release that installs cleanly in `.venv` (`pip index versions` 2026-11-20: 2.11.0; `pip install --dry-run` in `.venv` resolves cleanly, adding only `anthropic-2.11.0`, `docstring_parser-0.18.0`, `opentelemetry-api-1.45.2`). Pin exactly.
- Redirect probe: localhost `http.server` answering 307/302 to a second localhost port; SDK built with `base_url=http://127.0.0.1:<port>`, `max_retries=0`, explicit `timeout`. Ports picked at runtime (port 0), servers stopped in teardown, no sleeps, no non-localhost network.
- Wire facts come from installed SDK sources, never memory or network.

## Task 1: Install and pin (`requirements.txt`)

- Run `.venv/Scripts/python -m pip install anthropic==2.11.0`; append `anthropic==2.11.0` to `requirements.txt` (exact pin, same style as `sqlglot==30.27.0`). No other line changes.
- Record in the report `pip show anthropic httpx2 httpcore2`. Planner findings: `anthropic` 2.11.0 requires `httpx2>=2.0.0` (METADATA `Requires-Dist`), plus `anyio`, `jiter`, `pydantic`, `opentelemetry-api`, `docstring-parser`, `sniffio`, `typing-extensions`. **The PRD's "1.x on httpx2" is stale: 2.x is also httpx2.** `httpx2` 2.16.0 is already in `.venv` (required by `openai`, `requirements-e2e.txt:7`) and is a separate package from the harness's `httpx` 0.28.1 (PRD-020 `follow_redirects=False` client at `app/services/upstream/openai_compatible.py:110-115`). Transitive deps are not pinned in `requirements.txt` (precedent: `presidio-*`).
- `Dockerfile:6-7,54-55` and `.github/workflows/ci.yml:66` both install `requirements.txt`: nothing else to touch.
- **Validate**: `.venv/Scripts/python -c "import anthropic; print(anthropic.__version__)"` prints `2.11.0`; `.venv/Scripts/python -c "from app.main import app; print('OK')"`.

## Task 2: Verify the breaker (O10), read only

Confirmed by the planner at `app/services/circuit_breaker.py` (cite in the report; re-open the lines):
- `CircuitBreaker.__init__(name, failure_threshold, open_seconds, clock=time.monotonic, probe=None, on_transition=None)` `:109-118`; validates threshold >= 1 and open_seconds > 0.
- `before()` `:183` (raises `BreakerOpen(name, retry_after_seconds)` `:78-81`); `record_success()` `:246`; `record_failure(failure_class: str)` `:259` (free string, not an enum); `force_open(seconds)` `:281`; `status()` `:294` -> frozen `BreakerStatus(state, since, consecutive_failures, last_failure_class, retry_after_seconds)` `:62-76`.
- `probe=None` live-trial half-open: the first caller after the window is admitted (`_probing=True`, `before()` returns), others get `BreakerOpen(name, 1)`; a trial that never reports is replaced after `open_seconds` (lease, `:205-210`). `record_success`/`record_failure` close/reopen only when `probe is None` (`:246-278`).
- Injected clock: tests drive time without sleeping (`tests/test_circuit_breaker.py`).
- **Per-call open time: NOT supported by `record_failure`.** It opens for the fixed constructor `open_seconds` (`:259-278`). For the 429 rule `max(retry_after, 10)`, STORY-010 must call `force_open(max(retry_after, 10))`. Caveats for the report: on a closed breaker `force_open` transitions with class `"forced"` and neither increments `consecutive_failures` nor sets `last_failure_class` (`:281-292`); on an already-open breaker it overwrites `_open_until = now + seconds`, so it can **shorten** an existing window (a 300 s misconfigured outage then a 429 `force_open(10)` reopens sooner). STORY-010 must guard (only extend) or keep that rule in `health.py`.
- Gap list: none against the PRD's list. Extras: the `on_transition` hook.

## Task 3: Redirect probe (scratch first, then the committed test)

Planner result (scratch run, `anthropic` 2.11.0, httpx2 2.16.2): the SDK's default client `_DefaultHttpxClient` sets `follow_redirects=True` (`anthropic/_base_client.py:1008`, also `:1765`, `:1823`). A 307 was followed to the second port: **redirects ARE followed by default.** The credential header is **`Authorization: Bearer <key>`, not `x-api-key`** (`anthropic/_client.py:369-378`, `_api_key_auth`; confirmed on the wire; `x-api-key` appears only in `_validate_headers` `:411-414`). httpx2 pops `Authorization` when the redirect target's origin differs (`httpx2/_client.py:518-528`, `_redirect_headers`; origin = scheme+host+port), so the second request on another port carried **neither** `authorization` nor `x-api-key`. A same-origin redirect keeps it (code reading; the implementer proves it with a third case). A 302 turns POST into GET (`:466-480`): the second server needs a `do_GET`, else the SDK shows 501.
- With `http_client=anthropic.DefaultHttpxClient(follow_redirects=False)` the redirect surfaces as `APIStatusError` with `status_code` 307/302 and no second request: the PRD-020 D5 behaviour ("redirects are not followed", `openai_compatible.py:121-131`) and the recommended `AnthropicAdapter` construction. `DefaultHttpxClient` is exported by `anthropic` (subclass of `httpx2.Client`), so the adapter need not import `httpx2`.
- Report recommendation: D2's raw-`httpx` fallback is **not needed** (the key is not forwarded cross-origin even by default; `follow_redirects=False` removes the same-origin case too). The adapter must pass the no-redirect client.
- The test covers {307, 302} x {default client, no-redirect client}: whether the second request arrived and which of `authorization` / `x-api-key` it carried. Assert observed facts only.

## Task 4: Wire-format facts (report, with SDK paths relative to the install's `anthropic/`)

| Fact | Source (planner-read) |
|---|---|
| SSE events: `message_start`, `message_delta`, `message_stop`, `content_block_start`, `content_block_delta`, `content_block_stop`; `ping` and `error` handled by the stream class | `types/raw_message_stream_event.py`; `_streaming.py:93,99` |
| Deltas: `text_delta`, `input_json_delta` (`partial_json: str`), `citations_delta`, `thinking_delta`, `signature_delta` | `types/raw_content_block_delta.py`, `types/input_json_delta.py` |
| `content_block_start.content_block`: `text`, `thinking`, `redacted_thinking`, `tool_use`, `server_tool_use`, ... | `types/raw_content_block_start_event.py` |
| `stop_reason`: `end_turn, max_tokens, stop_sequence, tool_use, pause_turn, refusal, model_context_window_exceeded` (**one more than PRD 6.5**; needs a mapping, suggest `length`) | `types/stop_reason.py` |
| Usage: `input_tokens`, `output_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens` (both Optional), `output_tokens_details`; `message_delta.usage` is cumulative, its input/cache fields Optional; `message_start.message.usage` carries the input side | `types/usage.py`, `types/message_delta_usage.py`, `types/raw_message_delta_event.py:31-36` |
| Thinking request: `{"type":"adaptive","display":"summarized"\|"omitted"}` **exists**; `enabled` (+`budget_tokens` >= 1024, < `max_tokens`, `display`), `disabled`, `between_tools` | `types/thinking_config_*_param.py` |
| `tool_choice`: `auto`, `any`, `tool`, `none`; `disable_parallel_tool_use` on auto/any/tool, not `none` | `types/tool_choice_*_param.py` |
| Top-level `cache_control` on `messages.create` exists | `types/message_create_params.py:129` |
| Exceptions: `AnthropicError > APIError > APIStatusError > {BadRequestError 400, AuthenticationError 401, PermissionDeniedError 403, NotFoundError 404, RateLimitError 429, InternalServerError (503 ServiceUnavailableError, 504, `OverloadedError` 529)}`; `APIConnectionError > APITimeoutError` (**timeout is a subclass of connection error: catch it first**) | `_exceptions.py:43-260` |
| `retry-after`: not a typed attribute; read `exc.response.headers.get("retry-after")` (scratch run: 429 + `retry-after: 7` gave `"7"`). The SDK's own parser also reads `retry-after-ms` and HTTP-date. `exc.status_code`, `exc.request_id` exist | `_exceptions.py:85-140`; `_base_client.py:879-926` |
| `tool_use.id`: `str`, **no pattern or length in the SDK**; examples `toolu_01D7FLrfh4GYq7yT1ULFeyMV`. The `^[a-zA-Z0-9_-]+$` rule is the API's: **unverifiable offline**; R5 safe default: ids pass through, a provider 400 is a clear non-fallback `upstream_error` | `types/tool_use_block_param.py`, `types/message_create_params.py:269` |
| Observed request headers: `anthropic-version: 2026-10-21`, `Authorization: Bearer` | scratch run |

Unverifiable offline (record each with the PRD's safe default): thinking-without-history acceptance, non-empty summarized thinking on every model, OpenRouter 403 semantics, OpenAI SDK honouring `retry-after` on 502, Gemini OpenAI-compat coverage, and that the real API accepts `Authorization: Bearer <api key>` (the SDK sends it; the PRD says `x-api-key`).

## Task 5: `tests/test_prd022_spike_anthropic_sdk.py` (CREATE)

Mirror `tests/test_circuit_breaker.py` (module docstring citing PRD/story, pure, no sleeping, joins with timeout) and the free-port stub style of `tests/test_stub_openrouter.py`. Localhost only:
- `test_sdk_is_importable_at_the_pinned_version`: `anthropic.__version__` equals the `anthropic==` line of `requirements.txt`.
- `test_client_accepts_max_retries_zero_and_explicit_timeout`.
- `test_default_client_follows_redirects_but_not_the_key_cross_origin` (307/302) and `test_no_redirect_client_surfaces_the_30x_as_api_status_error` (second server saw 0 requests); plus a same-origin case documenting that the key travels there.
- `test_the_credential_header_is_authorization_bearer` (pins the divergence from the PRD).
- `test_exception_hierarchy_and_status_codes`.
- `test_rate_limit_error_exposes_retry_after_through_response_headers`.
- `test_wire_vocabulary_literals`: `typing.get_args(StopReason)`, `ThinkingConfigAdaptiveParam.__annotations__` has `display`, delta `type` literals, `Usage.model_fields` has both cache fields.
- `test_breaker_api_shape_for_prd022`: `inspect.signature` of `CircuitBreaker` (`probe=None` default) and `record_failure` taking only `failure_class` (pins "no per-call open time").
- Servers: `http.server.HTTPServer(("127.0.0.1", 0), ...)` on a thread, `shutdown()` + `server_close()` in the fixture finalizer. No real DNS, no `sleep`.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_prd022_spike_anthropic_sdk.py tests/test_circuit_breaker.py`.

## Task 6: Divergences (copy into the report; re-open each cite)

| PRD assumption | Built code | Consequence |
|---|---|---|
| `UpstreamError` has `kind`, `retry_after_seconds`, `fallback_eligible` (F1/D11) | `upstream/types.py:15-35`: only `upstream_status`, `retryable` | STORY-002 adds keyword-only fields with defaults; `str(exc)` and the positional message unchanged |
| `ToolCallDelta(index, id, name, arguments_fragment)` (6.6) | `types.py:78-84`: the field is `arguments` | Anthropic adapter emits `arguments=<whole string>`; fix PRD wording |
| Cache fields on usage/result | `UsageReport` `types.py:88-93` prompt/completion/total only; `UpstreamResult` `:38-60` none | STORY-002/003 add Optional fields declared last with defaults (PRD-013/015 precedent) |
| `stream(request, api_key)` | `ProviderAdapter.stream(request, api_key, *, reasoning=False)` `types.py:121-125`; `stream_upstream` passes `reasoning=route.capabilities.reasoning` (`upstream/__init__.py`, end of file) | Anthropic adapter accepts `reasoning`; sends `thinking` only when true |
| Dispatch by `provider.type` | `call_upstream`/`stream_upstream` hard-code `OpenAICompatibleAdapter` (`upstream/__init__.py`); registry rejects other types (`provider_registry.py:346-352`; `type="openai_compatible"` at `:396`, `:552`) | STORY-003/004 add an adapter factory and widen the registry. `Capabilities` (`:88-95`) lacks `forced_tool_choice`/`sampling_params`; `CatalogModel` (`:98-106`) lacks `prompt_cache`/`default_max_tokens` |
| Chain resolves each candidate | `_resolve_call` calls `provider_registry.resolve(model)` itself (`upstream/__init__.py`, `_resolve_call`); the pipeline authorizes once (`query_pipeline.py:540`) | The chain authorizes each candidate (D7) and calls the seam with that id; `resolve` runs again inside the seam |
| `_classify_http_error` reusable | lives in `upstream/openai_compatible.py:54-64`, typed on `httpx.HTTPError`, returns `(status, retryable)`; `v1.py` does not call it (`_fault_code` reads `exc.retryable`) | Not usable for SDK exceptions (httpx2 hierarchy); Anthropic adapter needs its own mapping; keep the 3xx-is-error rule (`:121-131`) |
| `authorize_route` | `authz.py:227-246`: returns `Route`; raises `PermissionDenied(f"query:model:{model}")` for unknown and forbidden alike (T3); wildcard roles reach any resolvable model; `authorize_model` `:249` delegates | Per-candidate `PermissionDenied` means "ineligible, skip"; identical text, no leakage |
| `_Upstream` | `v1.py:151-173`: stands in for `call_openrouter`, sets `called` and wakes the loop on the first call, keeps only the last `result`; `_CommitSink` for streams | The chain calls the injected `call_openrouter` / `stream_upstream` params (`query_pipeline.py:446,451`) once per attempt; `called` flips on attempt 1 |
| Fault mapping | `v1.py` `_fault_code` (~`:296-308`): `OpenRouterError` -> `UPSTREAM_UNAVAILABLE` if `.retryable` else `UPSTREAM_ERROR`; 4xx get `x-should-retry: false`; `Retry-After` from `error.retry_after_seconds` (`:258-283`) | Exhaustion errors reuse this path; keep `retryable` semantics |
| Audit columns | `AUDIT_LOGS_ADDED_COLUMNS` is a dict `name -> DDL` (`app/db/models.py:71-166`); provider fields at `:162-166`; record fields `:559-563` | New columns: dict + record + `log_query` kwargs after `**_route_fields(route)`; field-order guard (`grep usage_estimated tests/`) |
| Stream step | `query_pipeline.py:~1056-1075` consumes `stream_upstream(...)`, then `collect(...)` at `~:1142` | The chain wraps this block per attempt |
| SDK `x-api-key`; "1.x on httpx2" | Wire header is `Authorization: Bearer`; 2.11.0 is on httpx2; default follows redirects | Orchestrator amends 6.5/8/9; adapter passes `DefaultHttpxClient(follow_redirects=False)` |
| 5 `stop_reason` values + `pause_turn` | 7 values incl. `model_context_window_exceeded` | Add a mapping row |

## Task 7: Report

Write `.agents/reports/PRD-022-provider-fallback-and-native-adapters/STORY-001-foundations-spike.report.md` (`implement.md:218`, `commit: pending`): ACs 1-5 with evidence, the Task 2 verdict and `force_open` caveats, the Task 3 table, Task 4 table, unverifiable list with defaults, Task 6 divergences, and a handoff list of PRD amendments for the orchestrator.

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_prd022_spike_anthropic_sdk.py tests/test_circuit_breaker.py tests/test_untouched_app.py
```
`test_untouched_app.py` runs as the guard although `app/` is untouched.

## Acceptance Criteria -> Tasks -> Tests

| AC | Task(s) | Test that proves it |
|---|---|---|
| AC1 breaker API, O10 done | 2 | `test_breaker_api_shape_for_prd022` + report cites |
| AC2 divergence list | 6 | report |
| AC3 pin, HTTP dep, redirect proof | 1, 3 | `test_sdk_is_importable_at_the_pinned_version`, redirect tests |
| AC4 wire facts | 4 | `test_wire_vocabulary_literals`, `test_exception_hierarchy_and_status_codes`, `test_rate_limit_error_exposes_retry_after_through_response_headers`; report |
| AC5 committed offline test | 5 | the whole file |

Risks: pip may bump `pydantic` (installed 2.13.5; SDK allows <3); the test must work on Linux CI (ports via 0, no Windows-only paths).
