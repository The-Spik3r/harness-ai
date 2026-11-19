"""PRD-021 STORY-006: the streamed arm of step 7 in `run_conversation`.

Sections 6.1, 6.2, 6.3; F2, F4, F6; D4, D6, D8, D13, D17, D20; T1, T6. Scripted
generators stand in for `stream_upstream`. What is pinned:

- `committed` once, on the first event, with a `chatcmpl-harness-rt-` id; a
  buffered call commits on entry; an iterator that raises first never commits;
  `sink=None` is today's path (no stream, no phase, no id);
- phases: `waiting`, then changes only; non-empty text/reasoning forwarded in
  order, reasoning only with both grants; tool-call fragments never reach a
  sink (T1) and step 7c decides over the assembled calls as before;
- usage: realtime estimates a missing usage chunk, progress-only does not;
- a fault after a release charges the estimate of everything received before
  the failure row, one before a release charges nothing (T6);
- the total deadline, end to end through the default `stream_upstream` (D20).
"""

import io
import os
import re
import threading

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import pytest

import app.services.authz as authz
import app.services.query_pipeline as query_pipeline
from app.config import settings
from app.db.database import get_audit_log, get_connection
from app.models.messages import Message, ToolCallSpec
from app.models.schemas import QuerySuccessResponse
from app.services.identity import Identity
from app.services.openrouter_client import OpenRouterError, OpenRouterResult
from app.services.upstream import (
    Finish,
    ReasoningDelta,
    TextDelta,
    ToolCallDelta,
    ToolParams,
    UpstreamError,
    UsageReport,
)
from app.services.usage_estimate import estimate_tokens
from scripts.stub_openrouter import make_server, parse_script
from tests._providers import provider_file  # noqa: F401  (fixture)

_JUAN = Identity(user_id="juan@empresa.com", role="user")
_YAML = """
version: 1
default_model: s/m
providers:
  - name: s
    label: Stub
    type: openai_compatible
    base_url: http://127.0.0.1:{port}/v1
    insecure_http: true
    usage_missing: {usage_missing}
    byok: true
    estimate_chars_per_token: 1
    timeout_seconds: {timeout}
    models:
      - id: s/m
        upstream: up-m
        capabilities: {{streaming: true, reasoning: true}}
"""
_ID = re.compile(r"^chatcmpl-harness-rt-[0-9a-f]{32}$")
_SUBMIT = authz.PERMISSION_QUERY_SUBMIT
_RT = authz.PERMISSION_STREAM_REALTIME
_RV = authz.PERMISSION_REASONING_VIEW


class _Recorder:
    def __init__(self, log=None):
        self.calls = []
        self.log = log if log is not None else self.calls

    def stage(self, name):
        pass

    def phase(self, name, action_kind=None):
        self.log.append(("phase", name, action_kind))

    def content(self, text):
        self.log.append(("content", text))

    def reasoning(self, text):
        self.log.append(("reasoning", text))

    def committed(self, completion_id):
        self.log.append(("committed", completion_id))

    def of(self, kind):
        return [c[1] for c in self.log if c[0] == kind]


def _stream(events, then=None):
    """A `stream_upstream` stub yielding `events`, then raising `then` if given."""

    def fake(messages, model="gpt-4", api_key=None, params=None, *, tools=None):
        yield from events
        if then is not None:
            raise then

    return fake


def _buffered(response="Hi there!", calls=()):
    def fake(messages, model="gpt-4", api_key=None, params=None, *, tools=None):
        return OpenRouterResult(
            response=response, model_used=model, tokens_used=12, tool_calls=tuple(calls),
            finish_reason="tool_calls" if calls else "stop",
        )

    return fake


def _no_buffered(*a, **k):
    raise AssertionError("call_openrouter must not run on the streamed arm")


def _no_stream(*a, **k):
    raise AssertionError("stream_upstream must not run on the buffered arm")


_USAGE = UsageReport(prompt_tokens=3, completion_tokens=4, total_tokens=7)


def _run(sink, *, prompt="hello world", stream=None, buffered=None, ingress=None,
         profile="chat", identity=_JUAN, tools=None):
    return query_pipeline.run_conversation(
        identity, [Message("user", prompt)], "laptop", "s/m", None,
        call_openrouter=buffered or _no_buffered,
        stream_upstream=stream or _no_stream,
        ingress=ingress, profile=profile, sink=sink, tools=tools,
    )


@pytest.fixture
def setup(temp_db, provider_file, monkeypatch):
    """A file-mode registry with a streaming + reasoning model; grants per test."""

    def configure(grants=(_SUBMIT, _RT, _RV), usage_missing="estimate", port=9, timeout=30):
        provider_file(_YAML.format(port=port, usage_missing=usage_missing, timeout=timeout))
        monkeypatch.setattr(authz, "ROLE_PERMISSIONS", {"user": set(grants)})

    monkeypatch.setattr(settings, "USAGE_LIMITS_ENABLED", True)
    monkeypatch.setattr(settings, "PII_REDACTION_ENABLED", True)
    monkeypatch.setattr(settings, "STREAMING_ENABLED", True)
    monkeypatch.setattr(settings, "USAGE_REQUESTS_PER_MINUTE", "*=60")
    monkeypatch.setattr(settings, "USAGE_DAILY_TOKEN_BUDGET", "*=1000000")
    configure()
    return configure


