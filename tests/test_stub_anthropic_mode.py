"""PRD-022 STORY-006: the stub upstream's Anthropic Messages mode and scripted faults.

HTTP-level tests of `scripts/stub_openrouter.py` (`POST .../messages`, JSON and
SSE, `stop_reason` / `retry_after` / `fault` / cache usage, per-endpoint hit
counters), plus one end-to-end test that drives the REAL `AnthropicAdapter` (real
SDK path) against it. Every stub binds port 0 and is closed at teardown;
`server_close` releases held `timeout` faults, so teardown never waits.
"""

import importlib.util
import io
import json
import sys
import threading
import time
from pathlib import Path

import httpx
import pytest

from app.models.messages import Message
from app.services import provider_registry as registry
from app.services.upstream.anthropic import AnthropicAdapter
from app.services.upstream.types import UpstreamError, UpstreamRequest

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "stub_openrouter.py"
_spec = importlib.util.spec_from_file_location("stub_openrouter_under_test_messages", _SCRIPT)
stub_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = stub_mod
_spec.loader.exec_module(stub_mod)
ScriptError, make_server, parse_script = stub_mod.ScriptError, stub_mod.make_server, stub_mod.parse_script

_KEY = "sk-ant-STUBKEY-123"
_SECRET = "SECRET-PROMPT-TEXT"
_BODY = {"model": "claude-x", "max_tokens": 64, "messages": [{"role": "user", "content": "hello"}]}
_CHAT_BODY = {"model": "m", "messages": [{"role": "user", "content": "hello"}]}


@pytest.fixture
def stub():
    """Factory: (server, log, base) for a script dict; every server is closed at teardown."""
    servers = []

    def start(script, **kwargs):
        log = io.StringIO()
        server = make_server(parse_script(script), log=log, **kwargs)
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        thread.start()
        servers.append(server)
        return server, log, f"http://127.0.0.1:{server.server_address[1]}"

    yield start
    for server in servers:
        server.shutdown()
        server.server_close()


def _post(base, body=None, *, endpoint="messages", headers=None, **kwargs):
    path = "/v1/messages" if endpoint == "messages" else "/v1/chat/completions"
    default = _BODY if endpoint == "messages" else _CHAT_BODY
    return httpx.post(base + path, json=default if body is None else body, headers=headers, **kwargs)


def _sse_frames(response):
    """[(event, data dict)] from a Messages SSE body."""
    frames = []
    for block in response.text.split("\n\n"):
        if not block.strip():
            continue
        lines = dict(line.split(": ", 1) for line in block.split("\n"))
        frames.append((lines["event"], json.loads(lines["data"])))
    return frames


# --- Messages JSON ---------------------------------------------------------------


def test_json_text_usage_cache_and_stop_reason_mapping(stub):
    _, _, base = stub({"default": {
        "content": "the answer", "stop_reason": "max_tokens",
        "usage": {"prompt_tokens": 10, "completion_tokens": 4,
                  "cache_creation_input_tokens": 3, "cache_read_input_tokens": 2},
    }, "rules": [{"contains": "len", "content": "x", "finish_reason": "length"}]})
    response = _post(base)
    wire = response.json()
    assert response.status_code == 200 and response.headers["request-id"].startswith("req_stub_")
    assert (wire["type"], wire["role"], wire["model"]) == ("message", "assistant", "claude-x")
    assert wire["content"] == [{"type": "text", "text": "the answer"}]
    assert wire["stop_reason"] == "max_tokens" and wire["stop_sequence"] is None
    assert wire["usage"] == {  # input_tokens EXCLUDES the cache counts (PRD-022 6.5)
        "input_tokens": 10, "output_tokens": 4,
        "cache_creation_input_tokens": 3, "cache_read_input_tokens": 2,
    }
    forward = _post(base, {**_BODY, "messages": [{"role": "user", "content": "len"}]}).json()
    assert forward["stop_reason"] == "max_tokens"  # finish_reason "length", mapped forward


def test_json_tool_calls_become_tool_use_blocks_with_unique_ids(stub):
    _, _, base = stub({"default": {"tool_calls": [
        {"name": "get", "arguments": '{"a": 1}'},
        {"name": "put", "arguments": "{}", "id": "toolu_scripted"},
    ]}})
    first, second = _post(base).json(), _post(base).json()
    assert first["stop_reason"] == "tool_use"  # tool_calls mapped forward
    blocks = first["content"]  # content null: no text block
    assert [b["type"] for b in blocks] == ["tool_use", "tool_use"]
    assert blocks[0]["input"] == {"a": 1} and blocks[1]["id"] == "toolu_scripted"
    generated = [first["content"][0]["id"], second["content"][0]["id"]]
    assert all(i.startswith("toolu_stub_") for i in generated) and len(set(generated)) == 2


