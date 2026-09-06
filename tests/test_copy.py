import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from chat_ui.chat_ui.copy import (
    LOGIN_PROMPT_TITLE,
    COMPOSER_PLACEHOLDER,
    WELCOME_MESSAGE_CONTENT,
    PII_BADGE_TEMPLATE,
    FOOTER_SEPARATOR,
    RETRY_LABEL,
    EDIT_AND_RESEND_LABEL,
    DUPLICATE_CHANGE_NOTICE,
    UPSTREAM_ERROR_PREFIX,
    DUPLICATE_RELATIVE_TIME_TEMPLATE,
    DUPLICATE_WINDOW_RELEASE_TEMPLATE,
    SHELL_HEADER_TITLE,
    SHELL_HEADER_BADGE,
    SHELL_USER_LABEL,
    SHELL_LOGOUT_LABEL,
    SHELL_MODEL_SLOT_LABEL,
    EMPTY_STATE_TITLE,
    EMPTY_STATE_SUBTITLE,
    EMPTY_STATE_PII_FEATURE,
    EMPTY_STATE_SECURITY_FEATURE,
    EMPTY_STATE_DEDUP_FEATURE,
    # STORY-012: the two session fallbacks. Imported by name like every
    # constant above, so a rename fails at collection rather than at render.
    SESSION_UNTITLED_TITLE,
    SESSION_ACTIVITY_UNKNOWN,
    # STORY-014: the two transcript-persistence notices, same rule.
    TRANSCRIPT_NOT_SAVED_NOTICE,
    SESSION_ORDER_STALE_NOTICE,
    # STORY-015: the read counterpart of the two above.
    TRANSCRIPT_NOT_LOADED_NOTICE,
    # STORY-016: the delete flow's two words.
    SESSION_DELETE_CONFIRM_TEMPLATE,
    SESSION_DELETE_CONFIRM_LABEL,
    # STORY-017: the rail's remaining strings, imported by name like every
    # constant above, so a rename fails at collection rather than at render.
    SESSION_NEW_CHAT_LABEL,
    SESSION_RAIL_EMPTY_TITLE,
    SESSION_RAIL_EMPTY_BODY,
    SESSION_RAIL_FAULT_TITLE,
    SESSION_RAIL_FAULT_BODY,
    SESSION_RAIL_SCOPE_TEMPLATE,
    SESSION_RENAME_LABEL,
    SESSION_RENAME_PLACEHOLDER,
    SESSION_DELETE_CANCEL_LABEL,
    SESSION_RAIL_SHOW_LABEL,
)
from chat_ui.chat_ui.formatting import derive_title, format_duplicate_info

