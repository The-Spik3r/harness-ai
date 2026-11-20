"""PRD-022 STORY-014: streamed requests through the chain (6.6, D9, D10, F5, F7, F8).

    AC1  a fault before the first release falls back inside the same response
    AC2  a fault after a release is never retried: one charged failure row, an SSE `error`
    AC3  a candidate that does not declare `streaming` is skipped `capability`
    AC4  fresh per-attempt state: held text never leaks, an empty delta never closes the window
    AC5  no chain: one `stream_upstream` call with today's arguments

Exactly one audit row per attempt in every case: each test counts the rows by `attempt`.
Scripted generators stand in for `stream_upstream`; `chain.run` is real. The registry's
candidates declare `streaming: true` (the chain-test registry does not).
"""

import functools
import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import pytest
from fastapi.testclient import TestClient

import app.services.authz as authz
import app.services.query_pipeline as query_pipeline
from app.config import settings
from app.db.database import insert_user
from app.db.models import User
from app.main import app
from app.models.messages import Message
from app.models.schemas import QuerySuccessResponse
from app.services.identity import Identity, hash_token
from app.services.openrouter_client import OpenRouterError
from app.services.pii_redactor import PiiRedactorError
from app.services.query_pipeline import run_conversation
from app.services.upstream import (
    Finish,
    ReasoningDelta,
    TextDelta,
    UpstreamError,
    UsageReport,
    health,
)
from app.services.upstream.types import ChainExhausted
from app.services.usage_estimate import estimate_tokens
from tests._providers import chains_file, provider_file  # noqa: F401  (fixtures)
from tests.test_audit_characterization import _audit_rows_since, _last_audit_id

_USER_ID = "juan@empresa.com"
_TOKEN = "test-user-token"
_JUAN = Identity(user_id=_USER_ID, role="user")
_SUBMIT = authz.PERMISSION_QUERY_SUBMIT
_RT = authz.PERMISSION_STREAM_REALTIME
_RV = authz.PERMISSION_REASONING_VIEW
_USAGE = UsageReport(prompt_tokens=3, completion_tokens=4, total_tokens=7)

# a, b stream; c does not declare `streaming`.
_REGISTRY = """
version: 1
default_model: a/m
providers:
  - name: a
    label: A
    type: openai_compatible
    base_url: http://127.0.0.1:9/v1
    insecure_http: true
    byok: true
    estimate_chars_per_token: 1
    models:
      - id: a/m
        upstream: up-a
        capabilities: {streaming: true, reasoning: true}
      - id: a/cap
        upstream: up-acap
        capabilities: {streaming: true, reasoning: true}
  - name: b
    label: B
    type: openai_compatible
    base_url: http://127.0.0.1:9/v1
    insecure_http: true
    estimate_chars_per_token: 1
    models:
      - id: b/m
        upstream: up-b
        capabilities: {streaming: true, reasoning: true}
  - name: c
    label: C
    type: openai_compatible
    base_url: http://127.0.0.1:9/v1
    insecure_http: true
    models:
      - id: c/m
        upstream: up-c
"""

_CHAINS = """
version: 1
chains:
  - match: {model: a/m}
    candidates:
      - {model: a/m}
      - {model: b/m}
  - match: {model: a/cap}
    candidates:
      - {model: a/cap}
      - {model: c/m, capability_scoped: true}
      - {model: b/m}
"""


@pytest.fixture(autouse=True)
def _health():
    health.reset()
    yield
    health.reset()


@pytest.fixture
def setup(temp_db, provider_file, chains_file, monkeypatch):  # noqa: F811
    insert_user(User(user_id=_USER_ID, role="user", token_hash=hash_token(_TOKEN)))
    monkeypatch.setattr(settings, "USAGE_LIMITS_ENABLED", True)
    monkeypatch.setattr(settings, "PII_REDACTION_ENABLED", True)
    monkeypatch.setattr(settings, "STREAMING_ENABLED", True)
    monkeypatch.setattr(settings, "USAGE_REQUESTS_PER_MINUTE", "*=600")
    monkeypatch.setattr(settings, "USAGE_DAILY_TOKEN_BUDGET", "*=1000000")
    monkeypatch.setattr(
        authz, "ROLE_PERMISSIONS",
        {"user": {_SUBMIT, _RT, _RV, authz.PERMISSION_QUERY_BYOK}},
    )
    provider_file(_REGISTRY)
    chains_file(_CHAINS)


