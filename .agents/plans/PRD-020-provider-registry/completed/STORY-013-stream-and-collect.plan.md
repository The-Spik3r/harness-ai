---
story: STORY-013
prd: PRD-020
slug: stream-and-collect
title: Adapter stream() with normalized events and pure collect()
type: NEW_CAPABILITY
complexity: large
epic_branch: epic/PRD-020-provider-registry
created: 2026-11-18
---

# Plan: Adapter stream() with normalized events and pure collect()

## Summary

`complete()` is split into shared pieces so `stream()` and `collect()` reuse, not copy, its rules: `_payload`, HTTP error/redirect classification, and `result_from_reply(provider, request, data)` (everything after `resp.json()`). `stream()` is a sync generator over an SSE parser that yields frozen-dataclass events. `collect(events, *, provider, request)` assembles a reply dict equal to the non-stream body and calls `result_from_reply`. The stub learns SSE. A property test proves `collect(stream(r)) == complete(r)`. No production caller of `stream()`; `call_upstream` is untouched.

- Story: `.agents/stories/PRD-020-provider-registry/STORY-013-stream-and-collect.md`
- PRD sections used: 6.4, 6.7 (D8), F6, 9.2 T7, D8, D11, D13
- Systems affected: `app/services/upstream/`, `scripts/stub_openrouter.py`, PRD 6.4 text, tests

## Design Decisions (binding, from the orchestrator)

