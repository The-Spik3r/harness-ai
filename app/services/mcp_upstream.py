"""The southbound MCP client: the harness as a client of upstream servers (PRD-023 STORY-010).

The ONE module that imports the `mcp` SDK and `httpx2` (T17, enforced by
`tests/test_mcp_upstream_import_graph.py`). Everything it returns is plain
data (`UpstreamTool`, `CallOutcome`), so the gateway (STORY-012/013) never sees
an SDK type.

Public API (all async, none accepts a header, a URL or a credential):

- `list_tools(server_id, user_id)`: the upstream's tools, every page read,
  cached per server for `MCP_TOOLS_CACHE_SECONDS` (0 = never cached). Raises
  `McpUpstreamError` when the server cannot be listed.
- `call_tool(server_id, user_id, tool, arguments, *, timeout_seconds=None)`:
  one `tools/call`, returned as a `CallOutcome`. It never raises for an
  upstream failure, and it is NEVER replayed (T10): after a timeout or a
  dropped session the call may have run, and the caller decides what to say.
- `aclose_all()` and `invalidate_tools_cache()`: shutdown and a test hook.

How it holds the line:

- **Credentials (D10, T2, T16).** Headers come only from
  `mcp_config.upstream_auth_headers(server_id)`, set once on the
  `httpx2.AsyncClient` when a session is created. No inbound header is
  forwarded, no public parameter takes one, no `detail` or log line carries a
  URL, header name, env name or exception text (only the exception class and
  an MCP error code). Redirects are not followed by httpx2; the SDK refuses
  cross-origin and 301/302 itself and follows a same-origin 307/308 (T8, as
  measured in `tests/test_prd023_mcp_sdk_facts.py`).
- **No capabilities (T12, D16).** The `ClientSession` gets no sampling, roots,
  elicitation, logging or message callback, so the SDK answers a server's
  `sampling/createMessage` with `-32600` and declares nothing at `initialize`.
  `input_required` surfaces as an error from the SDK and becomes
  `upstream_error`.
- **Sessions.** One per `(server_id, user_id)`, owned by one asyncio task: the
  SDK's anyio cancel scopes must be entered and exited in the same task, so a
  caller never touches the session; it queues a request and awaits a future.
  A session ends after `MCP_UPSTREAM_SESSION_IDLE_SECONDS` of disuse or on any
  session-level error (HTTP failure, the SDK's "Session terminated" for an
  expired id, a closed stream); the next call re-initializes. A timeout does
  not end a session. `list_tools` (read-only) retries once on a session that
  was dropped under it; `call_tool` never does.
- **Timeouts (D14).** The per-call timeout is the SDK's `read_timeout_seconds`
  (`MCPError` -32001); the SDK sends `notifications/cancelled` itself. The
  caller additionally stops waiting after a bounded guard, so a stuck owner
  task cannot hang a request.

Stated limits: credentials are read when a session is created, so rotating
one needs a restart; the result-size cap is the call path's (STORY-013).

State lives per running event loop (a test's `asyncio.run`, or the server's
loop); a state from another loop is discarded, never awaited.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Literal, Optional

import httpx2
from mcp import ClientSession, MCPError
from mcp.client.streamable_http import DEFAULT_MAX_SSE_EVENT_SIZE, streamable_http_client
from mcp.types import PaginatedRequestParams
from pydantic import ValidationError

from app.config import settings
from app.services import mcp_config

logger = logging.getLogger(__name__)

# `MCPError.code` for a per-call timeout (SDK `REQUEST_TIMEOUT`; pinned in the facts tests).
_TIMEOUT_CODE = -32001
_MAX_PAGES = 100
_MAX_POLL_SECONDS = 1.0
_CLOSE_WAIT_SECONDS = 10.0
_GUARD_SLACK_SECONDS = 5.0
# connect/write/pool are bounded; read is None so httpx never fires before the SDK's own timeout.
_HTTP_TIMEOUT = httpx2.Timeout(connect=10.0, read=None, write=30.0, pool=10.0)

#: Module attribute so tests drive idle and cache expiry with an injected clock.
_now = time.monotonic

# The SDK caps one SSE event at 1 MiB and fails the request beyond it ("SSE stream
# failed: Server-sent event exceeded the N byte limit", `MCPError` -32000). One event
# carries the whole JSON-RPC response: the result can appear twice (`content` and
# `structuredContent`) and JSON escaping grows non-ASCII text up to 6x. So the event
# cap follows the server's `max_result_bytes` with room for both, and the gateway's
# own size check (M9) decides `result_too_large`. An event over even this cap is a
# result over `max_result_bytes`: `too_large`, never `upstream_error` (PRD-023 T15,
# found in the STORY-021 manual run: a 600 KB result under the 1 MiB default cap
# came back as "may have run").
_SSE_EVENT_FACTOR = 8
_SSE_EVENT_SLACK_BYTES = 64 * 1024
_SSE_OVERSIZED_MARKERS = ("SSE stream failed", "exceeded")

Outcome = Literal["ok", "error", "timeout", "upstream_error", "too_large"]


# --- Public data -------------------------------------------------------------


@dataclass(frozen=True)
class UpstreamTool:
    """One tool an upstream advertises, as plain data (JSON-ready dicts)."""

    name: str
    description: str = ""
    input_schema: dict = field(default_factory=dict)
    title: Optional[str] = None
    annotations: Optional[dict] = None
    output_schema: Optional[dict] = None


@dataclass(frozen=True)
class CallOutcome:
    """The result of one `tools/call` (PRD-023 Section 6.3, T10, T12).

    `outcome`: `ok`; `error` (the upstream answered `isError: true`, content
    passed through); `timeout`; `upstream_error` (nothing usable came back).
    `detail` is a credential-safe sentence for `timeout` / `upstream_error`.
    """

    outcome: Outcome
    is_error: bool = False
    content: list = field(default_factory=list)
    structured: Optional[dict] = None
    detail: str = ""


class McpUpstreamError(Exception):
    """`list_tools` could not list a server. The message names the server id and a fixed phrase."""


# --- Internals ---------------------------------------------------------------


class _SessionGone(Exception):
    """The session ended before the request was answered. `sent`: it may have reached the upstream."""

    def __init__(self, reason: str, sent: bool):
        super().__init__(reason)
        self.reason = reason
        self.sent = sent
        self.fresh = False  # set by `_submit`: the session was created for this request


class _Hostile(Exception):
    """The upstream's paging never ends (a repeated cursor or too many pages)."""


