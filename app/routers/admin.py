from fastapi import APIRouter, Depends

from app.db.database import count_audit_logs, list_audit_logs
from app.middleware.auth import require_admin_token
from app.models.schemas import AuditQueryEntry, AuditResponse

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
