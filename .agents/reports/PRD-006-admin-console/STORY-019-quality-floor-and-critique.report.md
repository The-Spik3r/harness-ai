---
story: STORY-019
prd: PRD-006
plan: .agents/plans/PRD-006-admin-console/completed/STORY-019-quality-floor-and-critique.plan.md
epic_branch: epic/PRD-006-admin-console
commit: 7cd66b4
status: COMPLETE
completed: 2026-08-31
---

# Implementation Report — STORY-019: Quality floor pass: keyboard, focus, narrow viewport — and a design self-critique

**Plan**: `.agents/plans/PRD-006-admin-console/completed/STORY-019-quality-floor-and-critique.plan.md`
**Epic Branch**: `epic/PRD-006-admin-console`
**Commit**: `7cd66b4`

## Summary

A measured pass over the finished console rather than new capability. 118 rows
were seeded across all four verdicts into the console's database, the production
server was run per the **reflex-process-management** skill, and each quality-floor
property was read out of the live document instead of inferred from the source: a
full `Tab` traversal recorded through a `focusin` listener, computed outlines at
every stop, `documentElement.scrollWidth` against `innerWidth` at three widths on
three surfaces, `document.getAnimations()` under a genuinely emulated
`prefers-reduced-motion: reduce`, and per-row `getBoundingClientRect()` offsets
down all one hundred rows.

**Every floor property already held.** No fix was required in Tasks 3–8 — not one
line of `register.py`, `summary.py` or `theme.py` changed, and `theme.py` was not
touched at all. That is the honest result of the pass, and it is what the earlier
stories' construction rules (native `<button>`s everywhere, one shared `_GRID`,
`wrap="wrap"` instead of breakpoints, a single global `:focus-visible`) were for.

The one change to a component is the **cut** PRD Section 12 Phase 4 requires: the
masthead's view word. Everything the pass measured is now pinned by tests, so a
floor met today cannot be lost silently tomorrow.

## The self-critique (AC 5)

Re-read of PRD Section 6.1 against the rendered screenshots at 1440px (full page,
all 100 rows) and 390px. The shortlist, with the case each way:

| # | Candidate | Verdict |
|---|-----------|---------|
| 1 | **The masthead's view word** — `HARNESS · REGISTER` while the two-view switch beside it already marks the active view as bold text with `aria-current="page"` | **CUT** |
| 2 | The sort cluster's third control — three sort keys where the register's one job is *find the exceptions* | Kept. PRD Section 4 lists all three explicitly; removing one is a scope change, not a cut. |
| 3 | The row hover ground (`theme.HOVER`) — a second row-level signal beside the stamp margin | Kept. It is a shared token with a reasoned defence in `theme.py`, and removing it would breach AC 7. |
| 4 | `_figure_note` under the counts block — possible double duty with the completion label | Kept. Measured on screen: the label states *what* is counted, the note states *why it is not an answer rate*. Two elements, two jobs. STORY-016 pins the label deliberately. |
| 5 | A second signal carrying the summary's subset relationship alongside the indent | Nothing to cut — Task 8 measured the blocked figures as identical to the total in every channel but `left`. |

**The cut, and why it is the right one.** The console named the current view
**twice in one header row**: once in the wordmark (`HARNESS · REGISTER`) and once
in the switch two clusters to the right, which renders the active destination as
plain bold text carrying `aria-current="page"`. That is the frontend-design
skill's *"let each element do exactly one job … nothing quietly does double
duty"*, and it is an accessory by that skill's own test — removing it loses no
information the screen does not already carry. It reads worst at a narrow
viewport, where the masthead wraps and the two namings land on consecutive lines
a few pixels apart (see the 390px screenshot evidence below).

Cutting the suffix also settles *which* element owns the fact: the switch does,
because it is the one that can be acted on. The wordmark now reads `HARNESS` on
both views and on the gate — one word, one job, stated once. Live after the cut:
`document.body.innerText.match(/REGISTER/g)` → **0 occurrences**, with
`aria-current="page"` still on `Register`.

Only one thing was cut. The skill asks for one accessory, not a demonstration of
thoroughness.

