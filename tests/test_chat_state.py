import ast
import asyncio
import dataclasses
import os
import pathlib

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.db.database import (
    count_chat_sessions,
    create_chat_session,
    deactivate_user,
    get_audit_log,
    get_connection,
    insert_audit_log,
    insert_user,
    list_chat_messages,
    list_chat_sessions,
    touch_chat_session,
)
from app.db.errors import StorageError
from app.db.models import AuditLog, StoredMessage, User
from app.main import app
from app.models.schemas import (
    QueryBlockedDuplicateResponse,
    QueryBlockedForbiddenResponse,
    QueryBlockedSuspiciousResponse,
    QuerySuccessResponse,
)
from app.config import settings
from app.services import chat_sessions
from app.services.chat_sessions import ChatSessionError
from app.services.authz import PERMISSION_QUERY_SUBMIT
from app.services.duplicate_checker import DuplicateCheckError, hash_prompt
from app.services.identity import Identity, hash_token
from app.services.openrouter_client import OpenRouterError, OpenRouterResult
from app.services.pii_redactor import PiiRedactorError
from app.services.query_pipeline import run_query

import chat_ui.chat_ui.state as chat_state_mod
from chat_ui.chat_ui.state import ChatState
from chat_ui.chat_ui.copy import (
    LOGIN_INVALID_TOKEN_ERROR,
    LOGIN_TOKEN_REQUIRED_ERROR,
    SESSION_INVALIDATED_ERROR,
    SESSION_ORDER_STALE_NOTICE,
    TRANSCRIPT_NOT_LOADED_NOTICE,
    TRANSCRIPT_NOT_SAVED_NOTICE,
)
from chat_ui.chat_ui.formatting import derive_title, format_duplicate_info
from chat_ui.chat_ui.models import ChatMessage, ChatSessionSummary

client = TestClient(app)

_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

_AUTH_USER_ID = "juan@empresa.com"
_AUTH_TOKEN = "test-user-token"


@pytest.fixture
def temp_db(temp_db):
    """conftest's initialized database, plus this suite's authenticated user."""
    insert_user(
        User(user_id=_AUTH_USER_ID, role="user", token_hash=hash_token(_AUTH_TOKEN))
    )
    return temp_db


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


def _make_state(user_id: str = _AUTH_USER_ID, token: str = _AUTH_TOKEN) -> ChatState:
    state = ChatState(_reflex_internal_init=True)
    state.user_id = user_id
    state._token = token
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
        identity=Identity(user_id="juan@empresa.com", role="user"),
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
        identity=Identity(user_id="juan@empresa.com", role="user"),
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
        identity=Identity(user_id="juan@empresa.com", role="user"),
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
            identity=Identity(user_id="juan@empresa.com", role="user"),
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
async def test_chat_state_send_forbidden_response_renders_its_own_bubble_not_injection(
    temp_db, monkeypatch
):
    """AC5: a QueryBlockedForbiddenResponse must hit its own isinstance branch,
    not fall through to the injection bubble the old catch-all `else` used."""

    def _fake_run_query(identity, prompt, device, model, openrouter_api_key, call_openrouter, session_id=None):
        return QueryBlockedForbiddenResponse(
            reason="Model not permitted for this role",
            required_permission="query:model:gpt-4",
        )

    monkeypatch.setattr(chat_state_mod, "run_query", _fake_run_query)

    state = _make_state()
    await _send(state, "hello world")

    assert state.messages[-1].kind == "forbidden"
    assert state.messages[-1].kind != "injection"
    assert state.messages[-1].content == "Model not permitted for this role"
    assert state.messages[-1].required_permission == "query:model:gpt-4"


@pytest.mark.asyncio
async def test_chat_state_send_reresolves_role_on_every_call(temp_db, monkeypatch):
    """AC3: the role must come from the database on every call, never from
    anything cached on ChatState -- promoting the user mid-session with no
    code path that touches ChatState must still be picked up on the next
    send()."""
    recorded_roles = []

    def _fake_run_query(identity, prompt, device, model, openrouter_api_key, call_openrouter, session_id=None):
        recorded_roles.append(identity.role)
        return QuerySuccessResponse(response="ok", audit_id=1, model_used=model, tokens_used=1)

    monkeypatch.setattr(chat_state_mod, "run_query", _fake_run_query)

    state = _make_state()
    await _send(state, "first prompt")
    assert recorded_roles == ["user"]

    with get_connection() as conn:
        conn.execute("UPDATE users SET role = 'admin' WHERE user_id = ?", (_AUTH_USER_ID,))

    await _send(state, "second prompt")
    assert recorded_roles == ["user", "admin"]


def test_chat_state_holds_no_token_or_role_var():
    """AC4: only `user_id` (and the backend-only `_token`) may exist as an
    identity-related field -- no field literally named `token` or `role`
    anywhere on the class."""
    assert "role" not in ChatState.__annotations__
    assert "token" not in ChatState.__annotations__
    assert "_token" in ChatState.__annotations__


