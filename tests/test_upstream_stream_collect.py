"""PRD-020 STORY-013: adapter `stream()`, the normalized events and the pure `collect()`.

    AC1  `stream()` sends `stream: true` and `stream_options`; `complete()` sends no `stream` key
    AC3  `collect` and its helpers are pure (AST); they reuse `complete()`'s reply rules
    AC4  `collect(stream(r)) == complete(r)` over every e2e script and inline edge cases
    AC5  malformed streams are non-retryable errors naming the field, never a value

The stub's SSE side is covered in `tests/test_stub_openrouter.py` (AC2).
"""

import ast
import dataclasses
import io
import json
import os
import threading
from pathlib import Path

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import httpx
import pytest

from app.models.messages import Message
from app.services import provider_registry
from app.services.upstream import (
    Finish,
    OpenAICompatibleAdapter,
    TextDelta,
    ToolCallDelta,
    ToolParams,
    UpstreamError,
    UpstreamRequest,
    UsageReport,
    collect,
)
from app.services.upstream import openai_compatible
from app.services.upstream.sse import parse_events
from scripts.stub_openrouter import _REPLY_KEYS, make_server, parse_script
from tests.e2e import _cline, _opencode

_REPO = Path(__file__).resolve().parent.parent
_PKG = _REPO / "app" / "services" / "upstream"
_KEY = "sk-test-key-STORY013"
_CANARY = "CANARY-value-9f3"
_TOOLS = ToolParams(tools=[{"type": "function", "function": {"name": "f", "parameters": {}}}])


def _provider(base_url="http://127.0.0.1:1/v1", **changes):
    base = provider_registry.current().providers[0]
    return dataclasses.replace(base, base_url=base_url, **changes)


def _request(text="hello", tools=None):
    return UpstreamRequest([Message("user", text)], "up-model", tools=tools)


# --------------------------------------------------------------------------
# helpers: a stub on a free port, a MockTransport client
# --------------------------------------------------------------------------


@pytest.fixture
def start_stub():
    started = []

    def start(script):
        log = io.StringIO()
        server = make_server(parse_script(script), log=log)
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        thread.start()
        started.append((server, thread))
        return server.server_address[1], log

    yield start
    for server, thread in started:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


class _Body(httpx.SyncByteStream):
    """A response body that records its close, optionally failing after its chunks."""

    def __init__(self, chunks, *, error=None):
        self._chunks, self._error, self.closed = chunks, error, False

    def __iter__(self):
        yield from self._chunks
        if self._error is not None:
            raise self._error

    def close(self):
        self.closed = True


def _sse(*payloads, done=True):
    lines = [f"data: {p if isinstance(p, str) else json.dumps(p)}\n\n" for p in payloads]
    if done:
        lines.append("data: [DONE]\n\n")
    return "".join(lines).encode("utf-8")


def _mock_client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def _stream_events(body, *, status=200, headers=None, error=None, client=None):
    """Drain `stream()` against a canned response body; returns the events list."""
    stream = _Body([body] if isinstance(body, bytes) else body, error=error)

    def handler(request):
        return httpx.Response(status, stream=stream, headers=headers)

    adapter = OpenAICompatibleAdapter(_provider(), client or _mock_client(handler))
    return list(adapter.stream(_request(), _KEY))


def _delta(**delta):
    return {"choices": [{"index": 0, "delta": delta, "finish_reason": None}]}


# PRD-021 F2: a stream must now carry a finish_reason chunk or stream() raises; the
# tests below that drain bodies without one append this chunk.
_FINISH_STOP = {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}


# --------------------------------------------------------------------------
# AC4: collect(stream(r)) == complete(r)
# --------------------------------------------------------------------------

