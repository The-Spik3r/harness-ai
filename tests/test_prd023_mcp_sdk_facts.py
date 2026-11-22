"""PRD-023 STORY-003: facts about the pinned `mcp` SDK client, observed offline.

A spike's findings, kept as tests so an SDK bump that changes one fails here
instead of in the upstream client STORY-009/010 build on them. Everything runs
against servers on 127.0.0.1 with ports picked by the OS: no real network, no
database, no bare sleeps (deadline loops and `threading.Event`s; every server
thread is stopped and joined in the fixture finalizer).

    AC 1  the pin (exact) and that `app/` never imports the SDK (T17)
    AC 2  module paths, static headers, redirect behaviour (T8), the per-call
          timeout (D14), server-initiated sampling (T12/D16), tools/list
          pagination, and the 2026-07-28 / `input_required` surfaces

The facts asserted are what the installed SDK does, not what PRD-023 assumed;
where they differ the test name says so:

    - T8   "redirects are not followed": same-origin 307/308 ARE followed
           (the SDK ignores `follow_redirects`); cross-origin and 301/302 are not.
    - T12  "-32601 for sampling": the SDK answers `-32600 "Sampling not supported"`.
    - D14  the timeout is `MCPError` -32001 and the SDK sends `notifications/cancelled`.
    - F12  `FastMCP` is `mcp.server.mcpserver.MCPServer`; the transport yields two
           streams and takes an `httpx2.AsyncClient`, not headers.
"""

import ast
import asyncio
import importlib.metadata
import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx2
import pytest

import mcp
import mcp.types as mcp_types_compat
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from tests._caddy import free_port

_REPO_ROOT = Path(__file__).resolve().parents[1]
_AUTH = "Bearer spike-TOKEN"
_DEADLINE = 10.0  # seconds; generous for CI


# --- helpers -----------------------------------------------------------------


def _flatten(exc):
    """Leaf exceptions of an (possibly nested) exception group; anyio task groups wrap errors."""
    if isinstance(exc, BaseExceptionGroup):
        return [leaf for inner in exc.exceptions for leaf in _flatten(inner)]
    return [exc]


def _run(coro, timeout=20):
    return asyncio.run(asyncio.wait_for(coro, timeout))


def _wait_until(predicate, timeout=_DEADLINE):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


async def _with_session(url, body, *, headers=None, initialize=True):
    """Open client + transport + session, run `await body(session)`, return its result."""
    async with httpx2.AsyncClient(headers=headers, timeout=_DEADLINE) as http:
        async with streamable_http_client(url, http_client=http) as (read, write):
            async with ClientSession(read, write) as session:
                if initialize:
                    await session.initialize()
                return await body(session)


def _leaves_of(coro_factory):
    """Run and return the leaf exceptions it raised (fails the test if it did not raise)."""
    try:
        _run(coro_factory())
    except BaseException as exc:  # noqa: BLE001 - we want the group's leaves
        return _flatten(exc)
    pytest.fail("expected the SDK call to raise")


