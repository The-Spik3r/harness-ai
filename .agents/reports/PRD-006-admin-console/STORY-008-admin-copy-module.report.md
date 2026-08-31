---
story: STORY-008
prd: PRD-006
plan: .agents/plans/PRD-006-admin-console/completed/STORY-008-admin-copy-module.plan.md
epic_branch: epic/PRD-006-admin-console
commit: pending
status: COMPLETE
completed: 2026-08-30
---

# Implementation Report — STORY-008: `admin_copy.py`, every admin-facing string in one module

**Plan**: `.agents/plans/PRD-006-admin-console/completed/STORY-008-admin-copy-module.plan.md`
**Epic Branch**: `epic/PRD-006-admin-console`
**Commit**: `pending`

## Summary

`chat_ui/chat_ui/admin_copy.py` now holds the console's entire vocabulary — 91 constants across twelve surface groups — written before any admin component exists, so the eight stories blocked on this one (009, 011 … 017) each start with their words already named. The module is modelled on `copy.py`: flat constants, grouped under banner comments, every string carrying a value defined as a `_TEMPLATE` rather than concatenated at a call site.

It imports **nothing at all**, and that is deliberate rather than incidental. Three words are shared with the chat — the `HARNESS` wordmark, the `" · "` separator and `"Matched pattern"` — and all three are re-declared here instead of imported from `copy.py`, because PRD-006 Section 4 requires that no admin module reach into a chat module and a shared constant is the first thread of exactly that coupling.

The second half of the story was a move `admin_state.py`'s own comments had been asking for since STORY-003: `GATE_REFUSED_MESSAGE`, `LOAD_FAILED_MESSAGE` and the ten fault labels spelled inline in `_READS` now live in `admin_copy` and reach `admin_state` as a re-export. The refusal keeps its name, the fault template is aliased back to `LOAD_FAILED_MESSAGE` at the import so `load()`'s call site is untouched, and the ten label values are byte-identical — `tests/test_admin_state.py` passes **unmodified**, including the three tests that compare against those labels as literals.

