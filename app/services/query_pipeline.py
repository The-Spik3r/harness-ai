from typing import Callable, Literal, Optional, Sequence, Tuple, Union

from app.config import settings
from app.models.messages import Message
from app.models.schemas import (
    QueryBlockedContextLimitResponse,
    QueryBlockedDuplicateResponse,
    QueryBlockedForbiddenResponse,
    QueryBlockedSuspiciousResponse,
    QuerySuccessResponse,
)
from app.services.audit_logger import log_query
from app.services.authz import (
    PERMISSION_QUERY_BYOK,
    PERMISSION_QUERY_SUBMIT,
    PermissionDenied,
    authorize,
    authorize_model,
)
from app.services.duplicate_checker import check_duplicate, dedup_key
from app.services.identity import Identity
from app.services.openrouter_client import (
    GenerationParams,
    OpenRouterError,
    OpenRouterResult,
    call_openrouter,
)
from app.services.pattern_detector import detect_suspicious_pattern
from app.services.pii_redactor import PiiRedactorError, redact

QueryPipelineResult = Union[
    QuerySuccessResponse,
    QueryBlockedDuplicateResponse,
    QueryBlockedSuspiciousResponse,
    QueryBlockedForbiddenResponse,
    QueryBlockedContextLimitResponse,
]

ContextLimit = Literal["messages", "characters"]


class InvalidConversationError(Exception):
    """The conversation is structurally malformed: a programming error.

    Unreachable from any ingress in this PRD (Section 9.2 invariants) --
    run_query always builds one well-formed user turn, and ChatState's
    history is built only from stored, already-answered exchanges (D4).
    Raised before dedup_key, authorization, or any log_query call, so it
    writes no audit row. Neither the router nor ChatState catches it.
    """


def _validate_conversation(messages: Sequence[Message]) -> None:
    if not messages:
        raise InvalidConversationError("messages must not be empty")
    if any(m.role == "tool" for m in messages):
        raise InvalidConversationError("tool turns are not supported (PRD-016)")
    if messages[-1].role != "user":
        raise InvalidConversationError("the last message must be a user turn")


def _inspection_target(messages: Sequence[Message]) -> str:
    """PROVISIONAL (PRD-010 D6): the last user turn. PRD-011 replaces this.

    Sufficient for chat history: every earlier user turn was itself the last
    user turn of a send that already passed inspection (D4). Not sufficient
    for caller-supplied history -- no ingress in this PRD accepts one.
    """
    return messages[-1].content


def _context_limit_exceeded(
    messages: Sequence[Message],
) -> Optional[Tuple[ContextLimit, int, int]]:
    """The limit this conversation breaks as (limit, maximum, actual), or None.

    Messages are checked first and the function returns on the first breach
    (PRD-010 D2), so a conversation over both limits is reported as `messages`
    and the character count is never computed for it. Only one limit is ever
    reported: a body naming both would imply they were measured independently.

    Both maxima are read off `settings` **here, per call** rather than captured
    at import. Two reasons: a process that read them once could not be
    reconfigured without a restart, and every test in this suite sets them with
    `monkeypatch.setattr(settings, ...)`, which a module-level constant would
    silently ignore (STORY-008 Technical Notes).

    The comparison is strict `>`: a conversation exactly at the maximum is
    within the limit, not over it.
    """
    message_count = len(messages)
    if message_count > settings.CONTEXT_MAX_MESSAGES:
        return "messages", settings.CONTEXT_MAX_MESSAGES, message_count

    character_count = sum(len(message.content) for message in messages)
    if character_count > settings.CONTEXT_MAX_CHARACTERS:
        return "characters", settings.CONTEXT_MAX_CHARACTERS, character_count

    return None


def _deny(
    identity: Identity,
    prompt: str,
    device: Optional[str],
    # Required, and deliberately not defaulted or closed over: this helper is
    # the single log_query call site serving all three authorization arms, and
    # a captured variable is how one of them silently stops passing the session
    # on. Required means a forgotten arm is a TypeError, not a NULL nobody
    # notices for a release. (PRD-008 STORY-009)
    session_id: Optional[str],
    # Required for the same reason as session_id: a forgotten arm is a
    # TypeError, not a NULL key. A NULL-key row can never serve as a prior query
    # once the lookup matches on the key, which silently disables the control
    # for that path (PRD-009 Risk 6). The name shadows the imported dedup_key()
    # inside this helper, harmlessly -- it only passes the value on.
    dedup_key: Optional[str],
    exc: PermissionDenied,
    reason: str,
) -> QueryBlockedForbiddenResponse:
    log_query(
        user_id=identity.user_id,
        prompt=prompt,
        device=device,
        success=True,
        role=identity.role,
        denied_permission=exc.permission,
        session_id=session_id,
        dedup_key=dedup_key,
    )
    return QueryBlockedForbiddenResponse(reason=reason, required_permission=exc.permission)


