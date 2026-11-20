"""PRD-022 STORY-001: facts about the pinned `anthropic` SDK, observed offline.

A spike's findings, kept as tests so an SDK bump that changes one fails here
instead of in the adapter STORY-003 builds on them. Everything runs against
`http.server` stubs on 127.0.0.1 with ports picked by the OS: no real network,
no database, no sleeping (servers answer inline and are shut down in the
fixture finalizer; every thread is joined with a timeout).

    AC 1  the breaker API PRD-022 reuses (probe=None, record_failure takes only
          a failure class, so a per-call open time is NOT available)
    AC 3  the pin, and the redirect behaviour of the SDK's default client versus
          a no-redirect client (the PRD-020 D5 rule)
    AC 4  wire vocabulary: stop reasons, deltas, usage, thinking, exceptions,
          the retry-after header

The facts asserted are what the installed SDK does, not what PRD-022 Section
6.5 assumed; where they differ (Authorization: Bearer rather than x-api-key,
redirects followed by default) the test name says so.
"""

import inspect
import json
import re
import threading
import typing
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import anthropic
import pytest

from app.services.circuit_breaker import CircuitBreaker

_REPO_ROOT = Path(__file__).resolve().parents[1]
_KEY = "sk-ant-spike-KEY"

_MESSAGE = {
    "id": "msg_01",
    "type": "message",
    "role": "assistant",
    "model": "claude-spike",
    "content": [{"type": "text", "text": "ok"}],
    "stop_reason": "end_turn",
    "stop_sequence": None,
    "usage": {"input_tokens": 1, "output_tokens": 1},
}


class _Stub:
    """One localhost server. `responder(handler)` answers every request."""

    def __init__(self, responder):
        self.requests = []  # (method, path, lower-cased header dict)
        outer = self

        class _Handler(BaseHTTPRequestHandler):
            def _handle(self):
                length = int(self.headers.get("content-length") or 0)
                if length:
                    self.rfile.read(length)
                outer.requests.append(
                    (self.command, self.path, {k.lower(): v for k, v in self.headers.items()})
                )
                responder(self)

            do_GET = do_POST = _handle

            def log_message(self, *args):  # keep the test output clean
                pass

        self._server = HTTPServer(("127.0.0.1", 0), _Handler)
        self.port = self._server.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def close(self):
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)


def _reply(handler, status, body=None, headers=None):
    payload = json.dumps(body if body is not None else _MESSAGE).encode()
    handler.send_response(status)
    handler.send_header("content-type", "application/json")
    handler.send_header("content-length", str(len(payload)))
    for name, value in (headers or {}).items():
        handler.send_header(name, value)
    handler.end_headers()
    handler.wfile.write(payload)


@pytest.fixture
def stubs():
    made = []

    def make(responder):
        stub = _Stub(responder)
        made.append(stub)
        return stub

    yield make
    for stub in made:
        stub.close()


def _create(client):
    return client.messages.create(
        model="claude-spike", max_tokens=1, messages=[{"role": "user", "content": "hi"}]
    )


def _client(base_url, **kwargs):
    kwargs.setdefault("max_retries", 0)
    kwargs.setdefault("timeout", 5.0)
    return anthropic.Anthropic(api_key=_KEY, base_url=base_url, **kwargs)


# --- AC 3: pin ---------------------------------------------------------------


def test_sdk_is_importable_at_the_pinned_version():
    text = (_REPO_ROOT / "requirements.txt").read_text(encoding="utf-8")
    pins = re.findall(r"^anthropic==(\S+)\s*$", text, flags=re.MULTILINE)
    assert pins == [anthropic.__version__]


def test_client_accepts_max_retries_zero_and_explicit_timeout():
    client = _client("http://127.0.0.1:9", max_retries=0, timeout=3.5)
    assert client.max_retries == 0
    assert client.timeout == 3.5


def test_sdk_runs_on_httpx2_not_the_harness_httpx():
    # The SDK's own client is httpx2's; the harness's PRD-020 client is httpx's.
    import httpx
    import httpx2

    assert issubclass(anthropic.DefaultHttpxClient, httpx2.Client)
    assert not issubclass(anthropic.DefaultHttpxClient, httpx.Client)


