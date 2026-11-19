"""PRD-021 STORY-008: the output and reasoning gates in `run_conversation`.

Sections 6.1, 6.5; D7, D8; T3, T6, T12; Risk 1. Scripted generators stand in for
`stream_upstream`, a recording sink for the reader. What is pinned:

- content: the sink gets only what the gate lets out, the held tail last; an
  entity split across deltas never appears raw; `code` with output off and the
  master switch off forward raw and never reach the final pass;
- step 8: a gated request takes response, entities and bubble from the gate's
  final pass and runs no second redaction; buffered and non-realtime requests
  build no gate;
- divergence: a forced cut logs one WARNING (user, completion id, no content)
  and the final pass is still the response;
- reasoning: redacted per segment in real time, whole on `result.reasoning`
  without the real-time grant, absent without the grant, persisted nowhere;
- faults: a gate failure is the fault of D8/T6: charged after a release, free
  before one, and no raw text follows it.
"""

import logging
import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import pytest

import app.services.authz as authz
import app.services.pii_redactor as pii_redactor
import app.services.query_pipeline as query_pipeline
from app.config import settings
from app.db.database import get_audit_log, get_connection
from app.models.messages import Message
from app.services.identity import Identity
from app.services.openrouter_client import OpenRouterError, OpenRouterResult
from app.services.pii_redactor import PiiRedactorError
from app.services.upstream import Finish, ReasoningDelta, TextDelta, UpstreamError, UsageReport
from app.services.usage_estimate import estimate_tokens
from tests._providers import provider_file  # noqa: F401  (fixture)

_JUAN = Identity(user_id="juan@empresa.com", role="user")
_YAML = """
version: 1
default_model: s/m
providers:
  - name: s
    label: Stub
    type: openai_compatible
    base_url: http://127.0.0.1:9/v1
    insecure_http: true
    usage_missing: estimate
    byok: true
    estimate_chars_per_token: 1
    models:
      - id: s/m
        upstream: up-m
        capabilities: {streaming: true, reasoning: true}
"""
_SUBMIT = authz.PERMISSION_QUERY_SUBMIT
_RT = authz.PERMISSION_STREAM_REALTIME
_RV = authz.PERMISSION_REASONING_VIEW
_USAGE = UsageReport(prompt_tokens=3, completion_tokens=4, total_tokens=7)
_EMAIL = "ana.garcia@example.com"
_SENTENCE = f"Please write to {_EMAIL} today. "


class _Recorder:
    def __init__(self):
        self.log = []

    def stage(self, name):
        self.log.append(("stage", name))

    def phase(self, name, action_kind=None):
        pass

    def content(self, text):
        self.log.append(("content", text))

    def reasoning(self, text):
        self.log.append(("reasoning", text))

    def committed(self, completion_id):
        self.log.append(("committed", completion_id))

    def of(self, kind):
        return [c[1] for c in self.log if c[0] == kind]


def _stream(events, then=None):
    def fake(messages, model="gpt-4", api_key=None, params=None, *, tools=None):
        yield from events
        if then is not None:
            raise then

    return fake


def _no_buffered(*a, **k):
    raise AssertionError("call_openrouter must not run on the streamed arm")


def _no_stream(*a, **k):
    raise AssertionError("stream_upstream must not run on the buffered arm")


def _run(sink, *, prompt="hello world", stream=None, buffered=None, ingress=None, profile="chat"):
    return query_pipeline.run_conversation(
        _JUAN, [Message("user", prompt)], "laptop", "s/m", None,
        call_openrouter=buffered or _no_buffered,
        stream_upstream=stream or _no_stream,
        ingress=ingress, profile=profile, sink=sink,
    )


def _deltas(text, size=7):
    return [TextDelta(text[i:i + size]) for i in range(0, len(text), size)]


