import dataclasses
import json
import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import httpx
import pytest

from app.config import settings
from app.models.messages import Message, ToolCallSpec
from app.services.openrouter_client import (
    GenerationParams,
    OpenRouterError,
    OpenRouterResult,
    ToolParams,
    UnsupportedParameterError,
    call_openrouter,
)

_API_URL = "https://openrouter.ai/api/v1/chat/completions"


class _FakeClient:
    def __init__(self, response=None, exc=None):
        self._response = response
        self._exc = exc
        self.requests = []

    def post(self, url, headers=None, json=None):
        self.requests.append({"url": url, "headers": headers, "json": json})
        if self._exc:
            raise self._exc
        return self._response


def _response(content="Hello!", tokens=45, status_code=200, body=None):
    request = httpx.Request("POST", _API_URL)
    payload = body if body is not None else {
        "choices": [{"message": {"content": content}}],
        "usage": {"total_tokens": tokens},
    }
    return httpx.Response(status_code, request=request, json=payload)


def test_success_returns_response_model_and_tokens():
    client = _FakeClient(response=_response(content="Hello!", tokens=45))

    result = call_openrouter([Message("user", "hello")], model="gpt-4", api_key="req-key", client=client)

    assert result.response == "Hello!"
    assert result.model_used == "gpt-4"
    assert result.tokens_used == 45


def test_default_model_used_when_omitted():
    client = _FakeClient(response=_response())

    result = call_openrouter([Message("user", "hello")], api_key="req-key", client=client)

    assert result.model_used == "gpt-4"
    assert client.requests[0]["json"]["model"] == "gpt-4"


def test_per_request_api_key_overrides_env(monkeypatch):
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "env-key")
    client = _FakeClient(response=_response())

    call_openrouter([Message("user", "hello")], api_key="explicit-key", client=client)

    assert client.requests[0]["headers"]["Authorization"] == "Bearer explicit-key"


def test_falls_back_to_env_key_when_not_provided(monkeypatch):
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "env-key")
    client = _FakeClient(response=_response())

    call_openrouter([Message("user", "hello")], client=client)

    assert client.requests[0]["headers"]["Authorization"] == "Bearer env-key"


def test_missing_key_raises_config_error(monkeypatch):
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "")

    with pytest.raises(OpenRouterError, match="not configured"):
        call_openrouter([Message("user", "hello")], client=_FakeClient())


def test_network_error_raises_openrouter_error():
    client = _FakeClient(exc=httpx.ConnectTimeout("timed out"))

    with pytest.raises(OpenRouterError):
        call_openrouter([Message("user", "hello")], api_key="k", client=client)


def test_non_2xx_status_raises_openrouter_error():
    client = _FakeClient(response=_response(status_code=500))

    with pytest.raises(OpenRouterError):
        call_openrouter([Message("user", "hello")], api_key="k", client=client)


def test_malformed_response_body_raises_openrouter_error():
    client = _FakeClient(response=_response(body={"unexpected": "shape"}))

    with pytest.raises(OpenRouterError):
        call_openrouter([Message("user", "hello")], api_key="k", client=client)


def test_api_key_never_appears_in_error_message():
    client = _FakeClient(exc=httpx.ConnectTimeout("timed out"))

    with pytest.raises(OpenRouterError) as exc_info:
        call_openrouter([Message("user", "hello")], api_key="super-secret-key", client=client)

    assert "super-secret-key" not in str(exc_info.value)


# --- PRD-010 STORY-003: characterization of today's OpenRouter payload ---
#
# Pinned before PRD-010 STORY-004. Assertions change only where a later
# story cites the decision.


def test_characterization_payload_shape_is_byte_identical():
    client = _FakeClient(response=_response())

    call_openrouter([Message("user", "hello")], model="gpt-4", api_key="k", client=client)

    payload = client.requests[0]["json"]
    expected = {"model": "gpt-4", "messages": [{"role": "user", "content": "hello"}]}
    # json.dumps with sort_keys=False makes this an ordered comparison, not
    # just an equal-set-of-keys one: a reordered payload would fail here
    # even though `payload == expected` would still pass.
    assert json.dumps(payload, sort_keys=False) == json.dumps(expected, sort_keys=False)


