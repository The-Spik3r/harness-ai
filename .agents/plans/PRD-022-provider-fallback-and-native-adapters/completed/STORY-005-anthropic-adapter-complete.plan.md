---
story: STORY-005
prd: PRD-022
slug: anthropic-adapter-complete
title: AnthropicAdapter.complete() — request/response mapping, SDK error mapping, cache tokens
type: NEW_CAPABILITY
complexity: large
epic_branch: epic/PRD-022-provider-fallback-and-native-adapters
created: 2026-11-20
---

# Plan: AnthropicAdapter.complete()

## Summary

New `app/services/upstream/anthropic.py`: pure `build_request` / `map_response` / `dropped_params`, plus `AnthropicAdapter` whose `complete()` builds an SDK client per call, calls `messages.create`, and maps SDK exceptions. `stream()` raises non-retryable `incompatible` ("streaming arrives with STORY-007"). Registered in `_ADAPTER_FACTORIES`, replacing `_anthropic_unavailable`. Pipeline wiring (`ignored_params` rows, STORY-008) and the stub's anthropic mode (STORY-006) are out of scope.

- Story: `.agents/stories/PRD-022-provider-fallback-and-native-adapters/STORY-005-anthropic-adapter-complete.md`
- PRD sections: 6.5 (all), 6.6 (only the `reasoning` thinking request), D2, D4, D14; STORY-001 report AC4 (SDK facts)
- Systems affected: `app/services/upstream/` only, plus tests

## Design Decisions

- **Construction (binding).** `anthropic.Anthropic(api_key=key, base_url=provider.base_url, timeout=provider.timeout_seconds, max_retries=0, http_client=anthropic.DefaultHttpxClient(follow_redirects=False))`, built per call by a module function `_open_sdk_client(provider, api_key)` and closed after the call. The seam's `client: httpx.Client` is ignored: the factory becomes `lambda provider, client: AnthropicAdapter(provider)`. Test injection: `AnthropicAdapter(provider, sdk_client=None)`; an injected client is used as is and never closed. The explicit `timeout` also avoids the SDK's "streaming is recommended" ValueError for large non-streaming `max_tokens` (assert with `default_max_tokens` 64000).
- **How the model reaches the adapter (smallest change).** `UpstreamRequest` carries `upstream_model` only. Looking up `Provider.models` by `upstream` is ambiguous when two catalogue ids share an upstream id with different capabilities, and a registry call from the adapter would break its purity. So add ONE defaulted field `model: Optional[Any] = None` to `UpstreamRequest` (`upstream/types.py:101-108`), set from `route.model` at the two construction sites `upstream/__init__.py:140,163`. It is typed `Any` because `v1_translate` imports `upstream.types` and `tests/test_v1_translate_request.py:328` AST-checks its imports (no registry import, not even under `TYPE_CHECKING`). No seam signature changes; `openai_compatible` ignores it. `CatalogModel.capabilities` also supplies `reasoning`, which `complete()` has no kwarg for (the protocol only has it on `stream`). `query_pipeline.py:1082` builds its own streaming `UpstreamRequest`: leave it (STORY-007/012 pass `model=`). A `None` model on an anthropic route cannot happen (passthrough is refused for anthropic, `provider_registry.py:404`); if it does, raise `incompatible`.
- **Pure functions.** `build_request(request, model, *, provider) -> dict` (provider only for the error label/name; the two positional args are as specified), `map_response(message, provider) -> UpstreamResult`, `dropped_params(request, model) -> tuple[str, ...]`. `complete()` = `build_request` (raises before any network) -> SDK call -> `map_response` -> `dataclasses.replace(result, dropped_params=...)`. `message` is duck-typed (`.content` blocks with `.type`, `.stop_reason`, `.usage`, `.model`).
- **Allowlist (T9).** `ANTHROPIC_REQUEST_KEYS = frozenset({"model","messages","max_tokens","system","tools","tool_choice","stop_sequences","temperature","top_p","thinking","cache_control"})`. Tests: `set(body) <= ALLOWLIST` over varied requests; `==` for a fully populated one.
- **Incompatible, never guessed, before the network.** `UpstreamError(f"{label}: <rule>", kind="incompatible", retryable=False, provider=provider.name)`; the message names the rule only, never request text (T10). Triggers: `json.loads(arguments)` fails or is not a `dict`; `tool_choice` `"required"`/named while `not capabilities.forced_tool_choice`.
- **Dropped channel.** `UpstreamResult.dropped_params: tuple[str, ...] = ()` declared last (`types.py:56-60` precedent). `UpstreamResult` is a plain non-frozen `@dataclass` (`types.py:~53`), not frozen as the brief assumed, so a defaulted last field leaves every existing construction (`reply.py`, `collect.py`, openai_compatible, tests) unchanged. Bare names, order `temperature`, `top_p`, only when the request set them and `sampling_params` is false. `name@provider` and the audit wiring are STORY-008. `collect()` is untouched (STORY-007 decides streaming).
- **Message mapping (6.5) and edge cases.**
  - System turns: hoisted wherever they occur, in order, joined `"\n\n"` into a string `system`; key omitted when none. A non-leading system turn loses its position (PRD says so); a test pins it.
  - user -> `{"role":"user","content":[{"type":"text","text":c}]}`. assistant: a text block only if `content != ""`, then one `tool_use` per call (`input=json.loads(arguments)`). `""` + tool_calls gives no empty text block.
  - Consecutive `tool` turns -> ONE user message, one `{"type":"tool_result","tool_use_id","content"}` each, in order.
  - **Tool turn followed by a user turn: two separate user messages, not merged.** The Messages API documents that consecutive same-role turns are combined server-side (tool_result blocks stay first, which is what it requires); client-side merging would add a rule the PRD table lacks. A test pins the two messages.
  - Tools: OpenAI `{"type":"function","function":{name,description?,parameters?,strict?}}` -> `{"name","description"?,"input_schema": parameters or {"type":"object"},"strict"?}`.
  - `tool_choice`: `none`->`{"type":"none"}`, `auto`->`{"type":"auto"}`, `required`->`{"type":"any"}`, named->`{"type":"tool","name"}`. `parallel_tool_calls is False` adds `disable_parallel_tool_use: True` to auto/any/tool, never to `none` (the SDK type does not allow it); with no `tool_choice`, send `{"type":"auto","disable_parallel_tool_use":True}`. No tools: neither key.
  - `max_tokens` = `params.max_tokens` else `model.default_max_tokens`; `stop` str -> `[str]`, list -> list; `temperature`/`top_p` only with `sampling_params`; `prompt_cache == "auto"` -> `cache_control: {"type":"ephemeral"}`; `capabilities.reasoning` -> `thinking: {"type":"adaptive","display":"summarized"}` (D14; STORY-001 AC4). Thinking text never enters `response`.
