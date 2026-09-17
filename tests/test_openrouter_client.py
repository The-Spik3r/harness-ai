import json
import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import httpx
import pytest

from app.config import settings
from app.models.messages import Message
from app.services.openrouter_client import (
    GenerationParams,
    OpenRouterError,
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

    assert captured["kwargs"] == {"timeout": 120.0}  # PRD-010 STORY-005: timeout from settings (default 120.0)


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

    assert captured["kwargs"] == {"timeout": 7.5}


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


def test_null_content_with_tool_calls_names_prd_016():
    client = _FakeClient(
        response=_null_content_response(finish_reason="tool_calls", tool_calls=[{"id": "1"}])
    )

    with pytest.raises(OpenRouterError, match=r"tool calls are not supported \(PRD-016\)"):
        call_openrouter([Message("user", "hi")], api_key="k", client=client)


def test_null_content_without_tool_calls_omits_prd_016_note():
    client = _FakeClient(response=_null_content_response(finish_reason="stop"))

    with pytest.raises(OpenRouterError) as exc_info:
        call_openrouter([Message("user", "hi")], api_key="k", client=client)

    assert "PRD-016" not in str(exc_info.value)


def test_null_content_error_never_contains_api_key():
    client = _FakeClient(response=_null_content_response())

    with pytest.raises(OpenRouterError) as exc_info:
        call_openrouter([Message("user", "hi")], api_key="super-secret-key", client=client)

    assert "super-secret-key" not in str(exc_info.value)
