"""PRD-022 STORY-007: `AnthropicAdapter.stream()` against a fake SDK (no network).

The fake `messages.create(stream=True)` returns a scripted list of raw SDK events,
so event mapping, error mapping and the client lifecycle are exercised without a
socket. The real-SDK/stub property test is `test_anthropic_stream_stub.py`.
"""

import types

import anthropic
import httpx
import pytest

from app.models.messages import Message, ToolCallSpec
from app.services import provider_registry as registry
from app.services.upstream import anthropic as adapter_mod
from app.services.upstream.anthropic import AnthropicAdapter, _in_stream_error, build_request
from app.services.upstream.collect import collect
from app.services.upstream.params import ToolParams
from app.services.upstream.types import (
    Finish,
    ReasoningDelta,
    TextDelta,
    ToolCallDelta,
    UpstreamError,
    UpstreamRequest,
    UsageReport,
)

_KEY = "sk-ant-TESTKEY-123"
_SECRET = "SECRET-PROMPT-TEXT"
NS = types.SimpleNamespace


def _provider():
    return registry.Provider(
        name="ant", label="Anthropic", type="anthropic", base_url="https://api.anthropic.com",
        key_env="K", insecure_http=False, trust="external", pii="redact", byok=False,
        passthrough=False, passthrough_capabilities=registry.Capabilities(),
        usage_missing="estimate", estimate_chars_per_token=4.0, timeout_seconds=12.5,
        roles=None, models=(),
    )


def _model(**caps):
    return registry.CatalogModel(
        id="claude-x", upstream="claude-up", roles=None,
        capabilities=registry.Capabilities(tools=True, **caps),
        provider_name="ant", default_max_tokens=1024, prompt_cache="off",
    )


def _req(messages=None, *, tools=None, **caps):
    return UpstreamRequest(
        messages if messages is not None else [Message("user", "hi")],
        "claude-up", None, tools, _model(**caps),
    )


# --- raw SDK events -----------------------------------------------------------------


def _start(input_tokens=5, cache_write=None, cache_read=None, output=1, usage=True):
    message = NS(usage=NS(
        input_tokens=input_tokens, output_tokens=output,
        cache_creation_input_tokens=cache_write, cache_read_input_tokens=cache_read,
    ) if usage else None)
    return NS(type="message_start", message=message)


def _block(index, kind, **fields):
    return NS(type="content_block_start", index=index, content_block=NS(type=kind, **fields))


def _delta(index, kind, **fields):
    return NS(type="content_block_delta", index=index, delta=NS(type=kind, **fields))


def _stop(index):
    return NS(type="content_block_stop", index=index)


def _text_block(index, *pieces):
    return [_block(index, "text", text=""), *(_delta(index, "text_delta", text=p) for p in pieces), _stop(index)]


def _tool_block(index, call_id, name, *fragments):
    return [
        _block(index, "tool_use", id=call_id, name=name, input={}),
        *(_delta(index, "input_json_delta", partial_json=f) for f in fragments),
        _stop(index),
    ]


def _end(stop_reason="end_turn", output=7, usage=True):
    return [
        NS(type="message_delta", delta=NS(stop_reason=stop_reason),
           usage=NS(input_tokens=None, output_tokens=output) if usage else None),
        NS(type="message_stop"),
    ]


class _Stream:
    """An SDK `Stream`: iterable, closable; optionally raises `error` after the events."""

    def __init__(self, events, error=None):
        self.events, self.error, self.closed = list(events), error, False

    def __iter__(self):
        yield from self.events
        if self.error is not None:
            raise self.error

    def close(self):
        self.closed = True


class _FakeClient:
    def __init__(self, events=(), error=None, create_error=None):
        self.bodies, self.closed, self.stream = [], False, None
        outer = self

        class _Messages:
            def create(self, **body):
                outer.bodies.append(body)
                if create_error is not None:
                    raise create_error
                outer.stream = _Stream(events, error)
                return outer.stream

        self.messages = _Messages()

    def close(self):
        self.closed = True


def _run(events, *, reasoning=False, request=None, error=None, client=None):
    client = client or _FakeClient(events, error)
    adapter = AnthropicAdapter(_provider(), sdk_client=client)
    return list(adapter.stream(request or _req(), _KEY, reasoning=reasoning))


def _error_of(events, **kwargs):
    seen = []
    with pytest.raises(UpstreamError) as caught:
        for event in _run_iter(events, **kwargs):
            seen.append(event)
    return caught.value, seen


def _run_iter(events, *, reasoning=False, request=None, error=None):
    return AnthropicAdapter(_provider(), sdk_client=_FakeClient(events, error)).stream(
        request or _req(), _KEY, reasoning=reasoning
    )


def _request():
    return httpx.Request("POST", "https://api.anthropic.com/v1/messages")