- **Response.** `text` blocks concatenated; `tool_use` -> `ToolCallSpec(id, name, json.dumps(input, ensure_ascii=False, separators=(",",":")))`; `thinking`/`redacted_thinking` only `reasoning_blocks += 1`. `stop_reason`: `end_turn`/`stop_sequence`->`stop`; `max_tokens`/`model_context_window_exceeded`->`length`; `tool_use`->`tool_calls`; `refusal`->`content_filter`; `pause_turn`, None or unknown -> `shape` (non-retryable, provider set). `usage` None -> `shape`. `input_tokens = input + cache_creation + cache_read` (None cache field = 0), `output_tokens`, `tokens_used` = their sum, `cache_write_tokens`/`cache_read_tokens` set, `usage_estimated=False`. No text and no tool call -> `shape` (STORY-002 precedent). Messages never carry body text.
- **Error order** (`_sdk_error(exc, provider)`): `APITimeoutError` -> `timeout` retryable; `APIConnectionError` -> `transport` retryable; `AuthenticationError` -> `misconfigured`, status 401, not retryable; `RateLimitError` -> `status` 429 retryable, `retry_after_seconds` from `exc.response.headers.get("retry-after")` (digits only, `max(1, n)`, else None; mirror `openai_compatible.py:83-93`); `InternalServerError` (incl. 529) -> `status` retryable with `exc.status_code`; other `APIStatusError` (incl. 3xx) -> `status` non-retryable; `APIResponseValidationError`/other `anthropic.APIError` -> `shape`. Messages: `f"{label} request failed: HTTP {status}"`, `"... timed out"`, `"... connection error"`; **never `str(exc)`** (SDK text can quote the body). The key lives in client headers, not in the exception; a test searches `str` and `repr` of every mapped error for the key.

