"""PRD-021 STORY-010: `/v1` real-time SSE and `reasoning_content`.

Sections 6.3, 6.4, 6.6; F8; D9, D15, D16, D21, D22; T1, T5, T13. Three layers:

- **No storage.** `v1_sse.realtime_events` over a hand-fed queue and future:
  order, keep-alive, coalescing, the drain of a threaded burst, the tail and
  `on_close`; `_CommitSink`'s `forward=False` and the verdict-after-commit
  warning.
- **Direct ASGI** (`_drive`, the `tests/test_v1_sse.py` approach): httpx and
  `TestClient` collect the body first, so only a timestamping `send` shows
  *when* a chunk arrived or lets a client leave mid-stream. The upstream is a
  scripted `stream_upstream` generator injected through
  `app.routers.v1.run_conversation`; the registry is file mode
  (`tests/_providers.py`) because legacy mode never streams (OD1).
- **Off means today** (D22): switch off, switch on without a grant and legacy
  mode all reach `call_openrouter`, never the streamed arm.

Every wait is bounded by `_HARD_TIMEOUT` (`pytest-timeout` is not installed).
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import asyncio
import concurrent.futures
import dataclasses
import functools
import gc
import json
import logging
import re
import threading
import time
from uuid import uuid4

import pytest

import app.services.authz as authz
import app.services.query_pipeline as query_pipeline
from app.config import settings
from app.db.database import get_audit_log, get_connection, insert_user
from app.db.models import User
from app.main import app
from app.models.schemas import QueryBlockedSuspiciousResponse
from app.models.v1_schemas import (
    AssistantMessage,
    ChatCompletion,
    Choice,
    CompletionToolCall,
    HarnessCompletionInfo,
    ToolCallFunction,
    Usage,
)
from app.routers.v1 import _CommitSink, _realtime_tail, _Upstream, _visibility
from app.services import pii_policy, pii_redactor, tool_release, v1_sse
from app.services.delivery import (
    CommittedEvent,
    ContentEvent,
    PhaseEvent,
    ReasoningEvent,
    StageEvent,
)
from app.services.identity import Identity, hash_token
from app.services.openrouter_client import OpenRouterResult
from app.services.pii_redactor import PiiRedactorError
from app.services.query_pipeline import run_conversation
from app.services.upstream import (
    Finish,
    ReasoningDelta,
    TextDelta,
    ToolCallDelta,
    UpstreamError,
    UsageReport,
)
from tests._providers import provider_file  # noqa: F401  (fixture)

_HARD_TIMEOUT = 15.0
_PATH = "/v1/chat/completions"
_USER = "juan@empresa.com"
_TOKEN = "test-user-token"
_ID = re.compile(r"^chatcmpl-harness-rt-[0-9a-f]{32}$")
_SUBMIT = authz.PERMISSION_QUERY_SUBMIT
_RT = authz.PERMISSION_STREAM_REALTIME
_RV = authz.PERMISSION_REASONING_VIEW
_USAGE = UsageReport(prompt_tokens=3, completion_tokens=4, total_tokens=7)
_AUDIT_REF = "0" * 32
_IDENTITY = Identity(user_id=_USER, role="user")
_YAML = """
version: 1
default_model: s/m
providers:
  - name: s
    label: Stub
    type: openai_compatible
    base_url: http://127.0.0.1:9/v1
    insecure_http: true
    usage_missing: estimate
    byok: true
    estimate_chars_per_token: 1
    timeout_seconds: 30
    models:
      - id: s/m
        upstream: up-m
        capabilities: {tools: true, streaming: true, reasoning: true}