def test_characterization_headers_and_url():
    client = _FakeClient(response=_response())

    call_openrouter([Message("user", "hello")], model="gpt-4", api_key="k", client=client)

    request = client.requests[0]
    assert request["url"] == _API_URL
    assert request["headers"] == {
        "Authorization": "Bearer k",
        "Content-Type": "application/json",
    }


def test_characterization_default_client_uses_todays_timeout(monkeypatch):
    """AC 3: the _TIMEOUT_SECONDS module constant is gone; the default client's
    timeout now comes from settings.OPENROUTER_TIMEOUT_SECONDS."""
    captured = {}

    class _StubHttpxClient:
        def __init__(self, *args, **kwargs):
            captured["kwargs"] = kwargs

        def post(self, url, headers=None, json=None):
            return _response()

        def close(self):
            pass

    monkeypatch.setattr(httpx, "Client", _StubHttpxClient)

    call_openrouter([Message("user", "hello")], api_key="k")

    assert captured["kwargs"] == {"timeout": 120.0, "follow_redirects": False}  # PRD-020 D5/F3: redirects never followed; PRD-010 STORY-005: timeout from settings (default 120.0)


def test_timeout_setting_is_read_per_call_not_cached_at_import(monkeypatch):
    """AC4: settings.OPENROUTER_TIMEOUT_SECONDS is read inside call_openrouter,
    so a monkeypatched value takes effect without reimporting the module."""
    monkeypatch.setattr(settings, "OPENROUTER_TIMEOUT_SECONDS", 7.5)
    captured = {}

    class _StubHttpxClient:
        def __init__(self, *args, **kwargs):
            captured["kwargs"] = kwargs

        def post(self, url, headers=None, json=None):
            return _response()

        def close(self):
            pass

    monkeypatch.setattr(httpx, "Client", _StubHttpxClient)

    call_openrouter([Message("user", "hello")], api_key="k")

    assert captured["kwargs"] == {"timeout": 7.5, "follow_redirects": False}  # PRD-020 D5/F3


# --- PRD-010 STORY-004: call_openrouter takes a list of Messages ---


def test_multi_message_conversation_preserves_order_roles_and_content():
    client = _FakeClient(response=_response())
    messages = [
        Message("system", "be terse"),
        Message("user", "hi"),
        Message("assistant", "hello"),
        Message("user", "and now?"),
    ]

    call_openrouter(messages, model="gpt-4", api_key="k", client=client)

    payload = client.requests[0]["json"]
    assert payload["messages"] == [
        {"role": "system", "content": "be terse"},
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
        {"role": "user", "content": "and now?"},
    ]


def test_empty_messages_raises_before_any_http_call():
    client = _FakeClient(response=_response())

    with pytest.raises(OpenRouterError):
        call_openrouter([], api_key="k", client=client)

    assert client.requests == []


# --- PRD-010 STORY-005: GenerationParams allowlist and range validation ---


def test_from_mapping_rejects_unsupported_keys_named_and_sorted():
    with pytest.raises(UnsupportedParameterError, match=r"logit_bias, stream, tools"):
        GenerationParams.from_mapping(
            {"logit_bias": {}, "tools": [], "stream": True, "temperature": 0.2}
        )


def test_from_mapping_builds_only_allowed_fields():
    params = GenerationParams.from_mapping({"temperature": 0.2, "max_tokens": 100})
    assert params == GenerationParams(temperature=0.2, max_tokens=100)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"temperature": 3},
        {"top_p": 0},
        {"max_tokens": 0},
        {"max_tokens": True},
        {"stop": ["a", "b", "c", "d", "e"]},
        {"stop": ["a", 2]},
    ],
)
def test_out_of_range_params_raise_naming_field_and_range(kwargs):
    with pytest.raises(UnsupportedParameterError):
        GenerationParams(**kwargs)


def test_invalid_params_raise_before_any_http_call():
    class _ExplodingClient:
        def post(self, *args, **kwargs):
            raise AssertionError("HTTP call must not happen for invalid params")

    with pytest.raises(UnsupportedParameterError):
        call_openrouter(
            [Message("user", "hi")],
            api_key="k",
            params=GenerationParams.from_mapping({"temperature": 3}),
            client=_ExplodingClient(),
        )


def test_params_only_non_none_fields_reach_the_payload():
    client = _FakeClient(response=_response())
    params = GenerationParams(temperature=0.2, max_tokens=100)

    call_openrouter([Message("user", "hi")], api_key="k", params=params, client=client)

    payload = client.requests[0]["json"]
    assert payload["temperature"] == 0.2
    assert payload["max_tokens"] == 100
    assert "top_p" not in payload
    assert "stop" not in payload