def _last_row():
    with get_connection() as conn:
        row = conn.execute("SELECT id FROM audit_logs ORDER BY id DESC LIMIT 1").fetchone()
    return get_audit_log(row["id"])


# --- AC1: commit and id ---------------------------------------------------------


def test_committed_once_on_first_event_with_rt_id(setup):
    rec = _Recorder()
    events = [TextDelta("Hel"), TextDelta("lo"), Finish("stop"), _USAGE]
    result = _run(rec, stream=_stream(events))

    assert isinstance(result, QuerySuccessResponse) and result.response == "Hello"
    committed = rec.of("committed")
    assert len(committed) == 1 and _ID.match(committed[0])
    kinds = [c[0] for c in rec.log]
    assert kinds.index("committed") < kinds.index("content")
    # The same answer a buffered run returns (7b/7c/8 are unchanged).
    twin = _run(None, prompt="another question", buffered=_buffered("Hello"))
    assert (result.response, result.model_used) == (twin.response, twin.model_used)


def test_buffered_commits_on_entry(setup):
    setup(grants=(_SUBMIT,))  # no real time, no chat ingress: nothing is streamed
    log = []
    rec = _Recorder(log)

    def buffered(messages, model="gpt-4", api_key=None, params=None, *, tools=None):
        log.append(("upstream",))
        return _buffered()(messages, model)

    _run(rec, buffered=buffered)
    assert [c[0] for c in log][:3] == ["phase", "committed", "upstream"]
    assert _ID.match(rec.of("committed")[0]) and len(rec.of("committed")) == 1


def test_no_commit_when_iterator_raises_first(setup):
    rec = _Recorder()
    with pytest.raises(OpenRouterError):
        _run(rec, stream=_stream([], then=UpstreamError("boom", retryable=True)))
    assert rec.of("committed") == []
    assert _last_row().success is False


def test_sink_none_is_todays_path(setup):
    result = _run(None, buffered=_buffered("plain"))
    assert isinstance(result, QuerySuccessResponse) and result.response == "plain"


# --- AC2: phases ------------------------------------------------------------------


def test_waiting_then_changes_only(setup):
    rec = _Recorder()
    events = [
        ReasoningDelta("hm"), ReasoningDelta("m"), TextDelta(""), TextDelta("a"), TextDelta("b"),
        ToolCallDelta(0, id="c1", name="bash", arguments="{"),
        ToolCallDelta(0, arguments="}"),
        ToolCallDelta(1, id="c2", name="read", arguments="{}"),
        Finish("tool_calls"), _USAGE,
    ]
    _run(rec, stream=_stream(events))
    assert [(c[1], c[2]) for c in rec.log if c[0] == "phase"] == [
        ("waiting", None), ("thinking", None), ("writing", None), ("preparing_action", "shell"),
    ]


# --- AC3: forwarding ---------------------------------------------------------------


def test_content_in_order_skips_empty(setup):
    rec = _Recorder()
    _run(rec, stream=_stream([TextDelta("a"), TextDelta(""), TextDelta("b"), Finish("stop"), _USAGE]))
    assert rec.of("content") == ["a", "b"]


@pytest.mark.parametrize(
    "grants,expected",
    [((_SUBMIT, _RT, _RV), ["why"]), ((_SUBMIT, _RT), []), ((_SUBMIT, _RV), [])],
)
def test_reasoning_only_with_both_grants(setup, grants, expected):
    setup(grants=grants)
    rec = _Recorder()
    # Without the real-time grant the chat ingress still streams, progress only.
    _run(rec, ingress="chat",
         stream=_stream([ReasoningDelta("why"), TextDelta("a"), Finish("stop"), _USAGE]))
    assert rec.of("reasoning") == expected
    if _RT not in grants:
        assert rec.of("content") == []


_FRAGMENTS = ["{", '"comm', 'and": "', "DROP ", "TABLE ", "users", ";", '"', "}"]


def _call_events():
    events = [TextDelta("before ")]
    events.append(ToolCallDelta(0, id="c1", name="bash", arguments=_FRAGMENTS[0]))
    events += [ToolCallDelta(0, arguments=f) for f in _FRAGMENTS[1:]]
    return events + [TextDelta("after"), Finish("tool_calls"), _USAGE]


def test_no_tool_fragment_reaches_any_sink_method(setup):
    rec = _Recorder()
    _run(rec, stream=_stream(_call_events()))
    everything = repr(rec.log)
    for fragment in ("DROP", "TABLE", "users", "command"):
        assert fragment not in everything
    assert rec.of("content") == ["before ", "after"]


