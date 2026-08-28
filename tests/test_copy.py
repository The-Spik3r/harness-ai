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


def test_duplicate_formatting_empty_and_unparseable_fallback():
    """AC3: Empty or unparseable first_query_at renders fallback without crash ('No silent drops')."""
    main_empty, release_empty = format_duplicate_info("")
    assert main_empty == "Already submitted recently."
    assert release_empty == ""

    main_bad, release_bad = format_duplicate_info("not-a-timestamp")
    assert "Already sent at not-a-timestamp" in main_bad
    assert release_bad == ""
