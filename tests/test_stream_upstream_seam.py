"""PRD-021 STORY-003: the stream_upstream seam, ReasoningDelta and collect()'s usage override.

    AC1  ReasoningDelta: frozen, in the UpstreamEvent union, exported
    AC2  opt-in reasoning mapping, replayed on the three PRD-021 survey fixtures
    AC3  collect() ignores reasoning and keeps the last non-None finish reason
    AC4  collect(usage_missing=...) overrides the provider's mode for one call
    AC5  stream_upstream: eager route/key errors, lazy network, no-Finish error
"""

import dataclasses
import io
import json
import os
import threading
import types
import typing
from pathlib import Path

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import httpx
import pytest

from app.config import settings
from app.models.messages import Message
from app.services import provider_registry, upstream
from app.services.upstream import (
    Finish,
    OpenAICompatibleAdapter,
    ReasoningDelta,
    TextDelta,
    UpstreamError,
    UpstreamEvent,
    UpstreamRequest,
    UsageReport,
    call_upstream,
    collect,
    stream_upstream,
)
from app.services.upstream import reply as upstream_reply
from app.services.upstream.sse import parse_events
from scripts.stub_openrouter import make_server, parse_script
from tests._providers import provider_file  # noqa: F401  (fixture)

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "prd021_survey"
_DEEPSEEK = _FIXTURES / "openrouter-deepseek-deepseek-r1-0528.sse"
_GPT = _FIXTURES / "openrouter-openai-gpt-4o-mini.sse"
_GEMMA = _FIXTURES / "local-google-gemma-4-e4b.sse"
_KEY = "sk-test-key-STORY003"
_MSG = [Message("user", "hello")]


def _lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def _chunks(path: Path) -> list[dict]:
    out = []
    for line in _lines(path):
        value = line[len("data:"):].strip()
        if line.startswith("data:") and value != "[DONE]":
            out.append(json.loads(value))
    return out


def _data(*payloads) -> list[str]:
    return [f"data: {json.dumps(p)}" for p in payloads] + ["data: [DONE]"]


def _delta(finish=None, **delta):
    return {"choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}


def _provider(**changes):
    base = provider_registry.current().providers[0]
    return dataclasses.replace(base, base_url="http://127.0.0.1:1/v1", **changes)


def _request(text="hello"):
    return UpstreamRequest([Message("user", text)], "up-model")


def _adapter_over(lines: list[str]) -> OpenAICompatibleAdapter:
    body = ("\n\n".join(lines) + "\n\n").encode("utf-8")
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=body)))
    return OpenAICompatibleAdapter(_provider(), client)


# --------------------------------------------------------------------------
# AC1
# --------------------------------------------------------------------------


def test_reasoning_delta_is_frozen_in_union_and_exported():
    event = ReasoningDelta("because")
    with pytest.raises(dataclasses.FrozenInstanceError):
        event.text = "x"  # type: ignore[misc]
    assert ReasoningDelta in typing.get_args(UpstreamEvent)
    assert "ReasoningDelta" in upstream.__all__ and "stream_upstream" in upstream.__all__


# --------------------------------------------------------------------------
# AC2: parser, replaying the saved streams
# --------------------------------------------------------------------------


def test_deepseek_fixture_maps_reasoning_only_when_enabled():
    chunks = _chunks(_DEEPSEEK)
    expected = "".join(
        c["choices"][0]["delta"]["reasoning"]
        for c in chunks
        if c["choices"] and isinstance(c["choices"][0]["delta"].get("reasoning"), str)
        and c["choices"][0]["delta"]["reasoning"]
    )
    empty_text = sum(
        1 for c in chunks if c["choices"] and c["choices"][0]["delta"].get("content") == ""
    )
    assert expected and empty_text > 0
    on = list(parse_events(_lines(_DEEPSEEK), "X", reasoning=True))
    off = list(parse_events(_lines(_DEEPSEEK), "X"))
    assert "".join(e.text for e in on if isinstance(e, ReasoningDelta)) == expected
    assert not any(isinstance(e, ReasoningDelta) for e in off)
    # Empty content keeps yielding TextDelta("") either way (PRD-021 orchestrator note).
    assert sum(e == TextDelta("") for e in on) == sum(e == TextDelta("") for e in off) == empty_text
    assert sum(isinstance(e, Finish) for e in on) == 2
    assert sum(isinstance(e, UsageReport) for e in on) == 1
    assert [e for e in on if not isinstance(e, ReasoningDelta)] == off