_INLINE = [
    {"tool_calls": [{"name": "read", "arguments": '{"path": "a.py"}'}]},
    {"content": "Looking.", "tool_calls": [{"name": "read", "arguments": '{"path": "a.py"}'}]},
    {"tool_calls": [{"name": "a", "arguments": "{}"}, {"name": "b", "arguments": '{"x": 1}', "id": "call_explicit"}]},
    {"tool_calls": [{"name": "noargs", "arguments": ""}]},
    {"tool_calls": [{"name": "broken", "arguments": "{not json"}]},
    {"content": "no usage", "usage": None},
    {"content": "partial", "usage": {"prompt_tokens": 5}},
    {"content": "split", "usage": {"prompt_tokens": 5, "completion_tokens": 7}},
    {"content": "", "finish_reason": "stop"},
    {"content": "x", "finish_reason": None},
    {"content": "a longer answer that is split in two", "finish_reason": "length"},
    {"fail_status": 503},
    {"fail_status": 429},
    {"fail_status": 400},
    {"redirect_status": 302, "location": "http://127.0.0.1:9/never"},
]


def _reply_only(raw: dict) -> dict:
    return {k: v for k, v in raw.items() if k in _REPLY_KEYS and k != "delay_seconds"}


def _all_replies():
    replies = [{"content": "default answer"}, *_INLINE]
    scripts = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((_REPO / "tests/e2e/scripts").glob("*.json"))]
    scripts.append(json.loads(_cline.render_script("C:/e2e/repo")))
    scripts.append(json.loads(_opencode.render_script("C:/e2e/repo")))
    for script in scripts:
        raws = [*script.get("rules", [])]
        if "default" in script:
            raws.append(script["default"])
        replies.extend(_reply_only(raw) for raw in raws)
    unique, seen = [], set()
    for reply in replies:
        key = json.dumps(reply, sort_keys=True)
        if key not in seen:
            seen.add(key)
            unique.append(reply)
    return unique


def _outcome(fn, port):
    """('ok', result) or ('error', type, text, status, retryable); the stub's port is masked."""
    try:
        return ("ok", fn())
    except UpstreamError as exc:
        return ("error", type(exc), str(exc).replace(f":{port}", ":PORT"), exc.upstream_status, exc.retryable)


@pytest.mark.parametrize("usage_missing", ["error", "estimate"])
@pytest.mark.parametrize("with_tools", [False, True])
def test_collect_of_stream_equals_complete(start_stub, usage_missing, with_tools):
    replies = _all_replies()
    assert len(replies) >= 20  # the property must actually cover the scripts
    script = {"rules": [{"contains": f"case-{i}", **reply} for i, reply in enumerate(replies)]}
    # Two stubs fed the same requests in the same order: generated call ids stay in step.
    port_a, _ = start_stub(script)
    port_b, _ = start_stub(script)
    provider_a = _provider(f"http://127.0.0.1:{port_a}/v1", usage_missing=usage_missing)
    provider_b = _provider(f"http://127.0.0.1:{port_b}/v1", usage_missing=usage_missing)
    tools = _TOOLS if with_tools else None
    mismatches = []
    # One shared client: building an httpx.Client per call (its TLS context) dominates the run time.
    client = httpx.Client(timeout=10, follow_redirects=False)
    for i, reply in enumerate(replies):
        request = _request(f"case-{i}", tools)
        whole = _outcome(lambda: OpenAICompatibleAdapter(provider_a, client).complete(request, _KEY), port_a)
        streamed = _outcome(
            lambda: collect(OpenAICompatibleAdapter(provider_b, client).stream(request, _KEY), provider=provider_b, request=request),
            port_b,
        )
        if whole != streamed:
            mismatches.append((i, reply, whole, streamed))
    client.close()
    assert not mismatches, mismatches[:3]


# --------------------------------------------------------------------------
# collect(): assembly rules on hand-made events
# --------------------------------------------------------------------------


def test_collect_assembles_text_calls_finish_and_usage():
    request = _request(tools=_TOOLS)
    events = [
        TextDelta("Hel"),
        TextDelta("lo"),
        ToolCallDelta(1, id="b", name="two", arguments='{"y'),
        ToolCallDelta(0, id="a", name="one", arguments="{"),
        ToolCallDelta(0, arguments="}"),
        ToolCallDelta(1, arguments='": 2}'),
        Finish("tool_calls"),
        UsageReport(prompt_tokens=3, completion_tokens=4, total_tokens=7),
    ]
    result = collect(events, provider=_provider(), request=request)
    assert result.response == "Hello"
    assert [(c.id, c.name, c.arguments) for c in result.tool_calls] == [
        ("a", "one", "{}"),  # ascending index; arguments concatenated, never parsed (D13)
        ("b", "two", '{"y": 2}'),
    ]
    assert (result.finish_reason, result.tokens_used, result.usage_estimated) == ("tool_calls", 7, False)
    assert result.model_used == "up-model"


