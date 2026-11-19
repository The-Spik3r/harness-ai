"""PRD-021 STORY-009: the four delivery columns written by `run_conversation`.

F7, D14, D17; T9. Rows are read back through `get_audit_log`. What is pinned:

- a realtime success row: `streamed_realtime`, `completion_id` equal to the id
  the sink was committed with, `reasoning_shown` only when reasoning text was
  released to the sink or returned whole;
- a buffered row (a sink with no realtime grant, or `sink=None`) stores 0 / NULL
  although a sink was told an id;
- a divergence between the gate and the final pass sets
  `stream_redaction_divergence`;
- failure rows record what was true at the fault, step 7 and step 8 alike;
- refusals (authorization, step 3) open no upstream, so they write 0 / NULL;
- one INFO line at the realtime commit: user, model, id, never content;
- a sink that fails (a disconnected client) does not stop the run: success row,
  tokens charged.
"""

import logging
import os
import re

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import pytest

import app.services.pii_redactor as pii_redactor
import app.services.query_pipeline as query_pipeline
from app.config import settings
from app.db.database import get_connection
from app.models.messages import Message
from app.models.schemas import QueryBlockedForbiddenResponse, QuerySuccessResponse
from app.services.openrouter_client import OpenRouterError
from app.services.pii_redactor import PiiRedactorError
from app.services.upstream import Finish, ReasoningDelta, TextDelta, UpstreamError
from tests._providers import provider_file  # noqa: F401  (fixture)
from tests.test_query_pipeline_gates import _EMAIL, _deltas
from tests.test_query_pipeline_streaming import (
    _JUAN,
    _RT,
    _RV,
    _SUBMIT,
    _USAGE,
    _buffered,
    _last_row,
    _Recorder,
    _run,
    _stream,
    setup,  # noqa: F401  (fixture)
)

_ID = re.compile(r"^chatcmpl-harness-rt-[0-9a-f]{32}$")
_THINK = [ReasoningDelta("First thought. "), ReasoningDelta("Second thought. ")]
_ANSWER = [TextDelta("Hello there. "), TextDelta("Bye now. ")]
_DONE = [Finish("stop"), _USAGE]


# --- AC4: a realtime success row ---------------------------------------------------


def test_realtime_success_row_carries_the_committed_id_and_shown_reasoning(setup):
    rec = _Recorder()
    result = _run(rec, stream=_stream(_THINK + _ANSWER + _DONE))

    assert isinstance(result, QuerySuccessResponse)
    row = _last_row()
    assert row.success is True and row.streamed_realtime is True
    assert row.completion_id == rec.of("committed")[0] and _ID.match(row.completion_id)
    assert rec.of("reasoning") and row.reasoning_shown is True
    assert row.stream_redaction_divergence is False


def test_realtime_without_the_reasoning_grant_shows_none(setup):
    setup(grants=(_SUBMIT, _RT))
    rec = _Recorder()
    _run(rec, stream=_stream(_THINK + _ANSWER + _DONE))

    row = _last_row()
    assert row.streamed_realtime is True and row.completion_id == rec.of("committed")[0]
    assert rec.of("reasoning") == [] and row.reasoning_shown is False


# --- AC4: a buffered row stores 0 / NULL -------------------------------------------


def test_buffered_row_with_a_sink_is_null_although_the_sink_got_an_id(setup):
    setup(grants=(_SUBMIT,))
    rec = _Recorder()
    _run(rec, buffered=_buffered())

    assert len(rec.of("committed")) == 1 and _ID.match(rec.of("committed")[0])
    row = _last_row()
    assert row.success is True
    assert (row.streamed_realtime, row.reasoning_shown) == (False, False)
    assert (row.stream_redaction_divergence, row.completion_id) == (False, None)


def test_sink_none_row_is_today(setup):
    # The default grants include real time: with no sink nothing is forwarded.
    _run(None, buffered=_buffered())

    row = _last_row()
    assert (row.streamed_realtime, row.reasoning_shown) == (False, False)
    assert (row.stream_redaction_divergence, row.completion_id) == (False, None)


# --- AC4: reasoning returned whole -------------------------------------------------