class _RawServer:
    """A hand-written streamable-HTTP MCP endpoint that records every request."""

    def __init__(self, other=None):
        self.requests = []  # (method, path, lower-cased headers, parsed body | None)
        self.sampling_reply = None
        self.reply_seen = threading.Event()
        self.release = threading.Event()
        self.other = other
        outer = self

        class _Handler(BaseHTTPRequestHandler):
            def _json(self, status, payload, headers=None):
                data = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(data)))
                for k, v in (headers or {}).items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(data)

            def _sse(self, payload):
                self.wfile.write(f"event: message\ndata: {json.dumps(payload)}\n\n".encode())
                self.wfile.flush()

            def do_POST(self):
                length = int(self.headers.get("content-length") or 0)
                raw = self.rfile.read(length) if length else b""
                try:
                    body = json.loads(raw) if raw else None
                except ValueError:
                    body = None
                headers = {k.lower(): v for k, v in self.headers.items()}
                outer.requests.append(("POST", self.path, headers, body))
                try:
                    self._dispatch(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass  # the client gave up (timeout case)

            def do_GET(self):
                outer.requests.append(("GET", self.path, {k.lower(): v for k, v in self.headers.items()}, None))
                self.send_response(405)
                self.send_header("content-length", "0")
                self.end_headers()

            do_DELETE = do_GET

            def _dispatch(self, body):
                if self.path.startswith("/redir"):
                    query = dict(p.split("=") for p in self.path.split("?", 1)[1].split("&"))
                    target = "/target"
                    if query["kind"] == "cross":
                        target = f"http://127.0.0.1:{outer.other.port}/target"
                    self.send_response(int(query["code"]))
                    self.send_header("location", target)
                    self.send_header("content-length", "0")
                    self.end_headers()
                    return
                if self.path.startswith("/target"):
                    self._json(200, {})
                    return
                if body is None:
                    self._json(400, {"error": "bad body"})
                    return
                method, rid = body.get("method"), body.get("id")
                if method is None:  # a response to a server-initiated request
                    if rid == 77:
                        outer.sampling_reply = body
                        outer.reply_seen.set()
                    self.send_response(202)
                    self.send_header("content-length", "0")
                    self.end_headers()
                    return
                if rid is None:  # a notification
                    self.send_response(202)
                    self.send_header("content-length", "0")
                    self.end_headers()
                    return
                if method == "initialize":
                    self._json(
                        200,
                        {
                            "jsonrpc": "2.0",
                            "id": rid,
                            "result": {
                                "protocolVersion": "2025-11-25",
                                "capabilities": {"tools": {}},
                                "serverInfo": {"name": "raw", "version": "0"},
                            },
                        },
                    )
                elif method == "tools/list":
                    cursor = (body.get("params") or {}).get("cursor")
                    result = {"tools": [{"name": "echo", "inputSchema": {"type": "object"}}]}
                    if cursor is None:
                        result["nextCursor"] = "c2"
                    self._json(200, {"jsonrpc": "2.0", "id": rid, "result": result})
                elif method == "tools/call":
                    self._call(body, rid)
                else:
                    self._json(
                        200, {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": "no such method"}}
                    )

            def _call(self, body, rid):
                name = body["params"]["name"]
                ok = {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"type": "text", "text": name}]}}
                if name == "slow":
                    outer.release.wait(30)
                    self._json(200, ok)
                elif name == "sample":
                    self.send_response(200)
                    self.send_header("content-type", "text/event-stream")
                    self.send_header("connection", "close")
                    self.end_headers()
                    self._sse(
                        {
                            "jsonrpc": "2.0",
                            "id": 77,
                            "method": "sampling/createMessage",
                            "params": {
                                "messages": [{"role": "user", "content": {"type": "text", "text": "hi"}}],
                                "maxTokens": 8,
                            },
                        }
                    )
                    outer.reply_seen.wait(_DEADLINE)
                    self._sse(ok)
                    self.close_connection = True
                elif name == "mrtr":
                    self._json(
                        200,
                        {
                            "jsonrpc": "2.0",
                            "id": rid,
                            "result": {"resultType": "input_required", "requestState": "s", "inputRequests": {}},
                        },
                    )
                else:
                    self._json(200, ok)

            def log_message(self, *args):
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self._server.daemon_threads = True
        self.port = self._server.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}/mcp"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def methods(self):
        return [r[3].get("method") for r in self.requests if isinstance(r[3], dict)]

    def close(self):
        self.release.set()
        self.reply_seen.set()
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)


@pytest.fixture
def raw_servers():
    made = []

    def make(**kwargs):
        server = _RawServer(**kwargs)
        made.append(server)
        return server

    yield make
    for server in reversed(made):
        server.close()


@pytest.fixture
def sdk_app_server():
    """Serve an ASGI app with uvicorn in a thread on a free port; stopped on teardown."""
    import uvicorn

    started = []

    def serve(app):
        port = free_port()
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        assert _wait_until(lambda: server.started), "uvicorn did not start"
        started.append((server, thread))
        return f"http://127.0.0.1:{port}/mcp"

    yield serve
    for server, thread in started:
        server.should_exit = True
        thread.join(timeout=5)


# --- AC 1: the pin and the T17 boundary ---------------------------------------