class _Recorder:
    def __init__(self):
        self.log = []

    def stage(self, name):
        pass

    def phase(self, name, action_kind=None):
        self.log.append(("phase", name))

    def content(self, text):
        self.log.append(("content", text))

    def reasoning(self, text):
        self.log.append(("reasoning", text))

    def committed(self, completion_id):
        self.log.append(("committed", completion_id))

    def of(self, kind):
        return [c[1] for c in self.log if c[0] == kind]


class _Streams:
    """A `stream_upstream` stub: `script[model]` is `(events, then)`; records every call."""

    def __init__(self, script):
        self.script = script
        self.calls = []  # (model, api_key, kwargs)

    def __call__(self, messages, model, api_key=None, **kw):
        self.calls.append((model, api_key, kw))
        events, then = self.script.get(model, ([TextDelta("answer. "), Finish("stop"), _USAGE], None))
        yield from events
        if then is not None:
            raise then

    @property
    def models(self):
        return [c[0] for c in self.calls]


def _503():
    return UpstreamError("unavailable", upstream_status=503, retryable=True)


_OK = ([TextDelta("clean answer. "), Finish("stop"), _USAGE], None)


def _run(streams, *, model="a/m", profile="chat", rec=None, api_key=None, prompt="hello world"):
    return run_conversation(
        _JUAN, [Message("user", prompt)], "pytest/stream", model, api_key,
        call_openrouter=lambda *a, **k: pytest.fail("buffered arm must not run"),
        stream_upstream=streams, ingress="chat", profile=profile, sink=rec or _Recorder(),
    )


def _attempts(before):
    """(attempt, success) per row since `before`: the single-write proof."""
    return [(r.attempt, r.success) for r in _audit_rows_since(before)]


@pytest.fixture
def charges(monkeypatch):
    order = []
    seen = []
    real_log = query_pipeline.log_query

    def charge(*args):
        seen.append(args)
        order.append("charge")

    def log_query(**kwargs):
        order.append("log_failure" if kwargs.get("success") is False else "log")
        return real_log(**kwargs)

    monkeypatch.setattr(query_pipeline, "charge", charge)
    monkeypatch.setattr(query_pipeline, "log_query", log_query)
    return order, seen


# --- AC1: fall back before the first release ----------------------------------------------


def test_open_error_before_any_event_falls_back(setup):
    before, rec = _last_audit_id(), _Recorder()
    streams = _Streams({"a/m": ([], _503()), "b/m": _OK})

    result = _run(streams, rec=rec)

    assert isinstance(result, QuerySuccessResponse) and result.model_used == "b/m"
    assert streams.models == ["a/m", "b/m"]
    assert len(rec.of("committed")) == 1
    assert _attempts(before) == [(1, False), (2, True)]
    failed, answered = _audit_rows_since(before)
    assert failed.route_model == "a/m" and answered.route_model == "b/m"
    assert failed.input_tokens is None and failed.fallback_reason is None
    assert answered.fallback_reason  # the closed-vocabulary reason of the failed attempt


def test_events_then_error_before_release_falls_back_with_no_leak(setup, charges):
    _order, seen = charges
    before, rec = _last_audit_id(), _Recorder()
    # Chat holds text without a boundary: nothing of the primary's is released.
    streams = _Streams({
        "a/m": ([TextDelta("PRIMARY-SECRET text with no boundary")], _503()),
        "b/m": _OK,
    })

    result = _run(streams, rec=rec)

    assert result.model_used == "b/m" and streams.models == ["a/m", "b/m"]
    assert len(rec.of("committed")) == 1
    assert rec.of("phase").count("waiting") >= 2  # a fallback restarts the wait (6.6)
    shown = "".join(rec.of("content"))
    assert "PRIMARY-SECRET" not in shown and shown.strip() == "clean answer."
    assert "PRIMARY-SECRET" not in result.response
    # Nothing of the primary was released, so only the answering attempt is charged (T6, 7b).
    assert [c[2:] for c in seen] == [(3, 4, 7)]
    assert _attempts(before) == [(1, False), (2, True)]
    failed, answered = _audit_rows_since(before)
    assert "PRIMARY-SECRET" not in (failed.error_message or "")
    assert answered.success is True
    assert failed.input_tokens is None and failed.output_tokens is None


# --- AC2: after a release, never retried ----------------------------------------------------


