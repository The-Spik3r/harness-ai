---
story: STORY-012
prd: PRD-023
plan: .agents/plans/PRD-023-mcp-and-skills/completed/STORY-012-tools-list-visibility.plan.md
epic_branch: epic/PRD-023-mcp-and-skills
commit: pending
status: COMPLETE
completed: 2026-11-22
---

# Implementation Report — STORY-012: `tools/list` visibility and catalogue inspection

**Plan**: `.agents/plans/PRD-023-mcp-and-skills/completed/STORY-012-tools-list-visibility.plan.md`
**Epic Branch**: `epic/PRD-023-mcp-and-skills`
**Commit**: `pending`

## Summary

New `app/services/mcp_gateway.py` (no `mcp` import) with `Catalogue` and `async visible_catalogue(identity)`: held tools from `mcp_config.visible_tools`, concurrent cached upstream lists, held-and-listed filter, `injection` inspection of `description`, `title` and every `description` inside `inputSchema`, sorted prefixed output, and the `callable` map for STORY-013. `handle_tools_list` now calls it and logs the T4 INFO line (user, servers, count, digest, per-description sha256). No row is written.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Gateway module | `app/services/mcp_gateway.py` | done |
| 2 | Wire `tools/list` + docstring row | `app/routers/mcp.py` | done |
| 3 | Tests | `tests/test_mcp_gateway.py` | done |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| Tests (`-m "not db"`: gateway, endpoint, upstream, import graph, untouched_app, caddyfile_routes) | 107 passed |
| E2E (real router + stub subprocess over HTTP) | pass |
| Full suite | GitHub CI on push (user decision) |

## Deviations from Plan

- Orchestrator decision: `icons` and `_meta` are dropped, not passed through (STORY-002 safe default). `UpstreamTool` unchanged. Story Technical Notes carry a line saying this supersedes "icons pass through".
- Plan additions kept: over-length text is withheld (fail closed); the built-in `injection` list is the fallback if a deployment file has none.
- The stub's tools have empty descriptions, so the HTTP hash check proves the hash format, not absence of description text; text absence is proven by the `poisoned` phrase never appearing in logs.

## Tests Written

`tests/test_mcp_gateway.py`: held skill lists exact sorted tools with callable map; plain user and RBAC-off list nothing; order independent of config; optional keys and `x-mcp-header` pass through; poisoned stub tool withheld with phrase-free WARNING; injection in nested property, title, `items/oneOf`, description withheld; property names and `default` not inspected; scan ceiling fails closed; missing `injection` list falls back; failing server (3 error kinds) and stopped stub tolerated without leaking text; unlisted tool INFO once per period (injected clock, TTL 0); non-object schemas unchanged with INFO; HTTP end to end with no row and audit line; AST guard (no `mcp` import).

## Acceptance Criteria

- [x] AC1 held skill -> 3 tools; user `[]`; RBAC off `[]` (`test_held_skill_lists_exactly_its_tools_sorted`, `test_plain_user_and_rbac_off_list_nothing`)
- [x] AC2 poisoned withheld, WARNING without text; schema/title inspected (`test_poisoned_tool_is_withheld_from_the_stub_catalogue`, `test_injection_in_any_inspected_text_withholds`)
- [x] AC3 down/timeout tolerated; unlisted INFO once per period (`test_a_failing_server_...`, `test_unlisted_tool_...`)
- [x] AC4 no `action_decisions` row; INFO with user, servers, count, digest, hashes (`test_http_tools_list_end_to_end`)