def test_pin_is_exact_and_installed():
    text = (_REPO_ROOT / "requirements.txt").read_text(encoding="utf-8")

    assert re.search(r"(?m)^mcp==2\.3\.0\s*$", text)
    assert importlib.metadata.version("mcp") == "2.3.0"
    # The pins this story must not have moved.
    assert re.search(r"(?m)^anthropic==2\.11\.0\s*$", text)
    assert re.search(r"(?m)^reflex==0\.9\.6\.post1\s*$", text)


def test_app_never_imports_mcp():
    """PRD-023 T17: until STORY-010 the SDK is imported by nothing under app/."""
    offenders = []
    for path in (_REPO_ROOT / "app").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names = [node.module]
            if any(n == "mcp" or n.startswith("mcp.") for n in names):
                offenders.append(str(path.relative_to(_REPO_ROOT)))
    assert offenders == []


# --- AC 2: the SDK's client surface -------------------------------------------


def test_import_paths_used_later_and_transport_yields_two_streams(raw_servers):
    """F12 amendment: v2 yields (read, write), not v1's three values; FastMCP is MCPServer."""
    from mcp.server.mcpserver import MCPServer

    assert MCPServer is not None
    assert issubclass(mcp.MCPError, Exception)
    assert mcp_types_compat.PaginatedRequestParams(cursor="x").cursor == "x"
    with pytest.raises(ImportError):
        from mcp.server.fastmcp import FastMCP  # noqa: F401 - removed in mcp 2

    server = raw_servers()

    async def go():
        async with httpx2.AsyncClient(timeout=_DEADLINE) as http:
            async with streamable_http_client(server.url, http_client=http) as streams:
                return len(streams)

    assert _run(go()) == 2


def test_handshake_negotiates_2025_11_25_and_declares_no_capabilities(raw_servers, sdk_app_server):
    from mcp.server.mcpserver import MCPServer

    raw = raw_servers()

    # Raw server: the initialize params carry empty capabilities (D16).
    async def go_raw():
        async def body(session):
            return (await session.initialize()).protocol_version

        return await _with_session(raw.url, body, initialize=False)

    assert _run(go_raw()) == "2025-11-25"
    init_body = next(r[3] for r in raw.requests if r[3] and r[3].get("method") == "initialize")
    assert init_body["params"]["capabilities"] == {}
    assert init_body["params"]["protocolVersion"] == "2025-11-25"

    # The SDK's own server agrees on the same version.
    url = sdk_app_server(MCPServer("facts").streamable_http_app())

    async def go_sdk():
        async def body(session):
            return (await session.initialize()).protocol_version

        return await _with_session(url, body, initialize=False)

    assert _run(go_sdk()) == "2025-11-25"


def test_static_headers_reach_the_server_via_httpx2_client_not_a_headers_argument(raw_servers):
    raw = raw_servers()

    async def body(session):
        return await session.call_tool("echo", {})

    result = _run(_with_session(raw.url, body, headers={"Authorization": _AUTH}))

    assert result.content[0].text == "echo"
    posts = [r for r in raw.requests if r[0] == "POST" and r[3]]
    by_method = {r[3]["method"]: r[2] for r in posts}
    assert by_method["initialize"]["authorization"] == _AUTH
    assert by_method["tools/call"]["authorization"] == _AUTH
    # Added by the SDK after the handshake, not by us.
    assert by_method["tools/call"]["mcp-protocol-version"] == "2025-11-25"


@pytest.mark.parametrize(
    ("kind", "code", "followed"),
    [
        ("cross", 301, False),
        ("cross", 302, False),
        # The SSRF property that matters: a cross-origin 307/308 is NOT followed.
        ("cross", 307, False),
        ("cross", 308, False),
        ("same", 301, False),
        ("same", 302, False),
        # Contradicts PRD-023 T8 ("redirects are not followed"): the SDK ignores
        # `follow_redirects` and replays the POST for a same-origin 307/308.
        ("same", 307, True),
        ("same", 308, True),
    ],
)
def test_redirects_cross_origin_and_301_302_not_followed_same_origin_307_308_followed(
    raw_servers, kind, code, followed
):
    other = raw_servers()
    raw = raw_servers(other=other)
    url = f"http://127.0.0.1:{raw.port}/redir?code={code}&kind={kind}"

    async def body(session):
        return None

    leaves = _leaves_of(lambda: _with_session(url, body))

    assert other.requests == []  # the other origin is never contacted
    reached_target = any(r[1].startswith("/target") for r in raw.requests)
    assert reached_target is followed
    if not followed:
        assert any(isinstance(e, mcp.MCPError) and "not followed" in str(e) for e in leaves), leaves


