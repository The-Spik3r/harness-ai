---
story: STORY-013
prd: PRD-015
slug: buffered-sse
title: "Buffered SSE: commit on upstream start, keep-alive, chunk sequence, include_usage, post-commit error"
type: NEW_CAPABILITY
complexity: HIGH
epic_branch: epic/PRD-015-openai-compatible-endpoint
created: 2026-10-26
---

# Plan: Buffered SSE: commit on upstream start, keep-alive, chunk sequence, include_usage, post-commit error

## Summary

Today `stream: true` on `POST /v1/chat/completions` returns a 501 placeholder (`app/routers/v1.py:174-181`,
`:198-200`). This story replaces it with PRD Section 6.4's commit rule and Section 7.6's buffered stream.

The router's existing `_Upstream` wrapper gains a start signal. It records `called = True` and sets an
`asyncio.Event` through `loop.call_soon_threadsafe` before it delegates to `call_openrouter`. The router
starts the pipeline as a task and waits for whichever comes first: the task finishing or the signal.

- **The wrapper was never called.** The task has finished, and the request gets the same JSON response the
  non-streaming path builds. That covers every verdict and every pre-upstream fault.
- **The wrapper was called.** The router commits a `StreamingResponse`. A new `app/services/v1_sse.py`
  writer sends `: keep-alive` comments every `settings.V1_SSE_KEEPALIVE_SECONDS` until the task resolves.
  It then sends the content, finish and optional usage chunks plus `[DONE]`, or a single `error` event.

The pipeline is never cancelled. A client disconnect stops only the writer. A done-callback retrieves the
task's outcome so the loop logs nothing, and a module-level set holds the task until it finishes.
`streamed=call.stream` is passed on every request. Chunks are derived from `translate_result`'s
`ChatCompletion`, so `finish_reason` and usage follow one rule on both paths.

## User Story

As an integrating developer whose client streams by default
I want `stream: true` to work, with the connection kept alive while the harness checks the full answer and blocks still arriving as real 400/403 errors
So that I can use my client unchanged without the harness ever releasing unchecked output

## Story Reference

- Story file: `.agents/stories/PRD-015-openai-compatible-endpoint/STORY-013-buffered-sse.md`
- PRD: `.agents/PRDs/PRD-015-openai-compatible-endpoint/PRD.md` (Sections 6.4, 7.5, 7.6, 9.2 T8, 11, 14 Risks 1/5/6, 15 D6/D8)

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | HIGH (story: large) |
| Systems Affected | `app/routers/v1.py`, new `app/services/v1_sse.py`, tests |
| Story | STORY-013 |
| PRD | PRD-015 |
| Epic Branch | `epic/PRD-015-openai-compatible-endpoint` (commit directly on this branch) |

The dependencies STORY-003, STORY-004, STORY-010 and STORY-011 are all `done`.

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | `.agents/skills/` holds only `frontend-design`. This story is backend only, and the story says "Skills: none applicable". | — |

---

## Patterns to Follow

### The wrapper this story extends

```python
# SOURCE: app/routers/v1.py:96-115
class _Upstream:
    """... STORY-013 adds the start signal here."""
    def __init__(self) -> None:
        self.result: Optional[OpenRouterResult] = None

    def __call__(self, messages, model, api_key, **kwargs) -> OpenRouterResult:
        self.result = call_openrouter(messages, model=model, api_key=api_key, **kwargs)
        return self.result
```

`**kwargs` already forwards `params=` only when the pipeline passed it (PRD-010 STORY-005). `call_openrouter`
is looked up at call time, so `monkeypatch.setattr("app.routers.v1.call_openrouter", stub)` still applies.
Keep both properties.

### The non-streaming outcome mapping, to be shared rather than copied

