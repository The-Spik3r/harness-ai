"""PRD-023 STORY-013: the `tools/call` path (`mcp_gateway.call`, M3-M9; D8, D9, D13-D15, T6, T7, T9, T10, T16).

Two groups. The tests that need no storage replace `action_audit.record` /
`record_outcome` and `usage_limits.admit` with recorders and run the real stub
MCP server (a subprocess on a runtime port) behind a bare `FastAPI` app with
`mcp_router.router`; they run under `-m "not db"`. The `*_db` tests use
`temp_db` and read the real `action_decisions` rows. One `TestClient` context is
one event loop, so the upstream session survives between requests; the fixture
closes every session before it ends.
"""

import asyncio
import hashlib
import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import settings
from app.db import database
from app.db.errors import StorageUnavailableError
from app.models import mcp_schemas
from app.routers import mcp as mcp_router
from app.services import (
    action_audit,
    action_config,
    action_policy,
    authz,
    mcp_config,
    mcp_gateway,
    mcp_upstream,
    strict_json,
    usage_limits,
)
from app.services.identity import Identity
from app.services.mcp_config import McpAuth, McpConfig, McpServer, Skill
from app.services.mcp_upstream import CallOutcome
from app.services.tool_release import DENIAL_NOTE_TEMPLATE

_SKILL = Skill(
    "open-pull-request", "1.0.0", "d", "i",
    (
        "stub__query", "stub__push_files", "stub__create_pull_request", "stub__slow",
        "stub__nope", "stub__poisoned",
    ),
    (),
)
_POLICY = """\
mcp_tools:
  stub:
    query: {kind: sql, target: sql}
    push_files: {kind: fs_write, target: "files[].path"}
mcp_opaque_tools:
  stub:
    create_pull_request: flag
    slow: allow
"""
_DDL = {"sql": "DROP TABLE accounts"}
_WORKFLOW = {
    "branch": "b",
    "files": [{"path": ".github/workflows/ci.yml", "content": "x"}],
    "message": "m",
}
_IDENTITIES = {
    "dev": Identity(user_id="u-dev", role="dev"),
    "dba": Identity(user_id="u-dba", role="dba"),
    "user": Identity(user_id="u-user", role="user"),
}
_UNKNOWN = {"code": -32602, "message": mcp_gateway.UNKNOWN_TOOL_MESSAGE}


def _server(url, timeout=30):
    return McpServer("stub", url, True, McpAuth(type="none"), timeout, 1_048_576)


def _configure(monkeypatch, url, timeout=30, skills=(_SKILL,)):
    monkeypatch.setattr(
        mcp_config, "_config", McpConfig(servers={"stub": _server(url, timeout)}, skills=tuple(skills))
    )


@pytest.fixture(autouse=True)
def _fresh(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "RBAC_ENABLED", True)
    monkeypatch.setattr(settings, "USAGE_LIMITS_ENABLED", True)
    monkeypatch.setattr(settings, "MCP_ALLOWED_ORIGINS", "")
    monkeypatch.setattr(
        authz, "ROLE_PERMISSIONS",
        {
            "dev": {"skill:open-pull-request", "mcp:connect"},
            "dba": {"skill:open-pull-request", "mcp:connect", authz.PERMISSION_ACTION_SQL_DDL},
            "user": {"mcp:connect"},
        },
    )
    policy_file = tmp_path / "action_policy.yaml"
    policy_file.write_text(_POLICY, encoding="utf-8")
    monkeypatch.setattr(action_config, "_policy", action_config._policy)  # restored at teardown
    monkeypatch.setattr(settings, "ACTION_POLICY_FILE", str(policy_file))
    action_config.load()
    monkeypatch.setattr(mcp_upstream, "_state", None)
    mcp_upstream.invalidate_tools_cache()
    mcp_gateway._unlisted_logged.clear()
    monkeypatch.setattr("app.middleware.auth.resolve", _IDENTITIES.get)
    yield
    mcp_upstream.invalidate_tools_cache()
    mcp_gateway._unlisted_logged.clear()


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(mcp_router.router)
    with TestClient(app) as test_client:
        try:
            yield test_client
        finally:
            test_client.portal.call(mcp_upstream.aclose_all)


