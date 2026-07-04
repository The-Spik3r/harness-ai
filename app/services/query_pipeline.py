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
        openrouter_result = call_openrouter(prompt, model=model, api_key=openrouter_api_key)
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

    audit_id = log_query(
        user_id=user_id,
        prompt=prompt,
        device=device,
        response=openrouter_result.response,
        model_used=openrouter_result.model_used,
        tokens_used=openrouter_result.tokens_used,
        success=True,
    )

    return QuerySuccessResponse(
        response=openrouter_result.response,
        audit_id=audit_id,
        model_used=openrouter_result.model_used,
        tokens_used=openrouter_result.tokens_used,
    )
