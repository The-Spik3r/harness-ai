"""PRD-023 STORY-012: `tools/list` visibility and catalogue inspection (`app/services/mcp_gateway.py`).

No database, no Docker. The stub tests run the STORY-009 stub subprocess on a
runtime port; the unit tests replace `mcp_upstream.list_tools` with a fake. The
repo has no pytest-asyncio, so each test drives one bounded `asyncio.run(...)`
and always closes every upstream session in `finally`.
"""

import ast
import asyncio
import hashlib
import inspect
import logging
import os
import time
from pathlib import Path

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import settings
from app.db import database
from app.routers import mcp as mcp_router
from app.services import action_audit, authz, mcp_config, mcp_gateway, mcp_upstream
from app.services.identity import Identity
from app.services.mcp_config import McpAuth, McpConfig, McpServer, Skill
from app.services.mcp_upstream import McpUpstreamError, UpstreamTool
from scripts.stub_mcp_server import INJECTION_PHRASE

_BOUND = 60
_PR_TOOLS = ("github__create_branch", "github__create_pull_request", "github__push_files")
_PR_SKILL = Skill(
    "open-pull-request", "1.0.0", "Open a PR", "Do it.",
    ("github__create_branch", "github__push_files", "github__create_pull_request"), (),
)
_DEV = Identity(user_id="u-dev", role="dev")
_USER = Identity(user_id="u-user", role="user")


def _go(coro_factory, bound=_BOUND):
    async def main():
        try:
            return await asyncio.wait_for(coro_factory(), bound)
        finally:
            await mcp_upstream.aclose_all()

    return asyncio.run(main())


def _server(sid, url="http://127.0.0.1:9/mcp", timeout=30):
    return McpServer(sid, url, True, McpAuth(type="none"), timeout, 1_048_576)


def _cfg(monkeypatch, servers, skills):
    monkeypatch.setattr(
        mcp_config, "_config", McpConfig(servers={s.id: s for s in servers}, skills=tuple(skills))
    )


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    monkeypatch.setattr(settings, "RBAC_ENABLED", True)
    monkeypatch.setattr(
        authz, "ROLE_PERMISSIONS",
        {"dev": {"skill:open-pull-request", "skill:s", "mcp:connect"}, "user": {"mcp:connect"}},
    )
    monkeypatch.setattr(mcp_upstream, "_state", None)
    monkeypatch.setattr(mcp_gateway, "_now", time.monotonic)
    mcp_upstream.invalidate_tools_cache()
    mcp_gateway._unlisted_logged.clear()
    yield
    mcp_upstream.invalidate_tools_cache()
    mcp_gateway._unlisted_logged.clear()


def _fake_upstream(monkeypatch, by_server):
    """`by_server`: server id -> tuple of UpstreamTool, or an Exception to raise."""

    async def fake(server_id, user_id):
        value = by_server[server_id]
        if isinstance(value, BaseException):
            raise value
        return value

    monkeypatch.setattr(mcp_upstream, "list_tools", fake)


def _skill(*tools):
    return Skill("s", "1.0.0", "d", "i", tuple(tools), ())


def _one_tool(monkeypatch, tool):
    _cfg(monkeypatch, [_server("g")], [_skill(f"g__{tool.name}")])
    _fake_upstream(monkeypatch, {"g": (tool,)})
    return _go(lambda: mcp_gateway.visible_catalogue(_DEV))


# --- AC1: held skills decide what is listed --------------------------------------


def test_held_skill_lists_exactly_its_tools_sorted(mcp_stub, monkeypatch):
    _cfg(monkeypatch, [_server("github", mcp_stub.url)], [_PR_SKILL])

    async def body():
        cat = await mcp_gateway.visible_catalogue(_DEV)
        upstream = {t.name: t for t in await mcp_upstream.list_tools("github", "u")}
        return cat, upstream

    cat, upstream = _go(body)

    assert [t["name"] for t in cat.tools] == list(_PR_TOOLS)
    for entry in cat.tools:
        src = upstream[entry["name"].split("__", 1)[1]]
        assert entry["description"] == src.description
        assert entry["inputSchema"] == src.input_schema
        for key, value in (("title", src.title), ("outputSchema", src.output_schema),
                           ("annotations", src.annotations)):
            assert (key in entry) == (value is not None)
        assert "nextCursor" not in entry
    assert cat.callable == {"github": frozenset({"create_branch", "push_files", "create_pull_request"})}


def test_plain_user_and_rbac_off_list_nothing(mcp_stub, monkeypatch):
    _cfg(monkeypatch, [_server("github", mcp_stub.url)], [_PR_SKILL])
    assert _go(lambda: mcp_gateway.visible_catalogue(_USER)) == mcp_gateway.Catalogue()
    monkeypatch.setattr(settings, "RBAC_ENABLED", False)
    monkeypatch.setattr(authz, "ROLE_PERMISSIONS", {"user": {"mcp:connect"}, "dev": {"mcp:connect"}})
    cat = _go(lambda: mcp_gateway.visible_catalogue(_DEV))
    assert cat.tools == () and dict(cat.callable) == {}


