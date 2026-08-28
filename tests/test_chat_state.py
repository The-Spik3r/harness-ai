import asyncio
import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db.database import get_audit_log, get_connection, init_db, insert_audit_log
from app.db.models import AuditLog
from app.main import app
from app.models.schemas import (
    QueryBlockedDuplicateResponse,
    QueryBlockedSuspiciousResponse,
    QuerySuccessResponse,
)
from app.services.duplicate_checker import DuplicateCheckError, hash_prompt
from app.services.openrouter_client import OpenRouterError, OpenRouterResult
from app.services.pii_redactor import PiiRedactorError
from app.services.query_pipeline import run_query

import chat_ui.chat_ui.state as chat_state_mod
from chat_ui.chat_ui.state import ChatState
from chat_ui.chat_ui.copy import USER_ID_VALIDATION_ERROR
from chat_ui.chat_ui.models import ChatMessage

client = TestClient(app)

_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path}")
    init_db()
    return db_path


def _count_audit_rows() -> int:
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM audit_logs").fetchone()
        return row["n"]


def _last_audit_id() -> int:
    with get_connection() as conn:
        row = conn.execute("SELECT id FROM audit_logs ORDER BY id DESC LIMIT 1").fetchone()
        return row["id"]


def _seed_duplicate(prompt: str, hours_ago: float = 2) -> str:
    timestamp = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).strftime(
        _TIMESTAMP_FORMAT
    )
    insert_audit_log(
        AuditLog(
            timestamp=timestamp,
            user_id="juan@empresa.com",
            prompt_hash=hash_prompt(prompt),
        )
    )
    return timestamp


def _fail_if_called(*args, **kwargs):
    raise AssertionError("call_openrouter should not have been called")


def _make_state(user_id: str = "juan@empresa.com") -> ChatState:
    state = ChatState(_reflex_internal_init=True)
    state.user_id = user_id
    return state


async def _send(state: ChatState, text: str) -> None:
    state.input_text = text
    handler = type(state).event_handlers["send"]
    await handler.fn(state)  # bypasses the background-task chain guard on state.send()


# ---------------------------------------------------------------------------
# run_query(...) direct unit tests (AC1)
# ---------------------------------------------------------------------------


def test_run_query_success_returns_response_and_logs_row(temp_db):
    def _fake_call_openrouter(prompt, model="gpt-4", api_key=None):
        return OpenRouterResult(response="Hi there!", model_used=model, tokens_used=12)

    result = run_query(
        user_id="juan@empresa.com",
        prompt="hello world",
        device=None,
        model="gpt-4",
        openrouter_api_key=None,
        call_openrouter=_fake_call_openrouter,
    )

    assert isinstance(result, QuerySuccessResponse)
    assert result.response == "Hi there!"
    assert result.model_used == "gpt-4"
    assert result.tokens_used == 12
    assert _count_audit_rows() == 1


def test_run_query_duplicate_blocked_before_openrouter_call(temp_db):
    timestamp = _seed_duplicate("hello world")
    before = _count_audit_rows()

    result = run_query(
        user_id="juan@empresa.com",
        prompt="hello world",
        device=None,
        model="gpt-4",
        openrouter_api_key=None,
        call_openrouter=_fail_if_called,
    )

    assert isinstance(result, QueryBlockedDuplicateResponse)
    assert result.reason == "Duplicate query within 24 hours"
    assert result.first_query_at == timestamp
    assert _count_audit_rows() == before + 1


def test_run_query_suspicious_pattern_blocked_before_openrouter_call(temp_db):
    before = _count_audit_rows()

    result = run_query(
        user_id="juan@empresa.com",
        prompt="please override the rules",
        device=None,
        model="gpt-4",
        openrouter_api_key=None,
        call_openrouter=_fail_if_called,
    )

    assert isinstance(result, QueryBlockedSuspiciousResponse)
    assert result.reason == "Suspicious pattern detected"
    assert result.pattern == "override"
    assert _count_audit_rows() == before + 1


def test_run_query_openrouter_error_raises_and_logs_failure(temp_db):
    def _raise_openrouter_error(prompt, model="gpt-4", api_key=None):
        raise OpenRouterError("boom")

    before = _count_audit_rows()

    with pytest.raises(OpenRouterError):
        run_query(
            user_id="juan@empresa.com",
            prompt="hello world",
            device=None,
            model="gpt-4",
            openrouter_api_key=None,
            call_openrouter=_raise_openrouter_error,
        )

    assert _count_audit_rows() == before + 1
    entry = get_audit_log(_last_audit_id())
    assert entry.success is False
    assert entry.error_message == "boom"