# --- AC 3: redirects ---------------------------------------------------------


def _redirecting(stubs, status):
    """(origin stub redirecting to `target`, target stub answering a valid message)."""
    target = stubs(lambda h: _reply(h, 200))
    origin = stubs(
        lambda h: (
            h.send_response(status),
            h.send_header("location", f"{target.url}/v1/messages"),
            h.send_header("content-length", "0"),
            h.end_headers(),
        )
    )
    return origin, target


@pytest.mark.parametrize("status", [307, 302])
def test_default_client_follows_redirects_but_not_the_key_cross_origin(stubs, status):
    origin, target = _redirecting(stubs, status)
    _create(_client(origin.url))  # the default client: the redirect is followed
    assert len(origin.requests) == 1
    assert len(target.requests) == 1, "observed: the default client follows the redirect"
    first, second = origin.requests[0][2], target.requests[0][2]
    assert first.get("authorization") == f"Bearer {_KEY}"
    # httpx2 strips Authorization when the origin (host:port) changes.
    assert "authorization" not in second
    assert "x-api-key" not in second
    # 302 turns the POST into a GET; 307 keeps the method.
    assert target.requests[0][0] == ("POST" if status == 307 else "GET")


def test_default_client_keeps_the_key_on_a_same_origin_redirect(stubs):
    seen = []

    def responder(handler):
        seen.append(handler.path)
        if handler.path == "/v1/messages":
            handler.send_response(307)
            handler.send_header("location", "/elsewhere")
            handler.send_header("content-length", "0")
            handler.end_headers()
        else:
            _reply(handler, 200)

    stub = stubs(responder)
    _create(_client(stub.url))
    assert seen == ["/v1/messages", "/elsewhere"]
    assert stub.requests[1][2].get("authorization") == f"Bearer {_KEY}"


@pytest.mark.parametrize("status", [307, 302])
def test_no_redirect_client_surfaces_the_30x_as_api_status_error(stubs, status):
    origin, target = _redirecting(stubs, status)
    client = _client(
        origin.url, http_client=anthropic.DefaultHttpxClient(follow_redirects=False)
    )
    with pytest.raises(anthropic.APIStatusError) as caught:
        _create(client)
    assert caught.value.status_code == status
    assert target.requests == [], "the second server saw no request"
    assert len(origin.requests) == 1


def test_the_credential_header_is_authorization_bearer_not_x_api_key(stubs):
    # PRD-022 Section 6.5 says x-api-key; this SDK version sends a bearer token.
    stub = stubs(lambda h: _reply(h, 200))
    _create(_client(stub.url))
    headers = stub.requests[0][2]
    assert headers.get("authorization") == f"Bearer {_KEY}"
    assert "x-api-key" not in headers
    assert headers.get("anthropic-version") == anthropic._constants.ANTHROPIC_API_VERSION


# --- AC 4: exceptions and retry-after ----------------------------------------


@pytest.mark.parametrize(
    "status, cls",
    [
        (400, anthropic.BadRequestError),
        (401, anthropic.AuthenticationError),
        (403, anthropic.PermissionDeniedError),
        (404, anthropic.NotFoundError),
        (429, anthropic.RateLimitError),
        (500, anthropic.InternalServerError),
        (503, anthropic.ServiceUnavailableError),
        (504, anthropic.GatewayTimeoutError),
        (529, anthropic.OverloadedError),
    ],
)
def test_exception_hierarchy_and_status_codes(stubs, status, cls):
    stub = stubs(lambda h: _reply(h, status, {"type": "error", "error": {"type": "e", "message": "m"}}))
    with pytest.raises(anthropic.APIStatusError) as caught:
        _create(_client(stub.url))
    assert type(caught.value) is cls
    assert caught.value.status_code == status
    assert issubclass(cls, anthropic.APIError) and issubclass(anthropic.APIError, anthropic.AnthropicError)
    if status >= 500:
        assert isinstance(caught.value, anthropic.InternalServerError)


