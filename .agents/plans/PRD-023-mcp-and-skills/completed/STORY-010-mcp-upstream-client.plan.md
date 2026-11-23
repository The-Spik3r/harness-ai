---
story: STORY-010
prd: PRD-023-mcp-and-skills
slug: mcp-upstream-client
title: "`mcp_upstream`: southbound sessions, harness-held credentials, timeouts, refusals, cached `tools/list`"
type: NEW_CAPABILITY
complexity: large
epic_branch: epic/PRD-023-mcp-and-skills
created: 2026-11-22
---

# Plan: mcp_upstream southbound client

## Summary

Create `app/services/mcp_upstream.py`, the only module that imports `mcp` and `httpx2`. It exposes an async, SDK-free API (`list_tools`, `call_tool`, `aclose_all`, `invalidate_tools_cache`) over one owner asyncio task per `(server_id, user_id)` session. Credentials come only from `mcp_config.upstream_auth_headers`. Upstream failures become `CallOutcome`s. Tests use the STORY-009 stub (small addition: session-expiry switch + initialize counter) and `asyncio.run` (the repo has no pytest-asyncio). Nothing is mounted or called yet, so MCP off is untouched (D20).

- Story: `.agents/stories/PRD-023-mcp-and-skills/STORY-010-mcp-upstream-client.md`
- PRD sections used: 6.3 (M8/M9 caller), F2 (7), T2/T8/T10/T12/T13/T17 (9.2), D10/D14/D16
- Systems affected: `app/services/` (new module), `scripts/stub_mcp_server.py`, `tests/`

## Design Decisions

The orchestrator's five design points are binding; restated only where they need detail.