_CLOSE = object()


@dataclass
class _Req:
    kind: Literal["list", "call"]
    fut: asyncio.Future
    name: str = ""
    arguments: Optional[dict] = None
    timeout: float = 0.0
    task: Optional[asyncio.Task] = None


@dataclass
class _Session:
    server_id: str
    user_id: str
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    task: Optional[asyncio.Task] = None
    last_used: float = 0.0
    inflight: int = 0
    dying: bool = False  # a session-level error or a close was requested: do not reuse
    closed: bool = False  # the owner has exited: nothing will read the queue
    reason: str = "session closed"


@dataclass
class _State:
    loop: asyncio.AbstractEventLoop
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    owners: dict = field(default_factory=dict)  # (server_id, user_id) -> _Session
    list_locks: dict = field(default_factory=dict)  # server_id -> asyncio.Lock


_state: Optional[_State] = None
_tools_cache: dict = {}  # server_id -> (expires_at, tuple[UpstreamTool, ...])


def _get_state() -> _State:
    global _state
    loop = asyncio.get_running_loop()
    if _state is None or _state.loop is not loop:
        # A state from another loop cannot be awaited from this one; drop it.
        _state = _State(loop)
    return _state


def invalidate_tools_cache(server_id: Optional[str] = None) -> None:
    """Forget the cached `tools/list` of one server, or of all (a test and operator hook)."""
    if server_id is None:
        _tools_cache.clear()
    else:
        _tools_cache.pop(server_id, None)


def _leaves(exc: BaseException) -> list:
    if isinstance(exc, BaseExceptionGroup):
        return [leaf for inner in exc.exceptions for leaf in _leaves(inner)]
    return [exc]


def _describe(exc: BaseException) -> str:
    """The exception class and an MCP code, never its message (httpx messages carry URLs, T16)."""
    leaf = _leaves(exc)[0]
    name = type(leaf).__name__
    if isinstance(leaf, MCPError):
        return f"{name} {leaf.error.code}"
    return name


def _is_timeout(exc: BaseException) -> bool:
    return any(isinstance(leaf, MCPError) and leaf.error.code == _TIMEOUT_CODE for leaf in _leaves(exc))


def _keeps_session(exc: BaseException) -> bool:
    """A failure that leaves the session usable: a timeout, `input_required`/shape errors, hostile paging,
    an oversized result (the SDK abandons that one stream only)."""
    return all(
        isinstance(leaf, (_Hostile, ValidationError, RuntimeError))
        or (isinstance(leaf, MCPError) and leaf.error.code == _TIMEOUT_CODE)
        or _is_oversized_leaf(leaf)
        for leaf in _leaves(exc)
    )