**What was deliberately not removed.** `admin_copy.CONSOLE_VIEW_REGISTER`,
`CONSOLE_VIEW_SUMMARY` and `MASTHEAD_SEPARATOR` remain declared and unrendered.
PRD-006 Section 15 lists `tests/test_copy.py` among the files that must pass
**unmodified**, and that file asserts each of them non-empty by name; deleting
them would force an edit to a file this PRD promises not to touch, to remove three
strings that cost nothing where they sit. `admin_copy.py` is therefore unchanged
by this story. `tests/test_admin_shell.py`'s `COPY_NAMES` tuple — the list of
strings the shell *renders* — did drop them, with a comment recording why.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Seed 118 rows across four verdicts, database backed up first | scratchpad (not committed) | ✅ |
| 2 | `reflex compile --dry`, then prod server; port read from `reflex.log` | — | ✅ |
| 3 | Full keyboard traversal: gate, register, summary, fault panel | — | ✅ no fix needed |
| 4 | Focus visibility measured at every stop | — | ✅ no fix needed |
| 5 | Narrow viewport, 3 widths × 3 surfaces + 4 register states | — | ✅ no fix needed |
| 6 | Reduced motion, emulated, with a matched negative control | — | ✅ no fix needed |
| 7 | 100 rows: stripe judged from screenshots, alignment measured | — | ✅ no fix needed |
| 8 | Summary: no card/fill/accent, indentation alone | — | ✅ no fix needed |
| 9 | Chat untouched; nothing shared altered | — | ✅ |
| 10 | **The self-critique and the cut** | `chat_ui/chat_ui/components/admin_shell.py` | ✅ |
| 11 | Pin the floor and the cut with tests | `tests/test_admin_shell.py`, `test_register.py`, `test_summary.py` | ✅ |
| 12 | Stop the server, restore database, lockfile and log | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| `reflex compile --dry` | ✅ clean |
| Tests | ✅ 848 passed |
| E2E | ✅ 18/18 |
| `git diff --stat -- app/` | ✅ empty |
| Chat modules changed | ✅ none |
| `theme.py` changed | ✅ not at all |
| Must-pass-unmodified suites | ✅ all 8 untouched |

## End-to-End Verification (live, prod server on :3000)

The port was read from `reflex.log`'s `App running at:` line rather than assumed.
The fault path was forced the way STORY-017 forced it — a `BEGIN EXCLUSIVE` lock
held on `harness_ai.db` from a second process, producing a real
`sqlite3.OperationalError` inside `asyncio.to_thread` and a multi-second in-flight
window to observe.

| # | Check | Measured result |
|---|-------|-----------------|
| 1 | Compile, server up, port from the log | ✅ `:3000` |
| 2 | Gate: Tab reaches field then submit; Enter submits; wrong token refused generically and field cleared | ✅ *"Access refused. That token was not accepted."*, `value=""` |
| 3 | Register walk | ✅ Summary → Refresh → Sign out → cleared/HELD/DENIED/FAULT → Find → Time↓/User/Verdict → row toggles, each once, in document order |
| 4 | `Clear filters` enters the order only when a filter is active | ✅ absent unfiltered; present at position 12 with DENIED selected (100 → 4 rows, *"4 of 100 shown"*) |
| 5 | The active view is not a focus stop | ✅ rendered as text with `aria-current="page"` |
| 6 | Summary walk | ✅ exactly three stops: Register, Refresh, Sign out |
| 7 | Fault panel open: retry reachable between masthead and content | ✅ tab index 3 of the order; it is the Refresh control itself |
| 8 | Focus ring on every stop | ✅ `2px solid rgb(52, 86, 127)` on all 15 stops, including both Radix fields |
| 9 | Enter and Space both toggle a row disclosure | ✅ `aria-expanded` false→true→false, label flips Show/Hide, focus stays on the toggle, no scroll jump |
| 10 | Shift+Tab reverses without a trap | ✅ toggle → Clear filters → Verdict |
| 11 | 360 / 390 / 640px × gate / register / summary | ✅ 9/9 with `documentElement.scrollWidth == innerWidth` |
| 12 | 360px register: container scrolls sideways, page does not | ✅ container `scrollWidth` 1066 vs `clientWidth` 350; `scrollLeft` 500 set and held |
| 13 | 360px register in its other states | ✅ no-matches and fault-panel-open both hold; empty-register state covered by construction (see Deviations) |
| 14 | `prefers-reduced-motion: reduce`, read in flight | ✅ `getAnimations().length === 0`, `.hx-pulse` present with `animation-name: none`, zero elements with animation or transition > 0.001s |
| 15 | Negative control, same harness, same in-flight condition | ✅ 1 animation running (`hx-pulse`), exactly one moving element |
| 16 | 100 rows: the stamp margin reads as a scannable stripe | ✅ judged from the full-page capture — see below |
| 17 | Column alignment down the full window | ✅ `tokens_used` and `audit_id` spread **0.000px** across all 100 rows; unchanged at the bottom of the scroll and under all three sorts |
| 18 | Summary: colours, fills, indentation | ✅ see below |
| 19 | Both pages at 100 rows: no preview sentinel in `outerHTML` | ✅ neither |
| 20 | Retry after the lock released | ✅ panel cleared, stamp advanced 20:22:11 → 20:29:40, 100 rows restored |
| 21 | Chat at `/` after the cut | ✅ gate, masthead, model selector, legend and composer all unchanged |

