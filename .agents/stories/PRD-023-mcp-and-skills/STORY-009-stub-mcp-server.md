---
id: STORY-009
prd: PRD-023
slug: stub-mcp-server
title: "Test infrastructure: the scripted stub MCP server and its pytest fixture"
type: technical
priority: high
complexity: medium
phase: "3 - The gateway"
status: done
labels: [tests, mcp]
epic_branch: epic/PRD-023-mcp-and-skills
plan: .agents/plans/PRD-023-mcp-and-skills/completed/STORY-009-stub-mcp-server.plan.md
report: .agents/reports/PRD-023-mcp-and-skills/STORY-009-stub-mcp-server.report.md
commit: null
depends_on: [STORY-003]
blocks: [STORY-010]
skills: []
created: 2026-11-22
updated: 2026-11-22
---

# STORY-009: Test infrastructure: the scripted stub MCP server and its pytest fixture

## Description

As a developer of the gateway, I want a scripted Streamable HTTP MCP server run as a separate process, so that every gateway behaviour is tested against a real protocol peer that counts calls.

## Acceptance Criteria

- [ ] Given `scripts/stub_mcp_server.py` (SDK `FastMCP`), when started on a free localhost port, then it exposes `query`, `push_files`, `create_branch`, `create_pull_request`, `slow`, `huge`, `inject` (an injection phrase in its result) and `poisoned` (an injection phrase in its description), and a way to make one tool send a server-to-client `sampling/createMessage`
- [ ] Given a call, when the stub handles it, then it counts calls per tool and records the inbound `Authorization` and header names, exposed to tests through a side channel (endpoint or file), and logs no arguments
- [ ] Given a pytest fixture, when a test uses it, then the stub runs as a subprocess, is ready before the test and is always stopped afterwards (no orphan process), working on Windows and Linux CI
- [ ] Given `app/`, when imported, then nothing imports `scripts/stub_mcp_server.py`

## Technical Notes

- Orchestrator decision (STORY-003, `mcp==2.3.0`): the server class is `mcp.server.mcpserver.MCPServer`; `FastMCP` was its 1.x name. `tests/test_prd023_mcp_sdk_facts.py` shows a working server under `uvicorn` in a thread, with a deadline loop and `should_exit` plus `join`. Reuse that pattern, but run the stub as a **subprocess**, as the AC says. The `sampling` trigger must send a real server-to-client `sampling/createMessage`. With no client callback, the harness's answer is `-32600` (accepted for T12).
- Test infrastructure only; may import `mcp.server` (the import-graph rule applies to `app/` only).
- Look at the existing stub upstream used by PRD-017/021 tests for the subprocess fixture pattern.
- Support enough pages in `tools/list` to test `nextCursor` pagination (STORY-010), e.g. a configurable page size.

## Dependencies

- **Blocked by**: STORY-003
- **Blocks**: STORY-010

## PRD Reference

Source: [`PRD-023/PRD.md`](../../PRDs/PRD-023-mcp-and-skills/PRD.md) — Sections 4 (Test infrastructure), F12, T12
