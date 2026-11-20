"""PRD-022 STORY-005: the native Anthropic adapter's `complete()`.

No network: a fake SDK client is injected through `sdk_client=`, client
construction is observed by patching the SDK names in the adapter module, and one
loopback stub server (port picked by the OS) proves the real SDK path.
"""

import dataclasses
import json
import threading
import types
from http.server import BaseHTTPRequestHandler, HTTPServer

import anthropic
import httpx
import pytest

from app.models.messages import Message, ToolCallSpec
from app.services import provider_registry as registry
from app.services.upstream import anthropic as adapter_mod
from app.services.upstream.anthropic import (
    ANTHROPIC_REQUEST_KEYS,
    AnthropicAdapter,
    build_request,
    dropped_params,
    map_response,
)
from app.services.upstream.params import GenerationParams, ToolParams
from app.services.upstream.types import UpstreamError, UpstreamRequest

_KEY = "sk-ant-TESTKEY-123"
_SECRET = "SECRET-PROMPT-TEXT"


def _provider(**overrides):
    fields = dict(
        name="ant", label="Anthropic", type="anthropic", base_url="https://api.anthropic.com",
        key_env="K", insecure_http=False, trust="external", pii="redact", byok=False,
        passthrough=False, passthrough_capabilities=registry.Capabilities(),
        usage_missing="estimate", estimate_chars_per_token=4.0, timeout_seconds=12.5,
        roles=None, models=(),
    )
    fields.update(overrides)
    return registry.Provider(**fields)


def _model(*, max_tokens=1024, prompt_cache="off", **caps):
    return registry.CatalogModel(
        id="claude-x", upstream="claude-up", roles=None,
        capabilities=registry.Capabilities(tools=True, **caps),
        provider_name="ant", default_max_tokens=max_tokens, prompt_cache=prompt_cache,
    )


def _req(messages=None, *, params=None, tools=None, model=None):
    return UpstreamRequest(
        messages if messages is not None else [Message("user", "hi")],
        "claude-up", params, tools, model if model is not None else _model(),
    )


def _body(request=None, model=None, provider=None):
    request = request or _req()
    return build_request(request, model or request.model, provider=provider or _provider())


def _tool(name="get", **function):
    return {"type": "function", "function": {"name": name, **function}}


def _msg(content=None, stop_reason="end_turn", usage=None, model="claude-up"):
    if content is None:
        content = [types.SimpleNamespace(type="text", text="hello")]
    if usage is None:
        usage = types.SimpleNamespace(input_tokens=2, output_tokens=3)
    return types.SimpleNamespace(content=content, stop_reason=stop_reason, usage=usage, model=model)


def _text(text):
    return types.SimpleNamespace(type="text", text=text)


class _FakeClient:
    def __init__(self, reply=None, error=None):
        self.bodies = []
        self.closed = False
        self._reply, self._error = reply, error
        outer = self

        class _Messages:
            def create(self, **body):
                outer.bodies.append(body)
                if outer._error is not None:
                    raise outer._error
                return outer._reply if outer._reply is not None else _msg()

        self.messages = _Messages()

    def close(self):
        self.closed = True


def _complete(request=None, client=None, provider=None):
    client = client or _FakeClient()
    return AnthropicAdapter(provider or _provider(), sdk_client=client).complete(
        request or _req(), _KEY
    )


# --- AC1: request mapping -----------------------------------------------------


def test_user_and_assistant_turns_become_blocks_and_system_is_hoisted_in_order():
    messages = [
        Message("system", "S1"),
        Message("user", "u1"),
        Message("assistant", "a1"),
        Message("system", "S2"),  # a non-leading system turn loses its position (PRD-022 6.5)
        Message("user", "u2"),
    ]
    body = _body(_req(messages))
    assert body["system"] == "S1\n\nS2"
    assert body["messages"] == [
        {"role": "user", "content": [{"type": "text", "text": "u1"}]},
        {"role": "assistant", "content": [{"type": "text", "text": "a1"}]},
        {"role": "user", "content": [{"type": "text", "text": "u2"}]},
    ]


def test_system_key_is_omitted_without_a_system_turn():
    assert "system" not in _body()


def test_assistant_tool_calls_become_tool_use_blocks_with_no_empty_text_block():
    call = ToolCallSpec("c1", "get", '{"a": 1}')
    body = _body(_req([Message("user", "q"), Message("assistant", "", (call,))]))
    assert body["messages"][1] == {
        "role": "assistant",
        "content": [{"type": "tool_use", "id": "c1", "name": "get", "input": {"a": 1}}],
    }
    with_text = _body(_req([Message("user", "q"), Message("assistant", "t", (call,))]))
    assert [b["type"] for b in with_text["messages"][1]["content"]] == ["text", "tool_use"]


