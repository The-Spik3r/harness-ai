"""PRD-013 STORY-013: the break-glass ingress policy (step 2b).

Sections 6.1, 6.8 (D4), 9.2 (T9 and the order invariant), 11 (Break-glass).
What is pinned here, by acceptance criterion:

- **AC 1.** The identity `resolve(ADMIN_TOKEN)` returns is refused under
  `ingress="v1"` and with no door at all (fail closed), with the existing
  forbidden body, one row carrying `denied_permission="ingress:break_glass"`,
  no upstream call and no usage-gate call. The label is not an RBAC permission.
- **AC 2.** Under the default `BREAK_GLASS_INGRESSES`, `/query` and the chat UI
  answer the token exactly as before.
- **AC 3.** The setting tightens: `chat` refuses `/query` with the `200`
  refusal body, `""` refuses the chat UI with its forbidden bubble, and the
  setting is read per call.
- **AC 4.** The role is not the marker: an `admin`-role user token, and an
  `Identity("admin", "admin")` built directly, are never refused here.
- **AC 5.** The admin console's gate never enters the pipeline, and spies put
  this arm after every authorization arm and before the usage gate.

The break-glass identity always comes from `resolve(settings.ADMIN_TOKEN)`,
never a hand-built `Identity(..., break_glass=True)`: the story states AC 1 in
terms of what `resolve` returns. Rows are read back by id through
`get_audit_log`, never by spying on `log_query`.
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

# Repo root, as tests/test_admin_state.py does for the AdminState import.
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from fastapi.testclient import TestClient

import app.services.query_pipeline as query_pipeline
import chat_ui.chat_ui.state as chat_state_mod
from app.config import settings
from app.db.database import get_audit_log, get_connection, insert_user
from app.db.models import User
from app.main import app
from app.models.messages import Message
from app.models.schemas import QueryBlockedForbiddenResponse, QuerySuccessResponse
from app.services import authz
from app.services.identity import Identity, hash_token, resolve
from app.services.openrouter_client import OpenRouterResult
from chat_ui.chat_ui.admin_state import AdminState
from chat_ui.chat_ui.state import ChatState

_REASON = "Break-glass credential not permitted on this ingress"
_LABEL = "ingress:break_glass"
_REFUSAL = QueryBlockedForbiddenResponse(reason=_REASON, required_permission=_LABEL)

_JUAN = Identity(user_id="juan@empresa.com", role="user")
_DENIED = Identity(user_id="reviewer", role="auditor")  # lacks query:submit
_ROOT = Identity(user_id="root", role="admin")  # holds query:byok

_ADMIN_ROLE_USER_TOKEN = "root-admin-role-token"


# --- helpers ----------------------------------------------------------------


def _break_glass() -> Identity:
    identity = resolve(settings.ADMIN_TOKEN)
    assert identity is not None and identity.break_glass is True  # precondition
    return identity


def _count_audit_rows() -> int:
    with get_connection() as conn:
        return conn.execute("SELECT COUNT(*) AS n FROM audit_logs").fetchone()["n"]


def _last_audit_entry():
    # By id, not timestamp: timestamps have one-second resolution.
    with get_connection() as conn:
        row = conn.execute("SELECT id FROM audit_logs ORDER BY id DESC LIMIT 1").fetchone()
    return get_audit_log(row["id"])


def _fail_if_called(*args, **kwargs):
    raise AssertionError("this collaborator should not have been called")


def _answer(messages, model="gpt-4", api_key=None):
    return OpenRouterResult(response="Hi there!", model_used=model, tokens_used=12)


_NO_DOOR = object()


def _run(identity, prompt="how do I parse a date?", *, ingress=_NO_DOOR, upstream=_answer,
         api_key=None):
    """`run_conversation` with one user turn; `ingress` omitted unless given."""
    kwargs = {} if ingress is _NO_DOOR else {"ingress": ingress}
    return query_pipeline.run_conversation(
        identity=identity, messages=[Message("user", prompt)], device=None,
        model="gpt-4", openrouter_api_key=api_key, call_openrouter=upstream,
        **kwargs,
    )


@pytest.fixture
def admin_client(temp_db):
    """`/query` authenticated with the break-glass credential itself."""
    return TestClient(app, headers={"Authorization": f"Bearer {settings.ADMIN_TOKEN}"})


def _admin_chat_state() -> ChatState:
    state = ChatState(_reflex_internal_init=True)
    state.user_id = "admin"
    state._token = settings.ADMIN_TOKEN
    return state


async def _send(state: ChatState, text: str) -> None:
    state.input_text = text
    handler = type(state).event_handlers["send"]
    await handler.fn(state)  # bypasses the background-task chain guard


# --- AC 1: refused on v1 and with no door; one row; nothing upstream ---------


@pytest.mark.parametrize(
    "door", [pytest.param("v1", id="v1"), pytest.param(_NO_DOOR, id="no-door")]
)
def test_break_glass_is_refused_with_the_forbidden_body_and_one_row(temp_db, monkeypatch, door):
    # The gate is never reached, so a refused attempt counts against nothing.
    monkeypatch.setattr(query_pipeline, "admit", _fail_if_called)
    before = _count_audit_rows()

    result = _run(_break_glass(), ingress=door, upstream=_fail_if_called)

    assert result == _REFUSAL
    assert _count_audit_rows() == before + 1
    row = _last_audit_entry()
    assert row.success is True
    assert row.denied_permission == _LABEL
    assert row.user_id == "admin"
    assert row.role == "admin"
    assert row.ingress == (None if door is _NO_DOOR else door)
    assert row.message_count == 1
    assert row.dedup_key is not None
    assert row.conversation_key is not None
    assert row.limit_exceeded is None
    assert row.was_duplicate_blocked is False
    assert row.error_message is None


def test_the_refusal_holds_with_usage_limits_off(temp_db, monkeypatch):
    monkeypatch.setattr(settings, "USAGE_LIMITS_ENABLED", False)

    assert _run(_break_glass(), ingress="v1", upstream=_fail_if_called) == _REFUSAL


def test_ingress_break_glass_is_not_an_rbac_permission():
    """A label on the row, like `query:model:{model}`: no role can be granted it."""
    assert _LABEL not in authz._KNOWN_PERMISSIONS


# --- AC 2: the default setting changes nothing on /query and chat -----------


@pytest.mark.parametrize("door", ["query", "chat"])
def test_default_setting_admits_break_glass_on_query_and_chat(temp_db, door):
    result = _run(_break_glass(), ingress=door)

    assert isinstance(result, QuerySuccessResponse)
    assert _last_audit_entry().denied_permission is None


def test_post_query_with_admin_token_succeeds_under_the_default(admin_client, monkeypatch):
    monkeypatch.setattr("app.routers.query.call_openrouter", _answer)

    response = admin_client.post("/query", json={"prompt": "recover the deployment"})

    assert response.status_code == 200
    assert response.json()["status"] == "SUCCESS"
    assert _last_audit_entry().ingress == "query"


@pytest.mark.asyncio
async def test_chat_ui_send_with_admin_token_is_answered_under_the_default(temp_db, monkeypatch):
    monkeypatch.setattr(chat_state_mod, "call_openrouter", _answer)
    state = _admin_chat_state()

    await _send(state, "hello from the break-glass seat")

    assert state.messages[-1].kind == "assistant"
    assert state.messages[-1].content == "Hi there!"


# --- AC 3: the setting tightens ---------------------------------------------


def test_setting_chat_only_refuses_post_query_with_the_200_body(admin_client, monkeypatch):
    monkeypatch.setattr(settings, "BREAK_GLASS_INGRESSES", "chat")
    monkeypatch.setattr("app.routers.query.call_openrouter", _fail_if_called)

    response = admin_client.post("/query", json={"prompt": "recover the deployment"})

    assert response.status_code == 200
    assert response.json() == {
        "status": "BLOCKED",
        "reason": _REASON,
        "required_permission": _LABEL,
    }
    row = _last_audit_entry()
    assert row.denied_permission == _LABEL
    assert row.ingress == "query"


@pytest.mark.asyncio
async def test_setting_empty_refuses_the_chat_ui_with_the_forbidden_bubble(temp_db, monkeypatch):
    monkeypatch.setattr(settings, "BREAK_GLASS_INGRESSES", "")
    monkeypatch.setattr(chat_state_mod, "call_openrouter", _fail_if_called)
    state = _admin_chat_state()

    await _send(state, "hello from the break-glass seat")

    bubble = state.messages[-1]
    assert bubble.kind == "forbidden"
    assert bubble.content == _REASON
    assert bubble.required_permission == _LABEL
    row = _last_audit_entry()
    assert row.denied_permission == _LABEL
    assert row.ingress == "chat"


def test_the_setting_is_read_per_call(temp_db, monkeypatch):
    identity = _break_glass()

    assert isinstance(_run(identity, "first", ingress="query"), QuerySuccessResponse)

    monkeypatch.setattr(settings, "BREAK_GLASS_INGRESSES", "chat")

    assert _run(identity, "second", ingress="query", upstream=_fail_if_called) == _REFUSAL


# --- AC 4: the role is not the marker ---------------------------------------


def test_an_admin_role_user_token_is_not_refused_on_v1(temp_db):
    insert_user(User(user_id="root", role="admin", token_hash=hash_token(_ADMIN_ROLE_USER_TOKEN)))
    identity = resolve(_ADMIN_ROLE_USER_TOKEN)
    assert identity.role == "admin"
    assert identity.break_glass is False

    assert isinstance(_run(identity, ingress="v1"), QuerySuccessResponse)


def test_a_directly_built_admin_identity_is_not_refused_on_v1(temp_db):
    assert isinstance(_run(Identity("admin", "admin"), ingress="v1"), QuerySuccessResponse)


@pytest.mark.parametrize(
    "identity, door, refused",
    [
        (Identity("admin", "admin", break_glass=True), "v1", True),
        (Identity("admin", "admin", break_glass=True), None, True),
        (Identity("admin", "admin", break_glass=True), "query", False),
        (Identity("admin", "admin", break_glass=True), "chat", False),
        (Identity("admin", "admin"), "v1", False),
        (Identity("admin", "admin"), None, False),
        (_ROOT, "v1", False),
        (_JUAN, None, False),
    ],
    ids=[
        "break-glass-v1", "break-glass-none", "break-glass-query", "break-glass-chat",
        "admin-role-v1", "admin-role-none", "admin-user-v1", "user-none",
    ],
)
def test_the_predicate_marks_the_credential_not_the_role(identity, door, refused):
    """Under the default setting. A unit-level table for the arm's condition."""
    assert query_pipeline._break_glass_refused(identity, door) is refused