@pytest.fixture
def setup(temp_db, provider_file, monkeypatch):
    def configure(grants=(_SUBMIT, _RT, _RV)):
        provider_file(_YAML)
        monkeypatch.setattr(authz, "ROLE_PERMISSIONS", {"user": set(grants)})

    monkeypatch.setattr(settings, "USAGE_LIMITS_ENABLED", True)
    monkeypatch.setattr(settings, "PII_REDACTION_ENABLED", True)
    monkeypatch.setattr(settings, "STREAMING_ENABLED", True)
    monkeypatch.setattr(settings, "USAGE_REQUESTS_PER_MINUTE", "*=60")
    monkeypatch.setattr(settings, "USAGE_DAILY_TOKEN_BUDGET", "*=1000000")
    configure()
    return configure


@pytest.fixture
def spies(monkeypatch):
    order, charges = [], []
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


def _last_row():
    with get_connection() as conn:
        row = conn.execute("SELECT id FROM audit_logs ORDER BY id DESC LIMIT 1").fetchone()
    return get_audit_log(row["id"])


# --- AC1: what the sink gets ---------------------------------------------------------


def test_sink_gets_gate_output_and_never_a_raw_split_entity(setup):
    rec = _Recorder()
    reply = "Hello. " + _SENTENCE + "Bye now"
    result = _run(rec, stream=_stream(_deltas(reply) + [Finish("stop"), _USAGE]))

    content = rec.of("content")
    assert not any(_EMAIL in d or "ana.garcia" in d for d in content)
    assert "".join(content) == result.response
    assert _EMAIL not in result.response and result.pii_redacted
    # The held tail ("Bye now", no boundary) is the last delta, sent at the end.
    assert content[-1].endswith("Bye now")


def test_code_with_output_off_forwards_raw_without_a_final_pass(setup, monkeypatch):
    real = query_pipeline.redact_for_policy

    def no_final_pass(text, policy):
        if _EMAIL in text:  # step 6 still masks the prompt through the same call
            pytest.fail("the final pass must not run when output is off")
        return real(text, policy)

    monkeypatch.setattr(query_pipeline, "redact_for_policy", no_final_pass)
    rec = _Recorder()
    result = _run(rec, profile="code",
                  stream=_stream([TextDelta("a "), TextDelta(_EMAIL), Finish("stop"), _USAGE]))
    assert rec.of("content") == ["a ", _EMAIL]  # raw, delta for delta
    assert result.response == f"a {_EMAIL}" and not result.pii_redacted


def test_master_switch_off_forwards_raw(setup, monkeypatch):
    monkeypatch.setattr(settings, "PII_REDACTION_ENABLED", False)
    rec = _Recorder()
    result = _run(rec, stream=_stream([TextDelta("a "), TextDelta(_EMAIL), Finish("stop"), _USAGE]))
    assert rec.of("content") == ["a ", _EMAIL]
    assert result.response == f"a {_EMAIL}"


# --- AC2: step 8 ---------------------------------------------------------------------


def _count_redact(monkeypatch, needle):
    calls = []
    real = query_pipeline.redact

    def spy(text, *a, **k):
        if text == needle:
            calls.append(text)
        return real(text, *a, **k)

    monkeypatch.setattr(query_pipeline, "redact", spy)
    return calls


def test_gated_request_runs_the_whole_reply_redaction_once(setup, monkeypatch):
    reply = "Hello. " + _SENTENCE + "Bye."
    calls = _count_redact(monkeypatch, reply)
    rec = _Recorder()
    result = _run(rec, stream=_stream(_deltas(reply) + [Finish("stop"), _USAGE]))

    assert len(calls) == 1  # the gate's final pass; step 8 made no second one
    assert ("stage", "masking_output") not in rec.log
    expected_text, expected_entities = pii_redactor.redact(reply)
    assert result.response == expected_text
    assert result.pii_entities_masked == sorted(set(expected_entities))
    assert set(_last_row().pii_entities.split(",")) >= set(expected_entities)  # comma-separated TEXT