def test_consecutive_tool_turns_are_one_user_message_in_order():
    calls = (ToolCallSpec("c1", "a", "{}"), ToolCallSpec("c2", "b", "{}"))
    messages = [
        Message("user", "q"),
        Message("assistant", "", calls),
        Message("tool", "r1", tool_call_id="c1"),
        Message("tool", "r2", tool_call_id="c2"),
    ]
    body = _body(_req(messages))
    assert body["messages"][2] == {
        "role": "user",
        "content": [
            {"type": "tool_result", "tool_use_id": "c1", "content": "r1"},
            {"type": "tool_result", "tool_use_id": "c2", "content": "r2"},
        ],
    }
    assert len(body["messages"]) == 3


def test_a_user_turn_after_tool_turns_stays_a_separate_message():
    # The API combines same-role turns itself; the adapter adds no merge rule (plan decision).
    messages = [
        Message("user", "q"),
        Message("assistant", "", (ToolCallSpec("c1", "a", "{}"),)),
        Message("tool", "r1", tool_call_id="c1"),
        Message("user", "next"),
    ]
    body = _body(_req(messages))
    assert [m["role"] for m in body["messages"]] == ["user", "assistant", "user", "user"]
    assert body["messages"][2]["content"][0]["type"] == "tool_result"
    assert body["messages"][3]["content"] == [{"type": "text", "text": "next"}]


def test_an_empty_user_turn_keeps_its_empty_text_block():
    # Orchestrator correction: do not invent content; the API's 400 is the honest outcome.
    body = _body(_req([Message("user", "")]))
    assert body["messages"][0]["content"] == [{"type": "text", "text": ""}]


def test_tools_map_to_input_schema():
    tools = ToolParams(
        [
            _tool("get", description="d", parameters={"type": "object", "properties": {}}, strict=True),
            _tool("bare"),
        ]
    )
    assert _body(_req(tools=tools))["tools"] == [
        {"name": "get", "description": "d", "input_schema": {"type": "object", "properties": {}}, "strict": True},
        {"name": "bare", "input_schema": {"type": "object"}},
    ]


@pytest.mark.parametrize(
    "choice, expected",
    [
        ("none", {"type": "none"}),
        ("auto", {"type": "auto"}),
        ("required", {"type": "any"}),
        ({"type": "function", "function": {"name": "get"}}, {"type": "tool", "name": "get"}),
    ],
)
def test_tool_choice_mapping(choice, expected):
    model = _model(forced_tool_choice=True)
    body = _body(_req(tools=ToolParams([_tool()], tool_choice=choice), model=model))
    assert body["tool_choice"] == expected


@pytest.mark.parametrize(
    "choice, expected",
    [
        ("none", {"type": "none"}),  # never gets the flag: the SDK type does not allow it
        ("auto", {"type": "auto", "disable_parallel_tool_use": True}),
        ("required", {"type": "any", "disable_parallel_tool_use": True}),
        ({"type": "function", "function": {"name": "get"}},
         {"type": "tool", "name": "get", "disable_parallel_tool_use": True}),
        (None, {"type": "auto", "disable_parallel_tool_use": True}),
    ],
)
def test_parallel_tool_calls_false_disables_parallel_use(choice, expected):
    model = _model(forced_tool_choice=True)
    tools = ToolParams([_tool()], tool_choice=choice, parallel_tool_calls=False)
    assert _body(_req(tools=tools, model=model))["tool_choice"] == expected


def test_no_tools_means_neither_tools_nor_tool_choice():
    body = _body()
    assert "tools" not in body and "tool_choice" not in body


def test_max_tokens_defaults_to_the_catalogue_and_is_overridden_by_the_request():
    assert _body()["max_tokens"] == 1024
    assert _body(_req(params=GenerationParams(max_tokens=77)))["max_tokens"] == 77


@pytest.mark.parametrize("stop, expected", [("x", ["x"]), (["a", "b"], ["a", "b"])])
def test_stop_becomes_stop_sequences(stop, expected):
    assert _body(_req(params=GenerationParams(stop=stop)))["stop_sequences"] == expected