@pytest.mark.asyncio
async def test_chat_state_send_when_credential_revoked_mid_session_appends_internal_error(
    temp_db, monkeypatch
):
    monkeypatch.setattr(chat_state_mod, "run_query", _fail_if_called)
    deactivate_user(_AUTH_USER_ID)

    state = _make_state()
    await _send(state, "hello world")

    assert state.messages[-1].kind == "internal_error"
    assert state.pending is False


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
async def test_chat_state_send_passes_resolved_identity_and_prompt_to_run_query(
    temp_db, monkeypatch
):
    recorded = {}

    def _fake_run_query(identity, prompt, device, model, openrouter_api_key, call_openrouter, session_id=None):
        recorded["identity"] = identity
        recorded["prompt"] = prompt
        return QuerySuccessResponse(
            response="ok", audit_id=1, model_used=model, tokens_used=1
        )

    monkeypatch.setattr(chat_state_mod, "run_query", _fake_run_query)

    state = _make_state()
    await _send(state, "hello world")

    assert recorded["identity"].user_id == _AUTH_USER_ID
    assert recorded["identity"].role == "user"
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

    state = _make_state()
    await _send(state, "prompt from chat")
    chat_row_id = _last_audit_id()

    client.post(
        "/query",
        headers={"Authorization": f"Bearer {_AUTH_TOKEN}"},
        json={"prompt": "prompt from api"},
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

    state = _make_state()
    await _send(state, "same prompt text")
    chat_entry = get_audit_log(_last_audit_id())

    response = client.post(
        "/query",
        headers={"Authorization": f"Bearer {_AUTH_TOKEN}"},
        json={"prompt": "same prompt text"},
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
    async def _slow_to_thread(fn, *args, **kwargs):
        # _do_send offloads two different callables now: the lazy session
        # create and the pipeline call. Count only the pipeline, so
        # `called_count` keeps meaning "run_query ran once" rather than
        # "something was offloaded once", and hand each caller the return
        # type it actually expects.
        nonlocal called_count
        await asyncio.sleep(0.05)
        if fn is chat_state_mod.run_query:
            called_count += 1
            return QuerySuccessResponse(response="ok", audit_id=1, model_used="gpt-4", tokens_used=1)
        return await asyncio.get_running_loop().run_in_executor(
            None, lambda: fn(*args, **kwargs)
        )

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
    state.token_input = "test-user-input"

    state.logout()
    assert state.user_id == ""
    assert state.token_input == ""


@pytest.mark.asyncio
async def test_chat_state_login_empty_token_shows_error():
    state = ChatState(_reflex_internal_init=True)
    state.token_input = "   "
    await state.login()
    assert state.user_id == ""
    assert state.login_error == LOGIN_TOKEN_REQUIRED_ERROR

    state.token_input = ""
    await state.login()
    assert state.user_id == ""
    assert state.login_error == LOGIN_TOKEN_REQUIRED_ERROR


@pytest.mark.asyncio
async def test_chat_state_login_invalid_token_shows_error_and_stays_locked(temp_db):
    state = ChatState(_reflex_internal_init=True)
    state.token_input = "not-a-real-token"
    await state.login()
    assert state.user_id == ""
    assert state.login_error == LOGIN_INVALID_TOKEN_ERROR


@pytest.mark.asyncio
async def test_chat_state_login_deactivated_token_rejected(temp_db):
    deactivate_user(_AUTH_USER_ID)
    state = ChatState(_reflex_internal_init=True)
    state.token_input = _AUTH_TOKEN
    await state.login()
    assert state.user_id == ""
    assert state.login_error == LOGIN_INVALID_TOKEN_ERROR


@pytest.mark.asyncio
async def test_chat_state_login_valid_token_sets_user_id_and_clears_error(temp_db):
    state = ChatState(_reflex_internal_init=True)
    state.token_input = "   "
    await state.login()
    assert state.login_error == LOGIN_TOKEN_REQUIRED_ERROR

    state.token_input = _AUTH_TOKEN
    await state.login()
    assert state.user_id == _AUTH_USER_ID
    assert state.login_error == ""
    assert state.token_input == ""
    assert state._token == _AUTH_TOKEN


@pytest.mark.asyncio
async def test_chat_state_logout_clears_session_and_credential(temp_db):
    state = ChatState(_reflex_internal_init=True)
    state.token_input = _AUTH_TOKEN
    await state.login()
    assert state.user_id == _AUTH_USER_ID

    state.logout()
    assert state.user_id == ""
    assert state.token_input == ""
    assert state.login_error == ""
    assert state._token == ""


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
    state.logout()
    assert state.selected_model == new_model


@pytest.mark.asyncio
async def test_chat_state_send_passes_selected_model(temp_db, monkeypatch):
    captured_model = []

    def _fake_run_query(identity, prompt, device, model, openrouter_api_key, call_openrouter, session_id=None):
        captured_model.append(model)
        return QuerySuccessResponse(
            response="ok",
            audit_id=1,
            model_used=model,
            tokens_used=10,
        )

    monkeypatch.setattr(chat_state_mod, "run_query", _fake_run_query)

    state = _make_state()
    state.selected_model = "claude-3-sonnet"
    await _send(state, "hello model")

    assert captured_model == ["claude-3-sonnet"]
    assert state.messages[-1].model_used == "claude-3-sonnet"


@pytest.mark.asyncio
async def test_chat_state_send_populates_device_from_router_headers(temp_db, monkeypatch):
    captured_device = []

    def _fake_run_query(identity, prompt, device, model, openrouter_api_key, call_openrouter, session_id=None):
        captured_device.append(device)
        return QuerySuccessResponse(
            response="ok",
            audit_id=1,
            model_used=model,
            tokens_used=10,
        )

    monkeypatch.setattr(chat_state_mod, "run_query", _fake_run_query)

    state = _make_state()
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

    def _fake_run_query(identity, prompt, device, model, openrouter_api_key, call_openrouter, session_id=None):
        captured_device.append(device)
        return QuerySuccessResponse(
            response="ok",
            audit_id=1,
            model_used=model,
            tokens_used=10,
        )

    monkeypatch.setattr(chat_state_mod, "run_query", _fake_run_query)

    state = _make_state()
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


def test_logout_clears_the_transcript():
    """Switching user ends the session. The header names who is sending, so a
    transcript surviving the switch would show one user's prompts under
    another's ID in a surface people read as a record."""
    state = ChatState(_reflex_internal_init=True)
    state.user_id = "alice"
    state.messages = [ChatMessage(kind="user", content="hola", prompt="hola")]
    state.input_text = "half-typed"

    state.logout()

    assert state.user_id == ""
    assert state.messages == []
    assert state.input_text == ""


# ---------------------------------------------------------------------------
# Cross-ingress denial parity (STORY-017) -- the regression guard for PRD
# Risk 1. test_chat_and_api_audit_rows_share_schema_and_fields above is the
# grant-path precedent these mirror for the deny path.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_model_allowlist_denial_identical_through_chat_and_api(temp_db, monkeypatch):
    """The model-allowlist check inside run_query() is a permission both
    ingresses reach through literally the same code path with no earlier
    gate on either side -- the strongest available proof that the chat UI
    cannot bypass authorization the router enforces (PRD Risk 1)."""
    model = "not-a-real-model"
    monkeypatch.setattr(chat_state_mod, "call_openrouter", _fail_if_called)
    monkeypatch.setattr("app.routers.query.call_openrouter", _fail_if_called)

    state = _make_state()
    state.selected_model = model
    await _send(state, "chat prompt outside allowlist")
    chat_bubble = state.messages[-1]
    chat_row_id = _last_audit_id()

    response = client.post(
        "/query",
        headers={"Authorization": f"Bearer {_AUTH_TOKEN}"},
        json={"prompt": "api prompt outside allowlist", "model": model},
    )
    api_row_id = _last_audit_id()

    required_permission = f"query:model:{model}"
    assert chat_bubble.kind == "forbidden"
    assert chat_bubble.required_permission == required_permission

    assert response.status_code == 200
    api_body = response.json()
    assert api_body["status"] == "BLOCKED"
    assert api_body["required_permission"] == required_permission

    assert chat_row_id != api_row_id
    assert _count_audit_rows() == 2
    for entry in (get_audit_log(chat_row_id), get_audit_log(api_row_id)):
        assert entry.role == "user"
        assert entry.denied_permission == required_permission


@pytest.mark.asyncio
async def test_query_submit_denial_decision_parity_across_ingresses_with_documented_audit_asymmetry(
    temp_db, monkeypatch
):
    """PRD Section 9 draws a deliberate line between a missing *endpoint*
    permission (401/403, transport-level) and a *content* policy refusal
    (200 + BLOCKED, audited like any other pipeline block). STORY-013 wired
    POST /query's query:submit check as Depends(require_permission(...)) on
    the router itself (app/routers/query.py:18), so an HTTP query:submit
    denial never reaches run_query()'s own step-0 authorize() call and
    writes no audit row (tests/test_query_router.py::
    test_identity_lacking_query_submit_returns_403_naming_permission already
    proves this in isolation). The chat ingress has no router layer at all
    -- ChatState._do_send() calls run_query() directly, so its only
    enforcement of query:submit is that same step-0 check, which DOES log a
    row. Both ingresses reach the identical *decision* -- refused, OpenRouter
    never called -- only the audit-row count legitimately differs, by the
    router's own pre-existing design. This test asserts that documented
    asymmetry rather than papering over it.
    """
    insert_user(
        User(user_id="reviewer", role="auditor", token_hash=hash_token("auditor-chat-token"))
    )
    monkeypatch.setattr(chat_state_mod, "call_openrouter", _fail_if_called)
    monkeypatch.setattr("app.routers.query.call_openrouter", _fail_if_called)

    state = _make_state(user_id="reviewer", token="auditor-chat-token")
    await _send(state, "auditor tries to query via chat")
    bubble = state.messages[-1]

    assert bubble.kind == "forbidden"
    assert bubble.required_permission == PERMISSION_QUERY_SUBMIT
    assert _count_audit_rows() == 1
    chat_entry = get_audit_log(_last_audit_id())
    assert chat_entry.role == "auditor"
    assert chat_entry.denied_permission == PERMISSION_QUERY_SUBMIT

    response = client.post(
        "/query",
        headers={"Authorization": "Bearer auditor-chat-token"},
        json={"prompt": "auditor tries to query via api"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": f"Permission denied: {PERMISSION_QUERY_SUBMIT}"}
    # Documented asymmetry: the router's require_permission dependency stops
    # this request before run_query() ever runs, so no second audit row is
    # written -- the count stays at 1, not 2.
    assert _count_audit_rows() == 1


# ---------------------------------------------------------------------------
# Session list and lazy creation (STORY-013)
# ---------------------------------------------------------------------------


def _session_rows(user_id: str = _AUTH_USER_ID):
    """The user's session rows, read straight from the store.

    Deliberately not through app/services/chat_sessions.py: AC 3 says "when the
    database is inspected", and asserting the service's own emptiness against
    the service would be asserting it against itself. The AST guard in
    tests/test_chat_sessions.py scans app/ and chat_ui/, not tests/.
    """
    return list_chat_sessions(user_id, limit=100)


def _backdate_session(session_id: str, hours_ago: float) -> None:
    """Move a session's updated_at into the past, so rail ordering is a fact
    rather than a tie-break."""
    stamp = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).strftime(
        _TIMESTAMP_FORMAT
    )
    with get_connection() as conn:
        conn.execute(
            "UPDATE chat_sessions SET updated_at = ? WHERE session_id = ?",
            (stamp, session_id),
        )


def _capturing_run_query(result=None, captured=None):
    """A run_query stand-in that records the session_id it was handed."""
    if result is None:
        result = QuerySuccessResponse(
            response="ok", audit_id=1, model_used="gpt-4", tokens_used=1
        )

    def _fake(identity, prompt, device, model, openrouter_api_key,
              call_openrouter, session_id=None):
        if captured is not None:
            captured["session_id"] = session_id
            captured["called"] = captured.get("called", 0) + 1
        return result

    return _fake


def test_chat_state_declares_the_three_session_vars():
    """AC 1. Asserted against __annotations__ rather than an instance, the way
    test_chat_state_holds_no_token_or_role_var pins the absence of a role var:
    the declaration is the thing the story is about."""
    annotations = ChatState.__annotations__
    assert annotations["sessions"] == list[ChatSessionSummary]
    assert annotations["active_session_id"] is str
    assert annotations["sessions_error"] is str

    state = ChatState(_reflex_internal_init=True)
    assert state.sessions == []
    assert state.active_session_id == ""
    assert state.sessions_error == ""


@pytest.mark.asyncio
async def test_login_loads_the_session_list_into_state(temp_db):
    """AC 2. Two owned sessions come back newest-activity-first, each carrying
    a title and a recomputed relative activity time."""
    older = create_chat_session(_AUTH_USER_ID, "Older chat")
    newer = create_chat_session(_AUTH_USER_ID, "Newer chat")
    # Backdate the first row rather than touching the second. Both are created
    # inside the same second, and `updated_at` is a TEXT timestamp: relying on
    # a touch to separate them would be relying on a tie that PRD-006 Section
    # 13 already records as breaking arbitrarily.
    _backdate_session(older, hours_ago=3)

    state = ChatState(_reflex_internal_init=True)
    state.token_input = _AUTH_TOKEN
    await state.login()

    assert state.sessions_error == ""
    assert [s.session_id for s in state.sessions] == [newer, older]
    assert [s.title for s in state.sessions] == ["Newer chat", "Older chat"]
    # Recomputed on load, never stored: a persisted "2m ago" is wrong the
    # moment it is read back (PRD Section 6).
    assert all(s.activity_info for s in state.sessions)


@pytest.mark.asyncio
async def test_login_offloads_the_session_read_to_a_thread(temp_db, monkeypatch):
    """AC 2's second half: the read is offloaded via asyncio.to_thread, not run
    on the event loop. Pins the function actually handed to it, so replacing the
    offload with a direct call fails here."""
    create_chat_session(_AUTH_USER_ID, "A chat")
    offloaded = []
    real_to_thread = chat_state_mod.asyncio.to_thread

    async def _recording_to_thread(fn, *args, **kwargs):
        offloaded.append(fn)
        return await real_to_thread(fn, *args, **kwargs)

    monkeypatch.setattr(chat_state_mod.asyncio, "to_thread", _recording_to_thread)

    state = ChatState(_reflex_internal_init=True)
    state.token_input = _AUTH_TOKEN
    await state.login()

    assert chat_sessions.list_for in offloaded
    assert len(state.sessions) == 1


@pytest.mark.asyncio
async def test_an_idle_mount_creates_no_session_row(temp_db):
    """AC 3, the PRD's headline behavioural claim: "a session row is written on
    the first send, never on page load -- an opened-and-abandoned tab leaves
    nothing behind." Sign in, send nothing, inspect the database."""
    state = ChatState(_reflex_internal_init=True)
    state.token_input = _AUTH_TOKEN
    await state.login()

    assert state.user_id == _AUTH_USER_ID
    assert count_chat_sessions(_AUTH_USER_ID) == 0
    assert state.active_session_id == ""
    assert state.sessions == []


@pytest.mark.asyncio
async def test_first_send_creates_exactly_one_session_titled_from_the_prompt(
    temp_db, monkeypatch
):
    """AC 4. One session, titled by formatting.derive_title through the
    service's injected-callable seam, and active_session_id names its row."""
    monkeypatch.setattr(chat_state_mod, "run_query", _capturing_run_query())

    state = _make_state()
    await _send(state, "summarise the Q3 vendor spend")

    rows = _session_rows()
    assert len(rows) == 1
    assert rows[0].title == derive_title("summarise the Q3 vendor spend")
    assert state.active_session_id == rows[0].session_id


@pytest.mark.asyncio
async def test_active_session_id_is_set_before_run_query_is_called(
    temp_db, monkeypatch
):
    """AC 4's ordering half, and the only assertion that distinguishes a create
    placed before the pipeline call from one placed after it: both leave the
    same row behind, but only the former puts the id on the audit row."""
    captured = {}
    monkeypatch.setattr(
        chat_state_mod, "run_query", _capturing_run_query(captured=captured)
    )

    state = _make_state()
    await _send(state, "first prompt")

    rows = _session_rows()
    assert len(rows) == 1
    assert captured["session_id"] == rows[0].session_id
    assert captured["session_id"] == state.active_session_id


@pytest.mark.asyncio
async def test_second_send_reuses_the_session_and_creates_no_second_row(
    temp_db, monkeypatch
):
    """AC 5. Lazy means once per chat, not once per send."""
    captured = {}
    monkeypatch.setattr(
        chat_state_mod, "run_query", _capturing_run_query(captured=captured)
    )

    state = _make_state()
    await _send(state, "first prompt")
    first_id = state.active_session_id

    await _send(state, "second prompt")

    assert count_chat_sessions(_AUTH_USER_ID) == 1
    assert state.active_session_id == first_id
    assert captured["session_id"] == first_id
    assert captured["called"] == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "result",
    [
        QuerySuccessResponse(
            response="ok", audit_id=1, model_used="gpt-4", tokens_used=1
        ),
        QueryBlockedDuplicateResponse(
            reason="Duplicate", first_query_at="2026-09-04T10:00:00Z"
        ),
        QueryBlockedSuspiciousResponse(reason="Suspicious", pattern="ignore previous"),
        QueryBlockedForbiddenResponse(
            reason="Forbidden", required_permission=PERMISSION_QUERY_SUBMIT
        ),
    ],
    ids=["success", "duplicate", "injection", "forbidden"],
)
async def test_run_query_receives_the_active_session_id_on_every_outcome(
    temp_db, monkeypatch, result
):
    """AC 6: "so the audit row carries it on every outcome, including the
    blocked and failed ones from STORY-009." The session is claimed before the
    pipeline runs, so which verdict comes back cannot change whether the record
    names the conversation."""
    captured = {}
    monkeypatch.setattr(
        chat_state_mod, "run_query", _capturing_run_query(result, captured)
    )

    state = _make_state()
    await _send(state, "a prompt")

    assert state.active_session_id != ""
    assert captured["session_id"] == state.active_session_id
    assert state.pending is False


@pytest.mark.asyncio
async def test_history_off_creates_no_session_and_passes_none_to_run_query(
    temp_db, monkeypatch
):
    """AC 7. The flag-off path is reached without this class branching on the
    flag: the service returns None, which is a value to proceed with. Note the
    `is None` -- an empty string would be falsy but would still write "" onto
    every audit row instead of NULL."""
    monkeypatch.setattr(settings, "CHAT_HISTORY_ENABLED", False)
    captured = {}
    monkeypatch.setattr(
        chat_state_mod, "run_query", _capturing_run_query(captured=captured)
    )

    state = _make_state()
    await _send(state, "a prompt")

    assert count_chat_sessions(_AUTH_USER_ID) == 0
    assert state.active_session_id == ""
    assert captured["session_id"] is None
    # "the send otherwise behaves exactly as it does today"
    assert [m.kind for m in state.messages] == ["user", "assistant"]
    assert state.pending is False


def test_chat_state_never_names_the_history_flag():
    """AC 7's structural half. PRD Section 6, verbatim: "No caller branches on
    the flag." tests/test_chat_sessions.py asserts this across every module
    under app/ and chat_ui/; this pins it for the one module this story edits,
    where the temptation is highest."""
    tree = ast.parse(
        pathlib.Path(chat_state_mod.__file__).read_text(encoding="utf-8")
    )
    named = [
        node
        for node in ast.walk(tree)
        if (isinstance(node, ast.Attribute) and node.attr == "CHAT_HISTORY_ENABLED")
        or (isinstance(node, ast.Name) and node.id == "CHAT_HISTORY_ENABLED")
    ]
    assert named == [], "ChatState branches on the flag"


@pytest.mark.asyncio
async def test_a_session_error_while_creating_sets_the_error_and_still_sends(
    temp_db, monkeypatch
):
    """AC 8: "a broken rail does not block the composer". The turn is sent
    unattached rather than refused, and the answer still reaches the screen."""
    def _raise(*args, **kwargs):
        raise ChatSessionError("create failed: store is down")

    monkeypatch.setattr(chat_state_mod.chat_sessions, "create", _raise)
    captured = {}
    monkeypatch.setattr(
        chat_state_mod, "run_query", _capturing_run_query(captured=captured)
    )

    state = _make_state()
    await _send(state, "a prompt")

    assert "store is down" in state.sessions_error
    assert state.active_session_id == ""
    assert captured["session_id"] is None
    assert [m.kind for m in state.messages] == ["user", "assistant"]


@pytest.mark.asyncio
async def test_a_session_error_while_loading_sets_the_error_and_still_signs_in(
    temp_db, monkeypatch
):
    """AC 8's load half. A rail that will not load is not a failed sign-in:
    the credential is good and the composer works without a session list."""
    def _raise(*args, **kwargs):
        raise ChatSessionError("list_for failed: store is down")

    monkeypatch.setattr(chat_state_mod.chat_sessions, "list_for", _raise)

    state = ChatState(_reflex_internal_init=True)
    state.token_input = _AUTH_TOKEN
    await state.login()

    assert state.user_id == _AUTH_USER_ID
    assert state.login_error == ""
    assert state.sessions == []
    assert "store is down" in state.sessions_error


@pytest.mark.asyncio
async def test_pending_clears_when_session_creation_raises(temp_db, monkeypatch):
    """AC 9. PRD-004 Risk 3 -- "a stuck flag locks the composer permanently".
    The lazy create is a new way for the send path to fail, and it sits inside
    the existing try/finally rather than beside it, so the guard still holds."""
    def _raise(*args, **kwargs):
        raise ChatSessionError("create failed: store is down")

    monkeypatch.setattr(chat_state_mod.chat_sessions, "create", _raise)
    monkeypatch.setattr(chat_state_mod, "run_query", _capturing_run_query())

    state = _make_state()
    await _send(state, "a prompt")

    assert state.pending is False

    # And the composer is genuinely usable again, not merely flagged so.
    await _send(state, "another prompt")
    assert len([m for m in state.messages if m.kind == "user"]) == 2


# ---------------------------------------------------------------------------
# Transcript persistence (STORY-014)
# ---------------------------------------------------------------------------


def _stored_messages(session_id: str, user_id: str = _AUTH_USER_ID):
    """The session's rows, read straight from the store rather than through
    app/services/chat_sessions.py -- asserting the service's writes against the
    service would be asserting it against itself, the rule `_session_rows`
    above already states for STORY-013."""
    return list_chat_messages(session_id, user_id)


def _raise_chat_session_error(*args, **kwargs):
    raise ChatSessionError("append_message failed: store is down")


@pytest.mark.asyncio
async def test_a_send_persists_the_user_bubble_and_the_assistant_bubble(
    temp_db, monkeypatch
):
    """AC 1 and AC 2. The second send of a chat is the one that writes both
    bubbles: the first send opens the session *after* the user bubble is
    already on screen, so that bubble has no session to be filed under (see the
    plan's Deviations)."""
    monkeypatch.setattr(chat_state_mod, "run_query", _capturing_run_query())

    state = _make_state()
    await _send(state, "first prompt")
    await _send(state, "second prompt")

    rows = _stored_messages(state.active_session_id)
    assert [r.kind for r in rows] == ["assistant", "user", "assistant"]
    assert [r.id for r in rows] == sorted(r.id for r in rows)

    second_turn = rows[1:]
    assert second_turn[0].content == "second prompt"
    assert second_turn[0].prompt == "second prompt"
    assert second_turn[1].content == "ok"


@pytest.mark.asyncio
async def test_the_bubble_is_appended_before_it_is_written(temp_db, monkeypatch):
    """AC 1's ordering half: "after the append, not before and not instead".

    The only assertion that distinguishes the two orderings -- both leave the
    same row behind, and only this one fails if the write moves ahead of the
    append."""
    monkeypatch.setattr(chat_state_mod, "run_query", _capturing_run_query())
    observed = []
    real_append = chat_sessions.append_message

    def _observing_append(identity, session_id, message):
        # The bubble being written is already the last one on screen.
        observed.append((message.kind, state.messages[-1].kind))
        return real_append(identity, session_id, message)

    monkeypatch.setattr(
        chat_state_mod.chat_sessions, "append_message", _observing_append
    )

    state = _make_state()
    await _send(state, "first prompt")
    await _send(state, "second prompt")

    assert observed, "append_message was never called"
    for written_kind, on_screen_kind in observed:
        assert written_kind == on_screen_kind


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "outcome,expected_kind",
    [
        (
            QuerySuccessResponse(
                response="ok", audit_id=1, model_used="gpt-4", tokens_used=1
            ),
            "assistant",
        ),
        (
            QueryBlockedDuplicateResponse(
                reason="Duplicate", first_query_at="2026-09-04T10:00:00Z"
            ),
            "duplicate",
        ),
        (
            QueryBlockedSuspiciousResponse(
                reason="Suspicious", pattern="ignore previous"
            ),
            "injection",
        ),
        (
            QueryBlockedForbiddenResponse(
                reason="Forbidden", required_permission=PERMISSION_QUERY_SUBMIT
            ),
            "forbidden",
        ),
        (OpenRouterError("upstream timeout"), "upstream_error"),
        (PiiRedactorError("redactor down"), "internal_error"),
    ],
    ids=[
        "assistant",
        "duplicate",
        "injection",
        "forbidden",
        "upstream_error",
        "internal_error",
    ],
)
async def test_every_bubble_kind_is_persisted(
    temp_db, monkeypatch, outcome, expected_kind
):
    """AC 2: all seven kinds, including the four non-success outcomes and the
    two error kinds. `user` is the seventh and rides along on every case.

    Asserted on the stored `kind` rather than on a row count -- a count passes
    even when every row is filed under the wrong verdict."""
    if isinstance(outcome, Exception):

        def _fake(*args, **kwargs):
            raise outcome

    else:
        _fake = _capturing_run_query(outcome)
    monkeypatch.setattr(chat_state_mod, "run_query", _fake)

    state = _make_state()
    await _send(state, "first prompt")
    await _send(state, "second prompt")

    rows = _stored_messages(state.active_session_id)
    assert [r.kind for r in rows[-2:]] == ["user", expected_kind]


@pytest.mark.asyncio
async def test_the_assistant_row_stores_the_redacted_response(temp_db, monkeypatch):
    """AC 3 and PRD Section 9: "The raw upstream text is never written to
    `chat_messages`." Asserted as an absence across every row, not merely as
    the presence of the redacted string in this one."""
    raw = "reach me at juan@empresa.com"
    redacted = "reach me at <EMAIL>"
    monkeypatch.setattr(
        chat_state_mod,
        "run_query",
        _capturing_run_query(
            QuerySuccessResponse(
                response=redacted, audit_id=1, model_used="gpt-4", tokens_used=1
            )
        ),
    )

    state = _make_state()
    await _send(state, "first prompt")
    await _send(state, "second prompt")

    rows = _stored_messages(state.active_session_id)
    assert rows[-1].kind == "assistant"
    assert rows[-1].content == redacted
    assert all(raw not in (r.content or "") for r in rows)


@pytest.mark.asyncio
async def test_a_successful_write_touches_the_session_and_moves_it_to_the_front(
    temp_db, monkeypatch
):
    """AC 4. `updated_at` moves and the in-state rail reorders so the active
    chat is first."""
    monkeypatch.setattr(chat_state_mod, "run_query", _capturing_run_query())

    older = create_chat_session(_AUTH_USER_ID, "Older chat")
    newer = create_chat_session(_AUTH_USER_ID, "Newer chat")
    _backdate_session(older, hours_ago=3)

    state = ChatState(_reflex_internal_init=True)
    state.token_input = _AUTH_TOKEN
    await state.login()
    assert [s.session_id for s in state.sessions] == [newer, older]

    before = {r.session_id: r.updated_at for r in _session_rows()}
    state.active_session_id = older
    await _send(state, "a prompt")

    after = {r.session_id: r.updated_at for r in _session_rows()}
    assert after[older] > before[older]
    assert after[newer] == before[newer]

    assert [s.session_id for s in state.sessions] == [older, newer]
    assert state.sessions[0].title == "Older chat"
    assert state.sessions[0].activity_info
    assert state.sessions_error == ""


@pytest.mark.asyncio
async def test_the_first_send_puts_the_new_chat_at_the_front_of_the_rail(
    temp_db, monkeypatch
):
    """AC 4's insert half. STORY-013's create leaves the new session out of
    `sessions`, so the reorder has to add it -- carrying the *stored* title,
    never one re-derived here (`derive_title` runs exactly once per session).

    The cleared `active_session_id` below is STORY-015's doing and is the whole
    of what changed here. Sign-in now *opens* the most recently active chat
    (STORY-015 AC 1), so a send straight after `login()` continues that chat
    instead of creating one -- which is the story's point, not a regression.
    Starting from an empty active id is what "New chat" will do in STORY-016,
    and it is the only state in which a create still happens, so it is the
    state this assertion has to be made from.
    """
    monkeypatch.setattr(chat_state_mod, "run_query", _capturing_run_query())

    existing = create_chat_session(_AUTH_USER_ID, "Older chat")
    _backdate_session(existing, hours_ago=3)

    state = ChatState(_reflex_internal_init=True)
    state.token_input = _AUTH_TOKEN
    await state.login()
    assert state.active_session_id == existing
    state.active_session_id = ""

    await _send(state, "summarise the Q3 vendor spend")

    assert state.sessions[0].session_id == state.active_session_id
    assert state.sessions[0].title == derive_title("summarise the Q3 vendor spend")
    assert [s.session_id for s in state.sessions[1:]] == [existing]


@pytest.mark.asyncio
async def test_a_failed_append_keeps_the_turn_on_screen_and_reports_it(
    temp_db, monkeypatch
):
    """AC 5 and AC 8, and PRD Risk 5 in one test: "the model answered, the
    audit row is written, and then the transcript insert fails -- a naive
    implementation raises and the user loses a paid, logged answer."""
    monkeypatch.setattr(chat_state_mod, "run_query", _capturing_run_query())
    monkeypatch.setattr(
        chat_state_mod.chat_sessions, "append_message", _raise_chat_session_error
    )

    state = _make_state()
    await _send(state, "a prompt")

    assert [m.kind for m in state.messages] == ["user", "assistant"]
    assert state.messages[-1].content == "ok"
    assert state.transcript_error == TRANSCRIPT_NOT_SAVED_NOTICE
    assert state.pending is False

    # And the composer is genuinely usable again, not merely flagged so.
    await _send(state, "another prompt")
    assert len([m for m in state.messages if m.kind == "user"]) == 2


@pytest.mark.asyncio
async def test_a_storage_error_that_escaped_wrapping_still_does_not_lose_the_turn(
    temp_db, monkeypatch
):
    """AC 5's structural half, and the reason the catch is a bare
    `except Exception`. The story: "A `ChatSessionError`-only catch would let a
    `StorageError` that escaped wrapping take the turn down."

    Patches `append_chat_message` -- the function AC 8 names -- so the service's
    own `_wrapped` arm is exercised end to end rather than bypassed."""
    monkeypatch.setattr(chat_state_mod, "run_query", _capturing_run_query())

    def _raise_storage_error(*args, **kwargs):
        raise StorageError("connection reset")

    monkeypatch.setattr(
        chat_state_mod.chat_sessions.database,
        "append_chat_message",
        _raise_storage_error,
    )

    state = _make_state()
    await _send(state, "a prompt")

    assert [m.kind for m in state.messages] == ["user", "assistant"]
    assert state.transcript_error == TRANSCRIPT_NOT_SAVED_NOTICE
    assert state.pending is False


@pytest.mark.asyncio
async def test_a_failed_touch_does_not_report_a_lost_turn(temp_db, monkeypatch):
    """AC 6: "a failed reorder is cosmetic and must not surface as a lost
    turn." The row *is* in the database, so the transcript notice must stay
    empty -- claiming "not saved" here would be a falsehood in the interface."""
    monkeypatch.setattr(chat_state_mod, "run_query", _capturing_run_query())

    def _raise(*args, **kwargs):
        raise ChatSessionError("touch failed: store is down")

    monkeypatch.setattr(chat_state_mod.chat_sessions, "touch", _raise)

    state = _make_state()
    await _send(state, "first prompt")
    await _send(state, "second prompt")

    rows = _stored_messages(state.active_session_id)
    assert [r.kind for r in rows[-2:]] == ["user", "assistant"]
    assert state.transcript_error == ""
    assert state.sessions_error == SESSION_ORDER_STALE_NOTICE
    assert [m.kind for m in state.messages] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    assert state.pending is False


@pytest.mark.asyncio
async def test_history_off_writes_nothing_and_says_nothing(temp_db, monkeypatch):
    """AC 7: "no write is attempted, no notice appears, and the chat behaves
    exactly as it does today." Reached without this class naming the flag --
    the service returns None and the helper's guard falls through."""
    monkeypatch.setattr(settings, "CHAT_HISTORY_ENABLED", False)
    monkeypatch.setattr(chat_state_mod, "run_query", _capturing_run_query())

    def _refuse(*args, **kwargs):
        raise AssertionError("no transcript write may be attempted")

    monkeypatch.setattr(
        chat_state_mod.chat_sessions.database, "append_chat_message", _refuse
    )

    state = _make_state()
    await _send(state, "a prompt")

    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM chat_messages").fetchone()
    assert row["n"] == 0
    assert state.transcript_error == ""
    assert state.sessions_error == ""
    assert [m.kind for m in state.messages] == ["user", "assistant"]
    assert state.pending is False


@pytest.mark.asyncio
async def test_the_audit_row_survives_a_failed_transcript_write(temp_db, monkeypatch):
    """AC 9: "the two writes are independent and the evidence one already
    happened inside `run_query`." The real pipeline runs here -- a faked
    run_query would write no audit row and the test would prove nothing."""

    def _fake_call_openrouter(prompt, model="gpt-4", api_key=None):
        return OpenRouterResult(response="Hi there!", model_used=model, tokens_used=12)

    monkeypatch.setattr(chat_state_mod, "call_openrouter", _fake_call_openrouter)
    monkeypatch.setattr(
        chat_state_mod.chat_sessions, "append_message", _raise_chat_session_error
    )

    state = _make_state()
    await _send(state, "hello world")

    assert _count_audit_rows() == 1
    audit_row = get_audit_log(_last_audit_id())
    assert audit_row.session_id == state.active_session_id
    assert state.messages[-1].kind == "assistant"
    assert state.transcript_error == TRANSCRIPT_NOT_SAVED_NOTICE


def test_every_bubble_append_in_do_send_goes_through_the_helper():
    """The structural half of the story's "a ninth outcome added later cannot
    be persisted-by-forgetting".

    `_do_send` must contain no `self.messages.append(...)` of its own: every
    bubble is the helper's, so a branch added later persists by default rather
    than by remembering. The AST walk is the shape
    `test_chat_state_never_names_the_history_flag` above already uses -- the
    drift fails a test rather than a review.
    """
    tree = ast.parse(pathlib.Path(chat_state_mod.__file__).read_text(encoding="utf-8"))
    do_send = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "_do_send"
    )
    appends = [
        node
        for node in ast.walk(do_send)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "append"
        and isinstance(node.func.value, ast.Attribute)
        and node.func.value.attr == "messages"
    ]
    assert appends == [], "_do_send appends a bubble without persisting it"

    helper_calls = [
        node
        for node in ast.walk(do_send)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "_append_and_persist"
    ]
    # The eight append sites the story enumerates, collapsed to six calls: the
    # four isinstance branches already share one.
    assert len(helper_calls) == 6


