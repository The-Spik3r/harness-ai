# PRD-023-mcp-and-skills: MCP Servers and Agent Skills Behind the Harness — Every tools/call Decided and Audited — Story Board

**PRD**: [PRD.md](./PRD.md)
**Epic Branch**: `epic/PRD-023-mcp-and-skills` (base: `main`)
**Status**: active

## Progress

7/21 stories done — 33%

## Stories

All stories commit on the epic branch `epic/PRD-023-mcp-and-skills`. No per-story branches.

| ID | Title | Type | Status | Complexity | Plan | Commit |
|----|-------|------|--------|------------|------|--------|
| STORY-001 | Spike — verify the MCP protocol facts and re-check the PRD's code evidence against main | spike | ✅ done | medium | [plan](../../plans/PRD-023-mcp-and-skills/completed/STORY-001-mcp-protocol-spike.plan.md) | `7e64933` |
| STORY-002 | Spike — survey OpenCode and the Cline CLI as remote Streamable HTTP MCP clients | spike | ✅ done | medium | [plan](../../plans/PRD-023-mcp-and-skills/completed/STORY-002-client-survey.plan.md) | `4bff962` |
| STORY-003 | Pin the `mcp` SDK and prove its client behaviours offline | technical | ✅ done | medium | [plan](../../plans/PRD-023-mcp-and-skills/completed/STORY-003-mcp-sdk-pin.plan.md) | `0abfc6e` |
| STORY-004 | MCP settings and RBAC vocabulary: `mcp:connect` and `skill:<id>` | feature | ✅ done | small | [plan](../../plans/PRD-023-mcp-and-skills/completed/STORY-004-settings-and-rbac.plan.md) | `d9beeb7` |
| STORY-005 | Action policy: `mcp_tools` / `mcp_opaque_tools` sections and the `tool.not_in_skill` rule | feature | ✅ done | medium | [plan](../../plans/PRD-023-mcp-and-skills/completed/STORY-005-policy-mcp-sections-and-rule.plan.md) | `5ea6493` |
| STORY-006 | Engine: `evaluate(..., surface=McpSurface)` with visibility inside the fail-closed boundary | feature | ✅ done | medium | [plan](../../plans/PRD-023-mcp-and-skills/completed/STORY-006-evaluate-mcp-surface.plan.md) | `ad6a286` |
| STORY-007 | `mcp_config`: servers, skills, aliases, cross-validation, digest, loaded in both lifespans | feature | ✅ done | large | [plan](../../plans/PRD-023-mcp-and-skills/completed/STORY-007-mcp-config-loader.plan.md) | `8fb312b` |
| STORY-008 | Audit: MCP columns on `action_decisions`, `record(..., mcp=)`, `record_outcome`, correlation lookup | feature | ⬜ todo | medium | — | — |
| STORY-009 | Test infrastructure: the scripted stub MCP server and its pytest fixture | technical | ⬜ todo | medium | — | — |
| STORY-010 | `mcp_upstream`: southbound sessions, harness-held credentials, timeouts, refusals, cached `tools/list` | feature | ⬜ todo | large | — | — |
| STORY-011 | Northbound `POST /mcp`: auth, Origin, JSON-RPC parsing, `initialize` / `ping` / notifications | feature | ⬜ todo | medium | — | — |
| STORY-012 | `tools/list`: visibility by held skills and catalogue injection inspection | feature | ⬜ todo | medium | — | — |
| STORY-013 | `tools/call`: usage, visibility, evaluation, record before forward, forward, outcome | feature | ⬜ todo | large | — | — |
| STORY-014 | Results: size cap, pattern inspection under the `tool` cell, uninspected counts | feature | ⬜ todo | medium | — | — |
| STORY-015 | `prompts/list` and `prompts/get` from held skills | feature | ⬜ todo | small | — | — |
| STORY-016 | `/v1` alias resolution at step 7c and gateway correlation at M7 | feature | ⬜ todo | large | — | — |
| STORY-017 | Admin API: `GET /audit/actions` MCP filters and fields, `GET /skills` | feature | ⬜ todo | medium | — | — |
| STORY-018 | Admin console: Actions view MCP filter and columns, Skills panel | feature | ⬜ todo | medium | — | — |
| STORY-019 | `tests/corpora/mcp/` decision corpus and the gateway latency measurement | technical | ⬜ todo | medium | — | — |
| STORY-020 | E2E (opt-in): OpenCode and the Cline CLI through `/mcp` against the stub | technical | ⬜ todo | medium | — | — |
| STORY-021 | Docs: README, features (MCP gateway and skills), roadmap, `.env.example`, examples | technical | ⬜ todo | small | — | — |

## Status Icons
- ⬜ todo
- 🟡 in-progress
- ✅ done
- 🔴 blocked

## Dependencies

- STORY-003 blocked by STORY-001
- STORY-004 blocked by STORY-001
- STORY-005 blocked by STORY-001
- STORY-006 blocked by STORY-005
- STORY-007 blocked by STORY-004, STORY-005
- STORY-008 blocked by STORY-001
- STORY-009 blocked by STORY-003
- STORY-010 blocked by STORY-003, STORY-007, STORY-009
- STORY-011 blocked by STORY-004, STORY-007
- STORY-012 blocked by STORY-006, STORY-010, STORY-011
- STORY-013 blocked by STORY-006, STORY-008, STORY-012
- STORY-014 blocked by STORY-013
- STORY-015 blocked by STORY-011, STORY-007
- STORY-016 blocked by STORY-002, STORY-013
- STORY-017 blocked by STORY-008, STORY-007
- STORY-018 blocked by STORY-017
- STORY-019 blocked by STORY-014, STORY-015, STORY-016
- STORY-020 blocked by STORY-019, STORY-002
- STORY-021 blocked by STORY-020
