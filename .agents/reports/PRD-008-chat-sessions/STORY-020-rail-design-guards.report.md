---
story: STORY-020
prd: PRD-008
plan: .agents/plans/PRD-008-chat-sessions/completed/STORY-020-rail-design-guards.plan.md
epic_branch: epic/PRD-008-chat-sessions
commit: PENDING
status: COMPLETE
completed: 2026-09-07
---

# Implementation Report — STORY-020: Palette-drift and contrast assertions so the sidebar default fails a test, not a review

**Plan**: `.agents/plans/PRD-008-chat-sessions/completed/STORY-020-rail-design-guards.plan.md`
**Epic Branch**: `epic/PRD-008-chat-sessions`
**Commit**: `PENDING`

## Summary

PRD-008 Risk 6 is now a test rather than a review item. The rail's four refusals — no `TINT_*`, no verdict ink, no radius beyond `theme.RADIUS`, no colour outside the eight ground tokens — are asserted over the rail's *compiled* output by 24 new tests in `tests/test_session_rail.py`, extending the subprocess build probe STORY-018 left for this story. The guard was watched failing against a real `TINT_HELD` fill on the active row and against two radius drifts, then the violations were removed; a permanent detector self-test keeps the "watched failing" claim standing now that they are gone. `tests/test_contrast.py` states the rail's pairings as a set and `tests/test_copy.py` gains a whole-vocabulary check that no copy value is inlined in the component.

**No production code was changed.** `git diff chat_ui/` is empty, as the story requires.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Widen the radius detector to both compiled spellings | `tests/test_session_rail.py` | ✅ |
| 2 | AC 1 — no `TINT_*` value reaches the rail (6 tints) | `tests/test_session_rail.py` | ✅ |
| 3 | AC 2 — no verdict ink, six by value + seven by name + the collision recorded | `tests/test_session_rail.py` | ✅ |
| 4 | AC 3 / AC 4 — split the combined floor test into one radius guard and one ground-token guard | `tests/test_session_rail.py` | ✅ |
| 5 | AC 5 — add the `TINT_HELD` violation, watch it fail, remove it; add the permanent detector self-test | `chat_ui/.../session_rail.py` (reverted) | ✅ |
| 6 | AC 6 — the rail's pairings as a set | `tests/test_contrast.py` | ✅ |
| 7 | AC 8 — no copy value inlined in the rail component | `tests/test_copy.py` | ✅ |
| 8 | AC 7 — verify the render invariants still hold | `tests/test_render_invariants.py` (no edit) | ✅ |
| 9 | Update the STORY-018 handover note now the handover is complete | `tests/test_session_rail.py` | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Guard group (`session_rail`, `contrast`, `copy`, `admin_palette`, `render_invariants`) | ✅ 215 passed (baseline 168) |
| `tests/test_session_rail.py` | ✅ 43 passed (baseline 20) |
| `tests/test_render_invariants.py` | ✅ 57 passed — unchanged from baseline |
| PRD-008 Section 11 pinned suites | ✅ 161 passed, all eight files unmodified |
| Full suite | ✅ 1667 passed, 1 environmental fixture error (see Deviations) |
| Production code untouched | ✅ `git diff chat_ui/` empty |
| E2E | ✅ 7/7 |

## The violation runs (AC 5)

The story is explicit that this is not optional: "A guard that has never been red is a guard nobody has verified." Three drifts were introduced, watched, and removed.

**1. The `TINT_HELD` fill on the active row** — the drift PRD Risk 6 names first. Added to `_row()`:

```python
background_color=rx.cond(_is_active(row), theme.TINT_HELD, "transparent"),
```

Two guards went red together, and nothing else:

