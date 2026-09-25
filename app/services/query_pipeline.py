import logging
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
from app.services.pattern_config import get_profile
from app.services.pattern_detector import inspect, strip_fenced_blocks
from app.services.pii_policy import PiiPolicy, get_pii_policy
from app.services.pii_redactor import PiiRedactorError, redact, redact_for_policy

QueryPipelineResult = Union[
    QuerySuccessResponse,
    QueryBlockedDuplicateResponse,
    QueryBlockedSuspiciousResponse,
    QueryBlockedForbiddenResponse,
    QueryBlockedContextLimitResponse,
]

ContextLimit = Literal["messages", "characters"]

logger = logging.getLogger(__name__)


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


def _analyzable_characters(messages: Sequence[Message], policy: PiiPolicy) -> int:
    """How many characters step 6 would hand the analyzer under `policy`.

    Only messages whose role the policy covers count: `code`'s `system` turn is
    not analyzed, so it costs nothing (PRD-012 D3). A covered message is
    measured as the analyzer sees it -- `strip_fenced_blocks(content)` when the
    policy skips fences, `content` otherwise -- and every newline is left out.
    A blanked fence is nothing but newlines, so fenced content counts zero; a
    newline in prose is a run of one, costs the analyzer nothing either, and is
    left out by the same rule (PRD-012 Section 6.7, "newline runs not
    counted"). Lengths only: nothing here calls the analyzer.
    """
    total = 0
    for message in messages:
        if message.role not in policy.input_roles:
            continue
        text = strip_fenced_blocks(message.content) if policy.skip_fenced_blocks else message.content
        total += len(text) - text.count("\n")
    return total


def _redaction_limit_exceeded(
    messages: Sequence[Message], policy: PiiPolicy
) -> Optional[Tuple[int, int]]:
    """(maximum, actual) when the analyzable characters break `policy`'s limit, or None.

    None without counting when the policy has no limit -- `chat`, whose
    `max_characters` is None because CONTEXT_MAX_CHARACTERS already bounds it
    -- and when PII_REDACTION_ENABLED is off. The master switch turns off every
    policy (PRD-012 Section 9.3): with nothing analyzed there is no redaction
    for size to get past, and "exceeds redaction limit" would be untrue. It is
    read here, per call, for the reason _context_limit_exceeded gives; the
    maximum is the policy's, which pii_policy.load() builds from settings.

    The comparison is strict `>`, as at step 3: a conversation exactly at the
    maximum is within the limit.
    """
    if policy.max_characters is None or not settings.PII_REDACTION_ENABLED:
        return None
    actual = _analyzable_characters(messages, policy)
    if actual > policy.max_characters:
        return policy.max_characters, actual
    return None


