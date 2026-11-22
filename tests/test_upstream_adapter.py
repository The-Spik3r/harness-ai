"""PRD-020 STORY-005: the upstream package, the OpenAI-compatible adapter, call_upstream.

    AC1  shim aliases, the app imports, injected `(messages, model, api_key, **kw)` stubs
    AC2  two stubs, two providers: each gets only its own key, `auth=yes|no`
    AC3  `httpx.Client(timeout=..., follow_redirects=False)`; a 3xx is an error, not followed
    AC4  provider labels in error strings (T7)
    AC5  D10 key choice; the legacy missing-key message

The legacy byte-for-byte replay is `tests/test_prd020_legacy_fixtures.py`.
"""

import inspect
import io
import json
import os
import threading
from pathlib import Path

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import httpx
import pytest

from app.config import settings
from app.models.messages import Message
from app.services import openrouter_client, provider_registry, upstream
from app.services.upstream import UpstreamError, UpstreamRequest, UpstreamResult, call_upstream
from app.services.upstream import params as upstream_params
from scripts.stub_openrouter import make_server, parse_script
from tests._providers import provider_file  # noqa: F401  (fixture)

_REPO = Path(__file__).resolve().parent.parent
_KEY_A = "sk-test-key-AAAA"
_KEY_B = "sk-test-key-BBBB"
_MSG = [Message("user", "hello")]


class _FakeClient:
    def __init__(self, response=None, exc=None):
        self._response, self._exc, self.requests = response, exc, []

    def post(self, url, headers=None, json=None):
        self.requests.append({"url": url, "headers": headers, "json": json})
        if self._exc:
            raise self._exc
        return self._response


def _response(status=200, body=None, headers=None):
    request = httpx.Request("POST", "http://127.0.0.1:1/v1/chat/completions")
    payload = body if body is not None else {
        "choices": [{"message": {"content": "ok"}}],
        "usage": {"total_tokens": 3},
    }
    return httpx.Response(status, request=request, json=payload, headers=headers)


@pytest.fixture(autouse=True)
def _remote_key_env(monkeypatch):
    """The file's `key_env` must be set at load (PRD-020 F3); tests override it via `env=`."""
    monkeypatch.setenv("REMOTE_KEY_ENV", _KEY_A)


@pytest.fixture
def stubs():
    """Factory: (port, log) for a stub, optionally requiring a key; stopped at teardown."""
    started = []

    def start(script=None, require_key=None):
        log = io.StringIO()
        server = make_server(
            parse_script(script or {"rules": [], "default": {"content": "pong"}}),
            log=log,
            require_key=require_key,
        )
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        thread.start()
        started.append((server, thread))
        return server.server_address[1], log

    yield start
    for server, thread in started:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _yaml(local_port, remote_port=None, *, byok=True):
    """`remote` is keyed (REMOTE_KEY_ENV), `local` has no key_env; both on loopback http."""
    return f"""
version: 1
default_model: remote/m
providers:
  - name: remote
    label: Remote
    type: openai_compatible
    base_url: http://127.0.0.1:{remote_port or local_port}/v1
    insecure_http: true
    key_env: REMOTE_KEY_ENV
    byok: {str(byok).lower()}
    models:
      - id: remote/m
        upstream: up-remote
  - name: local
    label: Local
    type: openai_compatible
    base_url: http://127.0.0.1:{local_port}/v1
    insecure_http: true
    models:
      - id: local/m
        upstream: up-local
"""


# --- AC1 -----------------------------------------------------------------------


def test_shim_is_aliases_only():
    assert openrouter_client.call_openrouter is call_upstream
    assert openrouter_client.OpenRouterError is UpstreamError
    assert openrouter_client.OpenRouterResult is UpstreamResult
    for name in ("GenerationParams", "ToolParams", "UnsupportedParameterError"):
        assert getattr(openrouter_client, name) is getattr(upstream_params, name)
        assert getattr(upstream, name) is getattr(upstream_params, name)


def test_call_upstream_keeps_call_openrouters_signature():
    sig = inspect.signature(call_upstream)
    # PRD-022 STORY-011 (F5): `timeout` joins as a keyword-only parameter; the positional ones are unchanged.
    assert list(sig.parameters) == ["messages", "model", "api_key", "params", "client", "tools", "timeout"]
    assert sig.parameters["timeout"].kind is inspect.Parameter.KEYWORD_ONLY and sig.parameters["timeout"].default is None
    assert sig.parameters["model"].default == "gpt-4"
    assert sig.parameters["tools"].kind is inspect.Parameter.KEYWORD_ONLY


