"""PRD-015 STORY-016: the shared E2E plumbing in `tests/e2e/_live.py`.

The E2E modules only run with `--run-e2e`, so the pieces of the plumbing that
decide what an E2E run asserts are pinned here, in the everyday suite: the
mirrored parameter sets, the `ignored_params` rule, the request shape the
recording proxy keeps (names, never content), the proxy's relay, and the
database guard. Nothing here reaches storage.
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import json
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest

from app.services import v1_translate
from tests.e2e import _live


def _entry(keys, stream_options_keys=(), message_keys=("content", "role")) -> dict:
    return {"keys": sorted(keys), "stream_options_keys": sorted(stream_options_keys),
            "message_keys": sorted(message_keys)}


# --------------------------------------------------------------------------
# The mirrors and the ignored_params rule
# --------------------------------------------------------------------------


def test_the_mirrored_sets_equal_the_translator_s():
    assert _live.FORWARDED == v1_translate.FORWARDED
    assert _live.REJECTED_UNLESS_DEFAULT == frozenset(v1_translate.REJECTED_UNLESS_DEFAULT)
    assert _live.STRUCTURAL == v1_translate._STRUCTURAL
    assert _live.IGNORED_MESSAGE_NAME == v1_translate.IGNORED_MESSAGE_NAME


def test_aider_s_request_shape_ignores_nothing():
    """Aider 0.86.2 in `diff` mode sends exactly these keys (STORY-016 spike)."""
    assert _live.expected_ignored_params(_entry(["messages", "model", "stream", "temperature"])) is None


def test_ignored_names_are_sorted_and_comma_joined():
    entry = _entry(["model", "messages", "user", "seed", "temperature", "stream_options"],
                   stream_options_keys=["include_usage", "chunk_hint"], message_keys=["content", "name", "role"])
    assert _live.expected_ignored_params(entry) == "messages[].name,seed,stream_options.chunk_hint,user"


def test_a_rejected_unless_default_key_is_never_ignored():
    entry = _entry(["model", "messages", "tools", "tool_choice", "n"])
    assert _live.expected_ignored_params(entry) is None


def test_the_rule_matches_the_translator_on_one_request():
    body = {"model": "openai/gpt-4o", "messages": [{"role": "user", "content": "hi", "name": "me"}],
            "seed": 7, "stream": True, "stream_options": {"include_usage": True, "x": 1}, "tools": []}
    request = v1_translate.ChatCompletionRequest.model_validate(body)
    assert _live.expected_ignored_params(_live.request_shape(body)) == v1_translate.translate_request(request).ignored_params


# --------------------------------------------------------------------------
# request_shape: names, roles, model; never content
# --------------------------------------------------------------------------


def test_the_shape_keeps_names_roles_and_model_but_no_content():
    body = {
        "model": "openai/gpt-4o",
        "messages": [{"role": "system", "content": "SECRET-SYSTEM"}, {"role": "user", "content": "SECRET-USER"}],
        "stream": True,
        "temperature": 0,
        "tools": [{"type": "function", "function": {"name": "SECRET-TOOL"}}],
        "tool_choice": None,
    }
    shape = _live.request_shape(body)
    assert shape == {
        "keys": ["messages", "model", "stream", "temperature", "tool_choice", "tools"],
        "model": "openai/gpt-4o",
        "stream": True,
        "stream_options_keys": [],
        "roles": ["system", "user"],
        "message_keys": ["content", "role"],
        "tools": "non-empty",
        "tool_choice": "null",
        "functions": "absent",
    }
    assert "SECRET" not in json.dumps(shape)


def test_an_empty_tools_list_is_its_own_shape():
    assert _live.request_shape({"tools": []})["tools"] == "[]"


# --------------------------------------------------------------------------
# Recorder: records the shape, relays status, headers and body unchanged
# --------------------------------------------------------------------------


class _Upstream(BaseHTTPRequestHandler):
    #: X-Harness-Device values this upstream received, in order.
    devices: list = []

    def log_message(self, *args):
        pass

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        _Upstream.devices.append(self.headers.get("X-Harness-Device"))
        seen_auth = self.headers.get("Authorization", "")
        if "split" in self.path:
            # A keep-alive line cut across two chunks, then a whole one.
            self.send_response(200)
            self.send_header("content-type", "text/event-stream")
            self.end_headers()
            for part in (b": keep-", b"alive\n\n: keep-alive\n\n", b"data: {\"x\": 1}\n\ndata: [DONE]\n\n"):
                self.wfile.write(part)
                self.wfile.flush()
                time.sleep(0.05)
            return
        if "refuse" in self.path:
            body = b'{"error": {"code": "suspicious_pattern"}}'
            self.send_response(400)
            self.send_header("content-type", "application/json")
            self.send_header("x-should-retry", "false")
            self.send_header("x-not-relayed", "1")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.send_header("x-auth-seen", seen_auth)
        self.end_headers()
        for part in (b": keep-alive\n\n", b"data: {\"x\": 1}\n\n", b"data: [DONE]\n\n"):
            self.wfile.write(part)
            self.wfile.flush()

    def do_GET(self):
        body = b'{"data": []}'
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def recorder():
    upstream = ThreadingHTTPServer(("127.0.0.1", 0), _Upstream)
    threading.Thread(target=upstream.serve_forever, daemon=True).start()
    proxy = _live.Recorder(f"http://127.0.0.1:{upstream.server_address[1]}")
    try:
        yield proxy
    finally:
        proxy.close()
        upstream.shutdown()
        upstream.server_close()


def test_the_recorder_relays_a_stream_and_records_only_the_shape(recorder):
    body = {"model": "m", "messages": [{"role": "user", "content": "SECRET"}], "stream": True}
    response = httpx.post(f"{recorder.base}/v1/chat/completions", json=body,
                          headers={"Authorization": "Bearer tok-123"})
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/event-stream"
    assert response.text == ': keep-alive\n\ndata: {"x": 1}\n\ndata: [DONE]\n\n'
    [entry] = recorder.posts()
    assert entry["path"] == "/v1/chat/completions"
    assert entry["keys"] == ["messages", "model", "stream"]
    assert entry["roles"] == ["user"]
    assert "SECRET" not in json.dumps(recorder.log) and "tok-123" not in json.dumps(recorder.log)


def test_the_recorder_forwards_the_authorization_header(recorder):
    response = httpx.post(f"{recorder.base}/v1/chat/completions", json={"model": "m"},
                          headers={"Authorization": "Bearer tok-123"})
    # The upstream echoes what it saw; the proxy does not relay that header back.
    assert "x-auth-seen" not in response.headers
    assert recorder.posts()[0]["keys"] == ["model"]


def test_the_recorder_relays_an_error_status_and_the_retry_header(recorder):
    response = httpx.post(f"{recorder.base}/v1/chat/completions/refuse", json={"model": "m"})
    assert response.status_code == 400
    assert response.headers["x-should-retry"] == "false"
    assert "x-not-relayed" not in response.headers
    assert response.json() == {"error": {"code": "suspicious_pattern"}}


def test_the_recorder_forwards_get_and_logs_it_apart_from_posts(recorder):
    response = httpx.get(f"{recorder.base}/v1/models")
    assert response.json() == {"data": []}
    assert recorder.posts() == []
    assert recorder.log == [{"method": "GET", "path": "/v1/models", "status": 200, "keepalives": 0,
                             "device_header": False}]


def test_a_body_that_is_not_json_is_still_relayed(recorder):
    response = httpx.post(f"{recorder.base}/v1/chat/completions", content=b"not json")
    assert response.status_code == 200
    assert recorder.posts()[0]["keys"] is None


def test_the_recorder_logs_the_status_of_a_get_and_a_post(recorder):
    """STORY-017 AC 3: a `/v1/models` call is judged by the status the client got."""
    httpx.get(f"{recorder.base}/v1/models")
    httpx.post(f"{recorder.base}/v1/chat/completions/refuse", json={"model": "m"})
    assert [(entry["method"], entry["status"]) for entry in recorder.log] == [("GET", 200), ("POST", 400)]


def test_the_recorder_counts_keep_alive_lines_across_chunk_boundaries(recorder):
    response = httpx.post(f"{recorder.base}/v1/chat/completions/split", json={"model": "m", "stream": True})
    assert response.text == ': keep-alive\n\n: keep-alive\n\ndata: {"x": 1}\n\ndata: [DONE]\n\n'
    [entry] = recorder.posts()
    assert entry["keepalives"] == 2


def test_the_recorder_counts_one_keep_alive_on_the_plain_stream(recorder):
    httpx.post(f"{recorder.base}/v1/chat/completions", json={"model": "m", "stream": True})
    assert recorder.posts()[0]["keepalives"] == 1


def test_the_recorder_forwards_the_device_header_and_records_only_its_presence(recorder):
    _Upstream.devices.clear()
    httpx.post(f"{recorder.base}/v1/chat/completions", json={"model": "m"},
               headers={"X-Harness-Device": "laptop-SECRET-7"})
    httpx.post(f"{recorder.base}/v1/chat/completions", json={"model": "m"})
    assert _Upstream.devices == ["laptop-SECRET-7", None]
    assert [entry["device_header"] for entry in recorder.posts()] == [True, False]
    assert "SECRET" not in json.dumps(recorder.log)


# --------------------------------------------------------------------------
# The database guard, ports and processes
# --------------------------------------------------------------------------


def test_the_guard_fails_without_an_e2e_url(monkeypatch):
    monkeypatch.delenv("HARNESS_E2E_LIBSQL_URL", raising=False)
    with pytest.raises(pytest.fail.Exception, match="is not set. Start a throwaway libSQL: RECIPE"):
        _live.resolve_e2e_db_url("RECIPE")


def test_the_guard_refuses_a_non_loopback_url(monkeypatch):
    monkeypatch.setenv("HARNESS_E2E_LIBSQL_URL", "http://db.example.com:8080")
    with pytest.raises(pytest.fail.Exception, match="must be a loopback endpoint, got host 'db.example.com'"):
        _live.resolve_e2e_db_url("RECIPE")


def test_the_guard_returns_a_loopback_url(monkeypatch):
    monkeypatch.setenv("HARNESS_E2E_LIBSQL_URL", " http://127.0.0.1:8088 ")
    assert _live.resolve_e2e_db_url("RECIPE") == "http://127.0.0.1:8088"


def test_port_closed_within_tells_open_from_closed():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        assert _live.port_closed_within(port, 0.3) is False
    assert _live.port_closed_within(port, 2) is True


def test_stop_ends_a_running_child():
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    _live.stop(proc, 10)
    assert proc.poll() is not None


def test_the_stub_log_is_read_as_rule_labels():
    class _Proc:
        stderr = iter([
            "stub_openrouter: listening on http://127.0.0.1:1/v1\n",
            "stub_openrouter: POST '/v1/chat/completions' model='m' messages=2 params=[] rule=1 delay=0 -> 200\n",
            "stub_openrouter: POST '/v1/chat/completions' model='m' messages=10 params=[] rule=default delay=0 -> 200\n",
        ])

    assert _live.Stub(_Proc(), "http://127.0.0.1:1/v1").settle() == ["1", "default"]
