import pytest
from pydantic import ValidationError

from app.models.schemas import (
    AuditQueryEntry,
    AuditResponse,
    QueryBlockedDuplicateResponse,
    QueryBlockedSuspiciousResponse,
    QueryRequest,
    QuerySuccessResponse,
    StatsResponse,
)


def test_query_request_missing_user_id_raises():
    with pytest.raises(ValidationError):
        QueryRequest(prompt="hi")


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
            }
        ],
    }


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
    assert sorted(QueryRequest.model_fields) == [
        "device",
        "model",
        "openrouter_api_key",
        "prompt",
        "user_id",
    ]
    assert QueryRequest.model_fields["user_id"].is_required()
    assert QueryRequest.model_fields["prompt"].is_required()