def test_reasoning_returned_whole_counts_as_shown_without_realtime(setup):
    setup(grants=(_SUBMIT, _RV))
    rec = _Recorder()
    result = _run(rec, ingress="chat", stream=_stream(_THINK + _ANSWER + _DONE))

    assert result.reasoning
    row = _last_row()
    assert row.reasoning_shown is True and row.streamed_realtime is False
    assert row.completion_id is None


def test_no_reasoning_in_the_stream_is_not_shown(setup):
    setup(grants=(_SUBMIT, _RV))
    result = _run(_Recorder(), ingress="chat", stream=_stream(_ANSWER + _DONE))

    assert result.reasoning is None
    assert _last_row().reasoning_shown is False


# --- D14: divergence ---------------------------------------------------------------


def test_a_forced_cut_across_an_entity_sets_the_divergence_flag(setup, monkeypatch):
    monkeypatch.setattr(settings, "STREAM_HOLDBACK_MAX_CHARACTERS", 10)
    reply = f"contact {_EMAIL} now"
    result = _run(_Recorder(), stream=_stream(_deltas(reply, 3) + _DONE))

    assert _EMAIL not in result.response  # the final pass stays authoritative
    row = _last_row()
    assert row.stream_redaction_divergence is True and row.streamed_realtime is True


def test_a_clean_run_does_not_set_the_divergence_flag(setup):
    _run(_Recorder(), stream=_stream(_deltas(f"Write to {_EMAIL} today. Bye. ") + _DONE))

    assert _last_row().stream_redaction_divergence is False


# --- failure rows ------------------------------------------------------------------


def test_fault_after_a_release_records_what_was_true_at_the_fault(setup):
    rec = _Recorder()
    with pytest.raises(OpenRouterError):
        _run(rec, stream=_stream(
            _THINK + _ANSWER, then=UpstreamError("connection dropped", retryable=True)
        ))

    row = _last_row()
    assert row.success is False and row.streamed_realtime is True
    assert row.completion_id == rec.of("committed")[0]
    assert rec.of("reasoning") and row.reasoning_shown is True


def test_fault_before_any_reasoning_release_is_not_shown(setup):
    rec = _Recorder()
    with pytest.raises(OpenRouterError):
        _run(rec, stream=_stream(
            [ReasoningDelta("no boundary yet")], then=UpstreamError("dropped", retryable=True)
        ))

    row = _last_row()
    assert rec.of("reasoning") == []
    assert (row.success, row.streamed_realtime, row.reasoning_shown) == (False, True, False)
    assert row.completion_id == rec.of("committed")[0]  # an event arrived: the id exists


def test_fault_before_any_event_has_no_completion_id(setup):
    rec = _Recorder()
    with pytest.raises(OpenRouterError):
        _run(rec, stream=_stream([], then=UpstreamError("refused", retryable=True)))

    row = _last_row()
    assert rec.of("committed") == []
    assert row.success is False and row.completion_id is None  # the id is made on the first event


def test_gate_fault_after_a_release_keeps_the_divergence_flag_off(setup, monkeypatch):
    real = pii_redactor.redaction_spans
    calls = {"n": 0}

    def spans(*a, **k):
        calls["n"] += 1
        if calls["n"] >= 2:
            raise PiiRedactorError("segment analysis failed")
        return real(*a, **k)

    monkeypatch.setattr(pii_redactor, "redaction_spans", spans)
    rec = _Recorder()
    events = [TextDelta("First sentence. "), TextDelta("Second sentence. "), TextDelta("Third. ")]
    with pytest.raises(PiiRedactorError):
        _run(rec, stream=_stream(events + _DONE))

    row = _last_row()
    assert row.success is False and row.streamed_realtime is True
    assert row.completion_id == rec.of("committed")[0]
    assert row.stream_redaction_divergence is False


def _fail_response_redaction(monkeypatch):
    real = query_pipeline._redact

    def redact(text, policy):
        if text == "hello world":  # step 6 masks the prompt through the same call
            return real(text, policy)
        raise PiiRedactorError("output redaction failed")

    monkeypatch.setattr(query_pipeline, "_redact", redact)


def test_step_8_failure_row_on_a_buffered_request(setup, monkeypatch):
    setup(grants=(_SUBMIT,))  # no real time: the upstream is called whole
    _fail_response_redaction(monkeypatch)
    with pytest.raises(PiiRedactorError):
        _run(_Recorder(), buffered=_buffered())

    row = _last_row()
    assert row.success is False
    assert (row.streamed_realtime, row.reasoning_shown, row.completion_id) == (False, False, None)