- **Signature** `collect(events, *, provider: Provider, request: UpstreamRequest) -> UpstreamResult`, pure. The keywords are needed for `_resolve_usage` (D8 estimate), the tools= gate (calls parsed only when `request.tools is not None`) and `model_used = request.upstream_model`. Deviates from 6.4's one-arg sketch: amend PRD 6.4 (the `collect` line in the code block, and the In Scope bullet at PRD `:62`) and record the deviation in the report. `call_upstream` still calls `complete()` only.
- **Protocol**: `ProviderAdapter` gains `stream(request, api_key) -> Iterator[UpstreamEvent]`.
- **One path, no fork**; `complete()` bytes and message texts unchanged (existing tests pass unmodified; `complete` sends no `stream` key).
- **Assembly**: content = `"".join` of TextDelta; no TextDelta -> `content: None` (null-content rules apply as in complete); `TextDelta("")` counts as present. Calls grouped by `index`, emitted in ascending order; id/name = first non-None seen; arguments = concatenation, never parsed (D13); the list goes through `_parse_tool_calls` (a missing name or duplicate id fails with the same field-naming text). The raw `tool_calls` key is set whenever any ToolCallDelta was seen, so the gate-off "tool calls are not supported" error note survives. Finish: last `Finish.reason` -> `finish_reason`. Usage: last `UsageReport` wins and becomes a `usage` dict of its non-None fields; none -> no `usage` key (D8 "absent").
- **Null usage field = absent in streaming** (document in `collect`'s docstring). Checked: the stub always emits all three usage fields as non-negative ints (`_parse_usage`, `stub_openrouter.py:~236`) and `usage: null` omits the chunk, so no script or test reply makes null-vs-absent differ under `usage_missing: error`. Only a real provider sending `total_tokens: null` diverges: `complete()` (error mode) returns the raw None, `collect` raises "'total_tokens'". Flagged, not a stub case. UsageReport passes wire values through unvalidated (so error mode keeps its raw-total rule); `_resolve_usage` validates.
- **Parser** (T7: names the field, never quotes a value; all non-retryable `UpstreamError`, prefix `"{label} returned an unexpected response shape: "`): ignore blank lines and `:` comments; `data: [DONE]` ends; other `data:` payload must be a JSON object ("stream data is not JSON" / "is not an object"); chunk `usage` object -> UsageReport; `choices[0].delta.content` str -> TextDelta; `delta.tool_calls[i]` -> ToolCallDelta (int, non-bool `index`, else error naming `delta.tool_calls[i].index`; the first delta for an index must carry `id`, else error naming `delta.tool_calls[i].index`); `choices[0].finish_reason` str -> Finish; `choices: []` is fine. EOF without `[DONE]` -> "stream ended without [DONE]".
- **Lazy**: `stream()` is a generator, so the request is sent and errors raise on the first `next()`. It owns and closes client and response in `finally`, `follow_redirects=False`, same redirect/HTTP-error handling; a transport error mid-read goes through the shared classifier.

## Skills In Use

None. `.agents/skills/` holds only `frontend-design` (UI); nothing here touches `chat_ui/`.

## Patterns to Follow

| Category | Source | What to mirror |
|----------|--------|----------------|
| Body to split | `app/services/upstream/openai_compatible.py:157-258` | payload `:167-186`; redirect/HTTP block `:193-211`; post-`json()` `:213-244`; usage `:246-248` |
| Moved helpers | `openai_compatible.py:14-103` (`_token_count`, `_parse_tool_calls`), `:121-154` (`_resolve_usage`) | move verbatim, same prefix and field naming |
| Event types | `app/services/upstream/types.py:50-76` | frozen dataclasses, `Optional` defaults, PRD-020 comments |
| Pure module | `app/services/usage_estimate.py:1-8` | pure docstring; `TYPE_CHECKING` for annotation-only imports |
| Stub reply/log | `scripts/stub_openrouter.py` `do_POST` (`:438-`), log `:465-469`, header note `:63-64` | `stream=` after `auth=`; `_send_json` pattern |
| Stub tests | `tests/test_stub_openrouter.py:293` (header value never logged), `:757` (`auth=` presence) | the no-header-value test already exists; extend it with a streaming request |
| Adapter tests | `tests/test_upstream_adapter.py:46-66` (`_FakeClient`, `_response`), `:70-` (`stubs` fixture) | free-port stub; MockTransport |

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/upstream/reply.py` | CREATE | pure: `_token_count`, `_parse_tool_calls`, `_resolve_usage`, `result_from_reply`, moved from `openai_compatible.py` (no httpx import, so `collect` stays pure) |
| `app/services/upstream/sse.py` | CREATE | pure `parse_events(lines: Iterable[str], label) -> Iterator[UpstreamEvent]` |
| `app/services/upstream/collect.py` | CREATE | pure `collect(...)` |
| `app/services/upstream/types.py` | UPDATE | `TextDelta`, `ToolCallDelta`, `UsageReport`, `Finish`, `UpstreamEvent`; `ProviderAdapter.stream` |
| `app/services/upstream/openai_compatible.py` | UPDATE | import moved helpers; `_payload`, shared HTTP classification, thinner `complete()`, new `stream()` |
| `app/services/upstream/__init__.py` | UPDATE | export `collect` and the event types (`__all__`) |
| `scripts/stub_openrouter.py` | UPDATE | SSE branch, `stream=yes\|no` log field, header note `:63-64` |
| `.agents/PRDs/PRD-020-provider-registry/PRD.md` | UPDATE | 6.4 `collect` signature + In Scope bullet, deviation note |
| `tests/test_upstream_stream_collect.py` | CREATE | property, malformed-stream and payload tests |
| `tests/test_stub_openrouter.py` | UPDATE | `stream=yes\|no` log, SSE body shape |

## Tasks

### Task 1: Event types and protocol
- **File**: `app/services/upstream/types.py`. Four frozen dataclasses per the design; `UpstreamEvent = Union[...]`; `ProviderAdapter.stream(self, request, api_key) -> Iterator[UpstreamEvent]`; cite PRD-020 D11.
- **Validate**: `.venv/Scripts/python -c "from app.main import app; print('OK')"`

### Task 2: Move shared helpers into `reply.py`; add `result_from_reply`
- Why a new module: `openai_compatible.py` imports httpx and `collect` must not. This deviates from "refactor inside openai_compatible.py"; flag it in the report. Nothing outside the package references the moved names (grepped).
- Cut `_token_count`, `_parse_tool_calls`, `_resolve_usage` verbatim. `result_from_reply(provider, request, data) -> UpstreamResult` = the `choices/message/content` extraction with its `except (KeyError, IndexError, ValueError)` wrapper, the tools gate, null-content handling and error text, finish_reason, `_resolve_usage`, and the `UpstreamResult(model_used=request.upstream_model, ...)`. `resp.json()` stays in `complete()`, its ValueError wrapped with the same text. `openai_compatible.py` re-imports the names.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_upstream_adapter.py tests/test_prd020_legacy_fixtures.py` (unmodified, green)

### Task 3: Refactor `complete()` onto shared helpers
- `_payload(request, *, stream=False)` (stream adds `"stream": True`, `"stream_options": {"include_usage": True}`); `_headers(api_key)`; `_raise_for_response(resp, label)` (redirect check + `raise_for_status`) and `_http_error(exc, label) -> UpstreamError`; one `_open_client()` keeping `follow_redirects=False`. Texts byte-identical. Validate as Task 2.

### Task 4: `sse.py` parser
- Lines are `str` (httpx `iter_lines`). `data:` with or without the space. `id=""` counts as missing. Errors name the field only, never the payload or the line. Mirror `_parse_tool_calls` wording.

### Task 5: `collect.py`
- Per the assembly rules: build `{"choices":[{"message":{"content":c,"tool_calls":[...]?},"finish_reason":f}], "usage":{...}?}` and `return result_from_reply(provider, request, data)`. An event outside the Union -> `TypeError` naming the type. No httpx, no settings (AST test).

### Task 6: `OpenAICompatibleAdapter.stream`
- `with http_client.stream("POST", url, headers=..., json=_payload(request, stream=True)) as resp:` inside `try/finally` (close the client when owned). Redirect/HTTP check via the shared helpers, body not read on non-2xx. `yield from parse_events(resp.iter_lines(), label)`; wrap `httpx.HTTPError` raised during iteration through `_http_error`. `Accept: text/event-stream` only on stream; complete's headers unchanged.

### Task 7: Exports
- `__init__.py`: import `collect`, the four events and `UpstreamEvent`; add to `__all__`.

### Task 8: Stub SSE
- After the fail/redirect branches, if `body.get("stream") is True`: `200 text/event-stream`, `Connection: close`, no Content-Length, flush per frame, `_DISCONNECTS` swallowed. Frames: content deltas (string content split at `len//2` into non-empty halves, one `""` delta if empty; null content: none); per tool call a first fragment `{index,id,type:"function",function:{name,arguments:first_half}}` then `{index,function:{arguments:rest}}` (two fragments even for empty arguments); a chunk with `finish_reason` and empty delta; then, only if `stream_options.include_usage is True` and `reply.usage is not None`, `choices: []` with `usage` verbatim; then `data: [DONE]`. Share the id-generation code with the JSON path (one `call_<n>` per answer).
- Log: `... auth={auth} stream={yes|no} tools=...`, `yes` iff `body.get("stream") is True`. Check `test_each_request_logs...` and the `endswith("tools=0 calls=0 -> 503")` assertion still hold (`stream=` sits before `tools=`).
- Rewrite the header note at `:63-64`: the stub streams when asked; `complete` never sends `stream`.

### Task 9: Tests
- `tests/test_upstream_stream_collect.py`:
  - (a) property: replies = default + every rule of each `tests/e2e/scripts/*.json` (matcher/qualifier/`times`/`delay_seconds` keys stripped; fail/redirect replies compared as equal `UpstreamError` str/status/retryable), the `render_script` outputs used at `tests/test_e2e_cline_script.py:34` and `test_e2e_opencode_script.py:33`, and inline scripts: call + null content, content + call, two calls (generated and explicit id), empty and unparsable arguments, `usage: null`, partial usage, `content: ""`. Run legacy (`usage_missing: error`) and estimate providers (`dataclasses.replace(provider_registry.current().providers[0], base_url=stub, usage_missing=...)`), with and without `tools`. Assert `collect(adapter.stream(r), provider=p, request=r) == adapter.complete(r, key)`; when both raise, equal type/str/retryable.
  - (b) malformed streams via `httpx.MockTransport`: non-JSON data, non-object data, missing `[DONE]`, fragment for an unseen index, non-int index, missing id on first delta, 3xx/4xx/5xx, mid-stream transport error; each names the field, a canary value never appears, `retryable` False except 5xx/429/transport. Blank lines, `:` comments ignored.
  - (c) `complete()` payload has no `stream` key; `stream()` sends `stream: True` and `stream_options`.
  - (d) AST purity of `collect.py`, `sse.py`, `reply.py`: no `httpx` or `settings` import.
  - (e) response and owned client closed on early generator close and on error; an injected client is not closed.
- `tests/test_stub_openrouter.py`: `stream=yes|no` log, SSE shape (two content deltas, two fragments, usage chunk only with `include_usage`, `[DONE]`), non-stream request unchanged, no header value logged on a streaming request.

### Task 10: PRD 6.4 amendment
- Edit the `collect` line and the In Scope bullet (PRD `:62`): keyword-only `provider`, `request`; add a one-line deviation note (STORY-013).

## End-to-End Tests

- [ ] Real stub on a free port: `adapter.stream` vs `complete` over every script (Task 9a).
- [ ] `httpx.post(..., json={"stream": true, ...})` on the stub: `text/event-stream`, log `stream=yes`; without it JSON and `stream=no`.
- No `TestClient` path changes (no production caller).

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_upstream_stream_collect.py tests/test_upstream_adapter.py tests/test_stub_openrouter.py tests/test_prd020_legacy_fixtures.py tests/test_e2e_cline_script.py tests/test_e2e_opencode_script.py tests/test_untouched_app.py
```
No test is renamed or removed, so `test_pii_redaction_integration.py` is not needed.

## Acceptance Criteria -> Tasks -> Tests

| AC | Task(s) | Test |
|----|---------|------|
| AC1 stream sends both keys, events; complete no `stream` | 1, 3, 6 | `test_upstream_stream_collect.py::test_payload_keys` |
| AC2 stub SSE + `stream=yes/no` | 8 | `test_stub_openrouter.py::test_stream_log_field`, `::test_sse_body_shape` |
| AC3 collect pure, complete's rules, D8 | 2, 5 | AST purity test; property cases null-content, D13, duplicate id, usage estimated |
| AC4 property over scripts, both paths | 9a | `::test_collect_of_stream_equals_complete` |
| AC5 malformed streams | 4, 9b | `::test_malformed_stream_*` |

## Risks

- `reply.py` is a deviation from "refactor in openai_compatible.py", needed to keep `collect` free of httpx; the existing tests and legacy fixtures guard byte-equality.
- Real-provider `total_tokens: null` under error mode differs between `complete` and `collect` (see Design); not reachable from the stub.
- Threaded stub without Content-Length: `Connection: close` so httpx sees EOF.
