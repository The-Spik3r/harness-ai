---
story: STORY-003
prd: PRD-023
slug: mcp-sdk-pin
title: "Pin the `mcp` SDK and prove its client behaviours offline"
type: technical
complexity: medium
epic_branch: epic/PRD-023-mcp-and-skills
created: 2026-11-22
---

# Plan: Pin the `mcp` SDK and prove its client behaviours offline

## Summary

Pin `mcp==2.3.0` (newest stable, uploaded 2026-10-02; the other candidate, `1.30.0`, is handshake-only) in `requirements.txt`, install it into `.venv`, and add `tests/test_prd023_mcp_sdk_facts.py`, which records what the SDK client really does. Nothing under `app/` imports `mcp`. The facts below were observed by the planner in throwaway venvs (scratchpad) and the test must re-prove each one.

- Story: `.agents/stories/PRD-023-mcp-and-skills/STORY-003-mcp-sdk-pin.md`
- PRD sections used: §6.1 (amended), §8, §15 facts, D14, D16, D18, T8, T10, T12
- Systems affected: `requirements.txt`, `.venv`, one new test file. CI (`.github/workflows/ci.yml:66`) and both `Dockerfile` stages run `pip install -r requirements.txt`, so the pin reaches them with no other change.

## Pin decision (planner evidence)

| Criterion | v2.3.0 | v1.30.0 |
|---|---|---|
| Client does `2025-11-25` handshake over Streamable HTTP | yes (observed: `initialize` -> `2025-11-25`) | yes (`LATEST_PROTOCOL_VERSION`, `types.py:27`) |
| `pip install --dry-run -c <current .venv freeze>` (Win, py3.12) | resolves, **no existing pin changed** | resolves, no pin changed |
| Python | `>=3.10` (CI/Docker 3.11 ok) | same |
| Newest stable | yes | no |

Selection: criteria 1 and 2 both hold for v2.3.0, so criterion 3 picks it; no pin change forces v1.

