---
story: STORY-016
prd: PRD-006
slug: completion-label-copy-test
title: "Copy test pinning the completion label so it cannot regress to \"success rate\""
type: REFACTOR
complexity: LOW
epic_branch: epic/PRD-006-admin-console
created: 2026-08-31
---

# Plan: Copy test pinning the completion label so it cannot regress to "success rate"

## Summary

STORY-008 wrote `FIGURE_COMPLETION_LABEL = "Completed without error (blocked
queries included)"` and appended a block of admin assertions to
`tests/test_copy.py`. What exists there today asserts every admin constant is
**non-empty** — it does not assert a single word of the completion label's
*content*, so the one label on this console with a correctness requirement is
currently pinned by nothing. A rename back to `"Success rate"` would keep the
whole suite green. This story closes that gap.

The work is one new file, `tests/test_admin_copy.py`, holding the assertions
Risk 4 and Section 12 Phase 3 name: the completion label states that blocked rows
are counted, the forbidden phrasings cannot appear, both scope lines state their
window, and exactly one refusal constant exists. `tests/test_copy.py` is **not
touched** — PRD-006 Section 15 lists it among the files that must pass
unmodified, and the story's Technical Notes offer the sibling file precisely so
that constraint stays literal from here on.

Assertions are on **substance, not sentences**: the label must contain the
blocked-inclusive qualifier and must not contain the answer-rate phrasings. A
test that pinned the exact string would fail on every legitimate wording tweak
and would be deleted the first time it did, which is the failure mode the story
exists to prevent.

Two assertions deliberately overlap `tests/test_copy.py` — the exhaustive
non-empty sweep (AC3) and the single-refusal rule (AC5). The overlap is the
point: the new file must stand on its own if the appended block in
`tests/test_copy.py` is ever reverted to satisfy Section 15's "unmodified"
literally. The sweep is written differently here — it iterates `dir(admin_copy)`
rather than restating the 95-name literal set — so the two are complementary
rather than copy-pasted: `test_copy.py` proves the *set* of constants is closed,
this file proves *each* one carries text.

## User Story

As an integrating developer
I want the completion figure's wording asserted in a test
So that the one label on the console with a correctness requirement cannot drift
back to a name that misstates what it counts

## Story Reference

- Story file: `.agents/stories/PRD-006-admin-console/STORY-016-completion-label-copy-test.md`
- PRD: `.agents/PRDs/PRD-006-admin-console/PRD.md` — Section 11, Section 12 Phase 3 validation, Risk 4, Section 9, Section 15

## Metadata

| Field | Value |
|-------|-------|
| Type | technical (REFACTOR — test-only, no production code changes) |
| Complexity | LOW |
| Systems Affected | `tests/` only — nothing under `app/`, nothing under `chat_ui/` |
| Story | STORY-016 |
| PRD | PRD-006 |
| Epic Branch | `epic/PRD-006-admin-console` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | `skills: []` in the story frontmatter. `.agents/skills/` holds one skill, **frontend-design**, whose description covers "distinctive, intentional visual design when building new UI or reshaping an existing one". This story writes no UI and changes no rendered output — it is a pytest module over string constants — so no skill rule binds any task below. Scanned and found not applicable, rather than skipped. | none |

The PRD's own "Skills referenced" line names frontend-design, reflex-docs and
reflex-process-management for the epic as a whole; none is engaged by a
test-only story that never starts the app.

---

## Patterns to Follow

### Naming — the module reaches its target by repo-root path

```python
# SOURCE: tests/test_copy.py:1-4, 30-33
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from chat_ui.chat_ui import admin_copy
from chat_ui.chat_ui.admin_copy import (
    FIGURE_COMPLETION_LABEL,
    ...
)
```

Both forms are used on purpose in the existing file and both are needed here:
the named imports fail at **collection** if a constant is deleted or renamed,
while the module handle is what a `dir()` sweep needs. `tests/test_summary.py`
takes the same `sys.path.insert(0, parents[1])` route.

### Assertion style — substance, with the reason in the docstring

```python
# SOURCE: tests/test_copy.py:196-200
def test_risk_5_pii_exchange_phrasing():
    """AC3 / Risk 5: PII badge copy explicitly states masking applies to the exchange, not prompt alone."""
    assert "masked in this exchange" in PII_BADGE_TEMPLATE
    formatted = PII_BADGE_TEMPLATE.format(count=2, entities="PERSON, EMAIL_ADDRESS")
    assert "exchange" in formatted
    assert "prompt" not in formatted
```

