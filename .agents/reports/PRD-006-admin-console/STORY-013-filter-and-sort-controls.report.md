---
story: STORY-013
prd: PRD-006
plan: .agents/plans/PRD-006-admin-console/completed/STORY-013-filter-and-sort-controls.plan.md
epic_branch: epic/PRD-006-admin-console
commit: PENDING
status: COMPLETE
completed: 2026-08-31
---

# Implementation Report — STORY-013: Verdict multi-select, free-text filter and sort controls on the register

**Plan**: `.agents/plans/PRD-006-admin-console/completed/STORY-013-filter-and-sort-controls.plan.md`
**Epic Branch**: `epic/PRD-006-admin-console`
**Commit**: `PENDING`

## Summary

The register's filter strip: a verdict multi-select over the four verdicts, a
free-text field over `user_id` / `model_used` / `audit_id`, three sort controls
and a clear action — all hung on the strip STORY-011 left above the table, laid
out as PRD-006 Section 6.1's wireframe shows.

The surface only. Every piece of filtering machinery was already STORY-005's
(`selected_verdicts`, `search`, `sort_key`, `sort_descending`, `visible_rows`,
`filters_active`, and the handlers `toggle_verdict`, `set_search`, `sort_by`,
`clear_filters`), and every string was already STORY-008's — `admin_copy.py` was
not touched. The controls write those handlers and read those vars; the
narrowing stays a synchronous computed var, so nothing on this surface reaches
the database.

Two supporting edits, both named in the plan rather than smuggled in: a
`register_filtered` computed var on `AdminState` (AC 4's count is a Python format
string over thousands-separated ints, neither of which runs against a Var), and
`#register_filter_input` added to `theme.py`'s Radix-text selector lists.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | `register_filtered` computed var — the filtered count as a second scope statement | `chat_ui/chat_ui/admin_state.py` | ✅ |
| 2 | `#register_filter_input` added to `GLOBAL_CSS`'s two Radix-text selector lists | `chat_ui/chat_ui/theme.py` | ✅ |
| 3 | The verdict multi-select — four chips, ink-and-rule selection, no fill | `chat_ui/chat_ui/components/register.py` | ✅ |
| 4 | The free-text field, the three sort controls and the clear action | `chat_ui/chat_ui/components/register.py` | ✅ |
| 5 | `_filter_strip()` + `_filtered_line()`, and `register()` reworked onto them | `chat_ui/chat_ui/components/register.py` | ✅ |
| 6 | Test extension: probe factories, 38-name copy sweep, 16 new assertions | `tests/test_register.py` | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| `reflex compile --dry` | ✅ compiled in 1.5s, no errors |
| Backend / `app/` untouched | ✅ `git diff --stat -- app/` empty |
| `tests/test_register.py` | ✅ 157 passed (was 116) |
| Full suite | ✅ 602 passed |
| Browser console (errors + warnings) | ✅ none |
| E2E | ✅ 10/10 |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `chat_ui/chat_ui/components/register.py` | UPDATE | +449/-16 |
| `tests/test_register.py` | UPDATE | +316/-9 |
| `chat_ui/chat_ui/admin_state.py` | UPDATE | +35 |
| `chat_ui/chat_ui/theme.py` | UPDATE | +4/-4 |
| `chat_ui/chat_ui/admin_copy.py` | **unchanged** | — |
| `app/**` | **unchanged** | — |

## Deviations from Plan

1. **A shared `_control_button` factory**, where the plan implied a separate
   builder per control kind. Forced by
   `test_the_data_face_is_dominant`, which asserts
   `count("theme.FONT_DATA") > count("theme.FONT_DISPLAY")`: three separate
   display-face declarations would have tied the count at 6–6 and inverted the
   type hierarchy PRD-006 Section 6.1 sets for this surface. Stating the face
   once in one factory is also the better code — it is the register's existing
   "a control that draws no chrome" idiom, now named.

2. **`_search_field()` returns the label and the field together**, rather than
   the plan's separate `_search_field` / `_search_field_row`. One name, one
   cluster; no behaviour difference.

3. **Two planned tests moved into the build probe.** They were written to import
   `_SORT_MARKS` / `_SORT_CONTROLS` in-process, which cannot work — `register.py`
   does `from chat_ui import admin_copy`, which resolves only under the `chat_ui/`
   PYTHONPATH the subprocess probe runs with. That is the whole reason the probe
   exists; the tables are now emitted as JSON from the probe instead.

4. **The direction-mark assertion counts the compiled escape, not the glyph.**
   Reflex emits `↑` into the generated JavaScript as the six-character `\uXXXX`
   escape, so counting the character found zero and would have passed a weaker
   test than intended. `_as_compiled()` converts before counting.

5. **Risk 1 did not materialise.** `rx.input` was kept: Radix resolved its colours
   to CSS custom properties, `test_no_colour_outside_the_allowed_set` passes over
   the compiled output, and the `rx.debounce_input(rx.el.input(...))` fallback was
   not needed. The Radix field also brings the 300 ms `DebounceInput` wrap that
   mitigates PRD Risk 5.

