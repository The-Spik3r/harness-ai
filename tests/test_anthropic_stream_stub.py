"""PRD-022 STORY-007: the property `collect(stream()) == complete()`, on the real SDK.

Every script runs against the STORY-006 stub's `/v1/messages` (JSON for `complete()`,
SSE for `stream()`) through the real `AnthropicAdapter` and the real SDK over
loopback. `reasoning_blocks` and `dropped_params` are neutralized before the
comparison: `collect()` ignores reasoning (PRD 6.6) and no event carries a block
count (known limitation), and `dropped_params` is a `complete()`-only field.
"""

import dataclasses
import importlib.util
import io
import sys
import threading
import time
from pathlib import Path

import pytest

from app.models.messages import Message
from app.services import provider_registry as registry
from app.services.upstream.anthropic import AnthropicAdapter
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

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "stub_openrouter.py"
_spec = importlib.util.spec_from_file_location("stub_openrouter_under_test_anthropic_stream", _SCRIPT)
stub_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = stub_mod
_spec.loader.exec_module(stub_mod)
make_server, parse_script = stub_mod.make_server, stub_mod.parse_script

_KEY = "sk-ant-STUBKEY-123"
_THINKING = "weighing the options carefully"
_USAGE = {"prompt_tokens": 10, "completion_tokens": 4,
          "cache_creation_input_tokens": 3, "cache_read_input_tokens": 2}
_TOOLS = ToolParams([{"type": "function", "function": {"name": "get", "parameters": {"type": "object"}}}])


@pytest.fixture
def stub():
    """Factory: (server, log, base) for a script dict; every server is closed at teardown."""
    servers = []

    def start(script, **kwargs):
        log = io.StringIO()
        server = make_server(parse_script(script), log=log, require_key=_KEY, **kwargs)
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        thread.start()
        servers.append(server)
        return server, log, f"http://127.0.0.1:{server.server_address[1]}"

    yield start
    for server in servers:
        server.shutdown()
        server.server_close()


def _provider(base, timeout=12.5):
    return registry.Provider(
        name="ant", label="Anthropic", type="anthropic", base_url=base,
        key_env="K", insecure_http=True, trust="external", pii="redact", byok=False,
        passthrough=False, passthrough_capabilities=registry.Capabilities(),
        usage_missing="estimate", estimate_chars_per_token=4.0, timeout_seconds=timeout,
        roles=None, models=(),
    )


def _request(text="hello", tools=None):
    model = registry.CatalogModel(
        id="claude-x", upstream="claude-up", roles=None,
        capabilities=registry.Capabilities(tools=True), provider_name="ant",
        default_max_tokens=256, prompt_cache="off",
    )
    return UpstreamRequest([Message("user", text)], "claude-up", None, tools, model)


def _both(base, request):
    provider = _provider(base)
    adapter = AnthropicAdapter(provider)
    whole = adapter.complete(request, _KEY)
    events = list(adapter.stream(request, _KEY, reasoning=True))
    return whole, events, collect(events, provider=provider, request=request)


def _neutral(result):
    return dataclasses.replace(result, reasoning_blocks=0, dropped_params=())


_SCRIPTS = {
    "text": ({"content": "the plain answer", "usage": _USAGE}, None),
    "text_chunked": ({"content": "abcdefghijkléè", "stream": {"chunk_chars": 3}, "usage": _USAGE}, None),
    "one_tool": ({"tool_calls": [{"id": "toolu_a", "name": "get", "arguments": '{"city": "Zürich", "n": [1, 2]}'}],
                  "usage": _USAGE}, _TOOLS),
    "one_tool_chunked": ({"tool_calls": [{"id": "toolu_a", "name": "get", "arguments": '{"city": "Zurich", "n": 12345}'}],
                          "stream": {"chunk_chars": 3}}, _TOOLS),
    "parallel_tools": ({"content": "calling", "tool_calls": [
        {"id": "toolu_a", "name": "get", "arguments": '{"a": 1}'},
        {"id": "toolu_b", "name": "get", "arguments": "{}"},
    ], "stream": {"chunk_chars": 2}}, _TOOLS),
    "thinking": ({"content": "the answer", "stream": {"reasoning": _THINKING, "chunk_chars": 5}, "usage": _USAGE}, None),
    "empty_refusal": ({"content": "", "stop_reason": "refusal", "usage": _USAGE}, None),
    "refusal_with_text": ({"content": "I cannot help", "stop_reason": "refusal"}, None),
    "cache_usage": ({"content": "cached", "usage": {"prompt_tokens": 100, "completion_tokens": 9,
                                                    "cache_creation_input_tokens": 40,
                                                    "cache_read_input_tokens": 50}}, None),
    "max_tokens": ({"content": "cut off", "stop_reason": "max_tokens"}, None),
}


@pytest.mark.parametrize("name", sorted(_SCRIPTS))
def test_collect_of_the_stream_equals_complete(stub, name):
    reply, tools = _SCRIPTS[name]
    server, log, base = stub({"default": reply})
    whole, events, collected = _both(base, _request(tools=tools))
    assert _neutral(collected) == _neutral(whole)
    assert isinstance(events[-1], Finish) and isinstance(events[-2], UsageReport)
    assert server.endpoint_hits() == {"chat": 0, "messages": 2}  # one complete(), one stream()
    assert _KEY not in log.getvalue()


