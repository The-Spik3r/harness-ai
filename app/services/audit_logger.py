from datetime import datetime, timezone
from typing import Optional

from app.db.database import insert_audit_log
from app.db.models import AuditLog
from app.services.duplicate_checker import hash_prompt

_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
_PREVIEW_LENGTH = 500


def log_query(
    user_id: str,
    prompt: str,
    device: Optional[str] = None,
    response: Optional[str] = None,
    model_used: Optional[str] = None,
    tokens_used: Optional[int] = None,
    was_duplicate_blocked: bool = False,
    suspicious_pattern: Optional[str] = None,
    success: bool = True,
    error_message: Optional[str] = None,
) -> int:
    entry = AuditLog(
        timestamp=datetime.now(timezone.utc).strftime(_TIMESTAMP_FORMAT),
        user_id=user_id,
        device=device,
        prompt_hash=hash_prompt(prompt),
        prompt_preview=prompt[:_PREVIEW_LENGTH],
        response_hash=hash_prompt(response) if response is not None else None,
        response_preview=response[:_PREVIEW_LENGTH] if response is not None else None,
        model_used=model_used,
        tokens_used=tokens_used,
        was_duplicate_blocked=was_duplicate_blocked,
        suspicious_pattern=suspicious_pattern,
        success=success,
        error_message=error_message,
    )
    return insert_audit_log(entry)