@pytest.mark.parametrize("path", [_GPT, _GEMMA])
def test_plain_fixtures_are_identical_with_either_flag(path):
    assert list(parse_events(_lines(path), "X", reasoning=True)) == list(parse_events(_lines(path), "X"))


def test_reasoning_content_is_mapped_and_one_event_per_delta():
    lines = _data(
        _delta(reasoning_content="a"),
        _delta(reasoning_content="b", reasoning="c"),
        _delta(finish="stop"),
    )
    events = list(parse_events(lines, "X", reasoning=True))
    assert events == [ReasoningDelta("a"), ReasoningDelta("b"), Finish("stop")]


@pytest.mark.parametrize(
    "delta",
    [
        {"reasoning": None},
        {"reasoning": ""},
        {"reasoning": 3},
        {"reasoning": ["x"]},
        {"reasoning_content": None},
        {"reasoning_details": [{"type": "reasoning.text", "text": "secret"}]},
    ],
)
def test_empty_and_non_string_reasoning_yields_nothing(delta):
    assert list(parse_events(_data(_delta(**delta)), "X", reasoning=True)) == []


def test_reasoning_never_reaches_text_and_is_dropped_when_off():
    lines = _data(_delta(content="hi", reasoning="think", reasoning_content="more"), _delta(finish="stop"))
    off = list(parse_events(lines, "X"))
    assert off == [TextDelta("hi"), Finish("stop")]
    on = list(parse_events(lines, "X", reasoning=True))
    assert on == [ReasoningDelta("more"), TextDelta("hi"), Finish("stop")]
    result = collect(on, provider=_provider(), request=_request(), usage_missing="estimate")
    assert result.response == "hi"


def test_empty_content_with_length_still_yields_text_delta_and_collects_to_empty():
    lines = _data(_delta(content=""), _delta(finish="length", content=""))
    events = list(parse_events(lines, "X"))
    assert events == [TextDelta(""), TextDelta(""), Finish("length")]
    result = collect(events, provider=_provider(), request=_request(), usage_missing="estimate")
    assert result.response == "" and result.finish_reason == "length"


# --------------------------------------------------------------------------
# AC3
# --------------------------------------------------------------------------


def test_collect_ignores_reasoning_and_keeps_last_finish():
    request = _request()
    base = [TextDelta("a"), Finish("stop"), UsageReport(1, 2, 3)]
    noisy = [ReasoningDelta("r"), TextDelta("a"), ReasoningDelta("s"), Finish("stop"), UsageReport(1, 2, 3)]
    assert collect(noisy, provider=_provider(), request=request) == collect(
        base, provider=_provider(), request=request
    )
    for finishes, expected in (
        ([Finish("length"), Finish("length")], "length"),
        ([Finish("stop"), Finish("length")], "length"),
    ):
        got = collect([TextDelta("a"), *finishes, UsageReport(1, 2, 3)], provider=_provider(), request=request)
        assert got.finish_reason == expected


# --------------------------------------------------------------------------
# AC4
# --------------------------------------------------------------------------


def _no_usage_events():
    return [TextDelta("some answer"), Finish("stop")]


def test_collect_usage_missing_override_estimates_on_an_error_provider():
    request = _request()
    strict = _provider(usage_missing="error")
    lenient = _provider(usage_missing="estimate")
    with pytest.raises(UpstreamError, match="'usage'"):
        collect(_no_usage_events(), provider=strict, request=request)
    got = collect(_no_usage_events(), provider=strict, request=request, usage_missing="estimate")
    want = collect(_no_usage_events(), provider=lenient, request=request)
    assert got.usage_estimated is True and got.tokens_used == want.tokens_used
    assert strict.usage_missing == "error"  # the frozen provider is untouched


def test_collect_usage_missing_override_error_on_an_estimate_provider():
    with pytest.raises(UpstreamError, match="'usage'"):
        collect(_no_usage_events(), provider=_provider(usage_missing="estimate"), request=_request(),
                usage_missing="error")