class Spy:
    """What the call path did, in order, with the arguments it did it with."""

    def __init__(self):
        self.order = []
        self.admit_args = []
        self.admit_result = usage_limits.Admission(day="2026-11-23")
        self.admit_raises = None
        self.decisions = []
        self.records = []
        self.record_raises = None
        self.outcomes = []
        self.outcome_raises = None
        self.engine_calls = []
        self.call_tool_args = []
        self.fake_call_tool = None
        self.parsed = []


@pytest.fixture
def spy(monkeypatch):
    s = Spy()

    def admit(identity, charges_budget):
        s.order.append("admit")
        s.admit_args.append((identity, charges_budget))
        if s.admit_raises is not None:
            raise s.admit_raises
        return s.admit_result

    def record(decisions, identity, *args, mcp=None, **kwargs):
        s.order.append("record")
        if s.record_raises is not None:
            raise s.record_raises
        s.decisions.extend(decisions)
        s.records.append((identity, mcp, args, kwargs))
        return [42]

    def record_outcome(row_id, outcome, duration_ms, result_bytes, result_hash, result_flags, *, user_id):
        s.order.append("outcome")
        if s.outcome_raises is not None:
            raise s.outcome_raises
        s.outcomes.append((row_id, outcome, duration_ms, result_bytes, result_hash, tuple(result_flags), user_id))

    real_catalogue = mcp_gateway.visible_catalogue

    async def catalogue(identity):
        s.order.append("catalogue")
        return await real_catalogue(identity)

    real_evaluate = action_policy.evaluate

    def evaluate(call, identity, *args, **kwargs):
        s.order.append("evaluate")
        s.engine_calls.append((call, kwargs.get("surface")))
        return real_evaluate(call, identity, *args, **kwargs)

    real_call_tool = mcp_upstream.call_tool

    async def call_tool(server, user_id, tool, arguments=None, **kwargs):
        s.order.append("call_tool")
        s.call_tool_args.append((server, user_id, tool, arguments))
        if s.fake_call_tool is not None:
            return s.fake_call_tool
        return await real_call_tool(server, user_id, tool, arguments, **kwargs)

    real_loads = strict_json.loads

    def loads(text, *args, **kwargs):
        parsed = real_loads(text, *args, **kwargs)
        s.parsed.append(parsed)
        return parsed

    monkeypatch.setattr(usage_limits, "admit", admit)
    monkeypatch.setattr(action_audit, "record", record)
    monkeypatch.setattr(action_audit, "record_outcome", record_outcome)
    monkeypatch.setattr(mcp_gateway, "visible_catalogue", catalogue)
    monkeypatch.setattr(action_policy, "evaluate", evaluate)
    monkeypatch.setattr(mcp_upstream, "call_tool", call_tool)
    monkeypatch.setattr(strict_json, "loads", loads)
    return s


def _post(client, token, name, arguments=None, *, id_=1, params=None, absent=False):
    if params is None:
        params = {"name": name}
        if not absent:
            params["arguments"] = arguments if arguments is not None else {}
    return client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": id_, "method": "tools/call", "params": params},
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )


def _text(response):
    return response.json()["result"]["content"][0]["text"]


def _error(response):
    assert response.status_code == 200
    return response.json()["error"]


# --- AC1: the engine decides, a deny is a result not an error ---------------------


def test_ddl_denied_without_grant_allowed_for_dba(mcp_stub, monkeypatch, client, spy):
    _configure(monkeypatch, mcp_stub.url)

    denied = _post(client, "dev", "stub__query", _DDL)
    assert denied.status_code == 200
    result = denied.json()["result"]
    assert result["isError"] is True
    decision = spy.decisions[-1]
    assert (decision.decision, decision.rule) == ("deny", "sql.ddl")
    assert result["content"][0]["text"] == DENIAL_NOTE_TEMPLATE.format(
        name="stub__query", id="1", reason=decision.reason
    )
    assert mcp_stub.calls("query") == 0
    assert spy.outcomes == []  # never forwarded: outcome stays NULL
    assert "call_tool" not in spy.order

    allowed = _post(client, "dba", "stub__query", _DDL, id_=2)
    assert allowed.json()["result"]["isError"] is False
    assert "rows: 1" in _text(allowed)
    assert mcp_stub.calls("query") == 1
    assert (spy.decisions[-1].decision, spy.decisions[-1].granted_by) == ("allow", authz.PERMISSION_ACTION_SQL_DDL)
    assert spy.outcomes[-1][1] == "ok"
    mcp = spy.records[-1][1]
    assert (mcp.surface, mcp.mcp_server, mcp.jsonrpc_id) == ("mcp", "stub", 2)


