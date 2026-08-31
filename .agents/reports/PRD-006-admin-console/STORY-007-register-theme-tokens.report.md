---
story: STORY-007
prd: PRD-006
plan: .agents/plans/PRD-006-admin-console/completed/STORY-007-register-theme-tokens.plan.md
epic_branch: epic/PRD-006-admin-console
commit: a650a97
status: COMPLETE
completed: 2026-08-30
---

# Implementation Report — STORY-007: theme.py register tokens

**Plan**: `.agents/plans/PRD-006-admin-console/completed/STORY-007-register-theme-tokens.plan.md`
**Epic Branch**: `epic/PRD-006-admin-console`
**Commit**: `a650a97`

## Summary

Four tokens added to `chat_ui/chat_ui/theme.py` — `HOVER`, `ROW_H`, `STAMP_X`, `TEXT_MICRO` — as module constants beside the existing ones, with the one hue-bearing value among them asserted against `tests/test_contrast.py`. The edit is **additions only**: `git diff --stat` reports 9 insertions and **0 deletions** on `theme.py`, which is AC 6 proven structurally rather than by inspection. `STAMP_X` binds to the `RAIL_X` constant rather than copying its literal, so the register's stamp margin and the chat's rail cannot drift apart — PRD Section 6.1's "continued rather than reinvented", made mechanical.

A second file, `tests/test_admin_palette.py`, carries the two claims that are about *absence* and therefore invisible in a diff: that the four tokens exist and are well-formed (AC 1), and that no admin module references `INK_UPSTREAM` or `INK_SELF` (AC 3).

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | `HOVER = "#F1F3F5"` into the Ground block | `chat_ui/chat_ui/theme.py` | ✅ |
| 2 | `TEXT_MICRO = "0.625rem"` above `TEXT_TAG`, block stays ascending | `chat_ui/chat_ui/theme.py` | ✅ |
| 3 | `STAMP_X = RAIL_X` and `ROW_H = "2.25rem"` in the metrics block | `chat_ui/chat_ui/theme.py` | ✅ |
| 4 | `_INK_ON_HOVER` table + two neutral rows, append-only | `tests/test_contrast.py` | ✅ |
| 5 | Token and chat-only-ink guard | `tests/test_admin_palette.py` | ✅ |
| 6 | Prove the chat is untouched | — (verification) | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| `theme` imports outside a Reflex context | ✅ |
| `tests/test_contrast.py` | ✅ 22 passed (was 16) |
| `tests/test_admin_palette.py` | ✅ 10 passed |
| Full suite `python -m pytest tests/ -q` | ✅ 374 passed |
| `theme.py` deletions | ✅ 0 |
| E2E | ⚠️ 6/7 — see *Deviations*, item 3 |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `chat_ui/chat_ui/theme.py` | UPDATE | +9 / −0 |
| `tests/test_contrast.py` | UPDATE | +27 / −1 (the −1 is a docstring line rewrapped; no assertion touched) |
| `tests/test_admin_palette.py` | CREATE | +118 |

## The values, as shipped

| Token | Value | Note |
|---|---|---|
| `HOVER` | `#F1F3F5` | Verdict inks land at 5.45 – 7.12, `INK` at 16.04, `MUTE` at 4.80. Lifts toward `CARD`; darkening was measured and rejected (`#E3E8EC` puts `MUTE` at 4.33, below AA). |
| `ROW_H` | `2.25rem` | 36px. Reasoned from target size and scan density, not observed — flagged for retuning in STORY-019. |
| `STAMP_X` | `RAIL_X` | Bound by identity; `test_stamp_margin_is_the_chat_rail_continued` fails on a hand-copied literal. |
| `TEXT_MICRO` | `0.625rem` | 10px, one step below `TEXT_TAG`. |

## Deviations from Plan

1. **The `RULE`-on-hover assertion was added, measured, and dropped — as the plan instructed.** Task 4 predicted it would fail at ~1.47:1. Measured, it is **1.372:1**. `RULE` is a hairline, not text, so WCAG AA does not apply to it; asserting it would have forced `AA_NORMAL` down for every pairing in the file. The row is gone and a comment in its place records the number and the reasoning, so the omission reads as a decision rather than an oversight. Final count is 22, exactly the plan's prediction.

2. **`test_console_adds_no_tint` was added to `tests/test_admin_palette.py`, beyond the two groups the plan specified.** The plan's Risk 4 names this file as where STORY-018 hangs the tint guard; adding the module-level half now costs six lines and makes PRD Risk 6's drift fail a test rather than a review. STORY-018 still owns the rendered-output half.

