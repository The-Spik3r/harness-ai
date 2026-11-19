import dataclasses
import functools
import logging
import uuid
from typing import Any, Callable, Iterator, Literal, Optional, Sequence, Tuple, Union

from app.config import settings
from app.db import audit_journal
from app.db.database import mark_audit_log_failed
from app.db.errors import AuditUnavailableError, StorageError
from app.models.messages import Message, ToolCallSpec, conversation_shape_violation
from app.models.schemas import (
    QueryBlockedContextLimitResponse,
    QueryBlockedDuplicateResponse,
    QueryBlockedForbiddenResponse,
    QueryBlockedSuspiciousResponse,
    QueryBlockedUsageLimitResponse,
    QuerySuccessResponse,
)
# PRD-017 STORY-010 DD-5: called through their modules (`action_policy.
# evaluate_all(...)`), so a test's monkeypatch of the source module reaches the
# pipeline, the rule `action_policy._classify` documents.
from app.services import action_adapters, action_audit, action_config, action_policy, tool_release
from app.services.audit_logger import log_query
from app.services.authz import (
    PERMISSION_QUERY_BYOK,
    PERMISSION_QUERY_SUBMIT,
    PERMISSION_REASONING_VIEW,
    PERMISSION_STREAM_REALTIME,
    PermissionDenied,
    authorize,
    authorize_route,
    holds,
)
from app.services.conversation_key import conversation_key
from app.services.delivery import DeliverySink, StageName, Visibility
from app.services.duplicate_checker import check_duplicate, dedup_key
from app.services.identity import Identity
from app.services.provider_registry import Route
from app.services.stream_assembly import phase_of
from app.services.stream_redaction import (
    GateResult,
    OutputGate,
    gate_applies,
    reasoning_policy,
    redact_reasoning,
)
from app.services.upstream import (
    GenerationParams,
    ReasoningDelta,
    TextDelta,
    ToolCallDelta,
    ToolParams,
    UpstreamError as OpenRouterError,
    UpstreamEvent,
    UpstreamRequest,
    UpstreamResult as OpenRouterResult,
    call_upstream as call_openrouter,
    collect,
    stream_upstream,
)
from app.services.pattern_config import get_profile
from app.services.pattern_detector import inspect, strip_fenced_blocks
from app.services.pii_policy import PiiPolicy, get_pii_policy
from app.services.pii_redactor import PiiRedactorError, redact, redact_for_policy
# By name into this module, not `usage_limits.admit`: the suite replaces
# `query_pipeline.admit` and `query_pipeline.charge` to spy on the gate and
# the charge or fail them, the binding rule `_redact` documents for `redact`.
from app.services.usage_estimate import estimate_tokens
from app.services.usage_limits import admit, charge

QueryPipelineResult = Union[
    QuerySuccessResponse,
    QueryBlockedDuplicateResponse,
    QueryBlockedSuspiciousResponse,
    QueryBlockedForbiddenResponse,
    QueryBlockedContextLimitResponse,
    QueryBlockedUsageLimitResponse,
]

ContextLimit = Literal["messages", "characters", "estimated_tokens"]

# The doors a call site may name (PRD-013 Sections 6.8, 6.9): `/query`, the
# chat UI, and `/v1`, which PRD-014 adds. None is a direct caller.
Ingress = Literal["query", "chat", "v1"]

logger = logging.getLogger(__name__)


class InvalidConversationError(Exception):
    """The conversation is structurally malformed: a programming error.

    Unreachable from any ingress in this PRD (Section 9.2 invariants) --
    run_query always builds one well-formed user turn, ChatState's history
    is built only from stored, already-answered exchanges (D4), and `/v1`
    checks the same D6 rules at its edge first (PRD-017 STORY-008).
    Raised before dedup_key, authorization, or any log_query call, so it
    writes no audit row. Neither the router nor ChatState catches it.
    """


#: The `error_message` of an audit row whose decisions could not be recorded (D8).
_ACTION_AUDIT_FAILED = "action audit failed"


class ActionAuditError(Exception):
    """The decisions of a tools response could not be recorded (PRD-017 D8, F7; PRD-018 D13).

    Raised after the success row was committed or journaled and its decisions
    could be neither written nor journaled, or when the row itself could be
    neither committed nor journaled on a response with decisions (PRD-018 6.7,
    R2: no row exists then, so nothing is marked failed).

    The pipeline logs the user and `audit_id` at ERROR, makes a best-effort
    attempt to mark that row `success = 0` so a retry is not held as a duplicate,
    and raises this with a fixed message (no driver text, because `/v1` sends
    the message to the client). `/v1` maps it to 500 `internal_error`, retryable,
    and nothing is released (T5). `/query` never reaches it: it sends no `tools`,
    so no calls come back (D17, D18).
    """


def _has_tool_turns(messages: Sequence[Message]) -> bool:
    """The request half of D19: an assistant `tool_calls` turn or a `tool` turn.

    A pure function of the conversation, so step 1b computes it once and every
    row carries it, whichever arm writes the row. The response half (the
    upstream carried calls) is known only from step 7c on.
    """
    return any(m.role == "tool" or bool(m.tool_calls) for m in messages)


