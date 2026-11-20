"""PRD-022 STORY-002: UpstreamError kind/provider/retry_after, ChainExhausted, cache result fields.

    AC1  defaults, unchanged `str`, the OpenRouterError alias, `/v1` mapping intact
    AC2  the closed `kind` vocabulary and `fallback_eligible` (6.2)
    AC3  the OpenAI-compatible adapter tags kind/provider/retry-after, complete() and stream()
    AC4  `ChainExhausted`
    AC5  cache fields on UsageReport / UpstreamResult, copied by collect()
"""

import json
import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import dataclasses

import httpx
import pytest

from app.config import settings
from app.models.messages import Message
from app.routers.v1 import _fault_code
from app.services import openrouter_client, provider_registry
from app.services import upstream as upstream_pkg
from app.services.upstream import (
    ChainExhausted,
    Finish,
    OpenAICompatibleAdapter,
    TextDelta,
    UpstreamError,
    UpstreamRequest,
    UpstreamResult,
    UsageReport,
    call_upstream,
    collect,
)
from app.services.upstream.types import UPSTREAM_ERROR_KINDS

_KEY = "sk-test-key-PRD022-S2"
_CANARY = "CANARY-value-7c1"
_MSG = [Message("user", "hello")]


def _provider(**changes):
    base = provider_registry.current().providers[0]
    return dataclasses.replace(base, base_url="http://127.0.0.1:1/v1", **changes)


def _request():
    return UpstreamRequest(_MSG, "up-model")


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def _complete_error(handler):
    adapter = OpenAICompatibleAdapter(_provider(), _client(handler))
    with pytest.raises(UpstreamError) as excinfo:
        adapter.complete(_request(), _KEY)
    return excinfo.value


def _stream_error(handler):
    adapter = OpenAICompatibleAdapter(_provider(), _client(handler))
    with pytest.raises(UpstreamError) as excinfo:
        list(adapter.stream(_request(), _KEY))
    return excinfo.value


def _status(status, headers=None, body=None):
    def handler(request):
        return httpx.Response(status, headers=headers, json=body or {"error": _CANARY})

    return handler


def _sse(*payloads, done=True):
    lines = [f"data: {p if isinstance(p, str) else json.dumps(p)}\n\n" for p in payloads]
    if done:
        lines.append("data: [DONE]\n\n")
    return "".join(lines).encode("utf-8")


def _assert_clean(exc):
    assert _CANARY not in str(exc) and _KEY not in str(exc)
    assert _CANARY not in repr(exc.__dict__) and _KEY not in repr(exc.__dict__)


# --------------------------------------------------------------------------
# AC1 / AC2: the error object
# --------------------------------------------------------------------------


def test_defaults_str_and_alias():
    exc = UpstreamError("boom")
    assert str(exc) == "boom"
    assert (exc.upstream_status, exc.retryable) == (None, False)
    assert (exc.provider, exc.kind, exc.retry_after_seconds) == (None, None, None)
    assert openrouter_client.OpenRouterError is UpstreamError


def test_kind_vocabulary_is_closed():
    assert UPSTREAM_ERROR_KINDS == (
        "timeout", "transport", "status", "shape", "refusal",
        "incompatible", "misconfigured", "exhausted",
    )
    for kind in UPSTREAM_ERROR_KINDS:
        assert UpstreamError("x", kind=kind).kind == kind
    with pytest.raises(ValueError, match="nope") as excinfo:
        UpstreamError("x", kind="nope")
    assert "timeout" in str(excinfo.value)


@pytest.mark.parametrize(
    "kind, retryable, eligible",
    [
        ("timeout", True, True),
        ("transport", True, True),
        ("status", True, True),  # 5xx / 429
        ("status", False, False),  # other 4xx
        ("misconfigured", False, True),  # 401: the provider's own key (D8)
        ("shape", False, False),
        ("refusal", False, False),
        ("incompatible", False, False),
        ("exhausted", True, True),
        (None, False, False),
        (None, True, True),
    ],
)
def test_fallback_eligible_table(kind, retryable, eligible):
    assert UpstreamError("x", kind=kind, retryable=retryable).fallback_eligible is eligible


