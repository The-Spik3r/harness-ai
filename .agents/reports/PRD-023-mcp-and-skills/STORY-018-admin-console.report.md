---
story: STORY-018
prd: PRD-023
plan: .agents/plans/PRD-023-mcp-and-skills/completed/STORY-018-admin-console.plan.md
epic_branch: epic/PRD-023-mcp-and-skills
commit: pending
status: COMPLETE
completed: 2026-11-23
---

# Implementation Report - STORY-018: Admin console: Actions view MCP filter and columns, Skills panel

## Summary

With `MCP_ENABLED=true` the Actions view gains a surface chip strip (All surfaces, /v1, Gateway), an "Unlinked gateway calls" toggle and four columns (Server, Skills, Outcome, Linked); a Skills view exists at `/admin/skills`. With it off, none of it is built and the MCP-off grid, min width and read kwargs are unchanged. The console reads in-process (no HTTP), so the "API" is `list_action_decisions(surface=, linked=)` and `mcp_config` + `authz.roles_holding`.

## Validation

| Check | Result |
|-------|--------|
| Backend import | OK |
| Tests (`-m "not db"`, 13 files) | 503 passed, 44 deselected |
| chat_ui startup guard | passed (tests/test_chat_ui_startup_guard.py; a direct probe needs the DB, Docker is down) |
| Full suite | GitHub CI on push (user decision) |

## Deviations from Plan

1. Linked column links to an in-page anchor `#<id>` (`href="#action-<id>"`, row `id="action-<row id>"`), not to a fetched row: no reader shows one row by id. Works only while the `/v1` row is in the 500-row window (cell title says so).
2. Scope line under a surface/unlinked narrowing names the narrowing and shows no whole-table total (`ACTIONS_SCOPE_NARROWED_TEMPLATE`).
3. Turning the unlinked toggle on switches the decision filter to "all" and clears the surface; choosing a surface clears the toggle.
4. Skills page and nav link exist only when `MCP_ENABLED` at import / build time.
5. `_MIN_WIDTH_MCP = "101rem"` (mins 67 + 25 = 92rem + twelve 0.75rem gaps = 9rem), not the plan's 103rem; the arithmetic is commented at `components/actions.py`.
6. Reflex anchor/Var concatenation works (`"action-" + row.row_id`); the plan's plain-text fallback was not needed. The link is `rx.el.a`, not `rx.link`, and the surface strip lives in a new `components/actions_mcp.py`, because the unmodified `test_actions_view.py` forbids `rx.link` and counts exactly one `on_click` in `actions.py`.
7. Census edits (not assertion changes): `tests/test_copy.py` admin_copy name set, `tests/test_admin_shell.py` ADMIN_MODULE_PATTERNS (+ skills.py, actions_mcp.py). No existing assertion modified.

## Files Changed

UPDATE: `admin_models.py`, `admin_formatting.py`, `admin_copy.py`, `admin_state.py`, `components/actions.py`, `components/admin_shell.py`, `chat_ui.py` (all under `chat_ui/chat_ui/`), `tests/test_copy.py`, `tests/test_admin_shell.py`.
CREATE: `components/skills.py`, `components/actions_mcp.py`, `tests/test_admin_mcp_console.py` (13 tests).

## Acceptance Criteria

- [x] AC1 MCP on: surface filter, 4 columns, unlinked filter: `test_mcp_on_actions_view_has_filters_and_columns`, `test_surface_chip_reads_with_the_surface`, `test_unlinked_toggle_reads_linked_false`
- [x] AC2 MCP off: no filter, no Skills panel: `test_mcp_off_view_is_unchanged`, `test_with_mcp_off_both_events_are_no_ops`, `test_skills_page_is_registered_only_with_mcp_on`
- [x] AC3 Skills empty state / list: `test_skills_empty_state`, `test_skills_list_from_config`, `test_load_reads_skills_only_with_mcp_on`
- [x] AC4 phone width: `test_mcp_table_scrolls_inside_its_container` (inside `.hx-scroll`, `overflow_x=auto`, min_width; skills have none)