# --- AC2: not callable is one recorded -32602; M3 faults are unrecorded ------------


def test_unresolvable_names_share_one_recorded_32602(mcp_stub, monkeypatch, client, spy):
    _configure(monkeypatch, mcp_stub.url)
    names = {
        "stub__create_branch": "stub",  # exists upstream, in no held skill: hidden
        "stub__nope": "stub",  # in a held skill, not listed upstream
        "stub__poisoned": "stub",  # listed, withheld by injection inspection
        "plain": None,  # no `__`
        "other__query": None,  # prefix is not a configured server
    }
    for name, expected_server in names.items():
        response = _post(client, "dev", name, {"branch": "x"})
        assert _error(response) == _UNKNOWN, name
        decision, (_, mcp, _, _) = spy.decisions[-1], spy.records[-1]
        assert (decision.decision, decision.rule) == ("deny", "tool.not_in_skill"), name
        assert mcp.mcp_server == expected_server, name
    assert len(spy.decisions) == len(names)
    assert mcp_stub.stats()["calls"] == {}
    assert spy.outcomes == [] and "call_tool" not in spy.order


def test_a_user_with_no_skill_sees_every_tool_as_unknown(mcp_stub, monkeypatch, client, spy):
    _configure(monkeypatch, mcp_stub.url)
    assert _error(_post(client, "user", "stub__query", _DDL)) == _UNKNOWN
    assert spy.decisions[-1].rule == "tool.not_in_skill"
    assert mcp_stub.calls("query") == 0


@pytest.mark.parametrize("bad_name", [5, None, "", ["a"], {"a": 1}])
def test_a_non_string_name_is_32602_and_unrecorded(mcp_stub, monkeypatch, client, spy, bad_name):
    _configure(monkeypatch, mcp_stub.url)
    error = _error(_post(client, "dev", None, params={"name": bad_name, "arguments": {}}))
    assert error["code"] == -32602
    assert error["message"] == mcp_gateway.INVALID_NAME_MESSAGE
    assert spy.order == []  # no usage count, no row, no upstream


@pytest.mark.parametrize("bad_arguments", [[1], "x", None, 3, True])
def test_non_object_arguments_are_32602_and_unrecorded(mcp_stub, monkeypatch, client, spy, bad_arguments):
    _configure(monkeypatch, mcp_stub.url)
    response = _post(client, "dev", None, params={"name": "stub__query", "arguments": bad_arguments})
    assert _error(response) == {"code": -32602, "message": mcp_gateway.INVALID_ARGUMENTS_MESSAGE}
    assert spy.order == []


def test_absent_arguments_forward_an_empty_object(mcp_stub, monkeypatch, client, spy):
    _configure(monkeypatch, mcp_stub.url)
    spy.fake_call_tool = CallOutcome("ok", content=[{"type": "text", "text": "fine"}])
    response = _post(client, "dev", "stub__slow", absent=True)
    assert response.json()["result"] == {"content": [{"type": "text", "text": "fine"}], "isError": False}
    assert spy.call_tool_args == [("stub", "u-dev", "slow", {})]
    assert spy.engine_calls[-1][0].arguments == "{}"


# --- AC3: evidence before effect; the outcome is best effort ----------------------


def test_record_failure_is_32603_and_not_forwarded(mcp_stub, monkeypatch, client, spy, caplog):
    _configure(monkeypatch, mcp_stub.url)
    spy.record_raises = StorageUnavailableError("db down at postgres://u:secret@h/d", 5)
    response = _post(client, "dba", "stub__query", _DDL)
    assert _error(response) == {"code": -32603, "message": mcp_gateway.RECORD_FAILED_MESSAGE}
    assert "call_tool" not in spy.order
    assert mcp_stub.stats()["calls"] == {}
    assert "secret" not in caplog.text and "secret" not in response.text


