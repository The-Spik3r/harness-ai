"""PRD-023 STORY-009: the scripted stub MCP server and its fixtures.

Real subprocess, real SDK client, real HTTP: no `TestClient`, no `app/`, no
database. Stubs run on ports picked at runtime and are stopped by the fixtures.

    AC 1  the nine tools and the sampling trigger
    AC 2  per-tool counts, `Authorization` and header names, no argument logging
    AC 3  the fixture is ready when handed over and always stopped
    AC 4  nothing under `app/` imports the stub
"""

import ast
import asyncio
import importlib.util
import time
from pathlib import Path

import httpx
import httpx2
import pytest

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import CreateMessageResult, PaginatedRequestParams, TextContent

from tests.e2e._live import port_closed_within
from tests.mcp_stub import INJECTION_PHRASE, SCRIPT, start_stub

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEADLINE = 20

_NINE = {
    "query",
    "push_files",
    "create_branch",
    "create_pull_request",
    "slow",
    "huge",
    "inject",
    "poisoned",
    "sample",
}


def _run(coro, timeout=40):
    return asyncio.run(asyncio.wait_for(coro, timeout))


async def _with_session(url, body, *, headers=None, **session_kwargs):
    async with httpx2.AsyncClient(headers=headers, timeout=_DEADLINE) as http:
        async with streamable_http_client(url, http_client=http) as (read, write):
            async with ClientSession(read, write, **session_kwargs) as session:
                await session.initialize()
                return await body(session)


def _text(result) -> str:
    return result.content[0].text


def _load_script():
    spec = importlib.util.spec_from_file_location("stub_mcp_server_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- AC 1 ---------------------------------------------------------------------


def test_lists_the_scripted_tools(mcp_stub):
    async def body(session):
        return (await session.list_tools()).tools

    tools = _run(_with_session(mcp_stub.url, body))

    assert {t.name for t in tools} == _NINE
    assert len(tools) == 9
    with_phrase = [t.name for t in tools if INJECTION_PHRASE in (t.description or "")]
    assert with_phrase == ["poisoned"]
    push = next(t for t in tools if t.name == "push_files")
    assert "files" in push.input_schema["properties"]  # the GitHub shape `files[].path` (PRD F12)


def test_huge_returns_requested_size_and_inject_returns_phrase(mcp_stub):
    async def body(session):
        return await session.call_tool("huge", {"size": 250_000}), await session.call_tool("inject", {})

    big, injected = _run(_with_session(mcp_stub.url, body))

    assert _text(big) == "x" * 250_000
    assert _text(injected) == INJECTION_PHRASE


def test_clamp_helper_bounds_sleep_and_size():
    script = _load_script()
    assert script.clamp(-5, 0, 30) == 0
    assert script.clamp(999, 0, 30) == 30
    assert script.clamp(2.5, 0, 30) == 2.5
    assert script.clamp(10**9, 0, script.HUGE_MAX_SIZE) == script.HUGE_MAX_SIZE
    assert script.INJECTION_PHRASE == INJECTION_PHRASE
    assert set(script.TOOL_NAMES) == _NINE


def test_slow_sleeps_for_the_requested_time(mcp_stub):
    async def body(session):
        started = time.monotonic()
        result = await session.call_tool("slow", {"seconds": 0.4})
        return result, time.monotonic() - started

    result, elapsed = _run(_with_session(mcp_stub.url, body))

    assert _text(result) == "done"
    assert elapsed >= 0.25  # lower bound only: CI timing has no upper guarantee


def test_sample_sends_server_to_client_request(mcp_stub):
    async def no_callback(session):
        return await session.call_tool("sample", {"prompt": "hello"})

    refused = _run(_with_session(mcp_stub.url, no_callback))
    # Facts test (STORY-003): the SDK client with no callback answers -32600.
    assert _text(refused).startswith("sampling:error:-32600")
    assert "Sampling not supported" in _text(refused)
    assert mcp_stub.stats()["sampling"] == {"requested": 1, "last_kind": "error"}

    seen = []

    async def callback(context, params):
        seen.append(params.messages[0].content.text)
        return CreateMessageResult(role="assistant", content=TextContent(type="text", text="fixed"), model="m")

    mcp_stub.reset()
    answered = _run(_with_session(mcp_stub.url, no_callback, sampling_callback=callback))
    assert _text(answered).startswith("sampling:result:")
    assert seen == ["hello"]
    assert mcp_stub.stats()["sampling"] == {"requested": 1, "last_kind": "result"}


# --- AC 2 ---------------------------------------------------------------------


def test_calls_are_counted_per_tool_and_reset(mcp_stub):
    async def body(session):
        await session.call_tool("query", {"sql": "SELECT 1"})
        await session.call_tool("query", {"sql": "SELECT 2"})
        await session.call_tool("create_branch", {"branch": "b"})

    _run(_with_session(mcp_stub.url, body))

    assert mcp_stub.stats()["calls"] == {"query": 2, "create_branch": 1}
    assert mcp_stub.calls("query") == 2
    assert mcp_stub.calls("push_files") == 0
    mcp_stub.reset()
    assert mcp_stub.stats()["calls"] == {}


def test_side_channel_records_authorization_and_header_names_never_arguments(mcp_stub):
    async def body(session):
        return await session.call_tool("query", {"sql": "SELECT secret_marker"})

    _run(_with_session(mcp_stub.url, body, headers={"Authorization": "Bearer t-1", "X-Probe": "1"}))

    stats = mcp_stub.stats()
    assert stats["last_authorization"] == "Bearer t-1"
    assert stats["header_names"] == sorted(stats["header_names"])
    assert "x-probe" in stats["header_names"]
    assert "secret_marker" not in str(stats)
    assert "secret_marker" not in mcp_stub.log_text()
    assert "tool=query" in mcp_stub.log_text()


def test_require_bearer_and_require_header_answer_401_and_count_zero(mcp_stub_factory):
    stub = mcp_stub_factory(name="gated", bearer="s3cret", headers=["X-Org=acme"])
    init = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}},
    }
    accept = {"Accept": "application/json, text/event-stream"}

    def post(headers):
        return httpx.post(stub.url, json=init, headers={**accept, **headers}, timeout=10, trust_env=False)

    assert post({}).status_code == 401
    assert post({"Authorization": "Bearer wrong", "X-Org": "acme"}).status_code == 401
    assert post({"Authorization": "Bearer s3cret"}).status_code == 401  # header missing
    assert post({"Authorization": "Bearer s3cret", "X-Org": "other"}).status_code == 401
    assert stub.stats()["unauthorized"] == 4
    assert stub.stats()["calls"] == {}

    good = {"Authorization": "Bearer s3cret", "X-Org": "acme"}
    assert post(good).status_code == 200

    async def body(session):
        return len((await session.list_tools()).tools)

    assert _run(_with_session(stub.url, body, headers=good)) == 9
    assert stub.stats()["unauthorized"] == 4


