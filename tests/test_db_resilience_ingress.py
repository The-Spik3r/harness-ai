"""PRD-018 STORY-006: every HTTP ingress answers a storage outage with a 503 + `Retry-After`.

`require_identity`, `POST /query` and `/v1` map `StorageUnavailableError` (and a
gate error *caused by* one) to a retryable 503 with fixed copy and
`Retry-After` = `retry_after_seconds` (Section 6.7, D8). Any other storage
failure keeps its 500 (`test_duplicate_check_storage_failure_returns_500`).

No test here touches storage, so the conftest guard proves zero driver calls. A
real outage is simulated by forcing the storage breaker open with a frozen
clock: `_unit_of_work` refuses before any client exists, which is the T1
property -- nothing is sent upstream and no row is written. The causes the
breaker cannot produce (a closed breaker with only the call's own budget spent,
a non-transient cause) are built by hand with `raise ... from`.
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import concurrent.futures
import json
import logging

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.config import settings
from app.db import database
from app.db.errors import MissingRelationError, StorageError, StorageUnavailableError
from app.main import app
from app.middleware.auth import require_identity
from app.routers.v1 import _fault_code, _sse_events, _Upstream
from app.services import chat_sessions, query_pipeline
from app.services.chat_sessions import ChatSessionError
from app.services.circuit_breaker import CircuitBreaker
from app.services.duplicate_checker import DuplicateCheckError
from app.services.identity import Identity
from app.services.openrouter_client import OpenRouterResult
from app.services.query_pipeline import ActionAuditError
from app.services.storage_faults import (
    STORAGE_UNAVAILABLE_DETAIL,
    STORAGE_UNAVAILABLE_NOT_SENT_DETAIL,
    retry_after_headers,
    storage_unavailable_cause,
)
from app.services.usage_limits import UsageLimitError
from app.services.v1_translate import STORAGE_UNAVAILABLE_MESSAGE

_CANARY = "CANARY-driver-text-5d1e"
_USER_TOKEN = "some-user-token"
_USER_HEADERS = {"Authorization": f"Bearer {_USER_TOKEN}"}
_RETRY_AFTER = 7
_V1_BODY = {"model": "openai/gpt-4o", "messages": [{"role": "user", "content": "hello world"}]}
_STORAGE_ERROR_OBJECT = {
    "message": STORAGE_UNAVAILABLE_MESSAGE,
    "type": "api_error",
    "param": None,
    "code": "storage_unavailable",
    "harness": None,
}


def _admin_headers():
    return {"Authorization": f"Bearer {settings.ADMIN_TOKEN}"}


@pytest.fixture
def breaker_open(monkeypatch):
    """The storage breaker, open for `_RETRY_AFTER` seconds on a frozen clock."""
    breaker = CircuitBreaker(
        "storage",
        database._BREAKER_FAILURE_THRESHOLD,
        database._BREAKER_OPEN_SECONDS,
        clock=lambda: 1000.0,
    )
    monkeypatch.setattr(database, "_storage_breaker", breaker)
    breaker.force_open(_RETRY_AFTER)
    return breaker


class _Recorder:
    def __init__(self):
        self.calls = []

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return OpenRouterResult(response="never", model_used="m", tokens_used=1)


@pytest.fixture
def upstream(monkeypatch):
    """A recording upstream on both routers, plus a recorder over every audit-row writer (O7)."""
    stub = _Recorder()
    monkeypatch.setattr("app.routers.query.call_openrouter", stub)
    monkeypatch.setattr("app.routers.v1.call_openrouter", stub)
    rows = _Recorder()
    monkeypatch.setattr(query_pipeline, "log_query", rows)
    monkeypatch.setattr("app.routers.query.log_query", rows)
    stub.rows = rows
    return stub


@pytest.fixture
def v1_identity():
    """`/v1` authenticated without a read, so a gate (not the identity lookup) is what fails."""
    app.dependency_overrides[require_identity] = lambda: Identity("ingress@test", "user")
    yield
    app.dependency_overrides.pop(require_identity, None)


@pytest.fixture(params=[False, True], ids=["json", "sse"])
def stream(request):
    return request.param


def _assert_no_side_effects(upstream):
    assert upstream.calls == []
    assert upstream.rows.calls == []


def _assert_v1_storage_unavailable(response, retry_after=str(_RETRY_AFTER)):
    assert response.status_code == 503
    assert response.json() == {"error": _STORAGE_ERROR_OBJECT}
    assert response.headers["Retry-After"] == retry_after
    # D7: a retryable fault carries no `x-should-retry`.
    assert "x-should-retry" not in response.headers
    assert response.headers["content-type"].startswith("application/json")
    assert _CANARY not in response.text


def _gate_error(cls, cause):
    """`cls` raised the way each gate raises it: `from` the unit's own exception."""
    try:
        raise cause
    except StorageError as exc:
        try:
            raise cls(f"gate failed: {exc}") from exc
        except cls as gate:
            return gate


# --- storage_unavailable_cause / retry_after_headers ------------------------------


def test_cause_is_the_error_itself():
    err = StorageUnavailableError("x", 3)
    assert storage_unavailable_cause(err) is err


