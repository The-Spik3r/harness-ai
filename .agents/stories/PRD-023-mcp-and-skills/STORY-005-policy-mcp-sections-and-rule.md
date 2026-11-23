---
id: STORY-005
prd: PRD-023
slug: policy-mcp-sections-and-rule
title: "Action policy: `mcp_tools` / `mcp_opaque_tools` sections and the `tool.not_in_skill` rule"
type: feature
priority: high
complexity: medium
phase: "2 - Vocabulary and configuration"
status: done
labels: [action-policy, config, security]
epic_branch: epic/PRD-023-mcp-and-skills
plan: .agents/plans/PRD-023-mcp-and-skills/completed/STORY-005-policy-mcp-sections-and-rule.plan.md
report: .agents/reports/PRD-023-mcp-and-skills/STORY-005-policy-mcp-sections-and-rule.report.md
commit: 5ea6493
depends_on: [STORY-001]
blocks: [STORY-006, STORY-007]
skills: []
created: 2026-11-22
updated: 2026-11-22
---

# STORY-005: Action policy: `mcp_tools` / `mcp_opaque_tools` sections and the `tool.not_in_skill` rule

## Description

As a security admin, I want per-server MCP mappings in `ACTION_POLICY_FILE` and a non-grantable `tool.not_in_skill` rule, so that gateway tools are classified by the same engine without reaching `/v1` mappings.

## Acceptance Criteria

- [ ] Given `ACTION_POLICY_FILE` with `mcp_tools: {postgres-staging: {query: {kind: sql, target: sql}}}` and `mcp_opaque_tools: {github: {create_pull_request: flag}}`, when `action_config.load()` runs, then each server mapping is validated by the existing `_validate_tools` / `_validate_opaque_tools`, the loaded policy exposes `mcp_tools` / `mcp_opaque_tools`, and both are part of `policy_digest()`
- [ ] Given an empty server mapping, a tool in both sections for one server, a server id outside `[a-z0-9][a-z0-9-]{0,31}`, or an invalid mapping, when loaded, then `ActionConfigError` names the file and node (one failing-file test each)
- [ ] Given the rule set, when inspected, then `tool.not_in_skill` exists with decision `deny`, no grant, subject `"a tool outside the caller's skills"`, and is in `NON_GRANTABLE_RULES`: 26 rules and 11 non-grantable; the PRD-016 count assertions change 25→26 and 10→11 with a comment citing PRD-023 D7
- [ ] Given `MCP_ENABLED=false`, when a policy file has the new sections, then it still validates (portable policy files)

## Technical Notes

- Files: `app/services/action_config.py` (`_FILE_SECTIONS`, `BUILT_IN_POLICY` with empty MCP tables, digest), `app/services/action_classifiers/__init__.py` (`RuleId`, `NON_GRANTABLE_RULES`).
- Do not change `evaluate()` here (STORY-006). The 'server id absent from MCP_CONFIG_FILE' check belongs to `mcp_config.load()` (STORY-007).

## Dependencies

- **Blocked by**: STORY-001
- **Blocks**: STORY-006, STORY-007

## PRD Reference

Source: [`PRD-023/PRD.md`](../../PRDs/PRD-023-mcp-and-skills/PRD.md) — Sections 4 (Action policy), 6.4, 9.3 (ACTION_POLICY_FILE additions), D4, D7
