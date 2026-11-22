---
story: STORY-003
prd: PRD-023
plan: .agents/plans/PRD-023-mcp-and-skills/completed/STORY-003-mcp-sdk-pin.plan.md
epic_branch: epic/PRD-023-mcp-and-skills
commit: pending
status: COMPLETE
completed: 2026-11-22
---

# Implementation Report - STORY-003: Pin the `mcp` SDK and prove its client behaviours offline

## Summary

`mcp==2.3.0` is pinned in `requirements.txt` and installed in `.venv`. `tests/test_prd023_mcp_sdk_facts.py` (18 cases, ~14 s) records what the SDK client does. Nothing under `app/` imports `mcp`. Orchestrator decisions applied: T12 accepts `-32600`; T8 pins same-origin 307/308 followed and cross-origin (any code) not followed; `httpx2` is not pinned.

## Transitive diff (pip freeze before/after; no existing pin moved)

Added: `mcp==2.3.0`, `mcp-types==2.3.0`, `PyJWT==2.15.1`, `jsonschema==4.26.0`, `jsonschema-specifications==2025.9.1`, `referencing==0.37.0`, `rpds-py==2026.9.1`, `attrs==26.1.0`, `sse-starlette==3.7.0`, `pywin32==312` (Windows only: `Requires-Dist: pywin32>=311; sys_platform == 'win32'`, so Linux CI/Docker skip it). `pip check`: "No broken requirements found" (local venv, py3.12). CI is Linux/py3.11; not run here, tests are version-agnostic.

`httpx2` is transitive (anthropic, mcp), not pinned. STORY-010's `mcp_upstream.py` will import it to build the client.

## Facts (test names in tests/test_prd023_mcp_sdk_facts.py)

1. Imports/transport: `test_import_paths_used_later_and_transport_yields_two_streams` (2-tuple; `FastMCP` import fails, server is `mcp.server.mcpserver.MCPServer`).
2. Headers: `test_static_headers_reach_the_server_via_httpx2_client_not_a_headers_argument`.
3. Redirects: `test_redirects_..._followed` (8 params).
4. Timeout: `test_per_call_timeout_raises_mcperror_32001_and_sends_cancelled`.
5. Sampling: `test_sampling_request_without_callback_is_answered_32600_not_32601`.
6. Pagination: `test_tools_list_cursor_pagination`.
7. Modern era: `test_modern_session_discover_and_input_required_surfaces`, `test_input_required_on_a_handshake_session_is_a_validation_error`. Handshake: `test_handshake_negotiates_2025_11_25_and_declares_no_capabilities`.
Pin/boundary: `test_pin_is_exact_and_installed`, `test_app_never_imports_mcp`.

Not verified: a server answering `initialize` with an error (truly modern-only); the discover-vs-initialize choice is STORY-009's.

## PRD amendments (AC4, for the orchestrator)

- Section 8 stub-server and MCP-client rows, F12: "FastMCP" is `mcp.server.mcpserver.MCPServer`; `streamable_http_client` yields 2 values and takes an `httpx2.AsyncClient`; add `httpx2`, `mcp-types`, `PyJWT`, `jsonschema`, `sse-starlette` (and `opentelemetry-api`, already present) to the transitive list; `httpx-sse` is not needed.
- T8: not followed for cross-origin and 301/302; same-origin 307/308 are followed (SDK ignores `follow_redirects`). Same origin only, host stays the configured one; cross-origin 307 is not followed (tested).
- T12/D16: sampling/elicitation/roots answered `-32600 "Sampling not supported"`, not `-32601`; harness registers no callback and never uses `mcp.Client`.
- T12 `input_required`: `RuntimeError` (modern session, default), `InputRequiredResult` (`allow_input_required=True`), `ValidationError` on a handshake session; STORY-009 maps all to `upstream_error`.
- D14: timeout is `MCPError` code -32001; the SDK sends `notifications/cancelled` itself.

## Validation

| Check | Result |
|---|---|
| `from app.main import app` | OK |
| `pip check` | no broken requirements |
| Targeted pytest (facts + test_untouched_app + sqlglot pin test), 3 consecutive runs | 28 passed each, ~14 s |

Full suite: GitHub CI on push (user decision).

## Files Changed

| File | Action |
|---|---|
| `requirements.txt` | UPDATE (+1, CRLF like the file) |
| `tests/test_prd023_mcp_sdk_facts.py` | CREATE |

## Deviations from Plan

None of substance. `test_handshake...` asserts `capabilities == {}` on the raw server and the negotiated version on both.

## Acceptance Criteria

- [x] AC1 exact pin, transitive diff, no pin moved
- [x] AC2 module paths, headers, redirect, timeout, sampling, cursor
- [x] AC3 `.venv` imports, `app.main` imports, `app/` has no `mcp` import
- [x] AC4 contradictions named with amendments