def test_collect_without_text_is_null_content_and_an_empty_delta_counts():
    provider = _provider(usage_missing="estimate")
    with pytest.raises(UpstreamError, match=r"returned no text content \(finish_reason=stop\)"):
        collect([Finish("stop")], provider=provider, request=_request())
    assert collect([TextDelta("")], provider=provider, request=_request()).response == ""


def test_collect_calls_are_ignored_without_tools_but_keep_the_not_supported_note():
    events = [ToolCallDelta(0, id="a", name="n", arguments="{}"), Finish("tool_calls")]
    with pytest.raises(UpstreamError, match=r"tool calls are not supported \(PRD-017\)"):
        collect(events, provider=_provider(usage_missing="estimate"), request=_request())


def test_collect_duplicate_call_id_fails_like_complete():
    # The stub refuses a duplicate scripted id, so this case is not in the property.
    events = [
        ToolCallDelta(0, id="same", name="a", arguments="{}"),
        ToolCallDelta(1, id="same", name="b", arguments="{}"),
    ]
    with pytest.raises(UpstreamError, match=r"tool_calls\[1\]\.id repeats an earlier id"):
        collect(events, provider=_provider(usage_missing="estimate"), request=_request(tools=_TOOLS))


def test_collect_call_without_a_name_names_the_field():
    events = [ToolCallDelta(0, id="a", arguments="{}")]
    with pytest.raises(UpstreamError, match=r"choices\[0\]\.message\.tool_calls\[0\]\.function\.name"):
        collect(events, provider=_provider(usage_missing="estimate"), request=_request(tools=_TOOLS))


def test_collect_usage_rules_follow_d8():
    request = _request()
    estimate = _provider(usage_missing="estimate")
    result = collect([TextDelta("abcd")], provider=estimate, request=request)
    assert result.usage_estimated and result.input_tokens is None
    with pytest.raises(UpstreamError, match=r"unexpected response shape: 'usage'"):
        collect([TextDelta("x")], provider=_provider(usage_missing="error"), request=request)
    # The last usage chunk wins.
    last = collect(
        [TextDelta("x"), UsageReport(total_tokens=1), UsageReport(total_tokens=9)],
        provider=estimate,
        request=request,
    )
    assert last.tokens_used == 9


def test_collect_rejects_an_unknown_event():
    with pytest.raises(TypeError, match="object"):
        collect([object()], provider=_provider(), request=_request())


# --------------------------------------------------------------------------
# AC5: malformed streams (T7: the field, never the value)
# --------------------------------------------------------------------------


def _error_of(body, **kwargs):
    with pytest.raises(UpstreamError) as info:
        _stream_events(body, **kwargs)
    return info.value


@pytest.mark.parametrize(
    "body,field",
    [
        (_sse(f"{{not json {_CANARY}"), "stream data is not JSON"),
        (_sse(f'["{_CANARY}"]'), "stream data is not an object"),
        (_sse(_delta(content="x"), done=False), r"stream ended without \[DONE\]"),
        (_sse({"choices": f"{_CANARY}"}), "choices is not a list"),
        (_sse({"choices": [_CANARY]}), r"choices\[0\] is not an object"),
        (_sse({"choices": [{"delta": [_CANARY]}]}), r"choices\[0\]\.delta is not an object"),
        (
            _sse(_delta(tool_calls=[{"index": 4, "function": {"arguments": _CANARY}}])),
            r"delta\.tool_calls\[0\]\.index has no earlier fragment carrying an id",
        ),
        (
            _sse(_delta(tool_calls=[{"index": "0", "id": "a", "function": {"name": _CANARY}}])),
            r"delta\.tool_calls\[0\]\.index must be an integer",
        ),
        (
            _sse(_delta(tool_calls=[{"index": True, "id": "a"}])),
            r"delta\.tool_calls\[0\]\.index must be an integer",
        ),
        (
            _sse(_delta(tool_calls=[{"index": 0, "id": "", "function": {"name": _CANARY}}])),
            r"delta\.tool_calls\[0\]\.index has no earlier fragment carrying an id",
        ),
        (
            _sse(_delta(tool_calls=[{"index": 0, "id": "a", "function": {"arguments": {"k": _CANARY}}}])),
            r"delta\.tool_calls\[0\]\.function\.arguments must be a string",
        ),
        (_sse(_delta(tool_calls=_CANARY)), r"delta\.tool_calls is not a list"),
    ],
)
def test_malformed_stream_names_the_field_and_is_not_retryable(body, field):
    exc = _error_of(body)
    assert exc.retryable is False and exc.upstream_status is None
    assert str(exc).startswith("OpenRouter returned an unexpected response shape: ")
    assert _CANARY not in str(exc)
    import re

    assert re.search(field, str(exc)), str(exc)