def test_collect_usage_missing_override_rejects_an_unknown_mode_before_reading_events():
    def events():
        raise AssertionError("events consumed before validation")
        yield  # pragma: no cover

    with pytest.raises(ValueError, match=r"usage_missing must be one of \('estimate', 'error'\), got bogus"):
        collect(events(), provider=_provider(), request=_request(), usage_missing="bogus")


def test_usage_modes_mirror_the_registry_vocabulary():
    assert upstream_reply._USAGE_MODES == provider_registry.USAGE_MISSING


# --------------------------------------------------------------------------
# AC5: the adapter's no-Finish rule and stream_upstream
# --------------------------------------------------------------------------


@pytest.mark.parametrize("path", [_DEEPSEEK, _GPT, _GEMMA])
def test_fixtures_drain_through_the_adapter_and_reasoning_flag(path):
    lines = _lines(path)
    events = list(_adapter_over(lines).stream(_request(), _KEY))
    assert any(isinstance(e, Finish) for e in events)
    with_reasoning = list(_adapter_over(lines).stream(_request(), _KEY, reasoning=True))
    assert [e for e in with_reasoning if not isinstance(e, ReasoningDelta)] == events
    assert not any(isinstance(e, ReasoningDelta) for e in events)


@pytest.mark.parametrize("path", [_DEEPSEEK, _GPT, _GEMMA])
def test_stream_without_finish_raises_non_retryable(path):
    kept = []
    for line in _lines(path):
        if line.startswith("data:") and "[DONE]" not in line:
            chunk = json.loads(line[len("data:"):])
            for choice in chunk.get("choices", []):
                choice["finish_reason"] = None
            line = "data: " + json.dumps(chunk)
        kept.append(line)
    with pytest.raises(UpstreamError) as excinfo:
        list(_adapter_over(kept).stream(_request(), _KEY, reasoning=True))
    assert excinfo.value.retryable is False and excinfo.value.upstream_status is None
    assert "stream ended without a finish reason" in str(excinfo.value)
    assert "Okay" not in str(excinfo.value)  # no payload text (T7)


def test_null_finish_chunk_stream_raises_while_complete_would_answer():
    # PRD-021 F2: the one accepted divergence from collect(stream(r)) == complete(r).
    lines = _data(_delta(content="x"), _delta(finish=None))
    with pytest.raises(UpstreamError, match="finish reason") as excinfo:
        list(_adapter_over(lines).stream(_request(), _KEY))
    assert excinfo.value.retryable is False


def _yaml(port, *, reasoning, byok=False, key_env=None):
    key_line = f"    key_env: {key_env}\n" if key_env else ""
    return f"""
version: 1
default_model: s/m
providers:
  - name: s
    label: Stub
    type: openai_compatible
    base_url: http://127.0.0.1:{port}/v1
    insecure_http: true
    byok: {str(byok).lower()}
{key_line}    models:
      - id: s/m
        upstream: up-s
        capabilities: {{streaming: true, reasoning: {str(reasoning).lower()}}}
"""


@pytest.fixture
def stub():
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

    start.servers = started  # (server, thread) pairs, for endpoint_hits()
    yield start
    for server, thread in started:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_stream_upstream_errors_are_eager(provider_file):
    provider_file(_yaml(1, reasoning=True))
    with pytest.raises(UpstreamError, match="messages must not be empty"):
        stream_upstream([], model="s/m")
    with pytest.raises(UpstreamError, match="No provider route for the requested model"):
        stream_upstream(_MSG, model="nope/none")


@pytest.mark.parametrize("fn", [call_upstream, stream_upstream])
def test_missing_key_message_matches_between_call_and_stream(monkeypatch, fn):
    # Legacy mode reads the key per call, so an empty setting reproduces D10's refusal.
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "")
    with pytest.raises(UpstreamError) as excinfo:
        fn(_MSG, model="gpt-4")
    assert str(excinfo.value) == (
        "OpenRouter API key not configured: pass openrouter_api_key or set OPENROUTER_API_KEY"
    )


def test_stream_upstream_is_lazy_and_maps_reasoning_by_route(provider_file, stub):
    port, log = stub({"rules": [], "default": {"content": "pong"}})
    provider_file(_yaml(port, reasoning=True))
    events = stream_upstream(_MSG, model="s/m")
    assert iter(events) is events and log.getvalue() == ""  # nothing sent before the first next()
    first = next(events)
    assert isinstance(first, TextDelta) and log.getvalue() != ""
    assert Finish("stop") in list(events)


