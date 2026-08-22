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
)


def test_copy_constants_exist_and_not_empty():
    """Verify all critical copy strings are non-empty and accessible."""
    assert USER_ID_PROMPT_TITLE
    assert COMPOSER_PLACEHOLDER == "Message..."
    assert WELCOME_MESSAGE_CONTENT
    assert RETRY_LABEL == "Retry"
    assert EDIT_AND_RESEND_LABEL == "Edit and resend"


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
