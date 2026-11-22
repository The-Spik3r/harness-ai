---
id: STORY-021
prd: PRD-023
slug: docs-and-roadmap
title: "Docs: README, features (MCP gateway and skills), roadmap, `.env.example`, examples"
type: technical
priority: medium
complexity: small
phase: "4 - Bridge, evidence and clients"
status: todo
labels: [docs]
epic_branch: epic/PRD-023-mcp-and-skills
plan: null
report: null
commit: null
depends_on: [STORY-020]
blocks: []
skills: []
created: 2026-11-22
updated: 2026-11-22
---

# STORY-021: Docs: README, features (MCP gateway and skills), roadmap, `.env.example`, examples

## Description

As a platform operator, I want the MCP gateway and skills documented with per-client setup and what it does not cover, so that I can deploy it correctly.

## Acceptance Criteria

- [ ] Given `docs/features.md`, when read, then it has an *MCP gateway and skills* section: topology, config, skills, per-client setup (OpenCode `codemode: false`, Cline), correlation described as correlation not proof, unverified annotations, and a 'what it does not cover' list (Section 9.4)
- [ ] Given `docs/roadmap.md`, when read, then the MCP item is ticked and the 'never executes a tool' sentence is reworded per the scope note
- [ ] Given README and `.env.example`, when read, then the feature and all nine settings are present; `examples/mcp.yaml` stays loaded by a test
- [ ] Given every docs link to a code location, when checked, then it resolves

## Technical Notes

- Last story: sets PRD `status: done`.

## Dependencies

- **Blocked by**: STORY-020
- **Blocks**: None

## PRD Reference

Source: [`PRD-023/PRD.md`](../../PRDs/PRD-023-mcp-and-skills/PRD.md) — Sections 4 (Documentation), 9.4, Scope note