The house pattern for exactly this job: a required substring, then a forbidden
substring, with the docstring naming the AC and the risk.
`test_risk_4_duplicate_change_notice` (`tests/test_copy.py:203-207`) is the
lowercased-comparison variant.

### Forbidden-word sweeps over the whole module

```python
# SOURCE: tests/test_copy.py:583-591
    refusals = [
        name
        for name in dir(admin_copy)
        if name.isupper() and "refus" in getattr(admin_copy, name).lower()
    ]
    assert refusals == ["GATE_REFUSED_MESSAGE"]

    forbidden = ("empty", "invalid", "incorrect", "wrong", "length", "expired", "format")
    assert not [word for word in forbidden if word in GATE_REFUSED_MESSAGE.lower()]
```

The existing shape for "no second constant may be added" and for a forbidden-word
list. Note the `dir()` comprehension calls `.lower()` unguarded — every public
uppercase name in `admin_copy` is a `str` today. The sweeps below guard with
`isinstance(value, str)` anyway, so a future tuple or int constant fails on its
own assertion rather than raising `AttributeError` inside an unrelated test.

### Template assertions format rather than eyeball

```python
# SOURCE: tests/test_copy.py:526-529
    assert REGISTER_SCOPE_TEMPLATE.format(shown=100, total="3,180") == (
        "100 most recent of 3,180"
    )
```

AC4's register half is already asserted this way at `tests/test_copy.py:526`;
what is missing is that the *rendered* sentence states a window. The new
assertion formats the template and checks the window words survive, which is the
claim Risk 4 actually makes.

---

## The gap this story closes (evidence)

| Claim | Where it stands today |
|-------|----------------------|
| Completion label non-empty | `tests/test_copy.py:322` — `assert FIGURE_COMPLETION_LABEL` |
| Completion label *says* blocked rows count | **nowhere** |
| "success rate" cannot come back | **nowhere** |
| Completion note reaches the screen | `tests/test_summary.py:315` — asserts the **note**, not the label |
| Label is the one `AdminState` builds | `tests/test_admin_state.py:1797` — `assert figure.label == FIGURE_COMPLETION_LABEL` (an identity check: it holds whatever the constant says, including "Success rate") |
| Register scope template formats | `tests/test_copy.py:526` — exact-string equality, no window claim |
| Summary all-time scope states its window | **nowhere** |
| Exactly one refusal constant | `tests/test_copy.py:583` (STORY-008) |

The three **nowhere** rows are AC1, AC2 and AC4's summary half. Everything else is
either already covered or covered by a check that a rename would pass.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `tests/test_admin_copy.py` | CREATE | The whole story. Six tests, one per AC. |
| `tests/test_copy.py` | **UNCHANGED** | Section 15 requires it to pass unmodified; AC6 asserts it does. Listed here so `/implement` does not "helpfully" extend it. |
| `chat_ui/chat_ui/admin_copy.py` | **UNCHANGED** | The constants already say the right thing. This story pins them; it does not rewrite them. |

No production file changes. `git diff main --stat` must continue to show nothing
under `app/`.

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Create the module header, path bootstrap and imports

- **File**: `tests/test_admin_copy.py`
- **Action**: CREATE
- **Implement**:
  - Module docstring stating what the file is for and, explicitly, **why it is
    not in `tests/test_copy.py`**: PRD-006 Section 15 lists `tests/test_copy.py`
    among the tests that must pass unmodified, so STORY-016's assertions land in
    a sibling. Note the deliberate overlap with STORY-008's appended block and
    the reason (this file must stand alone if that block is ever reverted).
  - `import sys`, `from pathlib import Path`,
    `sys.path.insert(0, str(Path(__file__).parent.parent))`.
  - `from chat_ui.chat_ui import admin_copy` for the sweeps.
  - Named imports for the constants asserted individually:
    `FIGURE_COMPLETION_LABEL`, `FIGURE_COMPLETION_NOTE`, `FIGURE_TOTAL_LABEL`,
    `FIGURE_BLOCKED_DUPLICATES_LABEL`, `FIGURE_BLOCKED_SUSPICIOUS_LABEL`,
    `REGISTER_SCOPE_TEMPLATE`, `SUMMARY_SCOPE_ALL_TIME`, `SUMMARY_SCOPE_NOTE`,
    `GATE_REFUSED_MESSAGE`. A rename breaks collection, which is the point.
  - A module-level helper used by three tests:
    ```python
    def _public_constants():
        """Every public uppercase name in admin_copy, as (name, value) pairs."""
        return [
            (name, getattr(admin_copy, name))
            for name in dir(admin_copy)
            if name.isupper() and not name.startswith("_")
        ]
    ```
