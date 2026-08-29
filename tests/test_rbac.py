"""Full role x permission matrix through the real endpoints/pipeline, plus a
pre-RBAC-migration-to-successful-query lifecycle test.

tests/test_authz.py already proves the raw matrix at the authorize() layer in
isolation (STORY-006). This file drives the same matrix through the actual
HTTP endpoints and the pipeline so a future permission or role change that
forgets to wire an endpoint correctly fails here, not only at the unit layer.
Cross-ingress denial-parity tests (POST /query vs ChatState.send()) live in
tests/test_chat_state.py, alongside their grant-path precedent
(test_chat_and_api_audit_rows_share_schema_and_fields) -- see this story's
plan for why the split is drawn there.
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db.database import (
    count_audit_logs,
    get_audit_log,
    get_connection,
    init_db,
    insert_audit_log,
    insert_user,
)
from app.db.models import AuditLog, User
from app.main import app
from app.models.schemas import QuerySuccessResponse
from app.services.authz import (
    MODEL_ALLOWLIST_WILDCARD_ROLES,
    PERMISSION_AUDIT_READ_ALL,
    PERMISSION_AUDIT_READ_OWN,
    PERMISSION_QUERY_BYOK,
    PERMISSION_QUERY_SUBMIT,
    PERMISSION_STATS_READ,
    ROLE_PERMISSIONS,
)
from app.services.identity import Identity, hash_token, resolve
from app.services.openrouter_client import OpenRouterResult
from app.services.query_pipeline import run_query

import chat_ui.chat_ui.state as chat_state_mod
from chat_ui.chat_ui.state import ChatState
from tests.test_db import _create_pre_rbac_database

client = TestClient(app)

_ROLES = ("admin", "auditor", "user")


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


def _latest_audit_entry() -> AuditLog:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM audit_logs ORDER BY id DESC LIMIT 1"
        ).fetchone()
    return get_audit_log(row["id"])


def _fail_if_called(*args, **kwargs):
    raise AssertionError("call_openrouter should not have been called")


def _fake_success(prompt, model="gpt-4", api_key=None):
    return OpenRouterResult(response="ok", model_used=model, tokens_used=1)


def _make_chat_state(user_id: str, token: str) -> ChatState:
    state = ChatState(_reflex_internal_init=True)
    state.user_id = user_id
    state._token = token
    return state


async def _send_via_chat(state: ChatState, text: str) -> None:
    state.input_text = text
    handler = type(state).event_handlers["send"]
    await handler.fn(state)  # bypasses the background-task chain guard on state.send()


# ---------------------------------------------------------------------------
# Full role x permission matrix, through the real endpoints (AC1)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("role", _ROLES)
def test_query_submit_matrix_through_post_query(role, temp_db, monkeypatch):
    token = f"{role}-token"
    insert_user(User(user_id=f"{role}-id", role=role, token_hash=hash_token(token)))
    expected_allowed = PERMISSION_QUERY_SUBMIT in ROLE_PERMISSIONS[role]

    monkeypatch.setattr(
        "app.routers.query.call_openrouter",
        _fake_success if expected_allowed else _fail_if_called,
    )

    response = client.post(
        "/query",
        headers={"Authorization": f"Bearer {token}"},
        json={"prompt": f"clean prompt for {role}"},
    )

    if expected_allowed:
        assert response.status_code == 200
        assert response.json()["status"] == "SUCCESS"
    else:
        assert response.status_code == 403
        assert response.json() == {"detail": f"Permission denied: {PERMISSION_QUERY_SUBMIT}"}
        assert _count_audit_rows() == 0


@pytest.mark.parametrize("role", _ROLES)
def test_stats_read_matrix_through_get_stats(role, temp_db):
    token = f"{role}-token"
    insert_user(User(user_id=f"{role}-id", role=role, token_hash=hash_token(token)))
    expected_allowed = PERMISSION_STATS_READ in ROLE_PERMISSIONS[role]

    response = client.get("/stats", headers={"Authorization": f"Bearer {token}"})

    if expected_allowed:
        assert response.status_code == 200
    else:
        assert response.status_code == 403
        assert response.json() == {"detail": f"Permission denied: {PERMISSION_STATS_READ}"}


@pytest.mark.parametrize("role", _ROLES)
def test_audit_scope_selection_matrix_through_get_audit(role, temp_db):
    token = f"{role}-token"
    own_user_id = f"{role}-id"
    insert_user(User(user_id=own_user_id, role=role, token_hash=hash_token(token)))
    insert_audit_log(
        AuditLog(timestamp="2026-07-01T10:00:00Z", user_id=own_user_id, prompt_hash="h1")
    )
    insert_audit_log(
        AuditLog(timestamp="2026-07-02T10:00:00Z", user_id="someone-else", prompt_hash="h2")
    )

    response = client.get("/audit", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    if PERMISSION_AUDIT_READ_ALL in ROLE_PERMISSIONS[role]:
        # app/routers/admin.py tries audit:read:all first -- admin and
        # auditor both hold it and see every row, unscoped.
        assert body["total"] == 2
    else:
        # user holds only audit:read:own -- every role in the built-in
        # matrix holds at least one of the two, so this branch is the only
        # other reachable outcome (a role holding neither is 403, already
        # covered by tests/test_audit_router.py::
        # test_identity_lacking_both_audit_permissions_returns_403).
        assert PERMISSION_AUDIT_READ_OWN in ROLE_PERMISSIONS[role]
        assert body["total"] == 1
        assert body["queries"][0]["user_id"] == own_user_id


@pytest.mark.parametrize("role", ("admin", "user"))
def test_query_byok_matrix_through_post_query_for_roles_holding_query_submit(
    role, temp_db, monkeypatch
):
    # auditor is excluded: it lacks query:submit, so the router's own
    # require_permission(query:submit) dependency denies it with 403 before
    # the BYOK check inside run_query() is ever reached -- see
    # test_query_submit_matrix_through_post_query for that denial.
    token = f"{role}-token"
    insert_user(User(user_id=f"{role}-id", role=role, token_hash=hash_token(token)))
    expected_allowed = PERMISSION_QUERY_BYOK in ROLE_PERMISSIONS[role]

    monkeypatch.setattr(
        "app.routers.query.call_openrouter",
        _fake_success if expected_allowed else _fail_if_called,
    )

    response = client.post(
        "/query",
        headers={"Authorization": f"Bearer {token}"},
        json={"prompt": f"byok prompt for {role}", "openrouter_api_key": "sk-test"},
    )

    assert response.status_code == 200
    body = response.json()
    if expected_allowed:
        assert body["status"] == "SUCCESS"
    else:
        assert body["status"] == "BLOCKED"
        assert body["required_permission"] == PERMISSION_QUERY_BYOK
        entry = _latest_audit_entry()
        assert entry.role == role
        assert entry.denied_permission == PERMISSION_QUERY_BYOK


@pytest.mark.parametrize("role", ("admin", "user"))
def test_model_allowlist_matrix_through_post_query(role, temp_db, monkeypatch):
    # auditor is excluded for the same reason as the BYOK matrix above: it
    # never reaches this check.
    token = f"{role}-token"
    insert_user(User(user_id=f"{role}-id", role=role, token_hash=hash_token(token)))
    model = "not-a-real-model"
    expected_allowed = role in MODEL_ALLOWLIST_WILDCARD_ROLES

    monkeypatch.setattr(
        "app.routers.query.call_openrouter",
        _fake_success if expected_allowed else _fail_if_called,
    )

    response = client.post(
        "/query",
        headers={"Authorization": f"Bearer {token}"},
        json={"prompt": f"model prompt for {role}", "model": model},
    )

    assert response.status_code == 200
    body = response.json()
    if expected_allowed:
        assert body["status"] == "SUCCESS"
    else:
        assert body["status"] == "BLOCKED"
        assert body["required_permission"] == f"query:model:{model}"
        entry = _latest_audit_entry()
        assert entry.role == role
        assert entry.denied_permission == f"query:model:{model}"


def test_unknown_role_denied_by_default_through_post_query(temp_db, monkeypatch):
    insert_user(User(user_id="outsider", role="guest", token_hash=hash_token("guest-token")))
    monkeypatch.setattr("app.routers.query.call_openrouter", _fail_if_called)

    response = client.post(
        "/query",
        headers={"Authorization": "Bearer guest-token"},
        json={"prompt": "hello from an unknown role"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": f"Permission denied: {PERMISSION_QUERY_SUBMIT}"}
    assert _count_audit_rows() == 0


# ---------------------------------------------------------------------------
# Full lifecycle: pre-RBAC migration -> bootstrap -> resolve -> authorize ->
# successful query (AC4, building on tests/test_db.py's column-level proof)
# ---------------------------------------------------------------------------


def test_full_rbac_lifecycle_after_migrating_pre_rbac_database(tmp_path, monkeypatch):
    """tests/test_db.py::test_init_db_migrates_pre_rbac_database already
    proves the ALTER TABLE mechanics in isolation. This test builds one
    level higher: a database created before PRD-005 migrates, a user
    bootstrapped exactly the way scripts/manage_users.py does resolves to a
    verified Identity, is authorized, and completes a real query -- while
    the pre-existing (pre-RBAC) row is left untouched.
    """
    db_path = tmp_path / "pre_rbac_lifecycle.db"
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path}")

    _create_pre_rbac_database(db_path)
    init_db()

    token = "lifecycle-token"
    insert_user(
        User(user_id="lifecycle-admin", role="admin", token_hash=hash_token(token))
    )

    identity = resolve(token)
    assert identity == Identity(user_id="lifecycle-admin", role="admin")

    result = run_query(
        identity=identity,
        prompt="post-migration query",
        device=None,
        model="gpt-4",
        openrouter_api_key=None,
        call_openrouter=_fake_success,
    )

    assert isinstance(result, QuerySuccessResponse)
    assert count_audit_logs() == 2  # the pre-existing legacy row, plus this one
    legacy = get_audit_log(1)
    assert legacy.user_id == "ana@empresa.com"
    assert legacy.role is None
    assert legacy.denied_permission is None


# ---------------------------------------------------------------------------
# query:byok is HTTP-only by design -- the chat UI has no BYOK affordance
# (Design Decision in this story's plan)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_state_never_forwards_a_byok_key_so_query_byok_has_no_chat_ingress(
    temp_db, monkeypatch
):
    """Pins chat_ui/chat_ui/state.py's hardcoded openrouter_api_key=None as
    an explicit, named invariant. query:byok is reachable only through
    POST /query -- there is no second ingress to compare it against, so this
    story does not (and cannot) offer a query:byok ingress-parity test. This
    test fails the moment someone adds a BYOK field to the chat composer
    without also revisiting that gap.
    """
    insert_user(User(user_id="chatter", role="user", token_hash=hash_token("chat-byok-token")))
    captured = {}

    def _fake_run_query(identity, prompt, device, model, openrouter_api_key, call_openrouter):
        captured["openrouter_api_key"] = openrouter_api_key
        return QuerySuccessResponse(response="ok", audit_id=1, model_used=model, tokens_used=1)

    monkeypatch.setattr(chat_state_mod, "run_query", _fake_run_query)

    state = _make_chat_state("chatter", "chat-byok-token")
    await _send_via_chat(state, "hello from chat")

    assert "openrouter_api_key" in captured
    assert captured["openrouter_api_key"] is None