@pytest.mark.parametrize("status,retryable", [(400, False), (404, False), (429, True), (500, True), (503, True)])
def test_http_errors_are_classified_like_complete(status, retryable):
    exc = _error_of(b'{"error": "' + _CANARY.encode() + b'"}', status=status)
    assert (exc.upstream_status, exc.retryable) == (status, retryable)
    assert _CANARY not in str(exc)  # the error body is never read


@pytest.mark.parametrize("status", [301, 302, 307])
def test_redirect_is_an_error_and_not_followed(status):
    exc = _error_of(b"", status=status, headers={"Location": f"http://elsewhere.invalid/{_CANARY}"})
    assert (exc.upstream_status, exc.retryable) == (status, False)
    assert "redirects are not followed" in str(exc) and _CANARY not in str(exc)


def test_mid_stream_transport_error_is_retryable():
    exc = _error_of([_sse(_delta(content="par"), done=False)], error=httpx.ReadError("connection lost"))
    assert exc.retryable is True and exc.upstream_status is None
    assert "OpenRouter request failed" in str(exc)


def test_blank_lines_comments_and_unknown_fields_are_ignored():
    body = (
        b": keep-alive\n\n"
        b"event: message\n"
        b"data:" + json.dumps(_delta(content="hi")).encode() + b"\n\n"
        b"\n"
        # PRD-021 F2: a finish chunk is now required, so the body carries one.
        b"data:" + json.dumps(_FINISH_STOP).encode() + b"\n\n"
        b"data: [DONE]\n\n"
    )
    assert _stream_events(body) == [TextDelta("hi"), Finish("stop")]


def test_chunk_with_empty_choices_and_usage_yields_a_usage_report():
    chunk = {"choices": [], "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3}}
    # PRD-021 F2: the finish chunk is now required; expected events include Finish.
    assert _stream_events(_sse(_FINISH_STOP, chunk)) == [Finish("stop"), UsageReport(1, 2, 3)]


def test_parse_events_is_lazy():
    def lines():
        yield "data: " + json.dumps(_delta(content="a"))
        raise AssertionError("read past what was consumed")

    events = parse_events(lines(), "X")
    assert next(events) == TextDelta("a")


# --------------------------------------------------------------------------
# AC1: payloads
# --------------------------------------------------------------------------


def _capture():
    seen = {}

    def handler(request):
        seen["json"] = json.loads(request.content)
        seen["headers"] = dict(request.headers)
        if seen["json"].get("stream"):
            # PRD-021 F2: a finish chunk is now required on every stream.
            return httpx.Response(
                200,
                content=_sse(_delta(content="ok"), _FINISH_STOP, {"choices": [], "usage": {"total_tokens": 2}}),
            )
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}], "usage": {"total_tokens": 2}})

    return seen, handler


def test_payload_keys():
    seen, handler = _capture()
    adapter = OpenAICompatibleAdapter(_provider(), _mock_client(handler))
    adapter.complete(_request(), _KEY)
    assert "stream" not in seen["json"] and "stream_options" not in seen["json"]
    assert seen["headers"].get("accept") != "text/event-stream"
    whole_payload = seen["json"]

    events = list(adapter.stream(_request(), _KEY))
    assert seen["json"]["stream"] is True
    assert seen["json"]["stream_options"] == {"include_usage": True}
    assert seen["headers"]["accept"] == "text/event-stream"
    assert seen["headers"]["authorization"] == f"Bearer {_KEY}"
    # Everything but the two stream keys is the payload complete() sends.
    assert {k: v for k, v in seen["json"].items() if k not in ("stream", "stream_options")} == whole_payload
    # PRD-021 F2: Finish("stop") now precedes the usage report.
    assert events == [TextDelta("ok"), Finish("stop"), UsageReport(total_tokens=2)]


