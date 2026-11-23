---
story: STORY-015
prd: PRD-023
plan: .agents/plans/PRD-023-mcp-and-skills/completed/STORY-015-prompts-from-skills.plan.md
epic_branch: epic/PRD-023-mcp-and-skills
commit: pending
status: COMPLETE
completed: 2026-11-23
---

# Implementation Report - STORY-015: `prompts/list` and `prompts/get` from held skills

## Summary

`prompts/list` returns one `skill-<id>` prompt per held skill; `prompts/get` returns that skill's instructions as one `user` text message. Unknown and not-held names share one code path and one message (`-32602`, "Unknown prompt"). `arguments` is ignored. No row, no usage admit, no upstream call. Thin router adapters over `mcp_gateway.list_prompts` / `get_prompt`.

## Files Changed

| File | Action |
|------|--------|
| `app/services/mcp_gateway.py` | UPDATE (`UNKNOWN_PROMPT_MESSAGE`, `list_prompts`, `get_prompt`) |
| `app/routers/mcp.py` | UPDATE (two handlers, docstring) |
| `tests/test_mcp_endpoint.py` | UPDATE (`test_seam_placeholders` -32601 -> -32602, new wire-shape test) |
| `tests/test_mcp_gateway.py` | UPDATE (6 new tests) |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| Tests (`-m "not db"`: test_mcp_endpoint, test_mcp_gateway, test_untouched_app) | 87 passed |
| E2E (wire-shape test over TestClient) | pass |
| Full suite | GitHub CI on push (user decision) |

## Deviations from Plan

None. `mcp:connect` is enforced at M0, no check added.

## Acceptance Criteria

- [x] AC1 list only held: `test_prompts_list_only_held_skills`
- [x] AC2 get is one user message: `test_prompts_get_returns_instructions_as_user_message`
- [x] AC3 -32602, same message: `test_prompts_get_unknown_and_not_held_share_one_message`, `test_seam_placeholders`, `test_prompts_wire_shape_and_one_unknown_message`
- [x] AC4 no row/upstream/admit: `test_prompts_touch_no_audit_usage_or_upstream`