6. **Incidental lockfile churn reverted.** The production build reformatted
   `chat_ui/reflex.lock/package.json` and bumped `lucide-react` 1.14.0 → 1.26.0.
   Unrelated to this story — which adds no dependency — so both files were
   restored and left out of the commit.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_register.py` | `test_every_verdict_is_offered_as_a_filter` (×4), `test_the_filter_strip_carries_both_filters`, `test_the_verdict_filter_writes_the_state_handler`, `test_the_selected_verdicts_are_marked_without_a_fill`, `test_the_free_text_field_is_bound_to_the_search_var`, `test_the_field_is_debounced_by_construction`, `test_the_filtered_count_is_a_second_line_not_a_replacement`, `test_the_filtered_count_shows_only_against_an_active_filter`, `test_the_clear_action_is_conditional_on_filters_active`, `test_each_sort_key_has_a_control` (×3), `test_the_sort_controls_cover_every_declared_key`, `test_the_timestamp_default_is_marked_active`, `test_the_direction_mark_is_chosen_per_ordering`, `test_the_direction_mark_rides_only_on_the_active_control`, `test_every_control_is_a_real_button`, `test_the_controls_set_no_focus_reset` |

Also updated: `test_body_face_appears_only_on_the_scope_line` →
`test_the_body_face_is_reserved_for_the_scope_lines`, asserting `== 2`. PRD-006
Section 6.1 reserves `FONT_BODY` for "the two or three explanatory lines that
state a scope"; the filtered count is the second, and setting it in another face
would say the two statements are different kinds of thing. Still an exact count —
the face creeping onto a third element is how a register starts reading as prose.

`COPY_NAMES` grew from 28 to 38, so `test_every_string_is_read_from_admin_copy`
and `test_no_copy_value_is_written_as_a_literal` now mechanically enforce AC 8
over every control label.

## Design Notes

**Why plain buttons and not a Radix group.** Verified against the pinned
`reflex==0.9.6.post1` / `reflex_components_radix==0.9.5` rather than recalled, per
`chat_ui/AGENTS.md`: there is no `rx.toggle_group` in this build;
`rx.checkbox_group.root` declares neither `value` nor `on_change` and so cannot
be driven from `selected_verdicts`; and `rx.segmented_control.root(type="multiple")`,
which *is* controlled, offers only the `classic` and `surface` variants — both
fills, both carrying a compile-time `color_scheme` accent, which PRD-006 Risk 6
rules out and which a source grep cannot see. Its `on_change` also hands over the
whole selection as a list, where `toggle_verdict` takes one verdict, so wiring it
would have meant adding a handler to STORY-005's state.

**The direction mark is chosen per ordering.** `sort_rows` documents
`sort_descending = False` as the *natural* order of the chosen key — and that is a
different direction for each: newest-first for timestamp, A–Z for user,
exceptions-first for verdict. One glyph cannot be true of all three, so
`_SORT_MARKS` pairs them per key. Verified live: Time shows ↓ on newest-first,
User ↑ on A–Z, Verdict ↓ on fault-first.

**The timestamp default is visible.** `sort_key` defaults to `""` so `sign_out()`'s
reset can clear it, and `sort_rows` reads `""` as the loaded order. `_is_sorted_by`
therefore matches the empty string too — without it PRD-006's "timestamp
descending remains the default" would be true of the table and invisible on the
surface. Confirmed in the browser: **Time↓** is `pressed` on a fresh load.

**Selection without a fill.** A selected chip carries its verdict's ink as text
plus a 2px rule in that same ink, never a ground — Risk 6, and the story's "the
verdict chips may carry their verdict ink as text, not as a fill". `aria-pressed`
is the third channel, for a reader that sees no colour.

## Acceptance Criteria

- [x] Given the register header, when it renders, then it carries a verdict multi-select over the four verdicts and a free-text field over `user_id` / `model_used` / `audit_id`, positioned as PRD Section 6.1's wireframe shows.
- [x] Given the verdict multi-select, when a verdict is toggled, then the table narrows without a database read and the selected verdicts are visibly marked. — *DENIED narrowed 6 rows to 1; chip took its ink, its rule and `aria-pressed`.*
- [x] Given the free-text field, when `127` is typed, then the row whose `audit_id` is 127 is isolated. — *Typing `3` surfaced `#3`; the second match was `claude-3` on `model_used`, which is the documented three-field search.*
- [x] Given both filters active, when the table renders, then they compose as AND and the row count shown reflects the filtered set, distinct from the "100 most recent of {total}" scope line. — *DENIED ∧ `m.silva` = "0 of 6 shown" beneath an unchanged "6 most recent of 6"; an OR would have widened it.*
- [x] Given active filters, when a clear action is used, then all filters reset and the full window returns. — *Chip unpressed, field emptied, filtered line and clear control gone, sort untouched.*
- [x] Given the sort controls, when timestamp, user or verdict is chosen, then the table reorders and the active sort is visibly indicated; timestamp descending remains the default. — *User↑ gave A–Z, User↓ gave Z–A, Verdict↓ gave FAULT→DENIED→HELD→cleared; Time↓ active on load; exactly one control marked at a time.*
- [x] Given a keyboard user, when they tab through the filter and sort controls, then each is reachable and operable with visible focus. — *Tab reached the chips in document order with the `:focus-visible` ring rendered; Enter toggled the focused chip.*
- [x] Given every label on these controls, when grepped, then each resolves from `admin_copy`. — *38 copy names asserted both directions; no prose literal in the control block.*
- [x] All tasks completed
- [x] `python -m pytest -q` passes (602), with `app/` and its test suites unmodified
- [x] Reflex app compiles and the register renders without error
- [x] Follows existing patterns