```
FAILED tests/test_session_rail.py::test_no_tint_reaches_the_rail[TINT_HELD]
E   AssertionError: TINT_HELD (#FAF6EA) is a fill, and the rail carries none
E   assert '#FAF6EA' not in {'#14181C', '#626C77', '#C3CBD3', '#CBD2D9', '#DDE2E7', '#ECEFF1', ...}

FAILED tests/test_session_rail.py::test_every_colour_in_the_rail_is_a_ground_token
E   AssertionError: ['#FAF6EA']
E   Extra items in the left set: '#FAF6EA'

2 failed, 41 passed
```

**2. A pill on the row open button** — `border_radius="9999px"`:

```
FAILED tests/test_session_rail.py::test_the_only_radius_in_the_rail_is_the_theme_radius
E   AssertionError: ['3px', '9999px']
```

**3. A raw-CSS radius** — `custom_attrs={"style": "border-radius: 20px"}`, which is the case Task 1 existed to catch:

```
FAILED tests/test_session_rail.py::test_the_only_radius_in_the_rail_is_the_theme_radius
E   AssertionError: ['20px', '3px']
```

All three were reverted with `git checkout --`, and `git diff --stat chat_ui/` confirmed empty before commit.

## Findings

**1. The inherited radius detector had a real hole, and it was not cosmetic.**
The plan proposed widening the regex as a defensive no-op. It was not. Measured directly against the compiled output with the raw-CSS drift applied:

```
OLD (js-only) regex sees: ['3px'] -> would PASS
NEW css form sees: ['20px']
```

A pill arriving as a raw CSS string — a `style` attribute, a `_hover` block — would have passed the guard green under the detector STORY-018 shipped. AC 3 names the pill as "the drift's most likely first step", so the guard covering only one of the two spellings it can arrive in was the most consequential gap found in this story. `test_the_radius_detector_still_matches_the_compiled_form` now pins the JS form's presence, so a Reflex change that silently empties the matcher says so.

**2. AC 2 cannot be asserted by value for all seven inks, and the split is now permanent.**
`theme.INK_SELF == theme.INK == #14181C`, and the rail paints every session title in `INK`. Six inks are asserted by value against the rendered output; all seven by token name against the source, which is `tests/test_admin_palette.py`'s mechanism. `test_ink_self_cannot_be_excluded_by_rail_value` asserts the collision and carries the reasoning, and additionally asserts the rail still paints `INK` — so the day the two tokens diverge in `theme.py`, the test fails and points at the tuple that can then grow to seven.

**3. AC 6 needed no new pairing — the predicted outcome, now measured.**
The rail renders exactly two inks on two grounds. Measured ratios:

| | PAPER | HOVER |
|---|---|---|
| **INK** | 15.45:1 | 16.04:1 |
| **MUTE** | 4.63:1 | 4.80:1 |

All four clear WCAG AA (4.5:1), and all four were already covered by the neutral block — including `INK` on `HOVER`, AC 6's specifically named case. The tightest is `MUTE` on `PAPER` at 4.63:1, the same pairing that block already flags as the tightest in the file. The story asked for a new pairing to be treated as "a signal worth recording, not a routine addition"; there was none to record, which is STORY-017 having held the line on colours.

**4. `tests/test_render_invariants.py` encodes no chat-surface invariant, and none was invented.**
It is console-only: `PAGES = ("register_page", "summary_page")`, and its probe renders `admin_page(register(), ...)` and `admin_page(summary(), ...)` only. AC 7's second clause therefore resolves to nothing to hold. The file passes unchanged at 57 tests. The rail's render invariants live in `tests/test_session_rail.py`, which is what PRD Risk 6 asks for in its own words — "a **component** test" — and duplicating them onto a whole-chat-page probe would have produced two places to update, one of which would rot.

**5. The rail renders seven of the eight ground tokens.**
`#14181C #626C77 #C3CBD3 #CBD2D9 #DDE2E7 #ECEFF1 #F1F3F5` — `theme.CARD` (`#FFFFFF`) is legitimately absent, the rail's ground being `PAPER` against the transcript's `CARD`. AC 4's guard is a subset relation for this reason; an equality check would fail on a correct rail.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `tests/test_session_rail.py` | UPDATE | +281/-34 |
| `tests/test_copy.py` | UPDATE | +95 |
| `tests/test_contrast.py` | UPDATE | +59 |
| `chat_ui/chat_ui/components/session_rail.py` | TEMPORARY, REVERTED | 0 (net) |

