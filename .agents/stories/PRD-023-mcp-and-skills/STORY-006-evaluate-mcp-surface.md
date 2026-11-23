---
id: STORY-006
prd: PRD-023
slug: evaluate-mcp-surface
title: "Engine: `evaluate(..., surface=McpSurface)` with visibility inside the fail-closed boundary"
type: feature
priority: high
complexity: medium
phase: "2 - Vocabulary and configuration"
status: done
labels: [action-policy, security]
epic_branch: epic/PRD-023-mcp-and-skills
plan: .agents/plans/PRD-023-mcp-and-skills/completed/STORY-006-evaluate-mcp-surface.plan.md
report: .agents/reports/PRD-023-mcp-and-skills/STORY-006-evaluate-mcp-surface.report.md
commit: ad6a286
depends_on: [STORY-005]
blocks: [STORY-012, STORY-013]
skills: []
created: 2026-11-22
updated: 2026-11-22
---

# STORY-006: Engine: `evaluate(..., surface=McpSurface)` with visibility inside the fail-closed boundary

## Description

As a security admin, I want a gateway call decided by the unchanged PRD-016 engine reading the server's MCP tables, with visibility checked first, so that one engine decides both surfaces.

## Acceptance Criteria

- [ ] Given `evaluate(call, identity)` with `surface` omitted, when the existing PRD-016/017 suites run, then they pass unchanged (apart from STORY-005's count changes)
- [ ] Given `surface=McpSurface('postgres-staging', frozenset({'query'}))` and `{"sql": "DROP TABLE users"}`, when evaluated for a role without `action:sql:ddl`, then the decision is `deny` / `sql.ddl`; for a role holding `action:sql:ddl` it is `allow` with `granted_by='action:sql:ddl'`
- [ ] Given a call whose name is not in `surface.visible`, when evaluated, then it is `deny` / `tool.not_in_skill` even for a role holding every `action:*` grant, and no mapping is consulted
- [ ] Given a monkeypatched failure inside the visibility check or MCP table selection, when evaluated, then the result is the fail-closed `deny` / `tool.malformed` (PRD-016 T9) and `evaluate` does not raise
- [ ] Given any surface, when the decision's digest is read, then it is the whole policy's `policy_digest()`

## Technical Notes

- Section 6.4 sketch: `McpSurface(server, visible)` frozen dataclass, `V1: Final = None`; `map_tool_call` already takes the tables as parameters (`app/services/action_adapters.py`), so the adapter layer does not change.
- `action_policy` stays pure: no I/O, no settings reads.
- Alias resolution for `/v1` (Section 6.8) is STORY-016, not here.
- Orchestrator decision (STORY-005 implement): two PRD-016 census tests temporarily exclude `tool.not_in_skill` because nothing produced it yet: `tests/test_action_policy.py::test_every_reason_is_the_fixed_template_plus_the_calls_fragment` and `tests/test_action_corpus.py::test_every_rule_id_is_reported_by_some_file`. This story adds a gateway (`McpSurface`) case that produces the rule and drops both exclusions (keep a PRD-023 D7 comment).
- Orchestrator decision (STORY-005): `ActionPolicy.mcp_tools` / `mcp_opaque_tools` are `Mapping[server, Mapping[tool, …]]` (`MappingProxyType` at both levels, empty by default); select with `policy.mcp_tools.get(surface.server, EMPTY)`.

## Dependencies

- **Blocked by**: STORY-005
- **Blocks**: STORY-012, STORY-013

## PRD Reference

Source: [`PRD-023/PRD.md`](../../PRDs/PRD-023-mcp-and-skills/PRD.md) — Sections 6.4, F4, D4, D7, T6, T9
