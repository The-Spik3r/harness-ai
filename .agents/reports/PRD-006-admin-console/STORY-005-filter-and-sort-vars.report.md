---
story: STORY-005
prd: PRD-006
plan: .agents/plans/PRD-006-admin-console/completed/STORY-005-filter-and-sort-vars.plan.md
epic_branch: epic/PRD-006-admin-console
commit: 631bbff
status: COMPLETE
completed: 2026-08-30
---

# Implementation Report — STORY-005: Client-side filter and sort as computed vars over the loaded rows

**Plan**: `.agents/plans/PRD-006-admin-console/completed/STORY-005-filter-and-sort-vars.plan.md`
**Epic Branch**: `epic/PRD-006-admin-console`
**Commit**: `631bbff`

## Summary

`AdminState` gained four plain filter/sort vars — `selected_verdicts`, `search`, `sort_key`, `sort_descending` — and two computed vars: `visible_rows`, which narrows and orders the 100-row window already in state, and `filters_active`, which STORY-013's clear control and STORY-014's no-matches state both read. The filtering predicate (`_matches` / `filter_rows`) and the sort-rank table (`_SORT_RANKS` / `sort_rows`) are module-level pure functions, so they are testable without a Reflex state; the getter loads all five of its state vars in its own body, which is the only form Reflex's dependency tracker actually sees. Four mutating handlers (`set_search`, `toggle_verdict`, `sort_by`, `clear_filters`) write the plain vars. `admin_formatting.VERDICTS` is imported rather than re-declared, and the verdict sort rank is the negated index into that same tuple, so the natural order runs fault → denied → held → cleared. Nothing under `app/` was touched, and no database function was added or changed.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Import `VERDICTS`; declare `SORT_TIMESTAMP` / `SORT_USER` / `SORT_VERDICT` / `SORT_KEYS` and the `_SORT_RANKS` table | `chat_ui/chat_ui/admin_state.py` | ✅ |
| 2 | Add the pure helpers `_matches`, `filter_rows`, `sort_rows` | `chat_ui/chat_ui/admin_state.py` | ✅ |
| 3 | Declare the four filter vars and the `visible_rows` / `filters_active` computed vars | `chat_ui/chat_ui/admin_state.py` | ✅ |
| 4 | Prove the auto-dependency set contains all five names | — (verification) | ✅ |
| 5 | Add `set_search`, `toggle_verdict`, `sort_by`, `clear_filters` | `chat_ui/chat_ui/admin_state.py` | ✅ |
| 6 | Drive the state directly and assert every AC | `<scratchpad>/drive_visible_rows.py` | ✅ 11/11 |
| 7 | Confirm nothing else moved | — (verification) | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| `import app.main` | ✅ |
| `import chat_ui.chat_ui.admin_state` | ✅ |
| Frontend lint | N/A — `chat_ui` is Reflex/Python, no JS package |
| Tests | ✅ 349 passed (was 324; +25 new) |
| `tests/test_admin_state.py` alone | ✅ 52 passed |
| Scratchpad AC drive | ✅ 11/11 assertions |
| E2E | ✅ 8/8 against a seeded 120-row SQLite database |
| Sort table well-formed (`set(_SORT_RANKS) == set(SORT_KEYS)`) | ✅ |
| No `cache=False`, no `async def visible_rows` | ✅ no matches |
| No re-declared verdict literal in `admin_state.py` | ✅ no matches |
| `insert_audit_log` still unreachable | ✅ 0 matches |
| Dependency tracking | ✅ `['rows', 'search', 'selected_verdicts', 'sort_descending', 'sort_key']` |

### E2E detail (seeded database, real `load()` read path)

Ran against 120 seeded rows in a scratchpad SQLite database, through the real `AdminState.load()` and the real `app/db/database.py` functions.

| # | Check | Result |
|---|-------|--------|
| 1 | `load()` → 100 rows of 120; `visible_rows == rows`, newest first | ✅ |
| 2 | Searching a known `audit_id` isolates that row | ✅ narrowed 100 → `[80]` |
| 3 | `denied` AND `a.torres` composes as intersection | ✅ denied=5, a.torres=25, AND=1 |
| 4 | Empty verdict selection shows all 100, not zero | ✅ |
| 5 | Verdict sort leads with exceptions; repeat click reverses | ✅ leads `fault, fault, fault`; reversed leads `cleared` |
| 6 | Evaluation over 100 rows under a 3-char search is sub-millisecond | ✅ 0.4466 ms |
| 7 | Filtered evaluation with all ten reads raising | ✅ no read attempted |
| 7b | Neither preview survives the projection on the filtered path (Risk 2) | ✅ |
| 8 | `sign_out()` clears filters, sort and rows | ✅ |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `chat_ui/chat_ui/admin_state.py` | UPDATE | +222/−1 |
| `tests/test_admin_state.py` | UPDATE | +385/−1 |
| `.agents/plans/PRD-006-admin-console/completed/STORY-005-filter-and-sort-vars.plan.md` | CREATE | +568 |

No file under `app/` was modified.

## Deviations from Plan

**1. Tests were written in this story rather than deferred to STORY-006.** The plan's Metadata said "no test file (that is STORY-006)". `implement.md` Phase 4 makes tests a hard gate — *"You MUST write tests for new code… Every new function needs ≥1 test"* — and this story adds three module-level functions, two computed vars and four handlers. The deferral was also inconsistent with this branch's own practice: STORY-004's story commit (`e8c331e`) carried 347 lines of `tests/test_admin_state.py`. 25 tests were therefore added to the existing file under a STORY-005 heading, and the file's module docstring now records the three invisible properties this story introduces. STORY-006 is not obsoleted — it still owns the four verdicts against constructed `AuditLog`s and the no-leak assertions — but it should extend this block rather than duplicate it. The `tests/test_admin_state.py` docstring was updated to say so.