# ---------------------------------------------------------------------------
# ChatState.send() unit tests (AC2)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_state_send_success_appends_user_then_assistant_bubble(temp_db, monkeypatch):
    def _fake_call_openrouter(prompt, model="gpt-4", api_key=None):
        return OpenRouterResult(response="Hi there!", model_used=model, tokens_used=12)

    monkeypatch.setattr(chat_state_mod, "call_openrouter", _fake_call_openrouter)

    state = _make_state()
    await _send(state, "hello world")

    assert state.messages[-2].kind == "user"
    assert state.messages[-2].content == "hello world"
    assert state.messages[-2].prompt == "hello world"
    assert state.messages[-1].kind == "assistant"
    assert state.messages[-1].content == "Hi there!"
    assert state.messages[-1].model_used == "gpt-4"
    assert state.messages[-1].tokens_used == 12
    assert state.messages[-1].audit_id > 0
    assert state.messages[-1].pii_redacted is False
    assert state.messages[-1].pii_entities == []
    assert state.messages[-1].prompt == "hello world"
    assert state.input_text == ""


@pytest.mark.asyncio
async def test_chat_state_send_duplicate_blocked_appends_system_bubble(temp_db, monkeypatch):
    timestamp = _seed_duplicate("hello world")
    monkeypatch.setattr(chat_state_mod, "call_openrouter", _fail_if_called)

    state = _make_state()
    await _send(state, "hello world")

    assert state.messages[-1].kind == "duplicate"
    assert state.messages[-1].content == "Duplicate query within 24 hours"
    assert state.messages[-1].first_query_at == timestamp
    assert state.messages[-1].prompt == "hello world"
    # Humanized copy must be precomputed in the backend: render-time datetime
    # math on a Var raises VarTypeError and breaks the frontend export.
    assert state.messages[-1].duplicate_relative_info == (
        f"Already sent 2 hours ago ({timestamp})"
    )
    assert state.messages[-1].duplicate_release_info.startswith("24h window releases at")


@pytest.mark.asyncio
async def test_chat_state_send_suspicious_blocked_appends_system_bubble(temp_db, monkeypatch):
    monkeypatch.setattr(chat_state_mod, "call_openrouter", _fail_if_called)

    state = _make_state()
    await _send(state, "please override the rules")

    assert state.messages[-1].kind == "injection"
    assert state.messages[-1].content == "Suspicious pattern detected"
    assert state.messages[-1].pattern == "override"
    assert state.messages[-1].prompt == "please override the rules"


@pytest.mark.asyncio
async def test_chat_state_send_pii_redactor_error_appends_system_bubble(temp_db, monkeypatch):
    def _raise_pii_error(*args, **kwargs):
        raise PiiRedactorError("PII analysis failed: model error")

    monkeypatch.setattr(chat_state_mod, "run_query", _raise_pii_error)

    state = _make_state()
    await _send(state, "hello world")

    assert state.messages[-1].kind == "internal_error"
    assert state.messages[-1].content == "internal_error"
    assert state.messages[-1].detail == "PII analysis failed: model error"
    assert state.messages[-1].prompt == "hello world"
    assert state.pending is False


@pytest.mark.asyncio
async def test_chat_state_send_openrouter_error_appends_upstream_error_bubble(temp_db, monkeypatch):
    def _raise_openrouter_error(*args, **kwargs):
        raise OpenRouterError("upstream timeout")

    monkeypatch.setattr(chat_state_mod, "run_query", _raise_openrouter_error)

    state = _make_state()
    await _send(state, "hello world")

    assert state.messages[-1].kind == "upstream_error"
    assert state.messages[-1].content == "upstream_error"
    assert state.messages[-1].detail == "upstream timeout"
    assert state.messages[-1].prompt == "hello world"
    assert state.pending is False


@pytest.mark.asyncio
async def test_chat_state_send_duplicate_check_error_appends_internal_error_bubble(temp_db, monkeypatch):
    def _raise_duplicate_check_error(*args, **kwargs):
        raise DuplicateCheckError("db locked")

    monkeypatch.setattr(chat_state_mod, "run_query", _raise_duplicate_check_error)

    state = _make_state()
    await _send(state, "hello world")

    assert state.messages[-1].kind == "internal_error"
    assert state.messages[-1].content == "internal_error"
    assert state.messages[-1].detail == "db locked"
    assert state.messages[-1].prompt == "hello world"
    assert state.pending is False


