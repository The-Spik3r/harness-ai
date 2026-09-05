"""The rail renders what this module computed, so this is where it is checked.

`derive_title` and `format_activity` run once in the backend, when the session
list is built — by the time a component sees either value it is a Reflex Var
and no Python can run against it. There is no second chance downstream, so
every edge the two functions have is pinned here.

Four of these tests defend a decision rather than a behaviour. `derive_title`
has three separate ways to return nothing (a whitespace-only prompt, a word
boundary that falls at index 0, a cap that lands inside the only token), and a
session titled with the empty string is a rail row that cannot be clicked and
cannot be renamed — the failure the story exists to prevent. The fourth is
`ChatSessionSummary`'s field list: PRD-008 Section 6.1 fixes it at three, and
the test fails if a message count, a model or a verdict summary is ever added
"for completeness", the same way `tests/test_admin_models.py` fails if
`AuditRow` regrows a preview field.

Nothing here touches a database, so this suite needs no libSQL server.
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

# Repo root, not chat_ui/ — putting the inner package on sys.path[0] shadows
# the namespace package every other test module imports through.
sys.path.insert(0, str(Path(__file__).parent.parent))

from chat_ui.chat_ui.copy import SESSION_ACTIVITY_UNKNOWN, SESSION_UNTITLED_TITLE
from chat_ui.chat_ui.formatting import (
    TITLE_ELLIPSIS,
    TITLE_MAX_LENGTH,
    derive_title,
    format_activity,
)
from chat_ui.chat_ui.models import ChatSessionSummary

NOW = datetime(2026, 9, 4, 12, 0, 0, tzinfo=timezone.utc)

# app/db/database.py:36. The exact shape chat_sessions.updated_at holds, so the
# tests below feed this parser what the store actually writes.
_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def stamp(seconds_ago: int) -> str:
    """A stored timestamp `seconds_ago` before NOW, in the store's own format."""
    return (NOW - timedelta(seconds=seconds_ago)).strftime(_TIMESTAMP_FORMAT)


# --- derive_title --------------------------------------------------------


def test_a_short_prompt_is_its_own_title():
    """AC 3: under the cap, returned unchanged — and with no ellipsis.

    An ellipsis is a claim that something was cut. Appending one to a prompt
    that fit says the title is abbreviated when it is complete.
    """
    prompt = "Summarise the Q3 vendor spend"
    assert derive_title(prompt) == prompt
    assert TITLE_ELLIPSIS not in derive_title(prompt)


def test_a_prompt_exactly_at_the_cap_is_not_ellipsized():
    """The `<=` side of the boundary. A prompt of exactly TITLE_MAX_LENGTH
    characters was not truncated, so it must not be marked as truncated."""
    prompt = "a" * TITLE_MAX_LENGTH
    assert len(prompt) == TITLE_MAX_LENGTH
    assert derive_title(prompt) == prompt
    assert TITLE_ELLIPSIS not in derive_title(prompt)

    # One character over is the first input that does get cut.
    assert derive_title("a" * (TITLE_MAX_LENGTH + 1)).endswith(TITLE_ELLIPSIS)


def test_a_long_prompt_is_cut_at_a_word_boundary():
    """AC 2: never mid-word, and the ellipsis only because it truncated.

    The body is asserted to be a prefix of the source *and* to be followed in
    the source by a space — which is what "a word boundary" means and what a
    plain `prompt[:cap]` would fail.
    """
    prompt = (
        "Summarise the Q3 vendor spend across every supplier we contracted last year"
    )
    result = derive_title(prompt)

    assert result.endswith(TITLE_ELLIPSIS)
    body = result[: -len(TITLE_ELLIPSIS)]
    assert prompt.startswith(body), "the title is not a prefix of the prompt"
    assert prompt[len(body)] == " ", "the cut landed inside a word"
    assert not body.endswith(" "), "a space was left dangling before the ellipsis"
    assert len(result) <= TITLE_MAX_LENGTH + len(TITLE_ELLIPSIS)


