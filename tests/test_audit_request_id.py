"""PRD-022 STORY-003: `request_id` on every audit row, and the step-7 trail.

F8, D10. What is pinned:

- one uuid4 per `run_conversation` call, on every row the call writes, and a
  different one on the next call;
- a refusal written before step 7 (an authorization arm through `_deny`, the
  context limit) carries the id and leaves `attempt` / `route_model` NULL;
- the step-7 failure row, the success row and the output-redaction failure row
  are attempt 1 on the requested catalogue id;
- `fallback_reason` and `skipped_providers` are never written yet (no chain);
- the success row copies the result's cache counts, absent counts stay NULL,
  failure rows write NULL;
- `_deny` without `request_id` is a TypeError;
- `GET /audit?request_id=` returns exactly that call's rows.
"""

import os
import re
import types
import uuid

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import pytest
from fastapi.testclient import TestClient

import app.services.query_pipeline as query_pipeline
from app.services import authz
from app.config import settings
from app.db.database import get_audit_log, get_connection
from app.main import app
from app.models.schemas import QueryBlockedForbiddenResponse, QuerySuccessResponse
from app.services.authz import PermissionDenied
from app.services.openrouter_client import OpenRouterError, OpenRouterResult
from app.services.pii_redactor import PiiRedactorError
from app.services.upstream import Finish, TextDelta, UpstreamError
from tests._providers import provider_file  # noqa: F401  (fixture)
from tests.test_query_pipeline_streaming import (
    _JUAN,
    _SUBMIT,
    _USAGE,
    _buffered,
    _Recorder,
    _run,
    _stream,
    setup,  # noqa: F401  (fixture)
)

client = TestClient(app)
_ADMIN = {"Authorization": f"Bearer {settings.ADMIN_TOKEN}"}
_MODEL = "s/m"
_UUID4 = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")


def _rows():
    with get_connection() as conn:
        ids = [r["id"] for r in conn.execute("SELECT id FROM audit_logs ORDER BY id")]
    return [get_audit_log(i) for i in ids]


def _cached(read=11, write=7):
    def fake(messages, model="gpt-4", api_key=None, params=None, *, tools=None):
        return OpenRouterResult(
            response="Hi there!", model_used=model, tokens_used=12,
            cache_read_tokens=read, cache_write_tokens=write,
        )

    return fake


def _failing(messages, model="gpt-4", api_key=None, params=None, *, tools=None):
    raise UpstreamError("connection dropped", retryable=True)


def _fail_response_redaction(monkeypatch):
    real = query_pipeline._redact

    def redact(text, policy):
        if text == "hello world":  # step 6 masks the prompt through the same call
            return real(text, policy)
        raise PiiRedactorError("output redaction failed")

    monkeypatch.setattr(query_pipeline, "_redact", redact)


# --- the id: one per call -----------------------------------------------------------


def test_each_call_mints_its_own_uuid4_and_every_row_of_a_call_shares_it(setup):
    setup(grants=(_SUBMIT,))  # no real time: the upstream is called whole
    first = _run(_Recorder(), prompt="first question", buffered=_buffered())
    second = _run(_Recorder(), prompt="second question", buffered=_buffered())

    assert isinstance(first, QuerySuccessResponse) and isinstance(second, QuerySuccessResponse)
    rows = _rows()
    assert len(rows) == 2
    ids = [r.request_id for r in rows]
    assert all(_UUID4.match(i) for i in ids)
    assert ids[0] != ids[1]
    assert uuid.UUID(ids[0]).version == 4


def test_a_forced_id_is_shared_by_the_refusal_and_filterable(setup, monkeypatch):
    """The id is minted by the pipeline, not read from the request: pin the mint
    and see that the one row of that call carries it."""
    fixed = "11111111-2222-4333-8444-555555555555"
    # A stand-in on the pipeline's own name: patching uuid.uuid4 itself would
    # also hand the audit writer's write_id the fixed value.
    monkeypatch.setattr(
        query_pipeline, "uuid", types.SimpleNamespace(uuid4=lambda: uuid.UUID(fixed))
    )
    setup(grants=())
    result = _run(_Recorder())

    assert isinstance(result, QueryBlockedForbiddenResponse)
    assert [r.request_id for r in _rows()] == [fixed]


# --- before step 7: the id, no attempt ----------------------------------------------


def test_an_authorization_refusal_has_the_id_and_no_attempt(setup):
    setup(grants=())
    result = _run(_Recorder())

    assert isinstance(result, QueryBlockedForbiddenResponse)
    (row,) = _rows()
    assert _UUID4.match(row.request_id)
    assert (row.attempt, row.route_model) == (None, None)
    assert (row.fallback_reason, row.skipped_providers) == (None, None)
    assert (row.cache_read_tokens, row.cache_write_tokens) == (None, None)


