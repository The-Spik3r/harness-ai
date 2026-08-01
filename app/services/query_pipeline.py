from typing import Callable, Optional, Union

from app.models.schemas import (
    QueryBlockedDuplicateResponse,
    QueryBlockedSuspiciousResponse,
    QuerySuccessResponse,
)
from app.services.audit_logger import log_query
from app.services.duplicate_checker import check_duplicate
from app.services.openrouter_client import OpenRouterError, OpenRouterResult, call_openrouter
from app.services.pattern_detector import detect_suspicious_pattern
from app.services.pii_redactor import PiiRedactorError, redact

QueryPipelineResult = Union[
    QuerySuccessResponse, QueryBlockedDuplicateResponse, QueryBlockedSuspiciousResponse
]


def run_query(
    user_id: str,
    prompt: str,
    device: Optional[str],
    model: str,
    openrouter_api_key: Optional[str],
    call_openrouter: Callable[..., OpenRouterResult] = call_openrouter,
) -> QueryPipelineResult:
    duplicate_result = check_duplicate(prompt)

    if duplicate_result.is_duplicate:
        log_query(
            user_id=user_id,
            prompt=prompt,
            device=device,
            was_duplicate_blocked=True,
            success=True,
        )
        return QueryBlockedDuplicateResponse(
            reason="Duplicate query within 24 hours",
            first_query_at=duplicate_result.first_query_at,
        )

    pattern_result = detect_suspicious_pattern(prompt)
    if pattern_result.is_suspicious:
        log_query(
            user_id=user_id,
            prompt=prompt,
            device=device,
            suspicious_pattern=pattern_result.pattern,
            success=True,
        )
        return QueryBlockedSuspiciousResponse(
            reason="Suspicious pattern detected",
            pattern=pattern_result.pattern,
        )

    try:
        redacted_prompt, input_entities = redact(prompt)
    except PiiRedactorError as exc:
        log_query(
            user_id=user_id,
            prompt=prompt,
            device=device,
            success=False,
            error_message=str(exc),
        )
        raise

    try:
        openrouter_result = call_openrouter(
            redacted_prompt, model=model, api_key=openrouter_api_key
        )
    except OpenRouterError as exc:
        log_query(
            user_id=user_id,
            prompt=prompt,
            device=device,
            model_used=model,
            success=False,
            error_message=str(exc),
        )
        raise

    try:
        redacted_response, output_entities = redact(openrouter_result.response)
    except PiiRedactorError as exc:
        log_query(
            user_id=user_id,
            prompt=prompt,
            device=device,
            response=openrouter_result.response,
            model_used=openrouter_result.model_used,
            tokens_used=openrouter_result.tokens_used,
            success=False,
            error_message=str(exc),
            pii_detected_input=bool(input_entities),
            pii_entities=input_entities,
        )
        raise

    audit_id = log_query(
        user_id=user_id,
        prompt=prompt,
        device=device,
        response=openrouter_result.response,
        model_used=openrouter_result.model_used,
        tokens_used=openrouter_result.tokens_used,
        success=True,
        pii_detected_input=bool(input_entities),
        pii_detected_output=bool(output_entities),
        pii_entities=sorted(set(input_entities) | set(output_entities)),
    )

    return QuerySuccessResponse(
        response=redacted_response,
        audit_id=audit_id,
        model_used=openrouter_result.model_used,
        tokens_used=openrouter_result.tokens_used,
    )
