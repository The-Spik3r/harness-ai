---
id: STORY-010
prd: PRD-023
slug: mcp-upstream-client
title: "`mcp_upstream`: southbound sessions, harness-held credentials, timeouts, refusals, cached `tools/list`"
type: feature
priority: high
complexity: large
phase: "3 - The gateway"
status: todo
labels: [mcp, upstream, security]
epic_branch: epic/PRD-023-mcp-and-skills
plan: null
report: null
commit: null
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

- The only module importing `mcp`. Return types the gateway needs without importing `mcp` elsewhere (e.g. plain dicts or a small local dataclass).
- Event loop: check how the app runs async code (FastAPI handlers vs sync pipeline) and keep SDK task groups contained per call/session; the Reflex mount bypasses app lifespans (PRD-007).
- Use STORY-003's proved facts for headers, redirects and timeouts.

## Dependencies

- **Blocked by**: STORY-003, STORY-007, STORY-009
- **Blocks**: STORY-012

## PRD Reference

Source: [`PRD-023/PRD.md`](../../PRDs/PRD-023-mcp-and-skills/PRD.md) — Sections 4 (Gateway, southbound), F2, D10, D14, D16, T2, T8, T10, T12, T13, T17