```python
# SOURCE: app/routers/v1.py:202-240
    upstream = _Upstream()
    try:
        result = await run_in_pipeline(run_conversation, identity, call.messages, device, call.model,
            None, call.params, call_openrouter=upstream, profile="code", ingress="v1",
            streamed=False, ignored_params=call.ignored_params)
    except _PIPELINE_FAULTS as exc:
        code = _fault_code(exc)
        logger.warning("v1 request failed: user_id=%s code=%s", identity.user_id, code)
        return _from_v1_error(translate_fault(code, str(exc)))
    if not isinstance(result, QuerySuccessResponse):
        return _from_v1_error(translate_verdict(result))
    assert upstream.result is not None
    completion = translate_result(result, upstream.result, int(time.time()))
    return JSONResponse(completion.model_dump(mode="json"),
                        headers={"X-Harness-Audit-Id": str(result.audit_id)})
```

### Error body (one builder)

```python
# SOURCE: app/routers/v1.py:118-148
def _error(status_code, type_, code, message, param=None, headers=None, harness=None) -> JSONResponse:
    body = ErrorResponse(error=ErrorDetail(message=message, type=type_, param=param, code=code, harness=harness))
    ...
def _from_v1_error(error: V1Error) -> JSONResponse: ...
```

The SSE error event body must be byte-for-byte the same `ErrorResponse` (AC 4: "the STORY-011 object").
Split the body construction out as `_error_body(...) -> ErrorResponse` so the JSON and SSE paths share it.

### Chunk schemas (already built in STORY-004)

```python
# SOURCE: app/models/v1_schemas.py:134-172
class ChunkDelta(BaseModel):     # serializer drops None keys -> finish chunk's delta is {}
class ChunkChoice(BaseModel):    # index=0, delta, finish_reason=None
class ChatCompletionChunk(BaseModel):  # id, object, created, model, choices, usage (dropped when None)
# SOURCE: app/models/v1_schemas.py:22-29
def chat_completion_id(audit_id: int) -> str
```

Serialize with `model_dump_json()` and never pass `exclude_none` (module docstring, `v1_schemas.py:9-12`).

### Executor helper

```python
# SOURCE: app/services/pipeline_executor.py:44-53
async def run_in_pipeline(fn, /, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_get_executor(), functools.partial(fn, *args, **kwargs))
```

It is a coroutine, so the router wraps it with `asyncio.ensure_future(...)` to get a task it can wait on
alongside the signal. Cancelling that task would not stop the executor thread. It would only orphan the
outcome, which is why nothing in this story cancels it.

### The call-site scan constraint

```python
# SOURCE: tests/test_query_pipeline_audit_fields.py:552-576
assert sorted(...) == [..., ("app/routers/v1.py", "chat_completions", "run_conversation"), ...]
```

There must stay **exactly one** `run_in_pipeline(run_conversation, ...)` call, lexically inside
`chat_completions`, with `ingress=` among its keywords. Do not move the call into a helper and do not
duplicate it per branch.

### Tests: concurrency without sleeps

```python
# SOURCE: tests/test_pipeline_concurrency.py:126-175, 191-222, 239-244
class _BlockingUpstream:  # parks the first N calls on threading.Event, announces on a Condition
    def __call__(self, messages, model="gpt-4", api_key=None) -> OpenRouterResult: ...
    def wait_until_blocked(self, n): ...   # reached through asyncio.to_thread
@pytest.fixture
def pipeline_pool(monkeypatch): ...        # release first, shutdown second
def _client() -> AsyncClient: return AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=_AUTH_HEADERS)
```

`@pytest.mark.asyncio` is used explicitly, with no `asyncio_mode` config. Every wait is bounded by
`_HARD_TIMEOUT`.

### Tests: fault injection through the real client

```python
# SOURCE: tests/test_v1_errors.py:508-560
def _upstream_over(handler): ...   # real call_openrouter over httpx.MockTransport
def _status(code): ...; def _transport_failure(exc_type): ...
def _real_then_raising(real, exc): ...   # input redaction real, output redaction raises
def _assert_fault(response, status_code, code, retryable, message=None): ...
def _assert_one_v1_failure_row(message): ...   # asserts streamed == False today
```

---

## Design decisions (made here, flagged for review)