def test_no_app_module_imports_the_shim():
    offenders = [
        str(p.relative_to(_REPO))
        for p in (_REPO / "app").rglob("*.py")
        if p.name != "openrouter_client.py" and "openrouter_client" in p.read_text(encoding="utf-8")
    ]
    assert offenders == []


def test_app_modules_keep_their_names_bound_to_the_package():
    from app.routers import query, v1
    from app.services import query_pipeline, v1_translate

    for module in (query, v1, query_pipeline):
        assert module.call_openrouter is call_upstream
        assert module.OpenRouterError is UpstreamError
    assert v1.OpenRouterResult is UpstreamResult
    assert v1_translate.OpenRouterResult is UpstreamResult
    # The default of run_query's injected callable is the bound alias, so a
    # (messages, model, api_key, **kw) stub still replaces it (PRD-020 D12).
    default = inspect.signature(query_pipeline.run_query).parameters["call_openrouter"].default
    assert default is query_pipeline.call_openrouter


# --- AC2 -----------------------------------------------------------------------


def test_two_stubs_each_get_only_their_own_key(stubs, provider_file, capfd):
    remote_port, remote_log = stubs(require_key=_KEY_A)
    local_port, local_log = stubs()
    provider_file(_yaml(local_port, remote_port), env={"REMOTE_KEY_ENV": _KEY_A})

    remote = call_upstream(_MSG, model="remote/m")
    local = call_upstream(_MSG, model="local/m", api_key=_KEY_B)  # keyless: caller key ignored

    assert remote.response == local.response == "pong"
    assert (remote.model_used, local.model_used) == ("remote/m", "local/m")
    assert remote_log.getvalue().strip().endswith("-> 200") and " auth=yes " in remote_log.getvalue()
    assert local_log.getvalue().strip().endswith("-> 200") and " auth=no " in local_log.getvalue()
    # A swapped key is refused by the stub's own comparison.
    with pytest.raises(UpstreamError) as excinfo:
        call_upstream(_MSG, model="remote/m", api_key=_KEY_B)
    assert excinfo.value.upstream_status == 401
    out = capfd.readouterr()
    for text in (remote_log.getvalue(), local_log.getvalue(), out.out, out.err, str(excinfo.value)):
        assert _KEY_A not in text and _KEY_B not in text and "Bearer" not in text


def test_upstream_model_goes_on_the_wire_and_model_used_is_the_requested_id(provider_file):
    provider_file(_yaml(1))
    client = _FakeClient(response=_response())
    result = call_upstream(_MSG, model="local/m", client=client)
    assert client.requests[0]["json"]["model"] == "up-local"
    assert result.model_used == "local/m"


def test_keyless_provider_sends_no_authorization_header(provider_file):
    provider_file(_yaml(1))
    client = _FakeClient(response=_response())
    call_upstream(_MSG, model="local/m", api_key=_KEY_A, client=client)
    assert list(client.requests[0]["headers"]) == ["Content-Type"]


# --- AC3 -----------------------------------------------------------------------


def test_default_client_kwargs(provider_file, monkeypatch):
    provider_file(_yaml(1))
    captured = {}

    class _Spy:
        def __init__(self, *args, **kwargs):
            captured["kwargs"] = kwargs

        def post(self, url, headers=None, json=None):
            return _response()

        def close(self):
            captured["closed"] = True

    monkeypatch.setattr(httpx, "Client", _Spy)
    call_upstream(_MSG, model="local/m")
    timeout = provider_registry.resolve("local/m").provider.timeout_seconds
    assert captured["kwargs"] == {"timeout": timeout, "follow_redirects": False}
    assert captured["closed"] is True


def test_302_is_a_non_retryable_error_and_not_followed(stubs, provider_file):
    target_port, target_log = stubs()
    location = f"http://127.0.0.1:{target_port}/v1/chat/completions"
    port, log = stubs({"rules": [], "default": {"redirect_status": 302, "location": location}})
    provider_file(_yaml(port))
    with pytest.raises(UpstreamError) as excinfo:
        call_upstream(_MSG, model="local/m")
    assert excinfo.value.retryable is False and excinfo.value.upstream_status == 302
    assert "Local request failed: unexpected redirect (HTTP 302)" in str(excinfo.value)
    assert str(target_port) not in str(excinfo.value)  # the Location is never quoted
    assert len(log.getvalue().strip().splitlines()) == 1
    assert target_log.getvalue() == ""


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_any_3xx_from_a_client_is_an_error(provider_file, status):
    provider_file(_yaml(1))
    client = _FakeClient(response=_response(status, headers={"Location": "http://elsewhere.invalid/"}))
    with pytest.raises(UpstreamError) as excinfo:
        call_upstream(_MSG, model="local/m", client=client)
    assert excinfo.value.upstream_status == status and excinfo.value.retryable is False
    assert "elsewhere" not in str(excinfo.value)