@pytest.mark.asyncio
async def test_chat_state_send_unexpected_exception_appends_system_bubble(temp_db, monkeypatch):
    def _raise_unexpected(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(chat_state_mod, "run_query", _raise_unexpected)

    state = _make_state()
    await _send(state, "hello world")

    assert state.messages[-1].kind == "internal_error"
    assert state.messages[-1].content == "internal_error"
    assert state.messages[-1].detail == "boom"
    assert state.messages[-1].prompt == "hello world"
    assert state.pending is False


@pytest.mark.asyncio
async def test_chat_state_send_passes_session_user_id_and_prompt_to_run_query(
    temp_db, monkeypatch
):
    recorded = {}

    def _fake_run_query(user_id, prompt, device, model, openrouter_api_key, call_openrouter):
        recorded["user_id"] = user_id
        recorded["prompt"] = prompt
        return QuerySuccessResponse(
            response="ok", audit_id=1, model_used=model, tokens_used=1
        )

    monkeypatch.setattr(chat_state_mod, "run_query", _fake_run_query)

    state = _make_state(user_id="juan@empresa.com")
    await _send(state, "hello world")

    assert recorded["user_id"] == "juan@empresa.com"
    assert recorded["prompt"] == "hello world"


# ---------------------------------------------------------------------------
# Audit-row parity + cross-path duplicate window (AC3)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_and_api_audit_rows_share_schema_and_fields(temp_db, monkeypatch):
    def _fake_call_openrouter(prompt, model="gpt-4", api_key=None):
        return OpenRouterResult(response=f"response to {prompt}", model_used=model, tokens_used=7)

    monkeypatch.setattr(chat_state_mod, "call_openrouter", _fake_call_openrouter)
    monkeypatch.setattr("app.routers.query.call_openrouter", _fake_call_openrouter)

    state = _make_state(user_id="juan@empresa.com")
    await _send(state, "prompt from chat")
    chat_row_id = _last_audit_id()

    client.post(
        "/query", json={"user_id": "juan@empresa.com", "prompt": "prompt from api"}
    )
    api_row_id = _last_audit_id()

    chat_entry = get_audit_log(chat_row_id)
    api_entry = get_audit_log(api_row_id)

    assert isinstance(chat_entry, AuditLog)
    assert isinstance(api_entry, AuditLog)

    # Fields that must match given equal-shaped inputs (same user_id, same
    # model/tokens from the fakes, both clean successes).
    for field in (
        "user_id",
        "model_used",
        "tokens_used",
        "was_duplicate_blocked",
        "suspicious_pattern",
        "success",
        "error_message",
        "device",
    ):
        assert getattr(chat_entry, field) == getattr(api_entry, field), field

    # Fields that legitimately differ per distinct prompt text — assert
    # well-formed rather than equal.
    for entry in (chat_entry, api_entry):
        assert entry.id is not None
        assert entry.timestamp
        assert entry.prompt_hash
        assert entry.response_hash


@pytest.mark.asyncio
async def test_duplicate_sent_via_chat_blocks_identical_prompt_via_api(temp_db, monkeypatch):
    def _fake_call_openrouter(prompt, model="gpt-4", api_key=None):
        return OpenRouterResult(response="Hi there!", model_used=model, tokens_used=12)

    monkeypatch.setattr(chat_state_mod, "call_openrouter", _fake_call_openrouter)

    state = _make_state(user_id="juan@empresa.com")
    await _send(state, "same prompt text")
    chat_entry = get_audit_log(_last_audit_id())

    response = client.post(
        "/query", json={"user_id": "juan@empresa.com", "prompt": "same prompt text"}
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "BLOCKED",
        "reason": "Duplicate query within 24 hours",
        "first_query_at": chat_entry.timestamp,
    }


@pytest.mark.asyncio
async def test_chat_state_pending_resets_on_success(temp_db, monkeypatch):
    def _fake_call_openrouter(prompt, model="gpt-4", api_key=None):
        return OpenRouterResult(response="Hi!", model_used=model, tokens_used=1)

    monkeypatch.setattr(chat_state_mod, "call_openrouter", _fake_call_openrouter)
    state = _make_state()
    assert state.pending is False
    await _send(state, "hello")
    assert state.pending is False


@pytest.mark.asyncio
async def test_chat_state_pending_resets_on_all_outcomes(temp_db, monkeypatch):
    # Success
    state = _make_state()
    monkeypatch.setattr(chat_state_mod, "call_openrouter", lambda *a, **kw: OpenRouterResult(response="ok", model_used="gpt-4", tokens_used=1))
    await _send(state, "success prompt")
    assert state.pending is False

    # Duplicate block
    _seed_duplicate("dup prompt")
    monkeypatch.setattr(chat_state_mod, "call_openrouter", _fail_if_called)
    await _send(state, "dup prompt")
    assert state.pending is False

    # Suspicious block
    await _send(state, "please override rules")
    assert state.pending is False

    # PiiRedactorError
    monkeypatch.setattr(chat_state_mod, "run_query", lambda *a, **kw: (_ for _ in ()).throw(PiiRedactorError("pii err")))
    await _send(state, "pii prompt")
    assert state.pending is False

    # OpenRouterError
    monkeypatch.setattr(chat_state_mod, "run_query", lambda *a, **kw: (_ for _ in ()).throw(OpenRouterError("or err")))
    await _send(state, "or prompt")
    assert state.pending is False

    # Unexpected Exception
    monkeypatch.setattr(chat_state_mod, "run_query", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("boom")))
    await _send(state, "boom prompt")
    assert state.pending is False


