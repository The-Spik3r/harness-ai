---
id: STORY-015
prd: PRD-023
slug: prompts-from-skills
title: "`prompts/list` and `prompts/get` from held skills"
type: feature
priority: medium
complexity: small
phase: "3 - The gateway"
status: done
labels: [mcp, skills]
epic_branch: epic/PRD-023-mcp-and-skills
plan: .agents/plans/PRD-023-mcp-and-skills/completed/STORY-015-prompts-from-skills.plan.md
report: .agents/reports/PRD-023-mcp-and-skills/STORY-015-prompts-from-skills.report.md
commit: 2c26c89
depends_on: [STORY-011, STORY-007]
blocks: [STORY-019]
skills: []
created: 2026-11-22
updated: 2026-11-23
---

# STORY-015: `prompts/list` and `prompts/get` from held skills

## Description

As an integrating developer, I want each skill I hold served as an MCP prompt carrying its instructions, so that my agent can load how to use the skill.

## Acceptance Criteria

- [ ] Given a role holding `skill:open-pull-request` and `skill:run-migration`, when it calls `prompts/list`, then it gets `skill-open-pull-request` and `skill-run-migration` with their descriptions, and nothing for skills it does not hold
- [ ] Given `prompts/get` on a held skill, when called, then it returns the instructions as one `user` message
- [ ] Given `prompts/get` on a skill the caller does not hold or an unknown name, when called, then `-32602` with the same message for both
- [ ] Given any prompts call, when done, then no row is written and no upstream is contacted (D19)

## Technical Notes

- Upstream prompts are not proxied (D19).
- Handler seam from STORY-011 in `mcp_gateway.py`.

## Dependencies

- **Blocked by**: STORY-011, STORY-007
- **Blocks**: STORY-019

## PRD Reference

Source: [`PRD-023/PRD.md`](../../PRDs/PRD-023-mcp-and-skills/PRD.md) — Sections 6.6, F8, D19, O11