def test_json_arguments_that_are_not_an_object_answer_500_without_echo(stub):
    _, log, base = stub({"default": {"tool_calls": [{"name": "get", "arguments": '"SECRET-ARGS"'}]}})
    response = _post(base)
    assert response.status_code == 500 and response.json()["error"]["type"] == "api_error"
    assert "SECRET-ARGS" not in response.text and "SECRET-ARGS" not in log.getvalue()


def test_json_reasoning_becomes_a_leading_thinking_block(stub):
    _, _, base = stub({"default": {"content": "ok", "stream": {"reasoning": "hmm"}}})
    blocks = _post(base).json()["content"]
    assert blocks[0] == {"type": "thinking", "thinking": "hmm", "signature": "stub-signature"}
    assert blocks[1]["type"] == "text"


def test_json_null_usage_is_sent_as_null(stub):
    _, _, base = stub({"default": {"content": "ok", "usage": None}})
    assert _post(base).json()["usage"] is None


def test_request_view_reaches_the_matchers(stub):
    _, _, base = stub({"rules": [
        {"contains": "be terse", "role": "system", "content": "system matched"},
        {"contains": "result-7", "role": "tool", "content": "tool matched"},
        {"regex": "", "after_call": "lookup", "advertises": "lookup", "content": "after_call matched"},
    ], "default": {"content": "default"}})
    body = {**_BODY, "system": [{"type": "text", "text": "be terse"}]}
    assert _post(base, body).json()["content"][0]["text"] == "system matched"
    results = {**_BODY, "messages": [
        {"role": "user", "content": "q"},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t", "content": "result-7"}]},
    ]}
    assert _post(base, results).json()["content"][0]["text"] == "tool matched"
    called = {**_BODY, "tools": [{"name": "lookup", "input_schema": {}}], "messages": [
        {"role": "user", "content": "q"},
        {"role": "assistant", "content": [{"type": "tool_use", "id": "t", "name": "lookup", "input": {}}]},
    ]}
    assert _post(base, called).json()["content"][0]["text"] == "after_call matched"


# --- auth and validation ---------------------------------------------------------


def test_auth_accepts_bearer_or_x_api_key_and_refuses_others(stub):
    _, _, base = stub({}, require_key=_KEY)
    assert _post(base, headers={"Authorization": f"Bearer {_KEY}"}).status_code == 200
    assert _post(base, headers={"x-api-key": _KEY}).status_code == 200
    wrong = _post(base, headers={"x-api-key": "nope"})
    assert wrong.status_code == 401 and wrong.json()["error"]["type"] == "authentication_error"
    assert wrong.json()["type"] == "error"
    assert _post(base).status_code == 401


@pytest.mark.parametrize("body", [
    {"model": "m", "messages": []},  # no max_tokens
    {"model": "m", "max_tokens": 0, "messages": []},
    {"model": "m", "max_tokens": True, "messages": []},
    {"max_tokens": 5, "messages": []},  # no model
    {"model": "m", "max_tokens": 5},  # no messages
])
def test_invalid_bodies_answer_400_in_the_anthropic_envelope(stub, body):
    _, _, base = stub({})
    response = _post(base, body)
    assert response.status_code == 400
    assert response.json()["type"] == "error"
    assert response.json()["error"]["type"] == "invalid_request_error"
    assert httpx.post(base + "/v1/messages", content=b"{nope").status_code == 400


# --- faults, on both endpoints ---------------------------------------------------


@pytest.mark.parametrize("endpoint", ["messages", "chat"])
@pytest.mark.parametrize("status, messages_type, retry_after", [
    (503, "api_error", None), (429, "rate_limit_error", 7), (401, "authentication_error", None),
    (400, "invalid_request_error", None), (529, "overloaded_error", None),
])
def test_fail_status_keeps_each_endpoints_error_shape(stub, endpoint, status, messages_type, retry_after):
    reply = {"fail_status": status}
    if retry_after:
        reply["retry_after"] = retry_after
    _, _, base = stub({"default": reply})
    response = _post(base, endpoint=endpoint)
    assert response.status_code == status
    error = response.json()["error"]
    if endpoint == "messages":
        assert response.json()["type"] == "error" and error["type"] == messages_type
    else:
        assert error["code"] == status and "type" not in error  # today's Chat shape
    assert response.headers.get("retry-after") == (str(retry_after) if retry_after else None)