def sse_event_limit(max_result_bytes: int) -> int:
    """The SDK's per-event cap for a server: never below the SDK default, and room for a result of
    `max_result_bytes` twice over and JSON-escaped (see `_SSE_EVENT_FACTOR`)."""
    return max(DEFAULT_MAX_SSE_EVENT_SIZE, _SSE_EVENT_FACTOR * max_result_bytes + _SSE_EVENT_SLACK_BYTES)


def _is_oversized_leaf(leaf: BaseException) -> bool:
    # The SDK turns httpx's SSEError into this MCPError text; the class is not kept (mcp==2.3.0,
    # pinned by tests/test_mcp_upstream.py). The message is matched here and never logged (T16).
    return isinstance(leaf, MCPError) and all(m in str(leaf.error.message) for m in _SSE_OVERSIZED_MARKERS)


def _is_oversized(exc: BaseException) -> bool:
    return any(_is_oversized_leaf(leaf) for leaf in _leaves(exc))


def _tool_from_sdk(tool: Any) -> UpstreamTool:
    data = tool.model_dump(mode="json", by_alias=True, exclude_none=True)
    return UpstreamTool(
        name=data["name"],
        description=data.get("description", ""),
        input_schema=data.get("inputSchema", {}),
        title=data.get("title"),
        annotations=data.get("annotations"),
        output_schema=data.get("outputSchema"),
    )


def _outcome_from_sdk(result: Any) -> CallOutcome:
    data = result.model_dump(mode="json", by_alias=True, exclude_none=True)
    is_error = bool(data.get("isError"))
    return CallOutcome(
        outcome="error" if is_error else "ok",
        is_error=is_error,
        content=data.get("content", []),
        structured=data.get("structuredContent"),
        detail="upstream reported a tool error" if is_error else "",
    )


def _resolve(fut: asyncio.Future, value: Any) -> None:
    if not fut.done():  # the caller may have been cancelled or timed out
        fut.set_result(value)


def _reject(fut: asyncio.Future, exc: BaseException) -> None:
    if not fut.done():
        fut.set_exception(exc)


async def _read_all_tools(session: ClientSession, server_id: str) -> tuple:
    tools: list = []
    seen: set = set()
    cursor: Optional[str] = None
    for _ in range(_MAX_PAGES):
        params = PaginatedRequestParams(cursor=cursor) if cursor else None
        page = await session.list_tools(params=params)
        tools.extend(_tool_from_sdk(t) for t in page.tools)
        cursor = page.next_cursor
        if not cursor:
            return tuple(tools)
        if cursor in seen:
            raise _Hostile("repeated cursor")
        seen.add(cursor)
    raise _Hostile("too many pages")


async def _handle(sess: _Session, session: ClientSession, req: _Req) -> None:
    """Run one request in its own task (a slow call must not block another caller)."""
    try:
        try:
            if req.kind == "call":
                result = await session.call_tool(req.name, req.arguments or {}, read_timeout_seconds=req.timeout)
                _resolve(req.fut, _outcome_from_sdk(result))
            else:
                _resolve(req.fut, await _read_all_tools(session, sess.server_id))
        except asyncio.CancelledError:
            _reject(req.fut, _SessionGone("session closed before the request completed", sent=True))
            raise
        except Exception as exc:  # noqa: BLE001 - every failure becomes an outcome or a typed error
            timed_out = _is_timeout(exc)
            keep = _keeps_session(exc)
            logger.warning(
                "mcp upstream request failed: server=%s user=%s kind=%s error=%s",
                sess.server_id, sess.user_id, req.kind, _describe(exc),
            )
            if not keep:
                _begin_close(sess, f"session failed ({_describe(exc)})")
            if req.kind == "call":
                if _is_oversized(exc):
                    outcome = CallOutcome(
                        "too_large",
                        detail=f"{req.name} on {sess.server_id}: result over the transport cap; the call ran",
                    )
                elif timed_out:
                    outcome = CallOutcome(
                        "timeout",
                        detail=f"{req.name} on {sess.server_id} timed out; it may have run",
                    )
                else:
                    outcome = CallOutcome(
                        "upstream_error",
                        detail=(
                            f"{req.name} on {sess.server_id} failed ({_describe(exc)}); it may have run"
                        ),
                    )
                _resolve(req.fut, outcome)
            elif keep:
                _reject(req.fut, McpUpstreamError(f"MCP server {sess.server_id!r}: tools/list failed"))
            else:
                _reject(req.fut, _SessionGone(f"session failed ({_describe(exc)})", sent=True))
    finally:
        sess.inflight -= 1
        sess.last_used = _now()


