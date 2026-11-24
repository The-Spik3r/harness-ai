---
story: STORY-018
prd: PRD-023
slug: admin-console
title: "Admin console: Actions view MCP filter and columns, Skills panel"
type: ENHANCEMENT
complexity: medium
epic_branch: epic/PRD-023-mcp-and-skills
created: 2026-11-23
---

# Plan: Admin console: Actions view MCP filter and columns, Skills panel

## Summary

The console does **not** call the HTTP API: `AdminState` imports read functions in-process (`chat_ui/chat_ui/admin_state.py:1-60`; the Providers view reads `health.providers_status()` the same way, `:1535-1557`). So STORY-017's API is consumed through the in-process readers it uses: `list_action_decisions(surface=, mcp_server=, outcome=, linked=)` (`app/db/database.py:3594-3602`) and `mcp_config.get_config().skills` + `authz.roles_holding` (mirroring `app/routers/admin.py:255-280`). The chat_ui process already loads `mcp_config` (`chat_ui/chat_ui/chat_ui.py:~287`, STORY-007) and `admin_state.py` already imports `settings`, so `settings.MCP_ENABLED` is read directly: no new mechanism. With MCP on, the Actions view gains a surface chip row, an "Unlinked gateway calls" toggle and four columns (server, skills, outcome, linked); a new Skills view (`/admin/skills`) lists the configured skills. With MCP off every new element is absent at build time (Python `if settings.MCP_ENABLED`), the read passes exactly the old kwargs, and existing chat_ui tests stay unmodified.

- Story: `.agents/stories/PRD-023-mcp-and-skills/STORY-018-admin-console.md`
- PRD sections used: §4 (API and admin console), F11, §10 (`/audit/actions`, `/skills`), D20/D21
- Systems affected: chat_ui only (`admin_state`, `admin_models`, `admin_formatting`, `admin_copy`, two components, shell nav, page registration). No backend change.

## Design Decisions

- **MCP off is today's console.** Builders test `settings.MCP_ENABLED` at call time (tests can monkeypatch); grid, head, row cells, chip strip, nav link and page registration are conditional. `read_actions` builds `{limit, decision}` and adds `surface`/`linked` **only when set**: `tests/test_actions_view.py:402-418` asserts `console.asked == [{"limit": 500, "decision": decision}]` and must pass unchanged.
- **Filters** (state): `actions_surface: str = ""` ("" = all, `"v1"`, `"mcp"`; falsy for `reset()`), `actions_unlinked: bool = False`. Unlinked on sends `linked=False` only (backend already implies `surface='mcp'`). Turning it on also sets `actions_filter = "all"`, because the default Denied chip would hide the typical unlinked row (an allowed gateway call); comment it. Events `choose_actions_surface(key)` / `toggle_actions_unlinked()` ignore unknown keys, no-op when `not settings.MCP_ENABLED`, and return `AdminState.load_actions` like `choose_actions_filter` (`admin_state.py:1294-1305`). The `load_actions` stale guard (`:1404-1418`) compares the tuple `(filter, surface, unlinked)`.
- **Scope line.** `count_action_decisions` totals are whole-table, so under a surface/unlinked narrowing the line would lie. New `ACTIONS_SCOPE_NARROWED_TEMPLATE = "{shown} most recent {decision}, {narrow}"` (no total), narrow words "/v1 calls", "gateway calls", "unlinked gateway calls". The un-narrowed text is unchanged.
- **Linked column (DEVIATION from "a link to the /v1 row").** No API or reader shows one row by id (`list_action_decisions` has no id filter; STORY-017 must not change). Cheapest honest rendering: with MCP on, each row gets DOM `id="action-<row id>"`; the linked cell is a link `#<linked_id>` with `href="#action-<linked_id>"`, which jumps to the `/v1` row when it is inside the current 500-row window (use the All or /v1 surface chip), with a `title` saying so otherwise. A gateway row with no link shows the word "unlinked"; a `/v1` row shows the absent mark. Report this as a deviation.
- **Skills panel is a view**: `/admin/skills`, `VIEW_SKILLS`; nav link and `app.add_page` only when `settings.MCP_ENABLED` at import (pages register at import, `chat_ui.py:205-225`). Static route like `/admin/providers`, not a backend path (`Caddyfile:5` matcher has `/skills` exact; no Caddy change). Read is in memory in `load()` with its own `skills_error`, Providers' shape. The `mcp_config_digest` is the caption.
- **Phone width.** Same rule as the existing Actions view: the table sits in `.hx-scroll` with `overflow_x="auto"` and a `min_width`, so it scrolls inside its container and the page does not (`components/actions.py:77-86, 226-238, 387-396`); the new chip strip uses `wrap="wrap"` (`:335-356`). Skills are stacked blocks (flex-wrap), not a table.