def test_per_call_timeout_raises_mcperror_32001_and_sends_cancelled(raw_servers):
    raw = raw_servers()

    async def body(session):
        try:
            await session.call_tool("slow", {}, read_timeout_seconds=0.5)
        except mcp.MCPError as exc:
            error = exc
        else:
            raise AssertionError("slow call did not time out")
        # The session survives: a following call works.
        follow_up = await session.call_tool("echo", {})
        return error, follow_up

    error, follow_up = _run(_with_session(raw.url, body))

    assert error.code == -32001
    assert "timed out" in str(error)
    assert follow_up.content[0].text == "echo"
    # D14 amendment: the SDK itself tells the server to stop; the harness need not.
    assert _wait_until(lambda: "notifications/cancelled" in raw.methods())


def test_sampling_request_without_callback_is_answered_32600_not_32601(raw_servers):
    """T12/D16 amendment: with no callback registered the SDK answers -32600."""
    raw = raw_servers()

    async def body(session):
        return await session.call_tool("sample", {})

    result = _run(_with_session(raw.url, body))

    assert result.content[0].text == "sample"  # the call itself still completes
    reply = raw.sampling_reply
    assert reply["id"] == 77
    assert reply["error"]["code"] == -32600
    assert "Sampling not supported" in reply["error"]["message"]


def test_tools_list_cursor_pagination(raw_servers):
    raw = raw_servers()

    async def body(session):
        first = await session.list_tools()
        second = await session.list_tools(params=mcp_types_compat.PaginatedRequestParams(cursor=first.next_cursor))
        return first, second

    first, second = _run(_with_session(raw.url, body))

    assert first.next_cursor == "c2"
    assert second.next_cursor is None
    list_bodies = [r[3] for r in raw.requests if r[3] and r[3].get("method") == "tools/list"]
    assert (list_bodies[1].get("params") or {}).get("cursor") == "c2"


def _modern_app():
    import mcp_types as T
    from mcp.server import Server

    async def on_list_tools(ctx, params):
        return T.ListToolsResult(tools=[T.Tool(name="ask", input_schema={"type": "object"})])

    async def on_call_tool(ctx, params):
        return T.InputRequiredResult(
            input_requests={
                "k": T.ElicitRequest(
                    params=T.ElicitRequestFormParams(message="m", requested_schema={"type": "object", "properties": {}})
                )
            },
            request_state="s",
        )

    return Server("low", on_list_tools=on_list_tools, on_call_tool=on_call_tool).streamable_http_app()


def test_modern_session_discover_and_input_required_surfaces(sdk_app_server):
    url = sdk_app_server(_modern_app())

    async def go():
        async def body(session):
            discovered = await session.discover()
            version = session.protocol_version
            try:
                await session.call_tool("ask", {})
            except RuntimeError as exc:
                default_error = exc
            else:
                raise AssertionError("input_required was swallowed")
            flagged = await session.call_tool("ask", {}, allow_input_required=True)
            return discovered, version, default_error, flagged

        return await _with_session(url, body, initialize=False)

    discovered, version, default_error, flagged = _run(go())

    assert version == "2026-07-28"
    assert discovered is not None
    assert "allow_input_required" in str(default_error)
    assert flagged.request_state == "s"
    assert "k" in flagged.input_requests


def test_input_required_on_a_handshake_session_is_a_validation_error(raw_servers):
    from pydantic import ValidationError

    raw = raw_servers()

    async def body(session):
        return await session.call_tool("mrtr", {})

    leaves = _leaves_of(lambda: _with_session(raw.url, body))

    assert any(isinstance(e, ValidationError) for e in leaves), leaves