@pytest.mark.parametrize("cls", [DuplicateCheckError, UsageLimitError, ChatSessionError])
def test_cause_of_a_gate_error_raised_from_an_outage(cls):
    err = StorageUnavailableError("x", 3)
    assert storage_unavailable_cause(_gate_error(cls, err)) is err


def test_cause_is_none_for_other_storage_failures_and_no_cause():
    assert storage_unavailable_cause(_gate_error(DuplicateCheckError, StorageError("x"))) is None
    assert (
        storage_unavailable_cause(
            _gate_error(DuplicateCheckError, MissingRelationError("audit_logs", "x"))
        )
        is None
    )
    assert storage_unavailable_cause(DuplicateCheckError("no cause")) is None


def test_cause_walks_one_level_only():
    # Documented on purpose: a deeper wrap must re-raise `from` the outage itself.
    inner = _gate_error(DuplicateCheckError, StorageUnavailableError("x", 3))
    try:
        raise inner
    except DuplicateCheckError as exc:
        try:
            raise ChatSessionError("wrapped again") from exc
        except ChatSessionError as outer:
            assert storage_unavailable_cause(outer) is None


def test_retry_after_headers_spelling():
    assert retry_after_headers(StorageUnavailableError("x", 12)) == {"Retry-After": "12"}


# --- require_identity (AC 1) ------------------------------------------------------

_fake_app = FastAPI()


@_fake_app.get("/fake-identity")
def _fake_identity(identity=Depends(require_identity)) -> dict:
    return {"user_id": identity.user_id}


_fake_client = TestClient(_fake_app)


def test_identity_outage_is_503_never_401(breaker_open):
    response = _fake_client.get("/fake-identity", headers=_USER_HEADERS)

    # PRD-018 D8: an outage must not read as a bad credential.
    assert response.status_code == 503
    assert response.json() == {"detail": STORAGE_UNAVAILABLE_DETAIL}
    assert response.headers["Retry-After"] == str(_RETRY_AFTER)


def test_break_glass_still_resolves_with_the_breaker_open(breaker_open):
    response = _fake_client.get("/fake-identity", headers=_admin_headers())

    assert response.status_code == 200


def test_identity_outage_on_query_is_503(breaker_open, upstream):
    response = TestClient(app).post("/query", json={"prompt": "hi"}, headers=_USER_HEADERS)

    assert response.status_code == 503
    assert response.json() == {"detail": STORAGE_UNAVAILABLE_DETAIL}
    assert response.headers["Retry-After"] == str(_RETRY_AFTER)
    _assert_no_side_effects(upstream)


@pytest.mark.parametrize("stream_flag", [False, True], ids=["json", "sse"])
def test_identity_outage_on_v1_chat_completions(breaker_open, upstream, stream_flag):
    response = TestClient(app).post(
        "/v1/chat/completions", json={**_V1_BODY, "stream": stream_flag}, headers=_USER_HEADERS
    )

    _assert_v1_storage_unavailable(response)
    _assert_no_side_effects(upstream)


def test_identity_outage_on_v1_models(breaker_open):
    response = TestClient(app).get("/v1/models", headers=_USER_HEADERS)

    _assert_v1_storage_unavailable(response)


# --- POST /query gates (AC 2, T1) -------------------------------------------------


@pytest.mark.parametrize("gate", ["usage", "duplicate", "session"])
def test_query_gate_outage_is_503_with_nothing_sent(breaker_open, upstream, monkeypatch, gate):
    monkeypatch.setattr(settings, "USAGE_LIMITS_ENABLED", gate == "usage")
    body = {"prompt": "hi"}
    if gate == "session":
        monkeypatch.setattr(settings, "USAGE_LIMITS_ENABLED", False)
        monkeypatch.setattr(settings, "CHAT_HISTORY_ENABLED", True)
        body["session_id"] = "6f0f3c52-7b4c-4a53-9f0c-4d6a2b7f9a11"

    response = TestClient(app).post("/query", json=body, headers=_admin_headers())

    assert response.status_code == 503
    assert response.json() == {"detail": STORAGE_UNAVAILABLE_NOT_SENT_DETAIL}
    assert response.headers["Retry-After"] == str(_RETRY_AFTER)
    _assert_no_side_effects(upstream)


@pytest.mark.parametrize("cls", [DuplicateCheckError, UsageLimitError])
def test_query_budget_exhausted_retry_after_is_one_and_nothing_leaks(
    upstream, monkeypatch, caplog, cls
):
    # AC 4: breaker closed, only this call's own budget ran out -> Retry-After 1.
    def fail(*args, **kwargs):
        raise _gate_error(cls, StorageUnavailableError(_CANARY, 1))

    monkeypatch.setattr(settings, "USAGE_LIMITS_ENABLED", cls is UsageLimitError)
    monkeypatch.setattr(query_pipeline, "check_duplicate", fail)
    monkeypatch.setattr(query_pipeline, "admit", fail)

    with caplog.at_level(logging.DEBUG):
        response = TestClient(app).post("/query", json={"prompt": "hi"}, headers=_admin_headers())

    assert response.status_code == 503
    assert response.json() == {"detail": STORAGE_UNAVAILABLE_NOT_SENT_DETAIL}
    assert response.headers["Retry-After"] == "1"
    assert _CANARY not in response.text
    # The router logs the code and the retry hint, never the exception text.
    assert _CANARY not in caplog.text
    _assert_no_side_effects(upstream)