- New distributions v2.3.0 adds to the environment: `mcp-types==2.3.0`, `PyJWT`, `jsonschema` (+`attrs`, `referencing`, `rpds-py`, `jsonschema-specifications`), `sse-starlette`, `pywin32` (Windows only), `cffi`/`pycparser`. Already present and satisfied by existing pins: `httpx2 2.16.0` (pulled by `anthropic==2.11.0`), `httpcore2`, `opentelemetry-api`, `truststore`, `pydantic 2.13.5` (needs `>=2.12`), `starlette 1.6.0`, `anyio 4.15.1`, `uvicorn`, `python-multipart`, `typing-extensions`. v2 uses **`httpx2`, not `httpx`** (v1 needs `httpx<1` + `httpx-sse`, which v2 drops).
- A full Linux/py3.11 dry run of `requirements.txt` was not possible (`spacy==3.8.16` has no wheel for pip's cross-platform mode, and pip evaluates `pywin32` markers on the host). Unpinned lines (`pydantic`, `httpx`, `starlette`, `anyio`) float in CI, but every v2.3.0 lower bound is below what they already resolve to. The implementer records `pip check` output after the real install.

### Verified client facts (v2.3.0; each becomes a test)

1. Imports: `from mcp import ClientSession`; `from mcp.client.streamable_http import streamable_http_client` (async context manager yielding a **2-tuple** `(read, write)`; v1 yielded 3). `mcp.types` still resolves. `mcp.Client` exists but auto-drives `input_required` via callbacks; the harness uses `ClientSession` only. Server side is `mcp.server.mcpserver.MCPServer` (v1's `FastMCP` import raises "removed in mcp 2", `server/fastmcp.py:1`).
2. Static headers: no `headers=` argument. Pass `http_client=httpx2.AsyncClient(headers={...}, timeout=...)`. The `Authorization` header reached the server on `initialize` and `tools/call`; `mcp-protocol-version: 2025-11-25` is added by the SDK after init. `initialize` params carry `capabilities: {}` when no callbacks are registered (matches D16).
3. Redirects: `follow_redirects` on the supplied client is **not consulted** (`streamable_http.py:72-86`, docstring at `:731-737`). Observed on a raw server: cross-origin 301/302/307/308 and same-origin 301/302 are not followed (`MCPError` "Redirect to ... not followed", target never hit); **same-origin 307/308 ARE followed** (POST replayed to the same host, then a JSON parse error because the stub target returns `{}`). No switch disables the same-origin case.
4. Per-call timeout: `call_tool(name, args, read_timeout_seconds=<float>)` (v2: float seconds, v1: `timedelta`). Raises `mcp.MCPError` with `.code == -32001` ("Request 'tools/call' timed out"); the SDK sends `notifications/cancelled` itself (observed); the session stays usable afterwards.
5. Server-to-client `sampling/createMessage` with no callback: the client answers a JSON-RPC **error `-32600` "Sampling not supported"** (`session.py:249-256`; same constant in v1 at `session.py:80-99`). Not `-32601` as T12 says. Passing any `sampling_callback` flips the declared capability (`session.py:631`), so the harness cannot both declare nothing and answer `-32601` through the SDK.
6. `tools/list` pagination: `ClientSession.list_tools(params=mcp.types.PaginatedRequestParams(cursor=...))` -> result `.next_cursor` (None at the end). v2 has no positional `cursor` argument.
7. `2026-07-28`: `ClientSession.discover()` reaches a modern session (`protocol_version == "2026-07-28"`); an SDK server (`Server`/`MCPServer.streamable_http_app()`) serves both eras. `input_required` surfaces as: modern session -> `RuntimeError("Server returned InputRequiredResult; pass allow_input_required=True ...")` by default, or an `InputRequiredResult` object (`.request_state`, `.input_requests`) with `allow_input_required=True`; **handshake session** (`2025-11-25`) -> a pydantic `ValidationError` for `CallToolResult` (`content` missing), not a clean return. Not verified: a server that answers `initialize` with an error (a truly modern-only server); the transport choice between `discover` and `initialize` is STORY-009's.

## Design Decisions

- Pin line `mcp==2.3.0`, no comment (`requirements.txt` has none today), after `anthropic==2.11.0`.
- The facts test is a spike-as-test (`tests/test_prd022_spike_anthropic_sdk.py:1-22` is the precedent): test names state the observed fact and the PRD claim it contradicts. When the SDK behaves differently from the PRD, the test asserts the SDK and the name says so.
- Test infra: raw `ThreadingHTTPServer` on port 0 (handshake JSON-RPC, SSE reply for the sampling case, `threading.Event` handshakes, no sleeps) plus one SDK `MCPServer`/lowlevel `Server` app run via `uvicorn.Server(Config(app, port=free_port()))` in a thread (`started` polled with a deadline, `should_exit=True` + `join(5)` in the finalizer). Async code runs through `asyncio.run` inside sync tests; wrap each await in `asyncio.wait_for(..., 10)`. Exception groups: flatten with a helper (SDK raises `ExceptionGroup`s from anyio task groups). `free_port` exists at `tests/_caddy.py:59`.
- No `app/` import of `mcp` (guard: a test greps `app/` for `import mcp`/`from mcp`). Later stories import `httpx2` indirectly: note in the report that `httpx2` is transitive (`anthropic`, `mcp`), not a direct pin.

## Skills In Use

None. `.agents/skills/` holds only `frontend-design` (UI design; not applicable).

## Patterns to Follow

| Category | Source | What to mirror |
|---|---|---|
| Spike-as-test | `tests/test_prd022_spike_anthropic_sdk.py:1-22` | Module docstring listing the facts and the PRD claim each checks |
| Localhost stub | `tests/test_prd022_spike_anthropic_sdk.py:48-84` | `HTTPServer(("127.0.0.1", 0))`, daemon thread, `shutdown`+`join(5)` in a fixture finalizer |
| Exact-pin test | `tests/test_action_sql.py:392-397` | regex on `requirements.txt` plus `__version__` assertion |
| Free port | `tests/_caddy.py:59-63` | `free_port()` |

## Files to Change

| File | Action | Purpose |
|---|---|---|
| `requirements.txt` | UPDATE | add `mcp==2.3.0` |
| `tests/test_prd023_mcp_sdk_facts.py` | CREATE | the facts above |
| `.agents/reports/PRD-023-mcp-and-skills/STORY-003-mcp-sdk-pin.report.md` | CREATE (implement phase) | transitive diff, facts, PRD amendments |

## Tasks

### Task 1: Pin and install
- **File**: `requirements.txt`. Append `mcp==2.3.0`.
- **Implement**: `.venv/Scripts/python -m pip install mcp==2.3.0`; run `pip freeze` before/after and `pip check`; the diff goes in the report (added list above; no pin moved). Confirm `.venv/Scripts/python -c "import mcp; print(mcp.__version__)"` if the attribute exists, else `importlib.metadata.version("mcp")`.
- **Validate**: `.venv/Scripts/python -c "from app.main import app; print('OK')"`

### Task 2: Facts test, harness
- **File**: `tests/test_prd023_mcp_sdk_facts.py` (CREATE). Module docstring as in the precedent. Helpers: `_RawServer` (handshake: `initialize` -> `2025-11-25`, `notifications/*` -> 202, `tools/list` with `nextCursor`, `tools/call` names `echo`/`slow` (waits on an Event, released in teardown)/`sample` (SSE stream: sends `sampling/createMessage` id 77, waits for the client's POST of the reply, then streams the result)/`mrtr`), records `(method, path, lower-cased headers, body)`; `/redir?code=N&same|cross` answers a 30x to a path on the same server or on a second server; `_flatten(exc)`; `_run(coro)` with `asyncio.run` + `wait_for`.
- **Mirror**: `tests/test_prd022_spike_anthropic_sdk.py:48-100`.

### Task 3: Facts test, cases
One test per fact; names state the finding.
- `test_pin_is_exact_and_installed`: regex `(?m)^mcp==2\.3\.0\s*$` + `importlib.metadata.version("mcp") == "2.3.0"`; `anthropic==2.11.0`, `reflex==0.9.6.post1` lines still present.
- `test_app_never_imports_mcp`: walk `app/**/*.py` with `ast`; no `mcp` / `mcp.*` import.
- `test_import_paths_used_later`: both imports, plus `mcp.MCPError`, `mcp.types.PaginatedRequestParams`; `streamable_http_client` yields a 2-tuple.
- `test_handshake_negotiates_2025_11_25_and_declares_no_capabilities`: against the SDK server app (thread) and the raw server; assert `initialize` body `capabilities == {}`.
- `test_static_headers_reach_the_server`: `httpx2.AsyncClient(headers=...)`; header seen on `initialize` and `tools/call`; `mcp-protocol-version` present on `tools/call`.
- `test_redirects_cross_origin_and_301_302_not_followed_same_origin_307_308_followed`: parametrised over (kind, code), asserts `MCPError` text for the unfollowed cases and that the second server saw nothing, and that the same-origin 307/308 replay reached `/target`. Name notes: contradicts T8 "redirects are not followed".
- `test_per_call_timeout_raises_mcperror_32001_and_sends_cancelled`: `read_timeout_seconds=0.5` on `slow`; `.code == -32001`; raw server saw `notifications/cancelled`; a following `echo` succeeds. Generous margin: the assertion is on shape, not elapsed time.
- `test_sampling_request_without_callback_is_answered_32600`: `sample` tool; `state.sampling_reply["error"]["code"] == -32600`, message "Sampling not supported"; final result still arrives.
- `test_tools_list_cursor_pagination`: first page `next_cursor == "c2"`, request body of page two carries `params.cursor == "c2"`, last page `next_cursor is None`.
- `test_modern_session_discover_and_input_required_surfaces`: lowlevel `Server` app whose `on_call_tool` returns `mcp_types.InputRequiredResult(...)` (verified shape: `import mcp_types as T`; `Server("low", on_list_tools=..., on_call_tool=...)` from `mcp.server`; `on_list_tools` returns `T.ListToolsResult(tools=[T.Tool(name="ask", input_schema={"type": "object"})])`; `on_call_tool` returns `T.InputRequiredResult(input_requests={"k": T.ElicitRequest(params=T.ElicitRequestFormParams(message="m", requested_schema={"type": "object", "properties": {}}))}, request_state="s")`; app = `server.streamable_http_app()`): `discover()` -> `2026-07-28`; default call raises `RuntimeError` mentioning `allow_input_required`; with the flag returns an `InputRequiredResult` with `request_state == "s"`.
- `test_input_required_on_a_handshake_session_is_a_validation_error`: raw `mrtr` tool; pydantic `ValidationError` (flatten exceptions).
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_prd023_mcp_sdk_facts.py` (run it three times in a row to catch port/teardown flakiness; confirm no leftover process).

### Task 4: Report (implement phase)
Transitive diff (before/after freeze), the seven facts with the test names, and the PRD amendments below.

## PRD amendments the report must name (AC4)

- **§8 stub-server row, §8 MCP-client row, F12:** "FastMCP" is `mcp.server.mcpserver.MCPServer` in 2.x (import of `FastMCP` fails). `streamable_http_client` yields 2 values and takes an `httpx2.AsyncClient`, not headers. Add `httpx2`, `mcp-types`, `PyJWT`, `jsonschema`, `sse-starlette`, `opentelemetry-api` to the transitive list; `httpx-sse` is not needed.
- **T8:** "Redirects are not followed" is true of cross-origin and 301/302/303; same-origin 307/308 are followed (SDK ignores `follow_redirects`). Same origin only, so not an SSRF primitive; reword the threat row.
- **T12 / D16:** the SDK answers server-initiated `sampling`, `elicitation` and `roots/list` with `-32600`, not `-32601`, and cannot be made to answer `-32601` without registering a callback, which would declare the capability. Treat `-32600` as the answer, or have STORY-009 use `message_handler`/a lower layer only if `-32601` matters.
- **T12 `input_required`:** surfaces as `RuntimeError` (modern session, default) or `InputRequiredResult` (`allow_input_required=True`); on a handshake session it is a `ValidationError`. STORY-009 maps all three to `upstream_error`. Never use `mcp.Client` (it auto-answers via callbacks).
- **D14:** timeout is `MCPError` code `-32001` and the SDK sends `notifications/cancelled` itself, so the harness need not.

## End-to-End Tests

- [ ] `from app.main import app` imports with the SDK installed.
- [ ] The facts file passes three consecutive runs on Windows; CI (Linux, 3.11) is the second platform, watched by the orchestrator.

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
.venv/Scripts/python -m pip check
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_prd023_mcp_sdk_facts.py tests/test_untouched_app.py tests/test_action_sql.py::test_requirements_pins_sqlglot_exactly
```

Do not run the full suite (GitHub CI). No `app/` file changes, so no DB or Reflex probe is needed.

## Acceptance Criteria -> Tasks -> Tests

| AC | Task(s) | Test that proves it |
|---|---|---|
| AC1 exact pin, transitive diff, no pin changed | 1, 4 | `test_pin_is_exact_and_installed`; report diff; `pip check` |
| AC2 module paths, headers, redirect, timeout, sampling, cursor | 2, 3 | `test_import_paths_used_later`, `test_static_headers_reach_the_server`, `test_redirects_*`, `test_per_call_timeout_*`, `test_sampling_request_without_callback_*`, `test_tools_list_cursor_pagination` |
| AC3 `.venv` imports, `app.main` still imports | 1 | `from app.main import app` check; `test_app_never_imports_mcp` |
| AC4 contradictions named with amendments | 4 | report section "PRD amendments" (list above) |
