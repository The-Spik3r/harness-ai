"""PRD-015 STORY-013: the buffered `/v1` stream (Sections 6.4, 7.6).

A `stream: true` request is committed to `200 text/event-stream` only once
the upstream call has started; every earlier outcome is the JSON error
`tests/test_v1_errors.py` pins with its `stream` fixture. After commit the
stream is `: keep-alive` comments until the pipeline finishes, then the
content chunk, the finish chunk, the usage chunk on request and `[DONE]`, or
one `error` event and no `[DONE]`.

Three layers:

- **No storage.** The renderers and the writer in `app.services.v1_sse`, and
  the router's post-commit rendering (`_sse_events`) over hand-made futures.
  These run under `-m "not db"`.
- **Over HTTP.** `TestClient`, as the rest of the `/v1` suites. It proves
  event *order*, headers and rows.
- **Direct ASGI.** httpx's `ASGITransport` (0.28) and `TestClient` both
  collect the body before returning, so neither can show *when* a keep-alive
  arrived or let a client leave mid-stream. `_drive` calls the app itself
  with a timestamping `send` and a `receive` that disconnects on demand,
  under both of Starlette's disconnect paths: ASGI spec < 2.4 (uvicorn sends
  2.3) cancels the writer; 2.4 makes `send` raise `OSError`.

Blocking stubs wait on `threading.Event`s, never on sleeps, except the AC 3
stub, whose 3.5 s delay is the criterion itself. Every wait is bounded by
`_HARD_TIMEOUT`, because `pytest-timeout` is not installed.
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import asyncio
import concurrent.futures
import gc
import json
import logging
import threading
import time
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from starlette.requests import ClientDisconnect

from app.config import settings
from app.db.database import get_audit_log, get_connection, insert_user
from app.db.models import User
from app.main import app
from app.models.schemas import QueryBlockedSuspiciousResponse, QuerySuccessResponse
from app.models.v1_schemas import (
    AssistantMessage,
    ChatCompletion,
    Choice,
    ErrorDetail,
    ErrorResponse,
    HarnessCompletionInfo,
    Usage,
)
from app.routers.v1 import _sse_events, _Upstream
from app.services import pii_policy, pii_redactor, pipeline_executor, query_pipeline, v1_sse
from app.services.identity import Identity, hash_token
from app.services.openrouter_client import OpenRouterError, OpenRouterResult
from app.services.openrouter_client import call_openrouter as _real_call_openrouter
from app.services.pii_redactor import PiiRedactorError

_AUTH_USER_ID = "juan@empresa.com"
_AUTH_TOKEN = "test-user-token"
_AUTH_HEADERS = {"Authorization": f"Bearer {_AUTH_TOKEN}"}
_MODEL = "openai/gpt-4o"
_PROMPT = "hello world"
_ANSWER = "Hello from the model."
_PATH = "/v1/chat/completions"
# The provider's body in fault tests: it must never reach an event.
_CANARY = "CANARY-7f3a-content"

_HARD_TIMEOUT = 15.0

client = TestClient(app, headers=_AUTH_HEADERS)


@pytest.fixture
def temp_db(temp_db):
    """conftest's initialized database, plus this suite's authenticated user."""
    insert_user(
        User(user_id=_AUTH_USER_ID, role="user", token_hash=hash_token(_AUTH_TOKEN))
    )
    return temp_db


@pytest.fixture
def warm_presidio():
    """The PII analyzer loaded before a timing window opens.

    No lifespan runs here, so the first pipeline call would otherwise pay the
    spaCy load inside the window (`tests/test_pipeline_concurrency.py`'s
    `_warm_presidio` has the full reasoning).
    """
    pii_redactor.load()


class _Answering:
    """The (messages, model, api_key) stub, with the token split for `usage`."""

    def __init__(self, delay=0.0, finish_reason="stop"):
        self.calls = []
        self.delay = delay
        self.finish_reason = finish_reason

    def __call__(self, messages, model="gpt-4", api_key=None):
        self.calls.append(model)
        if self.delay:
            time.sleep(self.delay)
        return OpenRouterResult(
            response=_ANSWER, model_used=model, tokens_used=908,
            input_tokens=812, output_tokens=96, finish_reason=self.finish_reason,
        )


@pytest.fixture
def upstream(monkeypatch):
    stub = _Answering()
    monkeypatch.setattr("app.routers.v1.call_openrouter", stub)
    return stub


def _body(content=_PROMPT, **extra):
    return {"model": _MODEL, "messages": [{"role": "user", "content": content}], **extra}


def _events(text):
    """An SSE body as [("comment", text) | ("data", dict | "[DONE]")], in order."""
    events = []
    for block in text.split("\n\n"):
        if not block:
            continue
        assert "\n" not in block, f"one line per event expected: {block!r}"
        if block.startswith(":"):
            events.append(("comment", block[1:].strip()))
        else:
            assert block.startswith("data: "), block
            payload = block[len("data: "):]
            events.append(("data", payload if payload == "[DONE]" else json.loads(payload)))
    return events


def _data(events):
    return [payload for kind, payload in events if kind == "data"]


def _rows():
    with get_connection() as conn:
        ids = [row["id"] for row in conn.execute("SELECT id FROM audit_logs ORDER BY id").fetchall()]
    return [get_audit_log(row_id) for row_id in ids]


def _assert_committed(response):
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"
    # The row does not exist at commit time (Section 7.6).
    assert "x-harness-audit-id" not in response.headers


# =============================================================================
# No storage: v1_sse's renderers and writer
# =============================================================================


def _completion(finish_reason="stop", usage=(812, 96, 908), audit_id=42):
    return ChatCompletion(
        id=f"chatcmpl-harness-{audit_id}",
        created=1700000000,
        model=_MODEL,
        choices=[Choice(message=AssistantMessage(content=_ANSWER), finish_reason=finish_reason)],
        usage=Usage(prompt_tokens=usage[0], completion_tokens=usage[1], total_tokens=usage[2]),
        harness=HarnessCompletionInfo(audit_id=audit_id, pii_redacted=False, pii_entities_masked=[]),
    )


def _chunk(choices, **extra):
    return {
        "id": "chatcmpl-harness-42", "object": "chat.completion.chunk",
        "created": 1700000000, "model": _MODEL, "choices": choices, **extra,
    }


_CONTENT_CHUNK = _chunk(
    [{"index": 0, "delta": {"role": "assistant", "content": _ANSWER}, "finish_reason": None}]
)
_FINISH_CHUNK = _chunk([{"index": 0, "delta": {}, "finish_reason": "stop"}])
_USAGE_CHUNK = _chunk([], usage={"prompt_tokens": 812, "completion_tokens": 96, "total_tokens": 908})


def test_completion_events_without_usage():
    events = _events("".join(v1_sse.completion_events(_completion(), include_usage=False)))

    assert events == [("data", _CONTENT_CHUNK), ("data", _FINISH_CHUNK), ("data", "[DONE]")]


def test_completion_events_with_usage():
    events = _events("".join(v1_sse.completion_events(_completion(), include_usage=True)))

    assert events == [
        ("data", _CONTENT_CHUNK), ("data", _FINISH_CHUNK), ("data", _USAGE_CHUNK), ("data", "[DONE]"),
    ]


def test_completion_events_carry_the_finish_reason():
    events = _events("".join(v1_sse.completion_events(_completion("length"), include_usage=False)))

    assert _data(events)[1]["choices"][0]["finish_reason"] == "length"


def test_error_event_is_the_error_object_and_no_done():
    body = ErrorResponse(error=ErrorDetail(
        message="probe", type="api_error", param=None, code="upstream_error", harness=None
    ))

    events = _events(v1_sse.error_event(body))

    assert events == [("data", body.model_dump(mode="json"))]


@pytest.mark.asyncio
async def test_stream_sends_keepalives_until_the_outcome_then_renders_once():
    loop = asyncio.get_running_loop()
    pipeline = loop.create_future()
    loop.call_later(0.1, pipeline.set_result, "done")
    rendered = []

    def _render(future):
        rendered.append(future.result())
        return ["data: x\n\n"]

    sent = [event async for event in v1_sse.stream(pipeline, _render, 0.01)]

    assert rendered == ["done"]
    assert sent[-1] == "data: x\n\n"
    assert sent.count(v1_sse.KEEPALIVE) >= 2
    assert set(sent[:-1]) == {v1_sse.KEEPALIVE}


@pytest.mark.asyncio
async def test_stream_of_a_finished_pipeline_sends_no_keepalive():
    pipeline = asyncio.get_running_loop().create_future()
    pipeline.set_result("done")

    sent = [event async for event in v1_sse.stream(pipeline, lambda f: ["data: x\n\n"], 0.01)]

    assert sent == ["data: x\n\n"]


@pytest.mark.asyncio
async def test_closing_the_stream_leaves_the_pipeline_running():
    pipeline = asyncio.get_running_loop().create_future()
    writer = v1_sse.stream(pipeline, lambda f: ["data: x\n\n"], 0.01)

    assert await writer.__anext__() == v1_sse.KEEPALIVE
    await writer.aclose()

    assert not pipeline.done()
    pipeline.set_result("done")


@pytest.mark.asyncio
async def test_cancelling_the_writer_leaves_the_pipeline_running():
    pipeline = asyncio.get_running_loop().create_future()

    async def _consume():
        async for _ in v1_sse.stream(pipeline, lambda f: [], 0.01):
            pass

    task = asyncio.ensure_future(_consume())
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert not pipeline.done()
    pipeline.set_result("done")


def _never_retrieved_logged(detach: bool, caplog) -> bool:
    """Whether an abandoned failed future is reported, with or without `detach`."""
    loop = asyncio.new_event_loop()
    try:
        future = loop.create_future()
        if detach:
            v1_sse.detach(future)
        future.set_exception(RuntimeError("probe"))
        loop.run_until_complete(asyncio.sleep(0))  # run the done-callbacks
        del future
        gc.collect()
    finally:
        loop.close()
    return any("never retrieved" in r.getMessage() for r in caplog.records)


def test_detach_retrieves_the_outcome_so_nothing_is_logged(caplog):
    with caplog.at_level(logging.ERROR, logger="asyncio"):
        # The control: without detach, the loop reports it.
        assert _never_retrieved_logged(detach=False, caplog=caplog)
        caplog.clear()
        assert not _never_retrieved_logged(detach=True, caplog=caplog)
    assert not v1_sse._RUNNING


@pytest.mark.asyncio
async def test_detach_holds_the_pipeline_until_done():
    pipeline = asyncio.get_running_loop().create_future()
    v1_sse.detach(pipeline)

    assert pipeline in v1_sse._RUNNING
    pipeline.set_result("done")
    await asyncio.sleep(0)
    assert pipeline not in v1_sse._RUNNING


@pytest.mark.asyncio
async def test_wait_for_commit_returns_on_the_signal_without_cancelling_the_pipeline():
    pipeline = asyncio.get_running_loop().create_future()
    started = asyncio.Event()
    asyncio.get_running_loop().call_later(0.01, started.set)

    await asyncio.wait_for(v1_sse.wait_for_commit(pipeline, started), _HARD_TIMEOUT)

    assert not pipeline.done()
    pipeline.set_result("done")


@pytest.mark.asyncio
async def test_wait_for_commit_returns_when_the_pipeline_finishes_first():
    pipeline = asyncio.get_running_loop().create_future()
    asyncio.get_running_loop().call_later(0.01, pipeline.set_result, "verdict")

    await asyncio.wait_for(v1_sse.wait_for_commit(pipeline, asyncio.Event()), _HARD_TIMEOUT)

    assert pipeline.result() == "verdict"


# --- The router's post-commit rendering (no storage) ------------------------------


_IDENTITY = Identity(user_id=_AUTH_USER_ID, role="user")


def _done(result=None, exc=None):
    """A finished outcome. `_sse_events` only calls `.result()`, so no loop is needed."""
    future = concurrent.futures.Future()
    if exc is not None:
        future.set_exception(exc)
    else:
        future.set_result(result)
    return future


def _upstream_wrapper(result=None):
    # Never called here, so it needs no loop to signal.
    wrapper = _Upstream(loop=None)
    wrapper.result = result
    return wrapper


def test_sse_events_for_a_success_are_the_chunks():
    success = QuerySuccessResponse(
        response=_ANSWER, audit_id=7, model_used=_MODEL, tokens_used=908,
        pii_redacted=False, pii_entities_masked=[],
    )
    upstream_result = OpenRouterResult(
        response=_ANSWER, model_used=_MODEL, tokens_used=908, input_tokens=812,
        output_tokens=96, finish_reason="stop",
    )

    events = _events("".join(_sse_events(
        _done(success), upstream=_upstream_wrapper(upstream_result), identity=_IDENTITY,
        include_usage=True,
    )))

    assert [payload["id"] for payload in _data(events)[:-1]] == ["chatcmpl-harness-7"] * 3
    assert _data(events)[-1] == "[DONE]"


def test_sse_events_for_an_unexpected_exception_are_internal_error(caplog):
    with caplog.at_level(logging.ERROR, logger="app.routers.v1"):
        events = _events("".join(_sse_events(
            _done(exc=RuntimeError(_CANARY)), upstream=_upstream_wrapper(), identity=_IDENTITY,
            include_usage=False,
        )))

    assert events == [("data", {"error": {
        "message": "Internal Server Error", "type": "api_error", "param": None,
        "code": "internal_error", "harness": None,
    }})]
    records = [r for r in caplog.records if r.name == "app.routers.v1"]
    assert [r.levelno for r in records] == [logging.ERROR]


def test_sse_events_for_a_verdict_after_commit_are_its_error(caplog):
    # Risk 5 says this cannot happen; the branch is defensive.
    verdict = QueryBlockedSuspiciousResponse(
        reason="Suspicious pattern detected", pattern="ignore previous instructions"
    )

    with caplog.at_level(logging.WARNING, logger="app.routers.v1"):
        events = _events("".join(_sse_events(
            _done(verdict), upstream=_upstream_wrapper(), identity=_IDENTITY, include_usage=False,
        )))

    (payload,) = _data(events)
    assert payload["error"]["code"] == "suspicious_pattern"
    assert payload["error"]["harness"]["pattern"] == "ignore previous instructions"
    assert [r.getMessage() for r in caplog.records if r.name == "app.routers.v1"] == [
        f"v1 verdict after stream commit: user_id={_AUTH_USER_ID} code=suspicious_pattern"
    ]


# =============================================================================
# Over HTTP: AC 2, AC 3 (order), AC 4
# =============================================================================


def test_answered_stream_is_the_chunk_sequence(temp_db, upstream):
    response = client.post(_PATH, json=_body(stream=True))

    _assert_committed(response)
    (row,) = _rows()
    audit_id = f"chatcmpl-harness-{row.id}"
    events = _events(response.text)
    assert [kind for kind, _ in events] == ["data", "data", "data"]
    content, finish, done = _data(events)
    assert done == "[DONE]"
    assert content["choices"] == [
        {"index": 0, "delta": {"role": "assistant", "content": _ANSWER}, "finish_reason": None}
    ]
    assert finish["choices"] == [{"index": 0, "delta": {}, "finish_reason": "stop"}]
    for chunk in (content, finish):
        assert (chunk["id"], chunk["object"], chunk["model"]) == (
            audit_id, "chat.completion.chunk", _MODEL
        )
        assert "usage" not in chunk
    assert content["created"] == finish["created"]
    assert (row.success, row.ingress, row.profile, row.streamed) == (True, "v1", "code", True)


def test_include_usage_adds_the_usage_chunk(temp_db, upstream):
    response = client.post(
        _PATH, json=_body(stream=True, stream_options={"include_usage": True})
    )

    _assert_committed(response)
    (row,) = _rows()
    data = _data(_events(response.text))
    assert len(data) == 4 and data[-1] == "[DONE]"
    usage = data[2]
    assert usage["id"] == f"chatcmpl-harness-{row.id}"
    assert usage["choices"] == []
    assert usage["usage"] == {"prompt_tokens": 812, "completion_tokens": 96, "total_tokens": 908}


def test_include_usage_without_stream_is_a_plain_completion(temp_db, upstream):
    response = client.post(_PATH, json=_body(stream_options={"include_usage": True}))

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.json()["object"] == "chat.completion"


def test_streamed_content_equals_the_non_streamed_content(temp_db, upstream):
    streamed = client.post(_PATH, json=_body(f"{_PROMPT} {uuid4()}", stream=True))
    plain = client.post(_PATH, json=_body(f"{_PROMPT} {uuid4()}"))

    deltas = [chunk["choices"][0]["delta"].get("content", "")
              for chunk in _data(_events(streamed.text))[:-1] if chunk["choices"]]
    plain_body = plain.json()
    assert "".join(deltas) == plain_body["choices"][0]["message"]["content"]
    finish = _data(_events(streamed.text))[1]["choices"][0]["finish_reason"]
    assert finish == plain_body["choices"][0]["finish_reason"]


def test_keepalives_come_before_the_first_data_and_never_after(temp_db, monkeypatch, warm_presidio):
    # AC 3, order. Timing is test_keepalives_arrive_at_the_interval below.
    monkeypatch.setattr(settings, "V1_SSE_KEEPALIVE_SECONDS", 1.0)
    monkeypatch.setattr("app.routers.v1.call_openrouter", _Answering(delay=3.5))

    response = client.post(_PATH, json=_body(stream=True))

    _assert_committed(response)
    kinds = [kind for kind, _ in _events(response.text)]
    first_data = kinds.index("data")
    assert first_data >= 3
    assert set(kinds[:first_data]) == {"comment"}
    assert set(kinds[first_data:]) == {"data"}
    assert [text for kind, text in _events(response.text) if kind == "comment"] == (
        ["keep-alive"] * first_data
    )


# --- AC 4: faults after the upstream call started ---------------------------------


def _upstream_over(handler):
    """The real call_openrouter over a MockTransport (tests/test_v1_errors.py)."""
    transport = httpx.MockTransport(handler)

    def _call(messages, model="gpt-4", api_key=None, params=None):
        with httpx.Client(transport=transport) as http_client:
            return _real_call_openrouter(
                messages, model=model, api_key=api_key, params=params, client=http_client
            )

    return _call


def _status(status_code):
    return lambda request: httpx.Response(status_code, text=_CANARY)


def _timeout(request):
    raise httpx.ReadTimeout("probe", request=request)


_ANSWER_BODY = {
    "choices": [{"message": {"content": _ANSWER}, "finish_reason": "stop"}],
    "usage": {"total_tokens": 12},
}


def _real_then_raising(real, exc):
    """Real on the first call (the user turn), raising on the second (the response)."""
    calls = []

    def _redact(*args, **kwargs):
        calls.append(args)
        if len(calls) == 1:
            return real(*args, **kwargs)
        raise exc

    return _redact


def _upstream_503(monkeypatch):
    monkeypatch.setattr("app.routers.v1.call_openrouter", _upstream_over(_status(503)))


def _upstream_400(monkeypatch):
    monkeypatch.setattr("app.routers.v1.call_openrouter", _upstream_over(_status(400)))


def _upstream_timeout(monkeypatch):
    monkeypatch.setattr("app.routers.v1.call_openrouter", _upstream_over(_timeout))


def _output_redaction(monkeypatch):
    # `code` does not redact output by default (PRD-012 D1); conftest's
    # _default_pii_policy restores the policies afterwards. A fresh
    # wrapper per request, so each one's first call is the input.
    monkeypatch.setattr(
        "app.routers.v1.call_openrouter",
        _upstream_over(lambda request: httpx.Response(200, json=_ANSWER_BODY)),
    )
    monkeypatch.setattr(settings, "PII_CODE_REDACT_OUTPUT", True)
    pii_policy.load()
    real = query_pipeline.redact_for_policy
    exc = PiiRedactorError("PII analysis failed: probe on output")

    def _install():
        monkeypatch.setattr(query_pipeline, "redact_for_policy", _real_then_raising(real, exc))

    return _install


@pytest.mark.parametrize(
    "install, code",
    [
        (_upstream_503, "upstream_unavailable"),
        (_upstream_400, "upstream_error"),
        (_upstream_timeout, "upstream_unavailable"),
        (_output_redaction, "redaction_failed"),
    ],
    ids=["upstream-5xx", "upstream-4xx", "upstream-timeout", "output-redaction"],
)
def test_post_commit_fault_is_one_error_event_without_done(temp_db, monkeypatch, install, code):
    reinstall = install(monkeypatch)

    if reinstall:
        reinstall()
    streamed = client.post(_PATH, json=_body(stream=True))
    if reinstall:
        reinstall()
    plain = client.post(_PATH, json=_body())

    _assert_committed(streamed)
    events = _events(streamed.text)
    assert [kind for kind, _ in events] == ["data"]
    (payload,) = _data(events)
    # The STORY-011 object, exactly as the JSON path sends it.
    assert payload == plain.json()
    assert payload["error"]["code"] == code
    assert _CANARY not in streamed.text
    # One row each, the same fault, told apart only by `streamed` (PRD-013 6.9).
    rows = _rows()
    assert [(row.success, row.ingress, row.profile, row.streamed) for row in rows] == [
        (False, "v1", "code", True), (False, "v1", "code", False),
    ]
    assert rows[0].error_message == rows[1].error_message


def test_an_upstream_that_fails_at_once_still_commits(temp_db, monkeypatch):
    # Design decision 2: being called is the commit point, so the fault is an
    # event even when it comes before the first keep-alive could.
    def _fail(messages, model="gpt-4", api_key=None):
        raise OpenRouterError("OpenRouter request failed: probe", retryable=True)

    monkeypatch.setattr("app.routers.v1.call_openrouter", _fail)

    response = client.post(_PATH, json=_body(stream=True))

    _assert_committed(response)
    (payload,) = _data(_events(response.text))
    assert payload["error"]["code"] == "upstream_unavailable"
    assert "[DONE]" not in response.text


def test_post_commit_unexpected_exception_is_internal_error_event(temp_db, upstream, monkeypatch, caplog):
    # A storage failure on the success row: past every arm the router maps.
    real_log_query = query_pipeline.log_query

    def _log_query(**kwargs):
        if kwargs.get("success") is True:
            raise RuntimeError(f"driver said {_CANARY}")
        return real_log_query(**kwargs)

    monkeypatch.setattr(query_pipeline, "log_query", _log_query)

    with caplog.at_level(logging.ERROR, logger="app.routers.v1"):
        response = client.post(_PATH, json=_body(stream=True))

    _assert_committed(response)
    (payload,) = _data(_events(response.text))
    assert payload["error"]["code"] == "internal_error"
    assert _CANARY not in response.text
    assert [r.levelno for r in caplog.records if r.name == "app.routers.v1"] == [logging.ERROR]


# =============================================================================
# Direct ASGI: AC 3 (timing), AC 5 (disconnect)
# =============================================================================


async def _drive(body, *, spec_version="2.3", disconnect_after_keepalives=None):
    """Run one request through the app, recording `(time, message)` per send.

    With `disconnect_after_keepalives=n`, the client leaves once `n`
    keep-alives arrived: `receive` returns `http.disconnect` (spec < 2.4),
    or `send` raises `OSError` (2.4), which Starlette turns into
    `ClientDisconnect`.
    """
    raw = json.dumps(body).encode()
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": spec_version},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": _PATH,
        "raw_path": _PATH.encode(),
        "root_path": "",
        "query_string": b"",
        "headers": [
            (b"host", b"test"),
            (b"authorization", f"Bearer {_AUTH_TOKEN}".encode()),
            (b"content-type", b"application/json"),
            (b"content-length", str(len(raw)).encode()),
        ],
        "client": ("127.0.0.1", 50000),
        "server": ("test", 80),
    }
    sent = []
    left = asyncio.Event()
    body_sent = False

    async def receive():
        nonlocal body_sent
        if not body_sent:
            body_sent = True
            return {"type": "http.request", "body": raw, "more_body": False}
        await left.wait()
        return {"type": "http.disconnect"}

    async def send(message):
        if left.is_set() and spec_version == "2.4":
            raise OSError("client gone")
        sent.append((time.monotonic(), message))
        keepalives = sum(1 for _, m in sent if m.get("body", b"").startswith(b":"))
        if disconnect_after_keepalives is not None and keepalives >= disconnect_after_keepalives:
            left.set()

    try:
        await asyncio.wait_for(app(scope, receive, send), _HARD_TIMEOUT)
    except ClientDisconnect:
        assert spec_version == "2.4"
    return sent


def _bodies(sent):
    return [(at, m["body"].decode()) for at, m in sent if m["type"] == "http.response.body" and m.get("body")]


@pytest.mark.asyncio
async def test_keepalives_arrive_at_the_interval(temp_db, monkeypatch, warm_presidio):
    # AC 3, timing: 3.5 s upstream, 1 s interval.
    monkeypatch.setattr(settings, "V1_SSE_KEEPALIVE_SECONDS", 1.0)
    monkeypatch.setattr("app.routers.v1.call_openrouter", _Answering(delay=3.5))

    sent = await _drive(_body(stream=True))

    assert sent[0][1]["status"] == 200
    bodies = _bodies(sent)
    first_data = next(i for i, (_, text) in enumerate(bodies) if text.startswith("data:"))
    keepalives = [at for at, text in bodies[:first_data]]
    assert len(keepalives) >= 3
    assert all(text == v1_sse.KEEPALIVE for _, text in bodies[:first_data])
    assert not any(text.startswith(":") for _, text in bodies[first_data:])
    # Generous for Windows timers; the point is "about once a second".
    gaps = [b - a for a, b in zip(keepalives, keepalives[1:])]
    assert all(0.5 <= gap <= 2.0 for gap in gaps), gaps
    assert keepalives[-1] < bodies[first_data][0]


class _BlockingUpstream:
    """Parks every call on `release`; announces arrivals (test_pipeline_concurrency)."""

    def __init__(self, fail=False):
        self.release = threading.Event()
        self._cond = threading.Condition()
        self.arrived = 0
        self.fail = fail

    def __call__(self, messages, model="gpt-4", api_key=None):
        with self._cond:
            self.arrived += 1
            self._cond.notify_all()
        if not self.release.wait(timeout=_HARD_TIMEOUT):
            raise AssertionError("blocked upstream was never released")
        if self.fail:
            raise OpenRouterError("OpenRouter request failed: probe", retryable=True)
        return OpenRouterResult(
            response=_ANSWER, model_used=model, tokens_used=908, input_tokens=812, output_tokens=96,
        )

    def wait_until_arrived(self, n):
        deadline = time.monotonic() + _HARD_TIMEOUT
        with self._cond:
            while self.arrived < n:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not self._cond.wait(timeout=remaining):
                    raise AssertionError(f"only {self.arrived} of {n} calls reached the upstream")


@pytest.fixture
def blocking(monkeypatch):
    """A `_BlockingUpstream` factory; every stub is released before the pool shuts down.

    `shutdown(wait=True)` joins the workers, so shutting down while one is
    parked would hang the teardown (test_pipeline_concurrency's order).
    """
    stubs = []

    def make(workers=8, fail=False):
        monkeypatch.setattr(settings, "PIPELINE_MAX_WORKERS", workers)
        pipeline_executor.shutdown()
        stub = _BlockingUpstream(fail=fail)
        stubs.append(stub)
        monkeypatch.setattr("app.routers.v1.call_openrouter", stub)
        return stub

    try:
        yield make
    finally:
        for stub in stubs:
            stub.release.set()
        pipeline_executor.shutdown()


async def _until_rows(n):
    deadline = time.monotonic() + _HARD_TIMEOUT
    while True:
        rows = await asyncio.to_thread(_rows)
        if len(rows) >= n:
            return rows
        assert time.monotonic() < deadline, f"{len(rows)} of {n} rows written"
        await asyncio.sleep(0.05)


def _charged():
    with get_connection() as conn:
        row = conn.execute(
            "SELECT input_tokens, output_tokens FROM usage_daily WHERE user_id = ?", (_AUTH_USER_ID,)
        ).fetchone()
    return (row["input_tokens"], row["output_tokens"])


def _loop_errors(caplog):
    return [r for r in caplog.records if r.name == "asyncio" or r.levelno >= logging.ERROR]


@pytest.mark.asyncio
@pytest.mark.parametrize("spec_version", ["2.3", "2.4"])
async def test_disconnect_leaves_the_pipeline_to_write_and_charge(
    temp_db, monkeypatch, blocking, warm_presidio, caplog, spec_version
):
    monkeypatch.setattr(settings, "V1_SSE_KEEPALIVE_SECONDS", 0.05)
    stub = blocking()

    with caplog.at_level(logging.WARNING):
        sent = await _drive(
            _body(stream=True), spec_version=spec_version, disconnect_after_keepalives=1
        )
        # The client is gone and the upstream call is still parked.
        assert not any(b"data:" in m.get("body", b"") for _, m in sent)
        assert stub.arrived == 1
        stub.release.set()

        (row,) = await _until_rows(1)
        await asyncio.sleep(0.05)
        gc.collect()

    assert (row.success, row.streamed) == (True, True)
    assert await asyncio.to_thread(_charged) == (812, 96)
    assert _loop_errors(caplog) == []


@pytest.mark.asyncio
async def test_disconnect_then_upstream_failure_logs_nothing_unhandled(
    temp_db, monkeypatch, blocking, warm_presidio, caplog
):
    # The outcome is an exception nobody renders: detach's callback retrieves it.
    monkeypatch.setattr(settings, "V1_SSE_KEEPALIVE_SECONDS", 0.05)
    stub = blocking(fail=True)

    with caplog.at_level(logging.WARNING):
        await _drive(_body(stream=True), disconnect_after_keepalives=1)
        stub.release.set()
        (row,) = await _until_rows(1)
        await asyncio.sleep(0.05)
        gc.collect()

    assert (row.success, row.streamed) == (False, True)
    assert _loop_errors(caplog) == []


@pytest.mark.asyncio
async def test_health_answers_while_twenty_streams_wait(temp_db, monkeypatch, blocking, warm_presidio):
    # AC 5: twenty committed streams sending keep-alives on the loop.
    monkeypatch.setattr(settings, "V1_SSE_KEEPALIVE_SECONDS", 0.05)
    stub = blocking(workers=24)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers=_AUTH_HEADERS
    ) as async_client:
        tasks = [
            asyncio.create_task(async_client.post(_PATH, json=_body(f"stream {i} {uuid4()}", stream=True)))
            for i in range(20)
        ]
        await asyncio.wait_for(asyncio.to_thread(stub.wait_until_arrived, 20), _HARD_TIMEOUT)

        timings = []
        for _ in range(10):
            started = time.monotonic()
            health = await async_client.get("/health")
            timings.append(time.monotonic() - started)
            assert health.status_code == 200
            await asyncio.sleep(0.02)

        stub.release.set()
        responses = await asyncio.wait_for(asyncio.gather(*tasks), _HARD_TIMEOUT)

    assert max(timings) < 0.2, timings
    for response in responses:
        _assert_committed(response)
        assert response.text.endswith(v1_sse.DONE)
    assert len(await asyncio.to_thread(_rows)) == 20
