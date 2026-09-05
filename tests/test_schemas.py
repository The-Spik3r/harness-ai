import pytest
from pydantic import ValidationError

from app.models.schemas import (
    AuditQueryEntry,
    AuditResponse,
    QueryBlockedDuplicateResponse,
    QueryBlockedForbiddenResponse,
    QueryBlockedSuspiciousResponse,
    QueryRequest,
    QuerySuccessResponse,
    StatsResponse,
)


def test_query_request_missing_user_id_defaults_to_none():
    request = QueryRequest(prompt="hi")
    assert request.user_id is None


def test_query_request_missing_prompt_raises():
    with pytest.raises(ValidationError):
        QueryRequest(user_id="juan@empresa.com")


def test_query_request_defaults():
    request = QueryRequest(user_id="juan@empresa.com", prompt="hi")
    assert request.model == "gpt-4"
    assert request.openrouter_api_key is None
    assert request.device is None


def test_query_success_response_shape():
    response = QuerySuccessResponse(
        response="La respuesta del modelo",
        audit_id=1,
        model_used="gpt-4",
        tokens_used=45,
    )
    assert response.model_dump() == {
        "status": "SUCCESS",
        "response": "La respuesta del modelo",
        "audit_id": 1,
        "model_used": "gpt-4",
        "tokens_used": 45,
        "pii_redacted": False,
        "pii_entities_masked": [],
    }


def test_query_blocked_duplicate_response_shape():
    response = QueryBlockedDuplicateResponse(
        reason="Duplicate query within 24 hours",
        first_query_at="2026-07-04T10:30:00Z",
    )
    assert response.model_dump() == {
        "status": "BLOCKED",
        "reason": "Duplicate query within 24 hours",
        "first_query_at": "2026-07-04T10:30:00Z",
    }


def test_query_blocked_suspicious_response_shape():
    response = QueryBlockedSuspiciousResponse(
        reason="Suspicious pattern detected",
        pattern="prompt_injection",
    )
    assert response.model_dump() == {
        "status": "BLOCKED",
        "reason": "Suspicious pattern detected",
        "pattern": "prompt_injection",
    }


def test_query_blocked_forbidden_response_shape():
    response = QueryBlockedForbiddenResponse(
        reason="Model not permitted for this role",
        required_permission="query:model:anthropic/claude-3.5-sonnet",
    )
    assert response.model_dump() == {
        "status": "BLOCKED",
        "reason": "Model not permitted for this role",
        "required_permission": "query:model:anthropic/claude-3.5-sonnet",
    }


def test_audit_response_shape():
    entry = AuditQueryEntry(
        audit_id=1,
        user_id="juan@empresa.com",
        timestamp="2026-07-04T10:30:00Z",
        model="gpt-4",
        prompt_hash="abc123def456",
        was_duplicate_blocked=False,
        suspicious_pattern_detected=False,
        device="Chrome/Windows",
    )
    response = AuditResponse(total=250, queries=[entry])
    assert response.model_dump() == {
        "total": 250,
        "queries": [
            {
                "audit_id": 1,
                "user_id": "juan@empresa.com",
                "timestamp": "2026-07-04T10:30:00Z",
                "model": "gpt-4",
                "prompt_hash": "abc123def456",
                "was_duplicate_blocked": False,
                "suspicious_pattern_detected": False,
                "device": "Chrome/Windows",
                "pii_detected_input": False,
                "pii_detected_output": False,
                "pii_entities": [],
                "role": None,
                "denied_permission": None,
                # PRD-008 STORY-011. The entry above is constructed without
                # `session_id`, so `None` here is the default being asserted
                # rather than merely accommodated.
                "session_id": None,
            }
        ],
    }


def test_audit_query_entry_session_id_is_optional_with_a_none_default():
    """STORY-011 AC 6, asserted on the field rather than on a serialized row.

    `test_audit_response_shape` above shows what an omitted `session_id`
    serializes to; this shows *why* omitting it is allowed at all. A required
    field here would break every existing constructor -- the one in that test,
    and the projection in `app/routers/admin.py` for as long as any row
    predates the column.
    """
    field = AuditQueryEntry.model_fields["session_id"]

    assert field.is_required() is False
    assert field.default is None