def _begin_close(sess: _Session, reason: str) -> None:
    """Mark the session unusable and wake its owner. Idempotent."""
    if not sess.dying:
        sess.dying = True
        sess.reason = reason
    sess.queue.put_nowait(_CLOSE)


async def _serve(sess: _Session, session: ClientSession) -> None:
    idle = float(settings.MCP_UPSTREAM_SESSION_IDLE_SECONDS)
    children: set = set()
    try:
        while not sess.dying:
            if sess.queue.empty() and sess.inflight == 0:
                remaining = idle - (_now() - sess.last_used)
                if remaining <= 0:
                    sess.dying = True
                    sess.reason = "session idle"
                    logger.info("mcp upstream session reaped: server=%s user=%s", sess.server_id, sess.user_id)
                    break
                wait = min(remaining, _MAX_POLL_SECONDS)
            else:
                wait = _MAX_POLL_SECONDS
            try:
                req = await asyncio.wait_for(sess.queue.get(), wait)
            except asyncio.TimeoutError:
                continue
            if req is _CLOSE:
                break
            if req.fut.done():  # cancelled while queued
                continue
            sess.inflight += 1
            sess.last_used = _now()
            task = asyncio.create_task(_handle(sess, session, req))
            req.task = task
            children.add(task)
            task.add_done_callback(children.discard)
    finally:
        for task in list(children):
            task.cancel()
        if children:
            await asyncio.gather(*children, return_exceptions=True)


async def _owner(state: _State, sess: _Session, server: mcp_config.McpServer) -> None:
    """The only task that enters or exits the SDK's contexts for this session."""
    try:
        headers = mcp_config.upstream_auth_headers(server.id)
        async with httpx2.AsyncClient(headers=headers, follow_redirects=False, timeout=_HTTP_TIMEOUT) as http:
            async with streamable_http_client(
                server.url, http_client=http, max_sse_event_size=sse_event_limit(server.max_result_bytes)
            ) as (read, write):
                # No sampling/roots/elicitation/logging/message callbacks (T12, D16).
                async with ClientSession(read, write, read_timeout_seconds=server.timeout_seconds) as session:
                    await session.initialize()
                    logger.info("mcp upstream session open: server=%s user=%s", sess.server_id, sess.user_id)
                    await _serve(sess, session)
    except asyncio.CancelledError:
        sess.reason = "session closed"
        raise
    except Exception as exc:  # noqa: BLE001 - the reason is the class and code only (T16)
        sess.reason = f"session could not be kept ({_describe(exc)})"
        logger.warning(
            "mcp upstream session ended: server=%s user=%s error=%s", sess.server_id, sess.user_id, _describe(exc)
        )
    finally:
        sess.dying = True
        sess.closed = True
        if state.owners.get((sess.server_id, sess.user_id)) is sess:
            del state.owners[(sess.server_id, sess.user_id)]
        while not sess.queue.empty():
            req = sess.queue.get_nowait()
            if req is not _CLOSE:
                _reject(req.fut, _SessionGone(sess.reason, sent=False))
        logger.debug("mcp upstream session closed: server=%s user=%s", sess.server_id, sess.user_id)


def _stale(sess: _Session) -> bool:
    if sess.dying or sess.closed or (sess.task is not None and sess.task.done()):
        return True
    return sess.inflight == 0 and sess.queue.empty() and (
        _now() - sess.last_used >= settings.MCP_UPSTREAM_SESSION_IDLE_SECONDS
    )


async def _session_for(server: mcp_config.McpServer, user_id: str) -> tuple:
    state = _get_state()
    key = (server.id, user_id)
    async with state.lock:
        sess = state.owners.get(key)
        if sess is not None and _stale(sess):
            if not sess.closed:
                _begin_close(sess, "session idle")
            state.owners.pop(key, None)
            sess = None
        created = sess is None
        if created:
            sess = _Session(server.id, user_id, last_used=_now())
            state.owners[key] = sess
            sess.task = asyncio.create_task(_owner(state, sess, server))
        return sess, created


