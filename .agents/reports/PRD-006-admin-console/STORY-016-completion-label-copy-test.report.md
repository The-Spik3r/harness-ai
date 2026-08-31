---
story: STORY-016
prd: PRD-006
plan: .agents/plans/PRD-006-admin-console/completed/STORY-016-completion-label-copy-test.plan.md
epic_branch: epic/PRD-006-admin-console
commit: PENDING
status: COMPLETE
completed: 2026-08-31
---

# Implementation Report — STORY-016: Copy test pinning the completion label so it cannot regress to "success rate"

**Plan**: `.agents/plans/PRD-006-admin-console/completed/STORY-016-completion-label-copy-test.plan.md`
**Epic Branch**: `epic/PRD-006-admin-console`
**Commit**: `PENDING`

## Summary

One new file, `tests/test_admin_copy.py` — five tests that pin what the console's
load-bearing strings *claim*, where the existing suite only pinned that they
exist.

The gap this closes was real and measured before writing anything: STORY-008's
appended block in `tests/test_copy.py` asserts all 96 admin constants are
non-empty, and asserts nothing about the content of any of them. Renaming
`FIGURE_COMPLETION_LABEL` back to `"Success rate"` left the whole 706-test suite
green. That label is the one string on this console carrying a correctness
requirement (PRD-006 Risk 4), so it was the one string with no test.

`tests/test_copy.py` was not touched. PRD-006 Section 15 lists it among the files
that must pass unmodified; STORY-008 read that as "no existing assertion
weakened" when it appended, and this story does not extend that reading further.
Two assertions here deliberately duplicate STORY-008's block — the non-empty
sweep and the single-refusal rule — written from the opposite angle (walk
`dir()` and check each member, rather than compare names against a literal set),
so this file still stands if that block is ever reverted to satisfy Section 15
literally.