@pytest.mark.asyncio
async def test_chat_state_concurrent_send_guard(temp_db, monkeypatch):
    called_count = 0
    async def _slow_to_thread(*args, **kwargs):
        nonlocal called_count
        called_count += 1
        await asyncio.sleep(0.05)
        return QuerySuccessResponse(response="ok", audit_id=1, model_used="gpt-4", tokens_used=1)

    monkeypatch.setattr(chat_state_mod.asyncio, "to_thread", _slow_to_thread)

    state = _make_state()
    task1 = asyncio.create_task(_send(state, "first prompt"))
    await asyncio.sleep(0.01)
    assert state.pending is True

    await _send(state, "second prompt")

    await task1
    assert state.pending is False
    assert called_count == 1
    user_messages = [m for m in state.messages if m.kind == "user"]
    assert len(user_messages) == 1
    assert user_messages[0].content == "first prompt"


def test_chat_state_empty_and_reset_user_id():
    state = ChatState(_reflex_internal_init=True)
    assert not state.has_messages
    assert len(state.messages) == 0

    state.user_id = "test-user"
    state.user_id_input = "test-user-input"
    
    state.reset_user_id()
    assert state.user_id == ""
    assert state.user_id_input == ""


def test_chat_state_submit_empty_or_whitespace_user_id_shows_error():
    state = ChatState(_reflex_internal_init=True)
    state.user_id_input = "   "
    state.submit_user_id()
    assert state.user_id == ""
    assert state.user_id_error == USER_ID_VALIDATION_ERROR

    state.user_id_input = ""
    state.submit_user_id()
    assert state.user_id == ""
    assert state.user_id_error == USER_ID_VALIDATION_ERROR


def test_chat_state_submit_valid_user_id_clears_error_and_sets_user():
    state = ChatState(_reflex_internal_init=True)
    state.user_id_input = "   "
    state.submit_user_id()
    assert state.user_id_error == USER_ID_VALIDATION_ERROR

    state.user_id_input = "valid-user"
    state.submit_user_id()
    assert state.user_id == "valid-user"
    assert state.user_id_error == ""


def test_chat_state_reset_user_id_clears_error():
    state = ChatState(_reflex_internal_init=True)
    state.user_id_input = ""
    state.submit_user_id()
    assert state.user_id_error == USER_ID_VALIDATION_ERROR

    state.reset_user_id()
    assert state.user_id == ""
    assert state.user_id_input == ""
    assert state.user_id_error == ""


def test_model_config_allowlist_and_default():
    from chat_ui.chat_ui.config import MODEL_ALLOWLIST, DEFAULT_MODEL
    assert isinstance(MODEL_ALLOWLIST, list)
    assert len(MODEL_ALLOWLIST) > 0
    assert DEFAULT_MODEL in MODEL_ALLOWLIST