# --- AC4 -----------------------------------------------------------------------


def _local(provider_file, client, **kwargs):
    provider_file(_yaml(1))
    return call_upstream(_MSG, model="local/m", client=client, **kwargs)


def test_local_label_on_connect_failure_and_503(provider_file):
    with pytest.raises(UpstreamError, match=r"^Local request failed:") as excinfo:
        _local(provider_file, _FakeClient(exc=httpx.ConnectError("boom")))
    assert excinfo.value.retryable is True
    with pytest.raises(UpstreamError, match=r"^Local request failed:") as excinfo:
        _local(provider_file, _FakeClient(response=_response(503)))
    assert excinfo.value.upstream_status == 503 and excinfo.value.retryable is True


def test_local_label_on_shape_and_content_errors(provider_file):
    with pytest.raises(UpstreamError, match=r"^Local returned an unexpected response shape:"):
        _local(provider_file, _FakeClient(response=_response(body={"choices": []})))
    null_content = {"choices": [{"message": {"content": None}}], "usage": {"total_tokens": 1}}
    with pytest.raises(UpstreamError, match=r"^Local returned no text content"):
        _local(provider_file, _FakeClient(response=_response(body=null_content)))
    # PRD-020 D8 / STORY-009: a file provider defaults to `usage_missing: estimate`, so a
    # missing usage is estimated, not a shape error (the raise case, `usage_missing: error`,
    # is pinned in test_usage_estimate_adapter.py).
    no_usage = {"choices": [{"message": {"content": "x"}}]}
    result = _local(provider_file, _FakeClient(response=_response(body=no_usage)))
    assert result.usage_estimated is True


def test_local_label_on_bad_tool_calls(provider_file):
    body = {"choices": [{"message": {"content": None, "tool_calls": "nope"}}], "usage": {"total_tokens": 1}}
    tools = upstream.ToolParams(tools=[{"type": "function", "function": {"name": "f"}}])
    with pytest.raises(UpstreamError) as excinfo:
        _local(provider_file, _FakeClient(response=_response(body=body)), tools=tools)
    assert str(excinfo.value) == (
        "Local returned an unexpected response shape: choices[0].message.tool_calls is not a list"
    )


# --- AC5 -----------------------------------------------------------------------


def test_byok_key_only_for_byok_provider(provider_file):
    provider_file(_yaml(1), env={"REMOTE_KEY_ENV": _KEY_A})
    client = _FakeClient(response=_response())
    call_upstream(_MSG, model="remote/m", api_key=_KEY_B, client=client)
    assert client.requests[0]["headers"]["Authorization"] == f"Bearer {_KEY_B}"
    call_upstream(_MSG, model="remote/m", client=client)
    assert client.requests[1]["headers"]["Authorization"] == f"Bearer {_KEY_A}"


def test_non_byok_provider_ignores_the_caller_key(stubs, provider_file):
    port, log = stubs(require_key=_KEY_A)
    provider_file(_yaml(1, port, byok=False), env={"REMOTE_KEY_ENV": _KEY_A})
    assert call_upstream(_MSG, model="remote/m", api_key=_KEY_B).response == "pong"
    assert log.getvalue().strip().endswith("-> 200") and " auth=yes " in log.getvalue()


def test_missing_key_message_matches_errors_json(monkeypatch):
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "")
    expected = json.loads(
        (_REPO / "tests/fixtures/prd020_legacy/errors.json").read_text(encoding="utf-8")
    )["key_missing"]
    with pytest.raises(UpstreamError) as excinfo:
        call_upstream(_MSG, model="any-model", client=_FakeClient(response=_response()))
    assert str(excinfo.value) == expected["message"]
    assert excinfo.value.retryable is False and excinfo.value.upstream_status is None


def test_unroutable_model_is_a_non_retryable_error_without_key_or_url(provider_file):
    provider_file(_yaml(1))  # no passthrough provider: an uncatalogued id has no route
    with pytest.raises(UpstreamError) as excinfo:
        call_upstream(_MSG, model="unknown/model", api_key=_KEY_A, client=_FakeClient(response=_response()))
    assert str(excinfo.value) == "No provider route for the requested model"
    assert excinfo.value.retryable is False


def test_empty_messages_is_rejected_first():
    with pytest.raises(UpstreamError, match="messages must not be empty"):
        call_upstream([], model="m")