# ---------------------------------------------------------------------------
# Transcript restore (STORY-015)
# ---------------------------------------------------------------------------


async def _select(state: ChatState, session_id: str) -> None:
    handler = type(state).event_handlers["select_session"]
    await handler.fn(state, session_id)


async def _restore(session_id: str) -> ChatState:
    """A fresh signed-in state showing `session_id` -- the reload, modelled."""
    state = _make_state()
    await _select(state, session_id)
    return state


# Every ChatMessage field a bubble renderer reads, minus the two duplicate
# fields, which the recompute test owns because they are derived rather than
# restored.
_ROUND_TRIP_FIELDS = (
    "kind",
    "content",
    "prompt",
    "model_used",
    "tokens_used",
    "audit_id",
    "pii_redacted",
    "pii_entities",
    "pattern",
    "required_permission",
    "first_query_at",
    "detail",
)


def _fields(bubble: ChatMessage) -> dict:
    return {name: getattr(bubble, name) for name in _ROUND_TRIP_FIELDS}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "outcome,expected_kind",
    [
        (
            QuerySuccessResponse(
                response="ok", audit_id=7, model_used="gpt-4", tokens_used=42
            ),
            "assistant",
        ),
        (
            QueryBlockedDuplicateResponse(
                reason="Duplicate", first_query_at="2026-09-04T10:00:00Z"
            ),
            "duplicate",
        ),
        (
            QueryBlockedSuspiciousResponse(
                reason="Suspicious", pattern="ignore previous"
            ),
            "injection",
        ),
        (
            QueryBlockedForbiddenResponse(
                reason="Forbidden", required_permission=PERMISSION_QUERY_SUBMIT
            ),
            "forbidden",
        ),
        (OpenRouterError("upstream timeout"), "upstream_error"),
        (PiiRedactorError("redactor down"), "internal_error"),
    ],
    ids=[
        "assistant",
        "duplicate",
        "injection",
        "forbidden",
        "upstream_error",
        "internal_error",
    ],
)
async def test_every_bubble_kind_survives_the_round_trip(
    temp_db, monkeypatch, outcome, expected_kind
):
    """AC 4 and AC 11: a store/restore round trip asserted **per kind**, not
    once for a representative kind.

    `user` is the seventh kind and rides along in every case, exactly as it
    does in `test_every_bubble_kind_is_persisted` on the write side.

    Two sends, not one: the first send appends the user bubble *before* the
    lazy create, deliberately, so that bubble has no session to be filed
    under. A restored first turn therefore starts at its outcome bubble --
    inherited from STORY-014 and recorded in the plan's Deviations. The live
    transcript's `[1:]` is what the store was ever given.
    """
    if isinstance(outcome, Exception):

        def _fake(*args, **kwargs):
            raise outcome

    else:
        _fake = _capturing_run_query(outcome)
    monkeypatch.setattr(chat_state_mod, "run_query", _fake)

    state = _make_state()
    await _send(state, "first prompt")
    await _send(state, "second prompt")

    live = state.messages[1:]
    assert [m.kind for m in live] == [expected_kind, "user", expected_kind]

    restored = (await _restore(state.active_session_id)).messages

    assert [m.kind for m in restored] == [expected_kind, "user", expected_kind]
    assert [_fields(m) for m in restored] == [_fields(m) for m in live]
    # The seventh kind, asserted rather than assumed to have ridden along.
    assert any(m.kind == "user" for m in restored)

    # The two derived fields, which `_fields` excludes because they are
    # recomputed rather than restored. Only a duplicate may carry them:
    # `format_duplicate_info` returns DUPLICATE_FALLBACK_TEXT rather than ""
    # for an empty timestamp, so a rehydration that called it for every kind
    # would put duplicate copy on a user bubble. Invisible on screen today --
    # only `render_duplicate` reads these -- and a divergence from the live
    # path that no other assertion here would catch.
    for bubble in restored:
        if bubble.kind == "duplicate":
            assert bubble.duplicate_relative_info
        else:
            assert bubble.duplicate_relative_info == ""
            assert bubble.duplicate_release_info == ""