@pytest.mark.parametrize("endpoint", ["messages", "chat"])
def test_malformed_is_a_truncated_body_or_a_truncated_first_frame(stub, endpoint):
    _, _, base = stub({"default": {"fault": "malformed"}})
    response = _post(base, endpoint=endpoint)
    assert response.status_code == 200
    with pytest.raises(ValueError):
        response.json()
    streamed_body = {**(_BODY if endpoint == "messages" else _CHAT_BODY), "stream": True}
    streamed = _post(base, streamed_body, endpoint=endpoint)
    assert streamed.status_code == 200 and "[DONE]" not in streamed.text
    first = "event: message_start" if endpoint == "messages" else "data: "
    assert streamed.text.startswith(first) and not streamed.text.endswith("\n\n")


@pytest.mark.parametrize("endpoint", ["messages", "chat"])
def test_timeout_sends_nothing_and_teardown_is_fast(stub, endpoint):
    server, _, base = stub({"default": {"fault": "timeout"}})
    started = time.monotonic()
    with pytest.raises(httpx.ReadTimeout):
        _post(base, endpoint=endpoint, timeout=0.3)
    assert time.monotonic() - started < 5
    closing = time.monotonic()
    server.shutdown()
    server.server_close()  # releases the parked handler
    assert time.monotonic() - closing < 5


@pytest.mark.parametrize("endpoint", ["messages", "chat"])
def test_refusal_from_one_stop_reason_script(stub, endpoint):
    _, _, base = stub({"default": {"content": "no", "stop_reason": "refusal"}})
    wire = _post(base, endpoint=endpoint).json()
    if endpoint == "messages":
        assert wire["stop_reason"] == "refusal"
    else:
        assert wire["choices"][0]["finish_reason"] == "content_filter"


def test_times_then_normal_on_messages_and_endpoint_hits(stub):
    server, _, base = stub({"rules": [
        {"regex": "", "times": 2, "fail_status": 503},
    ], "default": {"content": "fine"}})
    assert [_post(base).status_code for _ in range(3)] == [503, 503, 200]
    assert server.endpoint_hits() == {"chat": 0, "messages": 3}
    assert _post(base, endpoint="chat").status_code == 200  # the shared `times` is spent
    assert httpx.post(base + "/v1/models", json={}).status_code == 404  # not counted
    assert server.endpoint_hits() == {"chat": 1, "messages": 3}


def test_endpoint_hits_count_faulted_and_timed_out_requests(stub):
    server, _, base = stub({"rules": [
        {"contains": "hang", "fault": "timeout"},
        {"contains": "bad", "fault": "malformed"},
    ], "default": {"content": "ok"}}, require_key=_KEY)
    assert _post(base).status_code == 401  # unauthorized still counts
    auth = {"x-api-key": _KEY}
    with pytest.raises(httpx.ReadTimeout):
        _post(base, {**_BODY, "messages": [{"role": "user", "content": "hang"}]}, headers=auth, timeout=0.3)
    _post(base, {**_BODY, "messages": [{"role": "user", "content": "bad"}]}, headers=auth)
    assert server.endpoint_hits() == {"chat": 0, "messages": 3}
    snapshot = server.endpoint_hits()
    snapshot["messages"] = 99
    assert server.endpoint_hits()["messages"] == 3  # a copy


# --- SSE -------------------------------------------------------------------------

_KNOWN_EVENTS = {
    "message_start", "content_block_start", "content_block_delta", "content_block_stop",
    "message_delta", "message_stop", "ping",
}


def _stream(base, **extra):
    return _post(base, {**_BODY, "stream": True, **extra})