# STORY-008: the console's own copy module. Imported by name, as the chat
# constants above are, so a deleted or renamed constant fails at collection
# rather than at render.
from chat_ui.chat_ui import admin_copy
from chat_ui.chat_ui.admin_copy import (
    CONSOLE_TITLE,
    MASTHEAD_SEPARATOR,
    CONSOLE_VIEW_REGISTER,
    CONSOLE_VIEW_SUMMARY,
    VIEW_REGISTER_LABEL,
    VIEW_SUMMARY_LABEL,
    SIGN_OUT_LABEL,
    GATE_TITLE,
    GATE_BODY,
    GATE_PLACEHOLDER,
    GATE_SUBMIT_LABEL,
    GATE_REFUSED_MESSAGE,
    COLUMN_TIME,
    COLUMN_USER,
    COLUMN_VERDICT,
    COLUMN_MODEL,
    COLUMN_TOKENS,
    COLUMN_PII,
    COLUMN_DEVICE,
    COLUMN_ID,
    AUDIT_ID_PREFIX,
    PII_INDICATOR_LABEL,
    VERDICT_CLEARED_LABEL,
    VERDICT_HELD_LABEL,
    VERDICT_DENIED_LABEL,
    VERDICT_FAULT_LABEL,
    REGISTER_SCOPE_TEMPLATE,
    REGISTER_FILTERED_TEMPLATE,
    SUMMARY_SCOPE_ALL_TIME,
    SUMMARY_SCOPE_NOTE,
    REFRESH_LABEL,
    REFRESH_IN_FLIGHT_LABEL,
    REFRESHED_TEMPLATE,
    NEVER_REFRESHED_LABEL,
    FAULT_TITLE,
    FAULT_MESSAGE_TEMPLATE,
    READ_LABEL_ROWS,
    READ_LABEL_TOTAL,
    READ_LABEL_BLOCKED_DUPLICATES,
    READ_LABEL_BLOCKED_SUSPICIOUS,
    READ_LABEL_UNIQUE_USERS,
    READ_LABEL_SUCCESSFUL,
    READ_LABEL_PII_QUERIES,
    READ_LABEL_TOP_MODELS,
    READ_LABEL_TOP_USERS,
    READ_LABEL_TOP_PII,
    EMPTY_REGISTER_TITLE,
    EMPTY_REGISTER_BODY,
    EMPTY_MATCHES_TITLE,
    EMPTY_MATCHES_TEMPLATE,
    FILTER_DESCRIPTION_VERDICT_TEMPLATE,
    FILTER_DESCRIPTION_SEARCH_TEMPLATE,
    FILTER_DESCRIPTION_JOIN,
    FILTER_DESCRIPTION_VERDICT_JOIN,
    EMPTY_SUMMARY_TITLE,
    EMPTY_SUMMARY_BODY,
    FILTER_VERDICT_LABEL,
    FILTER_SEARCH_LABEL,
    FILTER_SEARCH_PLACEHOLDER,
    CLEAR_FILTERS_LABEL,
    SORT_LABEL,
    SORT_TIMESTAMP_LABEL,
    SORT_USER_LABEL,
    SORT_VERDICT_LABEL,
    SORT_ASCENDING_MARK,
    SORT_DESCENDING_MARK,
    DETAIL_TOGGLE_OPEN_LABEL,
    DETAIL_TOGGLE_CLOSE_LABEL,
    DETAIL_TOGGLE_OPEN_MARK,
    DETAIL_TOGGLE_CLOSE_MARK,
    DETAIL_TIMESTAMP_LABEL,
    DETAIL_PROMPT_HASH_LABEL,
    DETAIL_ERROR_LABEL,
    DETAIL_PATTERN_LABEL,
    DETAIL_DEVICE_LABEL,
    DETAIL_PII_ENTITIES_LABEL,
    DETAIL_PII_INPUT_LABEL,
    DETAIL_PII_OUTPUT_LABEL,
    DETAIL_PII_PRESENT_LABEL,
    DETAIL_PII_ABSENT_LABEL,
    SUMMARY_COUNTS_HEADING,
    SUMMARY_WHO_HEADING,
    SUMMARY_PII_HEADING,
    FIGURE_TOTAL_LABEL,
    FIGURE_BLOCKED_DUPLICATES_LABEL,
    FIGURE_BLOCKED_SUSPICIOUS_LABEL,
    FIGURE_COMPLETION_LABEL,
    FIGURE_COMPLETION_NOTE,
    FIGURE_UNIQUE_USERS_LABEL,
    FIGURE_TOP_MODELS_LABEL,
    FIGURE_TOP_USERS_LABEL,
    FIGURE_PII_QUERIES_LABEL,
    FIGURE_TOP_PII_LABEL,
    RANKED_CUT_TEMPLATE,
    SHARE_TEMPLATE,
    RANKED_EMPTY_LABEL,
)


def test_copy_constants_exist_and_not_empty():
    """Verify all critical copy strings are non-empty and accessible."""
    assert LOGIN_PROMPT_TITLE
    assert COMPOSER_PLACEHOLDER == "Message..."
    assert WELCOME_MESSAGE_CONTENT
    assert RETRY_LABEL == "Retry"
    assert EDIT_AND_RESEND_LABEL == "Edit and resend"
    assert SHELL_HEADER_TITLE
    assert SHELL_HEADER_BADGE
    assert SHELL_USER_LABEL
    assert SHELL_LOGOUT_LABEL
    assert SHELL_MODEL_SLOT_LABEL
    assert EMPTY_STATE_TITLE
    assert EMPTY_STATE_SUBTITLE
    assert EMPTY_STATE_PII_FEATURE
    assert EMPTY_STATE_SECURITY_FEATURE
    assert EMPTY_STATE_DEDUP_FEATURE


def test_risk_5_pii_exchange_phrasing():
    """AC3 / Risk 5: PII badge copy explicitly states masking applies to the exchange, not prompt alone."""
    assert "masked in this exchange" in PII_BADGE_TEMPLATE
    formatted = PII_BADGE_TEMPLATE.format(count=2, entities="PERSON, EMAIL_ADDRESS")
    assert "exchange" in formatted
    assert "prompt" not in formatted


def test_risk_4_duplicate_change_notice():
    """AC4 / Risk 4: Duplicate card copy states that text must change for resend to go through."""
    assert DUPLICATE_CHANGE_NOTICE
    assert "modify" in DUPLICATE_CHANGE_NOTICE.lower() or "change" in DUPLICATE_CHANGE_NOTICE.lower()


def test_risk_7_upstream_error_naming():
    """Technical Notes / Risk 7: Upstream-error copy names OpenRouter explicitly."""
    assert "OpenRouter" in UPSTREAM_ERROR_PREFIX


def test_footer_formatting_constants():
    """Verify footer separator and formatting tokens exist."""
    assert FOOTER_SEPARATOR == " · "


def test_duplicate_formatting_relative_and_window():
    """AC1 & AC2: Valid timestamp yields relative time, absolute timestamp, and 24h window release."""
    assert DUPLICATE_RELATIVE_TIME_TEMPLATE
    assert DUPLICATE_WINDOW_RELEASE_TEMPLATE
    main, release = format_duplicate_info("2026-08-21T10:30:00Z")
    assert "Already sent" in main
    assert "2026-08-21T10:30:00Z" in main
    assert "24h window releases at" in release
    assert "2026-08-22T10:30:00Z" in release