def test_7c_runs_over_collect_calls(setup):
    call = ToolCallSpec("c1", "bash", "".join(_FRAGMENTS))
    offered = ToolParams(tools=[{"type": "function", "function": {"name": "bash", "parameters": {}}}])
    streamed = _run(_Recorder(), prompt="drop it one", stream=_stream(_call_events()), tools=offered)
    buffered = _run(None, prompt="drop it two", buffered=_buffered("before after", calls=(call,)),
                    tools=offered)
    assert streamed.tool_outcome is not None
    assert [d.decision for d in streamed.tool_outcome.decisions] == [
        d.decision for d in buffered.tool_outcome.decisions
    ]
    assert streamed.tool_outcome.release.tool_calls == buffered.tool_outcome.release.tool_calls


# --- AC4: usage mode ----------------------------------------------------------------


def test_realtime_missing_usage_is_estimated_on_error_provider(setup):
    setup(usage_missing="error")
    result = _run(_Recorder(), stream=_stream([TextDelta("abcd"), Finish("stop")]))
    assert isinstance(result, QuerySuccessResponse) and result.tokens_used > 0
    assert _last_row().usage_estimated is True


def test_progress_only_error_provider_still_raises(setup):
    setup(grants=(_SUBMIT,), usage_missing="error")
    rec = _Recorder()
    with pytest.raises(OpenRouterError):
        _run(rec, ingress="chat", stream=_stream([TextDelta("abcd"), Finish("stop")]))
    assert rec.of("content") == []  # nothing was released, so nothing is charged


# --- AC5: a fault mid-stream -----------------------------------------------------------


@pytest.fixture
def spies(monkeypatch):
    order = []
    charges = []
    real_log = query_pipeline.log_query

    def charge(*args):
        charges.append(args)
        order.append("charge")

    def log_query(**kwargs):
        order.append("log_failure" if kwargs.get("success") is False else "log")
        return real_log(**kwargs)

    monkeypatch.setattr(query_pipeline, "charge", charge)
    monkeypatch.setattr(query_pipeline, "log_query", log_query)
    return order, charges


def test_fault_after_release_charges_estimate_before_failure_row(setup, spies):
    order, charges = spies
    fault = UpstreamError("connection dropped", retryable=True)
    with pytest.raises(OpenRouterError):
        _run(_Recorder(), prompt="count me",
             stream=_stream([TextDelta("abc"), TextDelta("de")], then=fault))
    assert order == ["charge", "log_failure"]
    (user, _day, input_tokens, output_tokens, total), = charges
    assert (user, input_tokens, output_tokens) == (_JUAN.user_id, None, None)
    assert total == estimate_tokens([Message("user", "count me")], ("abcde", ()), 1.0)
    assert _last_row().success is False


def test_fault_before_release_charges_nothing(setup, spies):
    order, charges = spies
    with pytest.raises(OpenRouterError):
        _run(_Recorder(), stream=_stream([TextDelta("")], then=UpstreamError("x", retryable=True)))
    assert charges == [] and order == ["log_failure"]


def test_fault_counts_everything_received_including_held_calls_and_reasoning(setup, spies):
    _order, charges = spies
    events = [
        ReasoningDelta("think"),  # forwarded (both grants), so something was released
        ToolCallDelta(0, id="c1", name="bash", arguments='{"command": '),
        ToolCallDelta(0, arguments='"ls"}'),
    ]
    with pytest.raises(OpenRouterError):
        _run(_Recorder(), prompt="count me",
             stream=_stream(events, then=UpstreamError("x", retryable=True)))
    (_u, _d, _i, _o, total), = charges
    held = ToolCallSpec("c1", "bash", '{"command": "ls"}')
    assert total == estimate_tokens([Message("user", "count me")], ("think", (held,)), 1.0)
    without_call = estimate_tokens([Message("user", "count me")], ("think", ()), 1.0)
    assert total > without_call  # the held arguments raise the estimate


def test_fault_charges_nothing_for_a_byok_caller(setup, spies):
    setup(grants=(_SUBMIT, _RT, authz.PERMISSION_QUERY_BYOK))
    _order, charges = spies
    with pytest.raises(OpenRouterError):
        query_pipeline.run_conversation(
            _JUAN, [Message("user", "hi")], "laptop", "s/m", "sk-own-key",
            call_openrouter=_no_buffered,
            stream_upstream=_stream([TextDelta("abc")], then=UpstreamError("x", retryable=True)),
            sink=_Recorder(),
        )
    assert charges == []


# --- D20: the total deadline end to end ------------------------------------------------


def test_total_deadline_through_the_default_stream_upstream(setup):
    script = {"rules": [], "default": {"content": "x" * 100, "stream": {"chunk_chars": 1, "delay_ms": 50}}}
    server = make_server(parse_script(script), log=io.StringIO())
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    try:
        setup(port=server.server_address[1], timeout=0.5)
        rec = _Recorder()
        with pytest.raises(OpenRouterError) as excinfo:
            query_pipeline.run_conversation(
                _JUAN, [Message("user", "slow please")], "laptop", "s/m", None,
                call_openrouter=_no_buffered, sink=rec,
            )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    assert excinfo.value.retryable is True
    assert _last_row().success is False
