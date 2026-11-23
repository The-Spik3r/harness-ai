---
id: STORY-012
prd: PRD-023
slug: tools-list-visibility
title: "`tools/list`: visibility by held skills and catalogue injection inspection"
type: feature
priority: high
complexity: medium
phase: "3 - The gateway"
status: in-progress
labels: [mcp, security, rbac]
epic_branch: epic/PRD-023-mcp-and-skills
plan: .agents/plans/PRD-023-mcp-and-skills/STORY-012-tools-list-visibility.plan.md
report: null
commit: null
depends_on: [STORY-006, STORY-010, STORY-011]
blocks: [STORY-013]
skills: []
created: 2026-11-22
updated: 2026-11-22
---

# STORY-012: `tools/list`: visibility by held skills and catalogue injection inspection

## Description

As a security admin, I want `tools/list` to show only the tools of the skills a role holds, and to withhold any tool whose description tries to instruct the model, so that the catalogue itself is controlled.

## Acceptance Criteria

- [ ] Given a role holding `skill:open-pull-request`, when it calls `tools/list`, then it gets exactly `github__create_branch`, `github__push_files`, `github__create_pull_request` with upstream `description`, `inputSchema`, and `title` / `outputSchema` / `annotations` when present; a plain `user` gets `[]`; RBAC off with the built-in matrix gets `[]`
- [ ] Given the stub's `poisoned` tool in a held skill, when listed, then it is omitted and a `WARNING` names the server, the tool and the matched list but contains no description text; descriptions inside `inputSchema` and `title` are inspected too, with the `injection` list only
- [ ] Given one upstream down or timing out, when `tools/list` runs, then the others' tools are returned, a `WARNING` is logged and the call succeeds; a skill tool the upstream does not list is omitted with an `INFO` once per cache period
- [ ] Given any `tools/list`, when it completes, then no `action_decisions` row is written and an `INFO` line records user, servers, tool count, `mcp_config_digest` and a description hash per tool (T4)

## Technical Notes

- Orchestrator decision (STORY-002): northbound `tools/list` returns every visible tool in **one page with no `nextCursor`**, because OpenCode reads only the first page. OpenCode drops a tool whose `inputSchema.type` is not `"object"`. Pass the schema through unchanged and do not repair it, but log `INFO` when a visible tool's schema is not an object. Cline 4.x reads `annotations`, so pass them through. The GitHub server's `x-mcp-header`, `icons` (`data:` URIs) and `outputSchema` pass through unchanged.
- Orchestrator decision (STORY-012 plan): icons and _meta are dropped (STORY-002 safe default); this supersedes "icons pass through" above.
- Visibility: `held = {s : holds(identity, 'skill:'+s.id)}`, `wanted = ⋃ s.tools` (Section 6.5). Upstream lists fetched concurrently with the per-server timeout.
- New `app/services/mcp_gateway.py` starts here; `pattern_detector.inspect` with the injection list (PRD-011).
- Withheld tools must also be excluded from the visible set used by `tools/call` (STORY-013): calling `poisoned` gets `-32602`.

## Dependencies

- **Blocked by**: STORY-006, STORY-010, STORY-011
- **Blocks**: STORY-013

## PRD Reference

Source: [`PRD-023/PRD.md`](../../PRDs/PRD-023-mcp-and-skills/PRD.md) — Sections 6.5, F5, D7, D12, O4, O6, T3, T4, User Stories 1, 7