def test_sampling_params_are_sent_only_when_the_model_accepts_them():
    params = GenerationParams(temperature=0.5, top_p=0.9)
    off = _body(_req(params=params))
    assert "temperature" not in off and "top_p" not in off
    on = _body(_req(params=params, model=_model(sampling_params=True)))
    assert (on["temperature"], on["top_p"]) == (0.5, 0.9)


def test_prompt_cache_auto_sets_cache_control():
    assert _body(_req(model=_model(prompt_cache="auto")))["cache_control"] == {"type": "ephemeral"}
    assert "cache_control" not in _body()


def test_thinking_is_sent_only_for_a_reasoning_model():
    assert "thinking" not in _body()
    body = _body(_req(model=_model(reasoning=True)))
    assert body["thinking"] == {"type": "adaptive", "display": "summarized"}


# --- AC1: T9 allowlist --------------------------------------------------------


def test_request_keys_within_allowlist():
    variants = [
        _req(),
        _req([Message("system", "s"), Message("user", "u")], params=GenerationParams(max_tokens=5, stop="x")),
        _req(tools=ToolParams([_tool()], tool_choice="auto"), model=_model(reasoning=True, prompt_cache="auto")),
        _req(params=GenerationParams(temperature=1.0, top_p=0.5), model=_model(sampling_params=True)),
    ]
    for request in variants:
        assert set(_body(request)) <= ANTHROPIC_REQUEST_KEYS


def test_fully_populated_request_has_exact_allowlist():
    request = _req(
        [Message("system", "s"), Message("user", "u")],
        params=GenerationParams(temperature=1.0, top_p=0.5, max_tokens=9, stop="x"),
        tools=ToolParams([_tool()], tool_choice="auto"),
        model=_model(sampling_params=True, reasoning=True, prompt_cache="auto"),
    )
    assert set(_body(request)) == ANTHROPIC_REQUEST_KEYS


# --- AC2: incompatible, before the network ------------------------------------


def _assert_incompatible(request, client):
    with pytest.raises(UpstreamError) as caught:
        _complete(request, client)
    error = caught.value
    assert error.kind == "incompatible" and error.retryable is False and error.fallback_eligible is False
    assert error.provider == "ant" and str(error).startswith("Anthropic: ")
    assert _SECRET not in str(error)
    assert client.bodies == []  # the SDK was never called
    return error


@pytest.mark.parametrize("arguments", ["[1]", "not json", "3"])
def test_incompatible_tool_arguments_that_are_not_a_json_object(arguments):
    messages = [
        Message("user", _SECRET),
        Message("assistant", "", (ToolCallSpec("c1", "get", arguments),)),
    ]
    _assert_incompatible(_req(messages), _FakeClient())


@pytest.mark.parametrize("choice", ["required", {"type": "function", "function": {"name": "get"}}])
def test_incompatible_forced_tool_choice_without_the_capability(choice):
    request = _req([Message("user", _SECRET)], tools=ToolParams([_tool()], tool_choice=choice))
    _assert_incompatible(request, _FakeClient())


@pytest.mark.parametrize("choice", ["required", {"type": "function", "function": {"name": "get"}}])
def test_incompatible_forced_tool_choice_with_extended_thinking(choice):
    # Orchestrator correction: the API rejects thinking with any/tool, so the candidate is ineligible.
    request = _req(
        [Message("user", _SECRET)],
        tools=ToolParams([_tool()], tool_choice=choice),
        model=_model(forced_tool_choice=True, reasoning=True),
    )
    error = _assert_incompatible(request, _FakeClient())
    assert "forced tool_choice cannot be combined with extended thinking" in str(error)


def test_auto_tool_choice_with_thinking_is_allowed():
    request = _req(tools=ToolParams([_tool()], tool_choice="auto"), model=_model(reasoning=True))
    assert _body(request)["thinking"]["type"] == "adaptive"


def test_a_missing_model_is_incompatible():
    request = UpstreamRequest([Message("user", "hi")], "claude-up")
    with pytest.raises(UpstreamError) as caught:
        AnthropicAdapter(_provider(), sdk_client=_FakeClient()).complete(request, _KEY)
    assert caught.value.kind == "incompatible"


# --- AC3: response mapping ----------------------------------------------------


def test_text_blocks_concatenate_and_the_model_is_reported():
    result = map_response(_msg([_text("a"), _text("b")]), _provider())
    assert result.response == "ab" and result.model_used == "claude-up"
    assert result.finish_reason == "stop" and result.usage_estimated is False