@pytest.mark.parametrize(
    "seconds,expected",
    [
        (-5, "just now"),
        (0, "just now"),
        (1, "1 second ago"),
        (2, "2 seconds ago"),
        (60, "1 minute ago"),
        (120, "2 minutes ago"),
        (3600, "1 hour ago"),
        (7200, "2 hours ago"),
        (86400, "1 day ago"),
        (172800, "2 days ago"),
    ],
)
def test_relative_time_reads_naturally_at_every_boundary(seconds, expected):
    """A duplicate card is the first thing many users see; "1 seconds ago"
    undermines it. Every unit boundary is pinned, singular and plural."""
    from chat_ui.chat_ui.formatting import _humanize

    assert _humanize(seconds) == expected


def test_duplicate_formatting_empty_and_unparseable_fallback():
    """AC3: Empty or unparseable first_query_at renders fallback without crash ('No silent drops')."""
    main_empty, release_empty = format_duplicate_info("")
    assert main_empty == "Already submitted recently."
    assert release_empty == ""

    main_bad, release_bad = format_duplicate_info("not-a-timestamp")
    assert "Already sent at not-a-timestamp" in main_bad
    assert release_bad == ""


# --------------------------------------------------------------------------
# STORY-008 — chat_ui/chat_ui/admin_copy.py
#
# Appended, never edited above: PRD-006 Section 15 lists this file as one that
# must pass unmodified, which is read here as "no existing assertion weakened,
# reworded, reordered or removed". Every test above this line is untouched.
# --------------------------------------------------------------------------


