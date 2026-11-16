"""PRD-016 STORY-016: `GET /audit/actions` and the three action counts on `/stats`.

Covers PRD-016 Sections 4 (API), 9.1 and 10, and F11: the endpoint is scoped
exactly as `GET /audit` (`audit:read:all` reads every user's rows,
`audit:read:own` only the caller's, neither is a 403 naming `audit:read:own`),
`?limit=` is 1-500 with a default of 100, `?decision=` is `allow|flag|deny`,
the entry has exactly the Section 10 fields with `classifications` decoded to a
list of objects, and `/stats` reports `actions_denied`, `actions_flagged` and
`actions_allowed`.

Requesting `temp_db` makes these `db` tests: they run against the libSQL dev
server. If many of them error at fixture setup, restart the container
(`docker restart harness-libsql-dev`) before suspecting code.

PRD-017 STORY-013 adds `?audit_id=` (Section 10).
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import dataclasses
import json
from types import MappingProxyType
from typing import get_args

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db.database import (
    count_action_decisions,
    insert_action_decisions,
    insert_user,
)
from app.db.models import ACTION_DECISION_VALUES, ActionDecisionRow, User
from app.main import app
from app.routers import admin
from app.services.action_adapters import ToolCall
from app.services.action_audit import record
from app.services.action_config import BUILT_IN_POLICY, Rule
from app.services.action_policy import evaluate
from app.services.identity import Identity, hash_token

client = TestClient(app)

_ADMIN_HEADERS = {"Authorization": f"Bearer {settings.ADMIN_TOKEN}"}

# Section 10's example entry, key for key.
_SECTION_10_FIELDS = {
    "id",
    "timestamp",
    "audit_id",
    "user_id",
    "role",
    "tool_call_id",
    "tool_name",
    "operation_kind",
    "target_preview",
    "decision",
    "rule",
    "reason",
    "granted_by",
    "classifications",
    "policy_digest",
}


def _fail_if_called(*args, **kwargs):
    raise AssertionError("repository function should not have been called")


def _row(**overrides) -> ActionDecisionRow:
    """A fixed, valid row; ids come from insertion order."""
    fields = dict(
        timestamp="2026-11-20T14:02:11Z",
        audit_id=None,
        session_id=None,
        user_id="dev-1",
        role="user",
        tool_call_id="call_9",
        tool_name="query",
        operation_kind="sql",
        target_preview="DROP TABLE users",
        arguments_hash="h" * 64,
        arguments_preview='{"sql":"DROP TABLE users"}',
        decision="deny",
        rule="sql.ddl",
        reason="destructive SQL is not permitted: DROP",
        granted_by=None,
        classifications=json.dumps(
            [{"rule": "sql.ddl", "kind": "sql", "detail": "DROP"}]
        ),
        policy_digest="sha256:3f1c",
    )
    fields.update(overrides)
    return ActionDecisionRow(**fields)


def _user(user_id: str, role: str) -> dict:
    """Insert a user with token `<user_id>-token`; return its auth header."""
    token = f"{user_id}-token"
    insert_user(User(user_id=user_id, role=role, token_hash=hash_token(token)))
    return {"Authorization": f"Bearer {token}"}


def _entries(response) -> list:
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"entries"}
    return body["entries"]


# --- AC 1: scoping ------------------------------------------------------------


@pytest.mark.parametrize("who", ["auditor", "admin-token"])
def test_audit_read_all_sees_every_users_rows_newest_first(temp_db, who):
    ids = insert_action_decisions(
        [_row(user_id="a"), _row(user_id="b"), _row(user_id="a")]
    )
    headers = _ADMIN_HEADERS if who == "admin-token" else _user("reviewer", "auditor")

    entries = _entries(client.get("/audit/actions", headers=headers))

    assert [e["id"] for e in entries] == sorted(ids, reverse=True)
    assert {e["user_id"] for e in entries} == {"a", "b"}


def test_audit_read_own_sees_only_own_rows(temp_db):
    insert_action_decisions(
        [_row(user_id="ana"), _row(user_id="someone-else"), _row(user_id="ana")]
    )
    headers = _user("ana", "user")

    entries = _entries(client.get("/audit/actions", headers=headers))

    assert len(entries) == 2
    assert {e["user_id"] for e in entries} == {"ana"}


def test_identity_lacking_both_audit_permissions_returns_403_naming_own(temp_db):
    insert_action_decisions([_row()])
    headers = _user("outsider", "guest")

    response = client.get("/audit/actions", headers=headers)

    assert response.status_code == 403
    assert response.json() == {"detail": "Permission denied: audit:read:own"}
    # Matching `GET /audit` for the same caller (PRD-016 9.1).
    audit = client.get("/audit", headers=headers)
    assert audit.status_code == 403
    assert audit.json() == response.json()


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer wrong-token"}])
def test_missing_or_wrong_token_rejected_before_db_access(temp_db, monkeypatch, headers):
    monkeypatch.setattr("app.routers.admin.list_action_decisions", _fail_if_called)

    response = client.get("/audit/actions", headers=headers)

    assert response.status_code in (401, 403)


# --- AC 2: filters and validation --------------------------------------------


def test_decision_deny_limit_1_returns_one_deny_row(temp_db):
    ids = insert_action_decisions(
        [
            _row(decision="deny"),
            _row(decision="allow", rule="sql.read"),
            _row(decision="deny"),
            _row(decision="flag", rule="shell.unlisted"),
        ]
    )

    entries = _entries(
        client.get("/audit/actions?decision=deny&limit=1", headers=_ADMIN_HEADERS)
    )

    assert len(entries) == 1
    assert entries[0]["decision"] == "deny"
    assert entries[0]["id"] == ids[2]  # the newer deny
    assert set(entries[0]) == _SECTION_10_FIELDS


def test_decision_filter_combines_with_own_scope(temp_db):
    insert_action_decisions(
        [
            _row(user_id="ana", decision="flag"),
            _row(user_id="ana", decision="deny"),
            _row(user_id="other", decision="flag"),
        ]
    )
    headers = _user("ana", "user")

    entries = _entries(client.get("/audit/actions?decision=flag", headers=headers))

    assert [(e["user_id"], e["decision"]) for e in entries] == [("ana", "flag")]


@pytest.mark.parametrize("limit", ["0", "501", "-1", "x"])
def test_limit_out_of_range_is_422(temp_db, monkeypatch, limit):
    monkeypatch.setattr("app.routers.admin.list_action_decisions", _fail_if_called)

    response = client.get(f"/audit/actions?limit={limit}", headers=_ADMIN_HEADERS)

    assert response.status_code == 422


@pytest.mark.parametrize("limit", [1, 500])
def test_limit_bounds_are_accepted(temp_db, limit):
    insert_action_decisions([_row(), _row()])

    entries = _entries(
        client.get(f"/audit/actions?limit={limit}", headers=_ADMIN_HEADERS)
    )

    assert len(entries) == min(limit, 2)


@pytest.mark.parametrize("decision", ["block", "DENY", ""])
def test_unknown_decision_is_422(temp_db, monkeypatch, decision):
    # `""` is included on purpose: FastAPI passes an empty query value through
    # as `""` (not as missing), and `""` is not in the Literal.
    monkeypatch.setattr("app.routers.admin.list_action_decisions", _fail_if_called)

    response = client.get(
        f"/audit/actions?decision={decision}", headers=_ADMIN_HEADERS
    )

    assert response.status_code == 422


def test_default_limit_is_100(temp_db, monkeypatch):
    calls: list = []

    def recorder(**kwargs):
        calls.append(kwargs)
        return []

    monkeypatch.setattr("app.routers.admin.list_action_decisions", recorder)

    assert _entries(client.get("/audit/actions", headers=_ADMIN_HEADERS)) == []
    # PRD-017 STORY-013 (Section 10): the router now always passes audit_id;
    # None is no filter.
    assert calls == [
        {"limit": 100, "user_id": None, "decision": None, "audit_id": None}
    ]


def test_decision_literal_mirrors_the_db_vocabulary():
    assert set(get_args(admin.ActionDecisionFilter)) == set(ACTION_DECISION_VALUES)


# --- PRD-017 STORY-013: ?audit_id= (Section 10) ---


def test_audit_id_returns_only_that_requests_decisions_newest_first(temp_db):
    ids = insert_action_decisions(
        [
            _row(audit_id=41),
            _row(audit_id=41),
            _row(audit_id=42),
            _row(audit_id=None),
            _row(audit_id=41),
        ]
    )
    ids_41 = [ids[0], ids[1], ids[4]]

    entries = _entries(client.get("/audit/actions?audit_id=41", headers=_ADMIN_HEADERS))

    assert [e["id"] for e in entries] == sorted(ids_41, reverse=True)
    assert all(e["audit_id"] == 41 for e in entries)


def test_audit_id_combines_with_decision(temp_db):
    ids = insert_action_decisions(
        [
            _row(audit_id=41, decision="deny"),
            _row(audit_id=41, decision="allow", rule="sql.read"),
            _row(audit_id=42, decision="deny"),
        ]
    )

    entries = _entries(
        client.get("/audit/actions?audit_id=41&decision=deny", headers=_ADMIN_HEADERS)
    )

    assert [e["id"] for e in entries] == [ids[0]]


def test_audit_id_of_another_users_request_is_empty_under_own_scope(temp_db):
    ids = insert_action_decisions(
        [_row(user_id="other", audit_id=41), _row(user_id="ana", audit_id=42)]
    )
    headers = _user("ana", "user")

    other = client.get("/audit/actions?audit_id=41", headers=headers)
    assert other.status_code == 200
    assert other.json() == {"entries": []}
    mine = _entries(client.get("/audit/actions?audit_id=42", headers=headers))
    assert [e["id"] for e in mine] == [ids[1]]


def test_audit_id_without_either_audit_permission_is_403(temp_db):
    headers = _user("outsider", "guest")

    response = client.get("/audit/actions?audit_id=41", headers=headers)

    assert response.status_code == 403
    assert response.json() == {"detail": "Permission denied: audit:read:own"}


@pytest.mark.parametrize("audit_id", ["-1", "0", "x", "1.5", ""])
def test_audit_id_invalid_is_422(temp_db, monkeypatch, audit_id):
    monkeypatch.setattr("app.routers.admin.list_action_decisions", _fail_if_called)

    response = client.get(f"/audit/actions?audit_id={audit_id}", headers=_ADMIN_HEADERS)

    assert response.status_code == 422


def test_audit_id_is_passed_to_the_repository(temp_db, monkeypatch):
    calls: list = []

    def recorder(**kwargs):
        calls.append(kwargs)
        return []

    monkeypatch.setattr("app.routers.admin.list_action_decisions", recorder)

    assert _entries(client.get("/audit/actions?audit_id=41", headers=_ADMIN_HEADERS)) == []
    assert calls == [
        {"limit": 100, "user_id": None, "decision": None, "audit_id": 41}
    ]


# --- AC 3: entry shape --------------------------------------------------------


def test_entry_has_exactly_the_section_10_fields(temp_db):
    insert_action_decisions([_row(session_id="s-1", audit_id=7)])

    (entry,) = _entries(client.get("/audit/actions", headers=_ADMIN_HEADERS))

    assert set(entry) == _SECTION_10_FIELDS
    assert "arguments_preview" not in entry
    assert "arguments_hash" not in entry
    # Section 10's example omits it (orchestrator decision, STORY-016 plan Q1).
    assert "session_id" not in entry
    assert entry["audit_id"] == 7
    assert entry["classifications"] == [
        {"rule": "sql.ddl", "kind": "sql", "detail": "DROP"}
    ]


def test_reason_is_returned_as_stored(temp_db):
    insert_action_decisions([_row(reason="stored reason text")])

    (entry,) = _entries(client.get("/audit/actions", headers=_ADMIN_HEADERS))

    assert entry["reason"] == "stored reason text"


# `make release` is `shell.unlisted`; flag it, so the batch has all three
# outcomes (the tests/test_action_audit.py pattern).
_POLICY = dataclasses.replace(
    BUILT_IN_POLICY,
    rules=MappingProxyType(
        {**BUILT_IN_POLICY.rules, "shell.unlisted": Rule("flag", "action:shell:exec")}
    ),
)


def test_classifications_is_a_list_of_objects(temp_db):
    """T9: a real `evaluate()` -> `record()` -> `GET /audit/actions` round trip."""
    identity = Identity("u", "user")
    decisions = [
        evaluate(ToolCall(cid, name, json.dumps(args)), identity, _POLICY)
        for cid, name, args in [
            ("c1", "query", {"sql": "SELECT 1"}),
            ("c2", "bash", {"command": "make release"}),
            ("c3", "query", {"sql": "DROP TABLE users"}),
        ]
    ]
    assert [d.decision for d in decisions] == ["allow", "flag", "deny"]
    record(decisions, identity)

    entries = _entries(client.get("/audit/actions", headers=_ADMIN_HEADERS))

    assert [e["tool_call_id"] for e in entries] == ["c3", "c2", "c1"]
    for entry in entries:
        assert set(entry) == _SECTION_10_FIELDS
        assert isinstance(entry["classifications"], list)
        assert entry["classifications"]
        for c in entry["classifications"]:
            assert isinstance(c, dict)
            assert set(c) == {"rule", "kind", "detail"}
    deny = decisions[2]
    assert entries[0]["decision"] == deny.decision
    assert entries[0]["rule"] == deny.rule
    assert entries[0]["reason"] == deny.reason
    assert entries[0]["granted_by"] == deny.granted_by
    assert entries[0]["policy_digest"] == deny.policy_digest


def test_null_kind_classification_and_nullable_fields_pass_through(temp_db):
    insert_action_decisions(
        [
            _row(
                tool_name="mystery",
                operation_kind=None,
                target_preview=None,
                audit_id=None,
                rule="tool.unknown",
                classifications=json.dumps(
                    [{"rule": "tool.unknown", "kind": None, "detail": "mystery"}]
                ),
            )
        ]
    )

    (entry,) = _entries(client.get("/audit/actions", headers=_ADMIN_HEADERS))

    assert entry["operation_kind"] is None
    assert entry["target_preview"] is None
    assert entry["audit_id"] is None
    assert entry["granted_by"] is None
    assert entry["classifications"] == [
        {"rule": "tool.unknown", "kind": None, "detail": "mystery"}
    ]


# --- AC 4: /stats -------------------------------------------------------------


def test_stats_action_counts_are_zero_on_an_empty_table(temp_db):
    body = client.get("/stats", headers=_ADMIN_HEADERS).json()

    assert body["actions_denied"] == 0
    assert body["actions_flagged"] == 0
    assert body["actions_allowed"] == 0


def test_stats_reports_action_counts(temp_db):
    insert_action_decisions(
        [_row(decision="deny")] * 3
        + [_row(decision="flag")] * 2
        + [_row(decision="allow")]
    )

    response = client.get("/stats", headers=_ADMIN_HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert (body["actions_denied"], body["actions_flagged"], body["actions_allowed"]) == (
        3,
        2,
        1,
    )
    counts = count_action_decisions()
    assert body["actions_denied"] == counts["deny"]
    assert body["actions_flagged"] == counts["flag"]
    assert body["actions_allowed"] == counts["allow"]
    # The audit figures are untouched by action rows.
    assert body["total_queries"] == 0
    assert body["blocked_duplicates"] == 0
    assert body["blocked_suspicious"] == 0
    assert body["unique_users"] == 0
    assert body["success_rate"] == "0.0%"


def test_stats_rejected_before_action_counts_read(temp_db, monkeypatch):
    monkeypatch.setattr("app.routers.admin.count_action_decisions", _fail_if_called)
    monkeypatch.setattr("app.routers.admin.summary_snapshot", _fail_if_called)

    response = client.get("/stats")

    assert response.status_code in (401, 403)