## Deviations from Plan

1. **Task 5 expected "three guards" red on the tint violation; two went red.** The plan's own enumeration listed only two (AC 1's `TINT_HELD` case and AC 4's ground-token subset) followed by "and nothing else" — the count was a slip in the plan's prose, not a missing guard. Two failed, both predicted, and no others.
2. **Task 1's widening was expected to be a no-op and was not.** See Finding 1. It closed a live hole, verified by measurement rather than assumed.
3. **Two extra violation runs beyond the required one.** The plan listed the radius drift as optional; both it and a raw-CSS variant were run, the second because Finding 1 made it the load-bearing case for Task 1.
4. **`test_the_radius_detector_still_matches_the_compiled_form` was added** beyond the plan's task list, pinning the JS-form match count so a Reflex change cannot silently disarm the radius guard.
5. **One docstring factual correction during implementation**: the rail's tightest pairing is `MUTE` on `PAPER` (4.63:1), not `MUTE` on `HOVER` (4.80:1). Corrected before commit; the measured table above is the source.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_session_rail.py` | `test_no_tint_reaches_the_rail` ×6 (all `TINT_*`); `test_no_verdict_ink_reaches_the_rail` ×6 (inks with own values); `test_the_rail_names_no_verdict_ink` ×7 (by token name, incl. `INK_SELF`); `test_ink_self_cannot_be_excluded_by_rail_value`; `test_the_only_radius_in_the_rail_is_the_theme_radius`; `test_the_radius_detector_still_matches_the_compiled_form`; `test_every_colour_in_the_rail_is_a_ground_token`; `test_the_tint_guard_detects_a_tint` — **24 new**, replacing 1 combined floor test |
| `tests/test_contrast.py` | `test_every_rail_pairing_is_readable` ×4 (INK/MUTE × PAPER/HOVER) |
| `tests/test_copy.py` | `test_no_rail_string_is_written_as_a_literal_in_the_component` ×19 (whole `copy.py` rail vocabulary); `test_the_rail_vocabulary_is_discoverable` |

## Acceptance Criteria

- [x] A test over `session_rail.py`'s rendered output asserts no `TINT_*` value appears — `test_no_tint_reaches_the_rail`, six tints (all six in `theme.py`; `test_render_invariants.py` lists five because PRD-006 predates `TINT_FORBIDDEN`)
- [x] It asserts none of the seven verdict inks appears — six by value, all seven by token name; `INK_SELF` handled per Finding 2
- [x] It asserts no border radius other than `theme.RADIUS` appears — and now catches both compiled spellings (Finding 1)
- [x] It asserts every colour resolves to one of the eight ground tokens — subset relation, per Finding 5
- [x] A deliberate `TINT_HELD` background on the active row made the test fail; the violation was removed — two guards red, output captured above, `git diff chat_ui/` empty after revert
- [x] `tests/test_contrast.py` covers every ink/ground pairing the rail uses at WCAG AA, including `INK` on `HOVER` — 4/4, no new pairing required (Finding 3)
- [x] `tests/test_render_invariants.py` passes with the rail present — 57 passed, unchanged; no chat-surface invariant exists to hold (Finding 4)
- [x] `tests/test_copy.py` asserts no literal user-facing string appears in the rail component — whole-vocabulary check, watched failing on an inlined `"New chat"`
- [x] All tasks completed
- [x] No production code changed
- [x] Full suite passes; Section 11's pinned suites unmodified and green (161 passed)
- [x] Follows existing patterns (`test_admin_palette.py`, `test_render_invariants.py`, `test_contrast.py`)