def test_admin_copy_constants_exist_and_not_empty():
    """AC6: every admin-facing string is non-empty and accessible, matching
    test_copy_constants_exist_and_not_empty's pattern above."""
    assert CONSOLE_TITLE
    assert MASTHEAD_SEPARATOR
    assert CONSOLE_VIEW_REGISTER
    assert CONSOLE_VIEW_SUMMARY
    assert VIEW_REGISTER_LABEL
    assert VIEW_SUMMARY_LABEL
    assert SIGN_OUT_LABEL
    assert GATE_TITLE
    assert GATE_BODY
    assert GATE_PLACEHOLDER
    assert GATE_SUBMIT_LABEL
    assert GATE_REFUSED_MESSAGE
    assert COLUMN_TIME
    assert COLUMN_USER
    assert COLUMN_VERDICT
    assert COLUMN_MODEL
    assert COLUMN_TOKENS
    assert COLUMN_PII
    assert COLUMN_DEVICE
    assert COLUMN_ID
    assert AUDIT_ID_PREFIX
    assert PII_INDICATOR_LABEL
    assert VERDICT_CLEARED_LABEL
    assert VERDICT_HELD_LABEL
    assert VERDICT_DENIED_LABEL
    assert VERDICT_FAULT_LABEL
    assert REGISTER_SCOPE_TEMPLATE
    assert REGISTER_FILTERED_TEMPLATE
    assert SUMMARY_SCOPE_ALL_TIME
    assert SUMMARY_SCOPE_NOTE
    assert REFRESH_LABEL
    assert REFRESH_IN_FLIGHT_LABEL
    assert REFRESHED_TEMPLATE
    assert NEVER_REFRESHED_LABEL
    assert FAULT_TITLE
    assert FAULT_MESSAGE_TEMPLATE
    assert READ_LABEL_ROWS
    assert READ_LABEL_TOTAL
    assert READ_LABEL_BLOCKED_DUPLICATES
    assert READ_LABEL_BLOCKED_SUSPICIOUS
    assert READ_LABEL_UNIQUE_USERS
    assert READ_LABEL_SUCCESSFUL
    assert READ_LABEL_PII_QUERIES
    assert READ_LABEL_TOP_MODELS
    assert READ_LABEL_TOP_USERS
    assert READ_LABEL_TOP_PII
    assert EMPTY_REGISTER_TITLE
    assert EMPTY_REGISTER_BODY
    assert EMPTY_MATCHES_TITLE
    assert EMPTY_MATCHES_TEMPLATE
    assert FILTER_DESCRIPTION_VERDICT_TEMPLATE
    assert FILTER_DESCRIPTION_SEARCH_TEMPLATE
    assert FILTER_DESCRIPTION_JOIN
    assert FILTER_DESCRIPTION_VERDICT_JOIN
    assert EMPTY_SUMMARY_TITLE
    assert EMPTY_SUMMARY_BODY
    assert FILTER_VERDICT_LABEL
    assert FILTER_SEARCH_LABEL
    assert FILTER_SEARCH_PLACEHOLDER
    assert CLEAR_FILTERS_LABEL
    assert SORT_LABEL
    assert SORT_TIMESTAMP_LABEL
    assert SORT_USER_LABEL
    assert SORT_VERDICT_LABEL
    assert SORT_ASCENDING_MARK
    assert SORT_DESCENDING_MARK
    assert DETAIL_TOGGLE_OPEN_LABEL
    assert DETAIL_TOGGLE_CLOSE_LABEL
    assert DETAIL_TOGGLE_OPEN_MARK
    assert DETAIL_TOGGLE_CLOSE_MARK
    assert DETAIL_PII_PRESENT_LABEL
    assert DETAIL_PII_ABSENT_LABEL
    assert DETAIL_TIMESTAMP_LABEL
    assert DETAIL_PROMPT_HASH_LABEL
    assert DETAIL_ERROR_LABEL
    assert DETAIL_PATTERN_LABEL
    assert DETAIL_DEVICE_LABEL
    assert DETAIL_PII_ENTITIES_LABEL
    assert DETAIL_PII_INPUT_LABEL
    assert DETAIL_PII_OUTPUT_LABEL
    assert SUMMARY_COUNTS_HEADING
    assert SUMMARY_WHO_HEADING
    assert SUMMARY_PII_HEADING
    assert FIGURE_TOTAL_LABEL
    assert FIGURE_BLOCKED_DUPLICATES_LABEL
    assert FIGURE_BLOCKED_SUSPICIOUS_LABEL
    assert FIGURE_COMPLETION_LABEL
    assert FIGURE_COMPLETION_NOTE
    assert FIGURE_UNIQUE_USERS_LABEL
    assert FIGURE_TOP_MODELS_LABEL
    assert FIGURE_TOP_USERS_LABEL
    assert FIGURE_PII_QUERIES_LABEL
    assert FIGURE_TOP_PII_LABEL
    assert RANKED_CUT_TEMPLATE
    assert SHARE_TEMPLATE
    assert RANKED_EMPTY_LABEL
    # And nothing is missing from the list: a constant added to admin_copy.py
    # without an assertion here would otherwise ship untested, which is the
    # failure mode "each constant is asserted non-empty" exists to prevent.
    declared = {
        name for name in dir(admin_copy) if name.isupper() and not name.startswith("_")
    }
    asserted = {
        "CONSOLE_TITLE",
        "MASTHEAD_SEPARATOR",
        "CONSOLE_VIEW_REGISTER",
        "CONSOLE_VIEW_SUMMARY",
        "VIEW_REGISTER_LABEL",
        "VIEW_SUMMARY_LABEL",
        "SIGN_OUT_LABEL",
        "GATE_TITLE",
        "GATE_BODY",
        "GATE_PLACEHOLDER",
        "GATE_SUBMIT_LABEL",
        "GATE_REFUSED_MESSAGE",
        "COLUMN_TIME",
        "COLUMN_USER",
        "COLUMN_VERDICT",
        "COLUMN_MODEL",
        "COLUMN_TOKENS",
        "COLUMN_PII",
        "COLUMN_DEVICE",
        "COLUMN_ID",
        "AUDIT_ID_PREFIX",
        "PII_INDICATOR_LABEL",
        "VERDICT_CLEARED_LABEL",
        "VERDICT_HELD_LABEL",
        "VERDICT_DENIED_LABEL",
        "VERDICT_FAULT_LABEL",
        "REGISTER_SCOPE_TEMPLATE",
        "REGISTER_FILTERED_TEMPLATE",
        "SUMMARY_SCOPE_ALL_TIME",
        "SUMMARY_SCOPE_NOTE",
        "REFRESH_LABEL",
        "REFRESH_IN_FLIGHT_LABEL",
        "REFRESHED_TEMPLATE",
        "NEVER_REFRESHED_LABEL",
        "FAULT_TITLE",
        "FAULT_MESSAGE_TEMPLATE",
        "READ_LABEL_ROWS",
        "READ_LABEL_TOTAL",
        "READ_LABEL_BLOCKED_DUPLICATES",
        "READ_LABEL_BLOCKED_SUSPICIOUS",
        "READ_LABEL_UNIQUE_USERS",
        "READ_LABEL_SUCCESSFUL",
        "READ_LABEL_PII_QUERIES",
        "READ_LABEL_TOP_MODELS",
        "READ_LABEL_TOP_USERS",
        "READ_LABEL_TOP_PII",
        "EMPTY_REGISTER_TITLE",
        "EMPTY_REGISTER_BODY",
        "EMPTY_MATCHES_TITLE",
        "EMPTY_MATCHES_TEMPLATE",
        "FILTER_DESCRIPTION_VERDICT_TEMPLATE",
        "FILTER_DESCRIPTION_SEARCH_TEMPLATE",
        "FILTER_DESCRIPTION_JOIN",
        "FILTER_DESCRIPTION_VERDICT_JOIN",
        "EMPTY_SUMMARY_TITLE",
        "EMPTY_SUMMARY_BODY",
        "FILTER_VERDICT_LABEL",
        "FILTER_SEARCH_LABEL",
        "FILTER_SEARCH_PLACEHOLDER",
        "CLEAR_FILTERS_LABEL",
        "SORT_LABEL",
        "SORT_TIMESTAMP_LABEL",
        "SORT_USER_LABEL",
        "SORT_VERDICT_LABEL",
        "SORT_ASCENDING_MARK",
        "SORT_DESCENDING_MARK",
        "DETAIL_TOGGLE_OPEN_LABEL",
        "DETAIL_TOGGLE_CLOSE_LABEL",
        "DETAIL_TOGGLE_OPEN_MARK",
        "DETAIL_TOGGLE_CLOSE_MARK",
        "DETAIL_PII_PRESENT_LABEL",
        "DETAIL_PII_ABSENT_LABEL",
        "DETAIL_TIMESTAMP_LABEL",
        "DETAIL_PROMPT_HASH_LABEL",
        "DETAIL_ERROR_LABEL",
        "DETAIL_PATTERN_LABEL",
        "DETAIL_DEVICE_LABEL",
        "DETAIL_PII_ENTITIES_LABEL",
        "DETAIL_PII_INPUT_LABEL",
        "DETAIL_PII_OUTPUT_LABEL",
        "SUMMARY_COUNTS_HEADING",
        "SUMMARY_WHO_HEADING",
        "SUMMARY_PII_HEADING",
        "FIGURE_TOTAL_LABEL",
        "FIGURE_BLOCKED_DUPLICATES_LABEL",
        "FIGURE_BLOCKED_SUSPICIOUS_LABEL",
        "FIGURE_COMPLETION_LABEL",
        "FIGURE_COMPLETION_NOTE",
        "FIGURE_UNIQUE_USERS_LABEL",
        "FIGURE_TOP_MODELS_LABEL",
        "FIGURE_TOP_USERS_LABEL",
        "FIGURE_PII_QUERIES_LABEL",
        "FIGURE_TOP_PII_LABEL",
        "RANKED_CUT_TEMPLATE",
        "SHARE_TEMPLATE",
        "RANKED_EMPTY_LABEL",
    }
    assert declared == asserted


