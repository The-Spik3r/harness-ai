from fastapi import APIRouter, Depends, HTTPException

from app.db.database import (
    count_audit_logs,
    count_blocked_duplicates,
    count_blocked_suspicious,
    count_pii_detected_queries,
    count_successful_queries,
    count_unique_users,
    list_audit_logs,
    top_models,
    top_pii_entities,
    top_users,
)
from app.middleware.auth import require_identity, require_permission
from app.models.schemas import AuditQueryEntry, AuditResponse, StatsResponse
from app.services.authz import (
    PERMISSION_AUDIT_READ_ALL,
    PERMISSION_AUDIT_READ_OWN,
    PERMISSION_STATS_READ,
    PermissionDenied,
    authorize,
)
from app.services.identity import Identity

router = APIRouter()


@router.get("/audit", response_model=AuditResponse)
def get_audit(identity: Identity = Depends(require_identity)) -> AuditResponse:
    try:
        authorize(identity, PERMISSION_AUDIT_READ_ALL)
        scope_user_id = None
    except PermissionDenied:
        try:
            authorize(identity, PERMISSION_AUDIT_READ_OWN)
        except PermissionDenied as exc:
            raise HTTPException(
                status_code=403, detail=f"Permission denied: {exc.permission}"
            ) from exc
        scope_user_id = identity.user_id

    total = count_audit_logs(user_id=scope_user_id)
    queries = [
        AuditQueryEntry(
            audit_id=log.id,
            user_id=log.user_id,
            role=log.role,
            denied_permission=log.denied_permission,
            timestamp=log.timestamp,
            model=log.model_used,
            prompt_hash=log.prompt_hash,
            was_duplicate_blocked=log.was_duplicate_blocked,
            suspicious_pattern_detected=log.suspicious_pattern is not None,
            device=log.device,
            pii_detected_input=log.pii_detected_input,
            pii_detected_output=log.pii_detected_output,
            pii_entities=log.pii_entities.split(",") if log.pii_entities else [],
        )
        for log in list_audit_logs(limit=100, user_id=scope_user_id)
    ]
    return AuditResponse(total=total, queries=queries)


@router.get(
    "/stats",
    response_model=StatsResponse,
    dependencies=[Depends(require_permission(PERMISSION_STATS_READ))],
)
def get_stats() -> StatsResponse:
    total = count_audit_logs()
    successful = count_successful_queries()
    success_rate = f"{(successful / total * 100):.1f}%" if total > 0 else "0.0%"

    return StatsResponse(
        total_queries=total,
        blocked_duplicates=count_blocked_duplicates(),
        blocked_suspicious=count_blocked_suspicious(),
        unique_users=count_unique_users(),
        success_rate=success_rate,
        top_models=top_models(),
        top_users=top_users(),
        pii_detected_queries=count_pii_detected_queries(),
        top_pii_entities=top_pii_entities(),
    )
