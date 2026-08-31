---
story: STORY-017
prd: PRD-006
plan: .agents/plans/PRD-006-admin-console/completed/STORY-017-refresh-and-fault-panel.plan.md
epic_branch: epic/PRD-006-admin-console
commit: PENDING
status: COMPLETE
completed: 2026-08-31
---

# Implementation Report — STORY-017: Manual refresh with a last-refreshed stamp, and a fault panel with retry on both pages

**Plan**: `.agents/plans/PRD-006-admin-console/completed/STORY-017-refresh-and-fault-panel.plan.md`
**Epic Branch**: `epic/PRD-006-admin-console`
**Commit**: `PENDING`

## Summary

The console now refreshes on purpose and says so, and a read that raises is
named on screen instead of being swallowed into an empty table.

Three components in `admin_shell.py`: `refresh_control()` — one button, one
handler, locked while `AdminState.loading` and reading *Refreshing* beside a
pulsing glyph; `refreshed_stamp()` — the *Refreshed 2026-08-31 19:37:54 UTC*
line; and `fault_panel()` — the title, the sentence `AdminState.error` already
carries, and that same control as its retry. One state addition,
`AdminState.refreshed_stamp`, because `REFRESHED_TEMPLATE` is a Python format
string and components receive Vars.

Nothing else was needed, and that is the story: STORY-004 already commits its
reads in one block (so a failed read leaves the record standing), clears
`loading` in a `finally` on both paths, and clears `error` on success; STORY-008
already declared all six strings and the ten read labels; STORY-014 and
STORY-015 already render their data in the fault arm, waiting for this panel to
hang above it. This story is the surface and the wiring.

The panel lives in `admin_page()`, so each page carries its own instance from one
call site. The stamp lives where PRD-006 Section 6.1's wireframe draws it — at
the foot of the register's scope column, the slot `_filter_strip` had reserved by
name, and under the summary's scope note. Motion is the chat's existing
`.hx-pulse` class, whose `prefers-reduced-motion` opt-out was already written: no
new CSS, no new keyframe, no interval anywhere.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | `AdminState.refreshed_stamp`, computed so a sign-out clears it | `chat_ui/chat_ui/admin_state.py` | ✅ |
| 2 | `refresh_control()`, `refreshed_stamp()`, `fault_panel()`; control into the masthead, panel into `admin_page()` | `chat_ui/chat_ui/components/admin_shell.py` | ✅ |
| 3 | The stamp at the foot of the register's scope column | `chat_ui/chat_ui/components/register.py` | ✅ |
| 4 | The stamp under the summary's scope note | `chat_ui/chat_ui/components/summary.py` | ✅ |
| 5 | State tests: the stamp, the sign-out, the fault that does not advance it, the retry that does | `tests/test_admin_state.py` | ✅ |
| 6 | Shell tests: bindings, lock, indicator, panel on both pages, no second animation, no auto-refresh | `tests/test_admin_shell.py` | ✅ |
| 7 | The stamp reaches each surface | `tests/test_register.py`, `tests/test_summary.py` | ✅ |
| 8 | Contrast — confirmed, no new pairing | `tests/test_contrast.py` | ✅ (no change needed) |
| 9 | Compile, run, force the fault, self-critique | — | ✅ (one accessory cut, below) |

## Validation Results

| Check | Result |
|-------|--------|
| `reflex compile` | ✅ compiled, no error |
| Prod server, both console views | ✅ render authenticated, fault path exercised on each |
| `tests/test_admin_shell.py` | ✅ 85 passed (59 before, +26) |
| `tests/test_admin_state.py` | ✅ 101 passed (96 before, +5) |
| `tests/test_register.py` | ✅ 175 passed (174 before, +1) |
| `tests/test_summary.py` | ✅ 61 passed (60 before, +1) |
| `tests/test_contrast.py` | ✅ 23 passed, unmodified |
| Full suite | ✅ 749 passed |
| PRD-001/003/004 test files | ✅ unmodified and passing |
| `git diff main -- app/` from this story | ✅ nothing added (pre-existing drift noted below) |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `chat_ui/chat_ui/components/admin_shell.py` | UPDATE | +180/-1 |
| `chat_ui/chat_ui/admin_state.py` | UPDATE | +39 |
| `chat_ui/chat_ui/components/register.py` | UPDATE | +7/-3 |
| `chat_ui/chat_ui/components/summary.py` | UPDATE | +8 |
| `tests/test_admin_shell.py` | UPDATE | +217 |
| `tests/test_admin_state.py` | UPDATE | +119 |
| `tests/test_register.py` | UPDATE | +17 |
| `tests/test_summary.py` | UPDATE | +14 |

`chat_ui/chat_ui/admin_copy.py`, `chat_ui/chat_ui/theme.py` and
`tests/test_contrast.py` are unchanged, as the plan expected: every string and
every token this story needed already existed.

## Deviations from Plan

**1. The fault panel's mark was cut in the Task 9 critique.** The plan specified a
solid `INK_FAULT` square in the register's stamp shape at the head of the panel,
and pre-registered it as the thing to cut if the critique disagreed (plan Risk
10). It disagreed. PRD-006 Section 6.1 spends the console's boldness on the stamp
margin, where a mark means *this row is an exception* and a hundred rows resolve
into a stripe of them; the same shape on something that is not a row spends that
vocabulary where it states nothing the words do not already state. The panel is
now title, sentence, retry and a hairline — no colour at all. Live, the stamp
margin's marks are the only marks on the page, which is what the signature is
for. `test_the_panel_paints_no_verdict_ink` pins the decision so it cannot drift
back.

**2. The panel renders from `admin_page()`, not from inside `register()`.** Called
out in the plan (Risk 3) as a deliberate departure from STORY-014's seam note. One
call site, an independent instance per page, and the fault is met before the
filter controls. Neither view's `rx.match` arms changed, which is what that note
was protecting.

