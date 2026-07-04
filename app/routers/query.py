from fastapi import APIRouter, HTTPException

from app.models.schemas import (
    QueryBlockedDuplicateResponse,
    QueryBlockedSuspiciousResponse,
    QueryRequest,
    QueryResponse,
    QuerySuccessResponse,
)
from app.services.audit_logger import log_query
from app.services.duplicate_checker import DuplicateCheckError, check_duplicate
from app.services.openrouter_client import OpenRouterError, call_openrouter
from app.services.pattern_detector import detect_suspicious_pattern

router = APIRouter()


@router.post("/query", response_model=QueryResponse)
def query(request: QueryRequest) -> QueryResponse:
    if not request.user_id.strip():
        raise HTTPException(status_code=400, detail="user_id is required")

    try:
        duplicate_result = check_duplicate(request.prompt)
    except DuplicateCheckError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if duplicate_result.is_duplicate:
        log_query(
            user_id=request.user_id,
            prompt=request.prompt,
            device=request.device,
            was_duplicate_blocked=True,
            success=True,
        )
        return QueryBlockedDuplicateResponse(
            reason="Duplicate query within 24 hours",
            first_query_at=duplicate_result.first_query_at,
        )

    pattern_result = detect_suspicious_pattern(request.prompt)
    if pattern_result.is_suspicious:
        log_query(
            user_id=request.user_id,
            prompt=request.prompt,
            device=request.device,
            suspicious_pattern=pattern_result.pattern,
            success=True,
        )
        return QueryBlockedSuspiciousResponse(
            reason="Suspicious pattern detected",
            pattern=pattern_result.pattern,
        )

    try:
        openrouter_result = call_openrouter(
            request.prompt,
            model=request.model,
            api_key=request.openrouter_api_key,
        )
    except OpenRouterError as exc:
        log_query(
            user_id=request.user_id,
            prompt=request.prompt,
            device=request.device,
            model_used=request.model,
            success=False,
            error_message=str(exc),
        )
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    audit_id = log_query(
        user_id=request.user_id,
        prompt=request.prompt,
        device=request.device,
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
