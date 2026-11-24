"""PRD-023 STORY-010: the southbound MCP client (`app/services/mcp_upstream.py`).

Everything runs against the STORY-009 stub subprocess (`mcp_stub_factory`), on
127.0.0.1 with runtime ports. No database, no Docker (nothing here is marked
`db`). The repo has no pytest-asyncio, so each test is sync and drives one
`asyncio.run(...)`; `_go` bounds it with `wait_for` and always runs
`aclose_all()` in `finally`, so a broken owner task fails a test instead of
hanging pytest.
"""

import asyncio
import inspect
import json
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from mcp import ClientSession
from mcp.types import CallToolResult, ListToolsResult, TextContent

from app.config import settings
from app.services import mcp_config, mcp_upstream
from app.services.mcp_config import McpAuth, McpConfig, McpServer
from tests._caddy import free_port

TOKEN = "sentinel-TOKEN-9f3a1c"
_BOUND = 60  # seconds for one test's whole event loop; generous for CI


def _go(coro_factory, bound=_BOUND):
    """Run `await coro_factory()` on a fresh loop, bounded, and always close every session."""

    async def main():
        try:
            return await asyncio.wait_for(coro_factory(), bound)
        finally:
            await mcp_upstream.aclose_all()

    return asyncio.run(main())


def _cfg(monkeypatch, *servers):
    """Put a config in force. Each entry: (id, stub-or-url, auth, timeout_seconds)."""
    built = {}
    for sid, target, auth, timeout in servers:
        url = target if isinstance(target, str) else target.url
        built[sid] = McpServer(sid, url, True, auth, timeout, 1_048_576)
    monkeypatch.setattr(mcp_config, "_config", McpConfig(servers=built))


def _bearer(secret=TOKEN):
    return McpAuth(type="bearer", env_name="X", _secret=secret)


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    mcp_upstream.invalidate_tools_cache()
    monkeypatch.setattr(mcp_upstream, "_state", None)
    monkeypatch.setattr(mcp_upstream, "_now", time.monotonic)
    yield
    mcp_upstream.invalidate_tools_cache()


def _wait_for_calls(stub, tool, count=1, deadline=15.0):
    end = time.monotonic() + deadline
    while stub.calls(tool) < count:
        assert time.monotonic() < end, f"{tool} never reached the stub"
        time.sleep(0.05)


# --- AC 1: credentials ---------------------------------------------------------


def test_bearer_and_header_auth_come_only_from_config(mcp_stub_factory, monkeypatch):
    bearer_stub = mcp_stub_factory(name="b", bearer=TOKEN)
    header_stub = mcp_stub_factory(name="h", headers=["X-Org=acme"])
    _cfg(
        monkeypatch,
        ("b", bearer_stub, _bearer(), 30),
        ("h", header_stub, McpAuth(type="header", env_name="V", header_name="X-Org", _secret="acme"), 30),
    )

    async def body():
        a = await mcp_upstream.list_tools("b", "u1")
        c = await mcp_upstream.call_tool("b", "u1", "query", {"sql": "select 1"})
        d = await mcp_upstream.call_tool("h", "u1", "query", {"sql": "select 1"})
        return a, c, d

    tools, called, header_called = _go(body)

    assert len(tools) == 9 and called.outcome == "ok" and header_called.outcome == "ok"
    stats = bearer_stub.stats()
    assert stats["last_authorization"] == f"Bearer {TOKEN}"
    assert stats["unauthorized"] == 0
    assert "cookie" not in stats["header_names"]
    assert header_stub.stats()["unauthorized"] == 0


def test_wrong_token_is_upstream_error_and_list_raises(mcp_stub_factory, monkeypatch):
    stub = mcp_stub_factory(bearer=TOKEN)
    _cfg(monkeypatch, ("gh", stub, _bearer("wrong"), 30))

    async def body():
        outcome = await mcp_upstream.call_tool("gh", "u1", "query", {"sql": "x"})
        with pytest.raises(mcp_upstream.McpUpstreamError) as err:
            await mcp_upstream.list_tools("gh", "u1")
        return outcome, str(err.value)

    outcome, message = _go(body)

    assert outcome.outcome == "upstream_error"
    assert stub.stats()["unauthorized"] >= 1
    assert stub.calls("query") == 0
    assert "gh" in message and "wrong" not in message and "http" not in message


