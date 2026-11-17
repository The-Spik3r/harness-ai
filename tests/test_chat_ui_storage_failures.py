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
from app.db.errors import AuditUnavailableError, StorageError, StorageUnavailableError
from app.models.schemas import QuerySuccessResponse
from app.services import chat_sessions
from app.services.chat_sessions import ChatSessionError
from app.services.duplicate_checker import DuplicateCheckError
from app.services.identity import Identity
from app.services.pii_redactor import PiiRedactorError
from app.services.usage_limits import UsageLimitError
from chat_ui.chat_ui.copy import (
    AUDIT_UNAVAILABLE_HEADLINE,
    AUDIT_UNAVAILABLE_NOTICE,
    FOOTER_AUDIT_PENDING,
    FOOTER_AUDIT_PREFIX,
    INTERNAL_ERROR_HEADLINE,
    LOGIN_INVALID_TOKEN_ERROR,
    LOGIN_STORAGE_UNAVAILABLE_ERROR,
    STORAGE_UNAVAILABLE_NOT_SENT_NOTICE,
)
from chat_ui.chat_ui.state import ChatState

# PRD-018 D14: `audit_ref` is required on every success (the row's write_id).
_AUDIT_REF = "0" * 32

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
        return QuerySuccessResponse(response="ok", audit_id=1, audit_ref=_AUDIT_REF, model_used="m", tokens_used=1)

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


# --- PRD-018 STORY-010: AuditUnavailableError, and a journaled success --------


def _audit_unavailable():
    return AuditUnavailableError("audit journal is full: AUDIT_BUFFER_MAX_BYTES=1 CANARY-journal-text")


@pytest.mark.asyncio
async def test_audit_unavailable_shows_the_fixed_bubble_not_driver_text(monkeypatch):
    # PRD-018 T5/T9, D10: the model may have answered, so the copy must not
    # say "nothing was sent".
    _stub_pipeline_raising(monkeypatch, _audit_unavailable())
    state = _make_state()
    await _send(state, "hello")
    bubble = state.messages[-1]
    assert bubble.kind == bubble.content == "internal_error"
    assert bubble.detail == AUDIT_UNAVAILABLE_NOTICE
    assert "nothing was sent" not in bubble.detail
    assert "CANARY" not in bubble.detail and "AUDIT_BUFFER" not in bubble.detail
    assert bubble.prompt == "hello"
    assert state.pending is False


# Rendering needs the Reflex import path (`chat_ui.components...`), which would
# break every other module in-process, so it runs in a subprocess (the approach of
# tests/test_chat_components_import.py).
_RENDER_SCRIPT = r"""
import json
from chat_ui.components import bubbles
from chat_ui.state import ChatState

var = ChatState.messages[0]
print(json.dumps({
    "internal_error": str(bubbles.render_internal_error(var).render()),
    "assistant": str(bubbles.render_assistant(var).render()),
}))
"""


def _rendered():
    import json
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join([str(root / "chat_ui"), str(root)]),
        "PYTHONUTF8": "1",
    }
    env.setdefault("DATABASE_URL", "http://127.0.0.1:8080")
    done = subprocess.run(
        [sys.executable, "-c", _RENDER_SCRIPT], cwd=root / "chat_ui", env=env,
        capture_output=True, text=True, timeout=120,
    )
    assert done.returncode == 0, done.stderr[-2000:]
    return json.loads(done.stdout.strip().splitlines()[-1])


def test_audit_unavailable_bubble_does_not_claim_it_failed_before_the_model():
    # PRD-018 T5: neither the detail nor the headline may say the harness failed
    # before reaching the model -- step 8 runs after the model answered.
    assert "before" not in AUDIT_UNAVAILABLE_NOTICE
    assert "before" not in AUDIT_UNAVAILABLE_HEADLINE
    assert AUDIT_UNAVAILABLE_HEADLINE != INTERNAL_ERROR_HEADLINE
    rendered = _rendered()["internal_error"]
    # The headline is chosen by the bubble's detail; the generic one stays the
    # default for every other internal error.
    assert AUDIT_UNAVAILABLE_HEADLINE in rendered and INTERNAL_ERROR_HEADLINE in rendered
    # Compared on a fragment: the compiled JS escapes the notice's apostrophe.
    assert AUDIT_UNAVAILABLE_NOTICE.split("'")[-1] in rendered


@pytest.mark.asyncio
async def test_a_journaled_success_stores_a_null_audit_id(monkeypatch):
    # PRD-018 D14 / 6.7: audit_id None on the result -> bubble 0 -> NULL on the row.
    monkeypatch.setattr(chat_state_mod, "resolve", lambda token: _IDENTITY)
    monkeypatch.setattr(chat_sessions, "create", lambda *a, **k: None)

    async def journaled(fn, *a, **k):
        return QuerySuccessResponse(
            response="ok", audit_id=None, audit_ref=_AUDIT_REF, model_used="m", tokens_used=1
        )

    monkeypatch.setattr(chat_state_mod, "run_in_pipeline", journaled)
    state = _make_state()
    await _send(state, "hello")

    bubble = state.messages[-1]
    assert bubble.kind == "assistant" and bubble.audit_id == 0
    assert chat_state_mod._to_stored_message(bubble, "s1").audit_id is None


def test_the_footer_shows_audit_pending_instead_of_audit_zero():
    # PRD-018 D14: a journaled success carries audit_id 0, which must not read "#0".
    rendered = _rendered()["assistant"]
    assert FOOTER_AUDIT_PENDING in rendered
    assert FOOTER_AUDIT_PREFIX in rendered  # the healthy "#<id>" arm is kept