def test_step_8_failure_row_on_a_realtime_request_carries_the_values(setup, monkeypatch):
    # The master switch off: no gate, so step 8 redacts the whole reply itself.
    monkeypatch.setattr(settings, "PII_REDACTION_ENABLED", False)
    _fail_response_redaction(monkeypatch)
    rec = _Recorder()
    with pytest.raises(PiiRedactorError):
        _run(rec, stream=_stream(_THINK + _ANSWER + _DONE))

    row = _last_row()
    assert row.success is False and row.streamed_realtime is True
    assert row.completion_id == rec.of("committed")[0]
    assert rec.of("reasoning") and row.reasoning_shown is True


# --- refusals open no upstream -----------------------------------------------------


def test_an_authorization_denial_writes_no_delivery(setup):
    setup(grants=())
    result = _run(_Recorder())

    assert isinstance(result, QueryBlockedForbiddenResponse)
    row = _last_row()
    assert (row.streamed_realtime, row.reasoning_shown) == (False, False)
    assert (row.stream_redaction_divergence, row.completion_id) == (False, None)


def test_a_step_3_refusal_of_a_would_be_realtime_request_writes_no_delivery(setup, monkeypatch):
    monkeypatch.setattr(settings, "CONTEXT_MAX_CHARACTERS", 5)  # "hello world" is over it
    rec = _Recorder()
    result = _run(rec, prompt="hello world", stream=_stream(_ANSWER + _DONE))

    assert not isinstance(result, QuerySuccessResponse)
    row = _last_row()
    assert (row.error_message or "").startswith("context limit")  # it really was step 3
    assert (row.streamed_realtime, row.reasoning_shown) == (False, False)
    assert row.completion_id is None
    assert rec.of("committed") == []


# --- D15: the INFO line ------------------------------------------------------------

_CANARY_PROMPT = "CANARYPROMPT please answer"
_CANARY_ANSWER = "CANARYANSWER here. "


def _info_lines(caplog):
    return [
        r.getMessage() for r in caplog.records
        if r.name == "app.services.query_pipeline" and r.levelno == logging.INFO
        and "realtime stream committed" in r.getMessage()
    ]


def test_one_info_line_at_the_realtime_commit_without_content(setup, caplog):
    rec = _Recorder()
    with caplog.at_level(logging.INFO, logger="app.services.query_pipeline"):
        _run(rec, prompt=_CANARY_PROMPT, stream=_stream(
            [ReasoningDelta("CANARYTHOUGHT done. "), TextDelta(_CANARY_ANSWER)] + _DONE
        ))

    lines = _info_lines(caplog)
    assert len(lines) == 1
    assert _JUAN.user_id in lines[0] and "s/m" in lines[0] and rec.of("committed")[0] in lines[0]
    assert "CANARY" not in "\n".join(r.getMessage() for r in caplog.records)


def test_no_info_line_for_a_buffered_run(setup, caplog):
    setup(grants=(_SUBMIT,))
    with caplog.at_level(logging.INFO, logger="app.services.query_pipeline"):
        _run(_Recorder(), buffered=_buffered())

    assert _info_lines(caplog) == []


# --- D15: a disconnected client ----------------------------------------------------


class _Disconnecting(_Recorder):
    """Accepts the first content delta, then raises like a closed connection."""

    def content(self, text):
        super().content(text)
        if len(self.of("content")) > 1:
            raise ConnectionResetError("client went away")


def _usage_row():
    with get_connection() as conn:
        return conn.execute(
            "SELECT input_tokens, output_tokens FROM usage_daily WHERE user_id = ?",
            (_JUAN.user_id,),
        ).fetchone()


def test_a_sink_that_fails_does_not_stop_the_run_or_the_charge(setup):
    rec = _Disconnecting()
    result = _run(rec, stream=_stream(_ANSWER + [TextDelta("More text. ")] + _DONE))

    assert isinstance(result, QuerySuccessResponse)
    row = _last_row()
    assert row.success is True and row.tokens_used == _USAGE.total_tokens
    assert row.streamed_realtime is True and row.completion_id == rec.of("committed")[0]
    usage = _usage_row()
    assert (usage["input_tokens"], usage["output_tokens"]) == (3, 4)  # charged as reported
