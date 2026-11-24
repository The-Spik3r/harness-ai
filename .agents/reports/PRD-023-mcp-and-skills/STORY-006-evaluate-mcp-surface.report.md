---
story: STORY-006
prd: PRD-023
plan: .agents/plans/PRD-023-mcp-and-skills/completed/STORY-006-evaluate-mcp-surface.plan.md
epic_branch: epic/PRD-023-mcp-and-skills
commit: ad6a286
status: COMPLETE
completed: 2026-11-22
---

# Implementation Report - STORY-006: Engine `evaluate(..., surface=McpSurface)`

## Summary

`action_policy.py` gains a frozen `McpSurface(server, visible)`, `V1 = None`, two private seams (`_is_visible`, `_select_tables`) and a keyword-only `surface` on `evaluate`. Inside the existing fail-closed `try`, a name outside `visible` becomes one `tool.not_in_skill` classification and `map_tool_call` is never called; a visible name is mapped through the server's `mcp_tools` / `mcp_opaque_tools` (never the `/v1` tables). Decide, fold, reason and boundary are unchanged. `evaluate_all` is unchanged.

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| Targeted tests (policy, corpus, vocabulary, adapters; `-k "not round_trips"`) | 1235 passed, 1 skipped, 6 deselected |
| `tests/test_untouched_app.py` | 9 passed |
| E2E | engine-only; covered by the gateway tests through the real `BUILT_IN_POLICY` and `authz` |
| Full suite | GitHub CI on push (user decision) |

Docker Desktop was down: the DB test `test_every_decision_round_trips_through_record_and_the_audit_api` (and 5 other `round_trips` cases) was deselected; CI covers it.

## Files Changed

- `app/services/action_policy.py` (UPDATE)
- `tests/test_action_policy.py` (UPDATE: new "PRD-023 STORY-006" section; census now includes a hidden gateway call, exclusion removed)
- `tests/test_action_corpus.py` (UPDATE: census uses one in-test `McpSurface` case)

## Deviations from Plan

- Corpus census: approved by the orchestrator, one in-test `McpSurface` case instead of a corpus file; the MCP corpus is STORY-019 (the plan said STORY-012).
- Hidden branch uses an explicit `hidden` flag rather than a `result = None` sentinel, so a mapper returning None still fails closed.

## Tests Written

New in `tests/test_action_policy.py`: surface keyword-only / V1 / default-equality sweep, frozen dataclass, gateway DROP TABLE deny and grant, hidden tool for every grant, `map_tool_call` not called, per-server table selection, fail-closed in both seams and a broken surface object, whole-policy digest.

## Acceptance Criteria

- [x] AC1 default surface unchanged: `test_surface_is_keyword_only_and_v1_is_none_and_default_changes_nothing`
- [x] AC2 sql.ddl deny / granted allow: `test_gateway_drop_table_denied_and_granted`
- [x] AC3 not_in_skill, no grant lifts it, no mapping consulted: `test_a_hidden_tool_is_not_in_skill_even_for_every_action_grant`, `test_a_hidden_tool_does_not_call_map_tool_call`
- [x] AC4 fail-closed: `test_a_failure_in_visibility_or_table_selection_fails_closed`, `test_a_surface_object_without_visible_fails_closed`
- [x] AC5 whole-policy digest: `test_the_gateway_digest_is_the_whole_policys`