# --- AC 5: the console is untouched, and the order ---------------------------


def test_admin_console_gate_still_accepts_admin_token(monkeypatch):
    """`AdminState.authenticate` compares against ADMIN_TOKEN directly: the
    console is not an ingress and never reaches the pipeline (Section 6.8)."""
    monkeypatch.setattr(query_pipeline, "run_conversation", _fail_if_called)
    monkeypatch.setattr(query_pipeline, "_break_glass_refused", _fail_if_called)
    state = AdminState(_reflex_internal_init=True)
    state.token_input = settings.ADMIN_TOKEN

    type(state).event_handlers["authenticate"].fn(state)

    assert state.authenticated is True
    assert state.gate_error == ""


def _trace_the_checks(monkeypatch) -> list:
    """Spies on every step up to the upstream call, recording one label each.
    Both authorization helpers record `authorize`, as the gate's order test does."""
    trace: list = []
    real = {
        "authorize": query_pipeline.authorize,
        "authorize_model": query_pipeline.authorize_model,
        "break_glass": query_pipeline._break_glass_refused,
        "admit": query_pipeline.admit,
        "context_limit": query_pipeline._context_limit_exceeded,
        "duplicate": query_pipeline.check_duplicate,
        "pattern": query_pipeline.inspect,
    }

    def _spy_authorize(identity, permission):
        trace.append("authorize")
        return real["authorize"](identity, permission)

    def _spy_authorize_model(identity, model):
        trace.append("authorize")
        return real["authorize_model"](identity, model)

    def _spy_break_glass(identity, ingress):
        trace.append("break_glass")
        return real["break_glass"](identity, ingress)

    def _spy_admit(identity, charges_budget):
        trace.append("usage")
        return real["admit"](identity, charges_budget=charges_budget)

    def _spy_context_limit(messages):
        trace.append("context_limit")
        return real["context_limit"](messages)

    def _spy_duplicate(user_id, key):
        trace.append("duplicate")
        return real["duplicate"](user_id, key)

    def _spy_inspect(messages, profile, **kwargs):
        trace.append("pattern")
        return real["pattern"](messages, profile, **kwargs)

    monkeypatch.setattr(query_pipeline, "authorize", _spy_authorize)
    monkeypatch.setattr(query_pipeline, "authorize_model", _spy_authorize_model)
    monkeypatch.setattr(query_pipeline, "_break_glass_refused", _spy_break_glass)
    monkeypatch.setattr(query_pipeline, "admit", _spy_admit)
    monkeypatch.setattr(query_pipeline, "_context_limit_exceeded", _spy_context_limit)
    monkeypatch.setattr(query_pipeline, "check_duplicate", _spy_duplicate)
    monkeypatch.setattr(query_pipeline, "inspect", _spy_inspect)
    return trace