- **Mirror**: `tests/test_copy.py:1-4` (path bootstrap), `tests/test_copy.py:30-33`
  (the module handle imported alongside the named constants, with STORY-008's
  comment explaining why both)
- **Validate**: `python -m pytest tests/test_admin_copy.py -q` — collects, 0 tests

### Task 2: AC3 — every constant asserted non-empty

- **File**: `tests/test_admin_copy.py`
- **Action**: UPDATE
- **Implement**: `test_every_admin_copy_constant_is_non_empty()`.
  - Iterate `_public_constants()`; for each, assert `isinstance(value, str)` and
    `value.strip()`, with the failing name in the assertion message
    (`assert value.strip(), f"{name} is empty"`).
  - Assert the sweep found something — `assert len(_public_constants()) > 50` —
    so a future import error that empties `dir()` cannot make this test vacuously
    pass.
  - Docstring: AC3, and the division of labour with
    `test_admin_copy_constants_exist_and_not_empty` at `tests/test_copy.py:311`
    — that one proves the *set* is closed against its literal list, this one
    proves *each* member carries text without restating 95 names.
- **Mirror**: `tests/test_copy.py:311-323` (the pattern AC3 names),
  `tests/test_copy.py:583-588` (the `dir()` comprehension shape)
- **Validate**: `python -m pytest tests/test_admin_copy.py -q -k non_empty`

### Task 3: AC1 — the completion label states blocked rows are counted

- **File**: `tests/test_admin_copy.py`
- **Action**: UPDATE
- **Implement**: `test_completion_label_states_that_blocked_rows_are_counted()`.
  - `label = FIGURE_COMPLETION_LABEL.lower()`
  - `assert "blocked" in label` and `assert "included" in label` — the qualifier,
    not the sentence. Present wording: `"Completed without error (blocked queries
    included)"`.
  - Assert the label names what it *does* count:
    `assert "completed" in label or "without error" in label`.
  - Assert `FIGURE_COMPLETION_NOTE` carries the same correction in prose — it is
    the line rendered beneath the figure
    (`chat_ui/chat_ui/components/summary.py:391`) and is the sentence a reader
    actually acts on: `note = FIGURE_COMPLETION_NOTE.lower()`;
    `assert "not an answer rate" in note`;
    `assert "held" in note and "denied" in note` (both blocked verdicts are named
    as counting).
  - Docstring quotes PRD Section 4's requirement verbatim: "labeled for what it
    counts — rows the pipeline completed without raising, blocked rows included —
    not as an answer rate."
- **Mirror**: `tests/test_copy.py:196-200` (`test_risk_5_pii_exchange_phrasing`)
- **Validate**: `python -m pytest tests/test_admin_copy.py -q -k completion`

### Task 4: AC2 — the answer-rate phrasings cannot come back

- **File**: `tests/test_admin_copy.py`
- **Action**: UPDATE
- **Implement**: `test_completion_label_cannot_regress_to_success_rate()`.
  - On the label, a forbidden-word tuple with the reason in a comment:
    `("success", "success rate", "success_rate", "answer rate", "succeeded",
    "successful", "% success")`. Assert
    `not [w for w in forbidden if w in FIGURE_COMPLETION_LABEL.lower()]`, with
    the offending words in the message.
  - Assert `"rate" not in FIGURE_COMPLETION_LABEL.lower()` separately, with a
    comment: any *rate* in a completion label reads as an answer rate regardless
    of the noun in front of it. Kept separate from the tuple so the failure
    message distinguishes "you wrote success" from "you wrote a rate".
  - Module-wide guard: over `_public_constants()`, assert no constant contains
    `"success rate"` or `"success_rate"` — a second constant carrying the old
    name is the other way this regresses. Scoped to `admin_copy` deliberately:
    `app/schemas.py` owns a legitimate `success_rate` field, and PRD-006 does not
    touch `app/`.
  - Note in the docstring what is **not** claimed: this pins the *label*, not the
    *computation*. `count_successful_queries()` still counts blocked rows;
    PRD-006 Section 13 defers the truthful metric. The test's job is that the
    console never again narrates the wrong number with the wrong name.
  - Docstring quotes Risk 4's mitigation verbatim.
- **Mirror**: `tests/test_copy.py:589-591` (the forbidden-word list),
  `tests/test_copy.py:583-588` (the module-wide sweep)
- **Validate**: `python -m pytest tests/test_admin_copy.py -q -k regress`