1. **Commit is decided by `upstream.called`, not by which awaitable finished first.** A fast stub can
   finish the pipeline in the same loop iteration that the signal is set, and then `asyncio.wait` returns
   both as done. Branching on the wrapper's own flag (set on the worker thread before the result can exist)
   is deterministic. If the wrapper was called, the request commits to SSE even when the pipeline has
   already finished. In that case the stream carries no keep-alives, just the chunks or the error event.
   This is PRD Section 6.4 read strictly: once step 7 started, the request is past every verdict.
2. **A wrapper call is the commit point, even if `call_openrouter` raises at once.** An `OpenRouterError`
   is always post-commit and becomes an SSE `error` event (AC 4), never JSON. This matches the table in PRD
   Section 6.4.
3. **A post-commit exception outside `_PIPELINE_FAULTS`** (for example a storage error in step 8's
   `log_query`) is logged with `logger.exception` and sent as an `internal_error` event, with no `[DONE]`.
   The non-streaming path leaves such errors to Starlette's 500, but there is no status to fall back on
   once a 200 is sent. Ending the event stream cleanly is better than a torn chunked response, and it keeps
   the loop free of unhandled exceptions (AC 5). Flag this if a reviewer prefers re-raising.
4. **A non-success, non-fault result after commit** is a verdict after step 7. Risk 5 says this cannot
   happen. If it does, it is translated with `translate_verdict` and sent as the error event, with a WARNING
   log. This branch is defensive and covered by one unit test with an injected outcome.
5. **The `Content-Type` is `text/event-stream; charset=utf-8`.** Starlette appends the charset to `text/*`
   media types. Tests assert `startswith("text/event-stream")`. Clients, the OpenAI SDK included, accept it.
6. **`created` is read once, when the outcome is rendered**, and all chunks share it. `model` is
   `result.model_used`, the same as the non-streaming body.
7. **The keep-alive loop uses `asyncio.wait({task}, timeout=interval)`**, not `wait_for`, because
   `asyncio.wait` never cancels what it waits on. The first keep-alive comes one interval after commit,
   never at once.
8. **Timing and disconnect tests drive the ASGI app directly.** httpx 0.28.1's `ASGITransport` runs the
   app to completion and buffers the body (`handle_async_request` collects `body_parts`, then returns), so
   it can prove **order** but not **arrival time** or a mid-stream disconnect. A small driver in
   `tests/test_v1_sse.py` calls `app(scope, receive, send)`. Its `send` timestamps each body message, and
   its `receive` returns `http.disconnect` on demand. It runs twice: `spec_version` `"2.0"` (Starlette's
   `listen_for_disconnect` cancel path) and `"2.4"` (`send` raises `OSError`, Starlette's
   `ClientDisconnect` path). Uvicorn currently sends `"2.3"`, which takes the first path. AC 3's "before
   the first `data:`" is still also asserted over plain `AsyncClient`.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/v1_sse.py` | CREATE | The SSE wire format (keep-alive, `data:` events, `[DONE]`), chunks from a `ChatCompletion`, the commit wait, and the keep-alive writer. No settings import: the interval is passed in |
| `app/routers/v1.py` | UPDATE | Start signal on `_Upstream`; one `run_in_pipeline` call as a task with `streamed=call.stream`; a shared outcome-to-JSON helper; the commit branch; `StreamingResponse`; remove `_placeholder`; module docstring |
| `tests/test_v1_sse.py` | CREATE | Unit tests for the renderers and the writer (no storage), HTTP tests over `AsyncClient`, and the direct-ASGI timing and disconnect tests |
| `tests/test_v1_router.py` | UPDATE | Remove `test_placeholder_stream_true_is_501_without_row` and its docstring paragraph; point to `tests/test_v1_sse.py` |
| `tests/test_v1_errors.py` | UPDATE | Parametrize the verdict and pre-upstream-fault tests over `stream` (AC 1). `_assert_one_v1_failure_row` takes the expected `streamed` |

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: `app/services/v1_sse.py`, the pure parts