def test_a_record_that_returns_no_row_id_is_32603(mcp_stub, monkeypatch, client, spy):
    _configure(monkeypatch, mcp_stub.url)
    monkeypatch.setattr(action_audit, "record", lambda *a, **k: [])
    assert _error(_post(client, "dba", "stub__query", _DDL))["code"] == -32603
    assert mcp_stub.stats()["calls"] == {}


def test_record_outcome_failure_still_returns_the_result(mcp_stub, monkeypatch, client, spy, caplog):
    _configure(monkeypatch, mcp_stub.url)
    spy.outcome_raises = RuntimeError("boom")
    response = _post(client, "dba", "stub__query", _DDL)
    assert response.json()["result"]["isError"] is False
    assert "rows: 1" in _text(response)
    assert [r for r in caplog.records if r.levelno == logging.ERROR and "outcome not recorded" in r.getMessage()]


_REAL_RECORD_OUTCOME = action_audit.record_outcome  # the `spy` fixture replaces the attribute


def test_the_real_record_outcome_swallows_a_failed_update(mcp_stub, monkeypatch, client, spy, caplog):
    _configure(monkeypatch, mcp_stub.url)

    def update_fails(*args, **kwargs):
        raise RuntimeError("db gone")

    monkeypatch.setattr(action_audit, "record_outcome", _REAL_RECORD_OUTCOME)
    monkeypatch.setattr(action_audit, "update_action_outcome", update_fails)
    response = _post(client, "dba", "stub__query", _DDL)
    assert "rows: 1" in _text(response)
    errors = [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]
    assert any("mcp outcome not recorded: user_id=u-dba row_id=42: RuntimeError" in m for m in errors)


# --- AC4: the usage gate ------------------------------------------------------------