def _redact(text: str, policy: PiiPolicy) -> Tuple[str, list[str]]:
    """Mask `text` under `policy`: the one redaction call steps 6 and 8 make.

    A policy without `structure_safe` (`chat`) is redact(), called by **this
    module's** name, byte for byte today's path (PRD-012 Section 2). The name
    is load-bearing: the suite replaces `query_pipeline.redact` to spy on it,
    fail it or count it, and redact_for_policy() reaches `pii_redactor.redact`
    instead, a binding those patches never touch. For `chat` both return the
    same value (STORY-008 AC 5), so this is a choice of binding, not of
    behaviour. The branch mirrors the one inside redact_for_policy(), so the
    two cannot disagree about which path `chat` takes.

    Any other policy (`code`) goes through redact_for_policy(). Both raise
    PiiRedactorError; the caller's redaction-error arm handles either.
    """
    if not policy.structure_safe:
        return redact(text)
    return redact_for_policy(text, policy)


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
    *,
    # Chosen by the call site, never by a request field: no schema carries it,
    # so the permissive profile cannot be requested by a caller (PRD-011
    # Section 6.6, D2, T1). None means PATTERN_PROFILE_DEFAULT. Keyword-only so
    # no positional caller can pass it by accident; run_query passes nothing.
    profile: Optional[str] = None,
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

    # Step 5: patterns, over the whole conversation under the profile's role
    # matrix (PRD-011 Sections 6.1, 6.4, 7/F5). The position is unchanged:
    # after every authorization arm and the duplicate check, before redaction,
    # so the raw text is inspected and never the masked one. Both settings are
    # read here, per call, for the reason _context_limit_exceeded gives.
    #
    # An unknown profile is a call-site bug and raises PatternConfigError here.
    # Every earlier arm that writes a row has already returned, so it leaves no
    # row behind.
    profile_name = profile if profile is not None else settings.PATTERN_PROFILE_DEFAULT
    scan_ceiling = settings.PATTERN_MAX_SCAN_CHARACTERS
    inspection = inspect(messages, get_profile(profile_name), max_scan_characters=scan_ceiling)
    for index in inspection.truncated:
        # PRD-011 Section 9.2, T9: the user id, the index and both lengths,
        # never the content. Deliberately not an audit column: the ceiling is a
        # backstop far above anything CONTEXT_MAX_CHARACTERS admits.
        logger.warning(
            "pattern scan truncated: user_id=%s message_index=%d length=%d scanned=%d",
            identity.user_id,
            index,
            len(messages[index].content),
            scan_ceiling,
        )

    if inspection.block is not None:
        block = inspection.block
        # The role goes to the audit and never to the body (PRD-011 D7).
        # `block.action` is always "block" here -- inspect() puts nothing
        # else in `.block` -- and is passed rather than spelled so the hit
        # stays the one source of what was done.
        log_query(
            user_id=identity.user_id,
            prompt=prompt,
            device=device,
            suspicious_pattern=block.pattern,
            success=True,
            session_id=session_id,
            dedup_key=key,
            pattern_role=block.role,
            pattern_action=block.action,
        )
        return QueryBlockedSuspiciousResponse(
            reason="Suspicious pattern detected",
            pattern=block.pattern,
        )

    # The flag arm (PRD-011 Sections 6.1, 6.7, F6): the first outcome in this
    # pipeline that writes a row and then continues. Written here, at step 5,
    # so a flagged request that later fails upstream leaves two rows -- the
    # flag and the failure -- rather than one row trying to say both. One row
    # names one hit: the first flag in walk order; further flags are not
    # recorded (a second table is PRD-013's). A block above has already
    # returned, so a flag followed by a block leaves only the block row.
    # Unreachable from any ingress today: `chat` has no flag cell, and step 0
    # refuses `tool` turns until PRD-016.
    if inspection.flags:
        first_flag = inspection.flags[0]
        log_query(
            user_id=identity.user_id,
            prompt=prompt,
            device=device,
            suspicious_pattern=first_flag.pattern,
            success=True,
            session_id=session_id,
            dedup_key=key,
            pattern_role=first_flag.role,
            pattern_action=first_flag.action,
        )

    # Step 6: redact input per the profile's PII policy (PRD-012 Sections
    # 6.1, 6.3, F8). Resolved once per request, from the name step 5 resolved:
    # `chat` for /query and the chat UI, a name without a PII policy falls
    # back to `chat` (D8).
    policy = get_pii_policy(profile_name)

    # The redaction size limit (PRD-012 Sections 6.1, 6.7; D4, T5). Here, at
    # the head of step 6 and not in step 3, because what it measures depends
    # on the policy: which roles are covered and how much sits inside fences.
    # So a refused conversation has already passed authorization, the
    # duplicate check and patterns -- a pattern block wins over it, and a flag
    # row above is followed by this one.
    #
    # Fail closed: over the limit, nothing is analyzed and nothing goes
    # upstream. There is deliberately no skip-and-flag alternative, not even
    # as an unused setting: skipping is forwarding unmasked text (D4).
    # `success=False` for step 3's reason, which also means the row can never
    # serve as a prior query (PRD-009 Section 6.3): the same request sent
    # after the operator raises the limit is answered, not held. `chat` has
    # no limit, so /query and the chat UI cannot reach this arm.
    over = _redaction_limit_exceeded(messages, policy)
    if over is not None:
        maximum, actual = over
        log_query(
            user_id=identity.user_id,
            prompt=prompt,
            device=device,
            success=False,
            error_message=f"redaction limit: characters {actual} > {maximum}",
            session_id=session_id,
            dedup_key=key,
        )
        return QueryBlockedContextLimitResponse(
            reason="Conversation exceeds redaction limit",
            limit="redaction_characters",
            maximum=maximum,
            actual=actual,
        )

    # Every role the policy covers is redacted, history included (PRD-010
    # D5): history must never leave the process unmasked, whatever its
    # source -- under `code` too, because a /v1 caller writes its own
    # `assistant` turns (PRD-012 T7). `chat` covers every role, so it is
    # today's "redact every message". Only the last user turn's entities
    # count toward the audit's PII fields (PRD-010 D7): re-redacting history
    # that already passed once is not a new PII event, or every later row of
    # a session would misreport one. The last message is always a `user`
    # turn (step 0), and both policies cover `user`.
    redacted_messages: list[Message] = []
    input_entities: list[str] = []
    last_index = len(messages) - 1
    for index, message in enumerate(messages):
        if message.role not in policy.input_roles:
            # The same object, so it reaches upstream byte-identical: `code`'s
            # `system` turn, the client's own prompt (PRD-012 D3). A `tool`
            # turn cannot get here; step 0 refuses it until PRD-016.
            redacted_messages.append(message)
            continue
        try:
            redacted_content, entities = _redact(message.content, policy)
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

    # Step 8: redact the response only when the policy's output switch is on,
    # then audit and return. `chat` always redacts it. `code` does not by
    # default (PRD-012 D1): the reader of a coding agent's output is the file
    # system, and a placeholder in a response becomes a placeholder in a file.
    # Its row then has pii_detected_output=0 because the output was **not
    # analyzed**, not because it was clean; PRD-012 STORY-011's `profile`
    # column is what tells a reader of the row which it was.
    if policy.output:
        try:
            redacted_response, output_entities = _redact(openrouter_result.response, policy)
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
    else:
        redacted_response = openrouter_result.response
        output_entities = []

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