"""

# =============================================================================
# No storage: realtime_events
# =============================================================================


def _completion(content="", calls=(), finish="stop", completion_id="chatcmpl-harness-1"):
    message = (
        AssistantMessage(content=content or None, tool_calls=list(calls))
        if calls
        else AssistantMessage(content=content)
    )
    return ChatCompletion(
        id=completion_id, created=1, model="s/m",
        choices=[Choice(message=message, finish_reason=finish)],
        usage=Usage(prompt_tokens=3, completion_tokens=4, total_tokens=7),
        harness=HarnessCompletionInfo(audit_id=1, audit_ref=_AUDIT_REF),
    )


_READ = CompletionToolCall(id="call_r", function=ToolCallFunction(name="read", arguments='{"path":"a"}'))


def _parse(items):
    """Yielded strings as [("comment", text) | ("data", dict | "[DONE]")]."""
    out = []
    for item in items:
        assert item.endswith("\n\n"), item
        body = item[:-2]
        if body.startswith(":"):
            out.append(("comment", body[1:].strip()))
        else:
            assert body.startswith("data: "), item
            payload = body[len("data: "):]
            out.append(("data", payload if payload == "[DONE]" else json.loads(payload)))
    return out


def _deltas(parsed):
    return [p["choices"][0]["delta"] for kind, p in parsed
            if kind == "data" and p != "[DONE]" and p["choices"]]


class _Rig:
    """A queue, a pipeline future and the generator under test."""

    def __init__(self, *, tail=None, coalesce_s=0.0, interval=10.0, include_usage=False):
        self.loop = asyncio.get_running_loop()
        self.queue = asyncio.Queue()
        self.pipeline = self.loop.create_future()
        self.closed = []
        self.tail_calls = 0
        self._tail = tail or (lambda: v1_sse.Tail(_completion(), ()))
        self.gen = v1_sse.realtime_events(
            self.queue, self.pipeline, created=1, model="s/m", tail=self._render,
            include_usage=include_usage, interval=interval, coalesce_s=coalesce_s,
            on_close=self.closed.append,
        )

    def _render(self, pipeline):
        self.tail_calls += 1
        return self._tail()

    def put(self, *events):
        for event in events:
            self.queue.put_nowait(event)

    def finish_after(self, seconds):
        self.loop.call_later(seconds, self.pipeline.set_result, "done")

    async def run(self):
        out = []

        async def consume():
            async for item in self.gen:
                out.append((time.monotonic(), item))

        await asyncio.wait_for(consume(), _HARD_TIMEOUT)
        return out


@pytest.mark.asyncio
async def test_sequence_role_deltas_tool_calls_notes_finish_usage_done():
    rig = _Rig(
        tail=lambda: v1_sse.Tail(
            _completion("ab", calls=[_READ], finish="tool_calls"), ("note one", "note two")
        ),
        include_usage=True,
    )
    rig.put(CommittedEvent("chatcmpl-harness-rt-" + "a" * 32), StageEvent("authorizing"),
            PhaseEvent("waiting"), ContentEvent("a"), ReasoningEvent("why"), ContentEvent("b"))
    rig.pipeline.set_result("done")

    parsed = _parse([item for _, item in await rig.run()])

    deltas = _deltas(parsed)
    assert deltas[0] == {"role": "assistant", "content": ""}
    assert deltas[1:4] == [{"content": "a"}, {"reasoning_content": "why"}, {"content": "b"}]
    assert deltas[4]["tool_calls"][0]["id"] == "call_r"
    assert deltas[5:7] == [{"content": "\n\nnote one"}, {"content": "\n\nnote two"}]
    assert deltas[7] == {} and parsed[-3][1]["choices"][0]["finish_reason"] == "tool_calls"
    assert parsed[-2][1]["choices"] == [] and parsed[-2][1]["usage"]["total_tokens"] == 7
    assert parsed[-1] == ("data", "[DONE]")
    assert {p["id"] for kind, p in parsed if p != "[DONE]"} == {"chatcmpl-harness-rt-" + "a" * 32}
    # T5: no stage or phase on the wire; O5: never a `reasoning` key.
    assert "waiting" not in json.dumps(parsed) and "authorizing" not in json.dumps(parsed)
    assert all("reasoning" not in d for d in deltas)
    assert rig.closed == [True]


@pytest.mark.asyncio
async def test_usage_chunk_only_on_request_and_first_note_has_no_separator():
    rig = _Rig(tail=lambda: v1_sse.Tail(_completion(""), ("only note",)))
    rig.put(CommittedEvent("id-1"))
    rig.pipeline.set_result("done")

    parsed = _parse([item for _, item in await rig.run()])

    assert _deltas(parsed)[1] == {"content": "only note"}  # nothing was sent before it
    assert all(p == "[DONE]" or p["choices"] for _, p in parsed)  # no usage chunk


@pytest.mark.asyncio
async def test_keepalive_while_idle_then_the_tail():
    rig = _Rig(interval=0.03)
    rig.put(CommittedEvent("id-1"))
    rig.finish_after(0.3)

    parsed = _parse([item for _, item in await rig.run()])

    assert [k for k, _ in parsed].count("comment") >= 2
    assert parsed[-1] == ("data", "[DONE]")


@pytest.mark.asyncio
async def test_keepalive_is_measured_from_the_last_bytes_sent():
    rig = _Rig(interval=0.15)

    async def feed():
        rig.put(CommittedEvent("id-1"))
        for _ in range(8):
            await asyncio.sleep(0.04)
            rig.put(ContentEvent("x"))
        rig.pipeline.set_result("done")

    feeding = asyncio.ensure_future(feed())
    parsed = _parse([item for _, item in await rig.run()])
    await feeding

    assert [k for k, _ in parsed].count("comment") == 0


@pytest.mark.asyncio
async def test_coalescing_never_crosses_kind_and_keeps_order():
    rig = _Rig(coalesce_s=0.05)
    rig.put(CommittedEvent("id-1"), ContentEvent("a"), ContentEvent("b"),
            ReasoningEvent("r"), ContentEvent("c"))
    rig.finish_after(0.3)

    deltas = _deltas(_parse([item for _, item in await rig.run()]))

    assert deltas[1:4] == [{"content": "ab"}, {"reasoning_content": "r"}, {"content": "c"}]


@pytest.mark.asyncio
async def test_coalescing_window_runs_from_the_first_pending_delta():
    rig = _Rig(coalesce_s=0.2)

    async def feed():
        rig.put(CommittedEvent("id-1"), ContentEvent("a"))
        await asyncio.sleep(0.1)
        rig.put(ContentEvent("b"))  # inside the window opened by "a"
        await asyncio.sleep(0.25)  # the window (0.2) has closed
        rig.put(ContentEvent("c"))
        await asyncio.sleep(0.4)
        rig.pipeline.set_result("done")

    feeding = asyncio.ensure_future(feed())
    deltas = _deltas(_parse([item for _, item in await rig.run()]))
    await feeding

    assert deltas[1:3] == [{"content": "ab"}, {"content": "c"}]


@pytest.mark.asyncio
async def test_pending_text_is_flushed_before_the_tail():
    rig = _Rig(coalesce_s=30.0)  # the window never closes by itself
    rig.put(CommittedEvent("id-1"), ContentEvent("a"), ContentEvent("b"))
    rig.finish_after(0.05)

    deltas = _deltas(_parse([item for _, item in await rig.run()]))

    assert deltas == [{"role": "assistant", "content": ""}, {"content": "ab"}, {}]


@pytest.mark.asyncio
async def test_window_zero_sends_every_delta_as_it_comes():
    rig = _Rig(coalesce_s=0)
    rig.put(CommittedEvent("id-1"), *[ContentEvent(c) for c in "abcd"])
    rig.pipeline.set_result("done")

    deltas = _deltas(_parse([item for _, item in await rig.run()]))

    assert [d.get("content") for d in deltas[1:5]] == list("abcd")


@pytest.mark.asyncio
async def test_a_burst_from_a_worker_thread_is_drained_when_the_pipeline_returns():
    loop = asyncio.get_running_loop()
    rig = _Rig(tail=lambda: v1_sse.Tail(_completion(), ()), coalesce_s=0)
    expected = "".join(str(i % 10) for i in range(2000))

    def work():
        loop.call_soon_threadsafe(rig.queue.put_nowait, CommittedEvent("id-1"))
        for i in range(2000):
            loop.call_soon_threadsafe(rig.queue.put_nowait, ContentEvent(str(i % 10)))
        return "done"  # returns at once: the puts are still queued on the loop

    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        rig.pipeline = asyncio.ensure_future(loop.run_in_executor(pool, work))
        rig.gen = v1_sse.realtime_events(
            rig.queue, rig.pipeline, created=1, model="s/m", tail=rig._render,
            include_usage=False, interval=10.0, coalesce_s=0, on_close=rig.closed.append,
        )
        deltas = _deltas(_parse([item for _, item in await rig.run()]))
    finally:
        pool.shutdown(wait=True)

    assert "".join(d.get("content", "") for d in deltas[1:]) == expected


@pytest.mark.asyncio
async def test_an_error_tail_is_sent_as_is_without_done():
    event = 'data: {"error": {"code": "upstream_error"}}\n\n'
    rig = _Rig(tail=lambda: [event])
    rig.put(CommittedEvent("id-1"), ContentEvent("partial"))
    rig.pipeline.set_result("done")

    items = [item for _, item in await rig.run()]

    assert items[-1] == event and v1_sse.DONE not in items
    assert rig.closed == [True]


@pytest.mark.asyncio
async def test_closing_the_stream_reports_it_and_leaves_the_pipeline_running():
    rig = _Rig(interval=0.01)

    assert await asyncio.wait_for(rig.gen.__anext__(), _HARD_TIMEOUT) == v1_sse.KEEPALIVE
    await rig.gen.aclose()

    assert rig.closed == [False]
    assert not rig.pipeline.done() and rig.tail_calls == 0
    rig.pipeline.set_result("done")


@pytest.mark.asyncio
async def test_commit_sink_that_does_not_forward_keeps_an_empty_queue():
    loop = asyncio.get_running_loop()
    sink = _CommitSink(loop, forward=False)

    def produce():
        sink.stage("authorizing")
        sink.phase("waiting")
        sink.content("text")
        sink.reasoning("why")
        sink.committed("chatcmpl-harness-rt-" + "b" * 32)

    await asyncio.to_thread(produce)
    await asyncio.wait_for(sink.started.wait(), _HARD_TIMEOUT)
    await asyncio.sleep(0.01)

    assert sink.called and sink.queue.empty()
    forwarding = _CommitSink(loop, forward=True)
    await asyncio.to_thread(forwarding.content, "x")
    await asyncio.sleep(0.01)
    assert forwarding.queue.qsize() == 1


def test_a_verdict_after_the_commit_keeps_the_t13_warning(caplog):
    verdict = QueryBlockedSuspiciousResponse(reason="Suspicious pattern detected", pattern="p")
    done = concurrent.futures.Future()
    done.set_result(verdict)
    wrapper = _Upstream(loop=None)

    with caplog.at_level(logging.WARNING, logger="app.routers.v1"):
        tail = _realtime_tail(done, upstream=wrapper, identity=_IDENTITY)

    assert isinstance(tail, list) and len(tail) == 1 and v1_sse.DONE not in tail
    assert [r.getMessage() for r in caplog.records if r.name == "app.routers.v1"] == [
        f"v1 verdict after stream commit: user_id={_USER} code=suspicious_pattern"
    ]


def test_buffered_completion_events_carry_reasoning_on_the_role_chunk_only_when_set():
    plain = _parse(v1_sse.completion_events(_completion("hi"), False))
    assert _deltas(plain)[0] == {"role": "assistant", "content": "hi"}
    with_reasoning = _completion("hi")
    with_reasoning.choices[0].message.reasoning_content = "why"
    shown = _deltas(_parse(v1_sse.completion_events(with_reasoning, False)))[0]
    assert shown == {"role": "assistant", "content": "hi", "reasoning_content": "why"}


# =============================================================================
# Direct ASGI: the router with a scripted upstream
# =============================================================================


@pytest.fixture
def rt(temp_db, provider_file, monkeypatch):
    """A file-mode registry with a streaming + reasoning + tools model; grants per test."""
    insert_user(User(user_id=_USER, role="user", token_hash=hash_token(_TOKEN)))

    def configure(grants=(_SUBMIT, _RT, _RV)):
        provider_file(_YAML)
        monkeypatch.setattr(authz, "ROLE_PERMISSIONS", {"user": set(grants)})

    monkeypatch.setattr(settings, "USAGE_LIMITS_ENABLED", True)
    monkeypatch.setattr(settings, "USAGE_REQUESTS_PER_MINUTE", "*=600")
    monkeypatch.setattr(settings, "USAGE_DAILY_TOKEN_BUDGET", "*=1000000")
    monkeypatch.setattr(settings, "PII_REDACTION_ENABLED", False)  # no gate: raw forward
    monkeypatch.setattr(settings, "STREAMING_ENABLED", True)
    monkeypatch.setattr(settings, "V1_TOOLS_ENABLED", True)
    monkeypatch.setattr(settings, "STREAM_COALESCE_MS", 0)
    configure()
    return configure


def _script(events, *, delay=0.0, then=None, stamp=None, hold=None):
    """A `stream_upstream` stub: `events` (each after `delay` s), then `then` raises."""

    def fake(messages, model="gpt-4", api_key=None, params=None, *, tools=None):
        if stamp is not None:
            stamp.append(time.monotonic())
        for index, event in enumerate(events):
            if delay:
                time.sleep(delay)
            if hold is not None and index == hold[0]:
                assert hold[1].wait(_HARD_TIMEOUT), "the test never released the stream"
            yield event
        if then is not None:
            raise then

    return fake


def _no_stream(*a, **k):
    raise AssertionError("stream_upstream must not run when nothing is delivered live")


def _install(monkeypatch, fake):
    monkeypatch.setattr(
        "app.routers.v1.run_conversation",
        functools.partial(run_conversation, stream_upstream=fake),
    )


def _body(prompt=None, **extra):
    prompt = prompt or f"question {uuid4()}"
    return {"model": "s/m", "messages": [{"role": "user", "content": prompt}], **extra}


async def _drive(body, *, disconnect_after_data=None, token=_TOKEN):
    """One request through the app: `[(monotonic time, message)]` per send."""
    raw = json.dumps(body).encode()
    scope = {
        "type": "http", "asgi": {"version": "3.0", "spec_version": "2.3"}, "http_version": "1.1",
        "method": "POST", "scheme": "http", "path": _PATH, "raw_path": _PATH.encode(),
        "root_path": "", "query_string": b"",
        "headers": [
            (b"host", b"test"), (b"authorization", f"Bearer {token}".encode()),
            (b"content-type", b"application/json"), (b"content-length", str(len(raw)).encode()),
        ],
        "client": ("127.0.0.1", 50000), "server": ("test", 80),
    }
    sent, left, state = [], asyncio.Event(), {"body": False}

    async def receive():
        if not state["body"]:
            state["body"] = True
            return {"type": "http.request", "body": raw, "more_body": False}
        await left.wait()
        return {"type": "http.disconnect"}

    async def send(message):
        sent.append((time.monotonic(), message))
        data = sum(1 for _, m in sent if m.get("body", b"").startswith(b"data:"))
        if disconnect_after_data is not None and data >= disconnect_after_data:
            left.set()

    await asyncio.wait_for(app(scope, receive, send), _HARD_TIMEOUT)
    return sent


def _text(sent):
    return b"".join(m.get("body", b"") for _, m in sent).decode()


def _status(sent):
    return next(m["status"] for _, m in sent if m["type"] == "http.response.start")


def _events(sent):
    return _parse([block + "\n\n" for block in _text(sent).split("\n\n") if block])


def _json_body(sent):
    return json.loads(_text(sent))


def _content(parsed):
    return "".join(d.get("content", "") for d in _deltas(parsed))


def _reasoning(parsed):
    return "".join(d.get("reasoning_content", "") for d in _deltas(parsed))


def _rows():
    with get_connection() as conn:
        ids = [r["id"] for r in conn.execute("SELECT id FROM audit_logs ORDER BY id").fetchall()]
    return [get_audit_log(i) for i in ids]


async def _until_rows(n):
    deadline = time.monotonic() + _HARD_TIMEOUT
    while True:
        rows = await asyncio.to_thread(_rows)
        if len(rows) >= n:
            return rows
        assert time.monotonic() < deadline, f"{len(rows)} of {n} rows written"
        await asyncio.sleep(0.05)


_ANSWER = [TextDelta("Hello "), TextDelta("wor"), TextDelta("ld"), Finish("stop"), _USAGE]


@pytest.mark.asyncio
async def test_sequence_ids_and_the_row(rt, monkeypatch):
    _install(monkeypatch, _script(_ANSWER))

    sent = await _drive(_body(stream=True, stream_options={"include_usage": True}))

    assert _status(sent) == 200
    parsed = _events(sent)
    deltas = _deltas(parsed)
    assert deltas[0] == {"role": "assistant", "content": ""}
    assert _content(parsed) == "Hello world"
    assert deltas[-1] == {} and parsed[-3][1]["choices"][0]["finish_reason"] == "stop"
    assert parsed[-2][1]["choices"] == [] and parsed[-2][1]["usage"]["total_tokens"] == 7
    assert parsed[-1] == ("data", "[DONE]")
    ids = {p["id"] for _, p in parsed if p != "[DONE]"}
    assert len(ids) == 1 and _ID.match(next(iter(ids)))
    (row,) = await _until_rows(1)
    assert row.completion_id == next(iter(ids)) and row.streamed_realtime is True
    assert '"harness"' not in _text(sent)  # no extension object on a chunk (D16)


@pytest.mark.asyncio
async def test_usage_chunk_only_with_include_usage(rt, monkeypatch):
    _install(monkeypatch, _script(_ANSWER))

    parsed = _events(await _drive(_body(stream=True)))

    assert all(p == "[DONE]" or p["choices"] for _, p in parsed)


@pytest.mark.asyncio
async def test_the_coalesce_interval_caps_the_chunk_count(rt, monkeypatch):
    text = "abcdefghijklmnopqrstuvwxyz0123456789ABCD"  # 40 one-character deltas
    events = [TextDelta(c) for c in text] + [Finish("stop"), _USAGE]
    _install(monkeypatch, _script(events))

    monkeypatch.setattr(settings, "STREAM_COALESCE_MS", 0)
    each = _events(await _drive(_body(stream=True)))
    monkeypatch.setattr(settings, "STREAM_COALESCE_MS", 500)
    merged = _events(await _drive(_body(stream=True)))

    assert _content(each) == _content(merged) == text
    assert sum(1 for d in _deltas(each) if d.get("content")) == 40
    assert sum(1 for d in _deltas(merged) if d.get("content")) <= 4


@pytest.mark.asyncio
async def test_a_gated_stream_merges_too_and_keeps_the_text(rt, monkeypatch):
    pii_redactor.load()
    monkeypatch.setattr(settings, "PII_REDACTION_ENABLED", True)
    code = pii_policy.get_pii_policy("code")
    monkeypatch.setattr(
        pii_policy, "_policies",
        {**pii_policy._policies, "code": dataclasses.replace(code, output=True)},
    )
    text = "abcdefghijklmnopqrstuvwxyz"
    events = [TextDelta(c) for c in text] + [Finish("stop"), _USAGE]
    _install(monkeypatch, _script(events))

    parsed = _events(await _drive(_body(stream=True)))

    assert _content(parsed) == text
    assert sum(1 for d in _deltas(parsed) if d.get("content")) < len(text)


# --- reasoning_content (D9, O5) --------------------------------------------------

_THINK = [ReasoningDelta("think "), ReasoningDelta("hard"), TextDelta("answer"), Finish("stop"), _USAGE]


@pytest.mark.asyncio
async def test_both_grants_stream_reasoning_content_never_reasoning(rt, monkeypatch):
    _install(monkeypatch, _script(_THINK))

    parsed = _events(await _drive(_body(stream=True)))

    assert _reasoning(parsed) == "think hard" and _content(parsed) == "answer"
    assert all("reasoning" not in d for d in _deltas(parsed))
    (row,) = await _until_rows(1)
    assert row.reasoning_shown is True


@pytest.mark.asyncio
async def test_reasoning_only_adds_it_to_the_body_and_the_role_chunk(rt, monkeypatch):
    rt(grants=(_SUBMIT, _RV))
    _install(monkeypatch, _script(_THINK))

    body = _json_body(await _drive(_body(stream=False)))
    message = body["choices"][0]["message"]
    assert message["content"] == "answer" and message["reasoning_content"] == "think hard"
    assert "reasoning" not in message

    sent = await _drive(_body(stream=True))
    parsed = _events(sent)
    role = _deltas(parsed)[0]
    # Buffered SSE (no real-time grant): one role chunk carries both, nothing live.
    assert role == {"role": "assistant", "content": "answer", "reasoning_content": "think hard"}
    assert all("reasoning" not in d for d in _deltas(parsed))
    assert not _ID.match(parsed[0][1]["id"])  # not a realtime id: the buffered stream
    rows = await _until_rows(2)
    assert [r.streamed_realtime for r in rows] == [False, False]
    # STORY-009 F7: the reply carried reasoning (in the body / the role chunk).
    assert [r.reasoning_shown for r in rows] == [True, True]


@pytest.mark.asyncio
async def test_no_grant_means_no_reasoning_key_in_any_shape(rt, monkeypatch):
    class Answering:
        def __call__(self, messages, model="gpt-4", api_key=None, **kw):
            return OpenRouterResult(response="answer", model_used=model, tokens_used=7,
                                    input_tokens=3, output_tokens=4, finish_reason="stop")

    monkeypatch.setattr("app.routers.v1.call_openrouter", Answering())
    rt(grants=(_SUBMIT,))
    _install(monkeypatch, _no_stream)
    assert "reasoning" not in json.dumps(_json_body(await _drive(_body(stream=False))))
    assert "reasoning" not in _text(await _drive(_body(stream=True)))

    # Real time without the reasoning grant: content live, reasoning dropped.
    rt(grants=(_SUBMIT, _RT))
    _install(monkeypatch, _script(_THINK))
    realtime = _text(await _drive(_body(stream=True)))
    assert "reasoning" not in realtime and "think" not in realtime and "answer" in realtime


@pytest.mark.asyncio
async def test_stream_false_with_real_time_is_todays_buffered_body(rt, monkeypatch):
    rt(grants=(_SUBMIT, _RT))
    monkeypatch.setattr(
        "app.routers.v1.call_openrouter",
        lambda messages, model="m", api_key=None, **kw: OpenRouterResult(
            response="answer", model_used=model, tokens_used=7, input_tokens=3,
            output_tokens=4, finish_reason="stop"),
    )
    _install(monkeypatch, _no_stream)  # D-A: no real time, no reasoning grant: not streamed

    body = _json_body(await _drive(_body(stream=False)))

    assert body["choices"][0]["message"] == {"role": "assistant", "content": "answer"}
    assert body["id"].startswith("chatcmpl-harness-") and not _ID.match(body["id"])


# --- T1 / T5: tool calls ----------------------------------------------------------

_DROP_ARGS = json.dumps({"command": 'sqlite3 app.db "DROP TABLE users"'})
_PIECES = [_DROP_ARGS[i:i + 5] for i in range(0, len(_DROP_ARGS), 5)]
_TOOLS = [
    {"type": "function", "function": {"name": name, "parameters": {"type": "object"}}}
    for name in ("shell", "read")
]


def _drop_events():
    events = [TextDelta("before ")]
    events.append(ToolCallDelta(0, id="call_1", name="shell", arguments=_PIECES[0]))
    events += [ToolCallDelta(0, arguments=piece) for piece in _PIECES[1:]]
    events += [
        ToolCallDelta(1, id="call_r", name="read", arguments='{"path":"src/a.py"}'),
        TextDelta("after"), Finish("tool_calls"), _USAGE,
    ]
    return events


@pytest.mark.asyncio
async def test_a_denied_call_never_leaks_its_fragments_and_the_note_closes_the_content(
    rt, monkeypatch
):
    assert len(_PIECES) >= 9
    _install(monkeypatch, _script(_drop_events()))

    # The same script, buffered (`stream: false`): the body step 7c and the release produce.
    buffered = _json_body(await _drive(_body(stream=False, tools=_TOOLS)))
    expected = buffered["choices"][0]["message"]["content"]
    parsed = _events(await _drive(_body(stream=True, tools=_TOOLS)))

    deltas = _deltas(parsed)
    leak = ("sqlite3", "DROP", "TABLE", "users", "command")
    note_at = next(i for i, d in enumerate(deltas) if d.get("content", "").startswith("\n\n"))
    for chunk in deltas[:note_at]:
        assert not any(word in json.dumps(chunk) for word in leak), chunk
    # The note is a content delta before the finish chunk; the concatenation is
    # `content_with_notes(redacted, notes)` (the buffered body's content).
    assert note_at < len(deltas) - 1 and deltas[-1] == {}
    assert _content(parsed) == expected
    notes = [d["content"][2:] for d in deltas[note_at:] if d.get("content")]
    assert expected == tool_release.content_with_notes("before after", notes)
    released = [d["tool_calls"][0] for d in deltas if d.get("tool_calls")]
    assert [c["id"] for c in released] == ["call_r"]
    finish = [p for _, p in parsed if p != "[DONE]" and p["choices"][0]["finish_reason"]]
    assert finish[0]["choices"][0]["finish_reason"] == buffered["choices"][0]["finish_reason"]
    for word in ("waiting", "thinking", "writing", "preparing_action"):
        assert word not in json.dumps(parsed)  # T5: no stage or phase word


# --- faults, disconnect (D15, T13) --------------------------------------------------


@pytest.mark.asyncio
async def test_an_upstream_fault_after_commit_is_one_error_event_and_no_done(rt, monkeypatch):
    _install(monkeypatch, _script(
        [TextDelta("partial answer")], then=UpstreamError("provider down", retryable=False)
    ))

    parsed = _events(await _drive(_body(stream=True)))

    errors = [p for _, p in parsed if p != "[DONE]" and "error" in p]
    assert len(errors) == 1 and errors[0]["error"]["code"] == "upstream_error"
    assert parsed[-1][1] == errors[0] and ("data", "[DONE]") not in parsed
    (row,) = await _until_rows(1)
    assert row.success is False


@pytest.mark.asyncio
async def test_a_gate_failure_is_redaction_failed(rt, monkeypatch):
    pii_redactor.load()
    monkeypatch.setattr(settings, "PII_REDACTION_ENABLED", True)
    code = pii_policy.get_pii_policy("code")
    monkeypatch.setattr(
        pii_policy, "_policies",
        {**pii_policy._policies, "code": dataclasses.replace(code, output=True)},
    )
    real = query_pipeline._redact

    def boom(text, policy):
        if "BOOM" in text:
            raise PiiRedactorError("gate failed")
        return real(text, policy)

    monkeypatch.setattr(query_pipeline, "_redact", boom)
    _install(monkeypatch, _script([TextDelta("BOOM "), TextDelta("text"), Finish("stop"), _USAGE]))

    parsed = _events(await _drive(_body(stream=True)))

    errors = [p for _, p in parsed if p != "[DONE]" and "error" in p]
    assert [e["error"]["code"] for e in errors] == ["redaction_failed"]
    assert ("data", "[DONE]") not in parsed


@pytest.mark.asyncio
async def test_a_disconnect_mid_stream_still_writes_the_row_and_charges(rt, monkeypatch, caplog):
    gate = threading.Event()
    _install(monkeypatch, _script(
        [TextDelta("first part"), TextDelta(" rest"), Finish("stop"), _USAGE], hold=(1, gate)
    ))

    with caplog.at_level(logging.INFO, logger="app.routers.v1"):
        # Leave after the role chunk and the first content chunk.
        sent = await _drive(_body(stream=True), disconnect_after_data=2)
        assert "first part" in _text(sent) and "[DONE]" not in _text(sent)
        gate.set()
        (row,) = await _until_rows(1)
        deadline = time.monotonic() + _HARD_TIMEOUT
        while time.monotonic() < deadline:
            gc.collect()  # a closed-but-not-awaited generator runs its `finally` here
            if any("disconnected" in r.getMessage() for r in caplog.records):
                break
            await asyncio.sleep(0.05)

    assert row.success is True and _ID.match(row.completion_id) and row.streamed_realtime is True
    with get_connection() as conn:
        charged = conn.execute(
            "SELECT output_tokens FROM usage_daily WHERE user_id = ?", (_USER,)
        ).fetchone()
    assert charged["output_tokens"] == 4
    lines = [r.getMessage() for r in caplog.records if "disconnected" in r.getMessage()]
    assert lines == [
        f"v1 realtime stream disconnected: user_id={_USER} completion_id={row.completion_id}"
    ]
    assert not any("first part" in r.getMessage() for r in caplog.records)  # T9


# --- off means today (D22) ----------------------------------------------------------


class _Buffered:
    def __init__(self):
        self.calls = []

    def __call__(self, messages, model="gpt-4", api_key=None, **kwargs):
        self.calls.append(kwargs)
        return OpenRouterResult(
            response="answer", model_used=model, tokens_used=7, input_tokens=3,
            output_tokens=4, finish_reason="stop",
        )


def _shape(sent, streamed):
    """The response with what varies per request (ids, times) removed."""
    if not streamed:
        body = _json_body(sent)
        return {"status": _status(sent), "choices": body["choices"], "usage": body["usage"],
                "keys": sorted(body), "harness": sorted(body["harness"])}
    parsed = _events(sent)
    return {"status": _status(sent), "events": [
        p["choices"] if p != "[DONE]" else p for _, p in parsed if p == "[DONE]" or "choices" in p
    ]}


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_off_means_today_switch_off_no_grant_and_legacy_mode(rt, monkeypatch, stream):
    stub = _Buffered()
    monkeypatch.setattr("app.routers.v1.call_openrouter", stub)
    _install(monkeypatch, _no_stream)

    monkeypatch.setattr(settings, "STREAMING_ENABLED", False)
    switch_off = _shape(await _drive(_body(stream=stream)), stream)
    monkeypatch.setattr(settings, "STREAMING_ENABLED", True)
    rt(grants=(_SUBMIT,))
    no_grant = _shape(await _drive(_body(stream=stream)), stream)

    assert len(stub.calls) == 2 and all("stream" not in call for call in stub.calls)
    assert switch_off == no_grant
    assert switch_off["status"] == 200
    # Legacy mode (no PROVIDERS_FILE) never streams (OD1); it answers the same way.
    from app.services import provider_registry
    provider_registry.reset()
    monkeypatch.setattr(settings, "PROVIDERS_FILE", "")
    legacy_body = _body(stream=stream)
    legacy_body["model"] = "openai/gpt-4o"
    legacy = _shape(await _drive(legacy_body), stream)
    assert legacy == switch_off and len(stub.calls) == 3


def test_visibility_is_none_when_the_switch_is_off_or_the_model_is_forbidden(rt, monkeypatch):
    assert _visibility(_IDENTITY, "s/m", True).realtime is True
    assert _visibility(_IDENTITY, "s/m", False).realtime is False
    assert _visibility(_IDENTITY, "not/catalogued", True) is None  # the pipeline's own denial
    monkeypatch.setattr(settings, "STREAMING_ENABLED", False)
    assert _visibility(_IDENTITY, "s/m", True) is None


# --- AC5: latency ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_first_content_latency_p95_and_the_sdk_accumulator(rt, monkeypatch):
    openai_streaming = pytest.importorskip("openai.lib.streaming.chat")
    from openai import NOT_GIVEN
    from openai.types.chat import ChatCompletionChunk as SdkChunk

    delay = 0.03
    monkeypatch.setattr(settings, "STREAM_COALESCE_MS", 50)  # the shipped default
    text = "def total(items):\n    return sum(items)\n"
    pieces = [text[i:i + 8] for i in range(0, len(text), 8)]
    waits = []
    for _ in range(20):
        stamp = []
        _install(monkeypatch, _script(
            [TextDelta(p) for p in pieces] + [Finish("stop"), _USAGE], delay=delay, stamp=stamp
        ))
        sent = await _drive(_body(stream=True))
        arrived = next(
            at for at, m in sent
            if m.get("body", b"").startswith(b"data:") and b'"content":"' in m["body"]
            and b'"content":""' not in m["body"]
        )
        waits.append(arrived - stamp[0])
    waits.sort()
    p95 = waits[int(0.95 * len(waits)) - 1]  # nearest rank over 20 runs
    assert p95 <= delay + 0.1, waits

    state = openai_streaming.ChatCompletionStreamState(
        input_tools=NOT_GIVEN, response_format=NOT_GIVEN
    )
    for _, payload in _events(sent):
        if payload != "[DONE]":
            state.handle_chunk(SdkChunk.model_validate(payload))
    final = state.get_final_completion()
    assert final.choices[0].message.content == text
    assert final.choices[0].finish_reason == "stop"