- **File**: `app/services/v1_sse.py`
- **Action**: CREATE
- **Implement**:
  - A module docstring in the style of `v1_translate.py`. Name PRD Sections 6.4 and 7.6 and T8 ("nothing
    but comments before the outcome"). Say that the module reads no settings, because the router passes the
    interval.
  - `KEEPALIVE = ": keep-alive\n\n"` and `DONE = "data: [DONE]\n\n"`.
  - `def data_event(payload: BaseModel) -> str` returns `f"data: {payload.model_dump_json()}\n\n"`.
  - `def completion_events(completion: ChatCompletion, include_usage: bool) -> List[str]` returns, in order:
    - the content chunk, `ChunkChoice(delta=ChunkDelta(role="assistant", content=completion.choices[0].message.content))`;
    - the finish chunk, `ChunkChoice(delta=ChunkDelta(), finish_reason=completion.choices[0].finish_reason)`;
    - when `include_usage`, the usage chunk, `ChatCompletionChunk(choices=[], usage=completion.usage)`;
    - `DONE`.

    Every chunk takes `id`, `created` and `model` from `completion`, so each id is
    `chat_completion_id(audit_id)` without being rebuilt.
  - `def error_event(body: ErrorResponse) -> str` returns `data_event(body)`. No `[DONE]` follows it, and
    the docstring says so: PRD Section 7.6, where the OpenAI SDK raises `APIError` on an `error` key.
- **Mirror**: `app/services/v1_translate.py` for purity and docstrings, `app/models/v1_schemas.py:134-172`
  for the shapes.
- **Validate**: `C:/Users/tobip/.venvs/harness-ai/Scripts/python.exe -c "import app.services.v1_sse"`

### Task 2: `v1_sse`, the commit wait and the writer

- **File**: `app/services/v1_sse.py`
- **Action**: UPDATE
- **Implement**:
  - `async def wait_for_commit(pipeline: asyncio.Future, started: asyncio.Event) -> None` waits for
    whichever finishes first with `asyncio.wait({pipeline, signal}, return_when=FIRST_COMPLETED)`, where
    `signal = asyncio.ensure_future(started.wait())`. It cancels `signal` in a `finally` when it is still
    pending, and never cancels `pipeline`. It returns nothing, because the caller decides from
    `upstream.called` (design decision 1).
  - `def detach(pipeline: asyncio.Future) -> None` keeps a strong reference in a module-level `_RUNNING: set`
    and adds a done-callback. The callback discards the future from the set and, unless it was cancelled,
    calls `future.exception()`, so a disconnected stream never leaves "exception was never retrieved" in the
    log (AC 5, PRD Section 7.6, "logs nothing extra").
  - `async def stream(pipeline: asyncio.Future, render: Callable[[asyncio.Future], List[str]], interval: float) -> AsyncIterator[str]`
    runs `while not pipeline.done(): done, _ = await asyncio.wait({pipeline}, timeout=interval); if not done: yield KEEPALIVE`,
    then `for event in render(pipeline): yield event`. No `try/except CancelledError` or `GeneratorExit`:
    letting cancellation or `aclose()` propagate is correct, and the pipeline is untouched because
    `asyncio.wait` does not cancel it.
- **Mirror**: the bounded-wait discipline of `tests/test_pipeline_concurrency.py`. The docstrings say why
  `wait`, not `wait_for` (design decision 7).
- **Validate**: import check, as in Task 1.

### Task 3: Unit tests for `v1_sse` (no storage)

- **File**: `tests/test_v1_sse.py`
- **Action**: CREATE (first section)
- **Implement**: these tests touch no storage fixture, so they run under `-m "not db"`. Output is ASCII only.
  - The `completion_events` sequence with and without `include_usage`: parse each `data:` JSON line and
    assert whole dicts. Content delta `{"role": "assistant", "content": ...}` with `finish_reason: null`.
    Finish delta `{}` with the reason. Usage chunk `choices == []` with the usage dict and no `usage` key on
    the other chunks. Every `id == "chatcmpl-harness-42"`. The last line is `DONE`.
  - `finish_reason` passes through `"length"`.
  - `error_event` gives one `data:` line whose JSON equals `ErrorResponse.model_dump(mode="json")`, with no
    `[DONE]`.
  - `stream()` with a hand-made `asyncio.Future` and `interval=0.01`: resolve it after about five intervals
    through `loop.call_later`. Assert at least two `KEEPALIVE`, no keep-alive after the first non-keep-alive,
    and render called exactly once.
  - `stream()` with a future already done yields no keep-alive.
  - `aclose()` on `stream()` mid-wait leaves the future pending and not cancelled. A later
    `set_exception(...)` plus `detach` logs nothing: use `caplog` at DEBUG on the `asyncio` logger and run
    `gc.collect()`.
  - `wait_for_commit` returns when only the event is set. It returns when only the future completes. It
    never cancels the future in either case.
- **Validate**: `C:/Users/tobip/.venvs/harness-ai/Scripts/python.exe -m pytest tests/test_v1_sse.py -m "not db" -q`

### Task 4: Router, signal, one call, shared outcome, commit branch

- **File**: `app/routers/v1.py`
- **Action**: UPDATE
- **Implement**:
  - `_Upstream.__init__(self, loop: asyncio.AbstractEventLoop)` adds `self.called = False` and
    `self.started = asyncio.Event()`. `__call__` sets `self.called = True`, then
    `self._loop.call_soon_threadsafe(self.started.set)`, then delegates exactly as today. Update the
    docstring and drop "STORY-013 adds the start signal here".
  - Split `_error` into `_error_body(type_, code, message, param, harness) -> ErrorResponse` plus the
    existing `JSONResponse` wrapper. Add `_v1_error_body(error: V1Error)` for the SSE path.
  - Add `_outcome(pipeline, upstream, identity) -> Union[ChatCompletion, V1Error, ...]`, the today's-logic
    mapping over a **done** future. It calls `pipeline.result()`, catches `_PIPELINE_FAULTS` (with the same
    WARNING log and `translate_fault`), maps a verdict with `translate_verdict`, and maps a success with
    `translate_result(..., int(time.time()))`. It returns the `ChatCompletion` plus the audit id, or the
    `V1Error`, and builds no response. Two thin renderers use it:
    - `_json_response(...)` gives today's exact `JSONResponse` or `_from_v1_error`, keeping the
      `X-Harness-Audit-Id` header on success.
    - `_sse_events(...)` gives `completion_events(completion, call.include_usage)`, or
      `[error_event(_v1_error_body(error))]`. It also catches any other `Exception` from `pipeline.result()`,
      logs it with `logger.exception`, and returns an `internal_error` event (design decision 3). A verdict
      after commit logs a WARNING and is still an error event (decision 4).
  - In `chat_completions`, after translation:
    ```python
    upstream = _Upstream(asyncio.get_running_loop())
    pipeline = asyncio.ensure_future(run_in_pipeline(run_conversation, ..., call_openrouter=upstream,
        profile="code", ingress="v1", streamed=call.stream, ignored_params=call.ignored_params))
    if call.stream:
        await v1_sse.wait_for_commit(pipeline, upstream.started)
    else:
        await asyncio.wait({pipeline})
    if not (call.stream and upstream.called):
        return _json_response(pipeline, upstream, identity)
    v1_sse.detach(pipeline)
    return StreamingResponse(
        v1_sse.stream(pipeline, functools.partial(_sse_events, ...), settings.V1_SSE_KEEPALIVE_SECONDS),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
    ```
    Keep the single `run_in_pipeline(run_conversation, ...)` lexically in `chat_completions` (the scan).
    `await asyncio.wait({pipeline})` rather than `await pipeline` keeps the exception handling in
    `_outcome`, so both paths share one mapping. A comment on the streamed keyword quotes `_deny`'s rule
    (`query_pipeline.py:217-218`): a defaulted False would mislabel this SSE refusal.
  - Delete `_placeholder`. Update the module docstring's STORY sentence and `_fault_code`'s docstring,
    which says "STORY-013's post-commit error event reuses this".
  - Read `settings.V1_SSE_KEEPALIVE_SECONDS` per request, so tests can monkeypatch it.
- **Mirror**: `app/routers/v1.py:202-240` (the logic being moved) and `app/routers/v1.py:174-181` (the
  header idiom).
- **Validate**:
  `C:/Users/tobip/.venvs/harness-ai/Scripts/python.exe -m pytest tests/test_v1_router.py tests/test_v1_errors.py tests/test_query_pipeline_audit_fields.py -q`.
  Everything passes except the placeholder test, which Task 5 removes.

### Task 5: Retire the placeholder test

- **File**: `tests/test_v1_router.py`
- **Action**: UPDATE
- **Implement**: delete `test_placeholder_stream_true_is_501_without_row` (`:349-356`) and the docstring
  paragraph at `:10-15` that pins it. Retitle the section comment at `:346`. Nothing else in the file
  changes. Its own docstring promised that.
- **Validate**: `... -m pytest tests/test_v1_router.py -q`

### Task 6: AC 1, every verdict and pre-upstream fault, streamed

- **File**: `tests/test_v1_errors.py`
- **Action**: UPDATE
- **Implement**:
  - Parametrize the verdict tests (`:137-331`) and the pre-upstream fault tests (duplicate lookup, usage
    gate, input redaction) with `stream` in `[False, True]`, using ids `json` and `sse`. `_body(..., stream=stream)`.
  - Add `assert not response.headers["content-type"].startswith("text/event-stream")`.
  - Leave the whole-body assertions as they are, so the same body and status are proven.
  - Give `_assert_one_v1_failure_row` and any row assertion a `streamed` argument, and check
    `row.streamed is stream`.
  - Add `test_pipeline_query_submit_refusal_*` with `stream=True` and the replaced `run_conversation`, so
    the refusal the dependency hides is covered too.
  - Leave the **post-upstream** fault tests (upstream 5xx/429/connect/timeout, output redaction) as
    non-streaming. Their streamed form is AC 4, in Task 7.
- **Mirror**: the existing parametrize style at `:604-614`.
- **Validate**: `... -m pytest tests/test_v1_errors.py -q`

### Task 7: HTTP tests for the stream (ACs 2, 3-order, 4)

- **File**: `tests/test_v1_sse.py`
- **Action**: UPDATE (DB section; `temp_db` plus the user fixture copied from `test_v1_errors.py:69-75`)
- **Implement** over `AsyncClient(transport=ASGITransport(app=app))`, with a helper `_events(text)` that
  splits on blank lines into `("comment", ...)`, `("data", json|"[DONE]")`:
  - **AC 2**: an answered request is `200`. `content-type` starts with `text/event-stream`.
    `cache-control == "no-cache"`. `x-accel-buffering == "no"`. There is no `x-harness-audit-id`. The
    events are exactly content, finish, `[DONE]`. With `stream_options.include_usage: true` they are
    content, finish, usage (`choices == []`, usage from the stub's split), `[DONE]`. Every `id` is
    `chatcmpl-harness-{row.id}`. One row: `success`, `ingress='v1'`, `profile='code'`, `streamed is True`.
    `include_usage` without `stream` sends no usage chunk, and nothing streams (the translator already
    gates it; one assertion).
  - The content equals the non-streaming body's content for the same stub (MVP: "chunks reassemble to the
    same content").
  - **AC 3, order**: `V1_SSE_KEEPALIVE_SECONDS=1` (monkeypatch `settings`) and a stub that sleeps 3.5 s
    (`time.sleep`, which is fine on an executor thread) give at least three `comment` events before the
    first `data`, and none after it.
  - **AC 4**, parametrized over `_upstream_over(_status(503))`, `_status(400)`, `_transport_failure(httpx.ReadTimeout)`,
    and output-redaction failure (`_real_then_raising` on the pipeline's redact binding with a `code`
    policy forced to `output=True`, as the existing redaction test does): `200` stream, the last event is
    one `data` with an `error` key whose object equals what the JSON path returns for the same fault
    (status-free, so compare `message`/`type`/`code`/`param`/`harness`), and no `[DONE]`. The rows match
    `_assert_one_v1_failure_row` with `streamed=True`. The provider canary is absent.
  - **Fast-failure commit (design decision 2)**: a stub that raises `OpenRouterError` at once still gives
    a `200` stream with an error event, not JSON.
  - The post-commit unexpected exception (design decision 3) is a stub `log_query` that raises on the
    success write. It gives an `internal_error` event, `caplog` has one ERROR from `app.routers.v1`, and
    the stream does not tear.
- **Validate**: `... -m pytest tests/test_v1_sse.py -q` (needs the libSQL container)

### Task 8: Direct-ASGI timing and disconnect (ACs 3-timing, 5)

- **File**: `tests/test_v1_sse.py`
- **Action**: UPDATE
- **Implement**:
  - `_drive(body, *, spec_version, disconnect_after=None)` builds an HTTP scope (path, method, headers
    including bearer and `content-type`, `"asgi": {"version": "3.0", "spec_version": spec_version}`), a
    `receive` that hands the body once and then waits on an `asyncio.Event` before returning
    `{"type": "http.disconnect"}`, and a `send` that records `(time.monotonic(), message)`. For `"2.4"` the
    disconnect is simulated by `send` raising `OSError` once the trigger is set. Bound everything by
    `asyncio.wait_for(..., _HARD_TIMEOUT)`.
  - **AC 3, timing**: with the 3.5 s stub and an interval of 1 s, at least three keep-alive body messages
    carry timestamps strictly before the first `data:` message. The gaps between keep-alives are within
    `[0.5, 2.0]` s, a generous range for Windows.
  - **AC 5, disconnect** (parametrized over spec `"2.0"` and `"2.4"`): use a `_BlockingUpstream`-style stub
    (event-released, no sleep) and an interval of 0.05. After the first keep-alive, trigger the disconnect.
    `_drive` returns, then release the stub. Poll in a bounded way until one row exists: `success=True`,
    `streamed=True`. Assert `usage_limits.charge` was called once (spy on `app.services.query_pipeline.charge`).
    `caplog` holds no ERROR, and nothing from the `asyncio` logger, after `gc.collect()`. Repeat with a
    stub that raises `OpenRouterError` after release: one `success=False` row and still no `asyncio` log
    (that path checks the done-callback).
  - **AC 5, concurrency**: `pipeline_pool(workers=24, block_first=20)` follows the
    `tests/test_pipeline_concurrency.py:191-222` pattern (copy the fixture and stub; do not import from
    another test module). Patch it at `app.routers.v1.call_openrouter` and set the interval to 0.05. Fire 20
    streamed posts as tasks and `wait_until_blocked(20)` through `asyncio.to_thread`. Then issue 10
    sequential `GET /health` calls, each timed: every one is under 0.2 s and returns `200`. Release, gather,
    and check all 20 are `200` streams ending in `[DONE]`. Use 20 rows.
- **Mirror**: `tests/test_pipeline_concurrency.py:191-300` (fixture order: release before shutdown;
  bounded waits; `asyncio.to_thread` for the blocking wait).
- **Validate**: `... -m pytest tests/test_v1_sse.py -q`, run three times to check for flakes

### Task 9: Regression sweep

- **Validate**:
  - `... -m pytest tests/test_v1_*.py tests/test_query_pipeline_audit_fields.py tests/test_query_pipeline_pii_profiles.py tests/test_query_outcomes_regression.py tests/test_pipeline_concurrency.py -q`
  - `... -m pytest tests/ -m "not db" -q` (Docker-free)
  - The full suite in the background (about 5.5 min). Rerun shared-DB flake files on their own before
    blaming the change.

---

## End-to-End Tests

For `/implement` to run against a live `uvicorn` with `call_openrouter` stubbed. The memory note says a real
upstream fails here, so there is no real-model E2E (STORY-014 brings the stub server):

- [ ] Start uvicorn in-process with `app.routers.v1.call_openrouter` replaced by a 3 s sleeper and
      `V1_SSE_KEEPALIVE_SECONDS=1`. Run `curl -N -H "Authorization: Bearer <tok>" -d '{"model":...,"messages":[...],"stream":true}' .../v1/chat/completions`
      and watch `: keep-alive` lines appear about once a second, then chunks and `data: [DONE]`.
- [ ] The same with `"stream_options":{"include_usage":true}`: the usage chunk appears before `[DONE]`.
- [ ] With `stream: true` and an injection prompt, the response is `HTTP 400` JSON with
      `code: suspicious_pattern` and no `text/event-stream`. The row has `streamed=1`.
- [ ] Optional: with the `openai` SDK in the venv, `client.chat.completions.create(..., stream=True)`
      reassembles the content, and a raising stub surfaces `openai.APIError`. STORY-015 owns the full
      version of this.

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| The signal and the pipeline completion race (Risk 5) | Branch on `upstream.called`, set on the worker before any result exists (design decision 1). A fast-stub test covers it |
| The pipeline is cancelled on disconnect, so no row and no charge | `asyncio.wait` never cancels, the generator does not own the task, and `detach` holds a strong reference. Tested on both ASGI spec paths |
| "exception was never retrieved" after a disconnect | The `detach` done-callback retrieves the exception. Tested with `gc.collect()` and `caplog` |
| The call-site scan breaks if the call is refactored into helpers | Exactly one `run_in_pipeline(run_conversation, ...)` stays in `chat_completions`. Task 4 validates against the scan |
| Timing flakes on Windows | Order is asserted over `AsyncClient`. Timing is a direct-ASGI test with wide bounds. Concurrency uses events, not sleeps |
| `ASGITransport` buffering hides streaming bugs | The direct-ASGI driver exercises Starlette's real send and disconnect paths (design decision 8) |
| A shared-DB flake looks like a stream bug | Rerun the errored files alone (memory note). A bare 500 on the JSON path is a storage stall |

---

## Validation

```bash
cd /c/Users/tobip/OneDrive/Documentos/prog/harness-ai
PY=/c/Users/tobip/.venvs/harness-ai/Scripts/python.exe
$PY -m pytest tests/test_v1_sse.py tests/test_v1_router.py tests/test_v1_errors.py -q
$PY -m pytest tests/test_query_pipeline_audit_fields.py tests/test_pipeline_concurrency.py tests/test_query_outcomes_regression.py -q
$PY -m pytest tests/ -m "not db" -q
```

---

## Acceptance Criteria

(Copied from story `STORY-013`)

- [ ] Given `stream: true` and a request the pipeline blocks or faults before the upstream call (every verdict in STORY-010, plus `DuplicateCheckError` / `UsageLimitError`), when it is sent, then the response is the same JSON error with the same status as without `stream`, not `text/event-stream`; the row has `streamed=1`.
- [ ] Given `stream: true` and an answered request, when it is read, then it is `200 text/event-stream` with `Cache-Control: no-cache` and `X-Accel-Buffering: no`, and its events are exactly: one chunk with `delta: {role: "assistant", content: <whole response>}`, one chunk with `delta: {}` and the `finish_reason`, a usage chunk with `choices: []` only when `stream_options.include_usage` is true, then `data: [DONE]`; every chunk's `id` is `chatcmpl-harness-{audit_id}`.
- [ ] Given an upstream stub that delays 3.5 s and `V1_SSE_KEEPALIVE_SECONDS=1`, when the stream is read, then at least three `: keep-alive` comment lines arrive before the first `data:` line, and none after it.
- [ ] Given an upstream failure or output-redaction failure after the upstream call started, when the stream is read, then it ends with one `data: {"error": {...}}` event (the STORY-011 object) and no `[DONE]`; the audit rows match the non-streaming case.
- [ ] Given a client that disconnects while the upstream call runs, when the pipeline finishes, then the success row is written and the tokens charged, and the event loop logs no unhandled exception; and given 20 concurrent streamed requests against a slow stub, `/health` answers within 200 ms throughout.
- [ ] All tasks completed
- [ ] `-m "not db"` passes without Docker, with ASCII-only output
- [ ] The call-site scans pass unchanged
- [ ] Follows existing patterns