def test_sse_event_order_text_and_tool_pieces_reassemble(stub):
    _, _, base = stub({"default": {
        "content": "hello world", "tool_calls": [{"name": "get", "arguments": '{"k": "value"}'}],
        "stream": {"chunk_chars": 4, "reasoning": "think hard"},
        "usage": {"prompt_tokens": 9, "completion_tokens": 5, "cache_read_input_tokens": 2},
    }})
    response = _stream(base)
    assert response.headers["content-type"].startswith("text/event-stream")
    frames = _sse_frames(response)
    names = [name for name, _ in frames]
    assert set(names) <= _KNOWN_EVENTS
    assert names[:2] == ["message_start", "ping"] and names[-2:] == ["message_delta", "message_stop"]
    # each block: start, delta+, stop, in order thinking, text, tool_use
    starts = [data["content_block"]["type"] for name, data in frames if name == "content_block_start"]
    assert starts == ["thinking", "text", "tool_use"]
    middle = names[2:-2]
    assert middle[0] == "content_block_start" and middle[-1] == "content_block_stop"
    deltas = [data["delta"] for name, data in frames if name == "content_block_delta"]
    kinds = [d["type"] for d in deltas]
    thinking = [d for d in deltas if d["type"] == "thinking_delta"]
    assert "".join(d["thinking"] for d in thinking) == "think hard" and max(len(d["thinking"]) for d in thinking) <= 4
    assert kinds[len(thinking)] == "signature_delta"  # after every thinking piece
    assert "".join(d["text"] for d in deltas if d["type"] == "text_delta") == "hello world"
    assert "".join(d["partial_json"] for d in deltas if d["type"] == "input_json_delta") == '{"k": "value"}'
    tool_start = next(d["content_block"] for n, d in frames if n == "content_block_start" and d["content_block"]["type"] == "tool_use")
    assert tool_start["id"].startswith("toolu_stub_") and tool_start["input"] == {}
    start_usage = frames[0][1]["message"]["usage"]
    assert start_usage["input_tokens"] == 9 and start_usage["cache_read_input_tokens"] == 2
    assert start_usage["output_tokens"] == 1 and frames[0][1]["message"]["content"] == []
    final = frames[-2][1]
    assert final["delta"] == {"stop_reason": "tool_use", "stop_sequence": None}
    assert final["usage"]["output_tokens"] == 5


def test_sse_default_pieces_are_halves(stub):
    _, _, base = stub({"default": {"content": "abcdef"}})
    texts = [d["delta"]["text"] for n, d in _sse_frames(_stream(base)) if n == "content_block_delta"]
    assert texts == ["abc", "def"]


def test_sse_fail_after_sends_k_deltas_and_no_tail(stub):
    _, _, base = stub({"default": {"content": "abcdefgh", "stream": {"chunk_chars": 2, "fail_after": 2}}})
    names = [n for n, _ in _sse_frames(_stream(base))]
    assert names.count("content_block_delta") == 2
    assert "message_delta" not in names and "message_stop" not in names


def test_sse_usage_null_omits_both_usage_objects(stub):
    _, _, base = stub({"default": {"content": "ok", "usage": None}})
    frames = _sse_frames(_stream(base))
    assert "usage" not in frames[0][1]["message"] and "usage" not in frames[-2][1]


def test_sse_delay_paces_every_delta(stub):
    _, _, base = stub({"default": {"content": "abcd", "stream": {"chunk_chars": 2, "delay_ms": 100}}})
    started = time.monotonic()
    _stream(base)
    assert time.monotonic() - started >= 0.15  # two deltas, 100 ms each (loose bound)


# --- privacy and parity ----------------------------------------------------------


def test_messages_traffic_never_reaches_the_log_or_the_console(stub, capfd):
    server, log, base = stub({"default": {"tool_calls": [{"name": "get", "arguments": '{"a": 1}'}]}},
                             require_key=_KEY)
    body = {**_BODY, "system": _SECRET, "tools": [{"name": "TOOLNAME-SECRET", "input_schema": {}}],
            "messages": [{"role": "user", "content": _SECRET}]}
    _post(base, body, headers={"Authorization": f"Bearer {_KEY}", "anthropic-version": "2023-06-01"})
    _post(base, body, headers={"x-api-key": _KEY})
    _post(base, body, headers={"x-api-key": _SECRET})  # a 401
    captured = capfd.readouterr()
    for text in (log.getvalue(), captured.out, captured.err):
        for secret in (_SECRET, _KEY, "TOOLNAME-SECRET", "Bearer", "2023-06-01"):
            assert secret not in text
    lines = log.getvalue().splitlines()
    assert len(lines) == 3 and all("api=messages" in line for line in lines)
    assert "auth=yes ver=yes" in lines[0] and "auth=yes ver=no" in lines[1]


def test_chat_parity_old_scripts_and_unserved_paths_are_unchanged(stub):
    _, log, base = stub({"default": {"content": "hi", "usage": {"prompt_tokens": 2}}})
    wire = _post(base, endpoint="chat").json()
    assert set(wire) == {"id", "object", "created", "model", "choices", "usage"}
    assert wire["usage"] == {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3}
    assert wire["choices"][0]["finish_reason"] == "stop"
    missing = httpx.post(base + "/v1/models", json={})
    assert missing.status_code == 404 and "only POST .../chat/completions is served" in missing.text
    assert "fault=" not in log.getvalue() and "api=" not in log.getvalue()