def _refusal(seconds=120):
    resets = (datetime.now(timezone.utc) + timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return usage_limits.Admission(
        day="2026-11-23",
        refusal=usage_limits.UsageRefusal(limit="requests", maximum=5, actual=6, resets_at=resets),
    )


def test_usage_refusal_is_429_with_retry_after_and_no_row(mcp_stub, monkeypatch, client, spy):
    _configure(monkeypatch, mcp_stub.url)
    spy.admit_result = _refusal(120)
    response = _post(client, "dba", "stub__query", _DDL)
    assert response.status_code == 429
    body = response.json()
    assert body["id"] == 1 and body["error"]["code"] == mcp_schemas.USAGE_LIMITED == -32000
    assert 100 <= int(response.headers["Retry-After"]) <= 121
    assert spy.order == ["admit"]  # before the catalogue, the engine, the row and the forward
    identity, charges_budget = spy.admit_args[0]
    assert identity.user_id == "u-dba" and charges_budget is False
    assert mcp_stub.stats()["calls"] == {}


def test_a_usage_storage_failure_fails_closed_as_32603(mcp_stub, monkeypatch, client, spy):
    _configure(monkeypatch, mcp_stub.url)
    spy.admit_raises = usage_limits.UsageLimitError("db down")
    response = _post(client, "dba", "stub__query", _DDL)
    assert _error(response) == {"code": -32603, "message": mcp_gateway.USAGE_UNCHECKED_MESSAGE}
    assert spy.order == ["admit"]


def test_usage_limits_off_skips_the_admit(mcp_stub, monkeypatch, client, spy):
    _configure(monkeypatch, mcp_stub.url)
    monkeypatch.setattr(settings, "USAGE_LIMITS_ENABLED", False)
    _post(client, "dba", "stub__query", _DDL)
    assert "admit" not in spy.order and spy.outcomes[-1][1] == "ok"


def test_the_call_path_order_and_at_most_three_storage_steps(mcp_stub, monkeypatch, client, spy):
    _configure(monkeypatch, mcp_stub.url)
    _post(client, "dba", "stub__query", _DDL)
    assert spy.order == ["admit", "catalogue", "evaluate", "record", "call_tool", "outcome"]
    assert [s for s in spy.order if s in ("admit", "record", "outcome")] == ["admit", "record", "outcome"]


# --- AC5: one parse, forwarding, failure texts --------------------------------------


def test_one_parse_forwarded_object_is_parsed_object(mcp_stub, monkeypatch, client, spy):
    _configure(monkeypatch, mcp_stub.url)
    arguments = {"sql": "SELECT 1", "b": 1, "a": [3, 2, {"z": 1, "y": 2}], "n": "ñ"}
    _post(client, "dba", "stub__query", arguments)
    parsed_arguments = spy.parsed[-1]["params"]["arguments"]
    assert spy.call_tool_args[-1][3] is parsed_arguments
    engine_call, surface = spy.engine_calls[-1]
    canonical = action_audit.canonical_json(parsed_arguments)
    assert engine_call.arguments == canonical
    assert engine_call.name == "query"  # the BARE tool: the surface's `visible` holds bare names
    assert (surface.server, "query" in surface.visible) == ("stub", True)
    # The row's hash comes from the same text, whatever order the client sent the keys in.
    shuffled = dict(reversed(list(arguments.items())))
    _post(client, "dba", "stub__query", shuffled, id_=2)
    first, second = (rec[1].arguments_canonical_hash for rec in spy.records[-2:])
    assert first == second == action_audit.arguments_canonical_hash(arguments)
    assert first == hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def test_the_row_carries_skills_digest_and_id(mcp_stub, monkeypatch, client, spy):
    _configure(monkeypatch, mcp_stub.url)
    _post(client, "dba", "stub__query", _DDL, id_="req-9")
    mcp = spy.records[-1][1]
    assert mcp.skills == ("open-pull-request@1.0.0",)
    assert mcp.mcp_config_digest == mcp_config.mcp_config_digest()
    assert mcp.jsonrpc_id == "req-9"
    assert (mcp.audit_id, mcp.linked_decision_id) == (None, None)  # STORY-016 fills correlation
    _post(client, "dba", "stub__create_branch", {"branch": "x"}, id_=3)
    assert spy.records[-1][1].skills == ()  # a hidden tool is in no held skill


def test_slow_timeout_text_and_no_retry(mcp_stub, monkeypatch, client, spy):
    _configure(monkeypatch, mcp_stub.url, timeout=2)
    started = time.monotonic()
    response = _post(client, "dev", "stub__slow", {"seconds": 20}, id_=7)
    assert time.monotonic() - started < 30
    result = response.json()["result"]
    assert result["isError"] is True
    assert result["content"][0]["text"] == (
        "[harness] stub__slow (7) timed out after 2s; the call may have run"
    )
    assert spy.outcomes[-1][1] == "timeout"
    deadline = time.monotonic() + 10
    while mcp_stub.calls("slow") < 1 and time.monotonic() < deadline:
        time.sleep(0.1)
    assert mcp_stub.calls("slow") == 1
    assert [s for s in spy.order if s == "call_tool"] == ["call_tool"]  # never replayed (T10)


def test_upstream_error_text_hides_detail(mcp_stub, monkeypatch, client, spy):
    _configure(monkeypatch, mcp_stub.url)
    sentinel = "http://sentinel.invalid/mcp?token=hunter2"
    spy.fake_call_tool = CallOutcome("upstream_error", detail=f"slow on stub: {sentinel}; it may have run")
    response = _post(client, "dev", "stub__slow", {"seconds": 1}, id_=4)
    assert response.json()["result"] == {
        "content": [{"type": "text", "text": "[harness] stub__slow (4) failed on server stub; the call may have run"}],
        "isError": True,
    }
    assert sentinel not in response.text
    assert spy.outcomes[-1][1] == "upstream_error"
    assert sentinel not in repr(spy.outcomes) and sentinel not in repr(spy.records)


def test_a_result_over_the_transport_cap_is_result_too_large(mcp_stub, monkeypatch, client, spy):
    # PRD-023 T15 (STORY-021 manual run): mcp_upstream reports `too_large` when the result exceeded the
    # SDK's SSE event cap, which sits above `max_result_bytes`. The call ran; nothing was measured.
    _configure(monkeypatch, mcp_stub.url)
    spy.fake_call_tool = CallOutcome("too_large", detail="huge on stub: result over the transport cap; the call ran")
    response = _post(client, "dev", "stub__slow", {"seconds": 1}, id_=5)
    cap = mcp_config.get_config().servers["stub"].max_result_bytes
    assert response.json()["result"] == {
        "content": [{"type": "text", "text": f"[harness] the result of stub__slow (5) exceeded {cap} bytes and was not returned; the call ran"}],
        "isError": True,
    }
    row_id, outcome, _ms, size, digest, flags, _user = spy.outcomes[-1]
    assert (outcome, size, digest, flags) == ("result_too_large", None, None, ())


def test_an_upstream_is_error_result_is_a_tool_error_returned_as_is(mcp_stub, monkeypatch, client, spy):
    _configure(monkeypatch, mcp_stub.url)
    content = [{"type": "text", "text": "the tool said no"}]
    spy.fake_call_tool = CallOutcome("error", is_error=True, content=content, structured={"code": 7})
    response = _post(client, "dev", "stub__slow", {"seconds": 1})
    assert response.json()["result"] == {"content": content, "isError": True, "structuredContent": {"code": 7}}
    assert spy.outcomes[-1][1] == "tool_error"


def test_the_outcome_row_keeps_size_and_hash_not_the_result(mcp_stub, monkeypatch, client, spy):
    _configure(monkeypatch, mcp_stub.url)
    response = _post(client, "dba", "stub__query", _DDL)
    row_id, outcome, duration_ms, size, digest, flags, user_id = spy.outcomes[-1]
    assert (row_id, outcome, flags, user_id) == (42, "ok", (), "u-dba")
    assert duration_ms >= 0
    # PRD-023 STORY-014: `result_digest` takes the canonical text (one serialization).
    assert (size, digest) == mcp_gateway.result_digest(
        action_audit.canonical_json(response.json()["result"])
    )
    assert size == len(action_audit.canonical_json(response.json()["result"]).encode("utf-8"))


def test_push_files_workflow_path_is_denied_by_the_engine(mcp_stub, monkeypatch, client, spy):
    _configure(monkeypatch, mcp_stub.url)
    response = _post(client, "dba", "stub__push_files", _WORKFLOW)
    assert response.json()["result"]["isError"] is True
    assert (spy.decisions[-1].decision, spy.decisions[-1].rule) == ("deny", "fs.write_protected")
    assert mcp_stub.calls("push_files") == 0


def test_create_pull_request_is_forwarded_and_flagged(mcp_stub, monkeypatch, client, spy):
    _configure(monkeypatch, mcp_stub.url)
    response = _post(client, "dev", "stub__create_pull_request", {"title": "t", "head": "h", "base": "b"})
    assert response.json()["result"]["isError"] is False
    assert (spy.decisions[-1].decision, spy.decisions[-1].rule) == ("flag", "tool.opaque")
    assert mcp_stub.calls("create_pull_request") == 1
    assert spy.outcomes[-1][1] == "ok"


def test_logs_carry_no_arguments_or_results(mcp_stub, monkeypatch, client, spy, caplog):
    caplog.set_level(logging.INFO)
    _configure(monkeypatch, mcp_stub.url)
    _post(client, "dba", "stub__query", {"sql": "DROP TABLE secret_table_name"})
    assert "secret_table_name" not in caplog.text
    assert "rows: 1" not in caplog.text
    assert [r for r in caplog.records if r.getMessage().startswith("mcp tools/call: user=u-dba")]


def test_the_handler_is_a_thin_adapter_over_the_gateway():
    import inspect

    assert "mcp_gateway.call(" in inspect.getsource(mcp_router.handle_tools_call)
    assert not hasattr(mcp_router, "mcp_upstream")


def test_the_gateway_never_imports_the_sdk_after_this_story():
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(mcp_gateway))
    imported = {
        (node.module or "") if isinstance(node, ast.ImportFrom) else alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in (node.names if isinstance(node, ast.Import) else [None])
    }
    assert not [n for n in imported if n == "mcp" or n.startswith("mcp.")]


