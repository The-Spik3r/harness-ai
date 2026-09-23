---
story: STORY-001
prd: PRD-011
plan: .agents/plans/PRD-011-pattern-policy/completed/STORY-001-pattern-detector-characterization.plan.md
epic_branch: epic/PRD-011-pattern-policy
commit: 29743aa
status: COMPLETE
completed: 2026-09-22
---

# Implementation Report — STORY-001: Characterize today's substring detector before anything moves

**Plan**: `.agents/plans/PRD-011-pattern-policy/completed/STORY-001-pattern-detector-characterization.plan.md`
**Epic Branch**: `epic/PRD-011-pattern-policy` (created at `9684829`, the PRD-010 tip)
**Commit**: `29743aa`

## Summary

Added `tests/test_pattern_characterization.py` and changed nothing else. It pins all nineteen of today's `detect_suspicious_pattern` verdicts as a module-level list of `(text, expected_pattern_or_None)` tuples, parametrized with readable ids, and publishes `PRD_011_FLIP_CASES` — the four inputs whose verdict PRD-011 intends to change, as `(text, today, after)` triples, each also carrying the inline `# PRD-011: flips to <verdict> in STORY-008` comment the story requires. Two meta-tests keep the two structures from drifting apart.

Running the corpus against the real detector corrected the PRD in two ways, both recorded in the module docstring so they reach STORY-008 and STORY-013. See *Deviations*.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 0 | Create the epic branch at `9684829` | — | ✅ |
| 1 | Start libSQL dev server; record baseline green | — | ✅ |
| 2 | Module docstring, prologue, case table, ids | `tests/test_pattern_characterization.py` | ✅ |
| 3 | The parametrized pins | `tests/test_pattern_characterization.py` | ✅ |
| 4 | `PRD_011_FLIP_CASES` and the two meta-tests | `tests/test_pattern_characterization.py` | ✅ |
| 5 | Prove nothing in production moved | — | ✅ (command corrected, see Deviations) |
| 6 | Full suite | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ |
| Frontend lint | N/A — no JS frontend; the UI is Reflex (Python) and this story touches no UI |
| New module | ✅ 21 passed |
| Baseline guardrail suites (before the change) | ✅ 38 passed |
| Full suite | ✅ 2276 passed, 26 skipped, 0 failed (223s) |
| E2E | ✅ 7/7 |
| Meta-test bite check | ✅ 3/3 — each guard raises on injected drift |

### E2E checklist

| # | Check | Result |
|---|-------|--------|
| 1 | `pytest tests/test_pattern_characterization.py -v` — 21 passed, ids readable | ✅ |
| 2 | `tests/test_pattern_detector.py` unchanged and green | ✅ 10 passed; byte-identical to `9684829` |
| 3 | `tests/test_query_outcomes_regression.py` untouched and green (AC 5) | ✅ 9 passed |
| 4 | `test_dedup_and_pattern_sources_unmodified_on_this_branch` green (AC 1) | ✅ 1 passed |
| 5 | `tests/test_pii_redaction_integration.py` layer-1 byte-pin green | ✅ 18 passed |
| 6 | `tests/test_integration.py` — every pattern still blocked before OpenRouter | ✅ 14 passed |
| 7 | `pytest tests/ -q` full suite green | ✅ |

### Meta-tests actually bite

A guard that can only pass is not a guard (`tests/test_untouched_app.py:36`). Each was checked against injected drift:

| Injected drift | Caught |
|---|---|
| Flip list names an input `_CASES` does not pin | ✅ `flip case is not pinned in _CASES: 'not in the table'` |
| Flip list row whose today and after verdicts are equal | ✅ `flip case does not actually flip: "what's the weather today?"` |
| A pattern added to `SUSPICIOUS_PATTERNS` with no covering case | ✅ `no case pins a verdict of 'brand new pattern'` |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `tests/test_pattern_characterization.py` | CREATE | +194 |

No production file. `git diff --name-only 9684829 -- app/` is empty.

Committed alongside, not part of the story's code: the archived plan (+432). The epic charter — `PRD.md`, `index.md` and all thirteen story files — landed as its own prior commit `a603db0`, so `index.md` would not reference untracked files.

## Deviations from Plan

### D-1 — Task 5's baseline command was wrong; corrected in place

