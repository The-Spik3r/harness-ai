---
story: STORY-014
prd: PRD-006
plan: .agents/plans/PRD-006-admin-console/completed/STORY-014-three-empty-states.plan.md
epic_branch: epic/PRD-006-admin-console
commit: 3fe5dda
status: COMPLETE
completed: 2026-08-31
---

# Implementation Report — STORY-014: Three distinct register states

**Plan**: `.agents/plans/PRD-006-admin-console/completed/STORY-014-three-empty-states.plan.md`
**Epic Branch**: `epic/PRD-006-admin-console`
**Commit**: `3fe5dda`

## Summary

The register renders three states instead of one table, and the precedence over
them lives in exactly one place: `AdminState.register_state`, a computed var
returning `read_failed` / `no_rows` / `no_matches` / `rows` in that order.
`components/register.py:_register_body` is an `rx.match` over it.

That shape was chosen for the story's hardest criterion. AC 4 is an *ordering* —
a failed read must never be dressed as emptiness — and `rx.match` compiles every
arm into the output, so the ordering is unreadable off the compiled JavaScript.
Resolved in Python it is a function `tests/test_admin_state.py` calls directly,
with `error` set both over an empty register and over a stale one.

The `read_failed` arm renders the **table**, deliberately:
`admin_copy.FAULT_MESSAGE_TEMPLATE` promises "Nothing on screen has changed", so
the previously loaded rows stay standing and STORY-017 hangs its fault panel
above them. What this story owns is that the arm exists and that neither empty
panel is reachable while `error` is set.

Every string was already declared — STORY-008 wrote the two panels' copy and
reserved it for this story by name. One constant was added
(`FILTER_DESCRIPTION_VERDICT_JOIN`), because the no-matches sentence lists
verdicts and AC 5 requires every string on these panels resolve from
`admin_copy`.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | `FILTER_DESCRIPTION_VERDICT_JOIN` — the verdict-list separator | `chat_ui/chat_ui/admin_copy.py` | ✅ |
| 2 | `REGISTER_STATE_*` keys, `_VERDICT_LABELS`, and the `register_state` + `empty_matches_message` computed vars | `chat_ui/chat_ui/admin_state.py` | ✅ |
| 3 | `_empty_panel` and `_empty_register` | `chat_ui/chat_ui/components/register.py` | ✅ |
| 4 | `_no_matches`, `_table`, `_register_body`; `register()` rewired | `chat_ui/chat_ui/components/register.py` | ✅ |
| 5 | Tests: the precedence in pytest, the panels in the probe | `tests/test_admin_state.py`, `tests/test_register.py`, `tests/test_copy.py` | ✅ |
| 6 | Full suite and the `app/` guarantee | — | ✅ (with one finding, below) |

## Validation Results

| Check | Result |
|-------|--------|
| `reflex compile --dry` | ✅ compiled in 1.55s, no errors |
| `tests/test_register.py` | ✅ 174 passed (was 157) |
| `tests/test_admin_state.py` | ✅ 80 passed (was 70) |
| `tests/test_copy.py` | ✅ passed, roster extended |
| Full suite | ✅ 630 passed (was 602) |
| Story touches `app/` | ✅ `git diff --stat -- app/` empty |
| Browser console (errors + warnings) | ✅ none, on both databases |
| E2E | ✅ 11/11 |

### E2E detail

Two browser sessions (prod build, `reflex run --env prod --single-port`) — one
against the repo's seeded database, one against a freshly initialised empty one —
plus a state-level harness driving `load()` against real SQLite files for the
paths a browser cannot force.

| # | Check | How | Result |
|---|-------|-----|--------|
| 1 | Full suite green, `app/` suites unmodified | pytest | ✅ 630 |
| 2 | Empty database → "The register is empty.", no column heads, no clear action | browser | ✅ |
| 3 | Seeded database → the table, neither empty state | browser | ✅ 6 rows |
| 4 | `zzzz` → the no-matches panel naming `text "zzzz"` and the loaded count, clear beneath it | browser | ✅ |
| 5 | + **denied** → both filters named, joined by " and " | browser | ✅ rendered `verdict held, denied and text "zzzz" matched none of the 6 rows loaded.` |
| 6 | The panel's **Clear filters** → full window returns, sort untouched | browser | ✅ |
| 7 | A verdict absent from the window → no-matches, not nothing-recorded | state harness on a seeded all-`cleared` database (the browser window held all four verdicts) | ✅ |
| 8 | A read forced to raise → the table stays, neither empty state appears | state harness, 3 variants: stale window, first-read failure, retry recovery | ✅ |
| 9 | Keyboard: the panel's clear action reachable, focus-visible, Enter operates it | browser | ✅ real `<button>`, `tabIndex 0`, `:focus-visible` matched, solid outline |
| 10 | Narrow viewport (640px) → the sentence wraps inside its measure, no horizontal page scroll | browser | ✅ |
| 11 | No user-facing string literal added | grep | ✅ every panel string reads `admin_copy.` or an `AdminState` var |

AC 6 was additionally confirmed against the live DOM rather than only the
compiled string: the panel computes to a transparent background, `0px` border,
`0px` radius, no box-shadow and zero `img`/`svg`; the title is Archivo at 17px
(`TEXT_LEAD`) in `INK`, the body Source Serif 4 in `MUTE` at a 672px measure
(`MEASURE`).

The precedence was also observed live: with a text filter typed against an empty
database, the register still reads "The register is empty." and never "No rows
match this filter."

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `chat_ui/chat_ui/admin_copy.py` | UPDATE | +9 |
| `chat_ui/chat_ui/admin_state.py` | UPDATE | +117 |
| `chat_ui/chat_ui/components/register.py` | UPDATE | +141/-13 |
| `tests/test_admin_state.py` | UPDATE | +203 |
| `tests/test_register.py` | UPDATE | +231/-9 |
| `tests/test_copy.py` | UPDATE | +34 |