def test_a_context_limit_refusal_has_the_id_and_no_attempt(setup, monkeypatch):
    monkeypatch.setattr(settings, "CONTEXT_MAX_CHARACTERS", 5)  # "hello world" is over it
    result = _run(_Recorder(), prompt="hello world", stream=_stream([TextDelta("x"), Finish("stop"), _USAGE]))

    assert not isinstance(result, QuerySuccessResponse)
    (row,) = _rows()
    assert (row.error_message or "").startswith("context limit")  # it really was step 3
    assert _UUID4.match(row.request_id)
    assert (row.attempt, row.route_model) == (None, None)


# --- at and after step 7: attempt 1 on the requested model --------------------------


def test_the_step_7_failure_row_is_attempt_one_on_the_requested_model(setup):
    setup(grants=(_SUBMIT,))  # no real time: the upstream is called whole
    with pytest.raises(OpenRouterError):
        _run(_Recorder(), buffered=_failing)

    (row,) = _rows()
    assert row.success is False
    assert _UUID4.match(row.request_id)
    assert (row.attempt, row.route_model) == (1, _MODEL)
    assert (row.fallback_reason, row.skipped_providers) == (None, None)
    assert (row.cache_read_tokens, row.cache_write_tokens) == (None, None)


def test_the_success_row_is_attempt_one_and_copies_the_cache_counts(setup):
    setup(grants=(_SUBMIT,))  # no real time: the upstream is called whole
    result = _run(_Recorder(), buffered=_cached(read=11, write=7))

    assert isinstance(result, QuerySuccessResponse)
    (row,) = _rows()
    assert row.success is True
    assert (row.attempt, row.route_model) == (1, _MODEL)
    assert (row.cache_read_tokens, row.cache_write_tokens) == (11, 7)
    assert (row.fallback_reason, row.skipped_providers) == (None, None)


def test_absent_cache_counts_stay_null_on_the_success_row(setup):
    setup(grants=(_SUBMIT,))  # no real time: the upstream is called whole
    _run(_Recorder(), buffered=_buffered())

    (row,) = _rows()
    assert row.success is True and (row.attempt, row.route_model) == (1, _MODEL)
    assert (row.cache_read_tokens, row.cache_write_tokens) == (None, None)


def test_a_streamed_success_row_is_attempt_one_with_null_cache_counts(setup):
    result = _run(_Recorder(), stream=_stream([TextDelta("Hello there. "), Finish("stop"), _USAGE]))

    assert isinstance(result, QuerySuccessResponse)
    (row,) = _rows()
    assert (row.attempt, row.route_model) == (1, _MODEL)
    assert (row.cache_read_tokens, row.cache_write_tokens) == (None, None)


def test_the_output_redaction_failure_row_is_attempt_one_on_the_requested_model(
    setup, monkeypatch
):
    setup(grants=(_SUBMIT,))
    _fail_response_redaction(monkeypatch)
    with pytest.raises(PiiRedactorError):
        _run(_Recorder(), buffered=_cached())

    (row,) = _rows()
    assert row.success is False
    assert _UUID4.match(row.request_id)
    assert (row.attempt, row.route_model) == (1, _MODEL)
    assert (row.cache_read_tokens, row.cache_write_tokens) == (None, None)


# --- _deny: a forgotten arm is a TypeError ------------------------------------------


def test_deny_without_request_id_is_a_type_error(setup):
    with pytest.raises(TypeError, match="request_id"):
        query_pipeline._deny(
            _JUAN, "hi", None, session_id=None, dedup_key=None, profile="chat",
            ingress=None, message_count=1, conversation_key=None, streamed=False,
            ignored_params=None, has_tool_calls=False, streamed_realtime=False,
            reasoning_shown=False, exc=PermissionDenied("query:submit"),
            reason="Missing required permission", route=None,
        )
    assert _rows() == []


# --- GET /audit ----------------------------------------------------------------------


def test_get_audit_filters_by_the_request_id_of_one_call(setup, monkeypatch):
    setup(grants=(_SUBMIT,))  # no real time: the upstream is called whole
    _run(_Recorder(), prompt="first question", buffered=_cached(read=3, write=2))
    _run(_Recorder(), prompt="second question", buffered=_buffered())
    first, second = _rows()
    # `setup` narrows the role table to the pipeline's caller; the admin token
    # needs its own read grant.
    monkeypatch.setattr(authz, "ROLE_PERMISSIONS", {"admin": {authz.PERMISSION_AUDIT_READ_ALL}})

    response = client.get(f"/audit?request_id={first.request_id}", headers=_ADMIN)
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["total"] == 1
    (entry,) = body["queries"]
    assert entry["audit_id"] == first.id
    assert (entry["request_id"], entry["attempt"], entry["route_model"]) == (
        first.request_id, 1, _MODEL,
    )
    assert (entry["cache_read_tokens"], entry["cache_write_tokens"]) == (3, 2)
    assert (entry["fallback_reason"], entry["skipped_providers"]) == (None, None)
    assert client.get("/audit", headers=_ADMIN).json()["total"] == 2
    assert first.request_id != second.request_id