def test_stream_upstream_route_reasoning_flag_decides_the_mapping(provider_file, monkeypatch):
    seen = {}

    def fake_stream(self, request, api_key, *, reasoning=False):
        seen["reasoning"] = reasoning
        seen["model"] = request.upstream_model
        return iter(())

    monkeypatch.setattr(OpenAICompatibleAdapter, "stream", fake_stream)
    provider_file(_yaml(1, reasoning=True))
    list(stream_upstream(_MSG, model="s/m"))
    assert seen == {"reasoning": True, "model": "up-s"}
    provider_file(_yaml(1, reasoning=False))
    list(stream_upstream(_MSG, model="s/m"))
    assert seen["reasoning"] is False


def test_stream_upstream_legacy_mode_never_maps_reasoning(monkeypatch):
    seen = {}

    def fake_stream(self, request, api_key, *, reasoning=False):
        seen["reasoning"] = reasoning
        return iter(())

    monkeypatch.setattr(OpenAICompatibleAdapter, "stream", fake_stream)
    list(stream_upstream(_MSG, model="gpt-4", api_key=_KEY))
    assert seen["reasoning"] is False  # OD1: legacy mode has reasoning=false


@pytest.mark.parametrize("caller_key,expected_byok", [(_KEY, _KEY), (None, "provider-key")])
def test_stream_upstream_key_choice_matches_call_upstream(provider_file, stub, caller_key, expected_byok):
    port, log = stub({"rules": [], "default": {"content": "pong"}}, require_key=expected_byok)
    provider_file(_yaml(port, reasoning=False, byok=True, key_env="STUB_KEY_ENV"), env={"STUB_KEY_ENV": "provider-key"})
    streamed = collect(
        stream_upstream(_MSG, model="s/m", api_key=caller_key),
        provider=provider_registry.resolve("s/m").provider,
        request=_request(),
    )
    called = call_upstream(_MSG, model="s/m", api_key=caller_key)
    assert streamed.response == called.response == "pong"
    assert log.getvalue().count("auth=yes") == 2


def test_stream_upstream_against_the_stub_collects_to_the_stub_answer(provider_file, stub):
    # E2E: file-mode registry, real HTTP to the stub, collect() over the events.
    port, _ = stub({"rules": [], "default": {"content": "stub says hi", "finish_reason": "stop"}})
    provider_file(_yaml(port, reasoning=True))
    route = provider_registry.resolve("s/m")
    result = collect(
        stream_upstream(_MSG, model="s/m"),
        provider=route.provider,
        request=UpstreamRequest(_MSG, route.upstream_model),
        usage_missing="estimate",
    )
    assert result.response == "stub says hi" and result.finish_reason == "stop"



# --- PRD-022 STORY-004: adapter dispatch by provider type -----------------------


def _anthropic_yaml(*, key_env="ANTHROPIC_STUB_KEY"):
    return f"""
version: 1
default_model: claude-x
providers:
  - name: ant
    label: Anthropic
    type: anthropic
    base_url: https://api.anthropic.com
    key_env: {key_env}
    models:
      - id: claude-x
        default_max_tokens: 1024
"""


_SECRET_PROMPT = [Message("user", "SECRET-PROMPT-TEXT")]


def _assert_unavailable(error):
    assert error.kind == "incompatible" and error.provider == "ant"
    assert error.retryable is False and error.fallback_eligible is False
    assert "SECRET-PROMPT-TEXT" not in str(error)  # T10: no prompt text in an error


# PRD-022 STORY-005 (D4): replaces test_call_upstream_on_an_anthropic_model_is_incompatible_until_story_005;
# the registry's anthropic type now dispatches to the native adapter instead of failing fast.
def test_call_upstream_dispatches_to_the_anthropic_adapter(provider_file, monkeypatch):
    from app.services.upstream import anthropic as anthropic_mod

    provider_file(_anthropic_yaml(), env={"ANTHROPIC_STUB_KEY": "k"})
    seen = {}

    class _Messages:
        def create(self, **body):
            seen["body"] = body
            return types.SimpleNamespace(
                content=[types.SimpleNamespace(type="text", text="hello")],
                stop_reason="end_turn",
                model="claude-x-upstream",
                usage=types.SimpleNamespace(input_tokens=2, output_tokens=3),
            )

    class _Client:
        messages = _Messages()

        def close(self):
            seen["closed"] = True

    monkeypatch.setattr(anthropic_mod, "_open_sdk_client", lambda provider, key: _Client())
    result = call_upstream(_SECRET_PROMPT, model="claude-x")
    assert result.response == "hello" and result.model_used == "claude-x"
    assert seen["body"]["max_tokens"] == 1024 and seen["closed"] is True