def test_public_api_accepts_no_headers():
    for fn in (mcp_upstream.list_tools, mcp_upstream.call_tool):
        names = set(inspect.signature(fn).parameters)
        assert not [n for n in names if "header" in n or "auth" in n or "url" in n or "cred" in n], names


def test_sentinel_token_never_logged_or_returned(mcp_stub_factory, monkeypatch, caplog):
    good = mcp_stub_factory(name="g", bearer=TOKEN)
    bad = mcp_stub_factory(name="x", bearer="other")
    _cfg(monkeypatch, ("g", good, _bearer(), 30), ("x", bad, _bearer(), 30))
    caplog.set_level(logging.DEBUG)

    async def body():
        seen = [
            await mcp_upstream.list_tools("g", "u1"),
            await mcp_upstream.call_tool("g", "u1", "query", {"sql": "x"}),
            await mcp_upstream.call_tool("g", "u1", "slow", {"seconds": 5}, timeout_seconds=0.5),
            await mcp_upstream.call_tool("x", "u1", "query", {"sql": "x"}),
        ]
        try:
            await mcp_upstream.list_tools("x", "u1")
        except mcp_upstream.McpUpstreamError as exc:
            seen.append(exc)
            seen.append(repr(exc))
        return seen

    seen = _go(body)

    assert [o.outcome for o in seen[1:4]] == ["ok", "timeout", "upstream_error"]
    blob = caplog.text + repr(seen) + "".join(str(o) for o in seen)
    # (the stub's own `WWW-Authenticate: Bearer` shows in httpcore debug traces; the secret must not)
    assert TOKEN not in blob and f"Bearer {TOKEN}" not in blob
    assert "other" not in " ".join(o.detail for o in seen[1:4])


# --- AC 2: sessions, reuse, expiry, no replay ----------------------------------


def test_sessions_keyed_by_server_and_user(mcp_stub_factory, monkeypatch):
    stub = mcp_stub_factory()
    _cfg(monkeypatch, ("gh", stub, McpAuth(type="none"), 30))

    async def body():
        await mcp_upstream.call_tool("gh", "u1", "query", {"sql": "1"})
        await mcp_upstream.call_tool("gh", "u1", "query", {"sql": "2"})
        first = stub.stats()["initializes"]
        await mcp_upstream.call_tool("gh", "u2", "query", {"sql": "3"})
        return first, stub.stats()["initializes"]

    assert _go(body) == (1, 2)


def test_idle_session_is_reaped(mcp_stub_factory, monkeypatch):
    stub = mcp_stub_factory()
    _cfg(monkeypatch, ("gh", stub, McpAuth(type="none"), 30))
    monkeypatch.setattr(settings, "MCP_UPSTREAM_SESSION_IDLE_SECONDS", 30)
    clock = [1000.0]
    monkeypatch.setattr(mcp_upstream, "_now", lambda: clock[0])

    async def body():
        await mcp_upstream.call_tool("gh", "u1", "query", {"sql": "1"})
        clock[0] += 10
        await mcp_upstream.call_tool("gh", "u1", "query", {"sql": "2"})
        same = stub.stats()["initializes"]
        clock[0] += 31
        result = await mcp_upstream.call_tool("gh", "u1", "query", {"sql": "3"})
        return same, stub.stats()["initializes"], result.outcome

    assert _go(body) == (1, 2, "ok")


