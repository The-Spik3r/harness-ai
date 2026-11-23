---
id: STORY-010
prd: PRD-023
slug: mcp-upstream-client
title: "`mcp_upstream`: southbound sessions, harness-held credentials, timeouts, refusals, cached `tools/list`"
type: feature
priority: high
complexity: large
phase: "3 - The gateway"
status: done
labels: [mcp, upstream, security]
epic_branch: epic/PRD-023-mcp-and-skills
plan: .agents/plans/PRD-023-mcp-and-skills/completed/STORY-010-mcp-upstream-client.plan.md
report: .agents/reports/PRD-023-mcp-and-skills/STORY-010-mcp-upstream-client.report.md
commit: pending
depends_on: [STORY-003, STORY-007, STORY-009]
blocks: [STORY-012]
skills: []
created: 2026-11-22
updated: 2026-11-22
---

# STORY-010: `mcp_upstream`: southbound sessions, harness-held credentials, timeouts, refusals, cached `tools/list`

## Description

As a platform operator, I want the harness to be the MCP client of record for each configured server, holding the credential, so that no agent ever holds an upstream token.

## Acceptance Criteria

- [ ] Given a server with `auth: {type: bearer, token_env: X}` or `{type: header, ...}`, when the harness calls it, then the stub sees exactly the configured credential, never the caller's token, `Cookie`, `Mcp-Session-Id` or other inbound header, and the value appears in no log line
- [ ] Given sessions keyed `(server, user_id)`, when idle beyond `MCP_UPSTREAM_SESSION_IDLE_SECONDS`, then they are reaped; when the server reports an unknown/expired session, then the harness re-initializes once and retries that call only in that case; otherwise a call is never retried
- [ ] Given `call_tool(server, user_id, name, arguments, timeout)` past the timeout, when it expires, then a best-effort `notifications/cancelled` is sent and a timeout outcome is returned to the caller (the stub's `slow` counter is 1)
- [ ] Given the stub sends `sampling/createMessage` (or `roots/list`, `elicitation/create`), when received, then it is answered `-32601` and nothing reaches OpenRouter; the client declares no capabilities; redirects are not followed
- [ ] Given `list_tools(server, user_id)`, when the server paginates, then all pages are read through `nextCursor` and cached per server for `MCP_TOOLS_CACHE_SECONDS` (`0` = no cache); an import-graph test asserts `mcp` is imported only by `app/services/mcp_upstream.py` and no `app/` module imports `subprocess` from `mcp_*`, `mcp.client.stdio` or `mcp.server` (T17)

## Technical Notes

- Orchestrator decision (STORY-003, `mcp==2.3.0`): facts proved in `tests/test_prd023_mcp_sdk_facts.py`, so reuse them and do not re-derive them:
  - Imports: `from mcp import ClientSession` and `from mcp.client.streamable_http import streamable_http_client`, which yields 2 streams. Pass static headers through `http_client=httpx2.AsyncClient(headers=...)`. `httpx2` is transitive (via `anthropic` and `mcp`), may be imported only by `mcp_upstream.py`, and gets no pin of its own.
  - Per-call timeout: `call_tool(..., read_timeout_seconds=...)` raises `MCPError` code `-32001`, and the SDK sends `notifications/cancelled` itself. Map it to `outcome='timeout'`.
  - Redirects: cross-origin and same-origin 301/302 are not followed; same-origin 307/308 are (accepted for T8).
  - Sampling with no callback: the SDK answers `-32600` (accepted for T12). Never register sampling/roots/elicitation callbacks, and never use `mcp.Client`, which auto-answers.
  - `input_required`: on a handshake session it surfaces as a pydantic `ValidationError`, and on a modern session as a `RuntimeError` (or `InputRequiredResult` with `allow_input_required=True`, which must not be set). Map all of these to `upstream_error`.
  - Negotiate with `initialize` (the handshake era). A modern-only upstream server is not verified; it is a stated limitation.
- Orchestrator decision (STORY-001): T10 amended. After an unknown-session `404` the harness re-initializes for the *next* call and never replays a forwarded `tools/call`, so the AC's 'retries that call only in that case' is superseded: no forwarded call is ever retried. An upstream `resultType: "input_required"` is refused as `upstream_error` and never answered (T12, amended).
- The only module importing `mcp`. Return types the gateway needs without importing `mcp` elsewhere (e.g. plain dicts or a small local dataclass).
- Event loop: check how the app runs async code (FastAPI handlers vs sync pipeline) and keep SDK task groups contained per call/session; the Reflex mount bypasses app lifespans (PRD-007).
- Use STORY-003's proved facts for headers, redirects and timeouts.

## Dependencies

- **Blocked by**: STORY-003, STORY-007, STORY-009
- **Blocks**: STORY-012

## PRD Reference

Source: [`PRD-023/PRD.md`](../../PRDs/PRD-023-mcp-and-skills/PRD.md) — Sections 4 (Gateway, southbound), F2, D10, D14, D16, T2, T8, T10, T12, T13, T17