def test_no_task_is_left_after_a_call(mcp_stub, monkeypatch, client, spy):
    _configure(monkeypatch, mcp_stub.url)
    _post(client, "dba", "stub__query", _DDL)

    async def drained():
        await mcp_upstream.aclose_all()
        others = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        if others:
            await asyncio.wait(others, timeout=5)  # SDK/httpx helpers may still be finishing
        return [t for t in asyncio.all_tasks() if t is not asyncio.current_task() and not t.done()]

    pending = client.portal.call(drained)
    # The TestClient portal's own loop machinery may hold a task; none may be a session owner.
    assert not [t for t in pending if "owner" in repr(t).lower() or "mcp_upstream" in repr(t)]


# --- the same scenarios against the real rows (CI: `db`) ----------------------------


def _rows():
    with database.get_connection() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM action_decisions ORDER BY id").fetchall()]


@pytest.fixture
def real_rows(temp_db, monkeypatch):
    monkeypatch.setattr(
        usage_limits, "admit", lambda identity, charges_budget: usage_limits.Admission(day="2026-11-23")
    )
    return temp_db


def test_ddl_deny_and_allow_write_rows_before_the_forward_db(mcp_stub, monkeypatch, client, real_rows):
    _configure(monkeypatch, mcp_stub.url)
    _post(client, "dev", "stub__query", _DDL)
    assert mcp_stub.calls("query") == 0
    (denied,) = _rows()
    assert (denied["surface"], denied["decision"], denied["rule"]) == ("mcp", "deny", "sql.ddl")
    assert denied["outcome"] is None and denied["mcp_server"] == "stub"
    assert json.loads(denied["skills"]) == ["open-pull-request@1.0.0"]
    assert denied["tool_call_id"] == "mcp:1"
    assert denied["arguments_canonical_hash"] == action_audit.arguments_canonical_hash(_DDL)

    response = _post(client, "dba", "stub__query", _DDL, id_=2)
    assert mcp_stub.calls("query") == 1
    allowed = _rows()[-1]
    assert (allowed["decision"], allowed["outcome"]) == ("allow", "ok")
    assert allowed["duration_ms"] is not None and allowed["result_flags"] == "[]"
    # PRD-023 STORY-014: `result_digest` takes the canonical text.
    assert (allowed["result_bytes"], allowed["result_hash"]) == mcp_gateway.result_digest(
        action_audit.canonical_json(response.json()["result"])
    )
    assert allowed["mcp_config_digest"] == mcp_config.mcp_config_digest()