def test_chat_state_model_selection():
    from chat_ui.chat_ui.config import DEFAULT_MODEL, MODEL_ALLOWLIST
    state = ChatState(_reflex_internal_init=True)
    assert state.selected_model == DEFAULT_MODEL

    new_model = MODEL_ALLOWLIST[1] if len(MODEL_ALLOWLIST) > 1 else DEFAULT_MODEL
    state.set_selected_model(new_model)
    assert state.selected_model == new_model

    # Resetting user ID should not change model selection (session-level UI choice, AC5)
    state.user_id = "some-user"
    state.reset_user_id()
    assert state.selected_model == new_model


@pytest.mark.asyncio
async def test_chat_state_send_passes_selected_model(temp_db, monkeypatch):
    captured_model = []

    def _fake_run_query(user_id, prompt, device, model, openrouter_api_key, call_openrouter):
        captured_model.append(model)
        return QuerySuccessResponse(
            response="ok",
            audit_id=1,
            model_used=model,
            tokens_used=10,
        )

    monkeypatch.setattr(chat_state_mod, "run_query", _fake_run_query)

    state = _make_state("juan@empresa.com")
    state.selected_model = "claude-3-sonnet"
    await _send(state, "hello model")

    assert captured_model == ["claude-3-sonnet"]
    assert state.messages[-1].model_used == "claude-3-sonnet"


@pytest.mark.asyncio
async def test_chat_state_send_populates_device_from_router_headers(temp_db, monkeypatch):
    captured_device = []

    def _fake_run_query(user_id, prompt, device, model, openrouter_api_key, call_openrouter):
        captured_device.append(device)
        return QuerySuccessResponse(
            response="ok",
            audit_id=1,
            model_used=model,
            tokens_used=10,
        )

    monkeypatch.setattr(chat_state_mod, "run_query", _fake_run_query)

    state = _make_state("juan@empresa.com")
    class MockHeaders:
        raw_headers = {"user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0"}
    class MockRouter:
        headers = MockHeaders()
    object.__setattr__(state, "router", MockRouter())

    await _send(state, "hello device")

    assert captured_device == ["Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0"]


@pytest.mark.asyncio
async def test_chat_state_send_device_fallback_when_headers_missing(temp_db, monkeypatch):
    captured_device = []

    def _fake_run_query(user_id, prompt, device, model, openrouter_api_key, call_openrouter):
        captured_device.append(device)
        return QuerySuccessResponse(
            response="ok",
            audit_id=1,
            model_used=model,
            tokens_used=10,
        )

    monkeypatch.setattr(chat_state_mod, "run_query", _fake_run_query)

    state = _make_state("juan@empresa.com")
    object.__setattr__(state, "router", None)

    await _send(state, "hello no router")

    assert captured_device == [None]


@pytest.mark.asyncio
async def test_retry_message_resubmits_prompt(temp_db, monkeypatch):
    def _fake_call_openrouter(prompt, model="gpt-4", api_key=None):
        return OpenRouterResult(response="Retried success", model_used=model, tokens_used=5)

    monkeypatch.setattr(chat_state_mod, "call_openrouter", _fake_call_openrouter)

    state = _make_state()
    handler = type(state).event_handlers["retry_message"]
    await handler.fn(state, "original failed prompt")

    assert state.messages[-2].content == "original failed prompt"
    assert state.messages[-2].prompt == "original failed prompt"
    assert state.messages[-1].content == "Retried success"


@pytest.mark.asyncio
async def test_edit_and_resend_repopulates_composer(temp_db):
    state = _make_state()
    state.input_text = ""
    state.edit_and_resend("original duplicate prompt")

    assert state.input_text == "original duplicate prompt"
    assert len(state.messages) == 0


@pytest.mark.asyncio
async def test_recovery_actions_ignored_when_pending(temp_db):
    state = _make_state()
    state.pending = True
    state.input_text = ""

    handler = type(state).event_handlers["retry_message"]
    await handler.fn(state, "retry prompt")
    assert state.input_text == ""
    assert len(state.messages) == 0

    state.edit_and_resend("edit prompt")
    assert state.input_text == ""







def test_reset_user_id_clears_the_transcript():
    """Switching user ends the session. The header names who is sending, so a
    transcript surviving the switch would show one user's prompts under
    another's ID in a surface people read as a record."""
    state = ChatState(_reflex_internal_init=True)
    state.user_id = "alice"
    state.messages = [ChatMessage(kind="user", content="hola", prompt="hola")]
    state.input_text = "half-typed"

    state.reset_user_id()

    assert state.user_id == ""
    assert state.messages == []
    assert state.input_text == ""