def _recording(trace):
    def _upstream(messages, model="gpt-4", api_key=None):
        trace.append("upstream")
        return _answer(messages, model, api_key)

    return _upstream


def test_check_order_puts_break_glass_after_authorization_and_before_the_gate(
    temp_db, monkeypatch
):
    trace = _trace_the_checks(monkeypatch)

    result = _run(_JUAN, upstream=_recording(trace))

    assert isinstance(result, QuerySuccessResponse)
    assert trace == [
        "authorize", "authorize", "break_glass", "usage",
        "context_limit", "duplicate", "pattern", "upstream",
    ]


def test_check_order_with_byok_puts_break_glass_after_all_three_arms(temp_db, monkeypatch):
    trace = _trace_the_checks(monkeypatch)

    result = _run(_ROOT, api_key="sk-caller-supplied", upstream=_recording(trace))

    assert isinstance(result, QuerySuccessResponse)
    assert trace[:5] == ["authorize", "authorize", "authorize", "break_glass", "usage"]


def test_a_refused_break_glass_attempt_stops_before_the_gate(temp_db, monkeypatch):
    trace = _trace_the_checks(monkeypatch)

    result = _run(_break_glass(), ingress="v1", upstream=_recording(trace))

    assert result == _REFUSAL
    assert trace == ["authorize", "authorize", "break_glass"]


def test_a_caller_denied_by_authorization_never_reaches_break_glass(temp_db, monkeypatch):
    monkeypatch.setattr(query_pipeline, "_break_glass_refused", _fail_if_called)

    result = _run(_DENIED, upstream=_fail_if_called)

    assert isinstance(result, QueryBlockedForbiddenResponse)
    assert result.required_permission == "query:submit"
