---
id: STORY-002
prd: PRD-023
slug: client-survey
title: "Spike — survey OpenCode and the Cline CLI as remote Streamable HTTP MCP clients"
type: spike
priority: high
complexity: medium
phase: "1 - Verify the protocol and the clients"
status: done
labels: [spike, mcp, clients]
epic_branch: epic/PRD-023-mcp-and-skills
plan: .agents/plans/PRD-023-mcp-and-skills/completed/STORY-002-client-survey.plan.md
report: .agents/reports/PRD-023-mcp-and-skills/STORY-002-client-survey.report.md
commit: 4bff962
depends_on: []
blocks: [STORY-016, STORY-020]
skills: []
created: 2026-11-22
updated: 2026-11-22
---

# STORY-002: Spike — survey OpenCode and the Cline CLI as remote Streamable HTTP MCP clients

## Description

As an integrating developer, I want to know exactly how OpenCode and the Cline CLI connect to a remote MCP server with a static bearer header and how they name its tools, so that the gateway and the `/v1` alias prefixes match real clients.

## Acceptance Criteria

- [ ] Given the OpenCode version installed on this machine (PRD names 2.0.10; PRD-021 verified 2.3.2), when surveyed from its source or docs at a pinned tag, then `SOURCES.md` records its remote MCP config (`type: remote`, `url`, `headers`, `codemode: false`), whether it insists on OAuth discovery on a `401`, and the exact tool-name prefix for a server named `harness`
- [ ] Given the Cline CLI installed here (3.0.74 per PRD-021) and Cline 4.x, when surveyed, then `SOURCES.md` records their Streamable HTTP config with headers, their name prefixing/sanitizing/64-char hashing for `harness`, and OAuth behaviour
- [ ] Given the survey, when done, then the report states whether `v1_aliases.prefixes: ["harness_", "harness__"]` (Section 6.6) is right, which `tools/list` / `initialize` fields each client needs, and whether each sends an `Origin` header
- [ ] Given the GitHub MCP server's `push_files` / `create_branch` / `create_pull_request`, when checked at a pinned commit, then `SOURCES.md` records their argument shapes (`files[].path`)

## Technical Notes

- Survey only; no application code. Append to `tests/corpora/mcp/SOURCES.md` (created by STORY-001).
- Local clients: find them with `where opencode` / `where cline`; record versions. PRD-021's E2E (`tests/test_e2e_cline_realtime_script.py`) shows how they were driven.
- Existing evidence: `tests/corpora/actions/SOURCES.md:80,112-113,160,222`.

## Dependencies

- **Blocked by**: None
- **Blocks**: STORY-016, STORY-020

## PRD Reference

Source: [`PRD-023/PRD.md`](../../PRDs/PRD-023-mcp-and-skills/PRD.md) — Sections 6.8, 9.1, 15 (Facts to verify: Clients, Servers), R2