def test_unknown_session_reinitializes_next_call_without_replay(mcp_stub_factory, monkeypatch):
    """T10 (amended): the dropped call is reported, not replayed; the next call re-initializes."""
    stub = mcp_stub_factory()
    _cfg(monkeypatch, ("gh", stub, McpAuth(type="none"), 30))

    async def body():
        assert (await mcp_upstream.call_tool("gh", "u1", "query", {"sql": "1"})).outcome == "ok"
        stub.expire_sessions()
        dropped = await mcp_upstream.call_tool("gh", "u1", "create_branch", {"branch": "b"})
        after = await mcp_upstream.call_tool("gh", "u1", "query", {"sql": "2"})
        return dropped, after

    dropped, after = _go(body)

    assert dropped.outcome == "upstream_error"
    assert "may have run" in dropped.detail
    assert stub.calls("create_branch") == 0 and stub.stats()["session_404"] == 1
    assert after.outcome == "ok"
    assert stub.stats()["initializes"] == 2


def test_list_tools_retries_once_on_a_dropped_session(mcp_stub_factory, monkeypatch):
    stub = mcp_stub_factory()
    _cfg(monkeypatch, ("gh", stub, McpAuth(type="none"), 30))
    monkeypatch.setattr(settings, "MCP_TOOLS_CACHE_SECONDS", 0)

    async def body():
        await mcp_upstream.call_tool("gh", "u1", "query", {"sql": "1"})
        stub.expire_sessions()
        return await mcp_upstream.list_tools("gh", "u1")

    tools = _go(body)

    assert len(tools) == 9
    assert stub.stats()["initializes"] == 2


# --- AC 3: timeouts and cancellation -------------------------------------------


def test_timeout_outcome_and_slow_counted_once(mcp_stub_factory, monkeypatch):
    stub = mcp_stub_factory()
    _cfg(monkeypatch, ("gh", stub, McpAuth(type="none"), 30))

    async def body():
        started = time.monotonic()
        outcome = await mcp_upstream.call_tool("gh", "u1", "slow", {"seconds": 5}, timeout_seconds=0.5)
        elapsed = time.monotonic() - started
        follow_up = await mcp_upstream.call_tool("gh", "u1", "query", {"sql": "1"})
        return outcome, elapsed, follow_up

    outcome, elapsed, follow_up = _go(body)

    assert outcome.outcome == "timeout" and "may have run" in outcome.detail
    assert elapsed < 4.5  # the 5s tool did not finish first
    assert stub.calls("slow") == 1  # never replayed
    assert follow_up.outcome == "ok" and stub.stats()["initializes"] == 1  # the session survived


def test_caller_cancel_keeps_session(mcp_stub_factory, monkeypatch):
    stub = mcp_stub_factory()
    _cfg(monkeypatch, ("gh", stub, McpAuth(type="none"), 30))

    async def body():
        task = asyncio.create_task(mcp_upstream.call_tool("gh", "u1", "slow", {"seconds": 5}))
        end = time.monotonic() + 15
        while stub.calls("slow") < 1:
            assert time.monotonic() < end
            await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        return await mcp_upstream.call_tool("gh", "u1", "query", {"sql": "1"})

    assert _go(body).outcome == "ok"
    assert stub.stats()["initializes"] == 1


def test_concurrent_calls_do_not_block_each_other(mcp_stub_factory, monkeypatch):
    stub = mcp_stub_factory()
    _cfg(monkeypatch, ("gh", stub, McpAuth(type="none"), 30))

    async def body():
        order = []

        async def run(tag, tool, args):
            outcome = await mcp_upstream.call_tool("gh", "u1", tool, args)
            order.append(tag)
            return outcome

        a, b = await asyncio.gather(run("slow", "slow", {"seconds": 1.5}), run("query", "query", {"sql": "1"}))
        return order, a, b

    order, slow, query = _go(body)

    assert slow.outcome == "ok" and query.outcome == "ok"
    assert order == ["query", "slow"]


# --- AC 4: refused capabilities, redirects, failure shapes ---------------------