## Skills In Use

| Skill | Why it applies | Tasks |
|-------|---------------|-------|
| frontend-design (`.agents/skills/frontend-design/SKILL.md`) | "Structure is information", bounded by the existing admin shell and theme (PRD skills note; `actions.py:9-15` already cites it). No new inks, chart or decoration; `theme.*` tokens and verdict inks only | 4, 5 |
| reflex-docs (`chat_ui/AGENTS.md`) | Check `rx.link`, `rx.cond`, `custom_attrs` id and Var concatenation (`"action-" + row.row_id`) against the installed Reflex, not memory | 4 |

## Patterns to Follow

| Category | Source | Mirror |
|----------|--------|--------|
| Wide table | `components/actions.py:77-86, 170-238` | `_GRID`/`_MIN_WIDTH` + sticky head; add `_GRID_MCP`/`_MIN_WIDTH_MCP`, keep the text `min_width=_MIN_WIDTH` (`tests/test_actions_view.py:910-915` scans for it) |
| Chip strip | `components/actions.py:299-356` | `_chip_button`, `rx.flex(..., wrap="wrap")`; second strip for surface chips + toggle (`aria-pressed`) |
| Non-DB view | `admin_state.py:674-685, 1535-1557`; `components/providers.py` | `skills_*` vars, load block, `fault_panel` |
| Row projection | `admin_formatting.py:443-474`, `admin_models.py:124-151` | every `ActionRow` field a str defaulting to "" (`test_every_action_row_field_is_a_string`) |
| Nav | `components/admin_shell.py:508-543` | boxed `_view_link` with left rule, inside a Python `if` |
| Copy | `admin_copy.py:316-360` | all strings in `admin_copy`; `test_actions_view.py:879-889` scans components for literals |

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `chat_ui/chat_ui/admin_models.py` | UPDATE | `ActionRow` + `row_id, mcp_server, skills, outcome, linked, linked_id` (str, ""); `SkillRow`, `SkillsView` |
| `chat_ui/chat_ui/admin_formatting.py` | UPDATE | `to_action_rows` fills new fields (skills list -> ", ".join or absent; `linked` = `#id` / "unlinked" if surface mcp / absent); `to_skills_view(skills, roles_of, digest)` |
| `chat_ui/chat_ui/admin_copy.py` | UPDATE | surface chips, unlinked toggle, 4 heads + titles, narrowed scope, skills view strings, `VIEW_SKILLS_LABEL`, `READ_LABEL_SKILLS`, skills empty state |
| `chat_ui/chat_ui/admin_state.py` | UPDATE | constants, vars, `read_actions(key, surface="", unlinked=False)`, events, scope var, skills load |
| `chat_ui/chat_ui/components/actions.py` | UPDATE | conditional columns, row anchors, second chip strip |
| `chat_ui/chat_ui/components/skills.py` | CREATE | Skills view (empty state + stacked list) |
| `chat_ui/chat_ui/components/admin_shell.py` | UPDATE | `ROUTE_SKILLS`, `VIEW_SKILLS`, conditional nav link |
| `chat_ui/chat_ui/chat_ui.py` | UPDATE | `admin_skills_page`, conditional `app.add_page` |
| `tests/test_admin_mcp_console.py` | CREATE | new tests, `-m "not db"` friendly |
| `tests/test_admin_shell.py` | UPDATE (census only) | add the new route/view/file entries it enumerates (`:69, 114, 172, 192, 219`); no existing assertion changes; grep first |
| `tests/test_copy.py`, `tests/test_admin_palette.py` | check | register new `admin_copy` constants if the census needs it; no chat-only inks in admin modules |

## Tasks