def run_conversation(
    identity: Identity,
    messages: Sequence[Message],
    device: Optional[str],
    model: str,
    openrouter_api_key: Optional[str],
    params: Optional[GenerationParams] = None,
    call_openrouter: Callable[..., OpenRouterResult] = call_openrouter,
    session_id: Optional[str] = None,
) -> QueryPipelineResult:
    # Step 0 (PRD Section 6.1): structural validation, before anything else
    # can run -- a malformed conversation is a programming error, not an
    # outcome, so it writes no audit row.
    _validate_conversation(messages)
    # Guaranteed by validation: the last message is always role == "user".
    prompt = messages[-1].content

    # Step 1: computed once, before authorization, on purpose (PRD-009
    # Section 6.1): it is pure, so it cannot change the check order, and
    # every row this function writes -- denials included -- carries it.
    # dedup_key runs over the raw conversation as received (STORY-007).
    key = dedup_key(identity.user_id, messages)

    # Step 2: authorize / model / BYOK.
    try:
        authorize(identity, PERMISSION_QUERY_SUBMIT)
    except PermissionDenied as exc:
        return _deny(
            identity, prompt, device, session_id=session_id, dedup_key=key, exc=exc,
            reason="Missing required permission",
        )

    try:
        authorize_model(identity, model)
    except PermissionDenied as exc:
        return _deny(
            identity, prompt, device, session_id=session_id, dedup_key=key, exc=exc,
            reason="Model not permitted for this role",
        )

    if openrouter_api_key is not None:
        try:
            authorize(identity, PERMISSION_QUERY_BYOK)
        except PermissionDenied as exc:
            return _deny(
                identity, prompt, device, session_id=session_id, dedup_key=key, exc=exc,
                reason="Missing required permission",
            )

    # Step 3: context limits (STORY-008; PRD Sections 6.1 and 6.5, D2).
    #
    # The position is the decision. It sits **after** all three authorization
    # arms, so a caller without `query:submit` is told they lack the permission
    # and learns nothing about how this deployment is configured. It sits
    # **before** check_duplicate, so an over-limit conversation neither consults
    # the duplicate window nor lands in it -- it never got a verdict, so it is
    # not a query anyone asked twice.
    #
    # `success=False`, unlike the three arms below, and that is not an
    # oversight. A duplicate/suspicious/forbidden row is `success=True` because
    # a verdict was reached and the row itself names it in a dedicated column.
    # `audit_logs` has no column for "over the context limit" and this story
    # adds none, so the reason goes in `error_message` with success unset --
    # the same shape the upstream-error arm uses. It also makes the row
    # unusable as a prior query (PRD-009 Section 6.3), which is exactly right
    # for an attempt that never reached the model. The cost is that these rows
    # count against `success_rate`; PRD Section 9.2 T7 accepts it.
    exceeded = _context_limit_exceeded(messages)
    if exceeded is not None:
        limit, maximum, actual = exceeded
        log_query(
            user_id=identity.user_id,
            prompt=prompt,
            device=device,
            success=False,
            error_message=f"context limit: {limit} {actual} > {maximum}",
            session_id=session_id,
            dedup_key=key,
        )
        return QueryBlockedContextLimitResponse(
            reason="Conversation exceeds context limit",
            limit=limit,
            maximum=maximum,
            actual=actual,
        )

    # Step 4: duplicate.
    #
    # identity.user_id is the credential-resolved id, never the request body's,
    # so a caller cannot choose whose window they are checked against
    # (PRD-009 Section 9.1, F5). The key is the one derived above, once: the
    # control checks exactly what every row records.
    duplicate_result = check_duplicate(identity.user_id, key)

    if duplicate_result.is_duplicate:
        log_query(
            user_id=identity.user_id,
            prompt=prompt,
            device=device,
            was_duplicate_blocked=True,
            success=True,
            session_id=session_id,
            dedup_key=key,
        )
        return QueryBlockedDuplicateResponse(
            reason="Duplicate query within 24 hours",
            first_query_at=duplicate_result.first_query_at,
        )

    # Step 5: patterns, on the provisional inspection target only (D6).
    pattern_result = detect_suspicious_pattern(_inspection_target(messages))
    if pattern_result.is_suspicious:
        log_query(
            user_id=identity.user_id,
            prompt=prompt,
            device=device,
            suspicious_pattern=pattern_result.pattern,
            success=True,
            session_id=session_id,
            dedup_key=key,
        )
        return QueryBlockedSuspiciousResponse(
            reason="Suspicious pattern detected",
            pattern=pattern_result.pattern,
        )

    # Step 6: redact every message (D5) -- history must never leave the
    # process unmasked, whatever its source. Only the last user turn's
    # entities count toward the audit's PII fields (D7): re-redacting
    # history that already passed once is not a new PII event, or every
    # later row of a session would misreport one (PRD Section 6.7).
    redacted_messages: list[Message] = []
    input_entities: list[str] = []
    last_index = len(messages) - 1
    for index, message in enumerate(messages):
        try:
            redacted_content, entities = redact(message.content)
        except PiiRedactorError as exc:
            log_query(
                user_id=identity.user_id,
                prompt=prompt,
                device=device,
                success=False,
                error_message=str(exc),
                session_id=session_id,
                dedup_key=key,
            )
            raise
        redacted_messages.append(Message(message.role, redacted_content))
        if index == last_index:
            input_entities = entities

    # Step 7: upstream. params is forwarded only when set: the existing
    # injected call_openrouter stubs across the suite have signature
    # (messages, model, api_key) and raise TypeError on an unexpected
    # params= keyword (PRD-010 STORY-005 Technical Notes).
    try:
        if params is not None:
            openrouter_result = call_openrouter(
                redacted_messages, model=model, api_key=openrouter_api_key, params=params
            )
        else:
            openrouter_result = call_openrouter(
                redacted_messages, model=model, api_key=openrouter_api_key
            )
    except OpenRouterError as exc:
        log_query(
            user_id=identity.user_id,
            prompt=prompt,
            device=device,
            model_used=model,
            success=False,
            error_message=str(exc),
            session_id=session_id,
            dedup_key=key,
        )
        raise

    # Step 8: redact response, audit, return.
    try:
        redacted_response, output_entities = redact(openrouter_result.response)
    except PiiRedactorError as exc:
        log_query(
            user_id=identity.user_id,
            prompt=prompt,
            device=device,
            response=openrouter_result.response,
            model_used=openrouter_result.model_used,
            tokens_used=openrouter_result.tokens_used,
            success=False,
            error_message=str(exc),
            pii_detected_input=bool(input_entities),
            pii_entities=input_entities,
            session_id=session_id,
            dedup_key=key,
        )
        raise

    masked_entities = sorted(set(input_entities) | set(output_entities))

    audit_id = log_query(
        user_id=identity.user_id,
        prompt=prompt,
        device=device,
        response=openrouter_result.response,
        model_used=openrouter_result.model_used,
        tokens_used=openrouter_result.tokens_used,
        success=True,
        pii_detected_input=bool(input_entities),
        pii_detected_output=bool(output_entities),
        pii_entities=masked_entities,
        session_id=session_id,
        dedup_key=key,
    )

    return QuerySuccessResponse(
        response=redacted_response,
        audit_id=audit_id,
        model_used=openrouter_result.model_used,
        tokens_used=openrouter_result.tokens_used,
        pii_redacted=bool(masked_entities),
        pii_entities_masked=masked_entities,
    )


def run_query(
    identity: Identity,
    prompt: str,
    device: Optional[str],
    model: str,
    openrouter_api_key: Optional[str],
    call_openrouter: Callable[..., OpenRouterResult] = call_openrouter,
    session_id: Optional[str] = None,
) -> QueryPipelineResult:
    return run_conversation(
        identity,
        [Message("user", prompt)],
        device,
        model,
        openrouter_api_key,
        call_openrouter=call_openrouter,
        session_id=session_id,
    )