def test_tool_use_maps_to_canonical_json_arguments():
    block = types.SimpleNamespace(type="tool_use", id="t1", name="get", input={"q": "ñandú", "n": [1, 2]})
    result = map_response(_msg([block], stop_reason="tool_use"), _provider())
    assert result.tool_calls == (ToolCallSpec("t1", "get", '{"q":"ñandú","n":[1,2]}'),)
    assert result.finish_reason == "tool_calls" and result.response == ""


def test_thinking_is_counted_and_never_emitted():
    blocks = [
        types.SimpleNamespace(type="thinking", thinking="PRIVATE", signature="s"),
        types.SimpleNamespace(type="redacted_thinking", data="x"),
        _text("answer"),
    ]
    result = map_response(_msg(blocks), _provider())
    assert result.response == "answer" and result.reasoning_blocks == 2
    assert "PRIVATE" not in repr(result)


@pytest.mark.parametrize(
    "stop, finish",
    [
        ("end_turn", "stop"),
        ("stop_sequence", "stop"),
        ("max_tokens", "length"),
        ("model_context_window_exceeded", "length"),
        ("tool_use", "tool_calls"),
        ("refusal", "content_filter"),
    ],
)
def test_map_response_stop_reasons(stop, finish):
    assert map_response(_msg(stop_reason=stop), _provider()).finish_reason == finish


def test_an_empty_refusal_is_an_answer_not_a_shape_error():
    # PRD-022 6.2 / T4: a refusal is an answer, never a fault, even with no content.
    result = map_response(_msg(content=[], stop_reason="refusal"), _provider())
    assert (result.response, result.finish_reason, result.tool_calls) == ("", "content_filter", ())


def test_empty_content_without_refusal_is_still_shape():
    with pytest.raises(UpstreamError) as caught:
        map_response(_msg(content=[]), _provider())
    assert caught.value.kind == "shape"


@pytest.mark.parametrize("stop", ["pause_turn", None, "something_new"])
def test_pause_turn_and_unknown_stop_reasons_are_shape(stop):
    with pytest.raises(UpstreamError) as caught:
        map_response(_msg(stop_reason=stop), _provider())
    assert (caught.value.kind, caught.value.retryable, caught.value.provider) == ("shape", False, "ant")


def test_missing_usage_is_shape():
    message = _msg()
    message.usage = None
    with pytest.raises(UpstreamError) as caught:
        map_response(message, _provider())
    assert caught.value.kind == "shape" and caught.value.retryable is False


def test_no_text_and_no_tool_call_is_shape():
    with pytest.raises(UpstreamError) as caught:
        map_response(_msg([]), _provider())
    assert caught.value.kind == "shape"


def test_usage_sums_cache_tokens():
    usage = types.SimpleNamespace(
        input_tokens=11, output_tokens=5, cache_creation_input_tokens=7, cache_read_input_tokens=5
    )
    result = map_response(_msg(usage=usage), _provider())
    assert (result.input_tokens, result.output_tokens, result.tokens_used) == (23, 5, 28)
    assert (result.cache_write_tokens, result.cache_read_tokens) == (7, 5)


def test_a_none_cache_field_counts_as_zero():
    usage = types.SimpleNamespace(
        input_tokens=4, output_tokens=1, cache_creation_input_tokens=None, cache_read_input_tokens=None
    )
    result = map_response(_msg(usage=usage), _provider())
    assert (result.input_tokens, result.cache_write_tokens, result.cache_read_tokens) == (4, 0, 0)


def test_complete_returns_the_mapped_result_with_dropped_params():
    request = _req(params=GenerationParams(temperature=0.5, top_p=0.9))
    client = _FakeClient()
    result = _complete(request, client)
    assert result.response == "hello"
    assert result.dropped_params == ("temperature", "top_p")
    assert "temperature" not in client.bodies[0]


def test_dropped_params_reported_only_when_set_and_not_accepted():
    assert dropped_params(_req(), _model()) == ()
    assert dropped_params(_req(params=GenerationParams(top_p=0.5)), _model()) == ("top_p",)
    both = _req(params=GenerationParams(temperature=1.0, top_p=0.5))
    assert dropped_params(both, _model(sampling_params=True)) == ()
    assert _complete(_req()).dropped_params == ()


# --- AC4: SDK errors ----------------------------------------------------------


def _request():
    return httpx.Request("POST", "https://api.anthropic.com/v1/messages")


def _status_error(cls, status, headers=None):
    response = httpx.Response(status, request=_request(), headers=headers or {}, json={"error": _SECRET})
    return cls(f"body quote {_SECRET} {_KEY}", response=response, body={"error": _SECRET})


