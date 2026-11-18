"""The one rule that tells a storage outage from any other storage failure.

PRD-018 D8 / Section 6.7. Every HTTP ingress (`/query`, `/v1`, and later the
chat UI, STORY-007) answers a *transient* storage refusal with a retryable 503
and `Retry-After`, and every other storage failure exactly as before. This
module is that decision, in one place: `storage_unavailable_cause()`.

It imports only `app.db.errors` (the `duplicate_checker` precedent) and does no
I/O. It is a service module, not `app/db/errors.py`, so a caller outside the
storage layer need not import the storage exception surface itself (the
coupling `chat_sessions.ChatSessionError` warns about).
"""

from typing import Dict, Optional

from app.db.errors import AuditUnavailableError, StorageUnavailableError

# Fixed client copy (PRD-018 Section 10). Driver text never reaches a client:
# it is logged once through `database._redacted()` by the unit of work. The
# `/v1` sentence lives in `v1_translate`, beside its other copy.
STORAGE_UNAVAILABLE_DETAIL = "Storage unavailable"
STORAGE_UNAVAILABLE_NOT_SENT_DETAIL = "Storage unavailable: the request was not sent to the model."


def storage_unavailable_cause(exc: BaseException) -> Optional[StorageUnavailableError]:
    """The `StorageUnavailableError` behind `exc`, or None.

    `exc` itself when it is one, else its direct `__cause__` when that is one.
    One level only, on purpose: every gate wraps the unit's own exception with
    `from exc` (`check_duplicate`, `admit`, `chat_sessions._wrapped`), and a
    deeper walk would also match faults whose cause is merely incidental.

    The caller decides which exception types the rule applies to. `/v1`, for
    one, does not apply it to `ActionAuditError`: tools keep PRD-017's
    `500 internal_error` (PRD-018 Section 6.7).
    """
    if isinstance(exc, StorageUnavailableError):
        return exc
    cause = exc.__cause__
    if isinstance(cause, StorageUnavailableError):
        return cause
    return None


def audit_unavailable_retry_after(exc: AuditUnavailableError) -> int:
    """Whole seconds for the `Retry-After` of an `AuditUnavailableError` 503 (PRD-018 R5).

    The first `StorageUnavailableError` on the `__context__` chain, else `1`.
    `__context__`, not `__cause__`: the append runs inside the `except
    StorageUnavailableError` block that sent the row to the journal, so the
    outage is the context, and when the journal write failed an `OSError` sits
    between them (`AuditUnavailableError` is raised `from` it).
    """
    seen = 0
    current = exc.__context__
    while current is not None and seen < 16:
        if isinstance(current, StorageUnavailableError):
            return current.retry_after_seconds
        current = current.__context__
        seen += 1
    return 1


def retry_after_headers(cause: StorageUnavailableError) -> Dict[str, str]:
    """`Retry-After` in whole seconds (>= 1, guaranteed by the error), one spelling for all ingresses."""
    return {"Retry-After": str(cause.retry_after_seconds)}