# --- AC1: mapping ---------------------------------------------------------------------


def test_text_deltas_come_in_order_then_usage_and_finish():
    events = [_start(), *_text_block(0, "hel", "", "lo"), *_end()]
    assert _run(events) == [
        TextDelta("hel"), TextDelta("lo"), UsageReport(5, 7, 12, 0, 0), Finish("stop"),
    ]


def test_tool_input_is_buffered_and_emitted_once_canonical_at_block_stop():
    fragments = ['{"city": "Zo', 'eürich", "n"', ': [1, 2]}']
    events = [_start(), *_tool_block(0, "toolu_1", "lookup", *fragments), *_end("tool_use")]
    iterator = _run_iter(events)
    emitted = next(iterator)
    # one ToolCallDelta, compact, ensure_ascii=False, and nothing earlier than the block stop
    assert emitted == ToolCallDelta(0, "toolu_1", "lookup", '{"city":"Zoeürich","n":[1,2]}')
    assert list(iterator) == [UsageReport(5, 7, 12, 0, 0), Finish("tool_calls")]


def test_parallel_tools_get_running_ordinals_ids_and_names():
    events = [
        _start(), *_text_block(0, "x"),
        *_tool_block(1, "t1", "a", '{"k":', '1}'), *_tool_block(2, "t2", "b", "{}"), *_end("tool_use"),
    ]
    calls = [e for e in _run(events) if isinstance(e, ToolCallDelta)]
    assert [(c.index, c.id, c.name, c.arguments) for c in calls] == [
        (0, "t1", "a", '{"k":1}'), (1, "t2", "b", "{}"),
    ]


def test_a_tool_without_argument_fragments_is_an_empty_object():
    events = [_start(), *_tool_block(0, "t1", "ping"), *_end("tool_use")]
    assert _run(events)[0] == ToolCallDelta(0, "t1", "ping", "{}")


def test_usage_merges_start_and_delta_and_counts_cache_into_the_prompt():
    events = [_start(input_tokens=10, cache_write=3, cache_read=2, output=1), *_text_block(0, "a"), *_end(output=4)]
    report = next(e for e in _run(events) if isinstance(e, UsageReport))
    # prompt = input + both cache counts; total is always set (collect never estimates)
    assert report == UsageReport(15, 4, 19, 2, 3)


def test_no_usage_anywhere_is_a_shape_error():
    error, seen = _error_of([_start(usage=False), *_text_block(0, "a"), *_end(usage=False)])
    assert (error.kind, error.retryable) == ("shape", False)
    assert not any(isinstance(e, (UsageReport, Finish)) for e in seen)


@pytest.mark.parametrize(
    "stop_reason, finish",
    [("end_turn", "stop"), ("stop_sequence", "stop"), ("max_tokens", "length"),
     ("model_context_window_exceeded", "length"), ("tool_use", "tool_calls"), ("refusal", "content_filter")],
)
def test_stop_reasons_map_like_complete(stop_reason, finish):
    assert _run([_start(), *_text_block(0, "a"), *_end(stop_reason)])[-1] == Finish(finish)


@pytest.mark.parametrize("stop_reason", ["pause_turn", None, "future_value"])
def test_an_unsupported_stop_reason_is_shape(stop_reason):
    error, _ = _error_of([_start(), *_text_block(0, "a"), *_end(stop_reason)])
    assert error.kind == "shape"


def test_an_empty_refusal_is_one_empty_text_delta_so_it_collects_to_empty_content():
    # PRD-022 T4 / fix 27e0e91: the only synthetic event.
    events = _run([_start(), *_end("refusal")])
    assert events == [TextDelta(""), UsageReport(5, 7, 12, 0, 0), Finish("content_filter")]
    result = collect(events, provider=_provider(), request=_req())
    assert (result.response, result.finish_reason) == ("", "content_filter")


def test_an_empty_end_turn_is_shape():
    error, _ = _error_of([_start(), *_end("end_turn")])
    assert error.kind == "shape"


def test_a_refusal_with_text_does_not_add_a_synthetic_delta():
    assert _run([_start(), *_text_block(0, "no"), *_end("refusal")])[0] == TextDelta("no")


# --- AC2: thinking --------------------------------------------------------------------


def _thinking_events():
    return [
        _start(),
        _block(0, "thinking", thinking=""),
        _delta(0, "thinking_delta", thinking="hm"), _delta(0, "thinking_delta", thinking=""),
        _delta(0, "thinking_delta", thinking="mm"),
        _delta(0, "signature_delta", signature="SIG-SECRET"),
        _stop(0),
        _block(1, "redacted_thinking", data="REDACTED-SECRET"), _stop(1),
        *_text_block(2, "answer"), *_end(),
    ]


