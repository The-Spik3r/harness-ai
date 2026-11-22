---
story: STORY-006
prd: PRD-022
slug: stub-anthropic-mode-and-faults
title: Stub upstream - Anthropic Messages mode (JSON + SSE) and scripted faults
type: ENHANCEMENT
complexity: medium
epic_branch: epic/PRD-022-provider-fallback-and-native-adapters
created: 2026-11-20
---

# Plan: Stub upstream - Anthropic Messages mode and scripted faults

## Summary

`scripts/stub_openrouter.py` gains a second endpoint, `POST <anything>/messages`, that answers from the SAME script (same rules, same matchers) as Anthropic Messages JSON or SSE, plus four additive reply keys (`stop_reason`, `retry_after`, `fault`, cache usage) that also work on Chat Completions. A per-endpoint hit counter is readable by tests. Nothing that exists changes: the Chat handler path, its log line, its 404 text and every existing script stay byte-identical; new code is new functions beside the old ones.

- Story: `.agents/stories/PRD-022-provider-fallback-and-native-adapters/STORY-006-stub-anthropic-mode-and-faults.md`
- PRD sections used: 6.5 (Response table), 6.6 (SSE event list), F11, D4
- Systems affected: `scripts/stub_openrouter.py` (test tool; nothing under `app/` imports it, `tests/test_stub_openrouter.py:471` checks that), `tests/e2e/scripts/README.md`

## Design Decisions

Not a critical story; the following are choices, not orchestrator design points.

- **Routing** (`stub_openrouter.py:618-625`): path ending `/chat/completions` stays as is; path ending `/messages` goes to a new `_post_messages`; anything else keeps today's 404 and its exact text (`:624`, and `test_bad_body...` `tests/test_stub_openrouter.py:322` + the 7-line log count at `:318` rely on it). Do the routing check without reading more than today's `Content-Length`.
- **Auth on /messages**: `require_key` (in-process) accepts `Authorization: Bearer <key>` (what SDK 2.11.0 sends, STORY-001) OR `x-api-key: <key>`; otherwise 401. No `require_key` means anything is accepted. `anthropic-version` is not required. The log line records presence only: `auth=yes|no` (either header) and `ver=yes|no`; never a value.
- **Request view**: `Request.from_messages_body(body)` builds the same `Request(messages, tool_names)` so matchers/qualifiers work unchanged: top-level `system` (str or text blocks) becomes a leading `system` message; a user message whose content is only `tool_result` blocks becomes role `tool` with the results' text; tool names come from `tool["name"]`. `_called_names` (`:205`) additionally reads `tool_use` content blocks (additive; Chat input unaffected). Rule hit counts (`times`) are shared across endpoints (one script, one `hits` dict).
- **Validation**: `/messages` needs a JSON object with a `messages` list, `model` and integer `max_tokens` >= 1, else 400 `invalid_request_error`. Error envelope on /messages is Anthropic's, `{"type":"error","error":{"type":<t>,"message":"stub_openrouter: ..."}}`, with `<t>` from status: 400 invalid_request_error, 401 authentication_error, 403 permission_error, 404 not_found_error, 429 rate_limit_error, 529 overloaded_error, other 5xx api_error. Chat faults keep `_send_error_body` (`:609`).
- **New reply keys** (added to `_REPLY_KEYS` `:103`, validated in `_parse_reply` `:353`, errors name `rules[i]`/`default`):
  - `stop_reason`: one of the 7 values recorded by STORY-001 (`end_turn, max_tokens, stop_sequence, tool_use, pause_turn, refusal, model_context_window_exceeded`). Not combinable with `finish_reason`. On /messages it is sent verbatim; on Chat it is mapped back (`end_turn|stop_sequence`->`stop`, `max_tokens|model_context_window_exceeded`->`length`, `tool_use`->`tool_calls`, `refusal`->`content_filter`, `pause_turn` verbatim). Conversely a script's `finish_reason` is mapped forward for /messages (`stop`->`end_turn`, `length`->`max_tokens`, `tool_calls`->`tool_use`, `content_filter`->`refusal`; other strings verbatim, null -> null). So `finish_reason: "content_filter"` already yields a refusal on both endpoints. A refusal needs non-empty `content` for the adapter (empty text with no tool call is a `shape` error, `app/services/upstream/anthropic.py:244`): scripts say so.
  - `retry_after`: integer >= 1, only with `fail_status`; sent as `Retry-After: N` on that error on either endpoint (nothing sent today, so Chat scripts without it are unchanged).
  - `fault`: closed set `timeout | malformed`, replaces the body like `fail_status`/`redirect_status` (exactly one of the three; conflicts with `_BODY_KEYS` rejected as at `:362`). `timeout`: after any `delay_seconds`, accept and read the request, send nothing, hold the connection until the server closes or `_HOLD_SECONDS` (60) passes; use a per-server `threading.Event` set by an overridden `_StubServer.server_close` so teardown never waits (handler threads are already daemon, `:706`). `malformed`: status 200 with a truncated body (`{"id": "` JSON; for a streaming request one truncated SSE frame: Chat `data: {"choices":`, Messages `event: message_start\ndata: {"type":"message_start","message":`), then close.
  - usage gains optional `cache_creation_input_tokens` and `cache_read_input_tokens` (`_USAGE_KEYS` `:117`). `_parse_usage` (`:279`) keeps returning exactly the three Chat keys; the two cache counts are split off into new `Reply.cache_creation_tokens` / `cache_read_tokens` (default 0) and are ignored by Chat bodies. A Chat-only script's usage dict is unchanged.