async def _submit(server: mcp_config.McpServer, user_id: str, req_kind: str, **fields: Any) -> Any:
    """Queue one request on the session and wait for its future, bounded by a guard."""
    sess, created = await _session_for(server, user_id)
    timeout = float(fields.get("timeout") or server.timeout_seconds)
    req = _Req(kind=req_kind, fut=asyncio.get_running_loop().create_future(), **fields)
    if sess.closed:
        gone = _SessionGone(sess.reason, sent=False)
        gone.fresh = created
        raise gone
    sess.last_used = _now()
    sess.queue.put_nowait(req)
    # A request may wait for `initialize` and then run: two timeouts, plus slack.
    guard = 2 * max(timeout, float(server.timeout_seconds)) + _GUARD_SLACK_SECONDS
    try:
        return await asyncio.wait_for(req.fut, guard)
    except _SessionGone as gone:
        gone.fresh = created
        raise
    except asyncio.TimeoutError:
        if req.task is not None:
            req.task.cancel()
        raise
    except asyncio.CancelledError:
        if req.task is not None:
            req.task.cancel()
        raise


def _server_or_none(server_id: str) -> Optional[mcp_config.McpServer]:
    return mcp_config.get_config().servers.get(server_id)


# --- Public API ---------------------------------------------------------------


async def list_tools(server_id: str, user_id: str) -> tuple:
    """Every tool the upstream advertises, all pages, cached per server (PRD-023 M8, D14).

    The cache is shared by users (the list is the server's, not the user's);
    visibility is the gateway's job. `MCP_TOOLS_CACHE_SECONDS=0` neither reads
    nor writes it. Raises `McpUpstreamError` on any failure.
    """
    server = _server_or_none(server_id)
    if server is None:
        raise McpUpstreamError(f"MCP server {server_id!r} is not configured")
    ttl = settings.MCP_TOOLS_CACHE_SECONDS
    if ttl > 0:
        hit = _tools_cache.get(server_id)
        if hit is not None and hit[0] > _now():
            return hit[1]
    state = _get_state()
    lock = state.list_locks.setdefault(server_id, asyncio.Lock())
    async with lock:  # single flight: concurrent misses share one refresh
        if ttl > 0:
            hit = _tools_cache.get(server_id)
            if hit is not None and hit[0] > _now():
                return hit[1]
        tools = await _list_uncached(server, user_id)
        if ttl > 0:
            _tools_cache[server_id] = (_now() + ttl, tools)
            logger.debug("mcp tools cache filled: server=%s tools=%d", server_id, len(tools))
        return tools


async def _list_uncached(server: mcp_config.McpServer, user_id: str) -> tuple:
    failure = f"MCP server {server.id!r}: tools/list failed"
    try:
        try:
            return await _submit(server, user_id, "list")
        except _SessionGone as gone:
            if gone.fresh:
                raise
            # Read-only, so safe to retry once on a session that was dropped under us.
            return await _submit(server, user_id, "list")
    except McpUpstreamError:
        raise
    except asyncio.TimeoutError as exc:
        raise McpUpstreamError(f"MCP server {server.id!r}: tools/list timed out") from exc
    except _SessionGone as exc:
        raise McpUpstreamError(failure) from exc


async def call_tool(
    server_id: str,
    user_id: str,
    tool: str,
    arguments: Optional[dict] = None,
    *,
    timeout_seconds: Optional[float] = None,
) -> CallOutcome:
    """One `tools/call`. Never raises for an upstream failure; never replayed (T10)."""
    server = _server_or_none(server_id)
    if server is None:
        return CallOutcome("upstream_error", detail=f"server {server_id} is not configured")
    timeout = float(timeout_seconds) if timeout_seconds else float(server.timeout_seconds)
    try:
        return await _submit(server, user_id, "call", name=tool, arguments=arguments or {}, timeout=timeout)
    except asyncio.TimeoutError:
        return CallOutcome("timeout", detail=f"{tool} on {server_id} timed out; it may have run")
    except _SessionGone as gone:
        sent = "it may have run" if gone.sent else "the call was not sent"
        return CallOutcome("upstream_error", detail=f"{tool} on {server_id}: {gone.reason}; {sent}")


async def aclose_all() -> None:
    """Close every session and wait (bounded) for its owner task. Safe to call twice."""
    global _state
    state, _state = _state, None
    if state is None:
        return
    try:
        running = asyncio.get_running_loop()
    except RuntimeError:  # pragma: no cover - always called from a coroutine
        return
    if state.loop is not running:
        return
    sessions = list(state.owners.values())
    for sess in sessions:
        if not sess.closed:
            _begin_close(sess, "session closed")
    tasks = [s.task for s in sessions if s.task is not None and not s.task.done()]
    if tasks:
        _, pending = await asyncio.wait(tasks, timeout=_CLOSE_WAIT_SECONDS)
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.wait(pending, timeout=_CLOSE_WAIT_SECONDS)
    state.owners.clear()