def test_admin_copy_templates_carry_their_placeholders():
    """AC3: a label with a value in it is a template constant formatted at the
    call site, not concatenation — so each one names its fields and formats
    without a KeyError. AC3 names the first two explicitly."""
    assert REGISTER_SCOPE_TEMPLATE.format(shown=100, total="3,180") == (
        "100 most recent of 3,180"
    )
    assert REFRESHED_TEMPLATE.format(time="14:22:07") == "Refreshed 14:22:07"
    assert REGISTER_FILTERED_TEMPLATE.format(shown=2, loaded=100) == "2 of 100 shown"
    assert "{read}" in FAULT_MESSAGE_TEMPLATE and "{detail}" in FAULT_MESSAGE_TEMPLATE
    assert FAULT_MESSAGE_TEMPLATE.format(read=READ_LABEL_ROWS, detail="boom")
    assert EMPTY_MATCHES_TEMPLATE.format(filters="verdict denied", loaded=100)
    assert FILTER_DESCRIPTION_VERDICT_TEMPLATE.format(verdicts="denied")
    assert FILTER_DESCRIPTION_SEARCH_TEMPLATE.format(search="a.torres")
    assert RANKED_CUT_TEMPLATE.format(n=5) == "top 5"
    assert SHARE_TEMPLATE.format(share="13.0%") == "13.0% of all queries"


def test_the_two_filter_joiners_are_distinct():
    """STORY-014: one joins a *list*, the other a *conjunction*.

    `FILTER_DESCRIPTION_VERDICT_JOIN` sits between two selected verdicts inside
    the verdict clause ("verdict held, denied"); `FILTER_DESCRIPTION_JOIN` sits
    between the two kinds of filter ('verdict denied and text "ana"'). Collapsing
    them into one constant reads as "verdict held and denied and text ...", so
    the assertion is that they are two strings and not one name used twice.
    """
    assert FILTER_DESCRIPTION_VERDICT_JOIN != FILTER_DESCRIPTION_JOIN
    sentence = EMPTY_MATCHES_TEMPLATE.format(
        filters=FILTER_DESCRIPTION_JOIN.join(
            [
                FILTER_DESCRIPTION_VERDICT_TEMPLATE.format(
                    verdicts=FILTER_DESCRIPTION_VERDICT_JOIN.join(
                        ["held", "denied"]
                    )
                ),
                FILTER_DESCRIPTION_SEARCH_TEMPLATE.format(search="ana"),
            ]
        ),
        loaded=100,
    )
    assert sentence == (
        'verdict held, denied and text "ana" matched none of the 100 rows '
        "loaded."
    )


def test_refresh_keeps_one_verb_across_the_flow():
    """AC4 / frontend-design: "an action keeps the same name through the whole
    flow" — the control says Refresh, the line it produces says Refreshed, and
    signing out returns the gate rather than announcing a session ended."""
    verb = REFRESH_LABEL.lower()
    assert REFRESHED_TEMPLATE.lower().startswith(verb)
    assert REFRESH_IN_FLIGHT_LABEL.lower().startswith(verb)
    # The fault panel's retry is REFRESH_LABEL itself; the message says the same
    # word, so no second name for the same button can creep in.
    assert verb in FAULT_MESSAGE_TEMPLATE.lower()

    assert SIGN_OUT_LABEL == "Sign out"
    for name in dir(admin_copy):
        if name.isupper():
            assert "session ended" not in getattr(admin_copy, name).lower()


