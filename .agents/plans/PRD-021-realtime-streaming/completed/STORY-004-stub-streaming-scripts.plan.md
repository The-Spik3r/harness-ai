---
story: STORY-004
prd: PRD-021
slug: stub-streaming-scripts
title: Stub upstream streams scripted replies with delays, reasoning and faults
type: ENHANCEMENT
complexity: small
epic_branch: epic/PRD-021-realtime-streaming
created: 2026-11-18
---

# Plan: Stub upstream streams scripted replies with delays, reasoning and faults

## Summary

Extend `scripts/stub_openrouter.py` (test tool; extend, do not fork) so a reply may carry `stream: {chunk_chars, delay_ms, reasoning, fail_after}`. A request with `stream: true` against such a reply is answered as SSE in that shape. A reply without `stream:`, or a request without `stream: true`, is answered byte-for-byte as today (PRD-020 STORY-013's two-halves SSE, or JSON). The usage chunk keeps today's shape: a separate last chunk with `choices: []`, sent only when `include_usage` and the reply has usage (orchestrator note; do not move usage onto the finish chunk). Reasoning goes in `delta.reasoning` (STORY-001: OpenRouter's field).

- Story: `.agents/stories/PRD-021-realtime-streaming/STORY-004-stub-streaming-scripts.md` (full AC text lives there)
- PRD sections used: §4 "Stub upstream", F10, T1 row (§9.2)
- Systems affected: `scripts/stub_openrouter.py` and its tests only. Nothing under `app/` (a guard test forbids it).

## Design Decisions

Not a critical story; no binding design points. Choices made, with edge cases:

- **Shape model**: `@dataclass(frozen=True) StreamShape(chunk_chars: Optional[int]=None, delay_ms: int=0, reasoning: Optional[str]=None, fail_after: Optional[int]=None)` and `Reply.stream: Optional[StreamShape] = None`. `stream: {}` is legal (flags the shape, all defaults).
- **Validation** in `_parse_reply`, errors in the file's style (`ScriptError(f"{where}: stream.chunk_chars must be an integer >= 1, got {v!r}")`): `stream` must be an object; unknown keys named; `chunk_chars` int >= 1; `delay_ms` int >= 0; `fail_after` int >= 0; `reasoning` a non-empty string; reject bool (reuse `_is_count`, `stream.py:252`). `stream` joins `_REPLY_KEYS` and `_BODY_KEYS`, so `fail_status`/`redirect_status` + `stream` is refused like content ("replaces the body; remove stream"). `reasoning` text is never echoed in an error (model output, like `arguments`, `:290`).
- **chunk_chars** absent: today's split (halves for content and for arguments). Present: content, reasoning and each tool call's `arguments` are cut into pieces of at most N characters. Empty content: no content delta (as today). Tool call: first fragment carries `index/id/type/function.name` plus `arguments[:N]`, each later fragment `{"index": i, "function": {"arguments": piece}}`; empty `arguments` gives one fragment with `""`. So a 72-char `DROP TABLE` argument string with `chunk_chars: 8` is exactly nine fragments (STORY-010, T1). Without `chunk_chars`, tool calls stay two fragments.
- **Emission order**: reasoning deltas, then content deltas, then tool-call fragments (call 0 whole, then call 1...), then the finish chunk, the usage chunk (when `include_usage`), `[DONE]`. Reasoning delta: `{"reasoning": piece}` with `finish_reason: null`. Reasoning without `chunk_chars` is one delta.
- **delay_ms**: `time.sleep(delay_ms / 1000)` before each *delta* frame (reasoning, content, tool fragment), so the first delta is also D ms after the headers are flushed. No sleep before finish, usage or `[DONE]`. Sleep happens after `end_headers()`/flush so the client sees the response start immediately. Python's `sleep` never returns early; tests still use margins.
- **fail_after K**: send the first K *delta* frames (all kinds, in the order above), flush, then return without finish, usage or `[DONE]`; the existing `Connection: close` + `close_connection = True` makes the server close the socket, so the client sees EOF (a clean FIN, no `Content-Length`). K=0: headers only, then close. K >= number of deltas: still no finish and no `[DONE]` (the fault is the point). A tail of the frame list, never an exception in the handler.
- **Logging**: the log line is left byte-identical (existing tests assert `... stream=yes tools=0 calls=0 -> 200`). No shape, content or reasoning goes into it. A new test proves it.
- **Refactor shape**: build `frames` as a list of `(bytes, is_delta)` (or a list of delta frames plus a tail list), so `delay_ms` and `fail_after` act in one loop. Keep `_DISCONNECTS` handling around the whole write loop (`:530`). With no shape the loop must emit the same bytes as today.

## Skills In Use

None apply (`.agents/skills/` holds only `frontend-design`; no UI here).

## Patterns to Follow

| Category | Source | What to mirror |
|----------|--------|----------------|
| Frozen dataclasses | `scripts/stub_openrouter.py:119-135` | `ScriptedCall`, `Reply` (frozen, defaulted) |
| Key sets | `:92-104` | `_REPLY_KEYS`, `_BODY_KEYS`, `_USAGE_KEYS` frozensets |
| Validation errors | `:257-272`, `:306-320` | `ScriptError` naming `where` and the field; `_parse_usage` for a sub-object |
| SSE writer | `:473-531` | `frame()`, `delta_choice()`, `_DISCONNECTS`; the loop to refactor |
| Docstring | `:65-70` | module docstring paragraph for the SSE mode; add the `stream:` shape there |
| Stub tests | `tests/test_stub_openrouter.py:77-96` (`stub` fixture), `:799-818` (`_sse_post`, `_frames`), `:835-850` | in-process stub on a free port (port 0), server shut down at teardown |
| File-mode registry | `tests/_providers.py:56-70` (`provider_file`), `tests/test_upstream_adapter.py:89-113` (`_yaml`) | loopback `http://127.0.0.1:{port}/v1`, `insecure_http: true`, keyless provider; add `capabilities: {streaming: true, reasoning: true}` to the model (`provider_registry.py:297-311`) |
| Adapter events | `app/services/upstream/types.py:76-115`; `upstream/__init__.py:106-127` (`stream_upstream`); `upstream/sse.py:26-51` | `TextDelta`, `ReasoningDelta`, `Finish`; EOF before `[DONE]` raises `UpstreamError` |

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `scripts/stub_openrouter.py` | UPDATE | `StreamShape`, parsing, `_send_sse` extension, docstring |
| `tests/test_stub_openrouter.py` | UPDATE | new section "PRD-021 STORY-004" (existing tests untouched) |

No new file, no `app/` change, no new dependency.

## Tasks

### Task 1: Parse the `stream:` shape
- **File**: `scripts/stub_openrouter.py`
- **Implement**: `_STREAM_KEYS = frozenset({"chunk_chars","delay_ms","reasoning","fail_after"})`; `StreamShape`; `Reply.stream`; `_parse_stream(raw, where)`; call it in `_parse_reply` only on the body path (after the `fail_status`/`redirect_status` branches, which refuse `stream` through `_BODY_KEYS`). Add `"stream"` to `_REPLY_KEYS` and `_BODY_KEYS`. `_parse_rule`/`parse_script` already allow `_REPLY_KEYS`, so rules and `default` both accept it.
- **Mirror**: `:257-272`, `:306-354`
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_stub_openrouter.py -k "bad_stream or stream"`

### Task 2: Shape the SSE body
- **File**: `scripts/stub_openrouter.py`, `_send_sse` (`:473`) and its call (`:604-607`, pass `reply.stream` via `reply`, already in scope)
- **Implement**: a small pure helper `_pieces(text, size)` (cut into <= size chunks; `size=None` keeps today's halves rule) used for content, reasoning and arguments; build the delta list per "Emission order"; write loop applies `delay_ms` before each delta and stops after K deltas for `fail_after`. With `reply.stream is None` every byte equals today's output.
- **Mirror**: `:497-531`
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_stub_openrouter.py`

### Task 3: Docs in the stub
- **File**: `scripts/stub_openrouter.py` module docstring (`:65-70`)
- **Implement**: one paragraph with the four keys, the emission order, the `fail_after` meaning and that the log never carries content or reasoning. Cite "PRD-021 F10".

### Task 4: Tests (append a section after `:890`)
All use the existing `stub` fixture and `_sse_post`/`_frames`; helper `_sse_get(...)` that streams with `httpx.stream(...)` and records `time.monotonic()` per `data:` line via `iter_lines()`.
- AC1 `chunk_chars: 4`: content `"abcdefghij"` arrives as `["abcd","efgh","ij"]`, every delta <= 4, then a finish chunk, then (with `include_usage`) the `choices: []` usage chunk, then `[DONE]`. Also tool args `chunk_chars: 8` over a 72-char string give nine fragments whose concatenation equals the original; the first carries `id`/`name`, later ones do not; no fragment is empty.
- AC2 `delay_ms: 200`: collect timestamps of the request start (before `httpx.stream`) and each delta; assert first delta >= 0.18 s after the request start (first-chunk delay) and each gap >= 0.18 s (10% margin). No upper bound assertion. Use a deadline-bounded read (`timeout=httpx.Timeout(10)`), never a bare `sleep`; keep D small (150-200 ms) and 3-4 deltas.
- AC3 `reasoning: "thinking it over"` + `chunk_chars: 5`: all `delta.reasoning` frames precede every `delta.content` frame; reasoning pieces join to the text; no frame carries `reasoning_content`.
- AC4 `fail_after: 2` (content split into >= 4 deltas): the raw body has exactly 2 delta frames, no `finish_reason` non-null, no `[DONE]`; use `httpx.stream` and read to EOF (`RemoteProtocolError` is not raised because the body has no length; assert on collected text). Also K=0 gives an empty body.
- **fail_after through the adapter (orchestrator note, real stub + file-mode registry)**: `provider_file(yaml)` with `capabilities: {streaming: true, reasoning: true}` on the model and `base_url` set to the `stub` server's port; `events = []`; `with pytest.raises(UpstreamError) as info: for e in stream_upstream([Message("user","x")], model="local/m", api_key=None): events.append(e)`; assert `info.value.retryable is False` (STORY-003's non-retryable EOF error), that `TextDelta`s were delivered before the raise (exactly K worth), and no `Finish` in `events`. A companion happy-path test with no `fail_after` and a `reasoning` script asserts the event order `ReasoningDelta... TextDelta... Finish` through `stream_upstream` (proves the field name `delta.reasoning` is what the adapter maps). Import `provider_file` as `tests/test_upstream_adapter.py:31` does (`# noqa: F401`).
- AC5 log: with a shape that has secret-looking `content` and `reasoning`, after a streamed and a plain request the log text contains neither string and every line is ASCII; the streamed line still ends `stream=yes tools=0 calls=0 -> 200`.
- AC5 unchanged: a request without `stream: true` against a reply that has a shape gets the same JSON as the reply without it (`choices[0].message.content` full, no `reasoning` key); a shape-less reply streamed gives the two-halves body (existing `test_sse_body_shape` stays and passes).
- Bad shapes (parametrized, like `:387`): non-object, unknown key, `chunk_chars` 0/true/"4", `delay_ms` -1, `fail_after` -1, empty `reasoning`, `stream` with `fail_status`; each error names `rules[i]`/`default` and the key; a rejected `reasoning` value is never echoed.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_stub_openrouter.py tests/test_upstream_adapter.py`

## End-to-End Tests

- [ ] The adapter tests above drive the real stub over a real socket through `stream_upstream` with a file-mode registry (the only E2E this story needs).
- No `chat_ui/` change.

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_stub_openrouter.py tests/test_upstream_adapter.py tests/test_upstream_stream_collect.py tests/test_untouched_app.py
```
`test_untouched_app.py` is only a precaution (no `app/` file changes). No test is renamed or removed, so no `_DELIBERATELY_SUPERSEDED_TESTS` entry. Full suite: GitHub CI.

## Risks

- Timing: `sleep` granularity on Windows ~15 ms; 10% margins, no upper bounds (CI slower).
- An abrupt close on Windows may surface as a raw httpx read error; if it escapes `stream_upstream` un-mapped, report a STORY-003 gap, do not paper over it.
- Byte-compat without a shape is guarded by the unchanged SSE tests (`:835-891`).

## Acceptance Criteria -> Tasks -> Tests

| AC | Task(s) | Test that proves it |
|----|---------|---------------------|
| AC1 chunk_chars, finish, usage, `[DONE]` | 1, 2 | `test_stream_chunk_chars_splits_content_and_ends_with_finish_usage_done`, `test_stream_chunk_chars_splits_tool_arguments_into_nine_fragments` |
| AC2 delay_ms incl. first chunk | 2 | `test_stream_delay_ms_spaces_every_delta_including_the_first` |
| AC3 reasoning before content | 2 | `test_stream_reasoning_deltas_precede_content`, `test_stream_upstream_maps_scripted_reasoning` |
| AC4 fail_after drops, no finish/DONE | 2 | `test_stream_fail_after_drops_the_connection_without_finish`, `test_stream_upstream_raises_upstream_error_after_fail_after` |
| AC5 log never has content; unchanged without shape | 2 | `test_stream_shape_never_reaches_the_log`, `test_shape_without_stream_request_answers_json_as_today`, existing `test_sse_body_shape` |
| Validation of shapes | 1 | `test_bad_stream_shapes_are_rejected_naming_the_field` |
