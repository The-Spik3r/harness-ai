"""PRD-023 STORY-017: `GET /audit/actions` MCP filters and fields, and `GET /skills`.

Covers PRD-023 Section 4 (API and admin console), D21 and Section 10. The
validation and `/skills` tests need no database; the ones that read seeded rows
request `temp_db` and so run as `db` tests against the libSQL dev server (CI).
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import json
from types import MappingProxyType
from typing import get_args

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db.database import insert_action_decisions, insert_user
from app.db.models import MCP_OUTCOME_VALUES, ActionDecisionRow, User
from app.main import app
from app.middleware.auth import require_identity
from app.routers import admin
from app.services import authz, mcp_config
from app.services.identity import Identity, hash_token
from app.services.mcp_config import McpAuth, McpConfig, McpServer, Skill

client = TestClient(app)

_ADMIN_HEADERS = {"Authorization": f"Bearer {settings.ADMIN_TOKEN}"}


def _row(**overrides) -> ActionDecisionRow:
    fields = dict(
        timestamp="2026-11-23T10:00:00Z",
        audit_id=None,
        session_id=None,
        user_id="dev-1",
        role="user",
        tool_call_id="call_1",
        tool_name="github__search",
        operation_kind=None,
        target_preview=None,
        arguments_hash="h" * 64,
        arguments_preview=None,
        decision="allow",
        rule="tool.not_in_skill",
        reason="r",
        granted_by=None,
        classifications="[]",
        policy_digest="sha256:3f1c",
        surface="mcp",
        mcp_server="github",
        skills=json.dumps(["triage"]),
        arguments_canonical_hash="c" * 64,
    )
    fields.update(overrides)
    return ActionDecisionRow(**fields)


def _entries(response) -> list:
    assert response.status_code == 200, response.text
    return response.json()["entries"]


# --- Validation and pass-through (no database) ---------------------------------


def test_surface_literal_is_pinned():
    assert get_args(admin.ActionSurfaceFilter) == ("v1", "mcp")


def test_outcome_filter_uses_the_closed_vocabulary():
    assert get_args(admin.McpOutcome) == MCP_OUTCOME_VALUES


@pytest.mark.parametrize(
    "query",
    ["linked=maybe", "surface=x", "outcome=bogus", "server="],
)
def test_invalid_filter_is_422_and_never_reaches_the_reader(monkeypatch, query):
    def fail(**kwargs):
        raise AssertionError("repository function should not have been called")

    monkeypatch.setattr("app.routers.admin.list_action_decisions", fail)

    assert client.get(f"/audit/actions?{query}", headers=_ADMIN_HEADERS).status_code == 422


def test_every_filter_reaches_the_reader(monkeypatch):
    calls: list = []

    def recorder(**kwargs):
        calls.append(kwargs)
        return []

    monkeypatch.setattr("app.routers.admin.list_action_decisions", recorder)

    response = client.get(
        "/audit/actions?surface=mcp&server=github&outcome=timeout&linked=false&decision=allow",
        headers=_ADMIN_HEADERS,
    )

    assert response.status_code == 200
    assert calls == [
        {
            "limit": 100, "user_id": None, "decision": "allow", "audit_id": None,
            "surface": "mcp", "mcp_server": "github", "outcome": "timeout",
            "linked": False,
        }
    ]


# --- Seeded rows (db) -----------------------------------------------------------


def _user(user_id: str, role: str) -> dict:
    token = f"{user_id}-token"
    insert_user(User(user_id=user_id, role=role, token_hash=hash_token(token)))
    return {"Authorization": f"Bearer {token}"}


def _ids(response) -> list:
    return [e["tool_call_id"] for e in _entries(response)]


def _seed():
    insert_action_decisions([
        _row(tool_call_id="ok", outcome="ok", duration_ms=5, result_bytes=10,
             result_flags=json.dumps(["x", {"list": "injection", "pattern_id": 2}])),
        _row(tool_call_id="late", outcome="timeout"),
        _row(tool_call_id="other", mcp_server="jira", outcome="ok"),
        _row(tool_call_id="v1", surface="v1", mcp_server="github", skills=None,
             arguments_canonical_hash="c" * 64),
    ])
    (v1_id,) = insert_action_decisions([_row(tool_call_id="v1b", surface="v1")])
    insert_action_decisions([
        _row(tool_call_id="linked", linked_decision_id=v1_id, outcome="ok"),
    ])


def test_filters_narrow_and_combine_db(temp_db):
    _seed()

    assert set(_ids(client.get("/audit/actions?surface=mcp&outcome=timeout", headers=_ADMIN_HEADERS))) == {"late"}
    assert set(_ids(client.get("/audit/actions?server=github&surface=mcp", headers=_ADMIN_HEADERS))) == {
        "ok", "late", "linked"}
    assert _ids(client.get("/audit/actions?server=nope", headers=_ADMIN_HEADERS)) == []
    assert set(_ids(client.get("/audit/actions?surface=v1", headers=_ADMIN_HEADERS))) == {"v1", "v1b"}
    # ANDed with `decision`.
    assert _ids(client.get("/audit/actions?surface=mcp&decision=deny", headers=_ADMIN_HEADERS)) == []


def test_linked_filter_db(temp_db):
    _seed()

    assert _ids(client.get("/audit/actions?linked=true", headers=_ADMIN_HEADERS)) == ["linked"]
    unlinked = set(_ids(client.get("/audit/actions?linked=false", headers=_ADMIN_HEADERS)))
    # Unlinked gateway rows only: no `/v1` row, no linked row.
    assert unlinked == {"ok", "late", "other"}


def test_own_scope_with_filters_db(temp_db):
    headers = _user("dev-1", "user")  # built-in `user` holds audit:read:own only
    insert_action_decisions([
        _row(tool_call_id="mine"),
        _row(tool_call_id="theirs", user_id="dev-2"),
    ])

    assert _ids(client.get("/audit/actions?surface=mcp", headers=headers)) == ["mine"]
    assert _ids(client.get("/audit/actions?server=github", headers=headers)) == ["mine"]
    # The filter narrows within the scope and never widens it.
    assert _ids(client.get("/audit/actions?server=jira", headers=headers)) == []


def test_entry_carries_the_gateway_fields_db(temp_db):
    _seed()

    entries = {e["tool_call_id"]: e for e in _entries(client.get("/audit/actions", headers=_ADMIN_HEADERS))}

    ok = entries["ok"]
    assert ok["surface"] == "mcp" and ok["mcp_server"] == "github"
    assert ok["skills"] == ["triage"]
    assert ok["outcome"] == "ok" and ok["duration_ms"] == 5 and ok["result_bytes"] == 10
    assert ok["result_flags"] == ["x", {"list": "injection", "pattern_id": 2}]
    assert ok["linked_decision_id"] is None
    assert entries["linked"]["linked_decision_id"] is not None
    v1 = entries["v1b"]
    assert v1["surface"] == "v1"
    assert v1["mcp_server"] is None and v1["outcome"] is None and v1["result_flags"] is None


# --- GET /skills ---------------------------------------------------------------

_SECRET_URL = "https://secret-host.example.invalid/mcp"
_SECRET_ENV = "SECRET_TOKEN_ENV_NAME"
_SECRET_HEADER = "X-Secret-Header-Name"
_SECRET_TEXT = "SECRET-INSTRUCTIONS-TEXT"


def _config() -> McpConfig:
    servers = MappingProxyType({
        "a": McpServer("a", _SECRET_URL, False,
                       McpAuth("bearer", _SECRET_ENV, "", "s3cret-value"), 10, 1000),
        "b": McpServer("b", "https://other-host.example.invalid/mcp", False,
                       McpAuth("header", "OTHER_ENV", _SECRET_HEADER, "v2"), 10, 1000),
    })
    return McpConfig(
        servers=servers,
        skills=(
            Skill("triage", "1.0.0", "Triage things", _SECRET_TEXT, ("a__search",), ("a",)),
            Skill("empty", "2.0.0", "Nobody holds", _SECRET_TEXT, (), ()),
        ),
    )


@pytest.fixture
def skills_on(monkeypatch):
    monkeypatch.setattr(settings, "MCP_ENABLED", True)
    monkeypatch.setattr(mcp_config, "_config", _config())
    monkeypatch.setattr(
        authz, "ROLE_PERMISSIONS",
        {"admin": {"stats:read", "skill:triage"}, "auditor": {"stats:read", "skill:triage"}},
    )


def test_skills_shape_roles_and_no_secrets(skills_on):
    response = client.get("/skills", headers=_ADMIN_HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"skills", "mcp_config_digest"}
    assert body["mcp_config_digest"] == mcp_config.mcp_config_digest()
    assert body["skills"] == [
        {"id": "triage", "version": "1.0.0", "description": "Triage things",
         "tools": ["a__search"], "requires": ["a"], "roles": ["admin", "auditor"]},
        {"id": "empty", "version": "2.0.0", "description": "Nobody holds",
         "tools": [], "requires": [], "roles": []},
    ]
    for secret in (_SECRET_URL, "other-host", _SECRET_ENV, "OTHER_ENV", _SECRET_HEADER,
                   _SECRET_TEXT, "s3cret-value"):
        assert secret not in response.text


def test_skills_with_mcp_off_is_an_empty_200(skills_on, monkeypatch):
    monkeypatch.setattr(settings, "MCP_ENABLED", False)

    response = client.get("/skills", headers=_ADMIN_HEADERS)

    assert response.status_code == 200
    assert response.json() == {"skills": [], "mcp_config_digest": None}


def test_skills_requires_stats_read(skills_on, monkeypatch):
    monkeypatch.setattr(settings, "RBAC_ENABLED", True)
    monkeypatch.setattr(authz, "ROLE_PERMISSIONS", {"user": {"mcp:connect"}})
    app.dependency_overrides[require_identity] = lambda: Identity("u", "user")
    try:
        response = client.get("/skills")
    finally:
        app.dependency_overrides.pop(require_identity, None)

    assert response.status_code == 403
    assert "stats:read" in response.json()["detail"]
