---
story: STORY-017
prd: PRD-023
plan: .agents/plans/PRD-023-mcp-and-skills/completed/STORY-017-admin-api.plan.md
epic_branch: epic/PRD-023-mcp-and-skills
commit: pending
status: COMPLETE
completed: 2026-11-23
---

# Implementation Report - STORY-017: Admin API for MCP audit and skills

## Summary

`GET /audit/actions` gains `?surface=`, `?server=`, `?outcome=`, `?linked=` (fixed SQL clauses in `list_action_decisions`, ANDed with scoping) and the eight PRD 10 entry fields. New read-only `GET /skills` (`stats:read`) lists skills with holding roles and the config digest; with `MCP_ENABLED=false` it answers 200 empty with a null digest. `/skills` is added to the Caddy matcher.

## Files Changed

`app/db/database.py`, `app/models/schemas.py`, `app/services/authz.py` (`roles_holding`), `app/routers/admin.py`, `Caddyfile`, `tests/test_caddyfile_routes.py`, `tests/test_admin_actions.py`, `tests/test_schemas.py`, `tests/test_admin_mcp.py` (new).

## Validation

- Import check OK.
- Targeted `-m "not db"`: 375 passed, 46 deselected (db tests run in CI; Docker down locally).
- Full suite: GitHub CI on push (user decision).

## Deviations from Plan

- `tests/test_schemas.py::test_actions_response_shape` also needed the eight new default keys (not named in the plan); comment cites PRD-023 D21.
- `linked=false` clause is parenthesised `(surface = 'mcp' AND linked_decision_id IS NULL)` so ANDing stays unambiguous.

## Acceptance Criteria

- [x] Filters, fields, scoping: `test_admin_mcp.py` db tests (CI), `test_entry_has_exactly_the_section_10_fields`
- [x] Invalid value -> 422: parametrized test (passes locally)
- [x] `/skills` shape, 403 (non-db identity override), off = empty 200, no secrets: passes locally