def test_fallback_eligible_is_read_only():
    exc = UpstreamError("x")
    with pytest.raises(AttributeError):
        exc.fallback_eligible = True


def test_v1_fault_mapping_ignores_the_new_fields():
    assert _fault_code(ChainExhausted([("a", "open")])) == "upstream_unavailable"
    assert _fault_code(UpstreamError("x", kind="misconfigured")) == "upstream_error"
    assert _fault_code(UpstreamError("x", kind="timeout", retryable=True)) == "upstream_unavailable"


# --------------------------------------------------------------------------
# AC3: adapter classification
# --------------------------------------------------------------------------


@pytest.mark.parametrize("path", ["complete", "stream"])
@pytest.mark.parametrize(
    "exc_type, kind",
    [(httpx.ReadTimeout, "timeout"), (httpx.ConnectError, "transport")],
)
def test_transport_faults(path, exc_type, kind):
    def handler(request):
        raise exc_type("down", request=request)

    err = (_complete_error if path == "complete" else _stream_error)(handler)
    assert (err.kind, err.provider, err.retryable, err.upstream_status) == (
        kind, _provider().name, True, None,
    )
    assert err.fallback_eligible and err.retry_after_seconds is None


@pytest.mark.parametrize("path", ["complete", "stream"])
@pytest.mark.parametrize(
    "status, kind, retryable",
    [
        (500, "status", True),
        (503, "status", True),
        (429, "status", True),
        (401, "misconfigured", False),
        (400, "status", False),
        (403, "status", False),
        (404, "status", False),
        (413, "status", False),
        (422, "status", False),
    ],
)
def test_http_status_faults(path, status, kind, retryable):
    err = (_complete_error if path == "complete" else _stream_error)(_status(status))
    assert (err.kind, err.provider, err.retryable, err.upstream_status) == (
        kind, _provider().name, retryable, status,
    )
    assert str(err).startswith(f"{_provider().label} request failed: ")
    _assert_clean(err)


@pytest.mark.parametrize(
    "header, expected",
    [("7", 7), ("0", 1), (" 12 ", 12), ("Wed, 21 Oct 2026 07:28:00 GMT", None), ("-3", None), ("1.5", None), (None, None)],
)
def test_retry_after_on_429(header, expected):
    headers = {"retry-after": header} if header is not None else None
    assert _complete_error(_status(429, headers)).retry_after_seconds == expected
    assert _stream_error(_status(429, headers)).retry_after_seconds == expected


def test_retry_after_is_only_read_on_429():
    assert _complete_error(_status(500, {"retry-after": "7"})).retry_after_seconds is None


def test_redirect_is_a_non_retryable_status_fault():
    def handler(request):
        return httpx.Response(302, headers={"location": f"http://elsewhere/{_CANARY}"})

    err = _complete_error(handler)
    assert (err.kind, err.provider, err.retryable, err.upstream_status) == (
        "status", _provider().name, False, 302,
    )
    assert not err.fallback_eligible
    _assert_clean(err)


@pytest.mark.parametrize(
    "handler",
    [
        lambda request: httpx.Response(200, content=b"not json " + _CANARY.encode()),
        lambda request: httpx.Response(200, json={"nochoices": _CANARY}),
        lambda request: httpx.Response(200, json={"choices": [{"message": {"content": None}}]}),
        lambda request: httpx.Response(200, json={"choices": [{"message": {"content": "x"}}]}),
    ],
)
def test_complete_shape_faults(handler):
    err = _complete_error(handler)
    assert (err.kind, err.provider, err.retryable) == ("shape", _provider().name, False)
    assert not err.fallback_eligible
    _assert_clean(err)


def test_stream_shape_faults():
    name = _provider().name

    def no_finish(request):
        return httpx.Response(200, content=_sse({"choices": [{"delta": {"content": "x"}}]}))

    def bad_chunk(request):
        return httpx.Response(200, content=b"data: {not json " + _CANARY.encode() + b"\n\n")

    for handler in (no_finish, bad_chunk):
        err = _stream_error(handler)
        assert (err.kind, err.provider, err.retryable) == ("shape", name, False)
        _assert_clean(err)


