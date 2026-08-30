---
story: STORY-006
prd: PRD-006
plan: .agents/plans/PRD-006-admin-console/completed/STORY-006-admin-state-tests.plan.md
epic_branch: epic/PRD-006-admin-console
commit: 3d6474e
status: COMPLETE
completed: 2026-08-30
---

# Implementation Report — STORY-006: tests/test_admin_state.py: gate, sign-out, failed read, four verdicts, no leak

**Plan**: `.agents/plans/PRD-006-admin-console/completed/STORY-006-admin-state-tests.plan.md`
**Epic Branch**: `epic/PRD-006-admin-console`
**Commit**: `3d6474e`

## Summary

Completed `tests/test_admin_state.py` and with it PRD-006 Section 12's Phase 1 validation. The file already existed at 1015 lines / 52 passing tests — STORY-003, STORY-004 and STORY-005 each wrote their own half as they landed, and the module docstring recorded that STORY-006 would finish it. The work was therefore the gap between the story's seven ACs and what was already asserted: the four verdicts against constructed `AuditLog`s (plus the Risk 3 fifth case), the no-leak claim asserted field by field, and the two filters applied to rows that genuinely came from a read with the database call list asserted unchanged. AC 1, AC 2 and AC 3 were already satisfied verbatim and were verified in place rather than rewritten; AC 5's two halves were brought into one test.

The file grew from 52 to **61 tests**. No application file was touched, no dependency added.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | `_Reads` gains a keyword-only `logs=`, defaulting to prior behaviour | `tests/test_admin_state.py` | ✅ |
| 2 | Four verdicts against constructed `AuditLog`s + Risk 3 fifth case (AC 4) | `tests/test_admin_state.py` | ✅ |
| 3 | Field-by-field no-leak assertion on a seeded row (AC 6, Risk 2) | `tests/test_admin_state.py` | ✅ |
| 4 | Filters narrow loaded rows without a second read (AC 7) | `tests/test_admin_state.py` | ✅ |
| 5 | AC 5's row half stated beside its read half | `tests/test_admin_state.py` | ✅ |
| 6 | Module docstring + STORY-005 block: forward references retired | `tests/test_admin_state.py` | ✅ |
| 7 | Scope verification (suite, named files, `app/`, dependencies) | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| `tests/test_admin_state.py` | ✅ 61 passed (was 52) |
| Full suite | ✅ 358 passed |
| Six PRD §11 named files, unmodified | ✅ 75 passed; `git diff --name-only` lists none of them |
| No new dependency | ✅ both `requirements.txt` unchanged |
| Story changed nothing under `app/` | ✅ (see Deviations — branch-level caveat) |
| Negative-control: no-leak test proven to fail | ✅ red when a preview field was reintroduced, then reverted |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `tests/test_admin_state.py` | UPDATE | +260 / −8 |
| `.agents/plans/PRD-006-admin-console/completed/STORY-006-admin-state-tests.plan.md` | CREATE (archived plan) | +278 |

## Deviations from Plan

1. **The file already existed.** The story's Technical Notes call for a *new* file `tests/test_admin_state.py`; STORY-003 created it and STORY-004/005 extended it. The assertions the story asks for were appended to that file rather than split across a second module. This was identified during planning and recorded in the plan's scope note — it changes what was written, not what is asserted.

2. **`git diff main --stat -- app/` is not empty**, contrary to the plan's E2E checklist. Two files differ: `app/db/database.py` (+14/−1) and `app/db/models.py` (+11). The divergence comes from commit `3f553f2` ("feat(chat-ui): implement PII column migration…"), a PRD-004-era commit already in this branch's history before any PRD-006 story began — `git log main..HEAD -- app/` names it as the only such commit. **This story changed nothing under `app/`**, and neither did STORY-001 … STORY-005. Flagged here because STORY-020 owns the "nothing under `app/` changed" proof and will have to reconcile this inherited state rather than discover it late.

3. **Task 3's negative control required temporarily editing two application files** (`admin_models.py`, `admin_formatting.py`) to prove the no-leak test fails when a preview returns. Confirmed red, then reverted via `git checkout --`; both files are byte-identical to their committed state and neither appears in this story's diff.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_admin_state.py` | `test_each_constructed_log_reaches_the_row_with_its_verdict` (×5 params: duplicate-blocked → **held**, suspicious-pattern → **denied**, failed → **fault**, plain → **cleared**, failed-with-model → **fault**) |
| | `test_the_loaded_register_carries_the_four_verdicts_in_order` — the same five logs through `load()` into `AdminState.rows` |
| | `test_a_failed_row_that_recorded_a_model_is_still_fault` — Risk 3 guard, both faults asserted equal to each other |
| | `test_a_row_built_from_a_seeded_log_carries_neither_preview` — no attribute, no declared field, no sentinel in any field value |
| | `test_filtering_the_loaded_register_narrows_it_without_a_second_read` — verdict + free text AND-composed over read rows, call list unchanged |

## Acceptance Criteria

- [x] Correct token → `authenticated` True; wrong and empty tokens leave it False with the **same** error string, asserted as equal to each other — `test_correct_token_authenticates_clears_the_error_and_triggers_the_load`, `test_the_three_refusals_produce_the_identical_message` (pre-existing, verified)
- [x] `sign_out()` empties rows, clears summary figures, clears the token, `authenticated` False — `test_sign_out_clears_the_token_the_rows_and_the_figures`, `test_sign_out_clears_every_declared_var` (pre-existing, verified)
- [x] A patched read that raises → error string set, `loading` False, previously loaded rows unchanged — `test_a_failed_read_names_it_and_leaves_the_record_untouched`, `test_every_read_position_faults_the_same_way` (pre-existing, verified)
- [x] Four constructed `AuditLog`s → exactly **held**, **denied**, **fault**, **cleared** — NEW
- [x] Risk 3 fifth case: `success=False` **with** `model_used` → **fault** — NEW
- [x] Unauthenticated `load()` → row list empty **and** no read function called — both halves now in `test_an_unauthenticated_load_calls_none_of_the_ten`
- [x] `AuditRow` from a seeded log: no preview attribute, neither preview string in any field value — NEW
- [x] `visible_rows` under verdict + free-text filter returns the expected rows with no second database call — NEW
- [x] All tasks completed
- [x] Full suite green; PRD §11's six named test files pass unmodified
- [x] No new dependency; this story's diff is one test file
- [x] Follows existing patterns (import preamble, handler-driving helpers, `_READS` patch site, imported verdict constants)