def test_order_does_not_depend_on_config_order(monkeypatch):
    tools = tuple(UpstreamTool(n, "d", {"type": "object"}) for n in ("b", "a", "c"))
    _cfg(monkeypatch, [_server("g")], [_skill("g__c", "g__a", "g__b")])
    _fake_upstream(monkeypatch, {"g": tools})
    forward = _go(lambda: mcp_gateway.visible_catalogue(_DEV))
    _cfg(monkeypatch, [_server("g")], [_skill("g__b", "g__c", "g__a")])
    _fake_upstream(monkeypatch, {"g": tuple(reversed(tools))})
    backward = _go(lambda: mcp_gateway.visible_catalogue(_DEV))
    assert forward.tools == backward.tools
    assert [t["name"] for t in forward.tools] == ["g__a", "g__b", "g__c"]


def test_optional_keys_and_x_mcp_header_pass_through(monkeypatch):
    schema = {"type": "object", "properties": {"r": {"type": "string", "x-mcp-header": "Region"}}}
    tool = UpstreamTool("t", "d", schema, title="T", annotations={"readOnlyHint": True},
                        output_schema={"type": "object"})
    entry = _one_tool(monkeypatch, tool).tools[0]
    assert entry == {
        "name": "g__t", "description": "d", "inputSchema": schema, "title": "T",
        "outputSchema": {"type": "object"}, "annotations": {"readOnlyHint": True},
    }
    assert set(_one_tool(monkeypatch, UpstreamTool("t", "d", {"type": "object"})).tools[0]) == {
        "name", "description", "inputSchema"
    }


# --- AC2: inspection --------------------------------------------------------------


