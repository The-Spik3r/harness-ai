import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "chat_ui"))

import pytest
from chat_ui.chat_ui.models import ChatMessage
from chat_ui.chat_ui import copy


def test_pii_badge_copy_templates():
    """Verify PII badge copy templates use entity types and exchange phrasing."""
    assert "masked in this exchange" in copy.PII_BADGE_TEMPLATE
    assert "1 PII type" in copy.PII_BADGE_SINGLE_TEMPLATE
    formatted_single = copy.PII_BADGE_SINGLE_TEMPLATE.format(entities="EMAIL_ADDRESS")
    assert "EMAIL_ADDRESS" in formatted_single
    formatted_multi = copy.PII_BADGE_TEMPLATE.format(count=2, entities="PERSON, EMAIL_ADDRESS")
    assert "2 PII types" in formatted_multi
    assert "PERSON, EMAIL_ADDRESS" in formatted_multi


def test_chat_message_pii_fields():
    """Verify ChatMessage supports pii_redacted and pii_entities fields."""
    msg = ChatMessage(
        kind="assistant",
        content="Hello",
        pii_redacted=True,
        pii_entities=["PERSON"],
    )
    assert msg.pii_redacted is True
    assert msg.pii_entities == ["PERSON"]