def test_timeout_is_a_connection_error_so_catch_it_first():
    assert issubclass(anthropic.APITimeoutError, anthropic.APIConnectionError)
    assert issubclass(anthropic.APIConnectionError, anthropic.APIError)
    assert not issubclass(anthropic.APIConnectionError, anthropic.APIStatusError)


def test_rate_limit_error_exposes_retry_after_through_response_headers(stubs):
    stub = stubs(
        lambda h: _reply(
            h, 429, {"type": "error", "error": {"type": "rate_limit_error", "message": "m"}},
            headers={"retry-after": "7", "request-id": "req_spike"},
        )
    )
    with pytest.raises(anthropic.RateLimitError) as caught:
        _create(_client(stub.url))
    assert caught.value.response.headers.get("retry-after") == "7"
    assert caught.value.status_code == 429
    assert caught.value.request_id == "req_spike"
    assert not hasattr(caught.value, "retry_after")  # not a typed attribute


# --- AC 4: wire vocabulary ---------------------------------------------------


def test_wire_vocabulary_literals():
    from anthropic.types import (
        CitationsDelta,
        InputJSONDelta,
        MessageDeltaUsage,
        RawMessageStreamEvent,
        SignatureDelta,
        StopReason,
        TextDelta,
        ThinkingConfigAdaptiveParam,
        ThinkingDelta,
        Usage,
    )

    # One more than PRD-022 Section 6.5 lists: model_context_window_exceeded.
    assert typing.get_args(StopReason) == (
        "end_turn", "max_tokens", "stop_sequence", "tool_use", "pause_turn", "refusal",
        "model_context_window_exceeded",
    )
    assert "display" in ThinkingConfigAdaptiveParam.__annotations__
    deltas = {
        cls: typing.get_args(cls.model_fields["type"].annotation)
        for cls in (TextDelta, InputJSONDelta, CitationsDelta, ThinkingDelta, SignatureDelta)
    }
    assert sorted(v[0] for v in deltas.values()) == [
        "citations_delta", "input_json_delta", "signature_delta", "text_delta", "thinking_delta",
    ]
    assert "partial_json" in InputJSONDelta.model_fields
    events = typing.get_args(typing.get_args(RawMessageStreamEvent)[0])
    assert sorted(typing.get_args(e.model_fields["type"].annotation)[0] for e in events) == [
        "content_block_delta", "content_block_start", "content_block_stop",
        "message_delta", "message_start", "message_stop",
    ]
    for usage in (Usage, MessageDeltaUsage):
        assert {"cache_creation_input_tokens", "cache_read_input_tokens"} <= set(usage.model_fields)


# --- AC 1: the breaker PRD-022 reuses ----------------------------------------


def test_breaker_api_shape_for_prd022():
    init = inspect.signature(CircuitBreaker.__init__).parameters
    assert list(init)[1:] == [
        "name", "failure_threshold", "open_seconds", "clock", "probe", "on_transition",
    ]
    assert init["probe"].default is None
    # No per-call open time: the 429 rule max(retry_after, 10) needs force_open.
    assert list(inspect.signature(CircuitBreaker.record_failure).parameters)[1:] == ["failure_class"]
    assert list(inspect.signature(CircuitBreaker.force_open).parameters)[1:] == ["seconds"]
    assert list(inspect.signature(CircuitBreaker.record_success).parameters)[1:] == []


def test_force_open_can_shorten_an_open_window_and_leaves_no_failure_count():
    now = [0.0]
    breaker = CircuitBreaker("p", 3, 300.0, clock=lambda: now[0])
    breaker.force_open(10)  # closed -> open; the transition log says class=forced
    status = breaker.status()
    # Observed: the forced open leaves the failure count and class untouched.
    assert (status.state, status.consecutive_failures, status.last_failure_class) == ("open", 0, None)
    breaker.force_open(300)
    assert breaker.status().retry_after_seconds == 300
    breaker.force_open(10)  # an open breaker is overwritten, so the window shrank
    assert breaker.status().retry_after_seconds == 10
