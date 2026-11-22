---
id: STORY-018
prd: PRD-023
slug: admin-console
title: "Admin console: Actions view MCP filter and columns, Skills panel"
type: feature
priority: medium
complexity: medium
phase: "4 - Bridge, evidence and clients"
status: todo
labels: [ui, admin]
epic_branch: epic/PRD-023-mcp-and-skills
plan: null
report: null
commit: null
depends_on: [STORY-017]
blocks: []
skills: [frontend-design]
created: 2026-11-22
updated: 2026-11-22
---

# STORY-018: Admin console: Actions view MCP filter and columns, Skills panel

## Description

As a security admin, I want the Actions view to show gateway calls with server, skills, outcome and the linked `/v1` row, and a Skills panel, so that I review MCP activity in the console.

## Acceptance Criteria

- [ ] Given `MCP_ENABLED=true`, when the Actions view loads, then it has a surface filter and `server`, `skills`, `outcome` and `linked` (a link to the `/v1` row) columns, and an 'unlinked gateway calls' filter
- [ ] Given `MCP_ENABLED=false`, when the console loads, then neither the filter nor the Skills panel shows
- [ ] Given the Skills panel, when there are zero skills, then it renders an empty state; with skills it lists `GET /skills`
- [ ] Given phone width, when the Actions view shows MCP rows, then it renders without horizontal page overflow

## Technical Notes

- `chat_ui/chat_ui/` admin shell; reuse the existing theme rather than restyle (PRD skills note).
- Skill rule (frontend-design, verbatim): "make deliberate, opinionated choices … specific to this brief" — bounded by the existing admin shell and theme.

## Dependencies

- **Blocked by**: STORY-017
- **Blocks**: None

## PRD Reference

Source: [`PRD-023/PRD.md`](../../PRDs/PRD-023-mcp-and-skills/PRD.md) — Sections 4 (API and admin console), 11 (Quality), F11
