"""Northbound `POST /mcp`: gate, JSON-RPC parsing, initialize/ping/notifications (PRD-023 STORY-011).

No database and no lifespan: identities come from a patched `resolve`, and the
router is mounted on a bare FastAPI app (the root app has no `/mcp` while
`MCP_ENABLED` is off). Runs under `-m "not db"`.
"""

import importlib.util
import inspect
import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.main as main_module
from app.config import settings
from app.db import database
from app.routers import mcp as mcp_router
from app.services import action_audit, authz, mcp_config
from app.services.identity import Identity
from app.services.mcp_config import McpConfig, Skill

USER_TOKEN = "user-token"
AUDITOR_TOKEN = "auditor-token"
ADMIN_TOKEN_VALUE = "break-glass-token"
HEADERS = {"Authorization": f"Bearer {USER_TOKEN}", "Content-Type": "application/json"}


def _fake_resolve(token):
    if token == USER_TOKEN:
        return Identity(user_id="u1", role="user")
    if token == AUDITOR_TOKEN:
        return Identity(user_id="u2", role="auditor")
    if token == ADMIN_TOKEN_VALUE:
        return Identity(user_id="admin", role="admin", break_glass=True)
    return None


@pytest.fixture(autouse=True)
def _identities(monkeypatch):
    monkeypatch.setattr("app.middleware.auth.resolve", _fake_resolve)
    monkeypatch.setattr(settings, "RBAC_ENABLED", True)
    monkeypatch.setattr(settings, "MCP_ALLOWED_ORIGINS", "")
    monkeypatch.setattr(settings, "MCP_MAX_REQUEST_BYTES", 1048576)


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(mcp_router.router)
    return TestClient(app)


@pytest.fixture
def no_side_effects(monkeypatch):
    """M0 refusals write no row and reach no upstream."""

    def boom(*args, **kwargs):
        raise AssertionError("an M0 refusal must not write a row or call upstream")

    monkeypatch.setattr(action_audit, "record", boom)
    monkeypatch.setattr(database, "insert_action_decisions", boom)


def _rpc(method, params=None, id_=1, **extra):
    body = {"jsonrpc": "2.0", "method": method, **extra}
    if id_ is not None:
        body["id"] = id_
    if params is not None:
        body["params"] = params
    return body


def _post(client, body, headers=None, **kwargs):
    return client.post("/mcp", json=body, headers=headers or HEADERS, **kwargs)


def _raw(client, data, headers=None):
    return client.post("/mcp", content=data, headers=headers or HEADERS)


# --- AC1: mounting ---------------------------------------------------------------


