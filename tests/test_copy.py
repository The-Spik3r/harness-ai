import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from chat_ui.chat_ui.copy import (
    USER_ID_PROMPT_TITLE,
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
    SHELL_CHANGE_USER_LABEL,
    SHELL_MODEL_SLOT_LABEL,
    EMPTY_STATE_TITLE,
    EMPTY_STATE_SUBTITLE,
    EMPTY_STATE_PII_FEATURE,
    EMPTY_STATE_SECURITY_FEATURE,
    EMPTY_STATE_DEDUP_FEATURE,
)
from chat_ui.chat_ui.formatting import format_duplicate_info

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
    DETAIL_TIMESTAMP_LABEL,
    DETAIL_PROMPT_HASH_LABEL,
    DETAIL_ERROR_LABEL,
    DETAIL_PATTERN_LABEL,
    DETAIL_DEVICE_LABEL,
    DETAIL_PII_ENTITIES_LABEL,
    DETAIL_PII_INPUT_LABEL,
    DETAIL_PII_OUTPUT_LABEL,
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
    assert USER_ID_PROMPT_TITLE
    assert COMPOSER_PLACEHOLDER == "Message..."
    assert WELCOME_MESSAGE_CONTENT
    assert RETRY_LABEL == "Retry"
    assert EDIT_AND_RESEND_LABEL == "Edit and resend"
    assert SHELL_HEADER_TITLE
    assert SHELL_HEADER_BADGE
    assert SHELL_USER_LABEL
    assert SHELL_CHANGE_USER_LABEL
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