# --- script validation -----------------------------------------------------------


@pytest.mark.parametrize("reply, fragment", [
    ({"fault": "boom"}, "rules[1]: fault must be one of timeout, malformed"),
    ({"retry_after": 3, "content": "x"}, "rules[1]: retry_after needs fail_status"),
    ({"retry_after": 0, "fail_status": 429}, "rules[1]: retry_after must be an integer >= 1"),
    ({"stop_reason": "end_turn", "finish_reason": "stop"}, "rules[1]: stop_reason and finish_reason"),
    ({"stop_reason": "bogus"}, "rules[1]: stop_reason must be one of"),
    ({"fault": "timeout", "content": "x"}, "rules[1]: fault replaces the body; remove content"),
    ({"fault": "timeout", "fail_status": 500}, "rules[1]: fault replaces the body; remove fail_status"),
    ({"fail_status": 500, "stop_reason": "end_turn"}, "rules[1]: fail_status replaces the body; remove stop_reason"),
    ({"usage": {"cache_read_input_tokens": -1}}, "rules[1]: usage.cache_read_input_tokens must be"),
    ({"usage": {"cache_creation_input_tokens": "x"}}, "rules[1]: usage.cache_creation_input_tokens must be"),
])
def test_parse_errors_name_the_rule(reply, fragment):
    with pytest.raises(ScriptError) as caught:
        parse_script({"rules": [{"contains": "a", "content": "ok"}, {"contains": "b", **reply}]})
    assert fragment in str(caught.value)


def test_default_rejects_unknown_keys_but_takes_the_new_ones():
    with pytest.raises(ScriptError, match="default: fault must be"):
        parse_script({"default": {"fault": "x"}})
    assert parse_script({"default": {"stop_reason": "pause_turn"}}).default.finish_reason == "pause_turn"


# --- end to end: the REAL adapter against the stub ---------------------------------


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


def _upstream_request(text="hi"):
    model = registry.CatalogModel(
        id="claude-x", upstream="claude-up", roles=None,
        capabilities=registry.Capabilities(tools=True), provider_name="ant",
        default_max_tokens=256, prompt_cache="off",
    )
    return UpstreamRequest([Message("user", text)], "claude-up", None, None, model)


def test_the_real_adapter_against_the_stub_messages_mode(stub):
    server, log, base = stub({"rules": [
        {"contains": "flaky", "times": 1, "fail_status": 503},
        {"contains": "limited", "fail_status": 429, "retry_after": 7},
        {"contains": "refuse", "content": "", "stop_reason": "refusal"},
        {"contains": "hang", "fault": "timeout"},
    ], "default": {"content": "stub answer", "usage": {
        "prompt_tokens": 10, "completion_tokens": 4,
        "cache_creation_input_tokens": 3, "cache_read_input_tokens": 2,
    }}}, require_key=_KEY)  # the SDK sends Authorization: Bearer, which the stub must accept

    def call(text, timeout=12.5):
        request = _upstream_request(text)
        return AnthropicAdapter(_provider(base_url=base, timeout_seconds=timeout)).complete(request, _KEY)

    calls = 0
    result = call("normal")
    calls += 1
    assert result.response == "stub answer" and result.finish_reason == "stop"
    assert result.tokens_used == 10 + 3 + 2 + 4  # input + cache write + cache read + output
    assert (result.cache_write_tokens, result.cache_read_tokens) == (3, 2)

    with pytest.raises(UpstreamError) as first:  # `times: 1`: the first call fails ...
        call("flaky")
    calls += 1
    assert (first.value.kind, first.value.upstream_status, first.value.retryable) == ("status", 503, True)
    assert call("flaky").response == "stub answer"  # ... the next one answers normally
    calls += 1

    with pytest.raises(UpstreamError) as limited:
        call("limited")
    calls += 1
    assert limited.value.retry_after_seconds == 7 and limited.value.retryable is True

    refused = call("refuse")  # an EMPTY refusal is an answer, not a shape error (PRD 6.2/T4)
    calls += 1
    assert refused.finish_reason == "content_filter" and refused.response == ""

    started = time.monotonic()
    with pytest.raises(UpstreamError) as timed_out:
        call("hang", timeout=1.0)
    calls += 1
    assert (timed_out.value.kind, timed_out.value.retryable) == ("timeout", True)
    assert time.monotonic() - started < 8

    assert server.endpoint_hits() == {"chat": 0, "messages": calls}
    assert _KEY not in log.getvalue() and "Bearer" not in log.getvalue()