@pytest.mark.asyncio
async def test_the_restored_transcript_is_in_id_order(temp_db, monkeypatch):
    """AC 2: "in `id ASC` order". The write side pins this shape in
    `test_a_send_persists_the_user_bubble_and_the_assistant_bubble`; this is
    the same shape read back, one send longer."""
    monkeypatch.setattr(chat_state_mod, "run_query", _capturing_run_query())

    state = _make_state()
    await _send(state, "one")
    await _send(state, "two")
    await _send(state, "three")

    restored = (await _restore(state.active_session_id)).messages

    assert [m.kind for m in restored] == [
        "assistant",
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    assert [m.content for m in restored if m.kind == "user"] == ["two", "three"]


@pytest.mark.asyncio
async def test_a_restored_duplicate_recomputes_its_relative_copy(temp_db, monkeypatch):
    """AC 5. The humanized copy is recomputed from the stored `first_query_at`
    through `format_duplicate_info`, never read from storage -- so "already
    sent 2m ago" reads correctly hours later."""
    two_hours = (datetime.now(timezone.utc) - timedelta(hours=2)).strftime(
        _TIMESTAMP_FORMAT
    )
    monkeypatch.setattr(
        chat_state_mod,
        "run_query",
        _capturing_run_query(
            QueryBlockedDuplicateResponse(reason="Duplicate", first_query_at=two_hours)
        ),
    )

    state = _make_state()
    await _send(state, "first prompt")
    await _send(state, "second prompt")

    restored = [
        m
        for m in (await _restore(state.active_session_id)).messages
        if m.kind == "duplicate"
    ]
    assert restored

    expected_relative, expected_release = format_duplicate_info(two_hours)
    for bubble in restored:
        assert bubble.duplicate_relative_info == expected_relative
        assert bubble.duplicate_release_info == expected_release
        assert bubble.duplicate_relative_info

    # The structural half: there is no column to have read it from. Neither
    # field exists on the stored row, which is what forces the recompute.
    stored_field_names = {f.name for f in dataclasses.fields(StoredMessage)}
    assert "duplicate_relative_info" not in stored_field_names
    assert "duplicate_release_info" not in stored_field_names

    # Two different stored timestamps must restore to two different strings --
    # a stored constant would give the same one twice.
    twenty_hours = (datetime.now(timezone.utc) - timedelta(hours=20)).strftime(
        _TIMESTAMP_FORMAT
    )
    assert format_duplicate_info(twenty_hours)[0] != expected_relative


@pytest.mark.asyncio
async def test_a_restored_assistant_keeps_its_footer_and_pii_badge(
    temp_db, monkeypatch
):
    """AC 6: the same model_used, tokens_used and #audit_id, and the same
    entity list in the PII badge."""
    monkeypatch.setattr(
        chat_state_mod,
        "run_query",
        _capturing_run_query(
            QuerySuccessResponse(
                response="redacted answer",
                audit_id=99,
                model_used="gpt-4",
                tokens_used=123,
                pii_redacted=True,
                pii_entities_masked=["EMAIL", "PHONE"],
            )
        ),
    )

    state = _make_state()
    await _send(state, "first prompt")
    await _send(state, "second prompt")

    restored = [
        m
        for m in (await _restore(state.active_session_id)).messages
        if m.kind == "assistant"
    ]
    assert restored

    for bubble in restored:
        assert bubble.content == "redacted answer"
        assert bubble.model_used == "gpt-4"
        assert bubble.tokens_used == 123
        assert bubble.audit_id == 99
        assert bubble.pii_redacted is True
        # A real list, because render_assistant calls .length() and .join(", ")
        # on it.
        assert bubble.pii_entities == ["EMAIL", "PHONE"]


@pytest.mark.asyncio
async def test_a_message_with_no_pii_entities_restores_to_an_empty_list(
    temp_db, monkeypatch
):
    """The phantom entity the column's own docstring predicted for this story
    by name: `"".split(",")` is `[""]`, one entity on a message that had
    none."""
    monkeypatch.setattr(chat_state_mod, "run_query", _capturing_run_query())

    state = _make_state()
    await _send(state, "first prompt")
    await _send(state, "second prompt")

    restored = (await _restore(state.active_session_id)).messages
    assert restored
    for bubble in restored:
        assert bubble.pii_entities == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "outcome,expected_kind",
    [
        (
            QueryBlockedDuplicateResponse(
                reason="Duplicate", first_query_at="2026-09-04T10:00:00Z"
            ),
            "duplicate",
        ),
        (
            QueryBlockedSuspiciousResponse(reason="Suspicious", pattern="ignore"),
            "injection",
        ),
        (OpenRouterError("upstream timeout"), "upstream_error"),
        (PiiRedactorError("redactor down"), "internal_error"),
    ],
    ids=["duplicate", "injection", "upstream_error", "internal_error"],
)
async def test_a_restored_bubble_keeps_the_prompt_its_actions_consume(
    temp_db, monkeypatch, outcome, expected_kind
):
    """AC 7: Retry and Edit and resend work on a restored bubble, because
    `prompt` survived the round trip -- it is what
    `ChatState.edit_and_resend(message.prompt)` and
    `ChatState.retry_message(message.prompt)` are handed."""
    if isinstance(outcome, Exception):

        def _fake(*args, **kwargs):
            raise outcome

    else:
        _fake = _capturing_run_query(outcome)
    monkeypatch.setattr(chat_state_mod, "run_query", _fake)

    state = _make_state()
    await _send(state, "first prompt")
    await _send(state, "second prompt")

    restored_state = await _restore(state.active_session_id)
    bubbles = [m for m in restored_state.messages if m.kind == expected_kind]
    assert bubbles
    assert bubbles[-1].prompt == "second prompt"

    # The action actually consumes it: the composer refills.
    restored_state.edit_and_resend(bubbles[-1].prompt)
    assert restored_state.input_text == "second prompt"