1. **Types (frozen dataclasses, plain data).** `UpstreamTool(name, description, input_schema: dict, title: str|None, annotations: dict|None, output_schema: dict|None)`; `CallOutcome(outcome: Literal['ok','error','timeout','upstream_error'], is_error: bool, content: list[dict], structured: dict|None, detail: str)`. Build from SDK models with `model_dump(mode="json", by_alias=True, exclude_none=True)`. `'error'` = upstream returned `isError: true` (content passed through). `class McpUpstreamError(Exception)` is raised by `list_tools` only (message = server id + fixed phrase). `call_tool` never raises for upstream failures, and an unconfigured server id is `upstream_error`.
2. **`detail` and exceptions are credential-safe.** Build from fixed phrases, server id, tool name, `type(exc).__name__` and MCP error code. Never `str(exc)` (httpx messages carry URLs; upstream text is untrusted). Timeout and upstream_error wording says the call "may have run" (T10). No URL, header name or env name (T16).
3. **Owner task per session.** `_Session` holds `queue`, `task`, `last_used` (from `_now()`), `inflight`. The owner `run()` enters `httpx2.AsyncClient(...)`, `streamable_http_client(url, http_client=http)` and `ClientSession(read, write, read_timeout_seconds=server.timeout_seconds)`, runs `initialize()`, then loops on `queue.get()` waiting `min(idle_remaining, _MAX_POLL=1.0)`. Each request spawns a child task, so a slow call does not block another caller; the child sets a future only if `not fut.done()` (the caller may have been cancelled). The owner exits on: idle past `settings.MCP_UPSTREAM_SESSION_IDLE_SECONDS` with `inflight == 0`, a close sentinel, or a session-level error. On exit it fails every queued future and removes itself from the registry in `finally`. A caller cancel cancels only the caller's `await fut`.
4. **Session-level errors drop the session.** Any request exception except the timeout (`MCPError` -32001) breaks the session: httpx2 errors, other `MCPError` (including the SDK's 404 mapping `-32600 "Session terminated"`, `.venv/Lib/site-packages/mcp/client/streamable_http.py:417-424`), `ClosedResourceError`, exception groups (flatten leaves like `facts.py:53`). The next call re-initializes. A timeout (session survives, `facts.py:423`) and `ValidationError`/`RuntimeError` (input_required, T12) keep it. `call_tool` is never replayed (T10 amended). `list_tools` is read-only and may retry once after a session-terminated error: this is a judgement beyond the brief, flagged for the orchestrator.
5. **Registry.** `_State(loop, asyncio.Lock, owners, per-server list locks)` is created lazily on the running loop. If `_state.loop is not asyncio.get_running_loop()` (tests use one `asyncio.run` each; the Reflex mount bypasses lifespan) the old state is discarded without awaiting. Creation is under the lock; reuse drops an owner that is done or idle by `_now()`. `aclose_all()` signals every owner and awaits its task (bounded), then clears.
6. **Timeouts.** `call_tool(timeout_seconds=None)` uses `server.timeout_seconds` (already defaulted from `MCP_CALL_TIMEOUT_SECONDS`, `mcp_config.py:396`). Pass `read_timeout_seconds=` to `session.call_tool`; the SDK raises -32001 and sends `notifications/cancelled` itself (D14 amendment), so do not hand-send it. The caller also waits `timeout + 5s` as a hung-owner guard and returns `timeout`. `httpx2.Timeout(connect=10, read=None, write=30, pool=10)` so httpx never beats the SDK timeout.
7. **Headers and redirects.** `httpx2.AsyncClient(headers=mcp_config.upstream_auth_headers(server_id), follow_redirects=False, timeout=...)`; no public parameter accepts headers. The SDK ignores `follow_redirects` and refuses cross-origin and same-origin 301/302 itself (`facts.py:404`; same-origin 307/308 followed, accepted for T8). `ClientSession` gets NO sampling/roots/elicitation/logging/message callbacks; never `mcp.Client`; `allow_input_required` stays False.
8. **`list_tools`.** Loop `session.list_tools(params=PaginatedRequestParams(cursor=...))` until `next_cursor` is None, with a 100-page cap and a repeated-cursor check (a looping cursor is a hostile server, raise `McpUpstreamError`). Cache: module dict `server_id -> (expires_at, tuple[UpstreamTool])` using `_now()`; TTL read from `settings.MCP_TOOLS_CACHE_SECONDS` per call; 0 = neither read nor write. Per-server lock for single-flight refresh. `invalidate_tools_cache(server_id=None)` is the test hook. `_now = time.monotonic` is a module attribute tests monkeypatch.
9. **Stated limits (docstring).** Credentials fixed at session creation (restart to rotate). Result-size cap is STORY-013's.

## Skills In Use

None apply (`.agents/skills/` holds only `frontend-design`).

---

## Patterns to Follow

| Category | Source | What to mirror |
|----------|--------|----------------|
| Docstring, `logger`, frozen dataclasses | `app/services/mcp_config.py:34-52`, `:118-160` | Cite PRD sections/decisions; `logging.getLogger(__name__)` |
| Config at call time | `mcp_config.py:170` (`get_config`), `:220` (`upstream_auth_headers`) | `get_config().servers[server_id]`; read `settings.MCP_*` per call, never at import |
| SDK recipe | `tests/test_prd023_mcp_sdk_facts.py:73-80` (`_with_session`), `:53-57` (`_flatten`) | AsyncClient -> `streamable_http_client` (2 streams) -> `ClientSession` -> `initialize` |
| Test driving | `tests/test_stub_mcp_server.py:45-48` (`_run`) | One `asyncio.run(wait_for(...))` per test |
| Stub fixtures | `tests/mcp_stub.py:147-166`; `scripts/stub_mcp_server.py:76-110` (Stats), `:206-260` (`_Gate`) | `mcp_stub_factory(name=, bearer=, headers=, page_size=)`, `stub.stats()`, `stub.calls(tool)`, `stub.reset()` |

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/mcp_upstream.py` | CREATE | The module |
| `scripts/stub_mcp_server.py` | UPDATE | `initializes` counter; `POST /__stub/expire-sessions` (next `/mcp` request carrying `mcp-session-id` gets a bare `404` once, counted `session_404`); additive keys in `Stats.reset`/`as_json` |
| `tests/mcp_stub.py` | UPDATE | `StubHandle.expire_sessions()` next to `reset` (line ~70) |
| `tests/test_mcp_upstream.py` | CREATE | Stub-backed tests (not `db`; no Docker) |
| `tests/test_mcp_upstream_import_graph.py` | CREATE | T17 AST test |
| `tests/test_prd023_mcp_sdk_facts.py` | UPDATE | `test_app_never_imports_mcp` (line 304): allow exactly `app/services/mcp_upstream.py`; keep the name; comment citing PRD-023 T17 / STORY-010 |
| `tests/test_stub_mcp_server.py` | UPDATE | One test for the new side-channel keys and the 404 switch |

## Tasks

### Task 1: Stub additions
- **File**: `scripts/stub_mcp_server.py`, `tests/mcp_stub.py`
- **Implement**: in `_Gate.__call__` (line 221) a `/mcp` POST with no `mcp-session-id` increments `stats.initializes`; if `expire_next` is set and the request carries a session id, answer `Response(404)`, clear the flag, count `session_404`; add the `/__stub/expire-sessions` branch in `_side_channel` (line 250); update the module docstring. Still no argument/result recording.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_stub_mcp_server.py`

### Task 2: `app/services/mcp_upstream.py`
- **Implement**: Design points 1-9. Public: `UpstreamTool`, `CallOutcome`, `McpUpstreamError`, `list_tools`, `call_tool`, `aclose_all`, `invalidate_tools_cache`. Log session open/close/reap and cache fills at INFO/DEBUG with server id and user id only; never headers, URL or exception text beyond the class name.
- **Validate**: `.venv/Scripts/python -c "from app.main import app; print('OK')"` and Task 3.

### Task 3: `tests/test_mcp_upstream.py`
Helper `_cfg(stub, auth, timeout)` builds an `McpConfig` (`McpServer(..., allow_insecure=True, auth=McpAuth(type="bearer", env_name="X", _secret=TOKEN))`) and `monkeypatch.setattr(mcp_config, "_config", cfg)`. Autouse fixture resets cache and state. Tests are sync, use `asyncio.run`, and `await aclose_all()` in `finally`. Cases:
- auth: stubs with `bearer=` / `headers=`; `last_authorization == f"Bearer {TOKEN}"`, `unauthorized == 0`, no `cookie` in `header_names`; `inspect.signature` of both functions has no header-like parameter; wrong token gives `upstream_error`.
- sentinel token under `caplog.set_level(DEBUG)` over list, call, 401 and timeout: absent from `caplog.text`, every `detail`, every repr.
- reuse: two calls `initializes == 1`; two users `== 2`. Idle reap: monkeypatch `_now` and `settings.MCP_UPSTREAM_SESSION_IDLE_SECONDS`, advance, next call `initializes == 2`.
- unknown session: `stub.expire_sessions()`, `call_tool("create_branch")` gives `upstream_error` and the stub count is not replayed; the next call succeeds, `initializes == 2`.
- timeout: `slow` 5s with `timeout_seconds=0.5` gives `timeout` quickly, `calls("slow") == 1`, session reused. Cancel the caller mid-`slow`: next call `ok`, `initializes == 1`. A `slow` and a `query` concurrently both complete.
- sampling: `call_tool("sample")` `ok`, `stats()["sampling"] == {"requested": 1, "last_kind": "error"}`, text has `-32600`. roots/elicitation are not scriptable: a spy `ClientSession` asserts no callback kwargs.
- redirect: in-test `ThreadingHTTPServer` replies 302 to a second local server; the second sees nothing; `upstream_error`.
- `input_required` (spy raising `RuntimeError`/`ValidationError`), closed port, unconfigured id: `upstream_error`, no raise, no registry entry left. Unit test: `CallToolResult(is_error=True)` maps to `'error'`.
- pagination: `page_size=3` returns 9 tools in 3 requests; a looping cursor raises `McpUpstreamError`.
- cache: TTL 60 gives one upstream list for two calls (also across users); advancing `_now` refetches; TTL 0 never caches; `invalidate_tools_cache` refetches.
- `aclose_all` leaves no owner task in `asyncio.all_tasks()`.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider -m "not db" tests/test_mcp_upstream.py`

### Task 4: Import-graph guard (T17) and amended STORY-003 test
- `tests/test_mcp_upstream_import_graph.py`: AST-scan `app/**/*.py`. `mcp`, `mcp.*`, `httpx2`, `httpx2.*` are imported only by `app/services/mcp_upstream.py`; no module imports `mcp.client.stdio`, `mcp.server*`, or `subprocess` from any `mcp*` module. Not vacuous: `mcp_upstream.py` itself imports both, and the scanner function flags a planted source string.
- Edit `tests/test_prd023_mcp_sdk_facts.py:304` per the table; keep the name.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_mcp_upstream_import_graph.py tests/test_prd023_mcp_sdk_facts.py tests/test_untouched_app.py`

## End-to-End Tests

- [ ] Real stub subprocess with a bearer: `list_tools` then `call_tool("query")`, then `aclose_all()` (covered by Task 3). No `chat_ui/` change.

---

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider -m "not db" tests/test_mcp_upstream.py tests/test_mcp_upstream_import_graph.py tests/test_stub_mcp_server.py tests/test_prd023_mcp_sdk_facts.py tests/test_mcp_config.py tests/test_untouched_app.py
```
Docker is down locally, so use `-m "not db"`; none of the new tests use a storage fixture. Full suite: GitHub CI.

## Acceptance Criteria -> Tasks -> Tests

| AC | Task(s) | Test that proves it |
|----|---------|---------------------|
| AC1 harness-held credential, no inbound header, no log leak | 2, 3 | `test_mcp_upstream.py::test_bearer_and_header_auth_come_only_from_config`, `::test_sentinel_token_never_logged_or_returned`, `::test_public_api_accepts_no_headers` |
| AC2 sessions per `(server,user)`, idle reap, unknown-session re-init, no replay (T10 amended) | 1, 2, 3 | `::test_sessions_keyed_by_server_and_user`, `::test_idle_session_is_reaped`, `::test_unknown_session_reinitializes_next_call_without_replay` |
| AC3 timeout outcome, `slow` counter 1, SDK cancel | 2, 3 | `::test_timeout_outcome_and_slow_counted_once`, `::test_caller_cancel_keeps_session` |
| AC4 sampling refused, no capabilities, redirects not followed | 2, 3 | `::test_sampling_refused_and_no_callbacks`, `::test_redirect_not_followed` |
| AC5 pagination, per-server cache, `0` = none, T17 import graph | 2, 3, 4 | `::test_pagination_reads_all_pages`, `::test_tools_cache_ttl_zero_and_invalidate`, `test_mcp_upstream_import_graph.py::test_only_mcp_upstream_imports_mcp_and_httpx2` |

## Risks

- anyio cancel scopes across tasks: only the owner enters/exits SDK contexts; the concurrency and cancel tests detect a violation.
- Per-test `asyncio.run` loops vs the registry: per-loop `_State`; `aclose_all()` in every `finally`.
- AC4 says `-32601`, the SDK answers `-32600` (STORY-003 facts); the plan follows the code. AC2's "retries that call" is superseded by T10 (amended).