# --- AC 3 ---------------------------------------------------------------------


def test_pagination_page_size_and_next_cursor(mcp_stub_factory):
    stub = mcp_stub_factory(name="paged", page_size=3)

    async def body(session):
        pages, cursor = [], None
        while True:
            params = PaginatedRequestParams(cursor=cursor) if cursor else None
            page = await session.list_tools(params=params)
            pages.append(page)
            cursor = page.next_cursor
            if not cursor:
                return pages

    pages = _run(_with_session(stub.url, body))

    assert [len(p.tools) for p in pages] == [3, 3, 3]
    assert [p.next_cursor for p in pages][-1] is None
    assert all(p.next_cursor for p in pages[:-1])
    assert {t.name for p in pages for t in p.tools} == _NINE


def test_two_stubs_in_one_test_have_separate_counters_and_names(mcp_stub_factory):
    github = mcp_stub_factory(name="github")
    postgres = mcp_stub_factory(name="postgres-staging")
    assert github.port != postgres.port

    async def body(session):
        await session.call_tool("create_branch", {"branch": "b"})

    _run(_with_session(github.url, body))

    assert github.stats()["name"] == "github" and postgres.stats()["name"] == "postgres-staging"
    assert github.calls("create_branch") == 1
    assert postgres.calls("create_branch") == 0


def test_teardown_leaves_no_orphan(tmp_path):
    handle = start_stub(tmp_path, name="orphan-check")
    assert handle.proc.poll() is None
    handle.stop()
    assert handle.proc.poll() is not None
    assert port_closed_within(handle.port, 5)
    handle.stop()  # idempotent


_COLLECTED = []


def test_fixture_hands_over_a_ready_stub_and_records_it(mcp_stub):
    assert mcp_stub.stats()["calls"] == {}
    _COLLECTED.append(mcp_stub)


def test_fixture_stopped_the_previous_stub():
    # Runs after the test above (file order): its fixture teardown has run.
    assert _COLLECTED, "the previous test did not run"
    for handle in _COLLECTED:
        assert handle.proc.poll() is not None
        assert port_closed_within(handle.port, 5)


# --- AC 4 ---------------------------------------------------------------------


def test_nothing_under_app_imports_the_stub():
    forbidden = ("stub_mcp_server", "scripts.stub_mcp_server", "tests.mcp_stub")
    offenders = []
    for path in (_REPO_ROOT / "app").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""] + [f"{node.module}.{a.name}" for a in node.names]
            if any(n in forbidden or n.endswith(".stub_mcp_server") for n in names):
                offenders.append(str(path.relative_to(_REPO_ROOT)))
    assert offenders == []


def test_the_script_imports_nothing_from_app():
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert not any(a.name == "app" or a.name.startswith("app.") for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            assert node.module != "app" and not node.module.startswith("app.")