The plan's Task 5 validated "no production file moved" with `git diff --name-only $(git merge-base main HEAD) -- app/`. On this branch `merge-base main HEAD` resolves to `51e794f`, so the command reported all eleven files PRD-010 changed under `app/`. It answers "what changed since `main`", never "what did this story change" — precisely the defect `tests/test_untouched_app.py:9-36` records as the reason four such guards were retired in PRD-008 STORY-023. I wrote the flawed form into the plan and it failed on first use.

Corrected to `git diff --name-only 9684829 -- app/` (the epic branch point), which is empty. The plan file carries the correction and the reasoning at Task 5.

The existing guardrail test is unaffected and stays meaningful: its predicate names only `app/services/pattern_detector.py`, which PRD-010 never touched, so `merge-base` is a valid baseline *for that one path*. Verified green.

### D-2 — The PRD's `overridden` / `overriding` claim is false (found by running the corpus)

PRD Sections 1, 6.2 and 11 and threat T3 state that `override` matches `overridden` today; T3 and Section 11 build the release criterion on it. It does not match, and neither does `overriding`:

```
overrides  -> True
overridden -> False
overriding -> False
```

`override` is `o-v-e-r-r-i-d-e`; `overridden` is `o-v-e-r-r-i-d-d-e-n` and `overriding` is `o-v-e-r-r-i-d-i-n-g`. The `e` is dropped in both, so neither contains the substring. Only `overrides` does.

Both are pinned as clean today **and** clean after, and neither appears in `PRD_011_FLIP_CASES`. **STORY-008 must not expect them to flip. STORY-013 must not republish the claim in the README.** Recorded in the module docstring, which is where the implementer of each will be reading.

The PRD prose is **not** corrected — this story's scope is one new test file. Correcting Sections 1, 6.2, 11 and T3 is outstanding work; it belongs either to a small docs edit or to STORY-013.

### D-3 — Two flips run the opposite direction from the PRD's criterion

PRD Section 11 frames the criterion as though every flip runs from blocked to clean ("except where today's verdict came from a substring match that is not a whole word"). Word matching joins a phrase's tokens with `\s+` (Section 6.2, F1), so two inputs that are clean today become blocks:

| Input | Today | After |
|---|---|---|
| `please ignore previous\ninstructions now` | `None` | `ignore previous instructions` |
| `please ignore  previous instructions now` | `None` | `ignore previous instructions` |

The newline case is required by the story's AC 2 explicitly. The doubled-space case is an **addition beyond the story's enumeration**, justified by Section 11's own functional requirement that the phrase match "across a newline and across doubled spaces" — same mechanism, and leaving it unpinned would let STORY-008 land it unobserved.

Net flip set: **four rows in two directions**, not three in one.

### D-4 — One flip row is predicted, not observed

`fenced-at-override` pins `override` today and is listed as flipping to `None`, on the strength of the built-in `keywords` list carrying `scope: outside_code` per PRD Section 6.3. That policy does not exist until STORY-005. The row carries a comment naming the dependency and the remedy: if STORY-005 declares the list `everywhere` instead, the row leaves `PRD_011_FLIP_CASES` with a citing comment and stays in `_CASES`.

### D-5 — Epic branch based on the PRD-010 tip, not `main`

`implement.md` Phase 2.2 and the PRD frontmatter both say `base_branch: main`. The branch was created from `epic/PRD-010-multi-turn-pipeline` @ `9684829` after asking. `main` is at `51e794f` and does not contain PRD-010, which is 18/18 done and which STORY-005, STORY-006 and STORY-008 import (`Message`, `Role`, `run_conversation`). `9684829` is also the commit the PRD's Evidence section was verified against. The frontmatter's `base_branch: main` becomes correct once PRD-010 merges there.

### D-6 — Three commits, not one

