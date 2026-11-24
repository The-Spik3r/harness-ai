---
id: STORY-011
prd: PRD-023
slug: northbound-endpoint
title: "Northbound `POST /mcp`: auth, Origin, JSON-RPC parsing, `initialize` / `ping` / notifications"
type: feature
priority: high
complexity: medium
phase: "3 - The gateway"
status: done
labels: [mcp, api, security]
epic_branch: epic/PRD-023-mcp-and-skills
plan: .agents/plans/PRD-023-mcp-and-skills/completed/STORY-011-northbound-endpoint.plan.md
report: .agents/reports/PRD-023-mcp-and-skills/STORY-011-northbound-endpoint.report.md
commit: 121ef12
depends_on: [STORY-004, STORY-007]
blocks: [STORY-012, STORY-015]
skills: []
created: 2026-11-22
updated: 2026-11-22
---

# STORY-011: Northbound `POST /mcp`: auth, Origin, JSON-RPC parsing, `initialize` / `ping` / notifications

## Description

As an integrating developer, I want a stateless Streamable HTTP MCP endpoint on the harness that takes my ordinary bearer token, so that my agent connects one MCP server named `harness`.

## Acceptance Criteria

- [x] Given `MCP_ENABLED=false`, when `/mcp` is requested, then it is 404; given it enabled, then `POST /mcp` is mounted and `GET` / `DELETE` return 405
- [x] Given M0, when the token is missing/invalid, the break-glass `ADMIN_TOKEN` is used, the role lacks `mcp:connect`, an `Origin` is present and not on `MCP_ALLOWED_ORIGINS`, the body exceeds `MCP_MAX_REQUEST_BYTES`, or the content type is not JSON, then 401 (with `WWW-Authenticate: Bearer realm="harness"` and no `resource_metadata`) / 403 / 403 / 403 / 413 / 415, and no row or upstream request is made
- [x] Given M1, when the body is not JSON or has duplicate keys, then `-32700`; a batch array or a non-2.0 object, then `-32600`; an unknown method, then `-32601`
- [x] Given `initialize`, when the client's protocol version is supported it is echoed, otherwise the newest supported is answered, with `capabilities: {tools: {listChanged: false}, prompts: {listChanged: false}}`, `serverInfo: {name: "harness", version}`, no `Mcp-Session-Id`, and no `instructions` (O11); `ping` answers `{}`; notifications get 202 with no body
- [x] Given `tools/list`, `tools/call`, `prompts/list`, `prompts/get`, when dispatched, then they reach clearly-named handler seams that later stories fill (until then `-32601` or an empty result, documented in the report)

## Technical Notes

- Orchestrator decision (STORY-002): observed facts (both CLIs send `protocolVersion` `2025-11-25`, no `Origin`, and a static `Authorization` on every request, with no OAuth discovery after a `401`). `/mcp` ignores unknown query parameters: OpenCode appends `?codemode=false` to non-loopback URLs. `/.well-known/oauth-*` stays `404` (nothing is mounted there). `initialize` must declare `capabilities.tools` (OpenCode requires it).
- Orchestrator decision (STORY-001): serve the handshake revisions `2025-03-26`, `2025-06-18` and `2025-11-25` only (D17, amended). A `2026-07-28`-style request (a modern `_meta` `io.modelcontextprotocol/protocolVersion` and no `initialize`, or `server/discover`) gets a plain HTTP `400` with a `-32600` body, so a dual-era client falls back. Compare header names case-insensitively (`Mcp-Session-Id` / `MCP-Session-Id`). Sources: `tests/corpora/mcp/SOURCES.md` (Protocol).
- New `app/routers/mcp.py` and `app/models/mcp_schemas.py` (pydantic, northbound only); hand-written, not the SDK server (Section 8, O-SDK).
- Duplicate keys: use `strict_yaml`'s JSON sibling if it exists, else add one there (T7). `canonical_json` = `json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True)`.
- Mount only when enabled, following the `V1_ENABLED` precedent in `app/main.py`; break-glass refusal as in `app/routers/v1.py`.
- Protocol versions from STORY-001's findings.

## Dependencies

- **Blocked by**: STORY-004, STORY-007
- **Blocks**: STORY-012, STORY-015

## PRD Reference

Source: [`PRD-023/PRD.md`](../../PRDs/PRD-023-mcp-and-skills/PRD.md) — Sections 4 (Gateway, northbound), 6.3 (M0–M2), 9.1, 10, F1, D3, D17, D19, T7, T11
