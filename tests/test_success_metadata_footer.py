import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "chat_ui"))

import pytest
from chat_ui.chat_ui.models import ChatMessage
from chat_ui.chat_ui import copy


def test_footer_copy_constants():
    """Verify footer copy constants are defined correctly."""
    assert copy.FOOTER_SEPARATOR == " · "
    assert copy.FOOTER_TOKENS_LABEL == "tokens"
    assert copy.FOOTER_AUDIT_PREFIX == "#"


def test_chat_message_metadata_fields():
    """Verify ChatMessage supports model_used, tokens_used, and audit_id fields."""
    msg = ChatMessage(
        kind="assistant",
        content="Hello",
        model_used="gpt-4",
        tokens_used=45,
        audit_id=127,
    )
    assert msg.model_used == "gpt-4"
    assert msg.tokens_used == 45
    assert msg.audit_id == 127