No file created. No file under `app/` touched.

## Deviations from Plan

1. **The `FONT_BODY` count moved to 3, not the 4 the plan predicted.** Both
   panels are built by the one `_empty_panel`, so they contribute a single use
   between them, not one each. `test_the_body_face_is_reserved_for_the_scope_lines`
   was updated to 3 with that reasoning written in — and the count stays exact
   rather than becoming a ceiling, so a second use appearing would mean the two
   states had grown two separate shapes.

2. **`test_the_data_face_is_dominant` needed a change the plan did not
   anticipate.** `_empty_panel`'s title is a fourth `FONT_DISPLAY` use, which tied
   the whole-file comparison at 6:6 and failed the `>`. Rather than weaken the
   invariant, the count is now taken over the table's half of the module —
   PRD-006 Section 6.1 grounds "the data face is dominant" in the table's own job
   ("the columns are numeric and must align down a hundred rows"), and the two
   panels have no columns and no rows. The section marker is asserted to exist so
   renaming it fails loudly rather than silently skewing the count.

3. **`tests/test_copy.py` was a third test file to update**, unlisted in the
   plan: it keeps an exhaustive roster of `admin_copy`'s public names, so the new
   constant had to be declared there. A test was added pinning that the two
   joiners are distinct — the reason the constant exists — by asserting the whole
   assembled sentence.

4. **The plan's comment for the `REGISTER_STATE_FAULT` rationale had to be
   reworded.** `test_the_verdict_vocabulary_is_imported_not_redeclared` forbids
   the four verdict strings appearing as literals anywhere in `admin_state.py`,
   and the explanatory comment quoted one. Caught by the existing test on first
   run; the comment now names the constant instead of quoting the word.

## Finding (not caused by this story)

The plan's Task 6 check `git diff main --stat -- app/` does **not** print
nothing: `app/db/database.py` (+14/-1) and `app/db/models.py` (+11) differ
between `main` and the epic branch. That delta comes from commit `3f553f2`
("feat(chat-ui): implement PII column migration…", 2026-08-28), which predates
PRD-006's story work and is not attributable to any story on this board. This
story itself touches no file under `app/` (`git diff --stat -- app/` on the
working tree is empty).

PRD-006 Section 3 offers "nothing under `app/` changes" as a guarantee to the
integrating developer, and **STORY-020** exists to prove it. That story will
either have to account for `3f553f2` explicitly or scope its assertion to the
PRD's own commits. Flagging it here so it is not discovered as a surprise at the
end of the epic.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_admin_state.py` | `test_register_state_resolves_the_three_states`, `test_a_failed_read_is_never_reported_as_emptiness`, `test_clearing_the_error_returns_the_register_to_its_data`, `test_register_state_is_computed_so_sign_out_keeps_its_guarantee`, `test_every_verdict_has_a_label`, `test_the_no_matches_sentence_names_the_filter_that_produced_it`, `test_the_verdict_list_is_ordered_and_labelled`, `test_the_no_matches_sentence_states_the_loaded_window`, `test_the_sentence_reads_the_trimmed_search`, `test_the_no_matches_state_implies_an_active_filter` |
| `tests/test_register.py` | `test_both_empty_states_reach_the_output`, `test_the_nothing_recorded_state_names_no_filter`, `test_the_no_matches_state_offers_the_clear_action`, `test_the_no_matches_sentence_is_bound_to_the_state`, `test_the_fault_arm_renders_the_table_not_an_empty_state`, `test_every_register_state_has_an_arm`, `test_the_table_is_the_default_arm`, `test_the_empty_states_carry_no_card_and_no_illustration`, `test_the_empty_states_use_the_registers_own_type_scale`, `test_the_table_arm_is_the_table_story_011_built`, `test_the_filter_strip_renders_in_every_state` |
| `tests/test_copy.py` | `test_the_two_filter_joiners_are_distinct`; roster + non-empty assertions extended |

## Acceptance Criteria

- [x] Given a database with no audit rows at all, when the register renders, then it shows a "nothing recorded" state that says the record is empty — distinct in wording from the no-matches state. *(E2E 2, browser, against a freshly initialised database; the two titles are asserted unequal in `test_both_empty_states_reach_the_output`.)*
- [x] Given rows loaded but a filter that matches none of them, when the register renders, then it names the filter that produced the empty result and offers to clear it, and the clear action restores the full window. *(E2E 4–6; the offer is `_clear_control()` itself, not a second button.)*
- [x] Given rows that match, when the register renders, then the table is shown and neither empty state appears. *(E2E 3.)*
- [x] Given a failed read, when the register renders, then the fault panel is shown (STORY-017) rather than either empty state — an error is never presented as emptiness. *(The precedence is `register_state`, asserted over an empty register, a stale one and a recovery; the arm renders the table so the rows stay standing for STORY-017's panel.)*
- [x] Given all three states, when their copy is grepped, then every string resolves from `admin_copy`. *(E2E 11 and `test_every_string_is_read_from_admin_copy`.)*
- [x] Given the empty states, when they render, then they use the register's existing type and rules — no illustration, no card, no accent colour. *(Live computed styles plus `test_the_empty_states_carry_no_card_and_no_illustration`.)*
- [x] All tasks completed
- [x] `python -m pytest -q` passes (630), with `app/` and its test suites unmodified by this story
- [x] Reflex app compiles and the register renders without error
- [x] Follows existing patterns