def test_sampling_refused_and_no_callbacks(mcp_stub_factory, monkeypatch):
    stub = mcp_stub_factory()
    _cfg(monkeypatch, ("gh", stub, McpAuth(type="none"), 30))
    captured = {}

    class Spy(ClientSession):
        def __init__(self, *args, **kwargs):
            captured["kwargs"] = kwargs
            captured["positional"] = args
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(mcp_upstream, "ClientSession", Spy)

    outcome = _go(lambda: mcp_upstream.call_tool("gh", "u1", "sample", {"prompt": "hi"}))

    assert outcome.outcome == "ok"
    assert "-32600" in outcome.content[0]["text"]
    assert stub.stats()["sampling"] == {"requested": 1, "last_kind": "error"}
    assert set(captured["kwargs"]) == {"read_timeout_seconds"}  # no sampling/roots/elicitation/logging/message
    assert len(captured["positional"]) == 2  # (read, write) only


class _Redirector:
    """A tiny server that answers every request with a 302 to `target`, recording hits."""

    def __init__(self, target=None):
        self.hits = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def _answer(self):
                outer.hits.append((self.command, self.path))
                length = int(self.headers.get("content-length") or 0)
                if length:
                    self.rfile.read(length)
                if outer.target:
                    self.send_response(302)
                    self.send_header("location", outer.target)
                else:
                    self.send_response(200)
                self.send_header("content-length", "0")
                self.end_headers()

            do_POST = do_GET = do_DELETE = _answer

            def log_message(self, *args):
                pass

        self.target = target
        self.port = free_port()
        self.server = ThreadingHTTPServer(("127.0.0.1", self.port), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5)


def test_redirect_not_followed(monkeypatch):
    second = _Redirector()
    first = _Redirector(target=f"http://127.0.0.1:{second.port}/mcp")
    try:
        _cfg(monkeypatch, ("gh", f"http://127.0.0.1:{first.port}/mcp", McpAuth(type="none"), 10))
        outcome = _go(lambda: mcp_upstream.call_tool("gh", "u1", "query", {"sql": "1"}))
    finally:
        first.stop()
        second.stop()

    assert outcome.outcome == "upstream_error"
    assert first.hits and second.hits == []  # the redirect target is never contacted
    assert str(second.port) not in outcome.detail


def test_input_required_and_session_errors_become_upstream_error(mcp_stub_factory, monkeypatch):
    stub = mcp_stub_factory()
    _cfg(monkeypatch, ("gh", stub, McpAuth(type="none"), 30))
    calls = []

    class Spy(ClientSession):
        async def call_tool(self, name, *args, **kwargs):
            calls.append(name)
            if name == "create_branch":
                raise RuntimeError("input_required with https://secret.example/path")
            return await super().call_tool(name, *args, **kwargs)

    monkeypatch.setattr(mcp_upstream, "ClientSession", Spy)

    async def body():
        refused = await mcp_upstream.call_tool("gh", "u1", "create_branch", {"branch": "b"})
        after = await mcp_upstream.call_tool("gh", "u1", "query", {"sql": "1"})
        return refused, after

    refused, after = _go(body)

    assert refused.outcome == "upstream_error"
    assert "secret.example" not in refused.detail and "RuntimeError" in refused.detail
    assert after.outcome == "ok"
    assert stub.stats()["initializes"] == 1  # input_required keeps the session (T12)


def test_closed_port_and_unconfigured_server_never_raise(monkeypatch):
    _cfg(monkeypatch, ("gh", f"http://127.0.0.1:{free_port()}/mcp", McpAuth(type="none"), 5))

    async def body():
        closed = await mcp_upstream.call_tool("gh", "u1", "query", {})
        unknown = await mcp_upstream.call_tool("nope", "u1", "query", {})
        leftover = dict(mcp_upstream._state.owners)
        with pytest.raises(mcp_upstream.McpUpstreamError):
            await mcp_upstream.list_tools("gh", "u1")
        with pytest.raises(mcp_upstream.McpUpstreamError):
            await mcp_upstream.list_tools("nope", "u1")
        return closed, unknown, leftover

    closed, unknown, leftover = _go(body)

    assert closed.outcome == "upstream_error" and unknown.outcome == "upstream_error"
    assert "127.0.0.1" not in closed.detail and "http" not in closed.detail
    assert leftover == {}