def test_unresolvable_names_are_rows_with_a_null_server_for_an_unconfigured_prefix_db(
    mcp_stub, monkeypatch, client, real_rows
):
    _configure(monkeypatch, mcp_stub.url)
    for name in ("stub__create_branch", "other__query", "plain"):
        assert _error(_post(client, "dev", name, {"branch": "x"})) == _UNKNOWN
    rows = _rows()
    assert [r["rule"] for r in rows] == ["tool.not_in_skill"] * 3
    assert [r["mcp_server"] for r in rows] == ["stub", None, None]
    assert all(r["outcome"] is None for r in rows)
    assert mcp_stub.stats()["calls"] == {}


def test_a_429_writes_no_row_db(mcp_stub, monkeypatch, client, real_rows):
    _configure(monkeypatch, mcp_stub.url)
    monkeypatch.setattr(usage_limits, "admit", lambda identity, charges_budget: _refusal(60))
    assert _post(client, "dba", "stub__query", _DDL).status_code == 429
    assert _rows() == []


def test_a_failed_outcome_update_leaves_outcome_null_db(mcp_stub, monkeypatch, client, real_rows, caplog):
    _configure(monkeypatch, mcp_stub.url)

    def update_fails(*args, **kwargs):
        raise RuntimeError("db gone")

    monkeypatch.setattr(action_audit, "update_action_outcome", update_fails)
    response = _post(client, "dba", "stub__query", _DDL)
    assert "rows: 1" in _text(response)
    (row,) = _rows()
    assert row["decision"] == "allow" and row["outcome"] is None
    assert [r for r in caplog.records if r.levelno == logging.ERROR and "outcome not recorded" in r.getMessage()]


def test_timeout_and_workflow_deny_rows_db(mcp_stub, monkeypatch, client, real_rows):
    _configure(monkeypatch, mcp_stub.url, timeout=2)
    _post(client, "dev", "stub__slow", {"seconds": 20}, id_=5)
    _post(client, "dba", "stub__push_files", _WORKFLOW, id_=6)
    timed_out, workflow = _rows()
    assert (timed_out["outcome"], timed_out["decision"]) == ("timeout", "allow")
    assert (workflow["rule"], workflow["outcome"]) == ("fs.write_protected", None)