Every assertion is a required or forbidden substring. Nothing compares against a
full label. A test that pinned the exact sentence would break on the next
legitimate wording tweak and be deleted the first time it did, which is the
failure mode the story exists to prevent.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Module docstring, path bootstrap, imports, `_public_constants()` helper | `tests/test_admin_copy.py` | ✅ |
| 2 | AC3 — every constant asserted non-empty, with a vacuity floor | `tests/test_admin_copy.py` | ✅ |
| 3 | AC1 — completion label states blocked rows are counted | `tests/test_admin_copy.py` | ✅ |
| 4 | AC2 — the answer-rate phrasings cannot come back | `tests/test_admin_copy.py` | ✅ |
| 5 | AC4 — both scope lines state their window | `tests/test_admin_copy.py` | ✅ |
| 6 | AC5 — exactly one refusal constant, naming no reason | `tests/test_admin_copy.py` | ✅ |
| 7 | AC6 — proof `tests/test_copy.py` is unmodified | — (verification) | ✅ |
| 8 | Falsification pass — four mutations, each run and reverted | — (verification) | ✅ |
| 9 | Full suite, report, story and index bookkeeping | `.agents/` | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| `tests/test_admin_copy.py` | ✅ 5 passed |
| `tests/test_copy.py` unmodified + green | ✅ 22 passed, `git status` clean on the file |
| `tests/test_summary.py` + `tests/test_admin_state.py` | ✅ 156 passed |
| Full suite | ✅ 711 passed (706 before, +5) |
| Falsification | ✅ 4/4 mutations failed the predicted tests |
| Nothing under `app/` or `chat_ui/` changed by this story | ✅ `git diff` empty on both |
| E2E | ✅ 7/7 (one item's expectation corrected — see Deviations) |

### Falsification pass (Task 8)

Each mutation applied to `chat_ui/chat_ui/admin_copy.py`, the suite run, then
reverted. `git status --porcelain chat_ui/` was empty at the end.

| Mutation | Predicted | Actual |
|----------|-----------|--------|
| `FIGURE_COMPLETION_LABEL = "Success rate"` | Tasks 3 + 4 fail | ✅ both failed |
| `FIGURE_COMPLETION_LABEL = "Completion rate"` | Task 4's split `"rate"` assertion fails | ✅ failed (and Task 3 too — a superset of the prediction) |
| `SUMMARY_SCOPE_ALL_TIME = "Summary"` | Task 5 fails | ✅ failed |
| add `GATE_REFUSED_MESSAGE_EMPTY` | Task 6 fails, Task 2's sweep still passes | ✅ exactly that |

The last row is the one worth keeping: the new constant is non-empty, so the
non-empty sweep passes it while the refusal rule catches it — the two tests
cover genuinely different failures rather than restating each other.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `tests/test_admin_copy.py` | CREATE | +222 |
| `tests/test_copy.py` | **UNCHANGED** | 0 |
| `chat_ui/chat_ui/admin_copy.py` | **UNCHANGED** | 0 |

No production code changed. This story adds tests over constants that already
said the right thing.

## Deviations from Plan

1. **Five tests, not six.** The plan's Summary and E2E list both said "six
   tests, one per AC", but its own task list only defines five test functions
   (Tasks 2–6) — AC6 is a git/suite verification (Task 7), not a pytest
   function. The task list was right and the count line was an off-by-one
   against it. All six ACs are covered.

2. **`git diff main --stat -- app/` is not empty — pre-existing, not from this
   story.** The plan's last E2E item expected it empty. It reports
   `app/db/database.py` and `app/db/models.py` as changed against `main`. The
   cause is commit `3f553f2` ("feat(chat-ui): implement PII column migration…",
   a different author, 2026-08-28), which predates every PRD-006 story on this
   branch and belongs to the PRD-003/PRD-004 era. No PRD-006 commit touches
   `app/`: `git log --oneline main..HEAD -- app/` returns that one commit and
   nothing else. This story changed nothing under `app/` — verified by
   `git diff --stat -- app/ chat_ui/` returning empty throughout.

   **This matters for STORY-020**, whose acceptance is "the proof that nothing
   under `app/` changed" and whose stated check is exactly this command. As
   written that check will fail on a pre-existing commit. STORY-020 will need
   either to scope its diff to PRD-006's own commit range, or to record
   `3f553f2` as a known, accepted exception. Flagged here rather than fixed:
   it is that story's call, and touching it now would mean editing history or
   `app/` on this branch.

3. **Two assertions added beyond the plan's letter**, both in Task 4, both
   cheap: the three sibling figure labels (`FIGURE_TOTAL_LABEL`,
   `FIGURE_BLOCKED_DUPLICATES_LABEL`, `FIGURE_BLOCKED_SUSPICIOUS_LABEL`) are
   also checked for `"success"`, since the regression could arrive under a
   different key rather than as a rename; and `_public_constants()` guards
   `isinstance(value, str)` before `.lower()`, as the plan's Risks table
   required.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_admin_copy.py` | `test_every_admin_copy_constant_is_non_empty` — all 96 constants are `str` and non-blank, with a `> 50` floor so an emptied `dir()` cannot pass vacuously |
| | `test_completion_label_states_that_blocked_rows_are_counted` — label carries "blocked" + "included"; the rendered note names both blocked verdicts and refuses the answer-rate reading |
| | `test_completion_label_cannot_regress_to_success_rate` — seven forbidden phrasings, a separate `"rate"` check so "Completion rate" cannot slip through, and a module-wide sweep against a second constant reviving `success_rate` |
| | `test_both_scope_lines_state_their_window` — register template names both placeholders and renders "100 most recent of 3,180"; summary states all-time; the prose note names both windows; the two cannot collapse into one |
| | `test_exactly_one_refusal_constant_exists` — exactly `["GATE_REFUSED_MESSAGE"]`, and eight reason-words forbidden inside it |

## Acceptance Criteria

- [x] `tests/test_admin_copy.py` asserts the completion label states that blocked
      rows are included in the count
- [x] The test fails if the wording becomes "success rate" or any phrasing that
      reads as an answer rate — proven by mutations 1 and 2 in Task 8
- [x] Every constant in `admin_copy.py` asserted non-empty, matching the existing
      `test_copy_constants_exist_and_not_empty` pattern
- [x] Both scope templates asserted to state their window (Risk 4)
- [x] Exactly one refusal constant exists; a second, more specific message fails
      the test — proven by mutation 4
- [x] The existing chat copy assertions in `tests/test_copy.py` pass unmodified —
      22 passed, file untouched in `git status`
- [x] All tasks completed
- [x] Each new test proven to fail against a mutated constant (Task 8)
- [x] `python -m pytest -q` green — 711 passed; nothing under `app/` or
      `chat_ui/` changed by this story
- [x] Follows existing patterns
