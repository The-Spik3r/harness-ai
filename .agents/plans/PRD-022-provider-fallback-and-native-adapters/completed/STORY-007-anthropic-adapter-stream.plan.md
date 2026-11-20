---
story: STORY-007
prd: PRD-022
slug: anthropic-adapter-stream
title: AnthropicAdapter.stream() — events, buffered tool input, ReasoningDelta, collect property
type: NEW_CAPABILITY
complexity: medium
epic_branch: epic/PRD-022-provider-fallback-and-native-adapters
created: 2026-11-20
---

# Plan: AnthropicAdapter.stream()

## Summary

Replace the `incompatible` placeholder (`app/services/upstream/anthropic.py:354-362`) with a real `stream()` built on `client.messages.create(**body, stream=True)` (raw SSE events, not the SDK's accumulating `messages.stream` helper). The mapping rules living in `map_response` (`:223-265`) and `_sdk_error` (`:274`) are factored into small pure helpers that both paths call; `complete()` behaviour is unchanged. A property test replays the STORY-006 stub scripts through `complete()` and `collect(stream())`.

- Story: `.agents/stories/PRD-022-provider-fallback-and-native-adapters/STORY-007-anthropic-adapter-stream.md`
- PRD sections used: 6.6, 6.5 (D4), 6.2/T4, F2, D14
- Systems affected: `upstream/anthropic.py`, its tests, `tests/test_stream_upstream_seam.py`

## Design Decisions

- **Plain function + inner generator.** `stream()` stays a plain function: it runs `build_request` (pure, so `incompatible`, incl. thinking + forced tool_choice, raises at call time before any network) and the owned-client no-key check (`:336-341`), then returns `self._events(...)`. The SDK client is opened and the request sent on the first `next()`. `openai_compatible.py:202` is itself a generator (all its errors surface on first `next()`); mirror the `stream_upstream` plain-function contract (`upstream/__init__.py:141-153`) instead. The generator owns client and SDK stream and closes both in `finally` (`complete()`'s `owns_client` rule, `:335-352`; an injected client is never closed).
- **Reasoning flag.** `build_request` gains keyword `reasoning: Optional[bool] = None` (None = `capabilities.reasoning`, so `complete()` is unchanged). `stream()` passes its own `reasoning`; it decides the `thinking` request key (STORY-001 shape, `:207`) and the forced-tool_choice check (`:187`). `stream_upstream` passes `route.capabilities.reasoning` (`__init__.py:152`), so both agree in production.
- **Shared helpers (pure, module level, used by both paths):**
  - `_canonical_arguments(value) -> str`: the `json.dumps(..., ensure_ascii=False, separators=(",", ":"))` now inline at `:233`.
  - `_finish_reason(stop_reason, provider)`: `_FINISH_REASONS.get` or `_shape("unsupported stop reason")` (`:237-239`).
  - `_check_answer(text, has_calls, finish, provider)`: the refusal rule at `:246-247`.
  - `_usage_counts(usage) -> (prompt, completion, cache_write, cache_read)`: `:248-252`.
  - `_timeout_error` / `_transport_error(provider)`: the two constructions at `:279-285`.
  `map_response` and `_sdk_error` call them; their tests (`tests/test_anthropic_adapter.py:343-430, 456-525`) stay unmodified and green.
- **Event mapping** (dispatch on `event.type`):
  - `message_start`: keep `message.usage` (input + both cache fields; the stub puts them here with `output_tokens=1`). Emit nothing.
  - `content_block_start`: record `index -> kind`; tool blocks keep id/name and get a running ordinal 0..n-1 used as `ToolCallDelta.index` (as the OpenAI adapter's tool index; `collect` sorts by it). `redacted_thinking` and unknown kinds are recorded as ignored.
  - `content_block_delta`: `text_delta` -> `TextDelta` (skip `""`); `thinking_delta` -> `ReasoningDelta` only if `reasoning` and text non-empty; `input_json_delta` -> append `partial_json` to that block's buffer; `signature_delta`, `citations_delta` and unknown -> ignored.
  - `content_block_stop` on a tool block: `json.loads(buffer or "{}")` (a no-arg tool sends no fragments; non-stream gives `input: {}`), must be a `dict`, else `_shape(provider, "tool input is not a JSON object")`; emit exactly one `ToolCallDelta(ordinal, id, name, _canonical_arguments(parsed))`.
  - `message_delta`: merge `usage` over the `message_start` usage (non-None fields win; both real API and stub send cumulative `output_tokens` here). No usage anywhere -> `_shape("no usage")`. Then `_finish_reason`, `_check_answer` (tracks whether text/tool was emitted), then yield `UsageReport(prompt, completion, total_tokens=prompt+completion, cache_read, cache_write)` and `Finish(reason)`. `total_tokens` is always set so `collect` never takes the D8 estimate path (parity with `usage_estimated=False`, `:261`).
  - `message_stop`: mark done. `ping`/unknown: ignored. Iterator ends without `message_stop`/`Finish` -> `_shape("stream ended without a stop")`. Nothing synthetic is ever yielded (one exception below).
- **Empty refusal must collect.** `collect` maps "no TextDelta" to `content=None` and `result_from_reply` then raises (`reply.py` "no text content"), diverging from `complete()` (`27e0e91`). Fix inside the adapter, leaving PRD-020 modules alone: in the empty `content_filter` case yield one `TextDelta("")` before `UsageReport`/`Finish`; `collect` then gives `response=""` (`collect.py:86`: `[""]` is truthy). Pinned by test. (Open question 2.)
- **Errors.** Loop wrapped in `except anthropic.APIError as exc: raise _sdk_error(exc, provider) from None` (an SSE `event: error` raises `APIStatusError`, `anthropic/_streaming.py:99-112`) and `except httpx.TransportError` (the SDK does not wrap read errors during iteration): `httpx.TimeoutException` -> `_timeout_error`, else `_transport_error`. Our own `UpstreamError`s pass through. `from None` always (T10); no event text, buffer or key in any message.
- **Deadline.** Not in scope: `timeout_seconds` is the SDK per-read timeout; the total deadline (PRD-021 D20 on the OpenAI path) belongs to STORY-014's per-attempt timeout. Say so in the report.

## Skills In Use

None: `.agents/skills/` has only `frontend-design`; no `chat_ui/` change.

## Patterns to Follow

| Category | Source | What to mirror |
|---|---|---|
| Seam contract | `upstream/__init__.py:141-153` | plain function, call-time errors, lazy network |
| Close in `finally`, no-Finish error | `openai_compatible.py:225-256`, `anthropic.py:335-352` | owned client closed on end/early close/failure |
| Error mapping | `anthropic.py:274-310` | `_sdk_error`, `from None`, label prefix, no `str(exc)` |
| Fake SDK | `tests/test_anthropic_adapter.py:83-100` | `_FakeClient`; add a `create(stream=True)` returning an event iterable |
| Stub harness | `tests/test_stub_anthropic_mode.py:39-56, 396-470` | `stub` fixture, `endpoint_hits()`, `_provider`, `_upstream_request` |
| Seam tests | `tests/test_stream_upstream_seam.py:321, 340, 411-460` | `provider_file`, `_anthropic_yaml`, eager/lazy asserts |

## Files to Change

| File | Action | Purpose |
|---|---|---|
| `app/services/upstream/anthropic.py` | UPDATE | helpers, `reasoning` kw, `stream()` + `_events`, shared transport errors, docstring `:8` |
| `tests/test_anthropic_stream.py` | CREATE | event mapping, errors, lifecycle (fake SDK, no network) |
| `tests/test_anthropic_stream_stub.py` | CREATE | property test and error parity on the STORY-006 stub, real SDK over loopback |
| `tests/test_anthropic_adapter.py` | UPDATE | `:590` asserts the removed placeholder |
| `tests/test_stream_upstream_seam.py` | UPDATE | anthropic eager/lazy seam test |
| `tests/test_pii_redaction_integration.py` | UPDATE | `_DELIBERATELY_SUPERSEDED_TESTS` (`:521`) gets the replaced test name |

## Tasks

### Task 1: Factor the shared helpers (no behaviour change)
- **File**: `app/services/upstream/anthropic.py`. Add the helpers; `map_response`/`_sdk_error` call them; error text identical.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_anthropic_adapter.py -k "not stream_raises"`

### Task 2: `build_request(..., reasoning=None)`
- Effective reasoning = `capabilities.reasoning if reasoning is None else reasoning` at `:187` and `:205`. No existing caller changes.

### Task 3: `stream()` and `_events`
- Per Design Decisions; `import httpx` (already a dependency). Update the module docstring (`:8`).
- **Mirror**: `openai_compatible.py:202-256`; `complete()` for client lifecycle.

### Task 4: `tests/test_anthropic_stream.py` (fake SDK)
- Text deltas in order. Tool fragments split mid-JSON -> one `ToolCallDelta`, canonical compact `ensure_ascii=False` string, emitted at `content_block_stop` and not before; parallel tools get ordinals 0/1 with ids and names; empty buffer -> `{}`.
- Thinking: `reasoning=True` yields only non-empty `ReasoningDelta`s and the body has `thinking == {"type":"adaptive","display":"summarized"}`; `reasoning=False` yields none and `thinking` is absent from the recorded body even if `capabilities.reasoning`; `redacted_thinking` and `signature_delta` never emitted.
- Usage: `message_start` + `message_delta` merge, cache fields on `UsageReport`, `total == prompt + completion`, no usage anywhere -> `shape`.
- Stop reasons parametrized like `:367-378`; `pause_turn`/None -> `shape`; empty refusal -> `TextDelta("")`, `UsageReport`, `Finish("content_filter")`; empty `end_turn` -> `shape`.
- Errors: no `message_stop` -> `shape` and no `Finish` in the yielded list; unparseable / non-object tool input -> `shape`; `APIConnectionError`, `APITimeoutError`, `httpx.ReadError`, `httpx.ReadTimeout` mid-iteration -> `transport`/`timeout` retryable; `RateLimitError` -> 429 with `retry_after_seconds` (reuse `_status_error`, `:456`); messages hold no scripted text or key.
- Lifecycle: `create` not called until first `next()`; `incompatible` (non-object history arguments, forced choice without capability, forced choice with `reasoning=True`) raises from `stream(...)` itself with zero `create` calls; owned client closed on exhaustion, on `.close()` mid-stream and on error; injected never closed; no key + owned client -> `misconfigured` at call time.

### Task 5: `tests/test_anthropic_stream_stub.py` (the property test)
- Use the STORY-006 stub (`make_server`, `stub` fixture pattern from `test_stub_anthropic_mode.py:39`; no ad-hoc server), `require_key`, port 0, fixture teardown.
- Scripts: text; one tool; parallel tools; thinking (`stream: {reasoning: ...}`); empty refusal; refusal with text; cache usage; `max_tokens`; `stream.chunk_chars: 3` for text and tool args.
- Each: `a = adapter.complete(r, KEY)`; `b = collect(adapter.stream(r, KEY, reasoning=True), provider=p, request=r)`; equal on all fields except `reasoning_blocks` and `dropped_params` (Open question 1), neutralized with `dataclasses.replace`. Tool scripts use a request with `tools=` (collect's gate). Separately: `a.reasoning_blocks == 1` for the thinking script; the stream's `ReasoningDelta`s concatenate to the scripted summary with `reasoning=True`, none with `False`; neither the thinking text nor `stub-signature` is in `b.response` or in any non-Reasoning event.
- Error parity on the same server: `fail_status` 503 / 429 (`retry_after`) / 401 give the same kind, status, retryable from `complete()` and from the first `next()`; `stream.fail_after: 1` -> `shape`; `fault: timeout` with `timeout_seconds=1.0` -> `timeout` (`< 8 s` bound as at `:468`); `fault: malformed`: run it, pin the observed kind in a closed set; `usage: null` -> `shape` from both.
- Hits: `server.endpoint_hits() == {"chat": 0, "messages": N}`; calling `stream(...)` without iterating leaves `messages == 0`; the log never contains the key.

### Task 6: Placeholder test and seam test
- `tests/test_anthropic_adapter.py:590`: replace `test_stream_raises_incompatible_at_call_time` with `test_stream_raises_incompatible_at_call_time_for_a_request_it_cannot_carry` (comment cites PRD-022 STORY-007, D4); register the old name under `"tests/test_anthropic_adapter.py"` in `_DELIBERATELY_SUPERSEDED_TESTS`.
- `tests/test_stream_upstream_seam.py`: add an anthropic route test (mirror `:321`, `:340`, YAML from `_anthropic_yaml`, `base_url` at the stub): unknown model and missing key raise at call time with zero hits; first `next()` makes `hits == 1`.

## End-to-End Tests

- [ ] Real SDK + local stub: `collect(stream) == complete` for every script (Task 5).
- [ ] `stream_upstream("<anthropic model>")` through the registry against the stub: events drain, `Finish` last, cache usage present, one `messages` hit (Task 6). Pipeline wiring is STORY-012/014, not here.

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_anthropic_stream.py tests/test_anthropic_stream_stub.py tests/test_anthropic_adapter.py tests/test_stub_anthropic_mode.py tests/test_stream_upstream_seam.py tests/test_upstream_stream_collect.py tests/test_upstream_adapter.py tests/test_untouched_app.py
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_pii_redaction_integration.py -k "superseded or deliberately or removed"
```
One pytest process at a time. Pick the last `-k` from the real guard test name near `test_pii_redaction_integration.py:589`.

## Acceptance Criteria -> Tasks -> Tests

| AC | Task(s) | Test that proves it |
|---|---|---|
| AC1 mapping, buffered tool input, Finish + cache usage | 1, 3, 4 | `test_anthropic_stream.py` text / tool / parallel / usage cases |
| AC2 thinking on/off, no redacted/signature | 2, 3, 4, 5 | `test_anthropic_stream.py` thinking cases; stub thinking script |
| AC3 `collect(stream) == complete` over all stub scripts | 3, 5 | `test_anthropic_stream_stub.py` property test |
| AC4 no stop / bad tool input / mid-stream SDK error | 3, 4, 5 | `test_anthropic_stream.py` error cases; stub `fail_after`, faults |
| AC5 seam eager route/key errors, lazy network | 3, 6 | `test_stream_upstream_seam.py` new test; `endpoint_hits()` in Task 5 |

## Open questions / deviations (for the orchestrator)

1. **`reasoning_blocks` cannot survive `collect()`.** The brief wants thinking blocks counted into `reasoning_blocks` so `collect(stream) == complete`. `collect()` is pure and PRD 6.6 says it ignores `ReasoningDelta`; no event carries a block count, and with `reasoning=False` the stream emits nothing at all for `complete()`'s count to match. Equality can hold only with `reasoning_blocks` (and the `complete()`-only `dropped_params`) neutralized; the plan does that and tests the count on `complete()` and the `ReasoningDelta` text on `stream()` separately. A real count needs a new event type or a `collect` change (PRD-020 modules): decide before implementing if wanted.
2. **Empty refusal emits `TextDelta("")`**, the only synthetic event, with no content, so `collect` equals `complete()`. The alternative (tolerate `content_filter` without text in `collect`/`reply.py`) touches PRD-020 modules and OpenAI-path behaviour.
3. **In-stream `overloaded_error`.** Anthropic sends it as an SSE `error` event under HTTP 200; `_sdk_error` would give `status`, `upstream_status=200`, non-retryable, so a chain would not fall back. Not in the ACs, left as is; suggest a follow-up mapping `body.error.type in {overloaded_error, api_error}` to retryable (STORY-014 or a small fix).

## Orchestrator corrections (binding, 3.2 review)

- OQ1 accepted: the property test neutralizes `reasoning_blocks` and `dropped_params`; `reasoning_blocks` has no consumer outside the adapter (`grep` app/), so a stream-path count of 0 is harmless. Document it in the report as a known limitation.
- OQ2 accepted: the single `TextDelta("")` for an empty refusal is allowed; pin it in tests and comment it (PRD-022 T4, fix 27e0e91).
- OQ3 is IN scope (AC4 "mapped status"): an in-stream SSE `event: error` reaches us as `APIStatusError` with `status_code == 200` (`anthropic/_streaming.py:98-111`, `_make_status_error` on the 200 response). In the stream path only, map it from `exc.body["error"]["type"]` before falling back to `_sdk_error`: `overloaded_error` -> kind `status`, `upstream_status=529`, retryable; `api_error` -> 500, retryable; `rate_limit_error` -> 429, retryable (no Retry-After available); `authentication_error`/`permission_error` -> `misconfigured` (401/403), not retryable; any other type or unparseable body -> `status`, `upstream_status=502`, not retryable. Never put the body text in the message (T10). Add a pure helper `_in_stream_error(exc, provider)` with fake-SDK tests for each row, and one stub test if the stub can script an in-stream `error` event (if it cannot, say so in the report; do not extend the stub).
