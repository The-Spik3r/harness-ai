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
    pii_detected_input: bool = False,
    pii_detected_output: bool = False,
    pii_entities: Optional[list[str]] = None,
    role: Optional[str] = None,
    denied_permission: Optional[str] = None,
    session_id: Optional[str] = None,
    dedup_key: Optional[str] = None,
    # PRD-011 STORY-009. Defaulted, unlike _deny's session_id/dedup_key: only
    # the pattern block and flag arms have a hit to describe, and NULL is the
    # truth for every other row.
    pattern_role: Optional[str] = None,
    pattern_action: Optional[str] = None,
    # PRD-012 STORY-011 (D9). Defaulted here but never omitted in the
    # pipeline: every row run_conversation writes passes it explicitly --
    # _deny requires it, and tests/test_query_pipeline_pii_profiles.py scans
    # every direct call site -- because a forgotten arm must not write a NULL
    # that makes a `code` row's pii_detected_output = 0 read as "clean"
    # (the PRD-008 STORY-009 / PRD-009 Risk 6 rule). The default exists for
    # one caller: /query's foreign-session refusal (app/routers/query.py),
    # which writes before run_query resolves any profile, so NULL is the truth.
    profile: Optional[str] = None,
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
        pii_detected_input=pii_detected_input,
        pii_detected_output=pii_detected_output,
        pii_entities=",".join(pii_entities) if pii_entities else None,
        role=role,
        denied_permission=denied_permission,
        session_id=session_id,
        dedup_key=dedup_key,
        pattern_role=pattern_role,
        pattern_action=pattern_action,
        profile=profile,
    )
    return insert_audit_log(entry)