**2. Task 6 assertion 8 could not test object identity through state, and was rewritten.** The plan asked that `state.rows` be "unchanged in both order and identity" after a sort. Identity is not observable through a Reflex state var: `rows` is a `MutableProxy`, and it re-wraps every element on each attribute read, so two *consecutive* reads of `state.rows` with no operation between them already yield different `id()`s. The assertion was split — order and value are asserted on the state (`test_visible_rows_does_not_reorder_or_alter_the_loaded_rows`), and the no-mutation guarantee is asserted on the pure functions, where identity survives (`test_the_pure_helpers_return_new_lists`). The underlying property the plan wanted is fully covered; only the mechanism changed.

**3. The plan's `git diff main --stat -- app/` check does not return empty on this branch.** Two files under `app/` (`app/db/database.py`, `app/db/models.py`) differ from `main`, but they come from commit `3f553f2`, which entered this branch through the PRD-004 epic merge at its base and predates every PRD-006 story commit. The check was inherited verbatim from STORY-004's plan and is scoped too widely to mean what it says. The property that actually holds, and was verified, is that **this story's own diff contains no file under `app/`** (`git diff --name-only` listed only `chat_ui/chat_ui/admin_state.py`). STORY-020 ("the proof that nothing under `app/` changed") should use `git diff 60835dc..HEAD -- app/` or an equivalent PRD-006-scoped range rather than `main`.

**4. `_SORT_RANKS`' comment references `admin_formatting.py` without a line range.** The plan's draft cited `admin_formatting.py:167-176` for `_format_timestamps`; the line numbers were dropped from the comment because they drift. The module and function are still named.

Everything else was implemented as specified, including the four handlers whose placement in this story (rather than STORY-013) the plan flagged as a deliberate scope call.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_admin_state.py` (+25) | `test_the_filter_and_sort_state_is_four_plain_vars`; `test_visible_rows_is_a_computed_var_over_the_rows_and_the_filter_state`; `test_visible_rows_tracks_all_five_of_its_dependencies`; `test_evaluating_visible_rows_performs_no_database_read`; `test_an_empty_verdict_selection_passes_every_row`; `test_free_text_matches_user_model_and_id_case_insensitively` (×7 params); `test_the_two_filters_compose_as_and`; `test_the_default_order_is_the_order_list_audit_logs_returned`; `test_each_sort_key_changes_the_ordering`; `test_sort_descending_reverses_the_chosen_order`; `test_an_unrecognised_sort_key_or_verdict_degrades_instead_of_raising`; `test_visible_rows_does_not_reorder_or_alter_the_loaded_rows`; `test_the_pure_helpers_return_new_lists`; `test_filters_active_reports_the_filters_and_ignores_the_sort`; `test_toggle_verdict_adds_removes_and_reassigns`; `test_sort_by_selects_a_key_then_flips_direction_on_repeat`; `test_clear_filters_restores_the_window_without_touching_sort_or_rows`; `test_sign_out_clears_the_filter_and_sort_state_too`; `test_the_verdict_vocabulary_is_imported_not_redeclared` |

The three that would fail silently without a test, and are the reason this block exists:

- `test_evaluating_visible_rows_performs_no_database_read` — replaces all ten reads *and* `_READS` with raising stubs, then evaluates the var across 120 filter/sort combinations. A var that grew an `await` would still look correct in review.
- `test_an_empty_verdict_selection_passes_every_row` — `row.verdict not in []` is `True` for every row, so dropping the `if verdicts and` guard empties the register on page load and renders as "nothing recorded".
- `test_visible_rows_tracks_all_five_of_its_dependencies` — Reflex's tracker fails by warning and returning *no* dependencies, yielding a filter that computes once and never updates.

## Skills

`reflex-docs` and `reflex-process-management` remain **not installed** (`~/.claude/plugins` absent; `.agents/skills/` holds only `frontend-design`) — the same gap STORY-001…004 recorded. Per `chat_ui/AGENTS.md`'s *"rather than relying on memory"* rule, the Reflex APIs were verified against the **installed** `reflex==0.9.6.post1` source (`reflex_base/vars/base.py` — `computed_var`'s signature and `cache=True` / `auto_deps=True` defaults, `ComputedVar._deps`' catch-and-warn failure mode) and against current Reflex documentation via context7 `/websites/reflex_dev` (`docs/vars/computed-vars`). `frontend-design` was read and found not binding: this story emits no user-facing string and no component.

## Acceptance Criteria

- [x] Given `AdminState`, when the filter state is inspected, then it holds a verdict multi-select (`selected_verdicts`), a free-text `search` and a `sort_key` / `sort_descending` pair — all plain state vars.
- [x] Given `visible_rows`, when it is defined, then it is a computed var over `rows` plus the filter and sort state, and evaluating it performs **no** database read.
- [x] Given a free-text value, when it is applied, then it matches case-insensitively against `user_id`, `model_used` and `audit_id`, and typing `127` isolates the row whose `audit_id` is 127.
- [x] Given a verdict multi-select with `denied` selected and the text `a.torres`, when both are applied, then the two filters compose as AND and the row count narrows accordingly.
- [x] Given `sort_key` set to timestamp, user, or verdict, when the register reads `visible_rows`, then the ordering changes and the default is timestamp, newest first — the order `list_audit_logs` returned.
- [x] Given an empty verdict selection, when `visible_rows` is evaluated, then all rows pass the verdict filter.
- [x] Given the filter and sort state, when `sign_out()` runs, then they are reset along with the rows.
- [x] All tasks completed
- [x] Frontend lint passes (N/A — no JS package in `chat_ui`)
- [x] Backend server starts without error
- [x] Follows existing patterns
