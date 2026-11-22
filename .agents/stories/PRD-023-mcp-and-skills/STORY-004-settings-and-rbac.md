---
id: STORY-004
prd: PRD-023
slug: settings-and-rbac
title: "MCP settings and RBAC vocabulary: `mcp:connect` and `skill:<id>`"
type: feature
priority: high
complexity: small
phase: "2 - Vocabulary and configuration"
status: todo
labels: [config, rbac]
epic_branch: epic/PRD-023-mcp-and-skills
plan: null
report: null
commit: null
depends_on: [STORY-001]
blocks: [STORY-007, STORY-011]
skills: []
created: 2026-11-22
updated: 2026-11-22
---

# STORY-004: MCP settings and RBAC vocabulary: `mcp:connect` and `skill:<id>`

## Description

As a platform operator, I want the nine `MCP_*` settings and the `mcp:connect` / `skill:<id>` permissions, so that the gateway can be configured and roles can be given skills.

## Acceptance Criteria

- [ ] Given `app/config.py`, when loaded, then `MCP_ENABLED`, `MCP_CONFIG_FILE`, `MCP_CALL_TIMEOUT_SECONDS`, `MCP_MAX_REQUEST_BYTES`, `MCP_MAX_RESULT_BYTES`, `MCP_TOOLS_CACHE_SECONDS`, `MCP_UPSTREAM_SESSION_IDLE_SECONDS`, `MCP_LINK_WINDOW_SECONDS`, `MCP_ALLOWED_ORIGINS` exist with Section 9.3's defaults, and each out-of-range value fails validation with a test per bound
- [ ] Given `authz`, when a roles file grants `skill:open-pull-request`, then `authz.load()` accepts it; `skill:Bad_Id` and a 49-char id are refused naming the file, role and rule (pattern `skill:[a-z0-9][a-z0-9-]{0,47}`)
- [ ] Given the built-in matrix, when inspected, then `admin` and `user` hold `mcp:connect` (O1) and no built-in role holds any `skill:*` (D6); `mcp:connect` is in `_KNOWN_PERMISSIONS`
- [ ] Given `.env.example`, when read, then the nine settings are documented

## Technical Notes

- `skill:<id>` existence is checked later by `mcp_config.load()` (STORY-007), not here.
- Existing permission/built-in-matrix tests that enumerate permissions get a comment citing PRD-023 O1/D6 when their assertion changes.
- Setting `MCP_ENABLED=true` with an empty `MCP_CONFIG_FILE` is a startup error, but it is raised by `mcp_config.load()` (STORY-007); here only the field types/ranges.

## Dependencies

- **Blocked by**: STORY-001
- **Blocks**: STORY-007, STORY-011

## PRD Reference

Source: [`PRD-023/PRD.md`](../../PRDs/PRD-023-mcp-and-skills/PRD.md) — Sections 4 (RBAC, Settings), 9.1, 9.3, D6, O1