def test_admin_copy_states_one_refusal_and_says_nothing_about_why():
    """AC5 / PRD-006 Section 9: "an empty, malformed or wrong token produces the
    same message. The gate reports that access was refused, not why." One
    constant, and no second, more specific one can be added beside it."""
    assert GATE_REFUSED_MESSAGE
    assert "refused" in GATE_REFUSED_MESSAGE.lower()

    refusals = [
        name
        for name in dir(admin_copy)
        if name.isupper() and "refus" in getattr(admin_copy, name).lower()
    ]
    assert refusals == ["GATE_REFUSED_MESSAGE"]

    # It must not name the reason: no oracle distinguishing empty from wrong
    # from malformed, and no advice that implies one.
    forbidden = ("empty", "invalid", "incorrect", "wrong", "length", "expired", "format")
    assert not [word for word in forbidden if word in GATE_REFUSED_MESSAGE.lower()]


# --------------------------------------------------------------------------
# STORY-012 -- the session rail's two fallback strings.
#
# Appended, never edited above: `tests/test_copy.py` is one of the two suites
# `tests/test_untouched_app.py` pins by census, and every test above this line
# is untouched.
# --------------------------------------------------------------------------


def test_session_fallback_copy_names_the_thing_rather_than_the_failure():
    """STORY-012: both fallbacks are user-facing sentences, so both live here.

    Neither may report a parse failure or apologize (frontend-design: "errors
    don't apologize, and they are never vague about what happened"), and the
    untitled fallback must be non-empty -- a blank row in the rail is
    unclickable and unnameable.
    """
    assert SESSION_UNTITLED_TITLE
    assert SESSION_ACTIVITY_UNKNOWN

    for text in (SESSION_UNTITLED_TITLE, SESSION_ACTIVITY_UNKNOWN):
        # Sentence case: the copy module's own register throughout.
        assert text == text[0].upper() + text[1:] or text == text.lower()
        assert not text.endswith("."), "a rail row is a label, not a sentence"
        lowered = text.lower()
        for word in (
            "error",
            "invalid",
            "failed",
            "failure",
            "sorry",
            "unparseable",
            "none",
            "null",
            "unknown",
        ):
            assert word not in lowered, f"{text!r} names the mechanism: {word!r}"


def test_the_untitled_fallback_is_the_string_derive_title_actually_returns():
    """The constant is proven to be wired, not merely present.

    A copy constant that nothing returns is a string in a file. This asserts
    the whitespace arm of `derive_title` reaches for this one, so renaming the
    constant without updating `formatting.py` fails here.
    """
    assert derive_title("   ") == SESSION_UNTITLED_TITLE
    assert derive_title("") == SESSION_UNTITLED_TITLE


def test_transcript_notices_name_the_saving_and_never_the_answer():
    """STORY-014 AC 5 and AC 6, as copy rather than as behaviour.

    Both notices are full sentences in the interface's voice (frontend-design:
    "explain what went wrong and how to fix it... errors don't apologize"), and
    the two are *different strings* on purpose: only one of them may claim a
    turn was not saved, because only one of the two failures means that.
    """
    assert TRANSCRIPT_NOT_SAVED_NOTICE
    assert SESSION_ORDER_STALE_NOTICE
    assert TRANSCRIPT_NOT_SAVED_NOTICE != SESSION_ORDER_STALE_NOTICE

    for text in (TRANSCRIPT_NOT_SAVED_NOTICE, SESSION_ORDER_STALE_NOTICE):
        assert text[0].isupper() and text.endswith(".")
        for word in ("sorry", "apologise", "apologize", "oops", "unfortunately"):
            assert word not in text.lower()
        # No mechanism: the reader does not run the database.
        for word in ("sql", "database", "exception", "storageerror", "insert"):
            assert word not in text.lower()

    assert "not saved" in TRANSCRIPT_NOT_SAVED_NOTICE.lower()
    # The stale-order notice must not read as a lost turn -- AC 6.
    assert "not saved" not in SESSION_ORDER_STALE_NOTICE.lower()
    assert "saved" in SESSION_ORDER_STALE_NOTICE.lower()