### Task 5: AC4 — both scope lines state their window

- **File**: `tests/test_admin_copy.py`
- **Action**: UPDATE
- **Implement**: `test_both_scope_lines_state_their_window()`.
  - Register half:
    `scope = REGISTER_SCOPE_TEMPLATE.format(shown=100, total="3,180")`; assert
    `"100" in scope and "3,180" in scope` (the window *and* the true total, which
    is the pairing Risk 4 asks for) and `"most recent" in scope.lower()`. Assert
    both placeholders are named — `"{shown}" in REGISTER_SCOPE_TEMPLATE` and
    `"{total}" in REGISTER_SCOPE_TEMPLATE` — so the cap cannot be hardcoded back
    to a literal 100 that a changed `REGISTER_ROW_LIMIT` would falsify.
  - Summary half: `assert "all time" in SUMMARY_SCOPE_ALL_TIME.lower()`; assert
    it claims the whole record —
    `assert "every" in SUMMARY_SCOPE_ALL_TIME.lower() or "all rows" in ...`.
  - `SUMMARY_SCOPE_NOTE` is the line that resolves the two windows against each
    other, so assert it names both sides: `"whole table" in note` and
    `"most recent" in note`.
  - Assert the two scope strings are different constants and different text —
    `assert SUMMARY_SCOPE_ALL_TIME != REGISTER_SCOPE_TEMPLATE` — the collapse
    Risk 4 warns about is one scope line doing both jobs.
  - Docstring: Risk 4's first clause, "all-time figures beside a 100-row window
    invite a wrong reading".
- **Mirror**: `tests/test_copy.py:526-529` (template formatted, then asserted)
- **Validate**: `python -m pytest tests/test_admin_copy.py -q -k scope`

### Task 6: AC5 — exactly one refusal constant, and it names no reason

- **File**: `tests/test_admin_copy.py`
- **Action**: UPDATE
- **Implement**: `test_exactly_one_refusal_constant_exists()`.
  - Over `_public_constants()`, collect names whose value contains `"refus"`;
    assert the list is exactly `["GATE_REFUSED_MESSAGE"]`.
  - Assert the message says access was refused and not why: forbidden tuple
    `("empty", "invalid", "incorrect", "wrong", "length", "expired", "format",
    "try again with")`.
  - Docstring quotes Section 9 verbatim: "an empty, malformed or wrong token
    produces the same message. The gate reports that access was refused, not
    why", and states plainly that this duplicates
    `test_admin_copy_states_one_refusal_and_says_nothing_about_why`
    (`tests/test_copy.py:576`) on purpose — AC5 requires *this* file to enforce
    it, and the no-oracle rule is a security property that should not depend on
    a file Section 15 may force back to its pre-STORY-008 state.
- **Mirror**: `tests/test_copy.py:576-591` — the same assertion, restated so this
  file stands alone
- **Validate**: `python -m pytest tests/test_admin_copy.py -q -k refusal`

### Task 7: AC6 — prove `tests/test_copy.py` was not touched

- **File**: none (verification task)
- **Action**: VERIFY
- **Implement**:
  - `git status --porcelain tests/` must list `?? tests/test_admin_copy.py` and
    **nothing else**. Any ` M tests/test_copy.py` means the story's central
    constraint was broken — revert it and move the assertion into the new file.
  - `git diff --stat` must show no change under `app/` or `chat_ui/`.
  - Run `python -m pytest tests/test_copy.py -q` — 22 passed, the count on the
    branch before this story.
- **Mirror**: PRD-006 Section 15's "Tests that must pass unmodified" list, which
  names `tests/test_copy.py`
- **Validate**:
  ```bash
  git status --porcelain tests/
  git diff --stat -- app/ chat_ui/
  python -m pytest tests/test_copy.py -q
  ```

### Task 8: Falsification pass — prove each new test can fail

- **File**: none (verification task; no committed change)
- **Action**: VERIFY
- **Implement**: A copy test that cannot fail is decoration. Temporarily edit
  `chat_ui/chat_ui/admin_copy.py` in the working tree, run the suite, confirm the
  expected test fails, then `git checkout -- chat_ui/chat_ui/admin_copy.py`.
  Four mutations, each run and reverted **one at a time**:
  1. `FIGURE_COMPLETION_LABEL = "Success rate"` → Task 3's and Task 4's tests both
     fail. This is the exact regression the story names.
  2. `FIGURE_COMPLETION_LABEL = "Completion rate"` → Task 4's separate `"rate"`
     assertion fails (the tuple alone would let this through — this is why the
     assertion is split).
  3. `SUMMARY_SCOPE_ALL_TIME = "Summary"` → Task 5 fails.
  4. Add `GATE_REFUSED_MESSAGE_EMPTY = "The token was refused: it was empty."` →
     Task 6 fails, and Task 2's sweep still passes (it is non-empty), confirming
     the two tests cover different failures.

  Confirm `git status --porcelain chat_ui/` is clean after each revert.