def test_fault_after_release_is_not_retried_and_is_charged_once(setup, charges):
    order, seen = charges
    before, rec = _last_audit_id(), _Recorder()
    # `code` has no output redaction: the deltas are released at once.
    streams = _Streams({"a/m": ([TextDelta("abc"), TextDelta("de")], _503()), "b/m": _OK})

    with pytest.raises(OpenRouterError):
        _run(streams, rec=rec, profile="code", prompt="count me")

    assert streams.models == ["a/m"]
    assert rec.of("content") == ["abc", "de"]
    assert order == ["charge", "log_failure"]
    (user, _day, input_tokens, output_tokens, total), = seen
    assert (user, input_tokens, output_tokens) == (_USER_ID, None, None)
    assert total == estimate_tokens([Message("user", "count me")], ("abcde", ()), 1.0)
    assert _attempts(before) == [(1, False)]


def test_reasoning_release_closes_the_window_like_content(setup):
    before, rec = _last_audit_id(), _Recorder()
    streams = _Streams({"a/m": ([ReasoningDelta("think. ")], _503()), "b/m": _OK})

    with pytest.raises(OpenRouterError):
        _run(streams, rec=rec, profile="code")

    assert streams.models == ["a/m"] and rec.of("reasoning") == ["think. "]
    assert _attempts(before) == [(1, False)]
    (row,) = _audit_rows_since(before)
    assert row.reasoning_shown is True


# --- AC3: capability -------------------------------------------------------------------------


def test_candidate_without_streaming_is_skipped_capability(setup):
    before = _last_audit_id()
    streams = _Streams({"a/cap": ([], _503()), "b/m": _OK})

    result = _run(streams, model="a/cap")

    assert result.model_used == "b/m" and streams.models == ["a/cap", "b/m"]
    assert _attempts(before) == [(1, False), (2, True)]
    answered = _audit_rows_since(before)[1]
    assert answered.skipped_providers == "c:capability"


# --- AC4: fresh state --------------------------------------------------------------------------


def test_529_in_stream_falls_back_and_an_empty_delta_does_not_close_the_window(setup):
    before = _last_audit_id()
    err = UpstreamError("overloaded", upstream_status=529, retryable=True)
    streams = _Streams({"a/m": ([TextDelta("")], err), "b/m": _OK})

    result = _run(streams)

    assert result.model_used == "b/m" and streams.models == ["a/m", "b/m"]
    assert _attempts(before) == [(1, False), (2, True)]


@pytest.mark.parametrize("raise_from", [1, 2])
def test_gate_failure_never_falls_back_and_writes_one_row(setup, charges, monkeypatch, raise_from):
    _order, seen = charges
    before, rec = _last_audit_id(), _Recorder()
    calls = []
    real_feed = query_pipeline.OutputGate.feed

    # The gate's pass, not step 6's input redaction (that fault has its own row, no attempt).
    def flaky(self, text):
        calls.append(text)
        if len(calls) >= raise_from:
            raise PiiRedactorError("redactor down")
        return real_feed(self, text)

    monkeypatch.setattr(query_pipeline.OutputGate, "feed", flaky)
    streams = _Streams({
        "a/m": ([TextDelta("One. "), TextDelta("Two. "), Finish("stop"), _USAGE], None),
        "b/m": _OK,
    })

    with pytest.raises(PiiRedactorError):
        _run(streams, rec=rec)

    assert streams.models == ["a/m"]  # fail closed: never a fallback
    # T6: charged iff something was released, once.
    assert len(seen) == (1 if rec.of("content") else 0)
    assert _attempts(before) == [(1, False)]
    (row,) = _audit_rows_since(before)
    assert row.route_model == "a/m"


def test_gate_failure_unchained_still_writes_one_row(setup, monkeypatch):
    before = _last_audit_id()

    def broken(self, text):
        raise PiiRedactorError("redactor down")

    monkeypatch.setattr(query_pipeline.OutputGate, "feed", broken)
    streams = _Streams({"b/m": _OK})

    with pytest.raises(PiiRedactorError):
        _run(streams, model="b/m")

    assert _attempts(before) == [(1, False)]


# --- exhaustion: one failure row per attempt, no exhaustion row -----------------------------


def test_every_candidate_fails_before_commit(setup):
    before, rec = _last_audit_id(), _Recorder()
    streams = _Streams({"a/m": ([], _503()), "b/m": ([], _503())})

    with pytest.raises(ChainExhausted):
        _run(streams, rec=rec)

    assert rec.of("committed") == []
    assert _attempts(before) == [(1, False), (2, False)]


