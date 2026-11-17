"""PRD-018 STORY-011: the admission headroom check (D10, 6.8 Bounds, T5, AC 4).

When the journal's bytes exceed `AUDIT_BUFFER_MAX_BYTES - PIPELINE_MAX_WORKERS x
64 KiB`, `query_pipeline.run_conversation` refuses at step 1c with
`AuditHeadroomError`: before step 2, so no row, no upstream call. The three
ingress arms of STORY-010 map it to 503 with the existing "not sent to the model"
copy (R2); `Retry-After` is 1 (R3). Non-`db`: every driver-facing writer is
stubbed to fail if called, and the conftest guard proves zero driver calls.

Orchestrator rulings applied: R2 (`AuditHeadroomError(AuditUnavailableError)`),
R3 (`Retry-After: 1`), R4 (the check is step 1c, before step 2).
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import logging
import uuid

import pytest
from fastapi.testclient import TestClient

import chat_ui.chat_ui.state as chat_state_mod
from app.config import settings
from app.db import audit_journal
from app.db.audit_journal import _JOURNAL_ENTRY_RESERVE_BYTES
from app.db.errors import AuditHeadroomError, AuditUnavailableError, StorageError
from app.db.models import AuditLog
from app.main import app
from app.middleware.auth import require_identity
from app.models.messages import Message
from app.services import audit_logger, chat_sessions, query_pipeline
from app.services.identity import Identity
from app.services.openrouter_client import OpenRouterResult
from app.services.storage_faults import STORAGE_UNAVAILABLE_NOT_SENT_DETAIL
from app.services.v1_translate import STORAGE_UNAVAILABLE_MESSAGE
from chat_ui.chat_ui.copy import STORAGE_UNAVAILABLE_NOT_SENT_NOTICE
from chat_ui.chat_ui.state import ChatState

_USER = Identity("dana@headroom.test", "user")
_SENTINEL = "SENTINEL-prompt-preview-5d1f"
_V1_BODY = {"model": "openai/gpt-4o", "messages": [{"role": "user", "content": "hello world"}]}
_V1_TOOL = {
    "type": "function",
    "function": {"name": "bash", "description": "run", "parameters": {"type": "object"}},
}


def _row() -> AuditLog:
    return AuditLog(
        write_id=uuid.uuid4().hex, user_id="u1", timestamp="2026-11-16T14:02:13Z", prompt_hash="h",
        prompt_preview=_SENTINEL, success=True, dedup_key="k",
    )


def _admin_headers():
    return {"Authorization": f"Bearer {settings.ADMIN_TOKEN}"}


class _Upstream:
    def __init__(self):
        self.sent = 0

    def __call__(self, *args, **kwargs):
        self.sent += 1
        return OpenRouterResult(response="ok", model_used="gpt-4", tokens_used=1)


@pytest.fixture
def full_journal(tmp_path):
    """max = 2 x reserve with W = 2, so the headroom threshold is 0 bytes; one row is above it."""
    opened = audit_journal.open_journal(str(tmp_path / "buf"), 2 * _JOURNAL_ENTRY_RESERVE_BYTES, 2)
    opened.append(_row())
    yield opened
    audit_journal.close_journal()


@pytest.fixture
def no_writes(monkeypatch):
    """Anything step 2 onwards would touch fails the test: the refusal is before step 2."""

    def boom(name):
        def _boom(*a, **k):
            raise AssertionError(f"{name} must not run after a headroom refusal")

        return _boom

    monkeypatch.setattr(settings, "USAGE_LIMITS_ENABLED", False)
    for module, name in (
        (query_pipeline, "log_query"),
        (query_pipeline, "check_duplicate"),
        (query_pipeline, "authorize"),
        (query_pipeline, "admit"),
        (audit_logger, "insert_audit_log"),
    ):
        monkeypatch.setattr(module, name, boom(name))


def test_the_boundary_admits_and_one_row_over_refuses(tmp_path):
    audit_journal.open_journal(str(tmp_path / "buf"), 2 * _JOURNAL_ENTRY_RESERVE_BYTES, 2)
    try:
        audit_journal.check_admission_headroom()  # bytes == 0 == threshold: admitted
        audit_journal.append(_row())
        with pytest.raises(AuditHeadroomError) as raised:
            audit_journal.check_admission_headroom()
        assert isinstance(raised.value, AuditUnavailableError)
        assert isinstance(raised.value, StorageError)
    finally:
        audit_journal.close_journal()


def test_no_open_journal_is_a_no_op():
    assert audit_journal.current() is None
    audit_journal.check_admission_headroom()


def test_pipeline_refuses_before_step_2_with_no_row_and_no_upstream(full_journal, no_writes):
    upstream = _Upstream()

    with pytest.raises(AuditHeadroomError):
        query_pipeline.run_conversation(
            identity=_USER, messages=[Message("user", "list files")], device=None,
            model="gpt-4", openrouter_api_key=None, call_openrouter=upstream,
        )
    with pytest.raises(AuditHeadroomError):
        query_pipeline.run_query(_USER, "list files", None, "gpt-4", None, call_openrouter=upstream)

    assert upstream.sent == 0
    assert full_journal.status().entries == 1  # no row journaled either


def test_the_refusal_logs_sizes_not_contents(full_journal, caplog):
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(AuditHeadroomError):
            audit_journal.check_admission_headroom()

    assert "bytes=" in caplog.text
    assert _SENTINEL not in caplog.text


def test_query_is_503_with_the_not_sent_copy_and_retry_after_1(full_journal, no_writes, monkeypatch):
    upstream = _Upstream()
    monkeypatch.setattr("app.routers.query.call_openrouter", upstream)

    response = TestClient(app).post("/query", json={"prompt": "hi"}, headers=_admin_headers())

    assert response.status_code == 503
    assert response.json() == {"detail": STORAGE_UNAVAILABLE_NOT_SENT_DETAIL}
    assert response.headers["Retry-After"] == "1"
    assert upstream.sent == 0


@pytest.fixture
def v1(monkeypatch):
    app.dependency_overrides[require_identity] = lambda: _USER
    upstream = _Upstream()
    monkeypatch.setattr("app.routers.v1.call_openrouter", upstream)
    yield TestClient(app), upstream
    app.dependency_overrides.pop(require_identity, None)


@pytest.mark.parametrize("variant", ["json", "stream", "tools"])
def test_v1_is_a_plain_503_json_refusal(variant, v1, full_journal, no_writes, monkeypatch):
    client, upstream = v1
    body = dict(_V1_BODY)
    if variant == "stream":
        body["stream"] = True
    if variant == "tools":
        monkeypatch.setattr(settings, "V1_TOOLS_ENABLED", True)
        monkeypatch.setattr(settings, "V1_TOOL_MODELS", "")
        body["tools"] = [_V1_TOOL]

    response = client.post("/v1/chat/completions", json=body)

    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/json")  # not SSE
    assert response.json()["error"]["code"] == "storage_unavailable"
    assert response.json()["error"]["message"] == STORAGE_UNAVAILABLE_MESSAGE
    assert response.headers["Retry-After"] == "1"
    assert upstream.sent == 0


@pytest.mark.asyncio
async def test_chat_shows_an_internal_error_bubble_that_says_nothing_was_sent(
    full_journal, no_writes, monkeypatch
):
    upstream = _Upstream()
    monkeypatch.setattr(chat_state_mod, "resolve", lambda token: _USER)
    monkeypatch.setattr(chat_sessions, "create", lambda *a, **k: None)
    monkeypatch.setattr(chat_state_mod, "call_openrouter", upstream)

    async def inline(fn, *a, **k):
        return fn(*a, **k)

    monkeypatch.setattr(chat_state_mod, "run_in_pipeline", inline)
    state = ChatState(_reflex_internal_init=True)
    state.user_id = _USER.user_id
    state._token = "tok"
    state.input_text = "hello"

    await type(state).event_handlers["send"].fn(state)

    assert state.pending is False
    bubble = state.messages[-1]  # the user bubble precedes it
    assert bubble.kind == bubble.content == "internal_error"
    assert bubble.detail == STORAGE_UNAVAILABLE_NOT_SENT_NOTICE
    assert upstream.sent == 0