def _fresh_main(monkeypatch, enabled):
    monkeypatch.setattr(settings, "MCP_ENABLED", enabled)
    spec = importlib.util.spec_from_file_location(
        f"_harness_main_mcp_{enabled}", Path(inspect.getsourcefile(main_module))
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_disabled_mcp_is_not_mounted(monkeypatch):
    module = _fresh_main(monkeypatch, False)
    off = TestClient(module.app)
    assert off.post("/mcp", json=_rpc("ping"), headers=HEADERS).status_code == 404
    assert off.get("/.well-known/oauth-protected-resource").status_code == 404
    assert off.get("/.well-known/oauth-authorization-server").status_code == 404
    # /query answers exactly as before.
    assert off.post("/query", json={"prompt": "hi"}).status_code == 401


def test_enabled_mcp_flow_and_get_delete_405_allow_post(monkeypatch):
    module = _fresh_main(monkeypatch, True)
    on = TestClient(module.app)
    # E2E: initialize -> notifications/initialized -> tools/list, all 2xx, no session.
    init = on.post("/mcp", json=_rpc("initialize", {"protocolVersion": "2025-06-18"}), headers=HEADERS)
    assert init.status_code == 200
    assert init.json()["result"]["protocolVersion"] == "2025-06-18"
    assert "mcp-session-id" not in init.headers
    note = on.post("/mcp", json=_rpc("notifications/initialized", id_=None), headers=HEADERS)
    assert note.status_code == 202
    assert note.content == b""
    listed = on.post("/mcp", json=_rpc("tools/list", id_=2), headers=HEADERS)
    assert listed.status_code == 200
    assert listed.json() == {"jsonrpc": "2.0", "id": 2, "result": {"tools": []}}
    assert "mcp-session-id" not in listed.headers
    assert on.post("/query", json={"prompt": "hi"}).status_code == 401
    for verb in ("get", "delete"):
        response = getattr(on, verb)("/mcp", headers=HEADERS)
        assert response.status_code == 405
        assert response.headers["allow"] == "POST"


def test_get_delete_405_allow_post(client):
    for verb in ("get", "delete"):
        response = getattr(client, verb)("/mcp", headers=HEADERS)
        assert response.status_code == 405
        assert response.headers["allow"] == "POST"


# --- AC2: M0 ----------------------------------------------------------------------


def test_m0_401_carries_www_authenticate(client, no_side_effects):
    for headers in ({}, {"Authorization": "Bearer nope"}, {"Authorization": "Basic abc"}):
        response = client.post("/mcp", json=_rpc("ping"), headers=headers)
        assert response.status_code == 401
        assert response.headers["www-authenticate"] == 'Bearer realm="harness"'


def test_m0_break_glass_is_403(client, no_side_effects):
    headers = {**HEADERS, "Authorization": f"Bearer {ADMIN_TOKEN_VALUE}"}
    response = _post(client, _rpc("ping"), headers)
    assert response.status_code == 403
    assert "ingress:break_glass" in response.json()["detail"]


def test_m0_missing_mcp_connect_is_403(client, no_side_effects):
    headers = {**HEADERS, "Authorization": f"Bearer {AUDITOR_TOKEN}"}
    response = _post(client, _rpc("ping"), headers)
    assert response.status_code == 403
    assert response.json()["detail"] == "Permission denied: mcp:connect"


def test_m0_rbac_off_opens_the_permission(client, monkeypatch):
    monkeypatch.setattr(settings, "RBAC_ENABLED", False)
    headers = {**HEADERS, "Authorization": f"Bearer {AUDITOR_TOKEN}"}
    assert _post(client, _rpc("ping"), headers).status_code == 200


def test_m0_origin_rules(client, monkeypatch, no_side_effects):
    monkeypatch.setattr(settings, "MCP_ALLOWED_ORIGINS", "https://a.com,http://localhost:3000")
    body = _rpc("ping")
    assert _post(client, body).status_code == 200  # absent
    for origin in ("https://a.com", "https://a.com:443", "HTTP://LOCALHOST:3000"):
        assert _post(client, body, {**HEADERS, "Origin": origin}).status_code == 200, origin
    for origin in ("https://evil.com", "null", "not a url", "https://a.com:444", "http://a.com"):
        response = _post(client, body, {**HEADERS, "Origin": origin})
        assert response.status_code == 403, origin
        assert origin not in response.text


def test_m0_origin_present_with_empty_allow_list_is_403(client):
    assert _post(client, _rpc("ping"), {**HEADERS, "Origin": "https://a.com"}).status_code == 403


def test_m0_413_by_content_length(client, monkeypatch, no_side_effects):
    monkeypatch.setattr(settings, "MCP_MAX_REQUEST_BYTES", 1024)
    big = _rpc("ping", {"pad": "x" * 2000})
    assert _post(client, big).status_code == 413


def test_m0_413_by_streamed_bytes_without_content_length(client, monkeypatch, no_side_effects):
    monkeypatch.setattr(settings, "MCP_MAX_REQUEST_BYTES", 1024)

    def chunks():
        for _ in range(4):
            yield b" " * 512

    response = client.post("/mcp", content=chunks(), headers=HEADERS)
    assert response.status_code == 413


def test_m0_body_at_the_limit_is_accepted(client, monkeypatch):
    monkeypatch.setattr(settings, "MCP_MAX_REQUEST_BYTES", 1024)
    body = b'{"jsonrpc":"2.0","id":1,"method":"ping"}'
    assert _raw(client, body + b" " * (1024 - len(body))).status_code == 200


def test_m0_415_and_charset_accepted(client, no_side_effects):
    for content_type in ("text/plain", "application/jsonx", ""):
        response = _raw(
            client, b"{}", {"Authorization": HEADERS["Authorization"], "Content-Type": content_type}
        )
        assert response.status_code == 415, content_type
    for content_type in ("application/json; charset=utf-8", " Application/JSON ;charset=UTF-8"):
        response = _raw(
            client,
            b'{"jsonrpc":"2.0","id":1,"method":"ping"}',
            {"Authorization": HEADERS["Authorization"], "Content-Type": content_type},
        )
        assert response.status_code == 200, content_type


def test_m0_unknown_query_params_are_ignored(client):
    response = client.post("/mcp?codemode=false&x=1", json=_rpc("ping"), headers=HEADERS)
    assert response.status_code == 200


def test_m0_order_credential_before_everything(client):
    # Bad credential, bad Origin, bad type: 401 wins.
    response = client.post(
        "/mcp", content=b"x", headers={"Origin": "https://evil.com", "Content-Type": "text/plain"}
    )
    assert response.status_code == 401


def test_m0_break_glass_before_origin_and_type(client):
    headers = {
        "Authorization": f"Bearer {ADMIN_TOKEN_VALUE}",
        "Origin": "https://evil.com",
        "Content-Type": "text/plain",
    }
    response = client.post("/mcp", content=b"x", headers=headers)
    assert response.status_code == 403
    assert "break_glass" in response.json()["detail"]


def test_m0_refusals_do_not_log_credentials_or_origin(client, caplog, monkeypatch):
    monkeypatch.setattr(settings, "MCP_ALLOWED_ORIGINS", "https://a.com")
    with caplog.at_level("INFO"):
        _post(client, _rpc("ping"), {**HEADERS, "Origin": "https://secret-origin.example"})
    assert "secret-origin" not in caplog.text
    assert USER_TOKEN not in caplog.text


# --- AC3: JSON-RPC -----------------------------------------------------------------


def _err(response):
    body = response.json()
    return body["id"], body["error"]["code"]


def test_parse_errors(client):
    bodies = (
        b"{not json",
        b"",
        b'{"jsonrpc":"2.0","id":1,"method":"ping","method":"x"}',
        b'{"jsonrpc":"2.0","id":1,"params":{"a":{"b":1,"b":2}},"method":"ping"}',
        b'\xff\xfe{"a":1}',
        b'{"jsonrpc":"2.0","id":NaN,"method":"ping"}',
    )
    for data in bodies:
        response = _raw(client, data)
        assert response.status_code == 200, data
        assert _err(response) == (None, -32700), data


def test_deeply_nested_body_is_a_parse_error(client):
    assert _err(_raw(client, b"[" * 50000)) == (None, -32700)


def test_invalid_request_variants(client):
    cases = [
        ([], None),
        (5, None),
        ("x", None),
        ({"id": 1, "method": "ping"}, 1),  # no jsonrpc
        ({"jsonrpc": "1.0", "id": 1, "method": "ping"}, 1),
        ({"jsonrpc": 2.0, "id": 1, "method": "ping"}, 1),
        ({"jsonrpc": "2.0", "id": True, "method": "ping"}, None),
        ({"jsonrpc": "2.0", "id": None, "method": "ping"}, None),
        ({"jsonrpc": "2.0", "id": {"a": 1}, "method": "ping"}, None),
        ({"jsonrpc": "2.0", "id": [1], "method": "ping"}, None),
        ({"jsonrpc": "2.0", "id": 1.5, "method": "ping"}, None),
        ({"jsonrpc": "2.0", "id": "a"}, "a"),
        ({"jsonrpc": "2.0", "id": 7, "method": 5}, 7),
        ({"jsonrpc": "2.0", "id": 7, "method": None}, 7),
    ]
    for body, expected_id in cases:
        response = _post(client, body)
        assert response.status_code == 200, body
        assert _err(response) == (expected_id, -32600), body


def test_a_json_null_body_is_invalid_request(client):
    assert _err(_raw(client, b"null")) == (None, -32600)


def test_unknown_method(client):
    response = _post(client, _rpc("nope/nothing", id_="r1"))
    assert response.status_code == 200
    assert _err(response) == ("r1", -32601)


def test_a_request_named_like_a_notification_is_unknown(client):
    assert _err(_post(client, _rpc("notifications/initialized"))) == (1, -32601)


def test_modern_era_is_refused_with_400(client):
    meta = {"_meta": {"io.modelcontextprotocol/protocolVersion": "2026-03-01"}}
    response = _post(client, _rpc("tools/list", meta))
    assert response.status_code == 400
    assert _err(response) == (1, -32600)
    discover = _post(client, _rpc("server/discover", id_="d"))
    assert discover.status_code == 400
    assert _err(discover) == ("d", -32600)


def test_modern_meta_on_initialize_passes(client):
    params = {
        "protocolVersion": "2025-06-18",
        "_meta": {"io.modelcontextprotocol/protocolVersion": "2026-03-01"},
    }
    assert _post(client, _rpc("initialize", params)).status_code == 200


def test_other_meta_keys_pass(client):
    response = _post(client, _rpc("tools/list", {"_meta": {"progressToken": 1}}))
    assert response.status_code == 200
    assert response.json()["result"] == {"tools": []}


def test_non_object_params_are_invalid_params(client):
    for method in ("initialize", "tools/list"):
        for params in ([1], "x", 5):
            response = _post(client, {"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
            assert response.status_code == 200
            assert _err(response) == (1, -32602), (method, params)


# --- AC4: initialize / ping / notifications ----------------------------------------


@pytest.mark.parametrize("version", ["2025-03-26", "2025-06-18", "2025-11-25"])
def test_initialize_echoes_a_supported_version(client, version):
    response = _post(client, _rpc("initialize", {"protocolVersion": version}))
    assert response.json()["result"]["protocolVersion"] == version


@pytest.mark.parametrize("requested", ["2024-11-05", "2026-01-01", 5, None, ""])
def test_initialize_falls_back_to_the_newest(client, requested):
    response = _post(client, _rpc("initialize", {"protocolVersion": requested}))
    assert response.json()["result"]["protocolVersion"] == "2025-11-25"


def test_initialize_result_shape(client):
    response = _post(client, _rpc("initialize", {"protocolVersion": "2025-06-18"}, id_="i"))
    assert response.json() == {
        "jsonrpc": "2.0",
        "id": "i",
        "result": {
            "protocolVersion": "2025-06-18",
            "capabilities": {"tools": {"listChanged": False}, "prompts": {"listChanged": False}},
            "serverInfo": {"name": "harness", "version": FastAPI().version},
        },
    }
    assert "mcp-session-id" not in response.headers


def test_initialize_without_params(client):
    assert _post(client, _rpc("initialize")).json()["result"]["protocolVersion"] == "2025-11-25"


def test_inbound_session_id_is_ignored(client):
    headers = {**HEADERS, "mcp-session-id": "abc", "Mcp-Protocol-Version": "2025-06-18"}
    response = _post(client, _rpc("tools/list"), headers)
    assert response.status_code == 200
    assert "mcp-session-id" not in response.headers


def test_ping(client):
    response = _post(client, _rpc("ping", id_="p"))
    assert response.json() == {"jsonrpc": "2.0", "id": "p", "result": {}}


def test_notification_202_empty_body(client):
    methods = ("notifications/initialized", "notifications/cancelled", "notifications/unknown", "ping")
    for method in methods:
        response = _post(client, _rpc(method, id_=None))
        assert response.status_code == 202, method
        assert response.content == b""
        assert "mcp-session-id" not in response.headers


def test_responses_are_plain_json(client):
    response = _post(client, _rpc("ping"))
    assert response.headers["content-type"].startswith("application/json")


# --- AC5: seams ---------------------------------------------------------------------


def test_seam_placeholders(client):
    assert _post(client, _rpc("tools/list")).json()["result"] == {"tools": []}
    # PRD-023 STORY-015: served from held skills; an empty config holds none.
    assert _post(client, _rpc("prompts/list")).json()["result"] == {"prompts": []}
    # PRD-023 STORY-013: tools/call is no longer a -32601 placeholder. A call with no
    # `name` is an M3 -32602 (no usage check, no row, no upstream), so this test needs no database.
    assert _err(_post(client, _rpc("tools/call", {}))) == (1, -32602)
    # PRD-023 STORY-015, D19: unknown prompt is -32602, no longer the -32601 placeholder.
    assert _err(_post(client, _rpc("prompts/get", {"name": "x"}))) == (1, -32602)


def test_prompts_wire_shape_and_one_unknown_message(client, monkeypatch):
    """PRD-023 STORY-015 E2E: list then get over HTTP; unknown and not-held are identical."""
    monkeypatch.setattr(authz, "ROLE_PERMISSIONS", {"user": {"mcp:connect", "skill:held"}})
    monkeypatch.setattr(
        mcp_config, "_config",
        McpConfig(servers={}, skills=(
            Skill("held", "1.0.0", "A held one", "Step one.", (), ()),
            Skill("other", "1.0.0", "Not held", "Secret.", (), ()),
        )),
    )
    listed = _post(client, _rpc("prompts/list")).json()["result"]
    assert listed == {"prompts": [{"name": "skill-held", "description": "A held one"}]}
    got = _post(client, _rpc("prompts/get", {"name": "skill-held"})).json()["result"]
    assert got == {
        "description": "A held one",
        "messages": [{"role": "user", "content": {"type": "text", "text": "Step one."}}],
    }
    unknown = _post(client, _rpc("prompts/get", {"name": "skill-nope"})).json()["error"]
    not_held = _post(client, _rpc("prompts/get", {"name": "skill-other"})).json()["error"]
    assert unknown == not_held == {"code": -32602, "message": "Unknown prompt"}


def test_seams_are_reached_without_initialize_with_params_and_identity(client, monkeypatch):
    seen = {}

    async def fake_call(identity, params, request_id):
        seen.update(identity=identity, params=params, request_id=request_id)
        return {"content": []}

    monkeypatch.setitem(mcp_router._HANDLERS, "tools/call", fake_call)
    response = _post(client, _rpc("tools/call", {"name": "a__b", "arguments": {"x": 1}}, id_="c9"))
    assert response.json() == {"jsonrpc": "2.0", "id": "c9", "result": {"content": []}}
    assert seen["identity"].user_id == "u1"
    assert seen["params"] == {"name": "a__b", "arguments": {"x": 1}}
    assert seen["request_id"] == "c9"


def test_seam_params_default_to_an_empty_dict(client, monkeypatch):
    seen = {}

    async def fake_list(identity, params, request_id):
        seen["params"] = params
        return {"tools": []}

    monkeypatch.setitem(mcp_router._HANDLERS, "tools/list", fake_list)
    _post(client, _rpc("tools/list"))
    assert seen["params"] == {}


def test_seam_json_rpc_error_is_http_200(client, monkeypatch):
    async def fake(identity, params, request_id):
        raise mcp_router.JsonRpcError(-32602, "bad thing")

    monkeypatch.setitem(mcp_router._HANDLERS, "tools/call", fake)
    response = _post(client, _rpc("tools/call", {}))
    assert response.status_code == 200
    assert response.json()["error"] == {"code": -32602, "message": "bad thing"}


def test_seam_crash_is_internal_error_without_request_data(client, monkeypatch):
    async def fake(identity, params, request_id):
        raise RuntimeError("boom with secret-arg")

    monkeypatch.setitem(mcp_router._HANDLERS, "tools/call", fake)
    response = _post(client, _rpc("tools/call", {"arguments": {"k": "secret-arg"}}))
    assert response.status_code == 200
    assert response.json()["error"] == {"code": -32603, "message": "internal error"}
    assert "secret-arg" not in response.text


def test_the_router_never_imports_the_sdk_or_upstream_client():
    """STORY-011 calls no upstream (STORY-012/013 do) and T17 keeps `mcp` out of app/."""
    import ast

    tree = ast.parse(Path(inspect.getsourcefile(mcp_router)).read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
            imported.update(f"{node.module}.{alias.name}" for alias in node.names)
    assert not [name for name in imported if name == "mcp" or name.startswith("mcp.")]
    assert not [name for name in imported if "mcp_upstream" in name]