def test_every_candidate_fails_after_commit(setup):
    before, rec = _last_audit_id(), _Recorder()
    streams = _Streams({"a/m": ([TextDelta("")], _503()), "b/m": ([TextDelta("")], _503())})

    with pytest.raises(ChainExhausted):
        _run(streams, rec=rec)

    assert len(rec.of("committed")) == 1  # one commit across both attempts
    assert _attempts(before) == [(1, False), (2, False)]


@pytest.fixture
def v1(setup, monkeypatch):
    monkeypatch.setattr(settings, "PII_REDACTION_ENABLED", False)  # raw forward
    monkeypatch.setattr(settings, "STREAM_COALESCE_MS", 0)

    def post(streams):
        monkeypatch.setattr(
            "app.routers.v1.run_conversation",
            functools.partial(run_conversation, stream_upstream=streams),
        )
        client = TestClient(app, headers={"Authorization": f"Bearer {_TOKEN}"})
        return client.post(
            "/v1/chat/completions",
            json={"model": "a/m", "stream": True, "messages": [{"role": "user", "content": "hi"}]},
        )

    return post


def test_v1_exhaustion_before_commit_is_a_json_502(setup, v1):
    before = _last_audit_id()

    response = v1(_Streams({"a/m": ([], _503()), "b/m": ([], _503())}))

    assert response.status_code == 502, response.text
    assert "error" in response.json()
    assert _attempts(before) == [(1, False), (2, False)]


def test_v1_exhaustion_after_commit_is_an_sse_error_event(setup, v1):
    before = _last_audit_id()

    response = v1(_Streams({"a/m": ([TextDelta("")], _503()), "b/m": ([TextDelta("")], _503())}))

    assert response.status_code == 200
    assert '"error"' in response.text and "[DONE]" not in response.text
    assert _attempts(before) == [(1, False), (2, False)]


def test_v1_fault_after_release_is_an_sse_error_and_one_attempt(setup, v1):
    before = _last_audit_id()
    streams = _Streams({"a/m": ([TextDelta("partial answer")], _503()), "b/m": _OK})

    response = v1(streams)

    assert response.status_code == 200
    assert '"error"' in response.text and "[DONE]" not in response.text
    assert streams.models == ["a/m"]
    assert _attempts(before) == [(1, False)]


def test_v1_fallback_before_release_streams_the_answer_once(setup, v1):
    before = _last_audit_id()
    streams = _Streams({"a/m": ([], _503()), "b/m": _OK})

    response = v1(streams)

    assert response.status_code == 200
    assert "clean answer." in response.text and '"error"' not in response.text
    assert response.text.count('"role": "assistant"') + response.text.count('"role":"assistant"') <= 1
    assert _attempts(before) == [(1, False), (2, True)]


# --- D15, deadline, AC5 --------------------------------------------------------------------


def test_chained_stream_passes_timeout_and_the_key_only_to_the_primary(setup):
    streams = _Streams({"a/m": ([], _503()), "b/m": _OK})
    _run(streams)  # no BYOK: the fallback may run
    assert [c[1] for c in streams.calls] == [None, None]
    assert all(isinstance(c[2].get("timeout"), float) for c in streams.calls)

    byok = _Streams({"a/m": ([TextDelta("x. "), Finish("stop"), _USAGE], None)})
    result = _run(byok, api_key="sk-own", prompt="another question")
    assert isinstance(result, QuerySuccessResponse), result
    assert byok.calls[0][1] == "sk-own"  # the primary gets the caller's key


def test_byok_stream_failure_never_reaches_another_provider(setup):
    streams = _Streams({"a/m": ([], _503()), "b/m": _OK})
    with pytest.raises(ChainExhausted):
        _run(streams, api_key="sk-own")
    assert streams.models == ["a/m"]  # b is skipped `byok`: the key never leaves the primary


def test_no_chain_is_one_stream_call_with_todays_arguments(setup):
    before = _last_audit_id()
    streams = _Streams({"b/m": _OK})

    result = _run(streams, model="b/m")

    assert isinstance(result, QuerySuccessResponse)
    assert streams.models == ["b/m"] and "timeout" not in streams.calls[0][2]
    assert _attempts(before) == [(1, True)]