Two absences in the module are as load-bearing as anything in it. There is no sign-out notice (PRD-006 Section 6.1: sign-out returns the gate, and the gate reappearing *is* the confirmation), and there is exactly one refusal message (Section 9's no-oracle rule). Both absences are asserted, not merely commented.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Create the copy module — 12 groups, 91 constants, zero imports | `chat_ui/chat_ui/admin_copy.py` | ✅ |
| 2 | Move the gate refusal out of the state, as a re-export | `chat_ui/chat_ui/admin_state.py` | ✅ |
| 3 | Move the fault template and the ten read labels | `chat_ui/chat_ui/admin_state.py` | ✅ |
| 4 | Extend the copy test, strictly append-only | `tests/test_copy.py` | ✅ |
| 5 | Prove the chat surface and `app/` untouched | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| `admin_copy` imports clean, zero imports of its own, no `rx.` | ✅ |
| `tests/test_copy.py` | ✅ 21 passed (17 existing + 4 new) |
| `tests/test_admin_state.py` **unmodified** | ✅ 61 passed |
| Full suite | ✅ 378 passed |
| `app/` untouched since the PRD-006 baseline | ✅ empty diff |
| Chat surface (`copy.py`, `state.py`, `components/`) untouched | ✅ empty diff |
| E2E | ✅ 8/8 |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `chat_ui/chat_ui/admin_copy.py` | CREATE | +289 |
| `chat_ui/chat_ui/admin_state.py` | UPDATE | +42/-29 |
| `tests/test_copy.py` | UPDATE | +358/-0 |

`tests/test_copy.py` shows **zero deletions**, which is the append-only guarantee stated as a number rather than as an intention.

## Deviations from Plan

**1. `git diff main -- app/` is the wrong baseline on this repo, and the plan (like STORY-007's before it) specified it.**
`main` predates PRD-004's merge, so that command reports `app/db/database.py` and `app/db/models.py` as changed — work from PRD-003/004 that is already on the branch and has nothing to do with PRD-006. The check was re-run against the true PRD-006 baseline, `d3e6279` (the parent of STORY-001's commit `577a285`), where `app/` and the whole chat surface both show an empty diff. **This affects every remaining PRD-006 story**: Section 11's quality indicator "`git diff main --stat` shows no file under `app/` changed" cannot be satisfied literally until the epic merges, and the honest form of the check is `git diff d3e6279 -- app/`. Recorded here so STORY-020's regression pass uses the baseline that actually answers the question.

**2. The exhaustive non-empty test is generated-then-checked-in, and carries a completeness assertion the plan did not specify.**
Task 4 asked for "a flat `assert CONSTANT` per constant". All 91 are written out explicitly, matching `test_copy_constants_exist_and_not_empty`'s shape — but a hand-maintained list of 91 names silently rots as later stories add constants, so the test closes with `declared == asserted` over `dir(admin_copy)`. A constant added by STORY-009 or STORY-015 without an assertion now fails the suite instead of shipping untested. This is stricter than the plan, in the direction the AC intends.

**3. `tests/test_copy.py` gained one import line above the appended block.**
`from chat_ui.chat_ui import admin_copy` sits beside the by-name import, because three of the four new tests scan the module's namespace (for a second refusal message, for a stray "session ended", for coverage) and cannot do that through imported names alone. It is an addition in the import region rather than strictly at the end of the file; no existing line was touched.

**4. No component was de-literalized, because none exists.**
AC 2's grep — "given any admin component, when it is grepped for quoted user-facing text, then none is found" — passes vacuously today: the three admin modules on disk are state, models and formatting, and none renders. The module was written to over-cover deliberately (STORY-012's disclosure labels and STORY-015's nine figure labels are already here) so that the components landing later find their words rather than inline them. The AC becomes a real check at STORY-018.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_copy.py` (appended) | `test_admin_copy_constants_exist_and_not_empty` — all 91 constants non-empty, plus `declared == asserted` so the list cannot fall behind the module |
| | `test_admin_copy_templates_carry_their_placeholders` — every `_TEMPLATE` formats without `KeyError`; AC 3's two named cases pinned to their exact output (`100 most recent of 3,180`, `Refreshed 14:22:07`) |
| | `test_refresh_keeps_one_verb_across_the_flow` — `Refresh` / `Refreshing` / `Refreshed {time}` share a stem, the fault message carries the same verb, and no constant anywhere in the module contains "session ended" (AC 4) |
| | `test_admin_copy_states_one_refusal_and_says_nothing_about_why` — `GATE_REFUSED_MESSAGE` is the *only* constant in the module whose text contains "refus", and it names none of empty / invalid / incorrect / wrong / length / expired / format (AC 5, PRD-006 Section 9) |

The refusal test is the one worth calling out: it does not assert a sentence, it asserts that a **second** refusal message cannot exist. Adding a more helpful "Token must be 32 characters" beside it fails the suite, which is the oracle Section 9 forbids caught by a test rather than by a reviewer.

## Acceptance Criteria

- [x] Given `chat_ui/chat_ui/admin_copy.py`, when it is created, then it holds every admin-facing string: the masthead, the two view-switch labels, the sign-out label, the gate prompt and its single refusal message, the column heads, the four verdict labels, the scope lines, the refresh label and refreshed stamp template, the fault panel, and the three empty states.
- [x] Given any admin component, when it is grepped for quoted user-facing text, then none is found — every string resolves through `admin_copy`. *(Vacuous today — no admin component exists; see Deviation 4. The three existing admin modules were checked and hold no user-facing literal: `admin_state.py`'s last two were moved out by Tasks 2–3, and `admin_formatting.py`'s remaining strings are the absence marks and a timestamp format, which are values rather than copy.)*
- [x] Given a label with a value in it, when it is defined, then it is a template constant rather than string concatenation at the call site — including "100 most recent of {total}" and "Refreshed {time}". *(Ten `_TEMPLATE` constants; both named cases pinned to their exact rendered output in a test.)*
- [x] Given the refresh control and the post-refresh line, when both are read, then they share the same verb — **Refresh** produces **Refreshed 14:22:07**, and **Sign out** returns the gate rather than a "session ended" notice.
- [x] Given the gate refusal string, when it is read, then it states that access was refused and does not say why — one message for empty, malformed and wrong tokens alike.
- [x] Given `admin_copy.py`, when `tests/test_copy.py` is extended, then each constant is asserted non-empty, matching the existing test's pattern.
- [x] All tasks completed
- [x] `tests/test_admin_state.py` passes unmodified (61 passed)
- [x] `app/` untouched *(against the PRD-006 baseline `d3e6279`; see Deviation 1)*
- [x] Follows existing patterns — `copy.py`'s grouping, naming and `_TEMPLATE` conventions