def test_params_none_leaves_payload_byte_identical_to_story_003():
    """AC2: same assertion as test_characterization_payload_shape_is_byte_identical,
    restated here with params passed explicitly as None."""
    client = _FakeClient(response=_response())

    call_openrouter([Message("user", "hello")], model="gpt-4", api_key="k", params=None, client=client)

    payload = client.requests[0]["json"]
    expected = {"model": "gpt-4", "messages": [{"role": "user", "content": "hello"}]}
    assert json.dumps(payload, sort_keys=False) == json.dumps(expected, sort_keys=False)


# --- PRD-010 STORY-005: explicit null-content error ---


def _null_content_response(finish_reason="stop", tool_calls=None, tokens=10):
    request = httpx.Request("POST", _API_URL)
    message = {"content": None}
    if tool_calls is not None:
        message["tool_calls"] = tool_calls
    payload = {
        "choices": [{"message": message, "finish_reason": finish_reason}],
        "usage": {"total_tokens": tokens},
    }
    return httpx.Response(200, request=request, json=payload)


def test_null_content_raises_with_finish_reason():
    client = _FakeClient(response=_null_content_response(finish_reason="length"))

    with pytest.raises(OpenRouterError, match=r"finish_reason=length"):
        call_openrouter([Message("user", "hi")], api_key="k", client=client)


def test_null_content_with_tool_calls_names_prd_017():
    client = _FakeClient(
        response=_null_content_response(finish_reason="tool_calls", tool_calls=[{"id": "1"}])
    )

    # PRD-016 D14 (STORY-002): tool calling is PRD-017; was (PRD-016).
    with pytest.raises(OpenRouterError, match=r"tool calls are not supported \(PRD-017\)"):
        call_openrouter([Message("user", "hi")], api_key="k", client=client)


def test_null_content_without_tool_calls_omits_prd_017_note():
    client = _FakeClient(response=_null_content_response(finish_reason="stop"))

    with pytest.raises(OpenRouterError) as exc_info:
        call_openrouter([Message("user", "hi")], api_key="k", client=client)

    # PRD-016 D14 (STORY-002): the note now names PRD-017; asserting the old
    # token here would pass whatever the code says.
    assert "PRD-017" not in str(exc_info.value)


def test_null_content_error_never_contains_api_key():
    client = _FakeClient(response=_null_content_response())

    with pytest.raises(OpenRouterError) as exc_info:
        call_openrouter([Message("user", "hi")], api_key="super-secret-key", client=client)

    assert "super-secret-key" not in str(exc_info.value)


# --- PRD-013 STORY-003: the token split ---


def _usage_call(usage):
    body = {"choices": [{"message": {"content": "Hello!"}}], "usage": usage}
    client = _FakeClient(response=_response(body=body))
    return call_openrouter([Message("user", "hello")], api_key="k", client=client)


_UNUSABLE_COUNTS = [
    pytest.param("120", id="string"),
    pytest.param(-1, id="negative"),
    pytest.param(True, id="true"),
    pytest.param(False, id="false"),
    pytest.param(120.0, id="float"),
    pytest.param(None, id="null"),
    pytest.param([120], id="list"),
    pytest.param({}, id="object"),
]