# PRD-022 STORY-007 (D4): replaces test_stream_upstream_on_an_anthropic_model_is_incompatible_at_call_time;
# AnthropicAdapter.stream is real now, so the seam streams through the registry and the key checks
# stay eager while the network stays lazy.
def test_stream_upstream_on_an_anthropic_model_streams_through_the_adapter(provider_file, stub):
    port, _ = stub(
        {"default": {"content": "stub says hi", "usage": {
            "prompt_tokens": 10, "completion_tokens": 4,
            "cache_creation_input_tokens": 3, "cache_read_input_tokens": 2,
        }}},
        require_key="k",
    )
    provider_file(
        _anthropic_yaml().replace(
            "base_url: https://api.anthropic.com", f"base_url: http://127.0.0.1:{port}\n    insecure_http: true"
        ),
        env={"ANTHROPIC_STUB_KEY": "k"},
    )
    server = stub.servers[-1][0]
    with pytest.raises(UpstreamError, match="No provider route for the requested model"):
        stream_upstream(_SECRET_PROMPT, model="nope/none")
    events = stream_upstream(_SECRET_PROMPT, model="claude-x")
    assert server.endpoint_hits() == {"chat": 0, "messages": 0}  # lazy: nothing sent before next()
    drained = list(events)
    assert server.endpoint_hits() == {"chat": 0, "messages": 1}
    assert isinstance(drained[0], TextDelta) and drained[-1] == Finish("stop")
    report = next(e for e in drained if isinstance(e, UsageReport))
    assert (report.prompt_tokens, report.completion_tokens, report.total_tokens) == (15, 4, 19)
    assert (report.cache_write_tokens, report.cache_read_tokens) == (3, 2)


def test_stream_upstream_on_an_anthropic_model_refuses_a_keyless_route_at_call_time(provider_file, monkeypatch):
    provider_file(_anthropic_yaml(), env={"ANTHROPIC_STUB_KEY": "k"})
    monkeypatch.setattr(provider_registry, "api_key_for", lambda provider: None)
    with pytest.raises(UpstreamError) as excinfo:  # raised by the call, not the first next()
        stream_upstream(_SECRET_PROMPT, model="claude-x")
    assert excinfo.value.kind == "misconfigured" and "SECRET-PROMPT-TEXT" not in str(excinfo.value)


def test_keyless_anthropic_route_is_misconfigured_before_dispatch(provider_file, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_STUB_KEY", raising=False)
    # key_env must be set to load (F-rule), so unset it after the registry is built.
    provider_file(_anthropic_yaml(), env={"ANTHROPIC_STUB_KEY": "k"})
    monkeypatch.setattr(provider_registry, "api_key_for", lambda provider: None)
    for seam in (call_upstream, stream_upstream):
        with pytest.raises(UpstreamError) as excinfo:
            seam(_SECRET_PROMPT, model="claude-x")
        assert excinfo.value.kind == "misconfigured"


def test_openai_compatible_dispatch_builds_one_adapter_with_provider_and_client(provider_file, monkeypatch):
    provider_file(_yaml(1, reasoning=False))
    builds = []

    class _Spy:
        def __init__(self, provider, client):
            builds.append((provider, client))

        def complete(self, request, api_key):
            return upstream.UpstreamResult("ok", "s/m", 1)

        def stream(self, request, api_key, *, reasoning=False):
            return iter(())

    monkeypatch.setitem(upstream._ADAPTER_FACTORIES, "openai_compatible", _Spy)
    client = httpx.Client()
    try:
        call_upstream(_MSG, model="s/m", client=client)
        stream_upstream(_MSG, model="s/m", client=client)
    finally:
        client.close()
    provider = provider_registry.resolve("s/m").provider
    assert builds == [(provider, client), (provider, client)]