@pytest.mark.asyncio
async def test_login_opens_the_most_recently_active_chat(temp_db, monkeypatch):
    """AC 1: "the most recently active session becomes active and its
    transcript is rendered"."""
    monkeypatch.setattr(chat_state_mod, "run_query", _capturing_run_query())

    older_state = _make_state()
    await _send(older_state, "older one")
    await _send(older_state, "older two")
    older = older_state.active_session_id

    newer_state = _make_state()
    await _send(newer_state, "newer one")
    await _send(newer_state, "newer two")
    newer = newer_state.active_session_id

    assert older != newer
    # Backdate rather than rely on a touch: both rows can land in the same
    # second on a TEXT timestamp, and that tie breaks arbitrarily.
    _backdate_session(older, hours_ago=3)

    state = ChatState(_reflex_internal_init=True)
    state.token_input = _AUTH_TOKEN
    await state.login()

    assert state.active_session_id == newer
    assert state.sessions_error == ""
    assert [m.content for m in state.messages if m.kind == "user"] == ["newer two"]
    assert [m.kind for m in state.messages] == ["assistant", "user", "assistant"]


@pytest.mark.asyncio
async def test_login_with_no_sessions_leaves_the_chat_empty(temp_db, monkeypatch):
    """The other half of AC 1: a user with nothing stored opens on an empty
    chat, and no read is attempted for a session that does not exist."""
    monkeypatch.setattr(chat_state_mod.chat_sessions, "messages_for", _fail_if_called)

    state = ChatState(_reflex_internal_init=True)
    state.token_input = _AUTH_TOKEN
    await state.login()

    assert state.sessions == []
    assert state.active_session_id == ""
    assert state.messages == []
    assert state.sessions_error == ""


@pytest.mark.asyncio
async def test_a_switch_replaces_the_transcript_and_moves_the_active_id(
    temp_db, monkeypatch
):
    """AC 2: `self.messages` is replaced by that session's stored messages and
    `active_session_id` moves."""
    monkeypatch.setattr(chat_state_mod, "run_query", _capturing_run_query())

    first = _make_state()
    await _send(first, "alpha one")
    await _send(first, "alpha two")
    alpha = first.active_session_id

    second = _make_state()
    await _send(second, "beta one")
    await _send(second, "beta two")
    beta = second.active_session_id

    assert alpha != beta
    # `second` is showing beta; switch it to alpha.
    await _select(second, alpha)

    assert second.active_session_id == alpha
    assert [m.content for m in second.messages if m.kind == "user"] == ["alpha two"]
    assert all("beta" not in m.content for m in second.messages)
    assert second.sessions_error == ""


@pytest.mark.asyncio
async def test_a_switch_touches_nothing_else(temp_db, monkeypatch):
    """AC 3: "the model selector and the signed-in user are untouched"."""
    monkeypatch.setattr(chat_state_mod, "run_query", _capturing_run_query())

    other = _make_state()
    await _send(other, "one")
    await _send(other, "two")
    target = other.active_session_id

    state = _make_state()
    state.selected_model = "anthropic/claude-3"
    before = (state.selected_model, state.user_id, state._token)

    await _select(state, target)

    assert (state.selected_model, state.user_id, state._token) == before
    assert state.messages


