from fastapi import APIRouter, Depends

from app.db.database import (
    count_audit_logs,
    count_blocked_duplicates,
    count_blocked_suspicious,
    count_successful_queries,
    count_unique_users,
    list_audit_logs,
    top_models,
    top_users,
)
from app.middleware.auth import require_admin_token
from app.models.schemas import AuditQueryEntry, AuditResponse, StatsResponse

router = APIRouter()


@router.get(
    "/audit",
    response_model=AuditResponse,
    dependencies=[Depends(require_admin_token)],
)
def get_audit() -> AuditResponse:
    total = count_audit_logs()
    queries = [
        AuditQueryEntry(
            audit_id=log.id,
            user_id=log.user_id,
            timestamp=log.timestamp,
            model=log.model_used,
            prompt_hash=log.prompt_hash,
            was_duplicate_blocked=log.was_duplicate_blocked,
            suspicious_pattern_detected=log.suspicious_pattern is not None,
            device=log.device,
        )
        for log in list_audit_logs(limit=100)
    ]
    return AuditResponse(total=total, queries=queries)


@router.get(
    "/stats",
    response_model=StatsResponse,
    dependencies=[Depends(require_admin_token)],
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
    )