def _validate_conversation(messages: Sequence[Message]) -> None:
    # PRD-017 D6, Section 6.3: the same helper as the `/v1` edge, so step 0 is
    # the programming-error guard behind it (PRD-010 Section 6.1).
    if not messages:
        raise InvalidConversationError("messages must not be empty")
    violation = conversation_shape_violation(messages)
    if violation is not None:
        index, rule = violation
        raise InvalidConversationError(f"messages[{index}]: {rule}")


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

    The character count is every turn's `content` plus every tool call's
    `arguments` (PRD-017 D12, Section 6.5); ids and names are not counted. The
    PII size limit at step 6 never counts arguments (`_analyzable_characters`,
    D13).
    """
    message_count = len(messages)
    if message_count > settings.CONTEXT_MAX_MESSAGES:
        return "messages", settings.CONTEXT_MAX_MESSAGES, message_count

    # PRD-017 D12: a history call's arguments are text the model reads, so they
    # count toward the limit like content. Arguments only, as Section 6.5 states;
    # a conversation without calls sums exactly today's terms.
    character_count = sum(
        len(message.content) + sum(len(call.arguments) for call in message.tool_calls)
        for message in messages
    )
    if character_count > settings.CONTEXT_MAX_CHARACTERS:
        return "characters", settings.CONTEXT_MAX_CHARACTERS, character_count

    return None


def _estimated_tokens_exceeded(
    messages: Sequence[Message],
    route: Route,
    tools: Optional[ToolParams],
) -> Optional[Tuple[ContextLimit, int, int]]:
    """`("estimated_tokens", maximum, actual)` when the conversation outgrows the model, else None.

    PRD-020 D9, T10: the route's `max_context_tokens` (the catalogued model's,
    or the passthrough role's) against the D8 estimate of what would be sent.
    A model that declares none is skipped before any estimate is computed, so
    legacy mode and every model without the key behave exactly as before (D1).

    The estimate is `usage_estimate.estimate_tokens` over the pre-redaction
    `messages` (step 3 precedes step 6) with the request's tools counted, at the
    provider's `estimate_chars_per_token`. It is a heuristic, a mitigation for
    sending an oversized conversation and not proof of the server's real window.
    Strict `>`, like the two character limits: exactly the maximum proceeds.
    """
    maximum = route.capabilities.max_context_tokens
    if maximum is None:
        return None
    actual = estimate_tokens(
        messages,
        ("", ()),
        route.provider.estimate_chars_per_token,
        tools=tools.tools if tools is not None else None,
    )
    if actual > maximum:
        return "estimated_tokens", maximum, actual
    return None


def _break_glass_refused(identity: Identity, ingress: Optional[Ingress]) -> bool:
    """Whether step 2b refuses this identity on this door (PRD-013 Section 6.8, D4).

    The marker is the credential, not the role: only `resolve(ADMIN_TOKEN)`
    sets `break_glass`. A user token with the `admin` role, and an
    `Identity("admin", "admin")` built directly, both carry False and are never
    refused here.

    Fails closed: `None` -- a direct call that named no door -- is in no
    allowed set, so the break-glass identity is refused there too (T9).

    The allowed set is read off `settings` **here, per call**, for the reason
    `_context_limit_exceeded` gives. It can only tighten: the setting's
    validator rejects `v1`, so no configuration admits the token there.

    Module-level, so the check-order tests can spy on it by name.
    """
    return identity.break_glass and ingress not in settings.break_glass_ingresses


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

    Content only: a `tool` turn counts when the policy covers `tool` (`code`
    does), and tool-call arguments never count, because they never reach the
    analyzer (PRD-017 D13). Step 3 counts them (D12).
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


def _route_fields(route: Optional[Route]) -> dict:
    """The three audit columns taken from the resolved Route (PRD-020 D13, T8).

    From the Route, never from the upstream result: `model_used` stays the
    requested id. All None when no route exists yet (steps 0-2 denials)."""
    if route is None:
        return {"provider": None, "upstream_model": None, "provider_trust": None}
    return {
        "provider": route.provider.name,
        "upstream_model": route.upstream_model,
        "provider_trust": route.provider.trust,
    }


class _SafeSink:
    """Wraps a DeliverySink so a fault in it never reaches the pipeline (PRD-021 D18, 6.3).

    A sink is a courtesy to a reader; the request, its audit row and its charge
    do not depend on it. Each method calls the real one and swallows any
    Exception; the first fault of a request logs one line naming the user and
    the method, never a payload (T9). Only built when a sink was passed: with
    `sink=None` the pipeline computes and emits nothing."""

    def __init__(self, sink: DeliverySink, user_id: str) -> None:
        self._sink = sink
        self._user_id = user_id
        self._faulted = False

    def _call(self, method: str, *args: Any) -> None:
        try:
            getattr(self._sink, method)(*args)
        except Exception:
            if not self._faulted:
                self._faulted = True
                logger.warning("delivery sink failed: user_id=%s method=%s", self._user_id, method)

    def stage(self, name: StageName) -> None:
        self._call("stage", name)

    def phase(self, name: Any, action_kind: Any = None) -> None:
        self._call("phase", name, action_kind)

    def content(self, text: str) -> None:
        self._call("content", text)

    def reasoning(self, text: str) -> None:
        self._call("reasoning", text)

    def committed(self, completion_id: str) -> None:
        self._call("committed", completion_id)


# PRD-018 D10/T5 (R1): a refusal is a release, and every refusal arm below
# writes its row through `log_query`. When that row can be neither committed nor
# journaled, `AuditUnavailableError` propagates and the request is refused with
# 503 instead of returning the refusal (and, at the upstream-error and
# output-redaction arms, instead of 502/500).
def _deny(
    identity: Identity,
    prompt: str,
    device: Optional[str],
    # Required, and deliberately not defaulted or closed over: this helper is
    # the single log_query call site serving every authorization arm, and
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
    # Required for the same reason as session_id and dedup_key: a forgotten
    # arm is a TypeError, not a NULL that makes a `code` row's
    # pii_detected_output = 0 read as clean (PRD-012 D9). `str`, not Optional:
    # after run_conversation's resolution it is never None.
    profile: str,
    # Required for the same reason as the three above (PRD-013 Section 6.9):
    # a forgotten arm is a TypeError, not a row that cannot say which door it
    # came through, how big it was, which conversation it belongs to or how it
    # was delivered. `streamed` is required too, although the story names
    # three: a defaulted False would quietly mislabel a PRD-014 SSE refusal.
    # The parameter name shadows the imported conversation_key() inside this
    # helper, harmlessly, like dedup_key above.
    ingress: Optional[Ingress],
    message_count: int,
    conversation_key: Optional[str],
    streamed: bool,
    # Required for the same reason as the five above (PRD-015 STORY-007): a
    # forgotten authorization arm is a TypeError, not a `/v1` row that
    # silently claims the client got everything it asked for.
    ignored_params: Optional[str],
    # Required for the same reason as the six above (PRD-017 D19): a forgotten
    # authorization arm is a TypeError, not a tool-turn row that claims no
    # tool calls were involved.
    has_tool_calls: bool,
    # Required for the same reason as the seven above (PRD-021 STORY-009, F7):
    # a forgotten authorization arm is a TypeError, not a row that cannot say
    # whether the reply was delivered in real time. Every caller passes False:
    # a refusal opens no upstream.
    streamed_realtime: bool,
    reasoning_shown: bool,
    exc: PermissionDenied,
    reason: str,
    # Required for the same reason as the seven above (PRD-020 D13, STORY-007):
    # a forgotten arm is a TypeError, not a row that cannot say where the
    # request was routed. None for every arm at or before the model check.
    route: Optional[Route],
) -> QueryBlockedForbiddenResponse:
    log_query(
        **_route_fields(route),
        user_id=identity.user_id,
        prompt=prompt,
        device=device,
        success=True,
        role=identity.role,
        denied_permission=exc.permission,
        session_id=session_id,
        dedup_key=dedup_key,
        profile=profile,
        ingress=ingress,
        message_count=message_count,
        conversation_key=conversation_key,
        streamed=streamed,
        ignored_params=ignored_params,
        has_tool_calls=has_tool_calls,
        streamed_realtime=streamed_realtime,
        reasoning_shown=reasoning_shown,
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
    # PRD-021 6.2: the streamed counterpart of `call_openrouter`, injectable the
    # same way; taken only when step 2d said `upstream_streamed`.
    stream_upstream: Callable[..., Iterator[UpstreamEvent]] = stream_upstream,
    # Chosen by the call site, never by a request field: no schema carries it,
    # so the permissive profile cannot be requested by a caller (PRD-011
    # Section 6.6, D2, T1). None means PATTERN_PROFILE_DEFAULT. Keyword-only so
    # no positional caller can pass it by accident; run_query passes nothing.
    profile: Optional[str] = None,
    # PRD-013 Section 6.9: the door this request came through, chosen by the
    # call site like `profile` -- "query" (run_query's default), "chat"
    # (ChatState), "v1" (PRD-014). None for direct callers, the test suite and
    # scripts/, where NULL is the honest record; tests/test_query_pipeline_
    # audit_fields.py fails if a production call site omits it.
    ingress: Optional[Ingress] = None,
    # Whether the response is delivered as SSE. Always False until PRD-014.
    streamed: bool = False,
    # PRD-015 Section 7.3: the request keys `/v1` did not forward, as
    # v1_translate names them, passed by the router (STORY-009) and recorded
    # on every row below. None for every other door; run_query passes nothing.
    ignored_params: Optional[str] = None,
    # PRD-017 Section 4, D11: the `/v1` router's ToolParams (STORY-008), passed
    # to step 7 only when set, as `params` is; every other door passes nothing
    # (D17).
    tools: Optional[ToolParams] = None,
    # PRD-021 D18, Section 6.9: where progress is reported, passed only by an
    # ingress that shows it (the `/v1` router, the chat UI). None -- every other
    # caller, `run_query` included -- computes and emits nothing.
    sink: Optional[DeliverySink] = None,
) -> QueryPipelineResult:
    # Step 0 (PRD Section 6.1): structural validation, before anything else
    # can run -- a malformed conversation is a programming error, not an
    # outcome, so it writes no audit row.
    _validate_conversation(messages)
    # PRD-017 D7: the audit prompt is the final turn, user or tool -- what this
    # request added. Validation guarantees it is one of the two.
    prompt = messages[-1].content

    # The profile name, resolved once, here, because every row this function
    # writes records it -- the forbidden arms included (PRD-012 D9). It is a
    # pure function of the argument and one setting, so resolving it before
    # authorization cannot change the check order: the same argument step 1
    # makes for the key. Step 5 looks the name up; step 6 reads its policy.
    profile_name = profile if profile is not None else settings.PATTERN_PROFILE_DEFAULT

    # Step 1: computed once, before authorization, on purpose (PRD-009
    # Section 6.1): it is pure, so it cannot change the check order, and
    # every row this function writes -- denials included -- carries it.
    # dedup_key runs over the raw conversation as received (STORY-007).
    # Step 1b (PRD-013 Sections 6.1-6.3) follows the same argument: the
    # message count as received, before redaction, and the conversation key
    # over the raw text are both pure, so computing them here cannot change
    # the check order, and every row below carries them.
    key = dedup_key(identity.user_id, messages)
    message_count = len(messages)
    conv_key = conversation_key(identity.user_id, messages)
    # PRD-017 D19, the request half of `has_tool_calls`: pure too, so every row
    # below carries it. The response half joins it at step 7c.
    request_has_tool_turns = _has_tool_turns(messages)

    # Step 1c: admission headroom (PRD-018 D10, Section 6.8 Bounds; T5).
    # Before step 2, so a refused request writes no row (there may be no room
    # for one) and pays for no upstream call; steps 0-1b above are pure. Every
    # worker already in flight keeps W x 64 KiB to journal its rows, so a paid
    # answer is never withheld for lack of space. AuditHeadroomError is an
    # AuditUnavailableError: /query and /v1 answer 503, the chat UI an
    # internal_error bubble, through their existing arms (STORY-011 R2). A
    # no-op when no journal is open.
    audit_journal.check_admission_headroom()

    # PRD-021 D18: the sink, wrapped once so no fault in it reaches the request.
    # Stage events below depend on configuration only (T10), never on a finding.
    safe = _SafeSink(sink, identity.user_id) if sink is not None else None

    # Step 2: authorize / model / BYOK.
    if safe is not None:
        safe.stage("checking_permissions")
    try:
        authorize(identity, PERMISSION_QUERY_SUBMIT)
    except PermissionDenied as exc:
        return _deny(
            identity, prompt, device, session_id=session_id, dedup_key=key,
            # PRD-021 F7: refused before step 2d, so nothing is known and nothing was sent.
            streamed_realtime=False, reasoning_shown=False,
            profile=profile_name, ingress=ingress, message_count=message_count,
            conversation_key=conv_key, streamed=streamed,
            ignored_params=ignored_params, has_tool_calls=request_has_tool_turns, exc=exc,
            reason="Missing required permission", route=None,
        )

    try:
        # PRD-020 D3: one resolution here; the Route is carried to the audit rows.
        route = authorize_route(identity, model)
    except PermissionDenied as exc:
        return _deny(
            identity, prompt, device, session_id=session_id, dedup_key=key,
            streamed_realtime=False, reasoning_shown=False,
            profile=profile_name, ingress=ingress, message_count=message_count,
            conversation_key=conv_key, streamed=streamed,
            ignored_params=ignored_params, has_tool_calls=request_has_tool_turns, exc=exc,
            reason="Model not permitted for this role", route=None,
        )

    if openrouter_api_key is not None:
        try:
            authorize(identity, PERMISSION_QUERY_BYOK)
        except PermissionDenied as exc:
            return _deny(
                identity, prompt, device, session_id=session_id, dedup_key=key,
                streamed_realtime=False, reasoning_shown=False,
                profile=profile_name, ingress=ingress, message_count=message_count,
                conversation_key=conv_key, streamed=streamed,
                ignored_params=ignored_params, has_tool_calls=request_has_tool_turns, exc=exc,
                reason="Missing required permission", route=None,
            )
        # PRD-020 D10: the caller's key goes only to a provider declared
        # `byok: true`. Refused before 2b/2c, so nothing is sent or charged.
        # A label on the row like `query:model:{model}`, never an RBAC permission.
        if not route.provider.byok:
            return _deny(
                identity, prompt, device, session_id=session_id, dedup_key=key,
                streamed_realtime=False, reasoning_shown=False,
                profile=profile_name, ingress=ingress, message_count=message_count,
                conversation_key=conv_key, streamed=streamed,
                ignored_params=ignored_params, has_tool_calls=request_has_tool_turns,
                exc=PermissionDenied(f"query:byok:{route.provider.name}"),
                reason="Missing required permission", route=None,
            )

    # Step 2b: break-glass ingress policy (PRD-013 Sections 6.1, 6.8; D4, F12, T9).
    #
    # After every authorization arm, so the three arms above run first and
    # unchanged (Section 9.1). Before the usage gate, so a refused break-glass
    # attempt consumes no one's window and is never charged.
    #
    # It reuses the forbidden arm: one row, `success=True`, and the existing
    # QueryBlockedForbiddenResponse, which the chat UI's forbidden bubble
    # already renders. "ingress:break_glass" is a label on the row, as
    # `query:model:{model}` is -- never an RBAC permission, so it is not in
    # authz's _KNOWN_PERMISSIONS and no role can be granted it. The admin
    # role's model-allowlist bypass is untouched (Section 6.8, last bullet).
    if _break_glass_refused(identity, ingress):
        return _deny(
            identity, prompt, device, session_id=session_id, dedup_key=key,
            streamed_realtime=False, reasoning_shown=False,
            profile=profile_name, ingress=ingress, message_count=message_count,
            conversation_key=conv_key, streamed=streamed,
            ignored_params=ignored_params, has_tool_calls=request_has_tool_turns,
            exc=PermissionDenied("ingress:break_glass"),
            reason="Break-glass credential not permitted on this ingress",
            route=route,
        )

    # Step 2c: the usage gate (PRD-013 Sections 6.1, 6.5-6.7; D7, D8, F10).
    #
    # Lettered, not renumbered: three PRDs and the comments below cite steps
    # 3-8 by number. The break-glass arm (2b) sits directly above.
    #
    # The position is the decision (D7). After every authorization arm, so a
    # caller without `query:submit` learns nothing about limits and consumes
    # no one's window (T11) -- it has no usage_daily row at all. Before the
    # context limit, the duplicate check and patterns, so every authorized
    # attempt counts toward the rate, including the ones those steps refuse:
    # a looping agent's retries are mostly duplicates (T2), and a resend after
    # a forced failure is an attempt too (PRD-009 T3).
    #
    # The switch is read here, per call, for the reason _context_limit_exceeded
    # gives. Off means admit() is not called and no statement touches
    # usage_daily: the pipeline's round trips are exactly the pre-PRD-013 ones.
    #
    # BYOK spends the caller's own key, so it is rate-limited but not held to
    # the budget (D8). `admission` is kept in a local: step 7b charges the
    # `day` it was counted against, so a request straddling midnight is
    # charged to the day it was admitted.
    #
    # admit() fails closed (T7): a counter outage raises UsageLimitError,
    # which propagates with no row written and nothing sent upstream -- the
    # router maps it to 500 beside DuplicateCheckError, ChatState to the
    # internal-error bubble.
    #
    # A refusal is `success=True`, unlike step 3: a verdict was reached and
    # the row names it in a dedicated column, `limit_exceeded` (PRD-013
    # Section 6.2) -- the rule step 3's comment states. It carries the key like
    # every row, and find_duplicate_timestamp excludes it, so a prompt refused
    # today is not held as a duplicate when sent again after the reset (D6).
    # None when the switch is off, which step 7b reads as "charge nothing".
    admission = None
    if settings.USAGE_LIMITS_ENABLED:
        if safe is not None:
            safe.stage("checking_usage")
        admission = admit(identity, charges_budget=openrouter_api_key is None)
        if not admission.admitted:
            refusal = admission.refusal
            log_query(
                # PRD-021 F7: refused before the upstream opened: nothing was delivered.
                streamed_realtime=False,
                reasoning_shown=False,
                **_route_fields(route),
                user_id=identity.user_id,
                prompt=prompt,
                device=device,
                success=True,
                role=identity.role,
                limit_exceeded=refusal.limit,
                session_id=session_id,
                dedup_key=key,
                profile=profile_name,
                ingress=ingress,
                message_count=message_count,
                conversation_key=conv_key,
                streamed=streamed,
                ignored_params=ignored_params,
                has_tool_calls=request_has_tool_turns,
            )
            return QueryBlockedUsageLimitResponse(
                reason="Usage limit reached",
                limit=refusal.limit,
                maximum=refusal.maximum,
                actual=refusal.actual,
                resets_at=refusal.resets_at,
            )

    # Step 2d: visibility (PRD-021 Section 6.1, F3, T8).
    #
    # After 2c on purpose: a caller refused above must not learn from timing
    # that its role holds a streaming grant, and no refusal computes it. The
    # grants are read with holds(), never authorize(): holds() has no
    # RBAC_ENABLED bypass, so RBAC off cannot hand every caller real time (T8).
    # Computed only when a sink was passed; `None` means nothing is forwarded
    # and step 7 stays today's. Step 7 (STORY-006) reads this local.
    visibility: Optional[Visibility] = None
    if safe is not None:
        visibility = Visibility.compute(
            streaming_enabled=settings.STREAMING_ENABLED,
            holds_realtime=holds(identity, PERMISSION_STREAM_REALTIME),
            holds_reasoning=holds(identity, PERMISSION_REASONING_VIEW),
            caps=route.capabilities,
            ingress=ingress,
            streamed=streamed,
        )
    realtime_request = bool(visibility is not None and visibility.realtime)

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
    #
    # PRD-020 D9: a third check follows the two character limits, the model's
    # `max_context_tokens` against the estimate. First breach wins, so it is not
    # computed for a conversation that already broke an earlier limit.
    exceeded = _context_limit_exceeded(messages) or _estimated_tokens_exceeded(
        messages, route, tools
    )
    if exceeded is not None:
        limit, maximum, actual = exceeded
        log_query(
            # PRD-021 F7: refused before the upstream opened: nothing was delivered.
            streamed_realtime=False,
            reasoning_shown=False,
            **_route_fields(route),
            user_id=identity.user_id,
            prompt=prompt,
            device=device,
            success=False,
            error_message=f"context limit: {limit} {actual} > {maximum}",
            session_id=session_id,
            dedup_key=key,
            profile=profile_name,
            ingress=ingress,
            message_count=message_count,
            conversation_key=conv_key,
            streamed=streamed,
            ignored_params=ignored_params,
            has_tool_calls=request_has_tool_turns,
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
    if safe is not None:
        safe.stage("checking_duplicates")
    duplicate_result = check_duplicate(identity.user_id, key)

    if duplicate_result.is_duplicate:
        log_query(
            # PRD-021 F7: refused before the upstream opened: nothing was delivered.
            streamed_realtime=False,
            reasoning_shown=False,
            **_route_fields(route),
            user_id=identity.user_id,
            prompt=prompt,
            device=device,
            was_duplicate_blocked=True,
            success=True,
            session_id=session_id,
            dedup_key=key,
            profile=profile_name,
            ingress=ingress,
            message_count=message_count,
            conversation_key=conv_key,
            streamed=streamed,
            ignored_params=ignored_params,
            has_tool_calls=request_has_tool_turns,
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
    # Only `content` is inspected. A `tool` turn takes the profile's `tool`
    # cell, and a history call's `arguments` are never pattern-inspected: they
    # are the model's proposal, which the action policy classifies (PRD-017
    # D13, Section 6.5).
    #
    # An unknown profile is a call-site bug and raises PatternConfigError here.
    # An earlier arm that wrote a row has already returned, and its row records
    # the name the call site passed -- which is what ran, as far as it went.
    if safe is not None:
        safe.stage("inspecting_prompt")
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
            # PRD-021 F7: refused before the upstream opened: nothing was delivered.
            streamed_realtime=False,
            reasoning_shown=False,
            **_route_fields(route),
            user_id=identity.user_id,
            prompt=prompt,
            device=device,
            suspicious_pattern=block.pattern,
            success=True,
            session_id=session_id,
            dedup_key=key,
            pattern_role=block.role,
            pattern_action=block.action,
            profile=profile_name,
            ingress=ingress,
            message_count=message_count,
            conversation_key=conv_key,
            streamed=streamed,
            ignored_params=ignored_params,
            has_tool_calls=request_has_tool_turns,
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
    # `chat` has no flag cell. `code` flags `assistant` turns (PRD-015 D9),
    # which `/v1` reaches once its router is mounted (STORY-009) -- until then
    # only tests do. Its `tool` cell is reached by any D6-valid conversation
    # with a tool turn, which step 0 has admitted since PRD-017 STORY-005. `/v1`
    # forwards such turns once its edge stops refusing them (PRD-017 STORY-008).
    if inspection.flags:
        first_flag = inspection.flags[0]
        log_query(
            # PRD-021 F7: refused before the upstream opened: nothing was delivered.
            streamed_realtime=False,
            reasoning_shown=False,
            **_route_fields(route),
            user_id=identity.user_id,
            prompt=prompt,
            device=device,
            suspicious_pattern=first_flag.pattern,
            success=True,
            session_id=session_id,
            dedup_key=key,
            pattern_role=first_flag.role,
            pattern_action=first_flag.action,
            profile=profile_name,
            ingress=ingress,
            message_count=message_count,
            conversation_key=conv_key,
            streamed=streamed,
            ignored_params=ignored_params,
            has_tool_calls=request_has_tool_turns,
        )

    # Step 6: redact input per the profile's PII policy (PRD-012 Sections
    # 6.1, 6.3, F8). Resolved once per request, from the name step 5 resolved:
    # `chat` for /query and the chat UI, a name without a PII policy falls
    # back to `chat` (D8).
    policy = get_pii_policy(profile_name)

    # PRD-020 D7, 6.6, T4: decided once, by the Route alone (an internal
    # provider that declares `pii: relaxed`, with the PII switch on) -- never
    # from a request field, role, profile or host. It skips only input
    # redaction and the code size limit: patterns above and output redaction
    # below are unchanged. `pii_detected_input=0` on such a row means not
    # analyzed, and `pii_input_relaxed` records that it was a decision.
    relaxed = route.relaxes_input()
    # PRD-021 T10: configuration only -- the switch and the route, never a finding.
    if safe is not None and settings.PII_REDACTION_ENABLED and not relaxed:
        safe.stage("masking_input")

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
    over = None if relaxed else _redaction_limit_exceeded(messages, policy)
    if over is not None:
        maximum, actual = over
        log_query(
            # PRD-021 F7: refused before the upstream opened: nothing was delivered.
            streamed_realtime=False,
            reasoning_shown=False,
            **_route_fields(route),
            pii_input_relaxed=relaxed,
            user_id=identity.user_id,
            prompt=prompt,
            device=device,
            success=False,
            error_message=f"redaction limit: characters {actual} > {maximum}",
            session_id=session_id,
            dedup_key=key,
            profile=profile_name,
            ingress=ingress,
            message_count=message_count,
            conversation_key=conv_key,
            streamed=streamed,
            ignored_params=ignored_params,
            has_tool_calls=request_has_tool_turns,
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
    # today's "redact every message". Only the final turn's entities
    # count toward the audit's PII fields (PRD-010 D7): re-redacting history
    # that already passed once is not a new PII event, or every later row of
    # a session would misreport one. The final turn is `user` or `tool` (step
    # 0, PRD-017 D7), and both policies cover both roles. A `tool` turn's
    # content is redacted like any covered turn (PRD-017 Section 6.5);
    # assistant `tool_calls` are not (D13).
    #
    # Relaxed (PRD-020 D7): the loop is bypassed. The original messages go
    # upstream as received (same objects, tool fields included) and no entity
    # is recorded.
    redacted_messages: list[Message] = list(messages) if relaxed else []
    input_entities: list[str] = []
    last_index = len(messages) - 1
    for index, message in enumerate([] if relaxed else messages):
        if message.role not in policy.input_roles:
            # The same object, every field included, so it reaches upstream
            # byte-identical: `code`'s `system` turn, the client's own prompt
            # (PRD-012 D3). Every policy covers `user`, `assistant` and `tool`,
            # so no turn that carries tool fields takes this branch.
            redacted_messages.append(message)
            continue
        try:
            redacted_content, entities = _redact(message.content, policy)
        except PiiRedactorError as exc:
            log_query(
                # PRD-021 F7: refused before the upstream opened: nothing was delivered.
                streamed_realtime=False,
                reasoning_shown=False,
                **_route_fields(route),
                pii_input_relaxed=relaxed,
                user_id=identity.user_id,
                prompt=prompt,
                device=device,
                success=False,
                error_message=str(exc),
                session_id=session_id,
                dedup_key=key,
                profile=profile_name,
                ingress=ingress,
                message_count=message_count,
                conversation_key=conv_key,
                streamed=streamed,
                ignored_params=ignored_params,
                has_tool_calls=request_has_tool_turns,
            )
            raise
        # `replace`, not `Message(role, content)`: an assistant turn's
        # `tool_calls` and a tool turn's `tool_call_id` go upstream as received.
        # Arguments are never redacted; only `content` reaches `_redact`
        # (PRD-012 Section 6.5, PRD-017 D13).
        redacted_messages.append(dataclasses.replace(message, content=redacted_content))
        if index == last_index:
            input_entities = entities

    # Step 7: upstream. params is forwarded only when set: the existing
    # injected call_openrouter stubs across the suite have signature
    # (messages, model, api_key) and raise TypeError on an unexpected
    # params= keyword (PRD-010 STORY-005 Technical Notes). A tools= keyword is
    # passed under the same rule (PRD-017 STORY-008).
    extra: dict[str, Any] = {}
    if params is not None:
        extra["params"] = params
    if tools is not None:
        extra["tools"] = tools
    # PRD-021 6.3: with a sink, the commit id is made here and `committed` is
    # signalled exactly once -- on the first event of a stream, or on entry for a
    # buffered call. `sink=None`: no id, no phases, no stream. STORY-009 (F7, D17)
    # persists `completion_id` only when `realtime_request`: a buffered row
    # stores NULL even though a sink was told an id.
    completion_id: Optional[str] = None
    streamed_step = bool(visibility is not None and visibility.upstream_streamed)
    if safe is not None:
        safe.phase("waiting")
    # T6: what counts as released. A non-empty text or reasoning passed to the
    # sink is something the reader already holds; only then is a mid-stream
    # fault charged. `received_*` is everything that arrived, forwarded or not.
    released = False
    # PRD-021 F7: a non-empty reasoning text reached the sink (`released` also
    # flips on content, so it cannot say this). Persisted as `reasoning_shown`.
    reasoning_sent = False
    received_text: list[str] = []
    received_calls: dict[int, dict[str, Any]] = {}
    # PRD-021 6.5, D7, D8 (STORY-008): the two gates exist only for a streamed
    # realtime request. The content gate runs when the master switch is on and the
    # policy redacts output (`code` may not: raw forward, no final pass, step 8
    # as today). `_redact` is called through a lambda so the spy on this module's
    # binding sees the gate's final pass as it sees step 8's.
    content_gate: Optional[OutputGate] = None
    reasoning_gate: Optional[OutputGate] = None
    gate_result: Optional[GateResult] = None
    raw_reasoning: list[str] = []  # reasoning granted but not realtime: redacted whole
    reasoning_text: Optional[str] = None
    stream_redaction_divergence = False
    if streamed_step and visibility is not None and visibility.realtime:
        if gate_applies(policy, settings.PII_REDACTION_ENABLED):
            content_gate = OutputGate(
                policy,
                settings.STREAM_HOLDBACK_MAX_CHARACTERS,
                final_redact=lambda text, pol: _redact(text, pol),
            )
        if visibility.reasoning:
            reasoning_gate = OutputGate(
                reasoning_policy(policy),
                settings.STREAM_HOLDBACK_MAX_CHARACTERS,
                final_redact=redact_reasoning,
            )
    if safe is not None and not streamed_step:
        completion_id = "chatcmpl-harness-rt-" + uuid.uuid4().hex
        safe.committed(completion_id)
    try:
        if streamed_step:
            assert safe is not None and visibility is not None and route is not None
            stream_request = UpstreamRequest(redacted_messages, route.upstream_model, params, tools)
            tool_kinds = {n: m.kind for n, m in action_config.get_policy().tools.items()}
            phase_now: Optional[str] = "waiting"
            events: list[UpstreamEvent] = []
            for event in stream_upstream(
                redacted_messages, model=model, api_key=openrouter_api_key, **extra
            ):
                if completion_id is None:
                    completion_id = "chatcmpl-harness-rt-" + uuid.uuid4().hex
                    safe.committed(completion_id)
                    if realtime_request:
                        # PRD-021 D15: user, model and id; never content or reasoning.
                        logger.info(
                            "realtime stream committed: user_id=%s model=%s completion_id=%s",
                            identity.user_id, model, completion_id,
                        )
                events.append(event)
                moved = phase_of(event, phase_now, tool_kinds)  # type: ignore[arg-type]
                if moved is not None:
                    phase_now = moved[0]
                    safe.phase(moved[0], moved[1])
                # Empty text never reaches the sink (STORY-001: collect needs the
                # event, a reader does not). Tool-call fragments are held, never
                # forwarded (D6, T1): a ToolCallDelta is read here only to count it.
                if isinstance(event, TextDelta) and event.text != "":
                    received_text.append(event.text)
                    if visibility.realtime:
                        # `released` flips on what the gate lets out, not on
                        # receipt (T6): a gate holding everything has shown nothing.
                        out = content_gate.feed(event.text) if content_gate else event.text
                        if out:
                            safe.content(out)
                            released = True
                elif isinstance(event, ReasoningDelta) and event.text != "":
                    received_text.append(event.text)
                    if visibility.reasoning and visibility.realtime:
                        assert reasoning_gate is not None
                        out = reasoning_gate.feed(event.text)
                        if out:
                            safe.reasoning(out)
                            released = True
                            reasoning_sent = True
                    elif visibility.reasoning:
                        raw_reasoning.append(event.text)
                elif isinstance(event, ToolCallDelta):
                    held = received_calls.setdefault(
                        event.index, {"id": None, "name": None, "arguments": []}
                    )
                    held["id"] = held["id"] or event.id
                    held["name"] = held["name"] or event.name
                    held["arguments"].append(event.arguments)
            # End of stream (PRD-021 6.5): the held tails leave last, reasoning
            # first, then content, so the content remainder is the last content
            # delta. A fault here is a fault after a release like any other.
            if reasoning_gate is not None:
                reasoning_done = reasoning_gate.finish()
                if reasoning_done.remainder:
                    safe.reasoning(reasoning_done.remainder)
                    released = True
                    reasoning_sent = True
                if reasoning_done.diverged:
                    logger.warning(
                        "stream redaction diverged (reasoning): user_id=%s completion_id=%s",
                        identity.user_id, completion_id,
                    )
            if content_gate is not None:
                gate_result = content_gate.finish()
                if gate_result.remainder:
                    safe.content(gate_result.remainder)
                    released = True
                if gate_result.diverged:
                    stream_redaction_divergence = True
                    logger.warning(
                        "stream redaction diverged: user_id=%s completion_id=%s",
                        identity.user_id, completion_id,
                    )
            if raw_reasoning:
                # D8: collected and returned whole, redacted, never persisted.
                reasoning_text = redact_reasoning("".join(raw_reasoning), policy).text
            # D4: a realtime stream is billed like a whole answer, so a missing
            # usage chunk is estimated whatever the provider's mode; progress-only
            # keeps today's rule (nothing was released, nothing is charged).
            # model_used stays the requested id, as call_upstream makes it (PRD-020 D13).
            openrouter_result = dataclasses.replace(
                collect(
                    events,
                    provider=route.provider,
                    request=stream_request,
                    usage_missing="estimate" if visibility.realtime else None,
                ),
                model_used=model,
            )
        else:
            openrouter_result = call_openrouter(
                redacted_messages, model=model, api_key=openrouter_api_key, **extra
            )
    except (OpenRouterError, PiiRedactorError) as exc:
        # A gate failure (PiiRedactorError from feed/finish) is the same fault as
        # a dropped stream: the same T6 charge, the same failure row (STORY-008).
        # PRD-021 T6 / PRD-020 D8: text already shown to a reader was spent
        # upstream, so charge the estimate of what was received before the fault,
        # before the failure row. Nothing released: nothing charged (today's rule).
        if released and admission is not None and openrouter_api_key is None and route is not None:
            charge(
                identity.user_id,
                admission.day,
                None,
                None,
                estimate_tokens(
                    redacted_messages,
                    (
                        "".join(received_text),
                        tuple(
                            ToolCallSpec(c["id"] or "", c["name"] or "", "".join(c["arguments"]))
                            for _, c in sorted(received_calls.items())
                        ),
                    ),
                    route.provider.estimate_chars_per_token,
                    tools=tools.tools if tools is not None else None,
                ),
            )
        log_query(
            # PRD-021 F7, D14, D17: what was true at this point of the request.
            streamed_realtime=realtime_request,
            reasoning_shown=reasoning_sent,
            stream_redaction_divergence=stream_redaction_divergence,
            completion_id=completion_id if realtime_request else None,
            **_route_fields(route),
            pii_input_relaxed=relaxed,
            user_id=identity.user_id,
            prompt=prompt,
            device=device,
            model_used=model,
            # No input_tokens/output_tokens: there is no result to read them
            # from, and NULL says no upstream usage was reported (PRD-013 6.2).
            success=False,
            error_message=str(exc),
            session_id=session_id,
            dedup_key=key,
            profile=profile_name,
            ingress=ingress,
            message_count=message_count,
            conversation_key=conv_key,
            streamed=streamed,
            ignored_params=ignored_params,
            has_tool_calls=request_has_tool_turns,
        )
        raise

    # Step 7b: charge (PRD-013 Sections 6.1, 6.5; D8; F11; T3, T8).
    #
    # Here, as soon as the provider has reported usage and before step 8, so
    # the output-redaction error arm below cannot skip it: tokens spent on a
    # response the user never receives are still spent (PRD-009 Risk 4, T3).
    # The upstream-error arm above re-raises before reaching this line, so a
    # call that reported nothing charges nothing.
    #
    # `admission` is None exactly when the switch was off at step 2c; reading
    # it rather than the setting means a request is charged by the rule it was
    # admitted under, and always has a row to charge. BYOK spends the caller's
    # own key, so it is rate-limited at 2c but charges nothing here (D8, T14);
    # its audit row still records the tokens.
    #
    # The admitted `day`, not today: a request straddling midnight is charged
    # to the day it was admitted. charge() fails open (T8) -- a storage error
    # is logged at ERROR with the user, day and counts and the caller still
    # gets the answer; the audit row's token columns are the record.
    if admission is not None and openrouter_api_key is None:
        charge(
            identity.user_id,
            admission.day,
            openrouter_result.input_tokens,
            openrouter_result.output_tokens,
            openrouter_result.tokens_used,
        )

    # Step 7c: actions (PRD-017 Section 6.1; F6; D1, D2, D9; T1).
    #
    # After 7b, so the tokens are charged whatever the decision (PRD-013 T3).
    # Before step 8, which needs the final content: the policy classifies the
    # arguments as the model wrote them (PRD-016 6.1), and the notes it yields
    # are joined after redaction below. It runs only when the upstream returned
    # calls, which D18 limits to a request that sent `tools=`; `/query`, the chat
    # UI and a `/v1` request without tools never enter it.
    #
    # `ToolCallSpec` -> `ToolCall` is field for field (F6): the arguments string
    # is the same object, never parsed here. evaluate_all() never raises for
    # model input (PRD-016 F7); apply_decisions()' ValueError is a programming
    # error and propagates, so no call is ever released undecided (T1).
    outcome: Optional[tool_release.ToolOutcome] = None
    if openrouter_result.tool_calls:
        if safe is not None:
            safe.stage("evaluating_actions")
        calls = tuple(
            action_adapters.ToolCall(c.id, c.name, c.arguments)
            for c in openrouter_result.tool_calls
        )
        decisions = action_policy.evaluate_all(calls, identity)
        outcome = tool_release.ToolOutcome(
            release=tool_release.apply_decisions(openrouter_result.tool_calls, decisions),
            decisions=decisions,
        )
    # PRD-017 D19: the request half, or the upstream response carried calls
    # (counted before release, so an all-denied response is still a tool turn).
    has_tool_calls = request_has_tool_turns or bool(openrouter_result.tool_calls)

    # Step 8: redact the response only when the policy's output switch is on,
    # then audit and return. `chat` always redacts it. `code` does not by
    # default (PRD-012 D1): the reader of a coding agent's output is the file
    # system, and a placeholder in a response becomes a placeholder in a file.
    # Its row then has pii_detected_output=0 because the output was **not
    # analyzed**, not because it was clean; the row's `profile` column says
    # which it was (PRD-012 D9). Only the upstream's content is redacted, never a
    # call's arguments (PRD-017 Section 6.5, D13); the denial notes are joined
    # after it, so they are never masked (Section 6.6).
    if gate_result is not None:
        # PRD-021 6.5: the gate's single whole-reply pass *is* step 8's redaction;
        # it is authoritative for the response, the bubble and the entities, and
        # runs once (nothing is masked now, so no `masking_output` stage).
        redacted_response, output_entities = gate_result.final_text, gate_result.final_entities
    elif policy.output:
        if safe is not None and settings.PII_REDACTION_ENABLED:
            safe.stage("masking_output")
        try:
            redacted_response, output_entities = _redact(openrouter_result.response, policy)
        except PiiRedactorError as exc:
            log_query(
                # PRD-021 F7, D14, D17: what was true at this point of the request.
                streamed_realtime=realtime_request,
                reasoning_shown=reasoning_sent,
                stream_redaction_divergence=stream_redaction_divergence,
                completion_id=completion_id if realtime_request else None,
                **_route_fields(route),
                pii_input_relaxed=relaxed,
                user_id=identity.user_id,
                prompt=prompt,
                device=device,
                response=openrouter_result.response,
                model_used=openrouter_result.model_used,
                tokens_used=openrouter_result.tokens_used,
                input_tokens=openrouter_result.input_tokens,
                output_tokens=openrouter_result.output_tokens,
                usage_estimated=openrouter_result.usage_estimated,
                success=False,
                error_message=str(exc),
                pii_detected_input=bool(input_entities),
                pii_entities=input_entities,
                session_id=session_id,
                dedup_key=key,
                profile=profile_name,
                ingress=ingress,
                message_count=message_count,
                conversation_key=conv_key,
                streamed=streamed,
                ignored_params=ignored_params,
                has_tool_calls=has_tool_calls,
            )
            # Nothing is released on this arm, and record() is a step 8 call
            # against the success row only (PRD-017 F7): no decision rows here.
            raise
    else:
        redacted_response = openrouter_result.response
        output_entities = []

    # The `outcome is None` branch is `/query`'s path, byte for byte.
    content = (
        redacted_response
        if outcome is None
        else tool_release.content_with_notes(redacted_response, outcome.release.notes)
    )

    masked_entities = sorted(set(input_entities) | set(output_entities))

    # PRD-018 D13, F7: `log_query` returns an AuditRef. When the row could only
    # be journaled it carries `audit_id=None`, and (on a response with
    # decisions) the decisions ride in the same journal entry through
    # `journal_decisions`, so the release below follows a commit or an fsync.
    try:
        audit_ref = log_query(
            # PRD-021 F7, D14, D17: what was true at this point of the request.
            streamed_realtime=realtime_request,
            reasoning_shown=reasoning_sent or bool(reasoning_text),
            stream_redaction_divergence=stream_redaction_divergence,
            completion_id=completion_id if realtime_request else None,
            **_route_fields(route),
            pii_input_relaxed=relaxed,
            user_id=identity.user_id,
            prompt=prompt,
            device=device,
            response=openrouter_result.response,
            model_used=openrouter_result.model_used,
            tokens_used=openrouter_result.tokens_used,
            input_tokens=openrouter_result.input_tokens,
            output_tokens=openrouter_result.output_tokens,
            usage_estimated=openrouter_result.usage_estimated,
            # PRD-017 D19: the request carried tool turns, or the response carried
            # calls (before release). The row's `response` stays what the upstream
            # said; the decisions live in `action_decisions` (STORY-010 DD-2).
            has_tool_calls=has_tool_calls,
            success=True,
            pii_detected_input=bool(input_entities),
            pii_detected_output=bool(output_entities),
            pii_entities=masked_entities,
            session_id=session_id,
            dedup_key=key,
            profile=profile_name,
            ingress=ingress,
            message_count=message_count,
            conversation_key=conv_key,
            streamed=streamed,
            ignored_params=ignored_params,
            journal_decisions=(
                None
                if outcome is None
                else functools.partial(
                    action_audit.decision_rows,
                    outcome.decisions,
                    identity,
                    session_id=session_id,
                )
            ),
        )
    except AuditUnavailableError as exc:
        if outcome is None:
            raise  # /query 503, /v1 503 storage_unavailable (6.7)
        # R2: a response with decisions whose row can be neither committed nor
        # journaled is PRD-017's 500 internal_error. No row exists, so no mark.
        logger.error(
            "action audit failed: user_id=%s audit_id=%s", identity.user_id, None
        )
        raise ActionAuditError(
            "Action audit failed: decisions could not be recorded"
        ) from exc

    # The decision audit (PRD-017 F7, D8; T5): after the row, whose id it needs
    # (PRD-016 6.1). Fail closed: no release without the decision rows. Only the
    # user and `audit_id` are logged, never the arguments or the driver's text.
    #
    # PRD-018 D13 (R3): a journaled row (`audit_id is None`) already carries its
    # decisions in its own entry, so `record` is not called for it. Otherwise the
    # journal is "recorded" for the decisions too: `record` journals them alone
    # on a StorageUnavailableError, and an AuditUnavailableError from a failed
    # append is a StorageError, so it takes this arm unchanged.
    if outcome is not None and audit_ref.audit_id is not None:
        audit_id = audit_ref.audit_id
        try:
            action_audit.record(
                outcome.decisions, identity, audit_ref=audit_ref, session_id=session_id
            )
        except StorageError as exc:
            logger.error(
                "action audit failed: user_id=%s audit_id=%s", identity.user_id, audit_id
            )
            # D8 (orchestrator decision): the success row exists, and a success
            # row is a prior query, so an honest retry would be held as a
            # duplicate. Mark it failed, best effort: if this fails too the
            # duplicate window holds the retry, and we still fail closed.
            try:
                mark_audit_log_failed(audit_id, _ACTION_AUDIT_FAILED)
            except Exception:
                logger.error(
                    "action audit failure not marked: user_id=%s audit_id=%s",
                    identity.user_id,
                    audit_id,
                )
            raise ActionAuditError(
                "Action audit failed: decisions could not be recorded"
            ) from exc

    success = QuerySuccessResponse(
        response=content,
        audit_id=audit_ref.audit_id,
        audit_ref=audit_ref.write_id,
        model_used=openrouter_result.model_used,
        tokens_used=openrouter_result.tokens_used,
        pii_redacted=bool(masked_entities),
        pii_entities_masked=masked_entities,
    )
    if outcome is not None:
        # Private, never serialized (STORY-010 DD-1): the router's only source of
        # released calls (T1).
        success._tool_outcome = outcome
    if reasoning_text is not None:
        # PRD-021 D8: private and never passed to log_query or chat_messages.
        success._reasoning = reasoning_text
    if streamed_step:
        # PRD-021 STORY-010: the streamed step never goes through the router's
        # `_Upstream` wrapper, so its finish reason and token split travel here.
        # Private, never serialized.
        success._upstream_result = openrouter_result
    return success


def run_query(
    identity: Identity,
    prompt: str,
    device: Optional[str],
    model: str,
    openrouter_api_key: Optional[str],
    call_openrouter: Callable[..., OpenRouterResult] = call_openrouter,
    session_id: Optional[str] = None,
    *,
    # PRD-013 Section 6.9: `/query` is this adapter's caller, so the default
    # names it. ChatState's history-off branch passes "chat".
    ingress: Optional[Ingress] = "query",
) -> QueryPipelineResult:
    return run_conversation(
        identity,
        [Message("user", prompt)],
        device,
        model,
        openrouter_api_key,
        call_openrouter=call_openrouter,
        session_id=session_id,
        ingress=ingress,
    )
