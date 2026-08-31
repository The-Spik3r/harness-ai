"""STORY-016 — the console's copy assertions that carry a correctness claim.

**Why this is not in `tests/test_copy.py`.** PRD-006 Section 15 lists
`tests/test_copy.py` among the tests that must pass *unmodified* — it is one of
the files that prove PRD-002's chat was not disturbed by this epic. STORY-008
already appended an admin block there, reading "unmodified" as "no existing
assertion weakened". STORY-016 does not extend that reading any further: its
assertions land in this sibling file, so from here on the constraint stays
literal and `git diff` on `tests/test_copy.py` stays empty.

**What this file adds that STORY-008's block does not.** That block asserts every
admin constant is non-empty. It asserts nothing about what any of them *says* —
so renaming `FIGURE_COMPLETION_LABEL` back to "Success rate" would leave the
whole suite green today. That label is the one string on this console with a
correctness requirement (PRD-006 Risk 4), and this file is its pin.

**Two assertions here deliberately duplicate that block** — the exhaustive
non-empty sweep and the single-refusal rule. The duplication is the point: this
file must still hold if that appended block is ever reverted to satisfy Section
15 literally. They are written from the opposite angle rather than copy-pasted:
`tests/test_copy.py` proves the *set* of constants is closed against a literal
95-name list, this file proves *each* member carries text without restating it.

**The house rule for every assertion below: substance, not sentences.** A test
that pins a full label breaks on the next legitimate wording tweak and gets
deleted the first time it does — which is the failure mode this file exists to
prevent. So each check is a required substring or a forbidden one. Rewording is
allowed; changing what the label *claims* is not.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# The module handle for the sweeps, and the named imports beside it — the same
# pairing `tests/test_copy.py` uses, and for the same reason: a renamed or
# deleted constant fails at collection rather than inside one assertion.
from chat_ui.chat_ui import admin_copy  # noqa: E402
from chat_ui.chat_ui.admin_copy import (  # noqa: E402
    FIGURE_COMPLETION_LABEL,
    FIGURE_COMPLETION_NOTE,
    FIGURE_TOTAL_LABEL,
    FIGURE_BLOCKED_DUPLICATES_LABEL,
    FIGURE_BLOCKED_SUSPICIOUS_LABEL,
    REGISTER_SCOPE_TEMPLATE,
    SUMMARY_SCOPE_ALL_TIME,
    SUMMARY_SCOPE_NOTE,
    GATE_REFUSED_MESSAGE,
)


def _public_constants():
    """Every public uppercase name in admin_copy, as (name, value) pairs."""
    return [
        (name, getattr(admin_copy, name))
        for name in dir(admin_copy)
        if name.isupper() and not name.startswith("_")
    ]


def test_every_admin_copy_constant_is_non_empty():
    """AC3: each constant in `admin_copy.py` asserted non-empty.

    The division of labour with `test_admin_copy_constants_exist_and_not_empty`
    (`tests/test_copy.py:311`): that one compares the module's names against a
    literal set, so it catches a constant added without a test. This one walks
    whatever is there and checks each carries text, so it needs no list to
    maintain and survives on its own if the other is ever reverted.
    """
    constants = _public_constants()

    # A guard against passing vacuously: if a future refactor empties the module
    # or moves the constants behind a lazy accessor, `dir()` returns nothing and
    # the loop below asserts nothing at all. 96 today; the floor is deliberately
    # loose, because the exact count is `tests/test_copy.py`'s claim, not this
    # file's.
    assert len(constants) > 50, f"only {len(constants)} constants found"

    for name, value in constants:
        assert isinstance(value, str), f"{name} is {type(value).__name__}, not str"
        assert value.strip(), f"{name} is empty"


def test_completion_label_states_that_blocked_rows_are_counted():
    """AC1 / Risk 4: the completion figure says what it actually counts.

    PRD-006 Section 4, verbatim: the figure must be "labeled for what it counts
    — rows the pipeline completed without raising, blocked rows included — not
    as an answer rate."

    Asserted on substance: the qualifier must be present, in whatever words. The
    label reads "Completed without error (blocked queries included)" today and
    may be reworded, but it may not stop saying that blocked rows are in there.
    """
    label = FIGURE_COMPLETION_LABEL.lower()

    # What is counted...
    assert "completed" in label or "without error" in label
    # ...and the qualifier that makes the number honest.
    assert "blocked" in label, FIGURE_COMPLETION_LABEL
    assert "included" in label, FIGURE_COMPLETION_LABEL

    # The note rendered beneath the figure (chat_ui/chat_ui/components/summary.py:391)
    # is the sentence a reader actually acts on, so it carries the same
    # correction in prose: both blocked verdicts named, and the answer-rate
    # reading refused outright.
    note = FIGURE_COMPLETION_NOTE.lower()
    assert "not an answer rate" in note, FIGURE_COMPLETION_NOTE
    assert "held" in note and "denied" in note, FIGURE_COMPLETION_NOTE


def test_completion_label_cannot_regress_to_success_rate():
    """AC2 / Risk 4 mitigation, verbatim: "The completion label is covered by a
    copy test so its wording cannot drift back to 'success rate'."

    What this pins is the *label*, not the *computation*. `count_successful_queries()`
    still counts every duplicate-blocked and pattern-blocked row as a success;
    `app/` is out of scope for PRD-006 and a truthful metric is deferred to its
    Section 13. The claim here is narrower and worth making on its own: the
    console never again narrates that number under a name that misstates it.
    """
    forbidden = (
        "success",
        "success rate",
        "success_rate",
        "answer rate",
        "succeeded",
        "successful",
        "% success",
    )
    hits = [word for word in forbidden if word in FIGURE_COMPLETION_LABEL.lower()]
    assert not hits, f"completion label reads as an answer rate: {hits}"

    # Split from the tuple above on purpose, so the failure message distinguishes
    # "you wrote success" from "you wrote a rate". Any *rate* in a completion
    # label reads as an answer rate whatever noun sits in front of it —
    # "Completion rate" would pass the tuple and still be the wrong claim.
    assert "rate" not in FIGURE_COMPLETION_LABEL.lower(), FIGURE_COMPLETION_LABEL

    # The other way this regresses: not a rename, but a second constant carrying
    # the old name alongside the corrected one. Scoped to admin_copy on purpose —
    # `app/schemas.py` owns a legitimate `success_rate` response field, and
    # PRD-006 does not touch `app/`.
    offenders = [
        name
        for name, value in _public_constants()
        if "success rate" in value.lower() or "success_rate" in value.lower()
    ]
    assert not offenders, f"admin copy names the old metric: {offenders}"

    # The three figures the completion label sits among must stay distinguishable
    # from it: if one of them were reworded into the answer-rate phrasing, the
    # sheet would carry the wrong claim under a different key.
    for label in (
        FIGURE_TOTAL_LABEL,
        FIGURE_BLOCKED_DUPLICATES_LABEL,
        FIGURE_BLOCKED_SUSPICIOUS_LABEL,
    ):
        assert "success" not in label.lower(), label


def test_both_scope_lines_state_their_window():
    """AC4 / Risk 4's first clause: all-time figures beside a 100-row window
    "invite a wrong reading". The mitigation is that scope is a required part of
    every label, so both scope lines are asserted to state their window here.
    """
    # The register: the window *and* the true total, which is the pairing Risk 4
    # asks for — "100 most recent of 3,180" reads as a cap, "100 rows" does not.
    assert "{shown}" in REGISTER_SCOPE_TEMPLATE
    assert "{total}" in REGISTER_SCOPE_TEMPLATE
    scope = REGISTER_SCOPE_TEMPLATE.format(shown=100, total="3,180")
    assert "100" in scope and "3,180" in scope
    assert "most recent" in scope.lower(), scope

    # The summary: all-time, and saying so.
    all_time = SUMMARY_SCOPE_ALL_TIME.lower()
    assert "all time" in all_time, SUMMARY_SCOPE_ALL_TIME
    assert "every" in all_time or "all rows" in all_time, SUMMARY_SCOPE_ALL_TIME

    # The one prose line that resolves the two windows against each other, so it
    # must name both sides rather than only its own.
    note = SUMMARY_SCOPE_NOTE.lower()
    assert "whole table" in note, SUMMARY_SCOPE_NOTE
    assert "most recent" in note, SUMMARY_SCOPE_NOTE

    # The collapse Risk 4 warns about is one scope line doing both jobs.
    assert SUMMARY_SCOPE_ALL_TIME != REGISTER_SCOPE_TEMPLATE


def test_exactly_one_refusal_constant_exists():
    """AC5 / PRD-006 Section 9, verbatim: "an empty, malformed or wrong token
    produces the same message. The gate reports that access was refused, not
    why."

    This duplicates `test_admin_copy_states_one_refusal_and_says_nothing_about_why`
    (`tests/test_copy.py:576`) on purpose. AC5 requires *this* file to enforce
    it, and the no-oracle rule is a security property that should not depend on
    a file Section 15 may force back to its pre-STORY-008 state.
    """
    assert GATE_REFUSED_MESSAGE
    assert "refused" in GATE_REFUSED_MESSAGE.lower()

    refusals = [
        name for name, value in _public_constants() if "refus" in value.lower()
    ]
    assert refusals == ["GATE_REFUSED_MESSAGE"], refusals

    # No second, more specific message beside it, and no reason inside it: each
    # of these words would tell a caller which of the three failures occurred.
    forbidden = (
        "empty",
        "invalid",
        "incorrect",
        "wrong",
        "length",
        "expired",
        "format",
        "try again with",
    )
    hits = [word for word in forbidden if word in GATE_REFUSED_MESSAGE.lower()]
    assert not hits, f"the refusal names a reason: {hits}"