**3. The refresh control's *line* is not in the masthead.** `test_admin_shell.py`
asserts the control on both pages; the stamp is asserted in `test_register.py` and
`test_summary.py` instead, because Section 6.1's wireframe puts it beside the
window it stamps rather than in the header. One draft assertion that expected the
stamp inside `admin_page()` was corrected to match the wireframe, not the reverse.

**4. `prefers-reduced-motion` was verified by rule, not by OS emulation.** The
chrome-devtools tooling here exposes no reduced-motion knob. What was checked
live: the `@media (prefers-reduced-motion: reduce)` block is present in the served
document and names `.hx-pulse` with `animation: none`, and the pulse is the only
animated element on the page. The unit tests
(`test_reduced_motion_covers_the_indicator`,
`test_the_indicator_is_the_only_moving_element`,
`test_no_admin_module_declares_its_own_animation`) carry the rest.

**5. `chat_ui/reflex.lock/` was reverted.** Running the production build bumped
`lucide-react` and reformatted the lockfile. That is a side effect of running the
app, not of this story, so it was restored rather than committed.

## Note: `app/` still differs from `main` on this branch

Unchanged from STORY-015's finding and repeated so it is not lost:
`git diff main --stat -- app/` is not empty — `app/db/database.py` and
`app/db/models.py` differ, both from commit `3f553f2` (a PRD-004-era PII column
migration), not from any PRD-006 story. This story adds nothing under `app/`.
STORY-020 has to decide whether its bar reads as "nothing under `app/` changed
*by PRD-006*" or whether `3f553f2` needs separating out.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_admin_state.py` | `test_the_stamp_states_that_nothing_has_been_read_yet`, `test_the_stamp_carries_the_time_of_the_read`, `test_the_stamp_is_computed_so_a_sign_out_clears_it`, `test_a_failed_read_does_not_advance_the_stamp`, `test_the_retry_clears_the_fault_and_advances_the_stamp` |
| `tests/test_admin_shell.py` | `test_the_refresh_control_reaches_both_pages`, `test_the_control_and_the_line_share_one_verb`, `test_the_stamp_binds_the_state_var_and_not_a_formatted_string`, `test_the_control_locks_for_the_duration_of_a_read`, `test_the_control_shows_an_indicator_while_the_read_is_out`, `test_the_panel_names_the_read_and_offers_the_retry`, `test_the_retry_is_the_refresh_control_itself`, `test_each_page_renders_its_own_panel`, `test_the_panel_does_not_apologise`, `test_the_panel_paints_no_verdict_ink`, `test_the_indicator_is_the_only_moving_element`, `test_no_admin_module_declares_its_own_animation` (×6 modules), `test_reduced_motion_covers_the_indicator`, `test_no_admin_module_refreshes_itself` (×6 modules) |
| `tests/test_register.py` | `test_the_refreshed_stamp_sits_at_the_foot_of_the_scope_column` |
| `tests/test_summary.py` | `test_the_refreshed_stamp_sits_under_the_scope_note` |

## End-to-End Verification (live, prod server on :3000)

The fault was forced by holding a `BEGIN EXCLUSIVE` lock on `harness_ai.db` from a
second process — a real `sqlite3.OperationalError` raised inside
`asyncio.to_thread`, not a stubbed one, and one that also gave a multi-second
in-flight window to observe the lock in.

| # | Check | Result |
|---|-------|--------|
| 1 | `reflex compile` | ✅ no error |
| 2 | `/admin/audit`: **Refresh** in the masthead, **Refreshed … UTC** at the foot of the scope column | ✅ |
| 3 | `/admin/stats`: same control, line under the scope note | ✅ |
| 4 | Refresh in flight: `disabled: true`, label *Refreshing*, exactly one `.hx-pulse` element, rows standing, stamp not yet moved | ✅ |
| 5 | Forced fault on the register: panel names *the audit rows*, all six rows still on screen, stamp unchanged | ✅ |
| 6 | Forced fault on the summary from its own control: its own panel, nine figures standing | ✅ |
| 7 | Retry after the lock released: panel cleared, stamp advanced 19:32:31 → 19:33:57 | ✅ |
| 8 | Panel copy: names the read, states nothing moved, gives the action; no apology | ✅ |
| 9 | `prefers-reduced-motion` rule present in the served document, covering `.hx-pulse` | ✅ (by rule — see Deviation 4) |
| 10 | Idle with both pages open: stamp never advanced, no periodic event | ✅ |
| 11 | Keyboard: both Refresh controls `tabIndex 0` and focusable; no local focus reset in the shell | ✅ |
| 12 | 640px viewport: masthead wraps, panel sentence wraps inside the measure, `scrollWidth == innerWidth` (no horizontal overflow) | ✅ |
| 13 | `grep '"' admin_shell.py`: no user-facing literal added — only tokens, layout values and docstring prose | ✅ |

## Acceptance Criteria

- [x] Either admin page carries a **Refresh** control and a **Refreshed {time}** stamp — one verb across both
- [x] A refresh in flight locks the control and shows a loading indicator
- [x] A read that raises renders a fault panel naming the read, with the rows and figures left untouched
- [x] The panel's retry clears the panel, updates the data and advances the stamp
- [x] The panel names what happened without apologising and without vagueness
- [x] The indicator does not animate under `prefers-reduced-motion: reduce`, and is the console's sole moving element
- [x] Both pages render the panel independently
- [x] The console never auto-refreshes, polls or pushes
- [x] All tasks completed
- [x] `python -m pytest -q` passes (749), with `app/` and its suites unmodified
- [x] The app compiles and both console views render without error
- [x] Follows existing patterns