### The stripe (AC 4)

Judged from a full-page capture of all 100 rows at 1440px, per the skill's *"a
picture is worth 1000 tokens"*. With 11 non-cleared rows scattered unevenly
through 100, the exceptions are findable by scanning the left edge alone without
reading the table — the fault mark at `#118`, denied at `#115`, held at `#98`,
denied at `#81`, fault at `#69`, held at `#66` and `#65`, denied at `#38`, and the
cluster around `#1`–`#6`. The margin does the job PRD Section 6.1 gives it. No
change to `theme.GLYPH` or `theme.STAMP_X` was needed — which matters, because both
are shared with the chat's rail and changing either would have been an AC 7 problem.

### The summary as a tally sheet (AC 6)

Swept over every element on the rendered page:

- **Backgrounds**: only `PAPER` (`#ECEFF1`) and `CARD` (`#FFFFFF`, the masthead, not the sheet). No fill on any figure.
- **Box shadows**: none. **Border radii**: none. No card, anywhere.
- **Borders**: only `RULE` (`#CBD2D9`) and `RULE_SOFT` (`#DDE2E7`) hairlines.
- **Text**: every element that paints visible text uses exactly two colours — `INK` (`#14181C`) and `MUTE` (`#626C77`). **No verdict ink and no accent appears on the summary at all.**
- **Indentation alone**: the blocked labels sit at `x=54` against the total's `x=24` — a 30px step, which is `theme.STAMP_X` — and match the total in *every* other channel: same family (Archivo), size (12px), weight (600), colour, letter-spacing and text-transform.

One computed value, `rgb(237, 238, 240)`, appears on container `<div>`s: it is
Radix's own root inherit on elements that own no text and is never painted. Noted
rather than treated as a finding — the check that matters is the one over elements
that actually paint text, and that set is `{INK, MUTE}`.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `chat_ui/chat_ui/components/admin_shell.py` | UPDATE | +22/-7 |
| `tests/test_admin_shell.py` | UPDATE | +122/-16 |
| `tests/test_register.py` | UPDATE | +79/-1 |
| `tests/test_summary.py` | UPDATE | +45/-0 |

Files the plan listed as conditional that were **not** changed, because nothing
failed: `register.py`, `summary.py`, `theme.py`, `admin_copy.py`,
`test_render_invariants.py`.

## Deviations from Plan

1. **No fixes were needed in Tasks 3–8.** The plan was written to fix whatever the
   live pass found, and it found nothing to fix. The floor was already met by
   construction. The only component change is Task 10's cut.

2. **`theme.py` was not touched.** The plan reserved a new token or an
   admin-scoped `GLOBAL_CSS` rule for a focus or viewport fix; neither was needed,
   so the `git diff -U0 theme.py | grep '^-'` check passes trivially.

3. **Reduced motion required a second browser.** The chrome-devtools MCP browser
   is attached over `--remote-debugging-pipe` (no TCP port for a second client),
   and its `emulate` tool has no reduced-motion switch. The check was therefore run
   by launching a separate headless Chrome with `--force-prefers-reduced-motion`
   and a debugging port, driven over raw CDP, with `matchMedia('(prefers-reduced-motion: reduce)')`
   asserted true inside the page. This **closes STORY-017's Deviation 4**, which
   could only verify the rule was served; AC 3 is now met by observation, with a
   matched negative control on the same harness.

4. **`resize_page` cannot reach 360px** — Chrome enforces a ~500px minimum window
   width. Viewport emulation (device metrics override) was used instead, which
   reports a true `innerWidth` of 360.

5. **The empty-register state was not exercised live at 360px.** It requires a
   database with no rows at all, which the seeded console cannot produce without a
   restart against an empty file. It renders through the *same* `_empty_panel`
   component as the no-matches state, which was exercised at 360px and holds. Noted
   rather than claimed.

6. **Stopping the server needed more than the skill's step.** The skill's
   `lsof -sTCP:LISTEN` has no Windows equivalent that behaves identically:
   `netstat` attributed port 3000 to a **dead** PID while the port stayed bound,
   because an orphaned `multiprocessing` spawn child of the first server run was
   still holding it. The parent was found by command line
   (`reflex run --env prod --single-port`) and stopped with `taskkill /F /T`, then
   the orphan was identified as a `python.exe` whose `ParentProcessId` no longer
   existed and stopped by PID. Confirmed free by binding the port. Nothing was
   killed by image name.