@pytest.mark.asyncio
async def test_a_switch_is_refused_while_pending(temp_db, monkeypatch):
    """AC 8: swapping the transcript out from under an in-flight send would
    append the answer to the wrong conversation, so the switch is refused --
    the guard `edit_and_resend` already applies."""
    monkeypatch.setattr(chat_state_mod, "run_query", _capturing_run_query())

    other = _make_state()
    await _send(other, "one")
    await _send(other, "two")
    target = other.active_session_id

    state = _make_state()
    state.active_session_id = "a-different-session"
    state.messages = [ChatMessage(kind="user", content="in flight")]
    state.pending = True

    await _select(state, target)

    assert state.active_session_id == "a-different-session"
    assert [m.content for m in state.messages] == ["in flight"]


@pytest.mark.asyncio
async def test_a_failed_read_keeps_the_transcript_and_reports_it(temp_db, monkeypatch):
    """AC 9: `sessions_error` is set, `self.messages` is left as it was, and
    the composer stays usable."""
    state = _make_state()
    state.active_session_id = "still-this-one"
    state.messages = [ChatMessage(kind="user", content="still here")]

    monkeypatch.setattr(
        chat_state_mod.chat_sessions, "messages_for", _raise_chat_session_error
    )
    await _select(state, "some-other-session")

    assert state.sessions_error == TRANSCRIPT_NOT_LOADED_NOTICE
    assert [m.content for m in state.messages] == ["still here"]
    # The active id stands too: marking a chat whose transcript is not on
    # screen would point the rail at a conversation the reader cannot see.
    assert state.active_session_id == "still-this-one"
    # The composer stays usable.
    assert state.pending is False


@pytest.mark.asyncio
async def test_a_storage_error_that_escaped_wrapping_still_keeps_the_transcript(
    temp_db, monkeypatch
):
    """The bare-`Exception` half of AC 9. A ChatSessionError-only catch would
    let a raw StorageError empty the screen -- the escape STORY-014's own
    storage-error test exists for, on the read side."""

    def _raise_storage_error(*args, **kwargs):
        raise StorageError("stream disconnected")

    monkeypatch.setattr(
        chat_state_mod.chat_sessions.database,
        "list_chat_messages",
        _raise_storage_error,
    )

    state = _make_state()
    state.messages = [ChatMessage(kind="user", content="still here")]
    await _select(state, "any-session")

    assert state.sessions_error == TRANSCRIPT_NOT_LOADED_NOTICE
    assert [m.content for m in state.messages] == ["still here"]


@pytest.mark.asyncio
async def test_a_foreign_session_id_restores_empty_rather_than_erroring(temp_db):
    """The story's Technical Note: "A foreign or unknown `session_id` yields an
    empty list, not an error -- the caller cannot distinguish the two, and the
    UI treats both as 'nothing here'."

    PRD-008 Risk 3: `active_session_id` is client-visible, so this is the case
    where the server re-checks ownership against the freshly resolved Identity
    rather than against the var.
    """
    insert_user(
        User(
            user_id="otro@empresa.com",
            role="user",
            token_hash=hash_token("otro-token"),
        )
    )
    theirs = create_chat_session("otro@empresa.com", "Their chat")

    state = _make_state()
    await _select(state, theirs)

    assert state.messages == []
    assert state.sessions_error == ""


@pytest.mark.asyncio
async def test_history_off_reads_nothing_on_login(temp_db, monkeypatch):
    """AC 10: with the flag off, no read is attempted and the chat opens
    empty, exactly as today."""
    create_chat_session(_AUTH_USER_ID, "A chat")
    monkeypatch.setattr(settings, "CHAT_HISTORY_ENABLED", False)
    monkeypatch.setattr(chat_state_mod.chat_sessions, "messages_for", _fail_if_called)

    state = ChatState(_reflex_internal_init=True)
    state.token_input = _AUTH_TOKEN
    await state.login()

    assert state.messages == []
    assert state.sessions == []
    assert state.active_session_id == ""
    assert state.sessions_error == ""


def test_the_rehydration_reads_every_stored_field():
    """The read-side counterpart of
    `test_every_bubble_append_in_do_send_goes_through_the_helper`.

    A column added to `chat_messages` later is written by `_to_stored_message`
    and would be silently dropped by `_to_chat_message` with no test failing --
    transcripts quietly losing a field. The AST walk makes that drift fail a
    test rather than a review.

    `session_id`, `created_at` and `id` are excluded: `ChatMessage` has no
    field for any of them, and `id` is the ordering the store already applied.
    """
    tree = ast.parse(pathlib.Path(chat_state_mod.__file__).read_text(encoding="utf-8"))
    fn = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_to_chat_message"
    )
    read = {
        node.attr
        for node in ast.walk(fn)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "row"
    }

    expected = {f.name for f in dataclasses.fields(StoredMessage)} - {
        "session_id",
        "created_at",
        "id",
    }

    assert expected <= read, f"_to_chat_message drops {sorted(expected - read)}"


# ---------------------------------------------------------------------------
# New chat, rename, delete, logout (STORY-016)
# ---------------------------------------------------------------------------


def _new_chat(state: ChatState) -> None:
    handler = type(state).event_handlers["new_chat"]
    handler.fn(state)


async def _rename(state: ChatState, session_id: str, title: str) -> None:
    handler = type(state).event_handlers["rename_session"]
    await handler.fn(state, session_id, title)


async def _delete(state: ChatState, session_id: str) -> None:
    handler = type(state).event_handlers["delete_session"]
    await handler.fn(state, session_id)


def _title_of(session_id: str, user_id: str = _AUTH_USER_ID) -> str:
    row = next(r for r in _session_rows(user_id) if r.session_id == session_id)
    return row.title


def _updated_at_of(session_id: str, user_id: str = _AUTH_USER_ID) -> str:
    row = next(r for r in _session_rows(user_id) if r.session_id == session_id)
    return row.updated_at


_OTHER_USER_ID = "otra@empresa.com"
_OTHER_TOKEN = "other-user-token"


def _seed_other_user_session(title: str = "Not yours") -> str:
    """A second identity with one session -- the foreign row AC 10 is about."""
    insert_user(
        User(user_id=_OTHER_USER_ID, role="user", token_hash=hash_token(_OTHER_TOKEN))
    )
    return create_chat_session(_OTHER_USER_ID, title)


@pytest.mark.asyncio
async def test_new_chat_clears_the_active_id_and_the_transcript_and_writes_nothing(
    temp_db, monkeypatch
):
    """AC 1: `active_session_id` and `messages` are cleared and no row is
    written."""
    monkeypatch.setattr(chat_state_mod, "run_query", _capturing_run_query())

    state = _make_state()
    await _send(state, "first subject")
    assert state.active_session_id
    assert state.messages
    before = count_chat_sessions(_AUTH_USER_ID)

    _new_chat(state)

    assert state.active_session_id == ""
    assert state.messages == []
    assert count_chat_sessions(_AUTH_USER_ID) == before == 1


def test_new_chat_twice_with_no_send_leaves_no_session(temp_db):
    """AC 2: the lazy rule, stated as the absence it is. Two clicks and an
    empty table -- an opened-and-abandoned tab leaves nothing behind."""
    state = _make_state()

    _new_chat(state)
    _new_chat(state)

    assert count_chat_sessions(_AUTH_USER_ID) == 0
    assert _session_rows() == []
    assert state.active_session_id == ""


@pytest.mark.asyncio
async def test_new_chat_then_a_send_creates_exactly_one_session(temp_db, monkeypatch):
    """AC 1's second half: "the next send creates the session". The first chat
    stays in the rail; the new one joins it."""
    monkeypatch.setattr(chat_state_mod, "run_query", _capturing_run_query())

    state = _make_state()
    await _send(state, "first subject")
    first = state.active_session_id

    _new_chat(state)
    await _send(state, "second subject")
    second = state.active_session_id

    assert second and second != first
    assert count_chat_sessions(_AUTH_USER_ID) == 2
    assert {s.session_id for s in state.sessions} == {first, second}
    # The new chat is the most recently active, so it leads the rail.
    assert state.sessions[0].session_id == second


@pytest.mark.asyncio
async def test_rename_persists_and_updates_the_rail_without_moving_the_row(
    temp_db, monkeypatch
):
    """AC 3: the title persists, the rail updates, and `updated_at` is not
    touched -- so the row does not move under the user's cursor."""
    monkeypatch.setattr(chat_state_mod, "run_query", _capturing_run_query())

    older_state = _make_state()
    await _send(older_state, "older subject")
    older = older_state.active_session_id

    state = _make_state()
    await _send(state, "newer subject")
    newer = state.active_session_id
    _backdate_session(older, hours_ago=3)

    # Both chats in one rail, newest first, so a reorder would be visible.
    state.sessions = [
        ChatSessionSummary(
            session_id=newer, title=_title_of(newer), activity_info="just now"
        ),
        ChatSessionSummary(
            session_id=older, title=_title_of(older), activity_info="3h ago"
        ),
    ]
    order_before = [s.session_id for s in state.sessions]
    activity_before = [s.activity_info for s in state.sessions]
    updated_before = _updated_at_of(older)
    newer_title = _title_of(newer)

    await _rename(state, older, "Vendor contract review")

    # Persisted.
    assert _title_of(older) == "Vendor contract review"
    # The rail updated, at the same index, keeping its activity string.
    assert [s.session_id for s in state.sessions] == order_before
    assert [s.activity_info for s in state.sessions] == activity_before
    assert state.sessions[1].title == "Vendor contract review"
    assert state.sessions[0].title == newer_title
    # A rename is not activity: the timestamp is byte-identical.
    assert _updated_at_of(older) == updated_before
    assert state.sessions_error == ""


@pytest.mark.asyncio
@pytest.mark.parametrize("blank", ["", "   ", "\t\n "])
async def test_a_blank_rename_is_refused_and_the_existing_title_stands(
    temp_db, monkeypatch, blank
):
    """AC 4. Refused silently: the refusal is of the input, not of the system,
    and the title standing is the whole feedback."""
    monkeypatch.setattr(chat_state_mod, "run_query", _capturing_run_query())

    state = _make_state()
    await _send(state, "keep this title")
    session_id = state.active_session_id
    title_before = _title_of(session_id)
    rail_before = [(s.session_id, s.title) for s in state.sessions]

    await _rename(state, session_id, blank)

    assert _title_of(session_id) == title_before
    assert [(s.session_id, s.title) for s in state.sessions] == rail_before
    # No notice: the rail's list is not what went wrong.
    assert state.sessions_error == ""