def test_the_load_notice_says_the_screen_is_unchanged_and_claims_no_lost_turn():
    """STORY-015 AC 9, as copy.

    The third notice in this family, and the reason it is a third string
    rather than a reuse of either: a read that failed did not lose a turn, so
    "not saved" would be false here, and the reader needs to know which
    conversation the bubbles still on screen belong to.
    """
    assert TRANSCRIPT_NOT_LOADED_NOTICE

    notices = (
        TRANSCRIPT_NOT_SAVED_NOTICE,
        SESSION_ORDER_STALE_NOTICE,
        TRANSCRIPT_NOT_LOADED_NOTICE,
    )
    assert len(set(notices)) == 3

    # The same shape and voice rules the two STORY-014 notices are held to.
    assert TRANSCRIPT_NOT_LOADED_NOTICE[0].isupper()
    assert TRANSCRIPT_NOT_LOADED_NOTICE.endswith(".")
    for word in ("sorry", "apologise", "apologize", "oops", "unfortunately"):
        assert word not in TRANSCRIPT_NOT_LOADED_NOTICE.lower()
    for word in ("sql", "database", "exception", "storageerror", "select"):
        assert word not in TRANSCRIPT_NOT_LOADED_NOTICE.lower()

    # A failed *read* costs no turn: only the write notice may say so.
    assert "not saved" not in TRANSCRIPT_NOT_LOADED_NOTICE.lower()
    # AC 9's promise, in the string that makes it.
    assert "unchanged" in TRANSCRIPT_NOT_LOADED_NOTICE.lower()


def test_the_delete_confirmation_names_the_chat_and_keeps_the_record():
    """STORY-016 AC 7, as copy.

    PRD-008 Section 9 is the source: "`delete_chat_session` removes rows from
    `chat_sessions` and `chat_messages` only. `audit_logs` is append-only and
    stays so... The confirmation copy says this in the user's words." Both
    halves are asserted -- the promise is present, and the schema's vocabulary
    is absent. A confirmation that said "audit_logs rows are retained" would
    be true and useless; one that said nothing about the record would leave
    the reader in an audited system guessing at the one fact they want.
    """
    assert SESSION_DELETE_CONFIRM_TEMPLATE
    assert SESSION_DELETE_CONFIRM_LABEL

    # One placeholder, filled per row by STORY-018's rx.foreach.
    assert SESSION_DELETE_CONFIRM_TEMPLATE.count("{title}") == 1
    filled = SESSION_DELETE_CONFIRM_TEMPLATE.format(title="Q3 vendor spend")
    assert "Q3 vendor spend" in filled
    assert "{" not in filled and "}" not in filled

    # The promise the reader is owed, in the words they use.
    assert "kept" in SESSION_DELETE_CONFIRM_TEMPLATE.lower()
    # ...and never in the words the system uses.
    for word in (
        "audit",
        "audit_logs",
        "row",
        "rows",
        "table",
        "database",
        "sql",
        "schema",
        "chat_sessions",
        "chat_messages",
    ):
        assert word not in SESSION_DELETE_CONFIRM_TEMPLATE.lower()

    # The same voice rules the notices above are held to.
    assert SESSION_DELETE_CONFIRM_TEMPLATE[0].isupper()
    for word in ("sorry", "apologise", "apologize", "oops", "unfortunately"):
        assert word not in SESSION_DELETE_CONFIRM_TEMPLATE.lower()


def test_the_delete_action_keeps_its_name_through_the_flow():
    """The frontend-design skill, verbatim: "An action keeps the same name
    through the whole flow, so the button that says 'Publish' produces a toast
    that says 'Published.'"

    The affordance says Delete and so does its confirmation. Nothing in this
    flow says Remove -- a second word for one action is a second thing to
    learn, and the vocabulary of an interface is its signposting.
    """
    assert SESSION_DELETE_CONFIRM_LABEL == "Delete"
    assert "delete" in SESSION_DELETE_CONFIRM_TEMPLATE.lower()
    for text in (SESSION_DELETE_CONFIRM_TEMPLATE, SESSION_DELETE_CONFIRM_LABEL):
        assert "remove" not in text.lower()
        assert "discard" not in text.lower()


def test_the_delete_confirmation_is_permanent_about_the_chat_and_only_the_chat():
    """The one claim in the string that could be false in the wrong direction.

    Deleting a chat *is* permanent -- `database.delete_chat_session` drops the
    session and its messages in one transaction with no recovery path -- so
    saying so is accurate and the reader deserves it before they confirm. What
    must never be permanent-sounding is the record: the same string says it is
    kept, and the two claims must sit on opposite sides of the sentence.
    """
    lowered = SESSION_DELETE_CONFIRM_TEMPLATE.lower()
    # Whatever wording carries the finality, it is about the chat.
    assert "for good" in lowered or "permanent" in lowered or "cannot be undone" in lowered
    # And the record is kept in the same breath, so no reader confirms one
    # believing the other.
    assert "kept" in lowered


# --------------------------------------------------------------------------
# STORY-017 -- the rail's remaining strings.
#
# Appended, never edited above: `tests/test_copy.py` is one of the two suites
# `tests/test_untouched_app.py` pins by census, and every test above this line
# is untouched.
# --------------------------------------------------------------------------


