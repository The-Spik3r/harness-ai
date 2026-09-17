import json
import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import httpx
import pytest

from app.config import settings
from app.models.messages import Message
from app.services.openrouter_client import (
    OpenRouterError,
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
    """AC 3: today's value (30.0). STORY-005 changes this deliberately,
    citing PRD-010 at that point."""
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

    assert captured["kwargs"] == {"timeout": 30.0}


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