def test_tool_error_result_maps_to_error_outcome():
    result = CallToolResult(content=[TextContent(type="text", text="boom")], is_error=True)

    mapped = mcp_upstream._outcome_from_sdk(result)

    assert mapped.outcome == "error" and mapped.is_error is True
    assert mapped.content == [{"type": "text", "text": "boom"}]
    ok = mcp_upstream._outcome_from_sdk(CallToolResult(content=[TextContent(type="text", text="fine")]))
    assert ok.outcome == "ok" and ok.is_error is False and ok.structured is None


# --- AC 5: pagination and the tools cache --------------------------------------


def test_pagination_reads_all_pages(mcp_stub_factory, monkeypatch):
    stub = mcp_stub_factory(page_size=3)
    _cfg(monkeypatch, ("gh", stub, McpAuth(type="none"), 30))
    pages = []

    class Spy(ClientSession):
        async def list_tools(self, *args, **kwargs):
            pages.append(kwargs.get("params"))
            return await super().list_tools(*args, **kwargs)

    monkeypatch.setattr(mcp_upstream, "ClientSession", Spy)

    tools = _go(lambda: mcp_upstream.list_tools("gh", "u1"))

    assert len(tools) == 9 and len({t.name for t in tools}) == 9
    assert len(pages) == 3
    assert isinstance(tools[0], mcp_upstream.UpstreamTool) and tools[0].input_schema


def test_looping_cursor_is_a_hostile_server(mcp_stub_factory, monkeypatch):
    stub = mcp_stub_factory()
    _cfg(monkeypatch, ("gh", stub, McpAuth(type="none"), 30))

    class Looping(ClientSession):
        async def list_tools(self, *args, **kwargs):
            return ListToolsResult(tools=[], next_cursor="again")

    monkeypatch.setattr(mcp_upstream, "ClientSession", Looping)

    async def body():
        with pytest.raises(mcp_upstream.McpUpstreamError):
            await mcp_upstream.list_tools("gh", "u1")

    _go(body)


def test_tools_cache_ttl_zero_and_invalidate(mcp_stub_factory, monkeypatch):
    stub = mcp_stub_factory()
    _cfg(monkeypatch, ("gh", stub, McpAuth(type="none"), 30))
    clock = [500.0]
    monkeypatch.setattr(mcp_upstream, "_now", lambda: clock[0])
    fetches = []
    real = mcp_upstream._read_all_tools

    async def counting(session, server_id):
        fetches.append(server_id)
        return await real(session, server_id)

    monkeypatch.setattr(mcp_upstream, "_read_all_tools", counting)
    monkeypatch.setattr(settings, "MCP_TOOLS_CACHE_SECONDS", 60)

    async def body():
        await mcp_upstream.list_tools("gh", "u1")
        await mcp_upstream.list_tools("gh", "u2")  # shared across users
        cached = len(fetches)
        clock[0] += 61
        await mcp_upstream.list_tools("gh", "u1")
        expired = len(fetches)
        mcp_upstream.invalidate_tools_cache("gh")
        await mcp_upstream.list_tools("gh", "u1")
        invalidated = len(fetches)
        monkeypatch.setattr(settings, "MCP_TOOLS_CACHE_SECONDS", 0)
        await mcp_upstream.list_tools("gh", "u1")
        await mcp_upstream.list_tools("gh", "u1")
        return cached, expired, invalidated, len(fetches)

    assert _go(body) == (1, 2, 3, 5)