def test_split_is_returned_beside_the_total():
    result = _usage_call({"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150})

    assert (result.input_tokens, result.output_tokens, result.tokens_used) == (120, 30, 150)


def test_total_only_succeeds_with_no_split():
    result = _usage_call({"total_tokens": 45})

    assert result.input_tokens is None
    assert result.output_tokens is None
    assert result.tokens_used == 45
    assert result.response == "Hello!"


@pytest.mark.parametrize("value", _UNUSABLE_COUNTS)
def test_an_unusable_prompt_count_is_none_and_the_call_succeeds(value):
    result = _usage_call({"prompt_tokens": value, "completion_tokens": 30, "total_tokens": 150})

    assert result.input_tokens is None
    assert result.output_tokens == 30
    assert result.tokens_used == 150


@pytest.mark.parametrize("value", _UNUSABLE_COUNTS)
def test_an_unusable_completion_count_is_none_and_the_call_succeeds(value):
    result = _usage_call({"prompt_tokens": 120, "completion_tokens": value, "total_tokens": 150})

    assert result.input_tokens == 120
    assert result.output_tokens is None
    assert result.tokens_used == 150


def test_a_zero_count_is_kept_as_zero():
    result = _usage_call({"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})

    # Zero is a count; None means "not reported". One must not become the other.
    assert result.input_tokens == 0 and result.input_tokens is not None
    assert result.output_tokens == 0 and result.output_tokens is not None


def test_the_split_is_reported_as_given_when_it_disagrees_with_the_total():
    result = _usage_call({"prompt_tokens": 100, "completion_tokens": 100, "total_tokens": 45})

    assert (result.input_tokens, result.output_tokens, result.tokens_used) == (100, 100, 45)


def test_a_split_without_a_total_still_raises():
    with pytest.raises(OpenRouterError, match=r"^OpenRouter returned an unexpected response shape: "):
        _usage_call({"prompt_tokens": 120, "completion_tokens": 30})


def test_three_positional_arguments_still_construct_a_result():
    positional = OpenRouterResult("r", "m", 3)

    assert positional.response == "r"
    assert positional.model_used == "m"
    assert positional.tokens_used == 3
    assert positional.input_tokens is None
    assert positional.output_tokens is None
    # The suite's stubs build it with these three keywords.
    assert OpenRouterResult(response="r", model_used="m", tokens_used=3) == positional


def test_the_split_fields_are_declared_last_and_in_order():
    assert [f.name for f in dataclasses.fields(OpenRouterResult)] == [
        # PRD-015 STORY-002 appends finish_reason after the split.
        # PRD-017 STORY-004 (D5, Section 6.9): tool_calls appended last with a default.
        "response", "model_used", "tokens_used", "input_tokens", "output_tokens", "finish_reason",
        "tool_calls",
    ]


# --- PRD-015 STORY-002: finish_reason ---


def _finish_reason_call(choice_extra):
    choice = {"message": {"content": "Hello!"}, **choice_extra}
    body = {"choices": [choice], "usage": {"total_tokens": 45}}
    client = _FakeClient(response=_response(body=body))
    return call_openrouter([Message("user", "hello")], api_key="k", client=client)


@pytest.mark.parametrize("reason", ["stop", "length", "content_filter"])
def test_finish_reason_is_carried_from_the_first_choice(reason):
    result = _finish_reason_call({"finish_reason": reason})

    assert result.finish_reason == reason
    assert result.response == "Hello!"


@pytest.mark.parametrize(
    "choice_extra",
    [
        pytest.param({}, id="absent"),
        pytest.param({"finish_reason": None}, id="null"),
        pytest.param({"finish_reason": 1}, id="int"),
        pytest.param({"finish_reason": True}, id="bool"),
        pytest.param({"finish_reason": ["stop"]}, id="list"),
    ],
)
def test_an_unusable_finish_reason_is_none_and_the_call_succeeds(choice_extra):
    result = _finish_reason_call(choice_extra)

    assert result.finish_reason is None
    assert (result.response, result.tokens_used) == ("Hello!", 45)


def test_three_argument_construction_leaves_finish_reason_none():
    assert OpenRouterResult("r", "m", 3).finish_reason is None
    assert OpenRouterResult(response="r", model_used="m", tokens_used=3).finish_reason is None


# --- PRD-015 STORY-002: upstream_status and retryable ---


def _status_client(status_code):
    return _FakeClient(response=_response(status_code=status_code, body={"error": "x"}))


def _malformed_json_client():
    request = httpx.Request("POST", _API_URL)
    return _FakeClient(response=httpx.Response(200, request=request, content=b"not json"))


_FAILURES = [
    pytest.param(lambda: _FakeClient(exc=httpx.ReadTimeout("t")), None, True, "OpenRouter request failed: ", id="read-timeout"),
    pytest.param(lambda: _FakeClient(exc=httpx.ConnectTimeout("t")), None, True, "OpenRouter request failed: ", id="connect-timeout"),
    pytest.param(lambda: _FakeClient(exc=httpx.ConnectError("c")), None, True, "OpenRouter request failed: ", id="connect-error"),
    pytest.param(lambda: _status_client(500), 500, True, "OpenRouter request failed: ", id="500"),
    pytest.param(lambda: _status_client(503), 503, True, "OpenRouter request failed: ", id="503"),
    pytest.param(lambda: _status_client(429), 429, True, "OpenRouter request failed: ", id="429"),
    pytest.param(lambda: _status_client(400), 400, False, "OpenRouter request failed: ", id="400"),
    pytest.param(lambda: _status_client(401), 401, False, "OpenRouter request failed: ", id="401"),
    pytest.param(lambda: _status_client(404), 404, False, "OpenRouter request failed: ", id="404"),
    pytest.param(_malformed_json_client, None, False, "OpenRouter returned an unexpected response shape: ", id="malformed-json"),
    pytest.param(
        lambda: _FakeClient(response=_response(body={"usage": {"total_tokens": 1}})),
        None, False, "OpenRouter returned an unexpected response shape: ", id="missing-choices",
    ),
    pytest.param(lambda: _FakeClient(response=_null_content_response()), None, False, "OpenRouter returned no text content", id="null-content"),
]


@pytest.mark.parametrize("make_client, status, retryable, prefix", _FAILURES)
def test_each_failure_carries_upstream_status_and_retryable(make_client, status, retryable, prefix):
    with pytest.raises(OpenRouterError) as exc_info:
        call_openrouter([Message("user", "hi")], api_key="k", client=make_client())

    assert exc_info.value.upstream_status == status
    assert exc_info.value.retryable is retryable
    assert str(exc_info.value).startswith(prefix)


def test_missing_key_is_not_retryable_and_has_no_status(monkeypatch):
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "")

    with pytest.raises(OpenRouterError) as exc_info:
        call_openrouter([Message("user", "hi")], client=_FakeClient())

    assert (exc_info.value.upstream_status, exc_info.value.retryable) == (None, False)
    assert str(exc_info.value) == (
        "OpenRouter API key not configured: pass openrouter_api_key or set OPENROUTER_API_KEY"
    )


def test_a_status_failure_message_is_byte_identical_to_todays():
    """The format is pinned, not httpx's wording: the expected string is built
    from the same HTTPStatusError the client sees."""
    response = _response(status_code=503, body={"error": "x"})
    with pytest.raises(httpx.HTTPStatusError) as status_exc:
        response.raise_for_status()

    with pytest.raises(OpenRouterError) as exc_info:
        call_openrouter([Message("user", "hi")], api_key="k", client=_FakeClient(response=response))

    assert str(exc_info.value) == f"OpenRouter request failed: {status_exc.value}"


def test_a_transport_failure_message_is_byte_identical_to_todays():
    error = httpx.ConnectError("connection refused")

    with pytest.raises(OpenRouterError) as exc_info:
        call_openrouter([Message("user", "hi")], api_key="k", client=_FakeClient(exc=error))

    assert str(exc_info.value) == f"OpenRouter request failed: {error}"


def test_a_shape_failure_message_is_byte_identical_to_todays():
    with pytest.raises(OpenRouterError) as exc_info:
        call_openrouter(
            [Message("user", "hi")], api_key="k",
            client=_FakeClient(response=_response(body={"unexpected": "shape"})),
        )

    assert str(exc_info.value) == "OpenRouter returned an unexpected response shape: 'choices'"


def test_positional_construction_keeps_message_and_conservative_defaults():
    exc = OpenRouterError("x")

    assert str(exc) == "x"
    assert exc.args == ("x",)
    assert exc.upstream_status is None
    assert exc.retryable is False


# --- PRD-015 STORY-002: OPENROUTER_BASE_URL ---


def test_default_base_url_gives_todays_request_url():
    client = _FakeClient(response=_response())

    call_openrouter([Message("user", "hi")], api_key="k", client=client)

    assert client.requests[0]["url"] == "https://openrouter.ai/api/v1/chat/completions"


@pytest.mark.parametrize("base_url", ["http://127.0.0.1:9100/v1", "http://127.0.0.1:9100/v1/"])
def test_base_url_setting_redirects_the_request(monkeypatch, base_url):
    monkeypatch.setattr(settings, "OPENROUTER_BASE_URL", base_url)
    client = _FakeClient(response=_response())

    call_openrouter([Message("user", "hi")], api_key="k", client=client)

    assert client.requests[0]["url"] == "http://127.0.0.1:9100/v1/chat/completions"


def test_base_url_is_read_per_call_not_cached_at_import(monkeypatch):
    client = _FakeClient(response=_response())

    monkeypatch.setattr(settings, "OPENROUTER_BASE_URL", "http://127.0.0.1:9100/v1")
    call_openrouter([Message("user", "hi")], api_key="k", client=client)
    monkeypatch.setattr(settings, "OPENROUTER_BASE_URL", "http://localhost:9200/v1")
    call_openrouter([Message("user", "hi")], api_key="k", client=client)

    assert [r["url"] for r in client.requests] == [
        "http://127.0.0.1:9100/v1/chat/completions",
        "http://localhost:9200/v1/chat/completions",
    ]


# --- PRD-017 STORY-004: tool calls upstream ---

_TOOLS = [{"type": "function", "function": {"name": "bash", "parameters": {"type": "object"}}}]
_NASTY_ARGS = '{"p":"C:\\\\x\\n", "email":"a@b.co"} '
_SHAPE = "OpenRouter returned an unexpected response shape: "


def _tool_call_response(content, tool_calls, finish_reason="tool_calls", usage=None):
    request = httpx.Request("POST", _API_URL)
    message = {"content": content}
    if tool_calls is not ...:
        message["tool_calls"] = tool_calls
    payload = {
        "choices": [{"message": message, "finish_reason": finish_reason}],
        "usage": usage or {"total_tokens": 12, "prompt_tokens": 7, "completion_tokens": 5},
    }
    return httpx.Response(200, request=request, json=payload)


def _entry(call_id="call_1", name="bash", arguments='{"command":"ls"}', **extra):
    entry = {"id": call_id, "type": "function", "function": {"name": name, "arguments": arguments}}
    entry.update(extra)
    return entry


def _send(client, tools=ToolParams(tools=_TOOLS), messages=None):
    return call_openrouter(messages or [Message("user", "hi")], "m", "k", client=client, tools=tools)


def test_tool_params_reach_the_payload_exactly_as_given():
    client = _FakeClient(response=_response())
    tp = ToolParams(tools=_TOOLS, tool_choice="auto", parallel_tool_calls=False)

    call_openrouter([Message("user", "hi")], "gpt-4", "k", client=client, tools=tp)

    payload = client.requests[0]["json"]
    expected = {
        "model": "gpt-4",
        "messages": [{"role": "user", "content": "hi"}],
        "tools": _TOOLS,
        "tool_choice": "auto",
        "parallel_tool_calls": False,
    }
    assert json.dumps(payload, sort_keys=False) == json.dumps(expected, sort_keys=False)
    assert payload["tools"] is tp.tools
    assert payload["parallel_tool_calls"] is False


@pytest.mark.parametrize(
    "choice",
    ["none", "auto", "required", {"type": "function", "function": {"name": "bash"}}],
)
def test_each_tool_choice_form_is_sent_as_given(choice):
    client = _FakeClient(response=_response())

    _send(client, ToolParams(tools=_TOOLS, tool_choice=choice))

    assert client.requests[0]["json"]["tool_choice"] == choice


def test_a_none_tool_field_is_not_sent():
    client = _FakeClient(response=_response())

    _send(client, ToolParams(tools=_TOOLS))

    payload = client.requests[0]["json"]
    assert "tool_choice" not in payload
    assert "parallel_tool_calls" not in payload
    assert payload["tools"] == _TOOLS


def test_without_tools_the_payload_is_byte_identical_to_a_recorded_one():
    client = _FakeClient(response=_response())
    messages = [Message("system", "be brief"), Message("user", "hi"), Message("assistant", "hello")]

    call_openrouter(
        messages, "gpt-4", "k", params=GenerationParams(temperature=0.2, stop=["x"]), client=client
    )

    recorded = (
        '{"model": "gpt-4", "messages": [{"role": "system", "content": "be brief"}, '
        '{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}], '
        '"temperature": 0.2, "stop": ["x"]}'
    )
    assert json.dumps(client.requests[0]["json"], sort_keys=False) == recorded


def test_tools_is_keyword_only():
    client = _FakeClient(response=_response())

    with pytest.raises(TypeError):
        call_openrouter([Message("user", "hi")], "m", "k", None, client, ToolParams(tools=_TOOLS))


def test_generation_params_still_refuse_tools():
    # PRD-010 T5: ToolParams is its own keyword, the allowlist did not widen.
    with pytest.raises(UnsupportedParameterError, match="tools"):
        GenerationParams.from_mapping({"tools": []})


def test_assistant_tool_call_turn_serializes_with_null_content():
    client = _FakeClient(response=_response())
    msgs = [
        Message("user", "ls"),
        Message("assistant", "", (ToolCallSpec("call_1", "bash", '{"command":"ls"}'),)),
    ]

    call_openrouter(msgs, "m", "k", client=client)

    wire = client.requests[0]["json"]["messages"][1]
    expected = (
        '{"role": "assistant", "content": null, "tool_calls": [{"id": "call_1", '
        '"type": "function", "function": {"name": "bash", "arguments": "{\\"command\\":\\"ls\\"}"}}]}'
    )
    assert json.dumps(wire, sort_keys=False) == expected


def test_assistant_tool_call_turn_keeps_its_content_string():
    client = _FakeClient(response=_response())
    msgs = [Message("assistant", "thinking", (ToolCallSpec("call_1", "bash", "{}"),))]

    call_openrouter(msgs, "m", "k", client=client)

    assert client.requests[0]["json"]["messages"][0]["content"] == "thinking"


def test_tool_turn_serializes_with_tool_call_id_before_content():
    client = _FakeClient(response=_response())

    call_openrouter([Message("tool", "app.db", tool_call_id="call_1")], "m", "k", client=client)

    wire = client.requests[0]["json"]["messages"][0]
    assert json.dumps(wire, sort_keys=False) == (
        '{"role": "tool", "tool_call_id": "call_1", "content": "app.db"}'
    )


def test_arguments_string_is_sent_byte_for_byte():
    client = _FakeClient(response=_response())
    spec = ToolCallSpec("call_1", "bash", _NASTY_ARGS)

    call_openrouter([Message("assistant", "", (spec,))], "m", "k", client=client)

    sent = client.requests[0]["json"]["messages"][0]["tool_calls"][0]["function"]["arguments"]
    assert sent == _NASTY_ARGS
    assert sent is spec.arguments


def test_empty_assistant_turn_without_calls_keeps_empty_string_content():
    client = _FakeClient(response=_response())

    call_openrouter([Message("assistant", "")], "m", "k", client=client)

    assert client.requests[0]["json"]["messages"][0] == {"role": "assistant", "content": ""}


def test_null_content_with_calls_parses_to_empty_response_and_ordered_calls():
    client = _FakeClient(
        response=_tool_call_response(
            None, [_entry("call_1", "bash", _NASTY_ARGS), _entry("call_2", "read", "{}")]
        )
    )

    result = _send(client)

    assert result.response == ""
    assert result.tool_calls == (
        ToolCallSpec("call_1", "bash", _NASTY_ARGS),
        ToolCallSpec("call_2", "read", "{}"),
    )
    assert result.tool_calls[0].arguments == _NASTY_ARGS
    assert result.finish_reason == "tool_calls"


def test_text_with_calls_keeps_both():
    client = _FakeClient(response=_tool_call_response("let me look", [_entry()]))

    result = _send(client)

    assert result.response == "let me look"
    assert len(result.tool_calls) == 1


@pytest.mark.parametrize("variant", ["absent", "null"])
def test_a_call_without_a_type_is_accepted(variant):
    entry = _entry()
    if variant == "absent":
        del entry["type"]
    else:
        entry["type"] = None
    client = _FakeClient(response=_tool_call_response(None, [entry]))

    assert _send(client).tool_calls == (ToolCallSpec("call_1", "bash", '{"command":"ls"}'),)


def test_usage_and_split_are_read_on_a_tool_call_response():
    client = _FakeClient(response=_tool_call_response(None, [_entry()]))

    result = _send(client)

    assert (result.tokens_used, result.input_tokens, result.output_tokens) == (12, 7, 5)


def test_a_tool_call_response_without_usage_total_still_fails():
    client = _FakeClient(response=_tool_call_response(None, [_entry()], usage={"prompt_tokens": 1}))

    with pytest.raises(OpenRouterError, match="unexpected response shape"):
        _send(client)


def test_tools_sent_and_no_tool_calls_key_returns_text_without_calls():
    client = _FakeClient(response=_tool_call_response("hi", ..., finish_reason="stop"))

    result = _send(client)

    assert result.response == "hi"
    assert result.tool_calls == ()


def test_tools_sent_and_empty_tool_calls_returns_text_without_calls():
    client = _FakeClient(response=_tool_call_response("hi", [], finish_reason="stop"))

    assert _send(client).tool_calls == ()


def test_tools_sent_and_null_content_with_null_tool_calls_is_the_no_text_error():
    client = _FakeClient(response=_tool_call_response(None, None, finish_reason="stop"))

    with pytest.raises(OpenRouterError, match=r"returned no text content \(finish_reason=stop\)") as exc_info:
        _send(client)

    assert "PRD-017" not in str(exc_info.value)


def test_empty_tool_calls_with_null_content_is_an_error_and_keeps_the_d18_note():
    # Pinned on purpose (PRD-017 D18): the no-text branch is byte-identical, so
    # its note condition (tool_calls is not None) also fires for [] under tools=.
    client = _FakeClient(response=_tool_call_response(None, [], finish_reason="stop"))

    with pytest.raises(OpenRouterError, match=r"tool calls are not supported \(PRD-017\)"):
        _send(client)


def test_tool_calls_without_tools_sent_keep_the_d18_error_exactly():
    client = _FakeClient(response=_tool_call_response(None, [_entry()]))

    with pytest.raises(OpenRouterError) as exc_info:
        call_openrouter([Message("user", "hi")], "m", "k", client=client)

    assert str(exc_info.value) == (
        "OpenRouter returned no text content (finish_reason=tool_calls); "
        "tool calls are not supported (PRD-017)"
    )
    assert exc_info.value.retryable is False


def test_text_with_calls_without_tools_sent_ignores_the_calls():
    client = _FakeClient(response=_tool_call_response("hi", [_entry()]))

    result = call_openrouter([Message("user", "hi")], "m", "k", client=client)

    assert result.response == "hi"
    assert result.tool_calls == ()


@pytest.mark.parametrize(
    "calls, path",
    [
        ({}, "choices[0].message.tool_calls is not a list"),
        ("x", "choices[0].message.tool_calls is not a list"),
        (["x"], "choices[0].message.tool_calls[0] is not an object"),
        ([{"type": "function", "function": {"name": "a", "arguments": "{}"}}], "tool_calls[0].id must be a non-empty string"),
        ([_entry(call_id="")], "tool_calls[0].id must be a non-empty string"),
        ([_entry(call_id=7)], "tool_calls[0].id must be a non-empty string"),
        ([_entry(type="custom")], 'tool_calls[0].type must be "function"'),
        ([_entry(type="")], 'tool_calls[0].type must be "function"'),
        ([{"id": "c", "type": "function"}], "tool_calls[0].function is not an object"),
        ([{"id": "c", "type": "function", "function": "bash"}], "tool_calls[0].function is not an object"),
        ([_entry(name="")], "tool_calls[0].function.name must be a non-empty string"),
        ([{"id": "c", "function": {"arguments": "{}"}}], "tool_calls[0].function.name must be a non-empty string"),
        ([_entry(arguments={"command": "ls"})], "tool_calls[0].function.arguments must be a string"),
        ([_entry(arguments=None)], "tool_calls[0].function.arguments must be a string"),
        ([_entry(arguments=3)], "tool_calls[0].function.arguments must be a string"),
        ([{"id": "c", "function": {"name": "a"}}], "tool_calls[0].function.arguments must be a string"),
        ([_entry("dup"), _entry("dup")], "tool_calls[1].id repeats an earlier id in this response"),
    ],
)
def test_malformed_tool_calls_are_a_non_retryable_shape_error(calls, path):
    client = _FakeClient(response=_tool_call_response(None, calls))

    with pytest.raises(OpenRouterError) as exc_info:
        _send(client)

    assert str(exc_info.value).startswith(_SHAPE)
    assert path in str(exc_info.value)
    assert exc_info.value.retryable is False
    assert exc_info.value.upstream_status is None


def test_a_shape_error_never_contains_a_value():
    secret = "SENTINEL-secret-value"
    cases = [
        [_entry(call_id=secret, type=secret)],
        [_entry(name=secret, arguments={"k": secret})],
        [_entry(secret, "n", secret), _entry(secret, "n", secret)],
    ]
    for calls in cases:
        client = _FakeClient(response=_tool_call_response(None, calls))
        with pytest.raises(OpenRouterError) as exc_info:
            _send(client)
        assert secret not in str(exc_info.value)