- **Messages JSON body**: `{"id":"msg_stub_<n>","type":"message","role":"assistant","model":<request model>,"content":[...],"stop_reason","stop_sequence":null,"usage":{"input_tokens":prompt_tokens,"output_tokens":completion_tokens,"cache_creation_input_tokens","cache_read_input_tokens"}}`. `input_tokens` is the script's `prompt_tokens` and EXCLUDES the cache counts (Anthropic semantics, 6.5), so the adapter's prompt = prompt + cache. `usage: null` emits `"usage": null` (a `shape` error for the adapter, as intended). Blocks in order: `thinking` (only when the reply's `stream.reasoning` is set: `{"type":"thinking","thinking":<text>,"signature":"stub-signature"}`), `text` (omitted when content is empty or null), then one `tool_use` per call (`id` scripted or `toolu_stub_<n>` from its own counter, `input` = `json.loads(arguments)`). Arguments that do not parse to a JSON object: answer 500 `api_error` ("tool arguments are not a JSON object", never echoing them); the SSE path emits the string as given in `input_json_delta`.
- **Messages SSE** (new `_send_messages_sse`, own piece-cutting helper `_cut`; the Chat `_send_sse` `:522-607` is NOT refactored): headers as `:591-595` (`text/event-stream`, `Connection: close`, one flush per frame), frames `event: <type>\ndata: <json>\n\n`. Order: `message_start` (message with empty content, usage with input and cache counts and `output_tokens: 1`), `ping`, then per block `content_block_start` / `content_block_delta`* / `content_block_stop` (thinking: `thinking_delta` pieces then one `signature_delta`; text: `text_delta` pieces; tool_use: start carries `id`, `name`, `input: {}`, then `input_json_delta` `partial_json` pieces of the arguments string), then `message_delta` (`delta.stop_reason`, `stop_sequence: null`, cumulative `usage` with `output_tokens`), `message_stop`. `stream:{chunk_chars,delay_ms,reasoning,fail_after}` keeps its PRD-021 meaning: pieces default to halves, `delay_ms` before every delta frame, `fail_after: K` sends K delta frames and closes with no `message_delta`/`message_stop`. `usage: null` omits both usage objects. Block events other than deltas are never counted by `fail_after`.
- **Hit counters**: `_StubServer.endpoint_hits() -> {"chat": n, "messages": n}` (a lock-protected copy), counted in `do_POST` at routing time for every POST to one of the two endpoints (faulted, 401, timeout and malformed included, before any delay); 404 paths are not counted. Handler class gets an `endpoint_hits` dict + the existing `hits_lock` (`:732`); `make_server` (`:709`) wires the event and dict into the server. Per-rule `hits` (`times`) is untouched.
- **Never logs prompt text** (`:650` rule): the Messages log line is `stub_openrouter: POST <path> api=messages model=... messages=<n> params=[keys] rule=<label> delay=<g> auth= ver= stream= tools=<n> calls=<n> -> <status>`; counts and keys only; `system`, content, tool names, arguments, `x-api-key` and `Authorization` values never appear; fault names are not content and may appear as `fault=<name>`.

## Skills In Use

None apply (`.agents/skills/` holds only `frontend-design`; no UI).

## Patterns to Follow

| Category | Source | What to mirror |
|----------|--------|----------------|
| Script validation | `scripts/stub_openrouter.py:279-319, 353-403` | `ScriptError(f"{where}: ...")` naming the key, never echoing model output; closed key frozensets at `:102-117` |
| Replace-the-body replies | `:358-383` | `fail_status`/`redirect_status` return early with `_BODY_KEYS` conflict check; do the same for `fault` |
| Frame sending | `:590-607` | one `send_response`, flush per frame, `except _DISCONNECTS: pass` |
| Server binding | `:722-736` | per-server state bound through the handler subclass dict, so two stubs in one process stay apart |
| Docstring | `:1-87` | extend the module docstring with a "Messages mode (PRD-022 STORY-006)" paragraph and the new keys |
| Tests (stub fixture) | `tests/test_stub_openrouter.py:79-98` | factory that starts `make_server` on port 0 in a daemon thread, `poll_interval=0.05`, shutdown at teardown |
| Tests (adapter loopback) | `tests/test_anthropic_adapter.py:593-660` | STORY-005's `test_the_real_sdk_path_*` use an AD-HOC `HTTPServer` fixture (`stub`, `_Handler` at `:604`), NOT `scripts/stub_openrouter.py`. Per orchestrator: do NOT rewrite them in this story; note it in the report (a later cleanup may move them onto the stub) |

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `scripts/stub_openrouter.py` | UPDATE | Messages endpoint (JSON + SSE), new reply keys, faults, endpoint hit counters, docstring |
| `tests/test_stub_anthropic_mode.py` | CREATE | HTTP-level Messages/SSE/fault tests plus the adapter end-to-end test |
| `tests/e2e/scripts/README.md` | UPDATE | document `stop_reason`, `retry_after`, `fault`, the cache usage keys and the `/messages` endpoint next to `fail_status` (`:59`) |
| `tests/test_stub_openrouter.py` | none | existing tests must pass unmodified |

## Tasks

Execute in order.

### Task 1: Script model and parsing
- **File**: `scripts/stub_openrouter.py`
- **Implement**: new `Reply` fields (`stop_reason`, `retry_after`, `fault`, `cache_creation_tokens`, `cache_read_tokens`, defaults keep current behaviour); constants for the 7 stop reasons, the two maps, `_FAULTS`, `_HOLD_SECONDS`; extend `_REPLY_KEYS`/`_BODY_KEYS` (`stop_reason` is a body key, so `fail_status` rejects it) and `_parse_usage`/`_parse_reply` as in Design. Error texts name `where` and the key.
- **Mirror**: `:297-319` (`_parse_stream`) and `:358-367`
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_stub_openrouter.py -k "script or parse or example"`

### Task 2: Request view and routing
- **File**: `scripts/stub_openrouter.py`
- **Implement**: `Request.from_messages_body`; `_called_names` reads `tool_use` blocks; `do_POST` dispatch by path suffix; shared helpers for faults (delay, retry-after header, `timeout` hold, `malformed`) used by both endpoints; `_send_json`/`_send_error_body` accept an optional `headers` for `Retry-After`/`request-id` without changing today's bytes when absent.
- **Mirror**: `:618-666` (order: log, delay, 401, redirect, fail_status, body)
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_stub_openrouter.py`

### Task 3: Messages JSON and SSE
- **File**: `scripts/stub_openrouter.py`
- **Implement**: `_post_messages`, `_messages_body(model, reply, calls)`, `_send_messages_sse`, Anthropic error envelope; add `request-id: req_stub_<n>` header on Messages responses (the SDK exposes `exc.request_id`).
- **Mirror**: `:522-607` for pacing/fail_after; `:668-701` for the Chat body
- **Validate**: new test file (Task 5), after Task 5 exists

### Task 4: Hit counters and server wiring
- **File**: `scripts/stub_openrouter.py`
- **Implement**: `endpoint_hits` on handler + `_StubServer.endpoint_hits()`; release `Event` and `server_close` override; `make_server` docstring.
- **Mirror**: `:704-736`
- **Validate**: `tests/test_stub_openrouter.py` unchanged-green

### Task 5: Tests (new file, sibling of the existing one)
- **File**: `tests/test_stub_anthropic_mode.py` (CREATE)
- **Implement**: fixture like `tests/test_stub_openrouter.py:79-98` returning `(server, log, base)` with a free port; small local `_provider`/`_req` helpers copied from `tests/test_anthropic_adapter.py:35-59` (do not import from a test module). HTTP level via `httpx`. Cases:
  1. JSON: text + usage with both cache counts + `stop_reason` mapping (`finish_reason: length` -> `max_tokens`; explicit `stop_reason`); tool calls -> `tool_use` blocks (generated `toolu_stub_` ids unique across answers, scripted id kept, `input` an object); non-object arguments -> 500; `stream.reasoning` -> `thinking` block first; `usage: null`.
  2. Auth: Bearer and `x-api-key` accepted, wrong value -> 401 envelope; missing/invalid body or `max_tokens` -> 400 envelope.
  3. Faults, parametrized over both endpoints: 503, 429 + `retry_after` (`Retry-After` header), 401, 400 (Chat shape `error.code`, Messages `error.type`), `malformed` (JSON decode fails; streaming variant ends in a truncated frame), `timeout` (client `timeout=0.3` raises `httpx.ReadTimeout`; teardown fast), refusal (Messages `stop_reason: "refusal"`; Chat `finish_reason: "content_filter"` from the same `stop_reason` script).
  4. `times: N` then normal on /messages (N=2: hits 1-2 fail, 3 answers), and `endpoint_hits()` per endpoint (mixed Chat/Messages traffic, faulted and timed-out requests counted, 404 path not).
  5. SSE (HTTP level only; STORY-007 owns `stream()`): parse `event:`/`data:` frames; exact order `message_start, ping, content_block_start/delta/stop..., message_delta, message_stop`; event names are a subset of the six recorded in STORY-001 plus `ping`; thinking -> `thinking_delta` then `signature_delta`; concatenated `text_delta` equals content; concatenated `partial_json` equals the arguments string; `chunk_chars` and default halves; `fail_after: K` yields K delta frames and no `message_stop`; `message_delta.usage` carries `output_tokens`; `usage: null` omits usage.
  6. Privacy: after Messages traffic with a secret in `system`, user text, tool args, `Authorization` and `x-api-key`, neither the log, `capfd` out/err nor any `Bearer` text contains them (mirror `tests/test_stub_openrouter.py:295-319`).
  7. Parse errors name the rule: bad `fault`, `retry_after` without `fail_status`, `stop_reason` with `finish_reason`, unknown stop reason, `fault` with `content`, bad cache count (assert `rules[1]`-style text).
  8. Chat parity guards: a script with only old keys gives the same Chat body keys; `/chat/completions` still 404s elsewhere (`/models`).
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_stub_anthropic_mode.py`

### Task 6: Docs
- **File**: `scripts/stub_openrouter.py` docstring, `tests/e2e/scripts/README.md`
- **Implement**: see Files to Change. Keep the stub's "never logged" paragraph accurate.

## End-to-End Tests

- [ ] `test_the_real_adapter_against_the_stub_messages_mode` (in the new file): `make_server` on a free port; `AnthropicAdapter(_provider(base_url=f"http://127.0.0.1:{port}", timeout_seconds=...))` with `sdk_client=None` and a key, so the REAL SDK path runs (SDK appends `/v1/messages`, so `base_url` has no `/v1`). Script: (a) ok answer with cache usage -> `result.response`, `tokens_used = input + cache_write + cache_read + output`, `cache_*_tokens`; (b) a rule `times: 1, fail_status: 503` then an answer -> first call `UpstreamError(kind="status", upstream_status=503, retryable=True)`, second call succeeds (hit N+1 answers normally); (c) `fail_status: 429, retry_after: 7` -> `retry_after_seconds == 7`, retryable; (d) `content` + `stop_reason: refusal` -> `finish_reason == "content_filter"`; (e) `fault: timeout` with `timeout_seconds=0.3` -> `kind == "timeout"`, retryable (optional if margin is flaky on CI: assert only the kind and a generous elapsed bound); `endpoint_hits()["messages"]` equals the number of calls and `["chat"] == 0`; the stub log holds no key text. The stub must receive `Authorization: Bearer` (`require_key=_KEY` on the stub proves the SDK header is accepted).
- [ ] Existing `tests/test_stub_openrouter.py` passes unmodified (byte-identical Chat behaviour).

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_stub_anthropic_mode.py tests/test_stub_openrouter.py tests/test_anthropic_adapter.py
# the e2e-script guards that load stub scripts and docs
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_e2e_live.py tests/test_e2e_opencode_script.py tests/test_e2e_cline_script.py
```
`tests/test_untouched_app.py` only if anything under `app/` changes (it should not). No test is renamed or removed.

## Acceptance Criteria -> Tasks -> Tests

| AC | Task(s) | Test that proves it |
|----|---------|---------------------|
| AC1 Messages JSON (text, tool_use, usage + cache, stop_reason) and SSE event sequence | 2, 3 | `tests/test_stub_anthropic_mode.py` JSON cases (1) and SSE cases (5) |
| AC2 faults on either endpoint (timeout, 503, 429+retry_after, 401, 400, malformed, refusal); Chat shapes kept | 1, 2, 3 | fault cases (3), parse-error cases (7), adapter E2E (b-e) |
| AC3 first-N faults then normal; per-endpoint hit counter readable | 4 | `times` + `endpoint_hits` cases (4), adapter E2E (b) |
| AC4 existing tests unchanged; new tests cover each fault; never logs prompt text | 5 | unmodified `tests/test_stub_openrouter.py`; privacy case (6) |

Plus: all tasks completed, validation passes, follows existing patterns.

## Risks

- `timeout` tests: handler threads parked on the event; mitigated by `server_close` setting it and daemon threads. Use generous bounds (< 5 s) for CI.
- SDK 2.11.0 may demand header/body details of the real API (e.g. `type`, `usage` fields); the E2E test is the check. If the SDK rejects a stub field, fix the stub, not the adapter.
- STORY-007's property test (`collect(stream(r)) == complete(r)`) will replay these scripts: `reasoning_blocks` comes from the JSON `thinking` block, so STORY-007 must count thinking blocks in the stream too. Flagged here, not solved.
- Rule `times` counters are shared across endpoints (one script): fine for the chain tests (one stub per provider), documented in the README.