def test_buffered_request_builds_no_gate_and_redacts_once(setup, monkeypatch):
    monkeypatch.setattr(query_pipeline, "OutputGate", lambda *a, **k: pytest.fail("no gate expected"))
    reply = "Hello. " + _SENTENCE
    calls = _count_redact(monkeypatch, reply)

    def buffered(messages, model="gpt-4", api_key=None, params=None, *, tools=None):
        return OpenRouterResult(response=reply, model_used=model, tokens_used=12)

    _run(None, buffered=buffered)
    assert len(calls) == 1


def test_chat_ingress_without_realtime_builds_no_gate(setup, monkeypatch):
    setup(grants=(_SUBMIT,))
    monkeypatch.setattr(query_pipeline, "OutputGate", lambda *a, **k: pytest.fail("no gate expected"))
    reply = "Hello. " + _SENTENCE
    calls = _count_redact(monkeypatch, reply)
    rec = _Recorder()
    result = _run(rec, ingress="chat", stream=_stream(_deltas(reply) + [Finish("stop"), _USAGE]))
    assert rec.of("content") == [] and len(calls) == 1
    assert _EMAIL not in result.response


# --- AC3: divergence -----------------------------------------------------------------


def test_forced_cut_across_an_entity_warns_once_and_final_pass_wins(setup, monkeypatch, caplog):
    # No boundary and a 10-character cap: the gate must cut inside the address.
    monkeypatch.setattr(settings, "STREAM_HOLDBACK_MAX_CHARACTERS", 10)
    reply = f"contact {_EMAIL} now"
    rec = _Recorder()
    with caplog.at_level(logging.WARNING, logger="app.services.query_pipeline"):
        result = _run(rec, stream=_stream(_deltas(reply, 3) + [Finish("stop"), _USAGE]))

    warnings = [r for r in caplog.records if "diverged" in r.getMessage()]
    assert len(warnings) == 1
    message = warnings[0].getMessage()
    assert _JUAN.user_id in message and "chatcmpl-harness-rt-" in message
    assert "contact" not in message and "ana" not in message
    assert result.response == pii_redactor.redact(reply)[0]  # authoritative
    assert _EMAIL not in result.response


# --- AC4: reasoning ------------------------------------------------------------------

_THOUGHT = f"SECRETREASONING mail {_EMAIL} first. "


def test_realtime_reasoning_is_redacted_per_segment(setup):
    rec = _Recorder()
    _run(rec, stream=_stream([ReasoningDelta(_THOUGHT[:15]), ReasoningDelta(_THOUGHT[15:]),
                              ReasoningDelta("tail"), TextDelta("ok. "), Finish("stop"), _USAGE]))
    reasoning = rec.of("reasoning")
    assert reasoning and reasoning[-1].endswith("tail")  # the held tail goes last
    assert _EMAIL not in "".join(reasoning) and "SECRETREASONING" in "".join(reasoning)


def test_reasoning_without_realtime_is_returned_whole_and_redacted(setup):
    setup(grants=(_SUBMIT, _RV))
    rec = _Recorder()
    result = _run(rec, ingress="chat", stream=_stream(
        [ReasoningDelta(_THOUGHT[:12]), ReasoningDelta(_THOUGHT[12:]), TextDelta("ok"),
         Finish("stop"), _USAGE]))
    assert rec.of("reasoning") == [] and rec.of("content") == []
    assert result.reasoning is not None and _EMAIL not in result.reasoning
    assert "SECRETREASONING" in result.reasoning
    assert "reasoning" not in result.model_dump()  # private: never serialized


def test_no_reasoning_grant_gives_none(setup):
    setup(grants=(_SUBMIT, _RT))
    rec = _Recorder()
    result = _run(rec, stream=_stream([ReasoningDelta(_THOUGHT), TextDelta("ok. "), Finish("stop"), _USAGE]))
    assert rec.of("reasoning") == [] and result.reasoning is None


def test_realtime_result_carries_no_reasoning(setup):
    result = _run(_Recorder(),
                  stream=_stream([ReasoningDelta(_THOUGHT), TextDelta("ok. "), Finish("stop"), _USAGE]))
    assert result.reasoning is None  # it went to the sink per segment