- **Mirror**: n/a — this is a one-off proof, not a committed artifact
- **Validate**: `git status --porcelain chat_ui/` empty at the end, and
  `python -m pytest -q` green

### Task 9: Full suite and story bookkeeping

- **File**: `.agents/stories/PRD-006-admin-console/STORY-016-completion-label-copy-test.md`
- **Action**: UPDATE (after implementation, per the epic's convention)
- **Implement**: run the whole suite; then record the commit SHA in the story's
  `commit:` field, write the report, and update
  `.agents/PRDs/PRD-006-admin-console/index.md` to `✅ done` — the same closing
  step every completed story on this epic took (see the last three commits on
  `epic/PRD-006-admin-console`).
- **Validate**: `python -m pytest -q` — whole suite green

---

## End-to-End Tests

- [ ] `python -m pytest tests/test_admin_copy.py -q` — six tests, all pass
- [ ] `python -m pytest tests/test_copy.py -q` — 22 passed, file unmodified
- [ ] `python -m pytest tests/test_summary.py tests/test_admin_state.py -q` — the
      two suites that also touch the completion constants stay green
- [ ] `python -m pytest -q` — whole suite green
- [ ] Falsification: `FIGURE_COMPLETION_LABEL = "Success rate"` makes
      `tests/test_admin_copy.py` fail, and reverting makes it pass again
- [ ] `git status --porcelain` shows one new file under `tests/` and nothing else
- [ ] `git diff main --stat -- app/` is empty

---

## Validation

```bash
python -m pytest tests/test_admin_copy.py -q
python -m pytest tests/test_copy.py tests/test_summary.py tests/test_admin_state.py -q
python -m pytest -q
git status --porcelain tests/
git diff main --stat -- app/
```

---

## Risks + Mitigations

| Risk | Mitigation |
|------|-----------|
| The assertions pin the sentence, so the next legitimate wording tweak deletes the test | Every assertion is a substring or a forbidden-word check. No `==` against a full label anywhere in the new file. Stated in the module docstring so the next author knows the rule. |
| The new file drifts out of sync with STORY-008's block in `tests/test_copy.py` | The overlap is only the two general sweeps, and they are written from different angles (closed set vs. per-member). Neither restates the other's literal data, so a new constant needs one edit in `test_copy.py` and none here. |
| Someone "tidies up" by folding the new file back into `tests/test_copy.py` | The module docstring states Section 15's constraint as the reason the file exists, and Task 7 asserts `test_copy.py` is unmodified. |
| The label passes but the screen shows something else | `tests/test_admin_state.py:1797` already binds `figure.label` to the constant, and `tests/test_summary.py:315` binds the note to rendered output. This story pins the constant; those two pin the path from constant to screen. Named here so the chain is explicit rather than assumed. |
| The `dir()` sweeps call `.lower()` on a non-`str` constant added later | Every sweep guards with `isinstance(value, str)` before touching the value. |

---

## Acceptance Criteria

(Copied from story `STORY-016`)

- [ ] Given `tests/test_admin_copy.py`, when it runs, then it asserts the
      completion label states that blocked rows are included in the count
- [ ] Given the completion label, when it is asserted, then the test fails if the
      wording becomes "success rate" or any phrasing that reads as an answer rate
- [ ] Given every constant in `admin_copy.py`, when the test runs, then each is
      asserted non-empty, matching the existing
      `test_copy_constants_exist_and_not_empty` pattern
- [ ] Given the scope templates — the register's "100 most recent of {total}" and
      the summary's all-time scope line — when the test runs, then both are
      asserted to state their window (Risk 4)
- [ ] Given the gate refusal string, when the test runs, then exactly one refusal
      constant exists — no second, more specific message can be added without
      failing the test (Section 9's no-oracle rule)
- [ ] Given the existing chat copy assertions in `tests/test_copy.py`, when the
      suite runs, then they pass unmodified
- [ ] All tasks completed
- [ ] Each new test proven to fail against a mutated constant (Task 8)
- [ ] `python -m pytest -q` green; nothing under `app/` or `chat_ui/` changed
- [ ] Follows existing patterns