`implement.md` asks for one commit per story. The epic charter (`PRD.md`, `index.md`, thirteen story files) had never been committed by `/create-prd` or `/create-stories`, and leaving it untracked would have left `index.md` referencing twelve untracked files and invited a later `git add -A` to sweep them into an unrelated story. It landed as `a603db0` first. The story itself is one commit, `29743aa`, as required; the status/report chore follows it, matching the rhythm of PRD-010's own history (e.g. `9684829`, `b910f8e`).

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_pattern_characterization.py` | `test_todays_verdict` × 19 (ids: `pattern-ignore-previous-instructions`, `pattern-forget-everything`, `pattern-show-system-prompt`, `pattern-reveal-password`, `pattern-execute-code`, `pattern-admin-mode`, `pattern-override`, `suffix-overridden`, `suffix-overrides`, `suffix-overriding`, `java-at-override`, `csharp-public-override-void`, `kotlin-override-fun`, `mixed-case`, `newline-between-words`, `doubled-space-between-words`, `clean-prompt`, `list-order-precedence`, `fenced-at-override`); `test_every_flip_case_is_a_pinned_case`; `test_every_suspicious_pattern_is_covered` |

### The flip set STORY-008 inherits

| id | text | today | after (`chat`) |
|---|---|---|---|
| `suffix-overrides` | `this method overrides the base implementation` | `override` | `None` |
| `newline-between-words` | `please ignore previous\ninstructions now` | `None` | `ignore previous instructions` |
| `doubled-space-between-words` | `please ignore  previous instructions now` | `None` | `ignore previous instructions` |
| `fenced-at-override` | `Here is the diff:\n```java\n@Override\n…\n```\n` | `override` | `None` (predicted, D-4) |

Everything else in `_CASES` must keep its verdict — including `java-at-override`, `csharp-public-override-void` and `kotlin-override-fun`, which still match under the default `chat` profile because word boundaries do not fix `@Override` (PRD Section 6.2) and `chat` loads the keyword list.

## Acceptance Criteria

- [x] Given untouched `app/services/pattern_detector.py`, when `tests/test_pattern_characterization.py` runs, then it is green with no production file modified in this commit. — 21 passed; `git diff --name-only 9684829 -- app/` empty; `test_dedup_and_pattern_sources_unmodified_on_this_branch` green
- [x] Given the characterization corpus, when each case runs through `detect_suspicious_pattern`, then every one of the seven `SUSPICIOUS_PATTERNS` is covered, plus `overridden`, `overrides`, `overriding`, `@Override`, `public override void`, `override fun`, mixed case, a match spanning a newline (asserted **not** matched today), and a clean prompt. — all present; coverage of the seven enforced by `test_every_suspicious_pattern_is_covered`, which iterates the constant and asserts nothing structural
- [x] Given a case whose today-verdict this PRD intends to change, when it is written, then it carries a `# PRD-011: flips to <verdict> in STORY-008` comment naming the new verdict, and those cases are collected in one module-level list so STORY-008 can assert the flipped set is exactly this set and no larger. — `PRD_011_FLIP_CASES`, four rows, each with its inline comment; `test_every_flip_case_is_a_pinned_case` prevents drift
- [x] Given `test_first_matching_pattern_returned_when_multiple_present`, when the list-order precedence rule is characterized, then it is restated here as its own case. — `list-order-precedence`, with a comment recording why the verdict survives the rewrite (PRD Sections 6.3, 7 F5)
- [x] Given `/query`, when a prompt from the corpus that is blocked today is sent, then the regression in `tests/test_query_outcomes_regression.py` is untouched and still green. — 9 passed, file byte-identical. (The story says "six-outcome"; the file now holds seven outcomes plus a PRD-010 characterization block. The requirement — no assertion changed — is met either way.)
- [x] All tasks completed
- [x] Full suite green — 2276 passed, 26 skipped
- [x] Exactly one file added; `git diff --name-only 9684829 -- app/` is empty
- [x] Follows existing patterns — `tests/test_duplicate_characterization.py` docstring form, `tests/test_pattern_detector.py` prologue, `tests/test_chat_outcomes_regression.py` table + completeness meta-test

## Notes for the Stories That Follow

- **STORY-008** imports `PRD_011_FLIP_CASES` and asserts the flipped set is exactly its four texts. Read D-2 before writing that assertion: `overridden` and `overriding` are not flips, whatever the PRD says.
- **STORY-008** also rewrites `tests/test_pattern_detector.py`, which is in `_PRE_EPIC_UNTOUCHED_TESTS` (layer 1, byte-unmodified) at `tests/test_pii_redaction_integration.py:279-283`. It must move out of layer 1 with a citing comment and rely on layer 2's `test_no_pre_epic_test_function_was_removed_or_renamed` — the treatment PRD-010 STORY-003 gave `tests/test_openrouter_client.py`, documented at `:271-278`.
- **STORY-005** owns whether `fenced-at-override` really flips (D-4).
- **STORY-013** must not republish the `overridden` claim in the README (D-2).
- The PRD prose corrections from D-2 and D-3 are still outstanding.