def test_reasoning_true_yields_only_non_empty_reasoning_deltas_and_asks_for_thinking():
    client = _FakeClient(_thinking_events())
    events = _run(None, reasoning=True, client=client)
    assert [e.text for e in events if isinstance(e, ReasoningDelta)] == ["hm", "mm"]
    assert client.bodies[0]["thinking"] == {"type": "adaptive", "display": "summarized"}
    assert client.bodies[0]["stream"] is True
    assert "SIG-SECRET" not in repr(events) and "REDACTED-SECRET" not in repr(events)


def test_reasoning_false_yields_none_and_omits_thinking_even_for_a_reasoning_model():
    client = _FakeClient(_thinking_events())
    events = _run(None, reasoning=False, client=client, request=_req(reasoning=True))
    assert not any(isinstance(e, ReasoningDelta) for e in events)
    assert "thinking" not in client.bodies[0]


def test_build_request_reasoning_none_keeps_the_capability():
    request = _req(reasoning=True)
    assert "thinking" in build_request(request, request.model, provider=_provider())
    assert "thinking" not in build_request(request, request.model, provider=_provider(), reasoning=False)
    plain = _req()
    assert "thinking" in build_request(plain, plain.model, provider=_provider(), reasoning=True)


# --- AC4: faults ----------------------------------------------------------------------


def test_no_stop_is_shape_and_no_finish_was_yielded():
    error, seen = _error_of([_start(), *_text_block(0, "partial")])
    assert error.kind == "shape" and "stream ended" in str(error)
    assert seen == [TextDelta("partial")]


@pytest.mark.parametrize("fragments", [['{"a": '], ["[1, 2]"], ['"text"'], ["not json"]])
def test_unparseable_or_non_object_tool_input_is_shape(fragments):
    error, seen = _error_of([_start(), *_tool_block(0, "t", "n", *fragments), *_end("tool_use")])
    assert error.kind == "shape" and not seen
    assert "not json" not in str(error)


@pytest.mark.parametrize(
    "raised, kind",
    [
        (anthropic.APIConnectionError(request=_request()), "transport"),
        (anthropic.APITimeoutError(request=_request()), "timeout"),
        (httpx.ReadError("boom"), "transport"),
        (httpx.ReadTimeout("slow"), "timeout"),
    ],
)
def test_transport_faults_mid_iteration_are_retryable(raised, kind):
    error, seen = _error_of([_start(), *_text_block(0, "a")], error=raised)
    assert (error.kind, error.retryable, error.provider) == (kind, True, "ant")
    assert seen == [TextDelta("a")]


def _status_error(cls, status, headers=None):
    response = httpx.Response(status, request=_request(), headers=headers or {}, json={"e": _SECRET})
    return cls(f"body quote {_SECRET} {_KEY}", response=response, body={"error": _SECRET})


def test_a_429_on_the_first_request_keeps_retry_after():
    client = _FakeClient(create_error=_status_error(anthropic.RateLimitError, 429, {"retry-after": "9"}))
    with pytest.raises(UpstreamError) as caught:
        list(AnthropicAdapter(_provider(), sdk_client=client).stream(_req(), _KEY))
    error = caught.value
    assert (error.kind, error.upstream_status, error.retryable, error.retry_after_seconds) == ("status", 429, True, 9)
    for text in (str(error), repr(error), repr(error.args)):
        assert _SECRET not in text and _KEY not in text


def test_a_non_200_status_error_mid_stream_goes_through_sdk_error():
    error, _ = _error_of([_start()], error=_status_error(anthropic.InternalServerError, 503))
    assert (error.kind, error.upstream_status, error.retryable) == ("status", 503, True)


# --- in-stream `event: error` (an APIStatusError with status 200) ----------------------


def _in_stream(error_type, *, body=None):
    response = httpx.Response(200, request=_request())
    if body is None:
        body = {"type": "error", "error": {"type": error_type, "message": _SECRET}}
    return anthropic.APIStatusError(f"{body}", response=response, body=body)


@pytest.mark.parametrize(
    "error_type, kind, status, retryable",
    [
        ("overloaded_error", "status", 529, True),
        ("api_error", "status", 500, True),
        ("rate_limit_error", "status", 429, True),
        ("authentication_error", "misconfigured", 401, False),
        ("permission_error", "misconfigured", 403, False),
        ("invalid_request_error", "status", 502, False),
        ("brand_new_error", "status", 502, False),
        (None, "status", 502, False),
    ],
)
def test_in_stream_error_events_are_mapped_by_error_type(error_type, kind, status, retryable):
    raised = _in_stream(error_type) if error_type else _in_stream(None, body={"unexpected": _SECRET})
    error = _in_stream_error(raised, _provider())
    assert (error.kind, error.upstream_status, error.retryable, error.provider) == (kind, status, retryable, "ant")
    assert error.retry_after_seconds is None
    for text in (str(error), repr(error), repr(error.args)):  # T10: never the event's text
        assert _SECRET not in text and _KEY not in text


