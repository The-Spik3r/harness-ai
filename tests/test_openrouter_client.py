import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import httpx
import pytest

from app.config import settings
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

    result = call_openrouter("hello", model="gpt-4", api_key="req-key", client=client)

    assert result.response == "Hello!"
    assert result.model_used == "gpt-4"
    assert result.tokens_used == 45


def test_default_model_used_when_omitted():
    client = _FakeClient(response=_response())

    result = call_openrouter("hello", api_key="req-key", client=client)

    assert result.model_used == "gpt-4"
    assert client.requests[0]["json"]["model"] == "gpt-4"


def test_per_request_api_key_overrides_env(monkeypatch):
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "env-key")
    client = _FakeClient(response=_response())

    call_openrouter("hello", api_key="explicit-key", client=client)

    assert client.requests[0]["headers"]["Authorization"] == "Bearer explicit-key"


def test_falls_back_to_env_key_when_not_provided(monkeypatch):
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "env-key")
    client = _FakeClient(response=_response())

    call_openrouter("hello", client=client)

    assert client.requests[0]["headers"]["Authorization"] == "Bearer env-key"


def test_missing_key_raises_config_error(monkeypatch):
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "")

    with pytest.raises(OpenRouterError, match="not configured"):
        call_openrouter("hello", client=_FakeClient())


def test_network_error_raises_openrouter_error():
    client = _FakeClient(exc=httpx.ConnectTimeout("timed out"))

    with pytest.raises(OpenRouterError):
        call_openrouter("hello", api_key="k", client=client)


def test_non_2xx_status_raises_openrouter_error():
    client = _FakeClient(response=_response(status_code=500))

    with pytest.raises(OpenRouterError):
        call_openrouter("hello", api_key="k", client=client)


def test_malformed_response_body_raises_openrouter_error():
    client = _FakeClient(response=_response(body={"unexpected": "shape"}))

    with pytest.raises(OpenRouterError):
        call_openrouter("hello", api_key="k", client=client)


def test_api_key_never_appears_in_error_message():
    client = _FakeClient(exc=httpx.ConnectTimeout("timed out"))

    with pytest.raises(OpenRouterError) as exc_info:
        call_openrouter("hello", api_key="super-secret-key", client=client)

    assert "super-secret-key" not in str(exc_info.value)