def test_stream_is_lazy_and_sends_nothing_until_first_next():
    seen, handler = _capture()
    adapter = OpenAICompatibleAdapter(_provider(), _mock_client(handler))
    gen = adapter.stream(_request(), _KEY)
    assert seen == {}
    next(gen)
    assert seen["json"]["stream"] is True
    gen.close()


# --------------------------------------------------------------------------
# AC3: purity (AST)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("module", ["collect.py", "reply.py", "sse.py"])
def test_pure_modules_import_no_http_client_settings_or_registry_at_runtime(module):
    tree = ast.parse((_PKG / module).read_text(encoding="utf-8"))
    runtime_imports = []

    def visit(nodes):
        for node in nodes:
            if isinstance(node, ast.If) and "TYPE_CHECKING" in ast.dump(node.test):
                continue  # annotation-only imports do not run
            if isinstance(node, ast.Import):
                runtime_imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                runtime_imports.append(node.module or "")
            for field in ("body", "orelse", "finalbody"):
                visit(getattr(node, field, []) or [])

    visit(tree.body)
    for name in runtime_imports:
        assert not name.startswith(("httpx", "requests", "app.config", "app.services.provider_registry")), (
            module,
            name,
        )
        assert name != "app.services.upstream", (module, name)  # the package pulls httpx and the registry


# --------------------------------------------------------------------------
# closing: the response always, the client only when the adapter owns it
# --------------------------------------------------------------------------


def _tracked(monkeypatch, body):
    state = {"clients_closed": 0, "stream": _Body([body] if isinstance(body, bytes) else body)}

    def handler(request):
        return httpx.Response(200, stream=state["stream"])

    class Tracking(httpx.Client):
        def __init__(self, **kwargs):
            super().__init__(transport=httpx.MockTransport(handler), **kwargs)

        def close(self):
            state["clients_closed"] += 1
            super().close()

    return state, handler, Tracking


def test_owned_client_and_response_are_closed_after_a_full_read(monkeypatch):
    state, _, tracking = _tracked(monkeypatch, _sse(_delta(content="a"), _FINISH_STOP))  # PRD-021 F2: finish chunk required
    monkeypatch.setattr(openai_compatible.httpx, "Client", tracking)
    assert list(OpenAICompatibleAdapter(_provider()).stream(_request(), _KEY)) == [TextDelta("a"), Finish("stop")]
    assert state["stream"].closed and state["clients_closed"] == 1


def test_owned_client_and_response_are_closed_on_early_close(monkeypatch):
    state, _, tracking = _tracked(monkeypatch, _sse(_delta(content="a"), _delta(content="b")))
    monkeypatch.setattr(openai_compatible.httpx, "Client", tracking)
    gen = OpenAICompatibleAdapter(_provider()).stream(_request(), _KEY)
    assert next(gen) == TextDelta("a")
    gen.close()
    assert state["stream"].closed and state["clients_closed"] == 1


def test_owned_client_and_response_are_closed_on_error(monkeypatch):
    state, _, tracking = _tracked(monkeypatch, _sse("{bad"))
    monkeypatch.setattr(openai_compatible.httpx, "Client", tracking)
    with pytest.raises(UpstreamError):
        list(OpenAICompatibleAdapter(_provider()).stream(_request(), _KEY))
    assert state["stream"].closed and state["clients_closed"] == 1


def test_injected_client_is_not_closed(monkeypatch):
    state, handler, tracking = _tracked(monkeypatch, _sse(_delta(content="a"), _FINISH_STOP))  # PRD-021 F2: finish chunk required
    client = tracking()
    adapter = OpenAICompatibleAdapter(_provider(), client)
    assert list(adapter.stream(_request(), _KEY)) == [TextDelta("a"), Finish("stop")]
    assert state["stream"].closed and state["clients_closed"] == 0
    client.close()