def test_poisoned_tool_is_withheld_from_the_stub_catalogue(mcp_stub, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    skill = _skill("github__poisoned", "github__query")
    _cfg(monkeypatch, [_server("github", mcp_stub.url)], [skill])
    cat = _go(lambda: mcp_gateway.visible_catalogue(_DEV))
    assert [t["name"] for t in cat.tools] == ["github__query"]
    assert cat.callable == {"github": frozenset({"query"})}
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "github" in warnings[0] and "poisoned" in warnings[0] and "injection" in warnings[0]
    assert INJECTION_PHRASE not in caplog.text


@pytest.mark.parametrize(
    "tool",
    [
        UpstreamTool("t", "fine", {"type": "object", "properties": {"x": {
            "type": "string", "description": INJECTION_PHRASE}}}),
        UpstreamTool("t", "fine", {"type": "object"}, title=INJECTION_PHRASE),
        UpstreamTool("t", "fine", {"type": "object", "properties": {"x": {
            "type": "array", "items": {"oneOf": [{"description": INJECTION_PHRASE}]}}}}),
        UpstreamTool("t", INJECTION_PHRASE, {"type": "object"}),
    ],
    ids=["nested-property", "title", "items-oneof", "description"],
)
def test_injection_in_any_inspected_text_withholds(monkeypatch, tool, caplog):
    cat = _one_tool(monkeypatch, tool)
    assert cat.tools == () and dict(cat.callable) == {}
    assert INJECTION_PHRASE not in caplog.text


def test_clean_tool_is_kept_and_names_defaults_are_not_inspected(monkeypatch):
    schema = {"type": "object", "properties": {INJECTION_PHRASE: {"type": "string", "default": INJECTION_PHRASE}}}
    cat = _one_tool(monkeypatch, UpstreamTool("t", "plain", schema))
    assert [t["name"] for t in cat.tools] == ["g__t"]


def test_text_over_the_scan_ceiling_fails_closed(monkeypatch):
    monkeypatch.setattr(settings, "PATTERN_MAX_SCAN_CHARACTERS", 50)
    assert _one_tool(monkeypatch, UpstreamTool("t", "x" * 51, {"type": "object"})).tools == ()
    assert _one_tool(monkeypatch, UpstreamTool("t", "x" * 50, {"type": "object"})).tools != ()


def test_missing_injection_list_falls_back_to_the_built_in(monkeypatch):
    from app.services import pattern_config

    policy = pattern_config.PatternPolicy(lists={}, profiles={})
    monkeypatch.setattr(pattern_config, "_policy", policy)
    tool = UpstreamTool("t", INJECTION_PHRASE, {"type": "object"})
    assert _one_tool(monkeypatch, tool).tools == ()


# --- AC3: failures and unlisted tools --------------------------------------------


@pytest.mark.parametrize(
    "error", [McpUpstreamError("x"), asyncio.TimeoutError(), RuntimeError("SECRET-MSG")]
)
def test_a_failing_server_contributes_nothing_and_leaks_nothing(monkeypatch, caplog, error):
    caplog.set_level(logging.INFO)
    _cfg(monkeypatch, [_server("a"), _server("b")], [_skill("a__t", "b__t")])
    _fake_upstream(monkeypatch, {"a": error, "b": (UpstreamTool("t", "d", {"type": "object"}),)})
    cat = _go(lambda: mcp_gateway.visible_catalogue(_DEV))
    assert [t["name"] for t in cat.tools] == ["b__t"]
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1 and type(error).__name__ in warnings[0] and "a" in warnings[0]
    assert "SECRET-MSG" not in caplog.text
    assert not [r for r in caplog.records if "not listed upstream" in r.getMessage()]


def test_a_stopped_stub_is_tolerated(mcp_stub_factory, monkeypatch, caplog):
    live = mcp_stub_factory(name="live")
    dead = mcp_stub_factory(name="dead")
    _cfg(monkeypatch, [_server("live", live.url, timeout=5), _server("dead", dead.url, timeout=5)],
         [_skill("live__query", "dead__query")])
    dead.stop()
    cat = _go(lambda: mcp_gateway.visible_catalogue(_DEV))
    assert [t["name"] for t in cat.tools] == ["live__query"]
    assert [r for r in caplog.records if r.levelno == logging.WARNING and "server=dead" in r.getMessage()]


def test_unlisted_tool_is_omitted_with_one_info_per_period(monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    clock = [1000.0]
    monkeypatch.setattr(mcp_gateway, "_now", lambda: clock[0])
    monkeypatch.setattr(settings, "MCP_TOOLS_CACHE_SECONDS", 60)
    _cfg(monkeypatch, [_server("g")], [_skill("g__t", "g__ghost")])
    _fake_upstream(monkeypatch, {"g": (UpstreamTool("t", "d", {"type": "object"}),)})

    def infos():
        return [r for r in caplog.records if "not listed upstream" in r.getMessage()]

    first = _go(lambda: mcp_gateway.visible_catalogue(_DEV))
    assert [t["name"] for t in first.tools] == ["g__t"] and len(infos()) == 1
    assert "ghost" in infos()[0].getMessage()
    _go(lambda: mcp_gateway.visible_catalogue(_DEV))
    assert len(infos()) == 1
    clock[0] += 61
    _go(lambda: mcp_gateway.visible_catalogue(_DEV))
    assert len(infos()) == 2
    assert len(mcp_gateway._unlisted_logged) == 1  # expired keys are pruned

    monkeypatch.setattr(settings, "MCP_TOOLS_CACHE_SECONDS", 0)
    _go(lambda: mcp_gateway.visible_catalogue(_DEV))
    _go(lambda: mcp_gateway.visible_catalogue(_DEV))
    assert len(infos()) == 4


# --- Non-object schemas -----------------------------------------------------------


@pytest.mark.parametrize("schema", [{"type": "string"}, {}])
def test_non_object_schema_is_emitted_unchanged_with_info(monkeypatch, caplog, schema):
    caplog.set_level(logging.INFO)
    cat = _one_tool(monkeypatch, UpstreamTool("t", "d", schema))
    assert cat.tools[0]["inputSchema"] == schema
    assert [r for r in caplog.records if "not type=object" in r.getMessage()]


# --- AC4: HTTP, no row, audit line -----------------------------------------------


def _http_identity(token):
    return {"dev": _DEV, "user": _USER}.get(token)


@pytest.fixture
def http(monkeypatch):
    monkeypatch.setattr("app.middleware.auth.resolve", _http_identity)
    monkeypatch.setattr(settings, "MCP_ALLOWED_ORIGINS", "")

    def boom(*args, **kwargs):
        raise AssertionError("tools/list must write no action_decisions row (O4)")

    monkeypatch.setattr(action_audit, "record", boom)
    monkeypatch.setattr(database, "insert_action_decisions", boom)
    app = FastAPI()
    app.include_router(mcp_router.router)
    # One client context = one event loop, so the upstream session survives between requests.
    with TestClient(app) as client:
        try:
            yield client
        finally:
            client.portal.call(mcp_upstream.aclose_all)


def _list(client, token):
    response = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    assert response.status_code == 200
    return response.json()["result"]["tools"]


def test_http_tools_list_end_to_end(mcp_stub, monkeypatch, http, caplog):
    caplog.set_level(logging.INFO)
    skill = Skill("open-pull-request", "1.0.0", "d", "i", (*_PR_SKILL.tools, "github__poisoned"), ())
    _cfg(monkeypatch, [_server("github", mcp_stub.url)], [skill])

    tools = _list(http, "dev")
    assert [t["name"] for t in tools] == list(_PR_TOOLS)  # `poisoned` is never listed
    assert _list(http, "user") == []

    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("mcp tools/list: user=")]
    line = next(entry for entry in lines if "u-dev" in entry)
    assert "servers=github" in line and "tools=3" in line
    assert f"digest={mcp_config.mcp_config_digest()}" in line
    first = tools[0]
    assert f"{first['name']}=sha256:{hashlib.sha256(first['description'].encode()).hexdigest()}" in line
    # The stub's tools carry no description, so the hash is of "": no text can leak.
    assert INJECTION_PHRASE not in caplog.text


# --- T17 --------------------------------------------------------------------------


def test_the_gateway_never_imports_the_sdk():
    tree = ast.parse(Path(inspect.getsourcefile(mcp_gateway)).read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    assert not [n for n in imported if n == "mcp" or n.startswith("mcp.")]


# --- STORY-015: prompts/list and prompts/get from held skills ------------------------------


def _prompt_skills(monkeypatch):
    monkeypatch.setattr(
        authz, "ROLE_PERMISSIONS",
        {"dev": {"skill:open-pull-request", "skill:run-migration", "mcp:connect"},
         "mid": {"skill:run-migration", "mcp:connect"}, "user": {"mcp:connect"}},
    )
    _cfg(monkeypatch, [], [
        Skill("open-pull-request", "1.0.0", "Open a PR", "PR steps.", (), ()),
        Skill("run-migration", "1.0.0", "Run a migration", "Migration steps.", (), ()),
    ])


def test_prompts_list_only_held_skills(monkeypatch):
    _prompt_skills(monkeypatch)
    assert mcp_gateway.list_prompts(_DEV) == [
        {"name": "skill-open-pull-request", "description": "Open a PR"},
        {"name": "skill-run-migration", "description": "Run a migration"},
    ]
    assert mcp_gateway.list_prompts(Identity(user_id="m", role="mid")) == [
        {"name": "skill-run-migration", "description": "Run a migration"},
    ]
    assert mcp_gateway.list_prompts(_USER) == []


def test_prompts_get_returns_instructions_as_user_message(monkeypatch):
    _prompt_skills(monkeypatch)
    assert mcp_gateway.get_prompt(_DEV, {"name": "skill-run-migration"}) == {
        "description": "Run a migration",
        "messages": [{"role": "user", "content": {"type": "text", "text": "Migration steps."}}],
    }


def test_prompts_get_unknown_and_not_held_share_one_message(monkeypatch):
    _prompt_skills(monkeypatch)
    mid = Identity(user_id="m", role="mid")
    seen = set()
    for who, name in ((mid, "skill-open-pull-request"), (mid, "skill-nope"), (_DEV, "run-migration")):
        with pytest.raises(mcp_gateway.GatewayRpcError) as exc:
            mcp_gateway.get_prompt(who, {"name": name})
        seen.add((exc.value.code, exc.value.message))
    # PRD-023 D19: the bare id (without the `skill-` prefix) does not resolve either.
    assert seen == {(-32602, mcp_gateway.UNKNOWN_PROMPT_MESSAGE)}


@pytest.mark.parametrize("params", [{}, {"name": ""}, {"name": 5}, {"name": None}])
def test_prompts_get_bad_name_is_invalid_params(monkeypatch, params):
    _prompt_skills(monkeypatch)
    with pytest.raises(mcp_gateway.GatewayRpcError) as exc:
        mcp_gateway.get_prompt(_DEV, params)
    assert (exc.value.code, exc.value.message) == (-32602, mcp_gateway.INVALID_NAME_MESSAGE)


def test_prompts_get_ignores_arguments(monkeypatch):
    _prompt_skills(monkeypatch)
    plain = mcp_gateway.get_prompt(_DEV, {"name": "skill-run-migration"})
    for junk in ({"a": 1}, "garbage", [1], None):
        assert mcp_gateway.get_prompt(_DEV, {"name": "skill-run-migration", "arguments": junk}) == plain


def test_prompts_touch_no_audit_usage_or_upstream(monkeypatch):
    _prompt_skills(monkeypatch)

    def boom(*args, **kwargs):
        raise AssertionError("prompts/* must not write a row, admit usage or reach upstream")

    for owner, attr in (
        (action_audit, "record"), (action_audit, "record_outcome"),
        (mcp_gateway.usage_limits, "admit"),
        (mcp_upstream, "list_tools"), (mcp_upstream, "call_tool"),
    ):
        monkeypatch.setattr(owner, attr, boom)
    mcp_gateway.list_prompts(_DEV)
    mcp_gateway.get_prompt(_DEV, {"name": "skill-open-pull-request"})