@pytest.mark.asyncio
async def test_a_rename_survives_the_next_send_and_is_never_re_derived(
    temp_db, monkeypatch
):
    """Technical Notes: "a rename that re-derives on the next send would
    silently undo the user's edit". derive_title runs once, at creation."""
    monkeypatch.setattr(chat_state_mod, "run_query", _capturing_run_query())

    state = _make_state()
    await _send(state, "summarise the Q3 vendor spend")
    session_id = state.active_session_id
    assert _title_of(session_id) == derive_title("summarise the Q3 vendor spend")

    await _rename(state, session_id, "Vendor contract review")
    await _send(state, "and the Q4 figures too")

    assert _title_of(session_id) == "Vendor contract review"
    assert _title_of(session_id) != derive_title("and the Q4 figures too")
    # The rail carries the stored title, not a re-derived one.
    assert state.sessions[0].title == "Vendor contract review"


@pytest.mark.asyncio
async def test_a_rename_is_stored_stripped(temp_db, monkeypatch):
    """The other half of AC 4's whitespace rule: a title that is not blank but
    is padded is one rename, not two different ones."""
    monkeypatch.setattr(chat_state_mod, "run_query", _capturing_run_query())

    state = _make_state()
    await _send(state, "anything")
    session_id = state.active_session_id

    await _rename(state, session_id, "  Payroll question  ")

    assert _title_of(session_id) == "Payroll question"
    assert state.sessions[0].title == "Payroll question"


@pytest.mark.asyncio
async def test_delete_removes_the_session_and_its_messages_and_no_audit_row(
    temp_db, monkeypatch
):
    """AC 5: the session and its messages are removed, the rail drops the row,
    and the audit trail is untouched across the delete."""
    monkeypatch.setattr(chat_state_mod, "run_query", _capturing_run_query())

    state = _make_state()
    await _send(state, "delete me")
    await _send(state, "and this turn too")
    session_id = state.active_session_id

    # run_query is patched out, so the pipeline wrote no audit row -- and an
    # unchanged count of zero would assert nothing. Seed the rows this
    # conversation would really have produced, carrying its session_id, so the
    # assertion below is about evidence that actually exists and is actually
    # joined to the chat being deleted.
    for prompt in ("delete me", "and this turn too"):
        insert_audit_log(
            AuditLog(
                timestamp=datetime.now(timezone.utc).strftime(_TIMESTAMP_FORMAT),
                user_id=_AUTH_USER_ID,
                prompt_hash=hash_prompt(prompt),
                session_id=session_id,
            )
        )

    assert _stored_messages(session_id)
    audit_before = _count_audit_rows()
    assert audit_before == 2

    await _delete(state, session_id)

    assert count_chat_sessions(_AUTH_USER_ID) == 0
    assert _stored_messages(session_id) == []
    assert [s.session_id for s in state.sessions] == []
    # PRD Section 9: deleting a conversation deletes a conversation. It does
    # not edit the record of what was asked. The orphaned session_id on those
    # rows is expected -- "it is what preserves the evidence when a user tidies
    # their list".
    assert _count_audit_rows() == audit_before
    with get_connection() as conn:
        orphaned = conn.execute(
            "SELECT COUNT(*) AS n FROM audit_logs WHERE session_id = ?",
            (session_id,),
        ).fetchone()["n"]
    assert orphaned == 2


@pytest.mark.asyncio
async def test_deleting_the_active_session_lands_on_the_next_most_recent(
    temp_db, monkeypatch
):
    """AC 6: the UI lands on the next most recent session."""
    monkeypatch.setattr(chat_state_mod, "run_query", _capturing_run_query())

    older_state = _make_state()
    await _send(older_state, "older one")
    await _send(older_state, "older two")
    older = older_state.active_session_id

    state = _make_state()
    await _send(state, "newer one")
    await _send(state, "newer two")
    newer = state.active_session_id
    _backdate_session(older, hours_ago=3)

    # The rail as login() would build it: newest activity first.
    state.sessions = [
        ChatSessionSummary(session_id=newer, title="newer", activity_info="just now"),
        ChatSessionSummary(session_id=older, title="older", activity_info="3h ago"),
    ]

    await _delete(state, newer)

    assert state.active_session_id == older
    assert [s.session_id for s in state.sessions] == [older]
    assert [m.content for m in state.messages if m.kind == "user"] == ["older two"]
    assert all("newer" not in m.content for m in state.messages)
    assert state.sessions_error == ""


@pytest.mark.asyncio
async def test_deleting_the_last_session_lands_on_the_empty_state(
    temp_db, monkeypatch
):
    """AC 6's other arm: "or on the empty state if none remains"."""
    monkeypatch.setattr(chat_state_mod, "run_query", _capturing_run_query())

    state = _make_state()
    await _send(state, "the only chat")
    session_id = state.active_session_id
    assert state.messages

    await _delete(state, session_id)

    assert state.active_session_id == ""
    assert state.messages == []
    assert state.sessions == []
    assert state.sessions_error == ""


@pytest.mark.asyncio
async def test_deleting_a_non_active_session_leaves_the_transcript_alone(
    temp_db, monkeypatch
):
    """AC 6 read the other way: a chat the reader is not looking at changes
    the rail and nothing else."""
    monkeypatch.setattr(chat_state_mod, "run_query", _capturing_run_query())

    other_state = _make_state()
    await _send(other_state, "the doomed chat")
    doomed = other_state.active_session_id

    state = _make_state()
    await _send(state, "the chat on screen")
    active = state.active_session_id
    state.sessions = [
        ChatSessionSummary(session_id=active, title="on screen", activity_info="now"),
        ChatSessionSummary(session_id=doomed, title="doomed", activity_info="now"),
    ]
    messages_before = list(state.messages)

    await _delete(state, doomed)

    assert state.active_session_id == active
    assert state.messages == messages_before
    assert [s.session_id for s in state.sessions] == [active]
    assert count_chat_sessions(_AUTH_USER_ID) == 1


@pytest.mark.asyncio
async def test_a_failed_read_after_a_delete_never_lands_on_the_deleted_transcript(
    temp_db, monkeypatch
):
    """AC 6's absolute: "never on a transcript belonging to a deleted id".

    The one place in the class where a failed read empties the screen, and the
    deliberate divergence from select_session -- whose transcript is still a
    real conversation when its read fails, and whose is not here.
    """
    monkeypatch.setattr(chat_state_mod, "run_query", _capturing_run_query())

    older_state = _make_state()
    await _send(older_state, "older one")
    older = older_state.active_session_id

    state = _make_state()
    await _send(state, "doomed one")
    await _send(state, "doomed two")
    doomed = state.active_session_id
    _backdate_session(older, hours_ago=3)
    state.sessions = [
        ChatSessionSummary(session_id=doomed, title="doomed", activity_info="now"),
        ChatSessionSummary(session_id=older, title="older", activity_info="3h ago"),
    ]

    def _raise_on_read(*args, **kwargs):
        raise ChatSessionError("messages_for failed: store is down")

    monkeypatch.setattr(chat_state_mod.chat_sessions, "messages_for", _raise_on_read)

    await _delete(state, doomed)

    assert state.messages == []
    assert state.active_session_id == older
    assert state.sessions_error == TRANSCRIPT_NOT_LOADED_NOTICE


@pytest.mark.asyncio
async def test_logout_clears_every_session_var_and_every_row_survives(
    temp_db, monkeypatch
):
    """AC 8, and the story's central distinction: logout() clears state,
    delete_session() deletes rows."""
    monkeypatch.setattr(chat_state_mod, "run_query", _capturing_run_query())

    state = _make_state()
    await _send(state, "first chat")
    first = state.active_session_id
    _new_chat(state)
    await _send(state, "second chat")
    second = state.active_session_id
    state.sessions_error = "something stale"

    sessions_before = count_chat_sessions(_AUTH_USER_ID)
    messages_before = len(_stored_messages(first)) + len(_stored_messages(second))
    assert sessions_before == 2
    assert messages_before > 0

    state.logout()

    assert state.sessions == []
    assert state.active_session_id == ""
    assert state.messages == []
    assert state.sessions_error == ""
    assert state.transcript_error == ""
    assert state._token == ""
    assert state.user_id == ""

    # Every row survives. This is the assertion the story asks for by name.
    assert count_chat_sessions(_AUTH_USER_ID) == sessions_before
    assert (
        len(_stored_messages(first)) + len(_stored_messages(second)) == messages_before
    )


@pytest.mark.asyncio
async def test_signing_back_in_lists_the_sessions_again(temp_db, monkeypatch):
    """AC 9: the rows survived, so the rail comes back."""
    monkeypatch.setattr(chat_state_mod, "run_query", _capturing_run_query())

    state = _make_state()
    await _send(state, "first chat")
    first = state.active_session_id
    _new_chat(state)
    await _send(state, "second chat")
    second = state.active_session_id

    # Backdate rather than rely on creation order: both rows can land in the
    # same second on a TEXT timestamp, and that tie breaks arbitrarily -- the
    # reason test_login_opens_the_most_recently_active_chat does the same.
    _backdate_session(first, hours_ago=3)

    state.logout()
    assert state.sessions == []

    fresh = ChatState(_reflex_internal_init=True)
    fresh.token_input = _AUTH_TOKEN
    await fresh.login()

    assert {s.session_id for s in fresh.sessions} == {first, second}
    assert fresh.active_session_id == second


@pytest.mark.asyncio
@pytest.mark.parametrize("handler", ["rename_session", "delete_session"])
async def test_a_foreign_session_id_changes_nothing(temp_db, monkeypatch, handler):
    """AC 10, and PRD Risk 3: `session_id` is client-visible and names a row.

    Neither handler validates it and neither should -- the service scopes the
    WHERE on the freshly resolved Identity and returns False for a foreign id,
    an unknown id and history-off alike.
    """
    monkeypatch.setattr(chat_state_mod, "run_query", _capturing_run_query())

    foreign = _seed_other_user_session("Not yours")
    foreign_title_before = _title_of(foreign, _OTHER_USER_ID)

    state = _make_state()
    await _send(state, "my own chat")
    mine = state.active_session_id
    rail_before = [(s.session_id, s.title) for s in state.sessions]
    messages_before = list(state.messages)

    if handler == "rename_session":
        await _rename(state, foreign, "Mine now")
    else:
        await _delete(state, foreign)

    # The foreign row is untouched, in both directions.
    assert count_chat_sessions(_OTHER_USER_ID) == 1
    assert _title_of(foreign, _OTHER_USER_ID) == foreign_title_before
    # And nothing of the caller's moved either.
    assert [(s.session_id, s.title) for s in state.sessions] == rail_before
    assert state.messages == messages_before
    assert state.active_session_id == mine
    assert count_chat_sessions(_AUTH_USER_ID) == 1