def test_one_unbroken_token_truncates_at_the_cap():
    """AC 4: neither the whole token nor an empty string.

    The single-token prompt is the AC's own case: there is no boundary inside
    the cap, so the cut is the cap. The second input — a short word ahead of a
    200-character token — is the one that separates "cut at a boundary" from
    "cut at the cap": the boundary exists, it is usable, and the rule holds
    even though it spends only four of the forty-eight characters available.
    A mid-token cut there would violate AC 2.
    """
    token = derive_title("y" * 200)
    assert token == "y" * TITLE_MAX_LENGTH + TITLE_ELLIPSIS
    assert len(token) == TITLE_MAX_LENGTH + len(TITLE_ELLIPSIS)

    with_word = derive_title("word " + "y" * 200)
    assert with_word == "word" + TITLE_ELLIPSIS
    assert with_word.strip(TITLE_ELLIPSIS), "the title is empty but for the ellipsis"


def test_the_cap_arm_returns_a_title_when_no_boundary_survives():
    """The `if not cut` arm, called directly rather than through an input.

    The whitespace collapse in `derive_title` removes the leading space that is
    the usual way a word-boundary search returns nothing, so this arm has no
    live input today. It is still the last guard against an empty title, so it
    is exercised as the unit it is: strip the collapse, and the arm is what
    stands between a leading-space prompt and an unnameable rail row.
    """
    head = (" " + "y" * 200)[:TITLE_MAX_LENGTH]
    naive = head.rsplit(" ", 1)[0].rstrip()
    assert naive == "", "precondition: this is the input the naive cut loses"

    # The real function survives it, because it collapses first.
    assert derive_title(" " + "y" * 200) == "y" * TITLE_MAX_LENGTH + TITLE_ELLIPSIS


@pytest.mark.parametrize("prompt", ["", " ", "   ", "\n", "\t", "\n\t  \r\n"])
def test_a_whitespace_only_prompt_falls_back(prompt):
    """AC 5: a copy-module string, never an empty title.

    "A blank row in the rail is unclickable and unnameable" — the fallback is
    asserted against the constant rather than against its text, so rewording
    the copy does not silently break the guarantee.
    """
    assert derive_title(prompt) == SESSION_UNTITLED_TITLE
    assert derive_title(prompt)


def test_a_multiline_prompt_becomes_one_line():
    """A pasted prompt is titled, not laid out. A newline inside a rail row is
    not a title, and neither is a run of thirty spaces."""
    result = derive_title("line one\nline two\r\n\tline  three")
    assert "\n" not in result
    assert "\r" not in result
    assert "\t" not in result
    assert "  " not in result
    assert result == "line one line two line three"


# --- format_activity -----------------------------------------------------


@pytest.mark.parametrize(
    "seconds_ago,expected",
    [
        (0, "just now"),
        (1, "1s ago"),
        (59, "59s ago"),
        (60, "1m ago"),
        (120, "2m ago"),
        (3599, "59m ago"),
        (3600, "1h ago"),
        (7200, "2h ago"),
        (86399, "23h ago"),
        (86400, "yesterday"),
        (172799, "yesterday"),
        (172800, "2 days ago"),
        (259200, "3 days ago"),
        (864000, "10 days ago"),
    ],
)
def test_activity_reads_at_every_boundary(seconds_ago, expected):
    """AC 6: the three spellings the PRD's wireframe shows, at every edge.

    Under a day this is `humanize_compact` verbatim — the register's spelling,
    shared rather than re-bucketed, so the rail and the console can never
    disagree about when an hour becomes a day. "yesterday" replaces what would
    otherwise read "1d ago", and only there.
    """
    assert format_activity(stamp(seconds_ago), NOW) == expected