def test_stats_response_shape():
    response = StatsResponse(
        total_queries=250,
        blocked_duplicates=12,
        blocked_suspicious=3,
        unique_users=8,
        success_rate="98.4%",
        top_models=["gpt-4", "claude-3-sonnet"],
        top_users=["juan@empresa.com", "maria@empresa.com"],
    )
    assert response.model_dump() == {
        "total_queries": 250,
        "blocked_duplicates": 12,
        "blocked_suspicious": 3,
        "unique_users": 8,
        "success_rate": "98.4%",
        "top_models": ["gpt-4", "claude-3-sonnet"],
        "top_users": ["juan@empresa.com", "maria@empresa.com"],
        "pii_detected_queries": 0,
        "top_pii_entities": [],
    }


def test_query_success_response_with_pii_signal_shape():
    response = QuerySuccessResponse(
        response="Sure, I'll draft a reply to <EMAIL_ADDRESS>.",
        audit_id=1,
        model_used="gpt-4",
        tokens_used=45,
        pii_redacted=True,
        pii_entities_masked=["EMAIL_ADDRESS"],
    )
    assert response.model_dump() == {
        "status": "SUCCESS",
        "response": "Sure, I'll draft a reply to <EMAIL_ADDRESS>.",
        "audit_id": 1,
        "model_used": "gpt-4",
        "tokens_used": 45,
        "pii_redacted": True,
        "pii_entities_masked": ["EMAIL_ADDRESS"],
    }


def test_query_success_response_pii_defaults_are_not_shared_between_instances():
    first = QuerySuccessResponse(
        response="a", audit_id=1, model_used="gpt-4", tokens_used=1
    )
    second = QuerySuccessResponse(
        response="b", audit_id=2, model_used="gpt-4", tokens_used=1
    )
    first.pii_entities_masked.append("PERSON")

    assert second.pii_entities_masked == []


def test_query_request_contract_is_unchanged():
    """`session_id` joined the contract in PRD-008 STORY-010.

    The name still reads "unchanged" because what it guards is unchanged: the
    field list is enumerated so that adding one is a decision somebody makes
    here, in a test, rather than a thing that happens. STORY-010 made it, and
    the two clauses below say what the new field promises -- optional and
    defaulted, so a client written against the previous release is unaffected.
    """
    assert sorted(QueryRequest.model_fields) == [
        "device",
        "model",
        "openrouter_api_key",
        "prompt",
        "session_id",
        "user_id",
    ]
    assert not QueryRequest.model_fields["user_id"].is_required()
    assert QueryRequest.model_fields["user_id"].default is None
    assert QueryRequest.model_fields["prompt"].is_required()
    assert not QueryRequest.model_fields["session_id"].is_required()
    assert QueryRequest.model_fields["session_id"].default is None


def test_query_request_accepts_a_uuid4_session_id_unchanged():
    """PRD-008 STORY-010 AC 1. Returned verbatim, not normalized or re-parsed:
    the value is written to the audit column as supplied."""
    session_id = "0f6c2e5a-9b3d-4c81-a7f2-1d5e8c9b0a34"

    request = QueryRequest(prompt="hi", session_id=session_id)

    assert request.session_id == session_id


def test_query_request_omitting_session_id_is_none():
    """AC 2 at the model level. Absence is not something the validator has an
    opinion about."""
    assert QueryRequest(prompt="hi").session_id is None


@pytest.mark.parametrize(
    "value",
    [
        "not-a-uuid",
        "",
        "0f6c2e5a9b3d4c81a7f21d5e8c9b0a34",
        "{0f6c2e5a-9b3d-4c81-a7f2-1d5e8c9b0a34}",
        "urn:uuid:0f6c2e5a-9b3d-4c81-a7f2-1d5e8c9b0a34",
        "0F6C2E5A-9B3D-4C81-A7F2-1D5E8C9B0A34",
        "d2b8f1e4-5c3a-11ee-9b0a-0242ac120002",
    ],
    ids=[
        "not-a-uuid",
        "empty",
        "unhyphenated",
        "braced",
        "urn",
        "uppercase",
        "version-1",
    ],
)
def test_query_request_refuses_anything_but_a_canonical_uuid4(value):
    """AC 3, and AC 1's "UUID4" taken literally.

    The last four cases all parse as UUIDs. They are refused because each is a
    *second representation of the same id*, and the id is a database key
    compared with `=` -- a value the harness never minted is one no `WHERE`
    clause will ever match.
    """
    with pytest.raises(ValidationError):
        QueryRequest(prompt="hi", session_id=value)


def test_query_request_session_id_error_names_the_field():
    """An integrating developer is told which field, not merely that something
    failed -- the error travels to them inside Pydantic's 422 body."""
    with pytest.raises(ValidationError) as caught:
        QueryRequest(prompt="hi", session_id="not-a-uuid")

    assert caught.value.errors()[0]["loc"] == ("session_id",)