## Skills In Use

None apply (`.agents/skills/` holds only `frontend-design`). STORY-001's report is the SDK fact source.

## Patterns to Follow

| Category | Source | What to mirror |
|----------|--------|----------------|
| Module docstring, PRD cites | `upstream/openai_compatible.py:1-9` | "no registry access, no settings" |
| Wire builder per message | `openai_compatible.py:33-49` | one small function per shape |
| Error construction | `openai_compatible.py:104-141` | `UpstreamError(f"{provider.label} ...", upstream_status, retryable, provider=provider.name, kind=)` |
| retry-after | `openai_compatible.py:83-93` | digits only |
| Shape errors | `openai_compatible.py:160-165` | `kind="shape"`, label prefix |
| Factory registry | `upstream/__init__.py:83-115` | replace `_anthropic_unavailable` |
| Defaulted result field | `types.py:56-60` | comment citing PRD-022 STORY, last with default |
| SDK exceptions in tests | `tests/test_prd022_spike_anthropic_sdk.py:100-117,190-215` | stub server and `_client` helper |
| File-mode registry | `tests/test_stream_upstream_seam.py:403-418` (`_anthropic_yaml`), `tests/_providers.py:50` | `provider_file` fixture |

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/upstream/anthropic.py` | CREATE | pure mapping, error mapping, `AnthropicAdapter` |
| `app/services/upstream/types.py` | UPDATE | `UpstreamResult.dropped_params`, `UpstreamRequest.model` |
| `app/services/upstream/__init__.py` | UPDATE | register adapter, drop `_anthropic_unavailable`, `model=route.model` at two sites, export |
| `tests/test_anthropic_adapter.py` | CREATE | all ACs, no network |
| `tests/test_stream_upstream_seam.py` | UPDATE | STORY-004 dispatch tests (Task 5) |
| `tests/test_pii_redaction_integration.py` | UPDATE if a test is renamed | `_DELIBERATELY_SUPERSEDED_TESTS` (`:516`) |

## Tasks

### Task 1: types
- `types.py`: add the two defaulted fields with PRD-022 STORY-005 comments (import `Any`). Grep `tests/` for `UpstreamRequest(` and `dataclasses.fields(` first.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_upstream_error_fields.py tests/test_v1_translate_request.py`

### Task 2: pure mapping (`anthropic.py`)
- `ANTHROPIC_REQUEST_KEYS`, `build_request`, `dropped_params`, `map_response`, `_incompatible(provider, rule)`. No settings, registry, network or client construction in these. `import anthropic` is for exception classes and the client only.

### Task 3: `AnthropicAdapter`
- `__init__(provider, *, sdk_client=None)`; `complete()` per above (own client closed in `finally`, injected one not). `stream(...)` is a plain function raising `UpstreamError(f"{label}: streaming arrives with STORY-007", provider=name, kind="incompatible")` at call time (keeps `reasoning` kwarg for the protocol).

### Task 4: register
- `upstream/__init__.py`: `"anthropic": lambda provider, client: AnthropicAdapter(provider)`; delete `_anthropic_unavailable`; `model=route.model` in both `UpstreamRequest(...)` calls; `__all__`.

### Task 5: STORY-004 tests (`tests/test_stream_upstream_seam.py:408-440`)
- `test_call_upstream_on_an_anthropic_model_is_incompatible_until_story_005`: replace by `test_call_upstream_dispatches_to_the_anthropic_adapter` (monkeypatch `anthropic_mod._open_sdk_client` to a fake; assert text and `model_used == "claude-x"`), comment citing PRD-022 STORY-005; register the old name in `_DELIBERATELY_SUPERSEDED_TESTS`.
- The stream test stays valid (`AnthropicAdapter.stream` raises the same kind/provider, no prompt text); add a comment citing STORY-005. `_assert_unavailable` unchanged.

### Task 6: `tests/test_anthropic_adapter.py` (fake `sdk_client` with `.messages.create(**body)` recording the body; SDK exceptions built as in the spike test)
- Request rows one by one (list in Design Decisions), including non-leading system, `""` + tool_calls, two tool turns, tool then user turn, `parallel_tool_calls` on each choice, `max_tokens` default/override, `stop`, sampling dropped vs sent, `cache_control`, `thinking` only with `reasoning`.
- T9 allowlist subset and exact-set tests.
- Incompatible: arguments `"[1]"`, `"not json"`, `"3"`; `required` and named without `forced_tool_choice`; `create` never called, `retryable False`, label prefix, no prompt text.
- Response: concat, canonical tool JSON (non-ASCII kept, no spaces), thinking counted not emitted, all seven stop reasons, `pause_turn` and missing usage -> shape, usage 11/5/7 -> prompt 23 with cache fields, `dropped_params == ("temperature","top_p")` through `complete()`.
- Errors: every SDK class -> kind/status/retryable; retry-after `"7"`->7, `"0"`->1, date/absent->None; 529 `OverloadedError`; 307 -> non-retryable `status`; timeout not shadowed by connection; key absent from `str`/`repr`.
- Construction: `_open_sdk_client` has `max_retries == 0`, `timeout`, `base_url`, no-redirect http client; owned client closed, injected not.
- `stream()` raises `incompatible`; one loopback stub-server test proving the real SDK path (Bearer header, canned message, 307 non-retryable).

## End-to-End Tests

- [ ] `call_upstream` on a file-mode anthropic catalogue model with the fake SDK client returns text, tool call, `finish_reason`, `model_used` = requested id.
- [ ] `tests/test_upstream_adapter.py` and `tests/test_prd020_legacy_fixtures.py` pass unmodified (openai_compatible untouched).

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_anthropic_adapter.py tests/test_stream_upstream_seam.py tests/test_upstream_adapter.py tests/test_upstream_error_fields.py tests/test_upstream_stream_collect.py tests/test_prd022_spike_anthropic_sdk.py tests/test_v1_translate_request.py tests/test_untouched_app.py tests/test_pii_redaction_integration.py
```

## Acceptance Criteria -> Tasks -> Tests

| AC | Task(s) | Test that proves it |
|----|---------|---------------------|
| AC1 request table + allowlist | 2, 6 | `test_anthropic_adapter.py`: row tests, `test_request_keys_within_allowlist`, `test_fully_populated_request_has_exact_allowlist` |
| AC2 incompatible before network | 2, 3, 6 | `test_incompatible_*` (create never called) |
| AC3 response mapping, tokens, shapes | 2, 6 | `test_map_response_*`, `test_usage_sums_cache_tokens`, `test_pause_turn_is_shape`, `test_missing_usage_is_shape` |
| AC4 SDK error mapping, label, no key | 3, 6 | `test_sdk_error_mapping[...]`, `test_key_never_in_error` |
| AC5 dropped params, cache_control, construction, no network | 1, 2, 3, 6 | `test_dropped_params_reported`, `test_prompt_cache_auto`, `test_client_construction` |
| Registered; STORY-004 tests updated | 4, 5 | `test_call_upstream_dispatches_to_the_anthropic_adapter` |

## Open risks / questions
- The API rejects `thinking` with a forced `tool_choice` (any/tool). With `reasoning` on plus a forced choice, both are sent and a 400 surfaces as non-retryable `status`. Not guessed; the orchestrator may want an `incompatible` rule.
- An empty user `content` would yield an empty text block (API 400); the normalizer is assumed to prevent it.
- `UpstreamRequest.model: Any` is a typing compromise forced by `v1_translate`'s AST purity test.

## Orchestrator corrections (binding)

- Thinking + forced tool choice (Risk above): resolved. When `capabilities.reasoning` is on AND `tool_choice` is `required` or named, `build_request` raises `UpstreamError(kind="incompatible")` before any network call (the Messages API rejects `thinking` with `any`/`tool` choice; PRD-022 6.5, D7: an incompatible request makes the candidate ineligible, it is not sent to fail with a 400). Message: `<label>: forced tool_choice cannot be combined with extended thinking`. Add one test next to the other AC2 incompatibility tests (asserting `create` is never called).
- `UpstreamRequest.model: Optional[Any] = None` accepted as planned; its comment cites PRD-022 STORY-005 and the v1_translate import guard.
- Empty user `content`: if the normalizer can pass `""` for a user turn, emit no text block for it only if the message still has other blocks; otherwise keep the empty text block (the API's 400 is the honest outcome). Do not invent content.