def test_reasoning_is_in_no_table(setup):
    setup(grants=(_SUBMIT, _RV))
    _run(_Recorder(), ingress="chat",
         stream=_stream([ReasoningDelta(_THOUGHT), TextDelta("ok"), Finish("stop"), _USAGE]))
    with get_connection() as conn:
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        dump = "".join(
            str(tuple(r)) for t in tables for r in conn.execute(f'SELECT * FROM "{t}"').fetchall()
        )
    assert "SECRETREASONING" not in dump


def test_reasoning_master_switch_off_is_unredacted(setup, monkeypatch):
    monkeypatch.setattr(settings, "PII_REDACTION_ENABLED", False)
    rec = _Recorder()
    _run(rec, stream=_stream([ReasoningDelta(_THOUGHT), ReasoningDelta("x"), TextDelta("ok"),
                              Finish("stop"), _USAGE]))
    assert _EMAIL in "".join(rec.of("reasoning"))


# --- T6: gate faults -----------------------------------------------------------------


def _fail_spans_from(monkeypatch, nth):
    """`redaction_spans` works for `nth - 1` calls, then raises."""
    real = pii_redactor.redaction_spans
    count = {"n": 0}

    def spans(*a, **k):
        count["n"] += 1
        if count["n"] >= nth:
            raise PiiRedactorError("segment analysis failed")
        return real(*a, **k)

    monkeypatch.setattr(pii_redactor, "redaction_spans", spans)


def test_gate_fault_after_a_release_charges_then_fails(setup, spies, monkeypatch):
    order, charges = spies
    _fail_spans_from(monkeypatch, 2)
    rec = _Recorder()
    events = [TextDelta("First sentence. "), TextDelta("Second sentence. "), TextDelta("Third. ")]
    with pytest.raises(PiiRedactorError):
        _run(rec, prompt="count me", stream=_stream(events + [Finish("stop"), _USAGE]))
    assert order == ["charge", "log_failure"]
    (_u, _d, _i, _o, total), = charges
    received = "".join(e.text for e in events[:2])  # the delta that failed was received
    assert total == estimate_tokens([Message("user", "count me")], (received, ()), 1.0)
    assert rec.of("content") and "Second" not in "".join(rec.of("content"))  # nothing raw after the error
    assert _last_row().success is False


def test_gate_fault_before_any_release_charges_nothing(setup, spies, monkeypatch):
    order, charges = spies
    _fail_spans_from(monkeypatch, 1)
    rec = _Recorder()
    with pytest.raises(PiiRedactorError):
        _run(rec, stream=_stream([TextDelta("First sentence. "), Finish("stop"), _USAGE]))
    assert charges == [] and order == ["log_failure"] and rec.of("content") == []


def test_final_pass_failure_in_finish_after_a_release_charges(setup, spies, monkeypatch):
    order, charges = spies
    real = query_pipeline._redact

    def redact_or_fail(text, policy):
        if text == "hello world":  # step 6 masks the prompt through the same call
            return real(text, policy)
        raise PiiRedactorError("final pass failed")

    monkeypatch.setattr(query_pipeline, "_redact", redact_or_fail)
    rec = _Recorder()
    events = [TextDelta("First sentence. "), TextDelta("held tail")]
    with pytest.raises(PiiRedactorError):
        _run(rec, stream=_stream(events + [Finish("stop"), _USAGE]))
    assert order == ["charge", "log_failure"]
    assert "held tail" not in "".join(rec.of("content"))  # the remainder was never sent


def test_a_gate_holding_everything_then_faulting_charges_nothing(setup, spies):
    order, charges = spies
    with pytest.raises(OpenRouterError):
        _run(_Recorder(), stream=_stream([TextDelta("no boundary yet")],
                                         then=UpstreamError("dropped", retryable=True)))
    assert charges == [] and order == ["log_failure"]