7. **The seed script needed a re-run guard.** Its verdict tally crashed the first
   time (`list_audit_logs` returns `AuditLog` objects, not rows), after the inserts
   had already landed; a blind second run would have doubled the window. It grew a
   `--tally-only` flag. Throwaway file, not committed.

8. **Task 9 was run after Task 10 rather than before.** The plan orders the
   untouched-chat verification before the cut, but its own text says "after every
   fix has landed" — and the cut was the only change, so verifying before it would
   have proved nothing about the shipped state.

## Note: `app/` still differs from `main` on this branch

Unchanged from STORY-015/017/018 and repeated so it is not lost:
`git diff main --stat -- app/` is not empty — `app/db/database.py` and
`app/db/models.py` differ, both from commit `3f553f2` (a PRD-004-era PII column
migration), not from any PRD-006 story. **This story adds nothing under `app/`**
(`git diff --stat -- app/` is empty). STORY-020 still owns deciding whether its
bar reads as "nothing under `app/` changed *by PRD-006*".

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_admin_shell.py` | `test_the_masthead_is_the_wordmark_and_nothing_else` (replaces `test_masthead_names_its_own_view`), `test_the_switch_still_owns_the_current_view`, `test_the_focus_ring_is_declared_for_every_focusable_element`, `test_no_admin_module_takes_the_focus_ring_back` (×6 modules), `test_no_admin_module_pins_a_width_the_viewport_cannot_meet` (×6 modules) |
| `tests/test_register.py` | `test_the_table_scrolls_sideways_in_its_own_container`, `test_the_grid_is_one_constant_shared_by_the_head_and_the_rows`, `test_every_control_is_a_native_focusable_element` |
| `tests/test_summary.py` | `test_a_blocked_figure_differs_from_the_total_by_its_indent_alone`, `test_the_indent_is_a_padding_and_not_a_second_element` |

Each new guard was **watched failing** before being trusted, per
`tests/test_admin_palette.py`'s rule that "a guard nobody has watched fail is a
guard nobody knows is armed":

- `test_the_masthead_is_the_wordmark_and_nothing_else` — restored the pre-cut masthead → *"the cut view word is back"*.
- `test_the_table_scrolls_sideways_in_its_own_container` — removed `overflow_x="auto"` → failed.
- `test_the_grid_is_one_constant_shared_by_the_head_and_the_rows` — gave the column head a hand-copied track list → failed.

`test_every_control_is_a_native_focusable_element` walks the module's AST rather
than counting strings: a first version counted `rx.el.button(` against `on_click=`
and mis-fired, because `_control_button` and `_toggle_button` are factories
serving five call sites from two definitions.

## Acceptance Criteria

- [x] **AC 1** — Every control reachable in a sensible order with visible focus. Full keyboard walk of gate, switch, filters, sort controls, row disclosures, refresh and sign out; 15 stops, each measured at `2px solid rgb(52, 86, 127)`; Shift+Tab reverses; Enter and Space both work on a disclosure; the active view is correctly not a stop.
- [x] **AC 2** — Layout holds at a narrow viewport with no horizontal page scroll, and the table scrolls in its own container. 9/9 measurements at 360/390/640px; container `scrollWidth` 1066 vs `clientWidth` 350 at 360px, demonstrably scrollable.
- [x] **AC 3** — Nothing animates under `prefers-reduced-motion: reduce`, including the loading indicator. Observed with the media feature genuinely emulated and a read in flight: `getAnimations().length === 0`; negative control shows 1.
- [x] **AC 4** — At a hundred rows the stamp margin reads as a scannable stripe and the numeric columns align down the full window. Stripe judged from a full-page screenshot; alignment measured at 0.000px spread across all 100 rows, at both ends of the scroll and in all three sorts.
- [x] **AC 5** — A self-critique against Section 6.1 identified and cut at least one accessory, recorded in this report. Five candidates weighed; the masthead's view word cut; live-verified at 0 occurrences.
- [x] **AC 6** — The summary carries no card, no fill and no accent colour, and the blocked figures read as a subset by indentation alone. Measured: two backgrounds (page + masthead), zero shadows, zero radii, two text colours, 30px indent as the only difference.
- [x] **AC 7** — The chat is unchanged; no shared component or token was altered. `theme.py` untouched; no chat module in the diff; nothing under `app/`; all eight must-pass-unmodified suites untouched; chat verified live after the cut.
- [x] All tasks completed
- [x] `python -m pytest -q` passes (848), with PRD-001/003/004 suites unmodified
- [x] `reflex compile --dry` clean and both console views render without error
- [x] Every new value resolves from `theme.py`; no literal hex or size added
- [x] Follows existing patterns