def test_query_chat_session_error_from_an_outage_is_503(upstream, monkeypatch):
    def fail(*args, **kwargs):
        raise _gate_error(ChatSessionError, StorageUnavailableError(_CANARY, 4))

    monkeypatch.setattr(chat_sessions, "owns", fail)

    response = TestClient(app).post(
        "/query",
        json={"prompt": "hi", "session_id": "6f0f3c52-7b4c-4a53-9f0c-4d6a2b7f9a11"},
        headers=_admin_headers(),
    )

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "4"
    assert _CANARY not in response.text
    _assert_no_side_effects(upstream)


# --- /v1 gates (AC 3, T1) ---------------------------------------------------------


@pytest.mark.parametrize("gate", ["usage", "duplicate"])
def test_v1_gate_outage_is_503_storage_unavailable(
    breaker_open, upstream, v1_identity, monkeypatch, stream, gate
):
    monkeypatch.setattr(settings, "USAGE_LIMITS_ENABLED", gate == "usage")

    response = TestClient(app).post("/v1/chat/completions", json={**_V1_BODY, "stream": stream})

    # A pre-commit stream is still the JSON error with its real status (Section 6.4).
    _assert_v1_storage_unavailable(response)
    _assert_no_side_effects(upstream)


@pytest.mark.parametrize("cls", [DuplicateCheckError, UsageLimitError])
def test_v1_budget_exhausted_retry_after_is_one_and_nothing_leaks(
    upstream, v1_identity, monkeypatch, caplog, cls, stream
):
    def fail(*args, **kwargs):
        raise _gate_error(cls, StorageUnavailableError(_CANARY, 1))

    monkeypatch.setattr(settings, "USAGE_LIMITS_ENABLED", cls is UsageLimitError)
    monkeypatch.setattr(query_pipeline, "check_duplicate", fail)
    monkeypatch.setattr(query_pipeline, "admit", fail)

    with caplog.at_level(logging.DEBUG):
        response = TestClient(app).post("/v1/chat/completions", json={**_V1_BODY, "stream": stream})

    _assert_v1_storage_unavailable(response, retry_after="1")
    assert _CANARY not in caplog.text
    _assert_no_side_effects(upstream)


# --- Non-transient causes are unchanged -------------------------------------------


def test_non_transient_cause_keeps_the_query_500(upstream, monkeypatch):
    def fail(*args, **kwargs):
        raise _gate_error(DuplicateCheckError, MissingRelationError("audit_logs", _CANARY))

    monkeypatch.setattr(settings, "USAGE_LIMITS_ENABLED", False)
    monkeypatch.setattr(query_pipeline, "check_duplicate", fail)

    response = TestClient(app).post("/query", json={"prompt": "hi"}, headers=_admin_headers())

    assert response.status_code == 500
    assert "gate failed" in response.json()["detail"]
    assert "Retry-After" not in response.headers


def test_non_transient_cause_keeps_the_v1_500(upstream, v1_identity, monkeypatch):
    def fail(*args, **kwargs):
        raise _gate_error(DuplicateCheckError, MissingRelationError("audit_logs", _CANARY))

    monkeypatch.setattr(settings, "USAGE_LIMITS_ENABLED", False)
    monkeypatch.setattr(query_pipeline, "check_duplicate", fail)

    response = TestClient(app).post("/v1/chat/completions", json=_V1_BODY)

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert "Retry-After" not in response.headers


def test_action_audit_error_from_an_outage_stays_internal_error():
    # PRD-018 Section 6.7: tools keep PRD-017's 500.
    exc = _gate_error(ActionAuditError, StorageUnavailableError("x", 3))
    assert _fault_code(exc) == "internal_error"


@pytest.mark.parametrize("cls", [DuplicateCheckError, UsageLimitError])
def test_fault_code_for_a_gate_caused_by_an_outage(cls):
    assert _fault_code(_gate_error(cls, StorageUnavailableError("x", 3))) == "storage_unavailable"


# --- Post-commit SSE rendering ----------------------------------------------------


def test_sse_event_for_a_post_commit_outage_is_the_fixed_error_object():
    future = concurrent.futures.Future()
    future.set_exception(
        _gate_error(DuplicateCheckError, StorageUnavailableError(_CANARY, 5))
    )
    wrapper = _Upstream(loop=None)

    events = _sse_events(
        future, upstream=wrapper, identity=Identity("ingress@test", "user"), include_usage=False
    )

    # The headers are already sent: no `Retry-After`, the event is all there is.
    assert len(events) == 1
    assert events[0].startswith("data: ")
    assert json.loads(events[0][len("data: "):]) == {"error": _STORAGE_ERROR_OBJECT}
    assert _CANARY not in events[0]
