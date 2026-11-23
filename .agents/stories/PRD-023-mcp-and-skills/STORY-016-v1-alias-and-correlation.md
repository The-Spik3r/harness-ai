---
id: STORY-016
prd: PRD-023
slug: v1-alias-and-correlation
title: "`/v1` alias resolution at step 7c and gateway correlation at M7"
type: feature
priority: high
complexity: large
phase: "4 - Bridge, evidence and clients"
status: in-progress
labels: [v1, mcp, action-policy, audit]
epic_branch: epic/PRD-023-mcp-and-skills
plan: .agents/plans/PRD-023-mcp-and-skills/STORY-016-v1-alias-and-correlation.plan.md
report: null
commit: null
depends_on: [STORY-002, STORY-013]
blocks: [STORY-019]
skills: []
created: 2026-11-22
updated: 2026-11-23
---

# STORY-016: `/v1` alias resolution at step 7c and gateway correlation at M7

## Description

As an auditor, I want a tool the model proposed through `/v1` under a gateway alias decided like its gateway execution, and the execution linked to that request, so that what was asked, proposed and run read together.

## Acceptance Criteria

- [ ] Given `MCP_ENABLED=true` and a `/v1` `tool_call` named `harness_postgres-staging__query` with `DROP TABLE` visible to the caller, when step 7c decides it, then it is `deny` / `sql.ddl` (today `tool.unknown`); with `SELECT` it is released; the row has `surface='v1'`, `mcp_server`, `arguments_canonical_hash`
- [ ] Given a name where two prefixes resolve, when decided, then `tool.malformed`; where none resolves (or a Cline hash-truncated name), then today's behaviour unchanged; with `MCP_ENABLED=false`, then every PRD-017 test passes unchanged
- [ ] Given a released alias decision and a matching gateway call (same user, server, tool, canonical arguments hash) within `MCP_LINK_WINDOW_SECONDS`, when the gateway records it, then the MCP row carries that `/v1` row's `audit_id` and `linked_decision_id`; outside the window or with no match, both are NULL; a row already linked is not reused
- [ ] Given step 7c, when alias resolution runs, then it adds no database read; the real-time streaming path (PRD-021) and the buffered path both apply it

## Technical Notes

- Orchestrator decision (STORY-002): the prefixes `harness_` (OpenCode 2.3.2, with `codemode: false`) and `harness__` (Cline) are confirmed. There is no Cline hash reverse map: a hashed name stays `tool.unknown` (a stated limitation, PRD 6.8). STORY-007 warns at startup for ids longer than 55 characters. With `codemode` unset, OpenCode shows only `execute` (still denied).
- Section 6.8. Alias resolution needs `visible_tools(identity)` and the prefixes from `mcp_config` passed into the engine call; keep `action_policy` free of I/O (the visible set is computed outside).
- Correlation uses STORY-008's lookup helper; fill STORY-013's M7 seam.
- Prefixes from STORY-002's survey.

- Orchestrator decision (STORY-008 plan): alias rows keep the raw `/v1` `tool_name` the model emitted (e.g. `harness__github__push_files`), with `mcp_server` set. Correlation calls `database.find_linkable_v1_decision(user_id, server, tool_names, hash, window_seconds)` passing the exact candidates `prefix + server + "__" + tool` for each configured prefix. That helper is read-only: closing the claim race (two gateway calls matching one `/v1` row) is this story's job. `McpRecord` carries an optional `audit_id` for the correlated row's audit id (PRD M7 predates PRD-018).
## Dependencies

- **Blocked by**: STORY-002, STORY-013
- **Blocks**: STORY-019

## PRD Reference

Source: [`PRD-023/PRD.md`](../../PRDs/PRD-023-mcp-and-skills/PRD.md) — Sections 6.8, F9, D15, O8, User Story 6, R5