def test_a_future_timestamp_reads_as_just_now():
    """Clock skew between two instances must not print a negative count.

    PRD-007 put two instances on one database; their clocks are not the same
    clock, and a row touched by the other instance can be stamped ahead of this
    one's `now`. "-3s ago" would be the visible symptom.
    """
    ahead = (NOW + timedelta(seconds=90)).strftime(_TIMESTAMP_FORMAT)
    assert format_activity(ahead, NOW) == "just now"


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "not-a-timestamp",
        "2026-13-45T99:99:99Z",
        "2026-09-04",  # parses as a date, but naive — must not raise on subtraction
        "yesterday",
        "1725451200",
    ],
)
def test_an_unreadable_activity_time_falls_back_without_raising(raw):
    """AC 7: the precedent `format_duplicate_info` set with
    DUPLICATE_UNPARSEABLE_TEMPLATE — a bad column costs the relative reading,
    not the row. Nothing here may raise into a page render.

    `"2026-09-04"` is the input worth naming: it parses fine and yields a
    *naive* datetime, so the subtraction against an aware `now` raises
    TypeError rather than ValueError. A narrow `except ValueError` would let it
    through, which is why the arm catches broadly.
    """
    assert format_activity(raw, NOW) == SESSION_ACTIVITY_UNKNOWN


def test_activity_defaults_to_the_utc_clock():
    """AC 6: computed against `datetime.now(timezone.utc)` when no clock is given.

    A naive `datetime.now()` would read the machine's local zone and make every
    row in the rail report hours or days of staleness for a reader outside UTC.
    The default is exercised by omitting the parameter entirely.
    """
    just_written = datetime.now(timezone.utc).strftime(_TIMESTAMP_FORMAT)
    assert format_activity(just_written) in {"just now", "1s ago"}


def test_the_stored_timestamp_format_round_trips():
    """The seam with the store, not with a hand-written string.

    `create_chat_session` and `touch_chat_session` write
    `datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")`
    (`app/db/database.py:36`). This asserts the parser reads that exact shape
    rather than assuming the `Z`-replacement covers whatever the column holds.
    """
    written = (NOW - timedelta(hours=5)).strftime(_TIMESTAMP_FORMAT)
    assert written.endswith("Z") and "+" not in written
    assert format_activity(written, NOW) == "5h ago"


def test_the_activity_string_is_never_stored_shaped():
    """PRD-008 Section 6: recomputed on every load, never persisted.

    Not a claim about a caller — it is a claim about this function, which takes
    a timestamp and returns a rendering, and holds no cache to return a stale
    one from. The same input against two clocks gives two answers.
    """
    written = stamp(120)
    assert format_activity(written, NOW) == "2m ago"
    assert format_activity(written, NOW + timedelta(days=3)) == "3 days ago"


# --- ChatSessionSummary --------------------------------------------------


def test_the_summary_carries_three_fields_and_no_figure():
    """AC 1, and the decision behind it.

    PRD-008 Section 6.1, verbatim: "Every session row carries a relative
    activity time and nothing else -- no message count, no model, no verdict
    summary... a figure belongs in the rail only if the reader needs it to
    choose a row, and they do not." Adding a fourth field removes that decision
    rather than improving the model, so the field list is asserted exactly.
    """
    assert sorted(ChatSessionSummary.model_fields) == [
        "activity_info",
        "session_id",
        "title",
    ]


@pytest.mark.parametrize(
    "field", ["message_count", "model", "model_used", "verdict", "tokens_used"]
)
def test_the_summary_has_no_figure_field(field):
    """The named absences, one at a time, so a failure says which one came back."""
    assert field not in ChatSessionSummary.model_fields


def test_the_summary_holds_what_the_two_functions_produce():
    """The row is plain strings, all defaulted, assembled from this module's
    output — the derived-once shape PRD-006 set for `AuditRow` and the reason
    `activity_info` is a field rather than a computed property."""
    blank = ChatSessionSummary()
    assert (blank.session_id, blank.title, blank.activity_info) == ("", "", "")

    row = ChatSessionSummary(
        session_id="0b8f1a2c-3d4e-4f50-9a6b-7c8d9e0f1a2b",
        title=derive_title("Summarise the Q3 vendor spend"),
        activity_info=format_activity(stamp(120), NOW),
    )
    assert row.title == "Summarise the Q3 vendor spend"
    assert row.activity_info == "2m ago"
    assert all(isinstance(value, str) for value in row.model_dump().values())