def test_no_key_value_appears_in_reprs_or_errors(provider_file, caplog):
    provider_file(_yaml(1), env={"REMOTE_KEY_ENV": _KEY_A})
    route = provider_registry.resolve("remote/m")
    with pytest.raises(UpstreamError) as excinfo:
        call_upstream(_MSG, model="remote/m", api_key=_KEY_B, client=_FakeClient(response=_response(500)))
    for text in (repr(route.provider), repr(route), str(excinfo.value), caplog.text):
        assert _KEY_A not in text and _KEY_B not in text


def test_stream_total_deadline_bounds_whole_stream(stubs):
    # PRD-021 D20: `timeout_seconds` bounds the whole stream, not each read. The
    # stub trickles one character every 50 ms (about 5 s in all); the httpx client
    # has a generous per-read timeout, so only the total deadline can stop it.
    import dataclasses
    import time

    from app.services.upstream import OpenAICompatibleAdapter, UpstreamRequest

    port, _ = stubs({"rules": [], "default": {"content": "x" * 100, "stream": {"chunk_chars": 1, "delay_ms": 50}}})
    provider = dataclasses.replace(
        provider_registry.current().providers[0],
        base_url=f"http://127.0.0.1:{port}/v1",
        timeout_seconds=0.4,
    )
    client = httpx.Client(timeout=10, follow_redirects=False)
    started = time.monotonic()
    try:
        with pytest.raises(UpstreamError) as excinfo:
            list(OpenAICompatibleAdapter(provider, client).stream(UpstreamRequest(_MSG, "up-model"), _KEY_A))
    finally:
        client.close()
    assert excinfo.value.retryable is True and excinfo.value.upstream_status is None
    assert "exceeded" in str(excinfo.value)
    assert time.monotonic() - started < 4  # well under the ~5 s the stream would take


# --- PRD-022 STORY-011: the per-attempt timeout keyword -----------------------------------


def test_timeout_keyword_reaches_the_client_and_unset_keeps_the_provider_timeout(provider_file, monkeypatch):
    provider_file(_yaml(1))
    seen = []

    class _Spy:
        def __init__(self, *args, **kwargs):
            seen.append(kwargs["timeout"])

        def post(self, url, headers=None, json=None):
            return _response()

        def close(self):
            pass

    monkeypatch.setattr(httpx, "Client", _Spy)
    call_upstream(_MSG, model="local/m", timeout=1.25)
    call_upstream(_MSG, model="local/m")
    assert seen == [1.25, provider_registry.resolve("local/m").provider.timeout_seconds]


def test_an_injected_client_gets_the_timeout_per_call_only_when_set(provider_file):
    provider_file(_yaml(1))

    class _Client(_FakeClient):
        def post(self, url, headers=None, json=None, **kwargs):
            self.requests.append({"kwargs": kwargs})
            return self._response

    client = _Client(_response())
    call_upstream(_MSG, model="local/m", client=client, timeout=2.0)
    call_upstream(_MSG, model="local/m", client=client)
    assert [r["kwargs"] for r in client.requests] == [{"timeout": 2.0}, {}]


def test_a_stub_without_the_timeout_keyword_is_untouched(provider_file):
    # The suite's stubs are (messages, model, api_key): the seam adds the keyword
    # to the request only; nothing here forces it on a caller.
    provider_file(_yaml(1))
    client = _FakeClient(_response())
    assert call_upstream(_MSG, model="local/m", client=client).response == "ok"
    assert UpstreamRequest(_MSG, "m").timeout_seconds is None


def test_stream_timeout_bounds_the_whole_stream(stubs):
    import dataclasses
    import time

    from app.services.upstream import OpenAICompatibleAdapter

    port, _ = stubs({"rules": [], "default": {"content": "x" * 100, "stream": {"chunk_chars": 1, "delay_ms": 50}}})
    provider = dataclasses.replace(
        provider_registry.current().providers[0],
        base_url=f"http://127.0.0.1:{port}/v1",
        timeout_seconds=30.0,
    )
    client = httpx.Client(timeout=10, follow_redirects=False)
    started = time.monotonic()
    try:
        with pytest.raises(UpstreamError) as excinfo:
            list(
                OpenAICompatibleAdapter(provider, client).stream(
                    UpstreamRequest(_MSG, "up-model", timeout_seconds=0.4), _KEY_A
                )
            )
    finally:
        client.close()
    assert excinfo.value.retryable is True and "exceeded 0.4s" in str(excinfo.value)
    assert time.monotonic() - started < 4