@pytest.mark.parametrize(
    "build, kind, status, retryable",
    [
        (lambda: anthropic.APITimeoutError(request=_request()), "timeout", None, True),
        (lambda: anthropic.APIConnectionError(request=_request()), "transport", None, True),
        (lambda: _status_error(anthropic.AuthenticationError, 401), "misconfigured", 401, False),
        (lambda: _status_error(anthropic.PermissionDeniedError, 403), "status", 403, False),
        (lambda: _status_error(anthropic.BadRequestError, 400), "status", 400, False),
        (lambda: _status_error(anthropic.NotFoundError, 404), "status", 404, False),
        (lambda: _status_error(anthropic.RateLimitError, 429), "status", 429, True),
        (lambda: _status_error(anthropic.InternalServerError, 500), "status", 500, True),
        (lambda: _status_error(anthropic.ServiceUnavailableError, 503), "status", 503, True),
        (lambda: _status_error(anthropic.OverloadedError, 529), "status", 529, True),
        (lambda: _status_error(anthropic.APIStatusError, 307), "status", 307, False),
    ],
)
def test_sdk_error_mapping(build, kind, status, retryable):
    client = _FakeClient(error=build())
    with pytest.raises(UpstreamError) as caught:
        _complete(client=client)
    error = caught.value
    assert (error.kind, error.upstream_status, error.retryable) == (kind, status, retryable)
    assert error.provider == "ant" and str(error).startswith("Anthropic request failed")
    # T10: neither the SDK's quoted body nor the key reaches the message or its repr.
    for text in (str(error), repr(error), repr(error.args)):
        assert _SECRET not in text and _KEY not in text


def test_other_sdk_api_errors_are_shape():
    error = anthropic.APIResponseValidationError(
        httpx.Response(200, request=_request(), json={}), body={}
    )
    with pytest.raises(UpstreamError) as caught:
        _complete(client=_FakeClient(error=error))
    assert (caught.value.kind, caught.value.retryable) == ("shape", False)


@pytest.mark.parametrize(
    "header, expected", [("7", 7), ("0", 1), ("Wed, 21 Oct 2026 07:28:00 GMT", None), (None, None)]
)
def test_retry_after_is_read_from_the_429_response_headers(header, expected):
    headers = {"retry-after": header} if header is not None else {}
    client = _FakeClient(error=_status_error(anthropic.RateLimitError, 429, headers))
    with pytest.raises(UpstreamError) as caught:
        _complete(client=client)
    assert caught.value.retry_after_seconds == expected


def test_a_non_429_never_carries_retry_after():
    client = _FakeClient(error=_status_error(anthropic.InternalServerError, 503, {"retry-after": "9"}))
    with pytest.raises(UpstreamError) as caught:
        _complete(client=client)
    assert caught.value.retry_after_seconds is None


def test_timeout_is_not_shadowed_by_connection_error():
    assert issubclass(anthropic.APITimeoutError, anthropic.APIConnectionError)
    with pytest.raises(UpstreamError) as caught:
        _complete(client=_FakeClient(error=anthropic.APITimeoutError(request=_request())))
    assert caught.value.kind == "timeout"


def test_a_misconfigured_error_is_fallback_eligible_and_others_follow_retryable():
    with pytest.raises(UpstreamError) as caught:
        _complete(client=_FakeClient(error=_status_error(anthropic.AuthenticationError, 401)))
    assert caught.value.fallback_eligible is True


def test_no_key_for_an_owned_client_is_misconfigured_without_building_one(monkeypatch):
    monkeypatch.setattr(adapter_mod, "_open_sdk_client", lambda *a: pytest.fail("built a client"))
    with pytest.raises(UpstreamError) as caught:
        AnthropicAdapter(_provider()).complete(_req(), None)
    assert caught.value.kind == "misconfigured"


# --- AC5: construction --------------------------------------------------------


def test_client_construction(monkeypatch):
    calls = {}

    def fake_http(**kwargs):
        calls["http"] = kwargs
        return "HTTP"

    def fake_anthropic(**kwargs):
        calls["client"] = kwargs
        return "CLIENT"

    monkeypatch.setattr(adapter_mod.anthropic, "DefaultHttpxClient", fake_http)
    monkeypatch.setattr(adapter_mod.anthropic, "Anthropic", fake_anthropic)
    assert adapter_mod._open_sdk_client(_provider(), _KEY) == "CLIENT"
    assert calls["client"] == {
        "api_key": _KEY,
        "base_url": "https://api.anthropic.com",
        "timeout": 12.5,
        "max_retries": 0,
        "http_client": "HTTP",
    }
    assert calls["http"] == {"follow_redirects": False}