def test_aclose_all_leaves_no_owner_task(mcp_stub_factory, monkeypatch):
    stub = mcp_stub_factory()
    _cfg(monkeypatch, ("gh", stub, McpAuth(type="none"), 30))

    async def body():
        # PRD-023 STORY-010 (fix after CI 45202980149): on Python 3.11 `wait_for`
        # runs this body in a child task, so `_go`'s `main` is a live parent here.
        # Only tasks created after this point count.
        before = asyncio.all_tasks()
        await mcp_upstream.call_tool("gh", "u1", "query", {"sql": "1"})
        await mcp_upstream.call_tool("gh", "u2", "query", {"sql": "2"})
        assert len(mcp_upstream._state.owners) == 2
        await mcp_upstream.aclose_all()
        await mcp_upstream.aclose_all()  # idempotent
        # PRD-023 STORY-010 (fix after CI 45199692297): SDK/httpx helper tasks
        # may still be finishing their teardown when aclose_all returns; on a
        # slow runner a snapshot caught one mid-exit. Give them a bounded grace,
        # then require that nothing is left pending.
        others = [t for t in asyncio.all_tasks() - before if t is not asyncio.current_task()]
        if others:
            await asyncio.wait(others, timeout=5)
        return [t for t in others if not t.done()]

    assert _go(body) == []


def test_end_to_end_list_then_call_against_a_bearer_stub(mcp_stub_factory, monkeypatch):
    """The plan's E2E: a real stub process, a bearer, list then call, then close."""
    stub = mcp_stub_factory(bearer=TOKEN)
    _cfg(monkeypatch, ("gh", stub, _bearer(), 30))

    async def body():
        tools = await mcp_upstream.list_tools("gh", "u1")
        outcome = await mcp_upstream.call_tool("gh", "u1", "query", {"sql": "select 1"})
        return tools, outcome

    tools, outcome = _go(body)

    assert "query" in {t.name for t in tools}
    assert outcome.outcome == "ok" and json.dumps(outcome.content).count("rows: 1") == 1
    assert stub.calls("query") == 1


# --- Large results and the SDK's SSE event cap (PRD-023 T15; STORY-021 manual run) -----


def _cfg_capped(monkeypatch, stub, max_result_bytes):
    server = McpServer("gh", stub.url, True, McpAuth(type="none"), 30, max_result_bytes)
    monkeypatch.setattr(mcp_config, "_config", McpConfig(servers={"gh": server}))


def test_sse_event_limit_follows_max_result_bytes():
    from mcp.client.streamable_http import DEFAULT_MAX_SSE_EVENT_SIZE

    # Never below the SDK default; room for the result twice over, JSON-escaped.
    assert mcp_upstream.sse_event_limit(1024) == DEFAULT_MAX_SSE_EVENT_SIZE
    assert mcp_upstream.sse_event_limit(1_048_576) == 8 * 1_048_576 + 64 * 1024


def test_a_result_under_the_cap_but_over_the_sdk_default_event_arrives(mcp_stub_factory, monkeypatch):
    # PRD-023 STORY-021 manual run: `huge` of 600 KB (sent as content + structuredContent, ~1.2 MB
    # on the wire) under the 1 MiB default cap came back `upstream_error` "may have run", because
    # the SDK's own 1 MiB SSE event limit was hit first.
    stub = mcp_stub_factory()
    _cfg_capped(monkeypatch, stub, 1_048_576)

    outcome = _go(lambda: mcp_upstream.call_tool("gh", "u1", "huge", {"size": 600_000}))

    assert outcome.outcome == "ok"
    assert len(outcome.content[0]["text"]) == 600_000


def test_an_event_over_the_transport_cap_is_too_large_and_keeps_the_session(mcp_stub_factory, monkeypatch):
    # Cap 2048 -> event limit is the SDK default (1 MiB); ~1.2 MB on the wire exceeds it. The call
    # ran, so it is `too_large` (recorded `result_too_large`), never `upstream_error`.
    stub = mcp_stub_factory()
    _cfg_capped(monkeypatch, stub, 2048)

    async def body():
        big = await mcp_upstream.call_tool("gh", "u1", "huge", {"size": 600_000})
        follow_up = await mcp_upstream.call_tool("gh", "u1", "query", {"sql": "1"})
        return big, follow_up

    big, follow_up = _go(body)

    assert big.outcome == "too_large" and "the call ran" in big.detail
    assert stub.calls("huge") == 1  # never replayed
    assert follow_up.outcome == "ok" and stub.stats()["initializes"] == 1  # the session survived