def test_empty_refusal_streams_one_empty_text_delta_and_collects_to_empty_content(stub):
    _, _, base = stub({"default": _SCRIPTS["empty_refusal"][0]})
    _, events, collected = _both(base, _request())
    assert events[0] == TextDelta("")  # the one synthetic event (T4)
    assert (collected.response, collected.finish_reason) == ("", "content_filter")


def test_thinking_is_counted_by_complete_and_streamed_as_reasoning_only_when_asked(stub):
    server, _, base = stub({"default": _SCRIPTS["thinking"][0]})
    provider, request = _provider(base), _request()
    adapter = AnthropicAdapter(provider)
    assert adapter.complete(request, _KEY).reasoning_blocks == 1
    on = list(adapter.stream(request, _KEY, reasoning=True))
    assert "".join(e.text for e in on if isinstance(e, ReasoningDelta)) == _THINKING
    off = list(adapter.stream(request, _KEY, reasoning=False))
    assert not any(isinstance(e, ReasoningDelta) for e in off)
    for events in (on, off):
        result = collect(events, provider=provider, request=request)
        assert result.response == "the answer"
        assert _THINKING not in repr([e for e in events if not isinstance(e, ReasoningDelta)])
        assert "stub-signature" not in repr(events)
    assert server.endpoint_hits()["messages"] == 3


def test_tool_input_is_one_event_per_call_even_when_the_wire_is_chunked(stub):
    _, _, base = stub({"default": _SCRIPTS["parallel_tools"][0]})
    _, events, _ = _both(base, _request(tools=_TOOLS))
    calls = [e for e in events if isinstance(e, ToolCallDelta)]
    assert [(c.index, c.id, c.arguments) for c in calls] == [(0, "toolu_a", '{"a":1}'), (1, "toolu_b", "{}")]


def test_stream_is_lazy_on_the_server(stub):
    server, _, base = stub({"default": {"content": "hi"}})
    iterator = AnthropicAdapter(_provider(base)).stream(_request(), _KEY)
    assert server.endpoint_hits()["messages"] == 0
    list(iterator)
    assert server.endpoint_hits() == {"chat": 0, "messages": 1}


# --- error parity ---------------------------------------------------------------------


def _raised(call):
    with pytest.raises(UpstreamError) as caught:
        call()
    return caught.value


@pytest.mark.parametrize(
    "reply",
    [
        {"fail_status": 503},
        {"fail_status": 429, "retry_after": 7},
        {"fail_status": 401},
        {"fail_status": 400},
        {"fail_status": 529},
    ],
)
def test_first_response_failures_match_between_complete_and_stream(stub, reply):
    _, _, base = stub({"default": reply})
    adapter, request = AnthropicAdapter(_provider(base)), _request()
    a = _raised(lambda: adapter.complete(request, _KEY))
    b = _raised(lambda: next(adapter.stream(request, _KEY)))
    key = lambda e: (e.kind, e.upstream_status, e.retryable, e.retry_after_seconds, e.provider, str(e))
    assert key(a) == key(b)


def test_a_stream_cut_before_its_stop_is_shape(stub):
    _, _, base = stub({"default": {"content": "abcdefgh", "stream": {"chunk_chars": 2, "fail_after": 1}}})
    seen = []
    with pytest.raises(UpstreamError) as caught:
        for event in AnthropicAdapter(_provider(base)).stream(_request(), _KEY):
            seen.append(event)
    assert (caught.value.kind, caught.value.retryable) == ("shape", False)
    assert seen == [TextDelta("ab")] and not any(isinstance(e, Finish) for e in seen)


def test_a_silent_upstream_times_out_like_complete(stub):
    _, _, base = stub({"default": {"fault": "timeout"}})
    adapter = AnthropicAdapter(_provider(base, timeout=1.0))
    started = time.monotonic()
    error = _raised(lambda: list(adapter.stream(_request(), _KEY)))
    assert (error.kind, error.retryable) == ("timeout", True)
    assert time.monotonic() - started < 8


def test_a_malformed_stream_is_a_classified_error_never_a_crash(stub):
    _, _, base = stub({"default": {"fault": "malformed"}})
    adapter = AnthropicAdapter(_provider(base))
    # Observed: the truncated first frame ends the stream with no message_delta -> shape. The
    # closed set keeps a transport-level break (platform timing) a typed error, never a Finish.
    error = _raised(lambda: list(adapter.stream(_request(), _KEY)))
    assert error.kind in {"shape", "transport"} and error.provider == "ant"


def test_missing_usage_is_shape_from_both_paths(stub):
    _, _, base = stub({"default": {"content": "ok", "usage": None}})
    adapter, request = AnthropicAdapter(_provider(base)), _request()
    a = _raised(lambda: adapter.complete(request, _KEY))
    b = _raised(lambda: list(adapter.stream(request, _KEY)))
    assert (a.kind, a.retryable) == (b.kind, b.retryable) == ("shape", False)