def test_every_rail_string_exists_and_is_not_empty():
    """AC 8: the whole rail vocabulary, asserted by name.

    Existence is the cheap half; the point of listing them together is that
    STORY-018 can be written against this tuple and find nothing missing. The
    six constants STORY-012, STORY-014, STORY-015 and STORY-016 contributed are
    included, because "every rail string" is the claim -- not "every string
    this story happened to add".
    """
    rail_strings = (
        SESSION_NEW_CHAT_LABEL,
        SESSION_RAIL_EMPTY_TITLE,
        SESSION_RAIL_EMPTY_BODY,
        SESSION_RAIL_FAULT_TITLE,
        SESSION_RAIL_FAULT_BODY,
        SESSION_RAIL_SCOPE_TEMPLATE,
        SESSION_RENAME_LABEL,
        SESSION_RENAME_PLACEHOLDER,
        SESSION_DELETE_CANCEL_LABEL,
        SESSION_RAIL_SHOW_LABEL,
        # Contributed early by the stories that needed them first.
        SESSION_UNTITLED_TITLE,
        SESSION_ACTIVITY_UNKNOWN,
        SESSION_DELETE_CONFIRM_TEMPLATE,
        SESSION_DELETE_CONFIRM_LABEL,
        TRANSCRIPT_NOT_SAVED_NOTICE,
        SESSION_ORDER_STALE_NOTICE,
        TRANSCRIPT_NOT_LOADED_NOTICE,
    )
    for text in rail_strings:
        assert isinstance(text, str)
        assert text.strip(), f"empty rail string: {text!r}"

    # PRD-008 Section 6.1 fixes these two words, and the control, the action
    # and what it produces all carry them (frontend-design: "an action keeps
    # the same name through the whole flow").
    assert SESSION_NEW_CHAT_LABEL == "New chat"
    # The scope line states both halves or it is not a scope line (PRD-006
    # Risk 4), and it is the register's own wording rather than a second
    # phrasing of one idea.
    assert "{shown}" in SESSION_RAIL_SCOPE_TEMPLATE
    assert "{total}" in SESSION_RAIL_SCOPE_TEMPLATE
    assert SESSION_RAIL_SCOPE_TEMPLATE == admin_copy.REGISTER_SCOPE_TEMPLATE


def test_the_empty_rail_invites_a_chat_rather_than_reporting_none():
    """AC 6, and the skill verbatim: "an empty screen is an invitation to act".

    PRD-008 Section 6.1: "the empty rail reads as an invitation to start one
    rather than as a report that none exist." An invitation names an act and a
    census does not, so both halves are checked -- a census sentence ("No chats
    yet", "You have no chats") passes a non-emptiness check and fails this one,
    which is the whole reason this test exists beside the one above.
    """
    assert SESSION_RAIL_EMPTY_TITLE
    assert SESSION_RAIL_EMPTY_BODY

    lowered = f"{SESSION_RAIL_EMPTY_TITLE} {SESSION_RAIL_EMPTY_BODY}".lower()
    for absence in ("no chats", "nothing here", "empty", "none", "0 chats"):
        assert absence not in lowered, f"the empty rail reports absence: {absence!r}"
    # The invitation names the act. Both verbs are ones the surface actually
    # offers: New chat above the rail, and the composer below it.
    assert "start" in lowered or "send" in lowered

    # Sentence case, not Title Case, and no mechanism words: the copy module's
    # own register throughout (frontend-design: "plain verbs, sentence case, no
    # filler").
    for text in (SESSION_RAIL_EMPTY_TITLE, SESSION_RAIL_EMPTY_BODY):
        assert text == text[0].upper() + text[1:]
        assert not text.isupper()
        for mechanism in ("session", "row", "record", "database", "null"):
            assert mechanism not in text.lower(), f"{text!r} names the mechanism"


def test_the_rail_read_failure_names_the_read_and_offers_the_retry():
    """AC 7, and the skill verbatim: "errors don't apologize, and they are
    never vague about what happened".

    Three claims, and the third is the one that would rot silently. First, the
    line names what failed -- the reader's chats, not "data". Second, it offers
    the action, spelled with the same word its control carries, so RETRY_LABEL
    is asserted *into* the sentence rather than beside it (the shape
    admin_copy's REFRESH_LABEL / FAULT_MESSAGE_TEMPLATE pair uses). Third, it
    states that the screen did not move: STORY-015 established that a failed
    read leaves the transcript alone, and a fault line that omits that leaves
    the reader unsure which chat the bubbles belong to.
    """
    assert "chats" in SESSION_RAIL_FAULT_TITLE.lower()
    assert RETRY_LABEL.lower() in SESSION_RAIL_FAULT_BODY.lower()
    assert "nothing on screen has changed" in SESSION_RAIL_FAULT_BODY.lower()

    for text in (SESSION_RAIL_FAULT_TITLE, SESSION_RAIL_FAULT_BODY):
        lowered = text.lower()
        # No apology, in any of its usual disguises.
        for apology in ("sorry", "apolog", "unfortunately", "oops"):
            assert apology not in lowered, f"{text!r} apologizes"
        # No vagueness, and no mechanism. "Something went wrong" is the
        # sentence this loop exists to refuse.
        for vague in ("something went wrong", "an error", "try again later"):
            assert vague not in lowered, f"{text!r} is vague: {vague!r}"
        for mechanism in ("session", "exception", "traceback", "null", "500"):
            assert mechanism not in lowered, f"{text!r} names the mechanism"