1. **Models + formatting** (`admin_models.py:124`, `admin_formatting.py:443`): add fields and `to_skills_view` (Skill id/version/description/tools/requires + roles). `duration_ms`/`result_flags` are not columns (story lists none). Validate: `tests/test_actions_view.py -k "action_row or null_columns or field"`.
2. **Copy** (`admin_copy.py`): English constants. Chips "All surfaces" / "/v1" / "Gateway"; toggle "Unlinked gateway calls"; heads "Server", "Skills", "Outcome", "Linked" with titles ("unlinked: no /v1 alias decision was claimed for this call").
3. **State** (`admin_state.py`): `ACTIONS_SURFACES`, vars, `read_actions` kwargs-only-when-set, the two events, tuple stale guard, narrowed `actions_scope` branch, skills vars + load block guarded by `settings.MCP_ENABLED` (in memory, own try/except like `:1535`). Import `authz`, `mcp_config` as modules (in-memory reads); extend the module docstring's read-only note.
4. **Actions component**: `_GRID_MCP` = base + `minmax(6rem,9rem) minmax(7rem,12rem) 7rem 5rem`; `_MIN_WIDTH_MCP` = 73rem + 27rem tracks + 4 gaps (3rem) = 103rem (recompute in the comment). `_column_head`/`_row` append four cells when enabled; row `custom_attrs` gains `"id": "action-" + row.row_id`; linked cell `rx.cond(row.linked_id != "", rx.link(row.linked, href="#action-" + row.linked_id), _cell(row.linked))`. Surface strip under `_filter_strip` only when enabled. Keep `class_name="hx-scroll"` and `overflow_x="auto"`.
5. **Skills component** (`components/skills.py`): imports only `admin_copy`, `theme`, `AdminState`, `fault_panel`, `refreshed_stamp` (the views-do-not-reach rule). Empty state is a sentence (what it lists, where skills come from: the `skills:` section of `MCP_CONFIG_FILE`), as `_empty_actions` (`actions.py:241-269`). Each skill: id + version, description, tools, requires, roles (absent mark when none).
6. **Shell + page**: nav link inside `if settings.MCP_ENABLED`; `chat_ui.py` page and conditional `add_page(route=ROUTE_SKILLS, context={"sitemap": None})`.
7. **Tests** in `tests/test_admin_mcp_console.py`; reuse the `_Console` fake and probe approach of `tests/test_actions_view.py:378-420, 736` (import or copy).
8. Run Validation, then the chat_ui probe.

## End-to-End Tests

- [ ] `MCP_ENABLED=true` (monkeypatched): compiled `actions()` has the 4 heads, surface chips, unlinked toggle and `action-` ids; with false, none of those strings appear.
- [ ] State: surface chip `mcp` -> read kwargs `{"limit":500,"decision":d,"surface":"mcp"}`; unlinked -> `linked=False`, filter "all", no `surface` kwarg; MCP off + either event -> no kwargs change.
- [ ] Skills: fake config with 2 skills -> rows with roles from monkeypatched `authz.roles_holding`; zero skills -> empty state; MCP off -> no nav link, no page.
- [ ] Phone width: compile/source test that the MCP table is inside `.hx-scroll` with `overflow_x="auto"` and `min_width`; the skills view has no fixed `min_width`.

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
# chat_ui touched: probe per the brief (cwd chat_ui/, PYTHONPATH="<repo>/chat_ui;<repo>", env set), or tests/test_chat_ui_startup_guard.py
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider -m "not db" tests/test_admin_mcp_console.py tests/test_actions_view.py tests/test_admin_shell.py tests/test_admin_copy.py tests/test_admin_formatting.py tests/test_admin_models.py tests/test_admin_state.py tests/test_admin_palette.py tests/test_copy.py tests/test_providers_view.py tests/test_chat_ui_startup_guard.py tests/test_caddyfile_routes.py tests/test_untouched_app.py
```
Docker is down locally (`-m "not db"`); CI covers db-marked tests. No `app/` file changes.

## Acceptance Criteria -> Tasks -> Tests

| AC | Task(s) | Test |
|----|---------|------|
| AC1 MCP on: surface filter, 4 columns, unlinked filter | 1-4 | `test_admin_mcp_console.py::test_mcp_on_actions_view_has_filters_and_columns`, `::test_unlinked_toggle_reads_linked_false` |
| AC2 MCP off: no filter, no Skills panel | 4, 6 | `::test_mcp_off_view_is_unchanged` (+ unmodified `test_actions_view.py`, `test_admin_shell.py`) |
| AC3 Skills empty state / list | 3, 5 | `::test_skills_empty_state`, `::test_skills_list_from_config` |
| AC4 phone width, no page overflow | 4, 5 | `::test_mcp_table_scrolls_inside_its_container` |

## Risks

- Hash anchors inside an overflow container and Var concat for `id`/`href` need checking against the installed Reflex early (Task 4); fallback is plain `#id` text.
- `tests/test_admin_shell.py` census may compare exact sets: adding skills entries is a census edit, to flag in the report.
- Default Denied chip plus Gateway surface can look empty; the empty-state title already names the filter.