@pytest.mark.parametrize("body", ["a string body", None, ["list"], {"error": "not a dict"}])
def test_an_unparseable_in_stream_error_body_is_a_final_502(body):
    error = _in_stream_error(_in_stream(None, body=body), _provider())
    assert (error.kind, error.upstream_status, error.retryable) == ("status", 502, False)


def test_an_in_stream_overloaded_event_surfaces_from_the_stream_as_retryable_529():
    error, seen = _error_of([_start(), *_text_block(0, "a")], error=_in_stream("overloaded_error"))
    assert (error.kind, error.upstream_status, error.retryable) == ("status", 529, True)
    assert seen == [TextDelta("a")] and error.__cause__ is None


# --- AC5 / lifecycle ------------------------------------------------------------------


def test_create_is_not_called_until_the_first_next():
    client = _FakeClient([_start(), *_text_block(0, "a"), *_end()])
    iterator = AnthropicAdapter(_provider(), sdk_client=client).stream(_req(), _KEY)
    assert client.bodies == []
    next(iterator)
    assert len(client.bodies) == 1


def test_incompatible_requests_raise_from_stream_itself_with_no_create_call():
    bad_history = _req([Message("user", "q"), Message("assistant", "", (ToolCallSpec("c", "get", "[1]"),))])
    forced = ToolParams([{"type": "function", "function": {"name": "get"}}], "required", None)
    cases = [
        (bad_history, False),
        (_req(tools=forced), False),  # model does not claim forced_tool_choice
        (_req(tools=forced, forced_tool_choice=True, reasoning=True), True),  # thinking + forced choice
    ]
    for request, reasoning in cases:
        client = _FakeClient([])
        with pytest.raises(UpstreamError) as caught:
            AnthropicAdapter(_provider(), sdk_client=client).stream(request, _KEY, reasoning=reasoning)
        assert caught.value.kind == "incompatible" and client.bodies == []


def test_a_forced_choice_is_allowed_when_the_stream_does_not_ask_for_thinking():
    forced = ToolParams([{"type": "function", "function": {"name": "get"}}], "required", None)
    request = _req(tools=forced, forced_tool_choice=True, reasoning=True)
    client = _FakeClient([_start(), *_tool_block(0, "t", "get", "{}"), *_end("tool_use")])
    list(AnthropicAdapter(_provider(), sdk_client=client).stream(request, _KEY, reasoning=False))
    assert client.bodies[0]["tool_choice"]["type"] == "any" and "thinking" not in client.bodies[0]


def test_no_key_with_an_owned_client_is_misconfigured_at_call_time(monkeypatch):
    monkeypatch.setattr(adapter_mod, "_open_sdk_client", lambda *a: pytest.fail("built a client"))
    with pytest.raises(UpstreamError) as caught:
        AnthropicAdapter(_provider()).stream(_req(), None)
    assert caught.value.kind == "misconfigured"


def _owned(monkeypatch, client):
    monkeypatch.setattr(adapter_mod, "_open_sdk_client", lambda provider, key: client)
    return AnthropicAdapter(_provider())


def test_an_owned_client_and_the_sdk_stream_are_closed_on_exhaustion(monkeypatch):
    client = _FakeClient([_start(), *_text_block(0, "a"), *_end()])
    list(_owned(monkeypatch, client).stream(_req(), _KEY))
    assert client.closed is True and client.stream.closed is True


def test_an_owned_client_is_closed_when_the_consumer_closes_mid_stream(monkeypatch):
    client = _FakeClient([_start(), *_text_block(0, "a", "b", "c"), *_end()])
    iterator = _owned(monkeypatch, client).stream(_req(), _KEY)
    next(iterator)
    assert client.closed is False
    iterator.close()
    assert client.closed is True and client.stream.closed is True


def test_an_owned_client_is_closed_on_error_and_when_create_itself_fails(monkeypatch):
    client = _FakeClient([_start()], error=anthropic.APIConnectionError(request=_request()))
    with pytest.raises(UpstreamError):
        list(_owned(monkeypatch, client).stream(_req(), _KEY))
    assert client.closed is True and client.stream.closed is True

    failing = _FakeClient(create_error=anthropic.APIConnectionError(request=_request()))
    with pytest.raises(UpstreamError):
        list(_owned(monkeypatch, failing).stream(_req(), _KEY))
    assert failing.closed is True


def test_an_injected_client_is_never_closed():
    client = _FakeClient([_start(), *_text_block(0, "a"), *_end()])
    list(AnthropicAdapter(_provider(), sdk_client=client).stream(_req(), _KEY))
    assert client.closed is False and client.stream.closed is True  # the stream is ours; the client is not

