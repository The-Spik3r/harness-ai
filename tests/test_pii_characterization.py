"""PRD-012 STORY-002: today's redact() and pipeline steps 6 and 8, pinned before anything moves.

**Every assertion in this module is a frozen record of pre-PRD-012 `chat`
behaviour. None of it is a requirement.** It was pinned green on untouched code
before any PRD-012 change (PRD-012 Section 6.10, "Characterization first"; the
precedents are PRD-009 STORY-001 and PRD-011 STORY-001). Unlike those two, no
story in this PRD flips a pin: `chat` must not move by a byte (PRD-012 Section
11, *Functional requirements*, first line), and STORY-014 checks that no
assertion here changed. A story that believes one must change stops and raises
it; it does not edit the pin.

**The real model, the shipped settings.** `redact()` runs on `en_core_web_lg`
with the four `PII_*` values `app/config.py` ships. `_shipped_pii_settings`
pins them per test and asserts the large model is the one in use, because
`tests/conftest.py` pins no `PII_*` setting and `tests/test_pii_redactor.py`
swaps in `en_core_web_sm`: a developer's `.env` or a leaked singleton must not
change what "today" means. Only `call_openrouter` is stubbed.

**Two quirks are pinned on purpose, not endorsed.** In the last conversation
case the NER span swallows a leading `Call` (`Call Aisha Bello` becomes
`<PERSON>`), and the audit row's `response_preview` and `response_hash` are
of the model's response **unmasked** (step 8 logs `openrouter_result.response`;
the preview is its first 500 characters, which every case here fits in).
Both are what `chat`
does today. Changing either is a separate, announced change, not a side effect
of PRD-012.

**Audit PII fields follow PRD-010 D7.** Only the last user turn's entities
and the output's count; entities masked in history are not recorded. The
stored `pii_entities` is a comma-joined string, or `None` when empty
(`app/services/audit_logger.py`), and is asserted as exactly that.

STORY-009 and STORY-014 may import `REDACT_CASES` and `CONVERSATION_CASES`
(the `tests.test_pattern_characterization` import precedent). They must not
copy them.
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

from dataclasses import dataclass
from typing import Any, Optional

import pytest

from app.config import settings
from app.db.database import get_audit_log
from app.models.messages import Message
from app.models.schemas import QuerySuccessResponse
from app.services.duplicate_checker import hash_prompt
from app.services.identity import Identity
from app.services.openrouter_client import OpenRouterResult
import app.services.pii_redactor as pii_redactor
import app.services.query_pipeline as query_pipeline

#: The four PII settings as shipped (app/config.py:82-85). Pinned per test
#: because conftest pins none of them and tests/test_pii_redactor.py swaps in
#: the small model: a developer's .env or a leaked singleton must not change
#: what "today" means.
_SHIPPED_PII_SETTINGS = {
    "PII_REDACTION_ENABLED": True,
    "PII_SCORE_THRESHOLD": 0.35,
    "PII_ENTITIES": "PERSON,EMAIL_ADDRESS,PHONE_NUMBER,CREDIT_CARD,US_SSN,IBAN_CODE,LOCATION",
    "PII_NLP_MODEL": "en_core_web_lg",
}

_LARGE_MODEL_NAME = "core_web_lg"


def _model_name(analyzer) -> str:
    return analyzer.nlp_engine.nlp["en"].meta["name"]


@pytest.fixture(autouse=True)
def _shipped_pii_settings(monkeypatch):
    for name, value in _SHIPPED_PII_SETTINGS.items():
        monkeypatch.setattr(settings, name, value)
    # Reset only a cached analyzer built on another model: an unconditional
    # reset would reload the large model for every test, and monkeypatch
    # restores the previous singleton afterwards either way.
    cached = pii_redactor._analyzer
    if cached is not None and _model_name(cached) != _LARGE_MODEL_NAME:
        monkeypatch.setattr(pii_redactor, "_analyzer", None)
    assert _model_name(pii_redactor._get_analyzer()) == _LARGE_MODEL_NAME
    yield


# --- AC 1: redact() -------------------------------------------------------------

#: (text, expected_text, expected_entities) -- redact()'s output on untouched
#: code, measured 2026-09-24 on epic/PRD-012-pii-for-code @ f98c57b with
#: presidio-analyzer/anonymizer 2.2.364, spaCy 3.8.16, en_core_web_lg 3.8.0,
#: phonenumbers 9.0.38. Every value is from the STORY-001 synthetic set
#: (tests/corpora/pii/SOURCES.md).
REDACT_CASES = [
    # No PII: returned unchanged, no entities.
    ("How do I reverse a linked list in Python?",
     "How do I reverse a linked list in Python?", []),
    # Empty: short-circuits before the analyzer.
    ("", "", []),
    # Already masked: placeholders are not re-detected (PRD-012 T9).
    ("Forward this to <PERSON> at <EMAIL_ADDRESS> when you can.",
     "Forward this to <PERSON> at <EMAIL_ADDRESS> when you can.", []),
    ("My name is Jane Doe and my email is jane.doe@example.com.",
     "My name is <PERSON> and my email is <EMAIL_ADDRESS>.", ["EMAIL_ADDRESS", "PERSON"]),
    # A bare 555-01xx phone scores 0.40: masked at chat's 0.35.
    ("Please call Maria Lopez on +1 415 555 0134 tomorrow.",
     "Please call <PERSON> on <PHONE_NUMBER> tomorrow.", ["PERSON", "PHONE_NUMBER"]),
    ("Charge the refund to card 4111 1111 1111 1111, please.",
     "Charge the refund to card <CREDIT_CARD>, please.", ["CREDIT_CARD"]),
    ("My social security number is 219-09-9999.",
     "My social security number is <US_SSN>.", ["US_SSN"]),
    ("Wire the salary to IBAN GB82 WEST 1234 5698 7654 32.",
     "Wire the salary to IBAN <IBAN_CODE>.", ["IBAN_CODE"]),
    # The apostrophe name is one span.
    ("Patrick O'Brien lives in Seattle.",
     "<PERSON> lives in <LOCATION>.", ["LOCATION", "PERSON"]),
    ("Tomás Herrera and Zoë Müller-Schmidt met in Berlin.",
     "<PERSON> and <PERSON> met in <LOCATION>.", ["LOCATION", "PERSON"]),
    # PRD-012 Section 1's example: what chat does to a line of code today.
    ('author = "Jane Doe"', 'author = "<PERSON>"', ["PERSON"]),
    # Every default entity type in one prompt.
    ("Priya Raghunathan (priya.raghunathan@example.com, phone +1 212 555 0147) moved to "
     "Chicago; her card 5555 5555 5555 4444, SSN 219-09-9999 (social security number), "
     "IBAN DE89370400440532013000.",
     "<PERSON> (<EMAIL_ADDRESS>, phone <PHONE_NUMBER>) moved to <LOCATION>; her card "
     "<CREDIT_CARD>, SSN <US_SSN> (social security number), IBAN <IBAN_CODE>.",
     ["CREDIT_CARD", "EMAIL_ADDRESS", "IBAN_CODE", "LOCATION", "PERSON", "PHONE_NUMBER",
      "US_SSN"]),
]

_REDACT_IDS = [
    "no-pii",
    "empty",
    "already-masked",
    "person-email",
    "person-phone",
    "card",
    "ssn",
    "iban",
    "apostrophe-name-location",
    "non-ascii-names",
    "code-string-literal",
    "every-default-entity",
]


@pytest.mark.parametrize("text,expected_text,expected_entities", REDACT_CASES, ids=_REDACT_IDS)
def test_redact_output_is_pinned(text, expected_text, expected_entities):
    # One tuple comparison: the masked bytes and the sorted entity order together.
    assert pii_redactor.redact(text) == (expected_text, expected_entities)


def test_the_every_entity_case_covers_every_default_entity():
    _, _, entities = REDACT_CASES[_REDACT_IDS.index("every-default-entity")]
    assert entities == sorted(settings.pii_entities_list)


def test_the_redact_cases_include_the_required_shapes():
    assert len(REDACT_CASES) == len(_REDACT_IDS)
    assert len(REDACT_CASES) >= 10, "AC 1 needs at least ten prompts"
    assert any(
        text and entities == [] and "<" not in text for text, _, entities in REDACT_CASES
    ), "no case without PII"
    assert any(
        "<PERSON>" in text and expected == text and entities == []
        for text, expected, entities in REDACT_CASES
    ), "no already-masked <PERSON> case"


# --- AC 2-4: run_conversation steps 6 and 8 -----------------------------------------

_ANALYST = Identity(user_id="analyst-7", role="user")
_MODEL = "gpt-4"
_TOKENS = 42


@dataclass(frozen=True)
class ConversationCase:
    id: str
    messages: tuple[Message, ...]
    upstream_response: str
    #: The exact list call_openrouter receives, roles and order included.
    expected_sent: tuple[Message, ...]
    #: QuerySuccessResponse.model_dump() without audit_id, which the DB assigns.
    expected_result: dict[str, Any]
    #: The audit row's PII fields and response preview, as get_audit_log returns them.
    expected_row: dict[str, Optional[Any]]


def _result(response: str, entities: list[str]) -> dict[str, Any]:
    return {
        "status": "SUCCESS",
        "response": response,
        "model_used": _MODEL,
        "tokens_used": _TOKENS,
        "pii_redacted": bool(entities),
        "pii_entities_masked": entities,
    }


#: Measured with the redact() cases above (same date, commit and versions).
CONVERSATION_CASES = [
    # AC 2: PII in the new user turn only.
    ConversationCase(
        id="pii-in-last-turn",
        messages=(
            Message("user", "How do I reverse a linked list in Python?"),
            Message("assistant", "Iterate once and flip each next pointer."),
            Message("user", "My name is Jane Doe and my email is jane.doe@example.com."),
        ),
        upstream_response="Noted. I will not repeat your details.",
        expected_sent=(
            Message("user", "How do I reverse a linked list in Python?"),
            Message("assistant", "Iterate once and flip each next pointer."),
            Message("user", "My name is <PERSON> and my email is <EMAIL_ADDRESS>."),
        ),
        expected_result=_result(
            "Noted. I will not repeat your details.", ["EMAIL_ADDRESS", "PERSON"]
        ),
        expected_row={
            "pii_detected_input": True,
            "pii_detected_output": False,
            "pii_entities": "EMAIL_ADDRESS,PERSON",
            "response_preview": "Noted. I will not repeat your details.",
        },
    ),
    # AC 3, PRD-010 D7: PII in history only is masked upstream and not recorded.
    ConversationCase(
        id="pii-in-history-only",
        messages=(
            Message("user", "Please call Maria Lopez on +1 415 555 0134 tomorrow."),
            Message("assistant", "I will remind you to call Maria Lopez on +1 415 555 0134."),
            Message("user", "Can you summarise that reminder?"),
        ),
        upstream_response="You asked to be reminded about a call tomorrow.",
        expected_sent=(
            Message("user", "Please call <PERSON> on <PHONE_NUMBER> tomorrow."),
            Message("assistant", "I will remind you to call <PERSON> on <PHONE_NUMBER>."),
            Message("user", "Can you summarise that reminder?"),
        ),
        expected_result=_result("You asked to be reminded about a call tomorrow.", []),
        expected_row={
            "pii_detected_input": False,
            "pii_detected_output": False,
            "pii_entities": None,
            "response_preview": "You asked to be reminded about a call tomorrow.",
        },
    ),
    # AC 4: PII in the response only; returned masked, previewed unmasked.
    ConversationCase(
        id="pii-in-response-only",
        messages=(Message("user", "Who owns the billing service?"),),
        upstream_response=(
            "Please contact John Smith at john.smith@example.com or phone 212-555-0199."
        ),
        expected_sent=(Message("user", "Who owns the billing service?"),),
        expected_result=_result(
            "Please contact <PERSON> at <EMAIL_ADDRESS> or phone <PHONE_NUMBER>.",
            ["EMAIL_ADDRESS", "PERSON", "PHONE_NUMBER"],
        ),
        expected_row={
            "pii_detected_input": False,
            "pii_detected_output": True,
            "pii_entities": "EMAIL_ADDRESS,PERSON,PHONE_NUMBER",
            "response_preview": "Please contact John Smith at john.smith@example.com or phone 212-555-0199.",
        },
    ),
    # A different type in history (IBAN), the last turn (email) and the response
    # (person, phone): IBAN_CODE is masked but absent from the row (D7). Two
    # quirks pinned, not endorsed: `Call` is swallowed into <PERSON>, and the
    # row's response preview is unmasked.
    ConversationCase(
        id="pii-in-history-last-turn-and-response",
        messages=(
            Message("user", "Wire the salary to IBAN GB82 WEST 1234 5698 7654 32."),
            Message("assistant", "Done. The transfer to GB82 WEST 1234 5698 7654 32 is queued."),
            Message("user", "Send the receipt to ops@example.org."),
        ),
        upstream_response=(
            "Sent. Call Aisha Bello on phone +1 415 555 0134 if it does not arrive."
        ),
        expected_sent=(
            Message("user", "Wire the salary to IBAN <IBAN_CODE>."),
            Message("assistant", "Done. The transfer to <IBAN_CODE> is queued."),
            Message("user", "Send the receipt to <EMAIL_ADDRESS>."),
        ),
        expected_result=_result(
            "Sent. <PERSON> on phone <PHONE_NUMBER> if it does not arrive.",
            ["EMAIL_ADDRESS", "PERSON", "PHONE_NUMBER"],
        ),
        expected_row={
            "pii_detected_input": True,
            "pii_detected_output": True,
            "pii_entities": "EMAIL_ADDRESS,PERSON,PHONE_NUMBER",
            "response_preview": "Sent. Call Aisha Bello on phone +1 415 555 0134 if it does not arrive.",
        },
    ),
]


def _case(case_id: str) -> ConversationCase:
    return next(case for case in CONVERSATION_CASES if case.id == case_id)


def _recording_stub(calls: list, response: str):
    # No `params`: the (messages, model, api_key) shape query_pipeline.py keeps
    # working by forwarding params only when set.
    def _call(messages, model=_MODEL, api_key=None):
        calls.append(list(messages))
        return OpenRouterResult(response=response, model_used=model, tokens_used=_TOKENS)

    return _call


@pytest.mark.parametrize("profile", [None, "chat"], ids=["default", "chat"])
@pytest.mark.parametrize("case", CONVERSATION_CASES, ids=[c.id for c in CONVERSATION_CASES])
def test_chat_conversation_is_pinned(temp_db, case, profile):
    # `profile=None` is the call-site default /query and ChatState use;
    # `"chat"` is the explicit name STORY-009's get_pii_policy resolves. Both
    # must produce these exact bytes.
    calls: list = []

    result = query_pipeline.run_conversation(
        identity=_ANALYST, messages=list(case.messages), device=None, model=_MODEL,
        openrouter_api_key=None,
        call_openrouter=_recording_stub(calls, case.upstream_response),
        profile=profile,
    )

    assert isinstance(result, QuerySuccessResponse)
    assert calls == [list(case.expected_sent)]
    assert result.model_dump(exclude={"audit_id"}) == case.expected_result

    row = get_audit_log(result.audit_id)
    assert {
        "pii_detected_input": row.pii_detected_input,
        "pii_detected_output": row.pii_detected_output,
        "pii_entities": row.pii_entities,
        "response_preview": row.response_preview,
    } == case.expected_row
    # The hash, like the preview, is of the unmasked response.
    assert row.response_hash == hash_prompt(case.upstream_response)


def test_the_conversation_cases_are_chat_shaped():
    for case in CONVERSATION_CASES:
        roles = [message.role for message in case.messages]
        assert "system" not in roles, f"{case.id}: has a system turn"
        assert roles[-1] == "user", f"{case.id}: does not end in a user turn"
        if case.id != "pii-in-response-only":
            assert len(roles) >= 3, f"{case.id}: no history"
        assert [m.role for m in case.expected_sent] == roles, f"{case.id}: roles differ"


def test_the_history_only_case_masks_history_and_records_nothing():
    case = _case("pii-in-history-only")
    assert case.expected_sent[:-1] != case.messages[:-1], "history is not masked"
    assert case.expected_sent[-1] == case.messages[-1]
    assert case.expected_row["pii_detected_input"] is False
    assert case.expected_row["pii_entities"] is None


def test_the_response_case_masks_the_response():
    case = _case("pii-in-response-only")
    assert case.expected_result["response"] != case.upstream_response
    assert case.expected_row["pii_detected_output"] is True