def test_stream_deadline_is_a_timeout(monkeypatch):
    from app.services.upstream import openai_compatible

    ticks = iter([0.0, 1000.0, 2000.0, 3000.0])
    monkeypatch.setattr(openai_compatible.time, "monotonic", lambda: next(ticks))

    def handler(request):
        return httpx.Response(
            200,
            content=_sse(
                {"choices": [{"delta": {"content": "a"}}]},
                {"choices": [{"delta": {}, "finish_reason": "stop"}]},
            ),
        )

    err = _stream_error(handler)
    assert (err.kind, err.retryable, err.provider) == ("timeout", True, _provider().name)


def test_call_upstream_missing_key_is_misconfigured(monkeypatch):
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "")
    with pytest.raises(UpstreamError) as excinfo:
        call_upstream(_MSG, model="any-model")
    err = excinfo.value
    assert err.kind == "misconfigured" and err.fallback_eligible and not err.retryable
    assert err.provider == provider_registry.resolve("any-model").provider.name


def test_call_upstream_errors_before_a_provider_is_known_are_unclassified():
    with pytest.raises(UpstreamError) as excinfo:
        call_upstream([], model="m")
    assert (excinfo.value.kind, excinfo.value.provider) == (None, None)
    assert not excinfo.value.fallback_eligible


# --------------------------------------------------------------------------
# AC4: ChainExhausted
# --------------------------------------------------------------------------


def test_chain_exhausted_fields():
    last = UpstreamError("down", kind="timeout", retryable=True, provider="p")
    exc = ChainExhausted(
        [["a", "open"], ["b", "trust"]], last_error=last, retry_after_seconds=9
    )
    assert isinstance(exc, UpstreamError)
    assert str(exc) == "all providers unavailable"
    assert (exc.kind, exc.retryable, exc.upstream_status, exc.provider) == (
        "exhausted", True, None, None,
    )
    assert exc.skipped == (("a", "open"), ("b", "trust"))
    assert exc.last_error is last and exc.retry_after_seconds == 9
    assert exc.fallback_eligible


def test_chain_exhausted_defaults_and_export():
    exc = ChainExhausted()
    assert exc.skipped == () and exc.last_error is None and exc.retry_after_seconds is None
    assert upstream_pkg.ChainExhausted is ChainExhausted and "ChainExhausted" in upstream_pkg.__all__


# --------------------------------------------------------------------------
# AC5: result fields
# --------------------------------------------------------------------------


def test_result_and_usage_defaults():
    result = UpstreamResult("r", "m", 3)
    assert (result.cache_read_tokens, result.cache_write_tokens, result.reasoning_blocks) == (None, None, 0)
    usage = UsageReport(1, 2, 3)
    assert (usage.cache_read_tokens, usage.cache_write_tokens) == (None, None)
    assert [f.name for f in dataclasses.fields(UpstreamResult)][-3:] == [
        "cache_read_tokens", "cache_write_tokens", "reasoning_blocks",
    ]


def _events(usage):
    return [TextDelta("hi"), usage, Finish("stop")]


def test_collect_copies_the_cache_pair():
    usage = UsageReport(5, 2, 7, cache_read_tokens=4, cache_write_tokens=1)
    result = collect(_events(usage), provider=_provider(), request=_request())
    assert (result.cache_read_tokens, result.cache_write_tokens) == (4, 1)
    assert (result.tokens_used, result.input_tokens, result.output_tokens) == (7, 5, 2)
    assert result.usage_estimated is False and result.reasoning_blocks == 0


def test_collect_takes_the_cache_pair_of_the_last_usage_report():
    events = [
        TextDelta("hi"),
        UsageReport(5, 2, 7, cache_read_tokens=4, cache_write_tokens=1),
        UsageReport(5, 2, 7),
        Finish("stop"),
    ]
    result = collect(events, provider=_provider(), request=_request())
    assert (result.cache_read_tokens, result.cache_write_tokens) == (None, None)


def test_collect_without_usage_has_no_cache_pair():
    result = collect(
        [TextDelta("hi"), Finish("stop")],
        provider=_provider(),
        request=_request(),
        usage_missing="estimate",
    )
    assert (result.cache_read_tokens, result.cache_write_tokens) == (None, None)
