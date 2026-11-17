"""PRD-018 STORY-007: the chat UI survives a storage failure.

Section 6.7 (chat column), T9, and the Section 11 criterion that `pending` is
False after a storage failure. Non-`db`: no database is touched; `resolve`,
the lazy session create and the pipeline are all stubbed.
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import pytest

import chat_ui.chat_ui.state as chat_state_mod
from app.db.errors import StorageError, StorageUnavailableError
from app.models.schemas import QuerySuccessResponse
from app.services import chat_sessions
from app.services.chat_sessions import ChatSessionError
from app.services.duplicate_checker import DuplicateCheckError
from app.services.identity import Identity
from app.services.pii_redactor import PiiRedactorError
from app.services.usage_limits import UsageLimitError
from chat_ui.chat_ui.copy import (
    LOGIN_INVALID_TOKEN_ERROR,
    LOGIN_STORAGE_UNAVAILABLE_ERROR,
    STORAGE_UNAVAILABLE_NOT_SENT_NOTICE,
)
from chat_ui.chat_ui.state import ChatState

_IDENTITY = Identity(user_id="u@example.com", role="user")


def _make_state() -> ChatState:
    state = ChatState(_reflex_internal_init=True)
    state.user_id = "u@example.com"
    state._token = "tok"
    return state


async def _send(state: ChatState, text: str) -> None:
    state.input_text = text
    handler = type(state).event_handlers["send"]
    await handler.fn(state)


def _raiser(exc):
    def _raise(*args, **kwargs):
        raise exc

    return _raise


def _outage(msg="Hrana: STREAM_EXPIRED"):
    return StorageUnavailableError(msg, retry_after_seconds=2)


def _caused(cls, cause):
    """`cls` raised `from cause`, so `__cause__` is set."""
    try:
        try:
            raise cause
        except Exception as inner:
            raise cls("Hrana: stream expired") from inner
    except cls as exc:
        return exc


def _fail_if_called(*args, **kwargs):
    raise AssertionError("pipeline must not be called")


def _stub_pipeline_raising(monkeypatch, exc):
    monkeypatch.setattr(chat_state_mod, "resolve", lambda token: _IDENTITY)
    monkeypatch.setattr(chat_sessions, "create", lambda *a, **k: None)

    async def fake(fn, *a, **k):
        raise exc

    monkeypatch.setattr(chat_state_mod, "run_in_pipeline", fake)


def _record_to_thread(monkeypatch):
    offloaded = []
    real = chat_state_mod.asyncio.to_thread

    async def rec(fn, *args, **kwargs):
        offloaded.append(fn)
        return await real(fn, *args, **kwargs)

    monkeypatch.setattr(chat_state_mod.asyncio, "to_thread", rec)
    return offloaded


@pytest.mark.asyncio
async def test_send_storage_unavailable_in_resolve_unlocks_the_composer(monkeypatch):
    monkeypatch.setattr(chat_state_mod, "resolve", _raiser(_outage()))
    monkeypatch.setattr(chat_state_mod, "run_in_pipeline", _fail_if_called)
    state = _make_state()
    await _send(state, "hello")
    # PRD-018 Section 11: pending is False after a storage failure.
    assert state.pending is False
    assert len(state.messages) == 1
    bubble = state.messages[0]
    assert bubble.kind == bubble.content == "internal_error"
    assert bubble.detail == STORAGE_UNAVAILABLE_NOT_SENT_NOTICE
    assert bubble.prompt == "hello"
    assert "Hrana" not in bubble.detail
    assert state.input_text == "hello"


@pytest.mark.asyncio
async def test_send_plain_storage_error_in_resolve_uses_the_same_bubble(monkeypatch):
    monkeypatch.setattr(
        chat_state_mod, "resolve", _raiser(StorageError("Hrana: SQL_PARSE_ERROR"))
    )
    state = _make_state()
    await _send(state, "hello")
    assert state.pending is False
    assert state.messages[-1].detail == STORAGE_UNAVAILABLE_NOT_SENT_NOTICE


@pytest.mark.asyncio
async def test_send_after_a_resolve_failure_can_send_again(monkeypatch):
    monkeypatch.setattr(chat_state_mod, "resolve", _raiser(_outage()))
    state = _make_state()
    await _send(state, "hello")
    assert state.pending is False

    monkeypatch.setattr(chat_state_mod, "resolve", lambda token: _IDENTITY)
    monkeypatch.setattr(chat_sessions, "create", lambda *a, **k: None)

    async def ok(fn, *a, **k):
        return QuerySuccessResponse(response="ok", audit_id=1, model_used="m", tokens_used=1)

    monkeypatch.setattr(chat_state_mod, "run_in_pipeline", ok)
    await _send(state, "hello again")
    assert state.pending is False
    assert state.messages[-1].kind == "assistant"


@pytest.mark.asyncio
async def test_send_resolves_off_the_event_loop(monkeypatch):
    stub = _raiser(_outage())
    monkeypatch.setattr(chat_state_mod, "resolve", stub)
    offloaded = _record_to_thread(monkeypatch)
    await _send(_make_state(), "hello")
    assert stub in offloaded


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exc",
    [_outage("Hrana: x"), StorageError("Hrana: SQL_PARSE_ERROR")],
    ids=["unavailable", "statement"],
)
async def test_login_storage_unavailable_shows_the_storage_notice(monkeypatch, exc):
    monkeypatch.setattr(chat_state_mod, "resolve", _raiser(exc))
    state = ChatState(_reflex_internal_init=True)
    state.token_input = "tok"
    await state.login()
    assert state.login_error == LOGIN_STORAGE_UNAVAILABLE_ERROR
    assert state.login_error != LOGIN_INVALID_TOKEN_ERROR
    assert state.user_id == ""
    assert state._token == ""
    assert state.sessions == []
    assert state.token_input == "tok"


@pytest.mark.asyncio
async def test_login_resolves_off_the_event_loop(monkeypatch):
    calls = []

    def stub(token):
        calls.append(token)
        return None

    monkeypatch.setattr(chat_state_mod, "resolve", stub)
    offloaded = _record_to_thread(monkeypatch)
    state = ChatState(_reflex_internal_init=True)
    state.token_input = "tok"
    await state.login()
    assert stub in offloaded and calls == ["tok"]


_GATES = [DuplicateCheckError, UsageLimitError, ChatSessionError]


@pytest.mark.asyncio
@pytest.mark.parametrize("cls", _GATES)
async def test_gate_fault_caused_by_an_outage_shows_fixed_copy(monkeypatch, cls):
    exc = _caused(cls, _outage("Hrana: stream expired"))
    _stub_pipeline_raising(monkeypatch, exc)
    state = _make_state()
    await _send(state, "hello")
    bubble = state.messages[-1]
    assert bubble.kind == "internal_error"
    assert bubble.detail == STORAGE_UNAVAILABLE_NOT_SENT_NOTICE
    assert "Hrana" not in bubble.detail
    assert state.pending is False


@pytest.mark.asyncio
@pytest.mark.parametrize("cls", _GATES)
@pytest.mark.parametrize("cause", [StorageError("Hrana: SQL_PARSE_ERROR"), None])
async def test_gate_fault_with_a_non_transient_cause_keeps_todays_detail(
    monkeypatch, cls, cause
):
    exc = _caused(cls, cause) if cause is not None else cls("db locked")
    _stub_pipeline_raising(monkeypatch, exc)
    state = _make_state()
    await _send(state, "hello")
    assert state.messages[-1].detail == str(exc)
    assert state.pending is False


@pytest.mark.asyncio
async def test_pii_redactor_error_is_not_a_storage_gate(monkeypatch):
    exc = _caused(PiiRedactorError, _outage())
    _stub_pipeline_raising(monkeypatch, exc)
    state = _make_state()
    await _send(state, "hello")
    assert state.messages[-1].detail == str(exc)