def test_logout_calls_no_service_and_can_write_nothing():
    """The structural half of "logout() clears state, delete_session() deletes
    rows".

    A comment saying "this must not delete" is exactly the artifact that
    survives the edit that makes it false. The AST walk is the shape
    test_chat_state_never_names_the_history_flag and the _do_send append guard
    already use in this file: the drift fails a test rather than a review. A
    logout that reached for chat_sessions.delete to "tidy up" the list would
    destroy a user's history on every sign-out of a shared machine.
    """
    tree = ast.parse(pathlib.Path(chat_state_mod.__file__).read_text(encoding="utf-8"))
    logout = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "logout"
    )

    # Synchronous by declaration: it is not an AsyncFunctionDef, so there is no
    # await to hang a service call on without changing the signature.
    assert not isinstance(logout, ast.AsyncFunctionDef)
    assert not [n for n in ast.walk(logout) if isinstance(n, ast.Await)]

    called = {
        node.func.attr
        for node in ast.walk(logout)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert called == set(), f"logout calls {sorted(called)}"

    names = {node.id for node in ast.walk(logout) if isinstance(node, ast.Name)}
    assert "chat_sessions" not in names
    assert "asyncio" not in names
    assert "resolve" not in names


# ---------------------------------------------------------------------------
# The rail's data and its modes (STORY-018)
#
# Everything below is state the *component* needs and the database does not:
# the true total behind the scope line, the retry behind the fault state, and
# the three per-row modes. `tests/test_session_rail.py` covers the rendering;
# these cover the behaviour it renders.
# ---------------------------------------------------------------------------


def _handler(state: ChatState, name: str):
    return type(state).event_handlers[name].fn


def test_rail_scope_is_silent_when_nothing_is_withheld():
    """A scope line on a complete list would state a window that is not a
    window. `copy.py` makes the cap's silence the thing to avoid, and the
    converse is this: only "more exist than are shown" is worth a line."""
    state = _make_state()
    state.sessions = [ChatSessionSummary(session_id="a", title="A")]
    state.sessions_total = 1

    assert state.rail_scope == ""


def test_rail_scope_states_the_window_against_the_true_total():
    """AC 11, "in the manner PRD-006's register states '100 most recent of
    3,180'" -- including the thousands separator, which is applied Python-side
    because a component reads Vars and cannot format a number."""
    state = _make_state()
    state.sessions = [
        ChatSessionSummary(session_id=str(n), title=str(n)) for n in range(50)
    ]
    state.sessions_total = 3180

    assert state.rail_scope == "50 most recent of 3,180"


@pytest.mark.asyncio
async def test_login_records_the_true_total_not_the_capped_length(
    temp_db, monkeypatch
):
    """The whole reason `chat_sessions.count` exists, driven through the state.

    Three sessions, a limit of two: the rail lists two and must still know there
    are three. `len(self.sessions)` could never produce the 3.
    """
    monkeypatch.setattr(chat_state_mod, "run_query", _capturing_run_query())
    state = _make_state()
    for text in ("first", "second", "third"):
        _new_chat(state)
        await _send(state, text)

    monkeypatch.setattr(settings, "CHAT_SESSION_LIMIT", 2)
    fresh = ChatState(_reflex_internal_init=True)
    fresh.token_input = _AUTH_TOKEN
    await _handler(fresh, "login")(fresh)

    assert len(fresh.sessions) == 2
    assert fresh.sessions_total == 3
    assert fresh.rail_scope == "2 most recent of 3"


@pytest.mark.asyncio
async def test_a_failed_read_empties_the_list_and_zeroes_the_total(
    temp_db, monkeypatch
):
    """The fault arm's contract: both are assigned, so the component never has
    to guess which of the three states it is in. A total left standing beside an
    emptied list would render "0 most recent of 12" over the fault panel."""
    def _raise(*args, **kwargs):
        raise ChatSessionError("list_for failed: store is down")

    monkeypatch.setattr(chat_state_mod.chat_sessions, "list_for", _raise)

    state = ChatState(_reflex_internal_init=True)
    state.token_input = _AUTH_TOKEN
    await _handler(state, "login")(state)

    assert state.sessions == []
    assert state.sessions_total == 0
    assert "store is down" in state.sessions_error


@pytest.mark.asyncio
async def test_retry_sessions_reloads_the_list_and_clears_the_fault(
    temp_db, monkeypatch
):
    """AC 6's second half. The fault state offers an action, and this is it."""
    monkeypatch.setattr(chat_state_mod, "run_query", _capturing_run_query())
    seeded = _make_state()
    await _send(seeded, "a real chat")

    state = _make_state()
    state.sessions_error = "list_for failed: store is down"

    await _handler(state, "retry_sessions")(state)

    assert state.sessions_error == ""
    assert [s.title for s in state.sessions] == ["a real chat"]
    assert state.sessions_total == 1


@pytest.mark.asyncio
async def test_retry_sessions_leaves_the_transcript_alone(temp_db, monkeypatch):
    """It re-reads the list and nothing else: the transcript on screen is still
    a real conversation, so a failed *rail* read must not cost the chat."""
    monkeypatch.setattr(chat_state_mod, "run_query", _capturing_run_query())
    state = _make_state()
    await _send(state, "a real chat")
    active, messages = state.active_session_id, list(state.messages)
    state.sessions_error = "list_for failed: store is down"

    await _handler(state, "retry_sessions")(state)

    assert state.active_session_id == active
    assert [m.content for m in state.messages] == [m.content for m in messages]


@pytest.mark.asyncio
async def test_retry_sessions_reports_a_credential_that_went_bad(temp_db):
    """The prologue every session handler shares: a credential deactivated while
    the tab was open is named, not retried into a silent empty list."""
    state = _make_state(token="not-a-real-token")

    await _handler(state, "retry_sessions")(state)

    assert state.sessions_error == SESSION_INVALIDATED_ERROR


def test_begin_rename_seeds_the_draft_and_closes_any_confirmation():
    """A row is in one mode or none."""
    state = _make_state()
    state.confirming_delete_id = "other"

    _handler(state, "begin_rename")(state, "abc", "Quarterly close")

    assert state.renaming_session_id == "abc"
    assert state.rename_draft == "Quarterly close"
    assert state.confirming_delete_id == ""


def test_ask_delete_arms_one_row_and_closes_any_rename():
    state = _make_state()
    state.renaming_session_id = "other"
    state.rename_draft = "half typed"

    _handler(state, "ask_delete")(state, "abc")

    assert state.confirming_delete_id == "abc"
    assert state.renaming_session_id == ""
    assert state.rename_draft == ""


def test_opening_a_mode_is_refused_while_a_send_is_in_flight():
    """The guard `new_chat` and `edit_and_resend` already carry. A confirmation
    armed against a rail that is about to reorder invites a click on the wrong
    row."""
    state = _make_state()
    state.pending = True

    _handler(state, "begin_rename")(state, "abc", "Quarterly close")
    _handler(state, "ask_delete")(state, "abc")

    assert state.renaming_session_id == ""
    assert state.confirming_delete_id == ""


def test_closing_a_mode_is_never_refused():
    """Getting *out* of a mode is unguarded: a reader who opened a rename before
    a send started must still be able to abandon it."""
    state = _make_state()
    state.pending = True
    state.renaming_session_id = "abc"
    state.rename_draft = "half typed"
    state.confirming_delete_id = "abc"

    _handler(state, "cancel_rename")(state)
    _handler(state, "cancel_delete")(state)

    assert state.renaming_session_id == ""
    assert state.rename_draft == ""
    assert state.confirming_delete_id == ""


def test_commit_rename_closes_the_field_and_delegates_the_write():
    """It validates nothing and writes nothing itself: `rename_session` owns the
    empty-title refusal and the ownership re-check, and a second copy of either
    would only be correct in one of the two places."""
    state = _make_state()
    _handler(state, "begin_rename")(state, "abc", "Quarterly close")
    _handler(state, "set_rename_draft")(state, "Q3 vendor spend")

    returned = _handler(state, "commit_rename")(state)

    assert state.renaming_session_id == ""
    assert state.rename_draft == ""
    assert returned is not None


def test_commit_rename_with_no_row_open_dispatches_nothing():
    """A blur arriving after the field has already closed must not rename
    whatever `rename_draft` last held."""
    state = _make_state()

    assert _handler(state, "commit_rename")(state) is None


def test_cancel_rename_discards_the_draft_without_dispatching():
    state = _make_state()
    _handler(state, "begin_rename")(state, "abc", "Quarterly close")
    _handler(state, "set_rename_draft")(state, "typed then abandoned")

    assert _handler(state, "cancel_rename")(state) is None
    assert state.rename_draft == ""


@pytest.mark.asyncio
async def test_a_landed_delete_moves_the_total_and_disarms_the_confirmation(
    temp_db, monkeypatch
):
    """The scope line counts the account, not the page, so a delete has to move
    it -- and the confirmation was about a row that no longer exists, so leaving
    it armed would arm whichever chat lands in its place."""
    monkeypatch.setattr(chat_state_mod, "run_query", _capturing_run_query())
    state = _make_state()
    await _send(state, "first chat")
    first = state.active_session_id
    _new_chat(state)
    await _send(state, "second chat")

    assert state.sessions_total == 2
    _handler(state, "ask_delete")(state, first)

    await _delete(state, first)

    assert state.sessions_total == 1
    assert state.confirming_delete_id == ""


@pytest.mark.asyncio
async def test_a_send_that_creates_a_session_moves_the_total(temp_db, monkeypatch):
    """The other half: lazy creation adds a chat that did not exist, so the
    total moves with the create exactly as it moves with a delete."""
    monkeypatch.setattr(chat_state_mod, "run_query", _capturing_run_query())
    state = _make_state()
    assert state.sessions_total == 0

    await _send(state, "first chat")
    assert state.sessions_total == 1

    await _send(state, "same chat, second turn")
    assert state.sessions_total == 1


@pytest.mark.asyncio
async def test_logout_clears_the_rails_modes_and_its_total(temp_db, monkeypatch):
    """A half-typed rename is one person's words about one person's chat, and an
    armed confirmation naming a chat the next reader cannot see is the rail's
    version of the misattribution `logout` already refuses for the bubbles."""
    monkeypatch.setattr(chat_state_mod, "run_query", _capturing_run_query())
    state = _make_state()
    await _send(state, "first chat")
    _handler(state, "begin_rename")(state, state.active_session_id, "Quarterly close")

    state.logout()

    assert state.sessions_total == 0
    assert state.renaming_session_id == ""
    assert state.rename_draft == ""
    assert state.confirming_delete_id == ""