def test_the_real_client_is_built_without_retries_or_redirects():
    client = adapter_mod._open_sdk_client(_provider(), _KEY)
    try:
        assert client.max_retries == 0 and client.timeout == 12.5
        assert str(client.base_url).startswith("https://api.anthropic.com")
        assert client._client.follow_redirects is False
    finally:
        client.close()


def test_an_owned_client_is_closed_and_an_injected_one_is_not(monkeypatch):
    owned = _FakeClient()
    monkeypatch.setattr(adapter_mod, "_open_sdk_client", lambda provider, key: owned)
    AnthropicAdapter(_provider()).complete(_req(), _KEY)
    assert owned.closed is True

    failing = _FakeClient(error=anthropic.APIConnectionError(request=_request()))
    monkeypatch.setattr(adapter_mod, "_open_sdk_client", lambda provider, key: failing)
    with pytest.raises(UpstreamError):
        AnthropicAdapter(_provider()).complete(_req(), _KEY)
    assert failing.closed is True

    injected = _FakeClient()
    AnthropicAdapter(_provider(), sdk_client=injected).complete(_req(), _KEY)
    assert injected.closed is False


def test_stream_raises_incompatible_at_call_time():
    with pytest.raises(UpstreamError) as caught:
        AnthropicAdapter(_provider(), sdk_client=_FakeClient()).stream(_req(), _KEY)
    error = caught.value
    assert (error.kind, error.provider, error.retryable) == ("incompatible", "ant", False)
    assert "STORY-007" in str(error)


def test_upstream_result_dropped_params_defaults_empty():
    from app.services.upstream.types import UpstreamResult

    assert dataclasses.fields(UpstreamResult)[-1].name == "dropped_params"
    assert UpstreamResult("a", "m", 1).dropped_params == ()


# --- the real SDK path, against a loopback stub -------------------------------

_WIRE_MESSAGE = {
    "id": "msg_01", "type": "message", "role": "assistant", "model": "claude-up",
    "content": [{"type": "text", "text": "from the wire"}],
    "stop_reason": "end_turn", "stop_sequence": None,
    "usage": {"input_tokens": 3, "output_tokens": 2},
}


@pytest.fixture
def stub():
    seen = []
    plan = {"status": 200, "headers": {}}

    class _Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("content-length") or 0)
            body = self.rfile.read(length)
            seen.append(
                (self.path, {k.lower(): v for k, v in self.headers.items()}, json.loads(body or b"{}"))
            )
            payload = json.dumps(_WIRE_MESSAGE).encode()
            self.send_response(plan["status"])
            for name, value in plan["headers"].items():
                self.send_header(name, value)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield types.SimpleNamespace(
        url=f"http://127.0.0.1:{server.server_address[1]}", seen=seen, plan=plan
    )
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def test_the_real_sdk_path_sends_a_bearer_header_and_maps_the_reply(stub):
    provider = _provider(base_url=stub.url)
    result = AnthropicAdapter(provider).complete(_req(), _KEY)
    assert result.response == "from the wire" and result.tokens_used == 5
    path, headers, body = stub.seen[0]
    assert path == "/v1/messages" and headers["authorization"] == f"Bearer {_KEY}"
    assert set(body) <= ANTHROPIC_REQUEST_KEYS


def test_the_real_sdk_path_surfaces_a_redirect_as_a_non_retryable_status(stub):
    stub.plan.update(status=307, headers={"location": "http://127.0.0.1:9/elsewhere"})
    with pytest.raises(UpstreamError) as caught:
        AnthropicAdapter(_provider(base_url=stub.url)).complete(_req(), _KEY)
    error = caught.value
    assert (error.kind, error.upstream_status, error.retryable) == ("status", 307, False)
    assert len(stub.seen) == 1  # not followed, and the SDK did not retry


def test_a_large_default_max_tokens_does_not_trip_the_sdks_streaming_guard(stub):
    # Without an explicit timeout the SDK refuses a non-streaming call this large (ValueError).
    request = _req(model=_model(max_tokens=64000))
    result = AnthropicAdapter(_provider(base_url=stub.url)).complete(request, _KEY)
    assert result.response == "from the wire" and stub.seen[0][2]["max_tokens"] == 64000