3. **The plan's E2E item "`git diff main -- app/` is empty" FAILS — on a pre-existing condition this story did not create.** Reported rather than papered over:
   - `app/db/database.py` (+14/−1) and `app/db/models.py` (+11) differ from `main` on this epic branch.
   - Both come from commit **`3f553f2`** (2026-08-28, *"feat(chat-ui): implement PII column migration and enhance duplicate message formatting"*), which predates every PRD-006 story.
   - STORY-007's own change set touches no file under `app/` — `git status --porcelain | grep app/` is empty.
   - **This matters beyond this story**: PRD Section 4 lists "Any change under `app/`" as out of scope, and STORY-020 is *"the proof that nothing under `app/` changed."* As the branch stands, STORY-020 cannot pass. It needs a decision — either the `app/` migration is moved off this epic branch, or PRD-006's scope is amended to acknowledge an inherited change. Flagged now rather than discovered at the end of Phase 4.

4. **`tests/test_pii_badge.py` and `tests/test_chat_components_import.py` show as differing from `main`.** They are *new files added* on the epic branch, not modified ones — `git cat-file -e main:<path>` fails for both. The "unmodified" guarantee holds.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_contrast.py` (extended) | `test_verdict_ink_is_readable_on_the_row_hover` ×4 (`INK_CLEAR`, `INK_HELD`, `INK_DENIED`, `INK_FAULT`); `test_neutral_pairs_are_readable` +2 rows (body ink on row hover, muted text on row hover) |
| `tests/test_admin_palette.py` (new) | `test_register_tokens_exist`; `test_hover_ground_is_a_hex_colour`; `test_register_sizes_scale_with_the_reader` ×2; `test_stamp_margin_is_the_chat_rail_continued`; `test_micro_step_is_below_the_tag_step`; `test_admin_modules_are_discoverable`; `test_no_admin_module_references_a_chat_only_ink` ×2; `test_console_adds_no_tint` |

**Negative control run on the guard**, so it is not a test that cannot fail: planting `INK_SELF` into `chat_ui/chat_ui/admin_models.py` produced `FAILED tests/test_admin_palette.py::test_no_admin_module_references_a_chat_only_ink[INK_SELF]`; the file was restored with `git checkout --` and the suite returned to 10 passed. The glob covers `admin_formatting.py`, `admin_models.py`, `admin_state.py` today and is written to pick up STORY-009/011/015's modules automatically.

**Recorded for STORY-018**: `theme.GLOBAL_CSS` sets the global `:focus-visible` outline to `INK_UPSTREAM`, and the admin pages inherit that stylesheet. Not a violation — the rule is about admin *modules*, and a focus ring is a shared accessibility affordance, not a verdict signal — but a naive grep of rendered admin HTML will find that blue. Written into `test_admin_palette.py`'s module docstring so the render-invariant test is authored knowing it.

## Acceptance Criteria

- [x] `theme.py` gains a register row height, a stamp-margin width, a row hover ground and a micro type step, each a module constant beside the existing ones — `ROW_H`, `STAMP_X`, `HOVER`, `TEXT_MICRO`; asserted by `test_register_tokens_exist`
- [x] Reuses `INK_CLEAR`, `INK_HELD`, `INK_DENIED`, `INK_FAULT`, `PAPER`, `CARD`, `RULE`, `RULE_SOFT`, `MUTE`, `SPINE` unchanged and introduces no new hue — `HOVER` is a neutral on the existing blue-grey axis, not an accent; 0 deletions in the diff
- [x] `INK_UPSTREAM` and `INK_SELF` referenced by no admin module — asserted by `test_no_admin_module_references_a_chat_only_ink`, negative-control verified
- [x] Every new ink/ground pairing asserted at or above `AA_NORMAL` in `tests/test_contrast.py`, alongside the existing chat pairings
- [x] The hover ground clears WCAG AA against every verdict ink (5.45 – 7.12) and against `INK` (16.04), covered by the contrast test
- [x] The chat renders identically — 9 insertions, 0 deletions on `theme.py`; no existing token value altered
- [x] All tasks completed
- [x] `python -m pytest tests/ -q` green (374 passed), PRD-001/003/004 tests unmodified
- [ ] `git diff main -- app/` empty — **fails on a pre-existing condition from `3f553f2`**, not from this story, which touches no `app/` file. See *Deviations*, item 3.
- [x] Follows existing patterns
