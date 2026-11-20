"""The OpenAI-compatible ingress (PRD-015 Sections 6.1, 6.4, 7.2, 7.4).

`POST /v1/chat/completions` authenticates exactly as `/query` does, turns the
body into pipeline arguments with `v1_translate`, and runs `run_conversation`
on the dedicated pipeline executor. The call site names the profile and the
door -- the literals `profile="code"` and `ingress="v1"` -- never a request
field (PRD-011 Section 6.6, PRD-013 Section 6.9).

`call_openrouter` is imported by name into this module so tests replace
`app.routers.v1.call_openrouter`, the binding rule `app/routers/query.py`
follows.

STORY-009 shipped the non-streaming success path; STORY-010 maps every
verdict to its Section 7.5 error and installs the `/v1`-scoped handlers for
the 401/403 dependency refusals and the 400 body failures. STORY-011 maps the
pipeline's faults to Section 7.5's 502/500 rows, retryable only when the
fault is transient (D7). STORY-012 added `GET /v1/models`, which lists
`MODEL_ALLOWLIST`, refuses the break-glass credential itself (no pipeline
runs there) and writes no row (Section 7.7). STORY-013 added the buffered
stream: a `stream: true` request is committed to SSE only once the upstream
call has started (Section 6.4), so every verdict keeps its real status.
PRD-017 STORY-008 passes the tool request through under `V1_TOOLS_ENABLED`;
STORY-010 decides and records every call in the pipeline (step 7c).
STORY-011 releases the allowed calls on the non-streamed body:
`translate_result` reads them from the pipeline result's `tool_outcome`,
never from `upstream.result` (T1). STORY-012 streams them.
"""

import asyncio
import functools
import logging
import time
from http import HTTPStatus
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from fastapi import APIRouter, Depends, FastAPI, Header, Request
from fastapi.exception_handlers import (
    http_exception_handler,
    request_validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import settings
from app.db.errors import AuditHeadroomError, AuditUnavailableError
from app.middleware.auth import require_permission
from app.models.schemas import QuerySuccessResponse
from app.models.v1_schemas import (
    ChatCompletion,
    ChatCompletionRequest,
    ErrorDetail,
    ErrorResponse,
    ModelCapabilities,
    ModelEntry,
    ModelHarness,
    ModelList,
)
from app.services import authz, provider_registry, v1_sse
from app.services.authz import (
    PERMISSION_QUERY_SUBMIT,
    PERMISSION_REASONING_VIEW,
    PERMISSION_STREAM_REALTIME,
)
from app.services.delivery import QueueSink, Visibility
from app.services.duplicate_checker import DuplicateCheckError
from app.services.identity import Identity
from app.services.upstream import (
    UpstreamError as OpenRouterError,
    UpstreamResult as OpenRouterResult,
    call_upstream as call_openrouter,
)
from app.services.upstream.types import ChainExhausted
from app.services.pii_redactor import PiiRedactorError
from app.services.pipeline_executor import run_in_pipeline
from app.services.query_pipeline import ActionAuditError, run_conversation
from app.services.storage_faults import (
    audit_unavailable_retry_after,
    storage_unavailable_cause,
)
from app.services.usage_limits import UsageLimitError
from app.services.v1_translate import (
    AUDIT_UNAVAILABLE_MESSAGE,
    BREAK_GLASS_NOT_PERMITTED,
    DEVICE_HEADER,
    INTERNAL_ERROR,
    INVALID_API_KEY,
    INVALID_REQUEST,
    MODEL_NOT_FOUND,
    PERMISSION_DENIED,
    REDACTION_FAILED,
    STORAGE_UNAVAILABLE,
    STORAGE_UNAVAILABLE_MESSAGE,
    UPSTREAM_ERROR,
    UPSTREAM_UNAVAILABLE,
    V1Error,
    V1RequestError,
    translate_device,
    translate_exhausted,
    translate_fault,
    translate_request,
    translate_result,
    translate_verdict,
)

logger = logging.getLogger(__name__)

router = APIRouter()

_V1_PREFIX = "/v1/"

# An `HTTPException` under `/v1/` as (type, code), by status (PRD-015 Section
# 7.5). 401 and 403 are `require_identity` / `require_permission`; 404 and 405
# are routing (an unknown path, a wrong method). `model_not_found` is not
# here: `retrieve_model` builds that 404 itself. Any other 4xx is
# `_OTHER_CLIENT_ERROR`, any 5xx `_SERVER_ERROR`: nothing under `/v1/` raises
# one but `require_identity`'s storage refusal (503, PRD-018 D8). The
# deliberate 5xx are the pipeline faults, which `chat_completions` maps itself
# (`_PIPELINE_FAULTS`).
_HTTP_ERRORS: Dict[int, Tuple[str, str]] = {
    401: ("authentication_error", INVALID_API_KEY),
    403: ("permission_error", PERMISSION_DENIED),
    404: ("invalid_request_error", "not_found"),
    405: ("invalid_request_error", "method_not_allowed"),
    503: ("api_error", STORAGE_UNAVAILABLE),
}
_OTHER_CLIENT_ERROR = ("invalid_request_error", INVALID_REQUEST)
_SERVER_ERROR = ("api_error", INTERNAL_ERROR)

# What `run_conversation` raises (PRD-015 Section 7.5): `/query`'s chain in
# app/routers/query.py minus `ChatSessionError`, which needs a session and
# `/v1` passes none, plus `ActionAuditError`, which only a tools request
# reaches (PRD-017 D8). Anything else is a bug and stays Starlette's 500.
_PIPELINE_FAULTS = (
    OpenRouterError,
    DuplicateCheckError,
    UsageLimitError,
    PiiRedactorError,
    ActionAuditError,
    # PRD-018 D10/D13, T5: a row (success or refusal) neither committed nor
    # journaled. Tools requests reach ActionAuditError instead (R2).
    # `AuditHeadroomError` (STORY-011) is a subclass, raised before step 2, so
    # tools requests get it as 503 too.
    AuditUnavailableError,
)

# The faults PRD-018 D8's outage rule applies to. `ActionAuditError` is
# deliberately absent: tools keep PRD-017's 500 `internal_error` (PRD-018
# Section 6.7). `ChatSessionError` is unreachable on `/v1` (no session).
_STORAGE_GATE_FAULTS = (DuplicateCheckError, UsageLimitError)


class _Upstream:
    """The `call_openrouter` the pipeline is handed, capturing its result.

    `QuerySuccessResponse` carries neither the finish reason nor the token
    split, and `/query`'s body must not change for them (STORY-001), so the
    router keeps the `OpenRouterResult` itself (PRD-015 Section 6.4).
    `call_openrouter` is looked up at call time, so a test's replacement
    applies. `kwargs` is forwarded as received: `params=` reaches the client
    only when the pipeline passed it, and the suite's stubs with signature
    (messages, model, api_key) keep working (PRD-010 STORY-005).

    It is also the commit signal for a streamed request (Section 6.4): being
    called means step 7 has started, so every verdict is behind the request.
    `called` is set on the pipeline thread before any result can exist, which
    makes it the deterministic answer to "commit or not"; `started` wakes the
    event loop for it.

    `result.tool_calls` are the raw upstream calls, decided only inside the
    pipeline: they are never read to build a response (PRD-017 T1).
    """

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self.result: Optional[OpenRouterResult] = None
        self.called = False
        self.started = asyncio.Event()
        self._loop = loop

    def __call__(self, messages, model, api_key, **kwargs) -> OpenRouterResult:
        self.called = True
        self._loop.call_soon_threadsafe(self.started.set)
        self.result = call_openrouter(messages, model=model, api_key=api_key, **kwargs)
        return self.result


class _CommitSink(QueueSink):
    """The sink a `/v1` request passes when step 2d will stream upstream (PRD-021 6.3).

    Its `committed` is the commit signal of a streamed upstream, as
    `_Upstream.__call__` is of a buffered one: `called` is set on the pipeline
    thread (the deterministic answer to "commit or not"), `started` wakes the
    event loop. With `forward=False` (a stream that is not delivered in real
    time: reasoning only, or `stream: false`) every put is dropped, so nothing
    accumulates in a queue nobody reads and only the commit signal acts.
    """

    def __init__(self, loop: asyncio.AbstractEventLoop, *, forward: bool) -> None:
        super().__init__(loop)
        self.called = False
        self.completion_id: Optional[str] = None
        self.started = asyncio.Event()
        self._forward = forward

    def _put(self, event) -> None:
        if self._forward:
            super()._put(event)

    def committed(self, completion_id: str) -> None:
        self.called = True
        self.completion_id = completion_id
        try:
            self._loop.call_soon_threadsafe(self.started.set)
        except RuntimeError:
            pass  # the loop is closed: the consumer is gone
        super().committed(completion_id)


def _visibility(identity: Identity, model: str, stream: bool) -> Optional[Visibility]:
    """Step 2d's answer for this request, or None when nothing streams (PRD-021 D22).

    One rule: the pipeline's own `Visibility.compute`, with the same inputs, so
    the router's sink decision cannot drift from step 7's. None (no sink, today's
    path) when the switch is off or the caller may not use the model: the
    pipeline's single denial applies then (T3). Grants are read with `holds`,
    never `authorize` (T8).
    """
    if not settings.STREAMING_ENABLED:
        return None
    try:
        caps = authz.authorize_route(identity, model).capabilities
    except authz.PermissionDenied:
        return None
    return Visibility.compute(
        streaming_enabled=True,
        holds_realtime=authz.holds(identity, PERMISSION_STREAM_REALTIME),
        holds_reasoning=authz.holds(identity, PERMISSION_REASONING_VIEW),
        caps=caps,
        ingress="v1",
        streamed=stream,
    )


def _error_body(
    type_: str,
    code: str,
    message: str,
    param: Optional[str] = None,
    harness: Optional[Dict[str, Any]] = None,
) -> ErrorResponse:
    """The error object itself, sent as a JSON body or as a post-commit SSE event."""
    return ErrorResponse(
        error=ErrorDetail(message=message, type=type_, param=param, code=code, harness=harness)
    )


def _error(
    status_code: int,
    type_: str,
    code: str,
    message: str,
    param: Optional[str] = None,
    headers: Optional[Dict[str, str]] = None,
    harness: Optional[Dict[str, Any]] = None,
) -> JSONResponse:
    """The one place a `/v1` error body is built.

    Every 4xx carries `x-should-retry: false` (Section 7.5, T7): 400/401/403
    are not retried by the OpenAI SDKs anyway, so the header makes "retry: no"
    one rule rather than one per status. A 5xx passes its own headers.
    """
    body = _error_body(type_, code, message, param, harness)
    if status_code < 500:
        headers = {**(headers or {}), "x-should-retry": "false"}
    return JSONResponse(body.model_dump(mode="json"), status_code=status_code, headers=headers)


def _from_v1_error(error: V1Error) -> JSONResponse:
    # A retryable fault carries no header, so the SDK's status rule retries
    # it; `true` would force a retry the status rule might not make (D7).
    headers: Optional[Dict[str, str]] = None if error.retryable else {"x-should-retry": "false"}
    if error.retry_after_seconds is not None:
        # PRD-018 D8: the outage tells the client when to come back.
        headers = {**(headers or {}), "Retry-After": str(error.retry_after_seconds)}
    return _error(
        error.status_code, error.type, error.code, error.message, error.param,
        headers=headers,
        harness=error.harness,
    )


def _fault_code(exc: Exception) -> str:
    """A `_PIPELINE_FAULTS` exception as its Section 7.5 code (D7).

    An upstream fault is retryable exactly when the client says so
    (`_classify_http_error`). A storage fault is transient by nature. A
    redaction failure repeats on the same text. A post-commit fault on a
    stream is the same code, sent as an SSE `error` event (Section 7.6). A gate
    that failed because storage is unavailable is `storage_unavailable` (503,
    PRD-018 D8); any other storage fault stays `internal_error`.
    """
    if isinstance(exc, OpenRouterError):
        return UPSTREAM_UNAVAILABLE if exc.retryable else UPSTREAM_ERROR
    if isinstance(exc, AuditUnavailableError):
        return STORAGE_UNAVAILABLE
    if isinstance(exc, _STORAGE_GATE_FAULTS) and storage_unavailable_cause(exc) is not None:
        return STORAGE_UNAVAILABLE
    if isinstance(exc, (DuplicateCheckError, UsageLimitError, ActionAuditError)):
        return INTERNAL_ERROR
    if isinstance(exc, PiiRedactorError):
        return REDACTION_FAILED
    raise TypeError(f"no /v1 fault for {type(exc).__name__}")


def _outcome(
    pipeline: asyncio.Future, upstream: _Upstream, identity: Identity
) -> Union[ChatCompletion, V1Error]:
    """A finished pipeline as the completion or the error, for either response.

    Anything outside `_PIPELINE_FAULTS` is a bug and propagates.
    """
    try:
        result = pipeline.result()
    except _PIPELINE_FAULTS as exc:
        # The pipeline has already written whatever row `/query` writes for
        # the same fault: one `success=False` row for an upstream or
        # redaction failure, none for a failed duplicate lookup or usage gate.
        code = _fault_code(exc)
        # Who and which fault, never the message: a storage error's text is
        # driver output (T9's rule, applied to faults).
        logger.warning("v1 request failed: user_id=%s code=%s", identity.user_id, code)
        if isinstance(exc, AuditUnavailableError):
            # PRD-018 D10, T5: fixed copy that does not say "not sent" -- step 8
            # runs after the upstream call. Retry-After per R5. PRD-018 D10
            # (STORY-011): the headroom subclass is refused before step 2, so
            # the pre-model copy ("not sent") is true for it.
            return translate_fault(
                code,
                (
                    STORAGE_UNAVAILABLE_MESSAGE
                    if isinstance(exc, AuditHeadroomError)
                    else AUDIT_UNAVAILABLE_MESSAGE
                ),
                retry_after_seconds=audit_unavailable_retry_after(exc),
            )
        if code == STORAGE_UNAVAILABLE:
            # Fixed copy, never `str(exc)`: that is driver text (T9, PRD-018 D8).
            cause = storage_unavailable_cause(exc)
            assert cause is not None  # `_fault_code` named it from this cause
            return translate_fault(
                code, STORAGE_UNAVAILABLE_MESSAGE, retry_after_seconds=cause.retry_after_seconds
            )
        if isinstance(exc, ChainExhausted):
            # PRD-022 F7, O5: classified from the attributes (closed vocabulary),
            # never `str(exc)`; a last attempt that failed non-eligibly is the
            # original `OpenRouterError`, not this, and keeps `upstream_error`.
            return translate_exhausted(exc.skipped, exc.last_error, exc.retry_after_seconds)
        return translate_fault(code, str(exc))

    if not isinstance(result, QuerySuccessResponse):
        # A verdict: 400 or 403, never 429 or 5xx (D2, T7). The pipeline has
        # already written the row.
        return translate_verdict(result)

    # A success means step 7 ran: the wrapper holds its result, or, when step 7
    # streamed (PRD-021), the pipeline carried it on the response.
    upstream_result = upstream.result or result.upstream_result
    assert upstream_result is not None
    return translate_result(result, upstream_result, int(time.time()))


def _json_response(pipeline: asyncio.Future, upstream: _Upstream, identity: Identity) -> Any:
    outcome = _outcome(pipeline, upstream, identity)
    if isinstance(outcome, V1Error):
        return _from_v1_error(outcome)
    harness = outcome.harness
    # PRD-018 D14 (R4): the healthy header is unchanged; a journaled success has
    # no id, so it sends `X-Harness-Audit-Ref` instead.
    headers = (
        {"X-Harness-Audit-Id": str(harness.audit_id)}
        if harness.audit_id is not None
        else {"X-Harness-Audit-Ref": harness.audit_ref}
    )
    if harness.provider is not None:
        # PRD-022 F10: JSON only. A stream's headers go out at commit, before the
        # answer exists, so the buffered-SSE answer carries only the `model`.
        headers["X-Harness-Provider"] = harness.provider
    return JSONResponse(outcome.model_dump(mode="json"), headers=headers)


def _sse_outcome(
    pipeline: asyncio.Future, upstream: _Upstream, identity: Identity
) -> Union[ChatCompletion, List[str]]:
    """A finished pipeline as the completion, or the error events after commit (Section 7.6).

    The `200` is already sent, so there is no status left to fall back on:
    an exception outside `_PIPELINE_FAULTS` (a bug, which the JSON path
    leaves to Starlette's 500) is logged and sent as `internal_error`, so the
    stream ends with an event rather than a torn body. A post-commit
    `storage_unavailable` is sent the same way, without `Retry-After`: the
    headers are gone (PRD-018 Section 6.7).
    """
    try:
        outcome = _outcome(pipeline, upstream, identity)
    except Exception:
        logger.exception(
            "v1 stream failed after commit: user_id=%s code=%s", identity.user_id, INTERNAL_ERROR
        )
        outcome = translate_fault(INTERNAL_ERROR, HTTPStatus.INTERNAL_SERVER_ERROR.phrase)
    if isinstance(outcome, ChatCompletion):
        return outcome
    if outcome.harness is not None:
        # Only a verdict carries a pipeline response, and every verdict is
        # decided before step 7 (Risk 5). Sent as the error event regardless.
        logger.warning(
            "v1 verdict after stream commit: user_id=%s code=%s", identity.user_id, outcome.code
        )
    return [v1_sse.error_event(
        _error_body(outcome.type, outcome.code, outcome.message, outcome.param, outcome.harness)
    )]


def _sse_events(
    pipeline: asyncio.Future, upstream: _Upstream, identity: Identity, include_usage: bool
) -> List[str]:
    """`_sse_outcome` as the buffered stream's events, `[DONE]` included."""
    outcome = _sse_outcome(pipeline, upstream, identity)
    if isinstance(outcome, ChatCompletion):
        return v1_sse.completion_events(outcome, include_usage)
    return outcome


def _realtime_tail(
    pipeline: asyncio.Future,
    upstream: _Upstream,
    identity: Identity,
) -> Union[v1_sse.Tail, List[str]]:
    """The realtime stream's end: `_sse_outcome`, so the fault mapping and the T13
    warning are the buffered stream's. The notes come from step 7c's release (T1)."""
    outcome = _sse_outcome(pipeline, upstream, identity)
    if not isinstance(outcome, ChatCompletion):
        return outcome
    tool_outcome = pipeline.result().tool_outcome
    notes = tuple(tool_outcome.release.notes) if tool_outcome is not None else ()
    return v1_sse.Tail(outcome, notes)


def _tools_supported(identity: Identity, model: str) -> bool:
    """File-mode tool capability of `model`, decided only for a model the caller
    may use (PRD-020 T3). `authorize_route` is pure; a denial answers True so the
    pipeline's step-2 denial is the one verdict for an uncatalogued, forbidden or
    unlisted passthrough id, and a forbidden model's flag never leaks."""
    try:
        return authz.authorize_route(identity, model).capabilities.tools
    except authz.PermissionDenied:
        return True


@router.post("/v1/chat/completions")
async def chat_completions(
    body: ChatCompletionRequest,
    x_harness_device: Optional[str] = Header(default=None, alias=DEVICE_HEADER),
    identity: Identity = Depends(require_permission(PERMISSION_QUERY_SUBMIT)),
) -> Any:
    # Both refusals come before the pipeline, so neither writes a row (T9).
    try:
        device = translate_device(x_harness_device)
        # Read per request, so a flipped flag takes effect without a restart
        # and tests monkeypatch it (PRD-017 Section 6.7). The translator reads
        # no settings.
        # PRD-020 D6: in file mode the capability comes from the registry and
        # V1_TOOL_MODELS is not read; legacy passes the list and None.
        file_mode = not provider_registry.current().is_legacy
        call = translate_request(
            body,
            tools_enabled=settings.V1_TOOLS_ENABLED,
            tool_models=() if file_mode else settings.v1_tool_models_list,
            tools_supported=_tools_supported(identity, body.model) if file_mode else None,
        )
    except V1RequestError as exc:
        # T9: who and which rule, never the message, param value or body.
        logger.info("v1 request refused: user_id=%s code=%s", identity.user_id, exc.code)
        return _error(400, "invalid_request_error", exc.code, exc.message, exc.param)

    loop = asyncio.get_running_loop()
    upstream = _Upstream(loop)
    # PRD-021 6.3: a sink only when step 2d will stream upstream (real time or
    # reasoning); otherwise nothing changes (D22). Real time needs `stream: true`
    # too: `Visibility.compute(streamed=)` carries that rule.
    visibility = _visibility(identity, call.model, call.stream)
    sink: Optional[_CommitSink] = None
    realtime = bool(visibility is not None and visibility.realtime and call.stream)
    if visibility is not None and visibility.upstream_streamed:
        sink = _CommitSink(loop, forward=realtime)
    extra: Dict[str, Any] = {"sink": sink} if sink is not None else {}
    # A task, not an await: a streamed request waits on it alongside the
    # upstream signal. It is never cancelled (Section 7.6).
    pipeline = asyncio.ensure_future(run_in_pipeline(
        run_conversation,
        identity,
        call.messages,
        device,
        call.model,
        None,  # openrouter_api_key: BYOK is out (PRD-015 Section 4)
        call.params,
        call_openrouter=upstream,
        profile="code",
        ingress="v1",
        # From the request, on every arm: `_deny`'s rule that a defaulted
        # False would mislabel an SSE refusal (PRD-013 Section 6.9).
        streamed=call.stream,
        ignored_params=call.ignored_params,
        # None unless the flag is on and tools were sent; run_conversation
        # forwards it to step 7 only when set (PRD-017 STORY-008).
        tools=call.tools,
        **extra,
    ))
    # Whatever happens to this request, the pipeline finishes and its outcome
    # is retrieved.
    v1_sse.detach(pipeline)

    if call.stream:
        await v1_sse.wait_for_commit(
            pipeline, sink.started if sink is not None else upstream.started
        )
    else:
        await asyncio.wait({pipeline})

    # The commit rule (Section 6.4, D8): until the upstream is called, the
    # outcome is a verdict or a pre-upstream fault and keeps its real status.
    # Read from the wrapper's flag, not from which wait finished first.
    committed = upstream.called or (sink is not None and sink.called)
    if not (call.stream and committed):
        if sink is not None:
            sink.close()
        return _json_response(pipeline, upstream, identity)

    if sink is not None and realtime:
        # PRD-021 6.6: live deltas. `created` and `model` are fixed here so every
        # chunk agrees; the id is the commit id the role chunk carries (D15).
        live_sink = sink

        def on_close(completed: bool) -> None:
            live_sink.close()
            if not completed:
                # D15: the client left; the pipeline finishes, the row is written
                # and the tokens charged. User and id, never content.
                logger.info(
                    "v1 realtime stream disconnected: user_id=%s completion_id=%s",
                    identity.user_id, live_sink.completion_id,
                )

        return StreamingResponse(
            v1_sse.realtime_events(
                live_sink.queue,
                pipeline,
                created=int(time.time()),
                model=call.model,
                tail=functools.partial(_realtime_tail, upstream=upstream, identity=identity),
                include_usage=call.include_usage,
                interval=settings.V1_SSE_KEEPALIVE_SECONDS,
                coalesce_s=settings.STREAM_COALESCE_MS / 1000,
                on_close=on_close,
            ),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # No X-Harness-Audit-Id: the row does not exist yet. Every chunk's id
    # carries it, or the ref when the row was journaled (Section 7.6, PRD-018 D14).
    return StreamingResponse(
        v1_sse.stream(
            pipeline,
            functools.partial(
                _sse_events, upstream=upstream, identity=identity,
                include_usage=call.include_usage,
            ),
            settings.V1_SSE_KEEPALIVE_SECONDS,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# --- GET /v1/models (PRD-015 Section 7.7) ---------------------------------------


def _model_entry(model_id: str) -> ModelEntry:
    """One allowlisted name as its entry: `owned_by` is the prefix before `/`, else `harness`."""
    prefix, sep, _ = model_id.partition("/")
    return ModelEntry(id=model_id, owned_by=prefix if sep and prefix else "harness")


def _registry_entry(model: provider_registry.CatalogModel) -> ModelEntry:
    """A catalogued model as its file-mode entry (PRD-020 Section 10)."""
    caps = model.capabilities
    return ModelEntry(
        id=model.id,
        owned_by=model.provider_name,
        harness=ModelHarness(
            provider=model.provider_name,
            capabilities=ModelCapabilities(
                tools=caps.tools,
                streaming=caps.streaming,
                reasoning=caps.reasoning,
                max_context_tokens=caps.max_context_tokens,
            ),
        ),
    )


def _refuse_break_glass(identity: Identity) -> Optional[JSONResponse]:
    """The break-glass refusal for a route that runs no pipeline (PRD-015 Section 7.2).

    `chat_completions` leaves this to the pipeline's step 2b, which writes
    the row. Here nothing runs, so the router refuses and nothing is written.
    Only `resolve(ADMIN_TOKEN)` sets `break_glass`, so a user token with the
    `admin` role passes. `BREAK_GLASS_INGRESSES` is not read: its validator
    forbids `v1` (PRD-013), so the answer is always to refuse. The message is
    the pipeline's, so one rule reads the same on every `/v1` route.
    """
    if not identity.break_glass:
        return None
    logger.info(
        "v1 request refused: user_id=%s code=%s", identity.user_id, BREAK_GLASS_NOT_PERMITTED
    )
    return _error(
        403, "permission_error", BREAK_GLASS_NOT_PERMITTED,
        "Break-glass credential not permitted on this ingress: ingress:break_glass",
    )


@router.get("/v1/models")
async def list_models(
    identity: Identity = Depends(require_permission(PERMISSION_QUERY_SUBMIT)),
) -> Any:
    refusal = _refuse_break_glass(identity)
    if refusal is not None:
        return refusal
    if not provider_registry.current().is_legacy:
        # PRD-020 D4: the catalogued models this role may use, in registry order.
        return JSONResponse(ModelList(
            data=[_registry_entry(m) for m in provider_registry.visible_models(identity)]
        ).model_dump(mode="json"))
    # Read per request (tests monkeypatch it). An `admin` may send any model,
    # but "any" cannot be listed, so every role sees the configured entries.
    models = ModelList(data=[_model_entry(model) for model in settings.model_allowlist_list])
    return JSONResponse(models.model_dump(mode="json"))


@router.get("/v1/models/{model_id:path}")
async def retrieve_model(
    model_id: str,
    identity: Identity = Depends(require_permission(PERMISSION_QUERY_SUBMIT)),
) -> Any:
    # `:path` because ids contain `/`. Routing matches the decoded path, so
    # `openai%2Fgpt-4o` arrives as `openai/gpt-4o`.
    refusal = _refuse_break_glass(identity)
    if refusal is not None:
        return refusal
    # Exact match, no aliasing (D4). Neither the body nor the log names the
    # id: the rule is enough, and the id is the caller's input.
    if not provider_registry.current().is_legacy:
        # PRD-020 T3: uncatalogued, not-visible and passthrough ids share this
        # one branch, so the bodies are equal.
        for entry in provider_registry.visible_models(identity):
            if entry.id == model_id:
                return JSONResponse(_registry_entry(entry).model_dump(mode="json"))
        logger.info(
            "v1 request refused: user_id=%s code=%s", identity.user_id, MODEL_NOT_FOUND
        )
        return _error(404, "invalid_request_error", MODEL_NOT_FOUND, "model not found")
    if model_id not in settings.model_allowlist_list:
        logger.info(
            "v1 request refused: user_id=%s code=%s", identity.user_id, MODEL_NOT_FOUND
        )
        return _error(
            404, "invalid_request_error", MODEL_NOT_FOUND, "model is not in MODEL_ALLOWLIST"
        )
    return JSONResponse(_model_entry(model_id).model_dump(mode="json"))


# --- /v1-scoped exception handlers (PRD-015 Section 7.5, Risk 4) ---------------


def _is_v1(request: Request) -> bool:
    return request.url.path.startswith(_V1_PREFIX)


def _param(loc: Sequence[Union[str, int]]) -> Optional[str]:
    """A validation error's `loc` as the OpenAI `param`: `messages[0].content`.

    The leading "body" is dropped. A `json_invalid` loc is ("body", <offset>):
    an offset into the raw bytes is no parameter, so it is None, as is a
    missing body.
    """
    parts = list(loc)
    if parts and parts[0] == "body":
        parts = parts[1:]
    if not parts or not isinstance(parts[0], str):
        return None
    param = parts[0]
    for part in parts[1:]:
        param += f"[{part}]" if isinstance(part, int) else f".{part}"
    return param


async def _http_exception(request: Request, exc: StarletteHTTPException):
    if not _is_v1(request):
        return await http_exception_handler(request, exc)
    if exc.status_code in _HTTP_ERRORS:
        type_, code = _HTTP_ERRORS[exc.status_code]
    elif exc.status_code < 500:
        type_, code = _OTHER_CLIENT_ERROR
    else:
        type_, code = _SERVER_ERROR
    # The dependencies' details name the rule ("Permission denied: query:submit");
    # a non-string detail is replaced by the status phrase.
    if code == STORAGE_UNAVAILABLE:
        # PRD-018 D8: the identity refusal's detail is `/query`'s copy; `/v1`
        # sends its own fixed sentence. `headers=exc.headers` carries `Retry-After`.
        message = STORAGE_UNAVAILABLE_MESSAGE
    elif isinstance(exc.detail, str):
        message = exc.detail
    else:
        message = HTTPStatus(exc.status_code).phrase
    # T9. No identity here: the dependency refused before one existed.
    logger.info("v1 request refused: code=%s", code)
    return _error(exc.status_code, type_, code, message, headers=exc.headers)


async def _validation_exception(request: Request, exc: RequestValidationError):
    """A body that is not JSON or fails `ChatCompletionRequest`, as 400 `invalid_request`.

    The first error names the location and pydantic's rule (`msg`); its
    `input` and `ctx` are never read, so no content is echoed (T6). FastAPI
    parses the body before resolving dependencies, so a non-JSON body without
    a bearer is this 400, not a 401: nothing but the rule is disclosed.
    """
    if not _is_v1(request):
        return await request_validation_exception_handler(request, exc)
    errors = exc.errors()
    first = errors[0] if errors else {}
    param = _param(first.get("loc", ()))
    msg = first.get("msg", "Invalid request body")
    message = f"{param}: {msg}" if param else msg
    # T9. No user id: the identity dependency's result is not available here.
    logger.info("v1 request refused: user_id=%s code=%s", None, INVALID_REQUEST)
    return _error(400, "invalid_request_error", INVALID_REQUEST, message, param)


def install_error_handlers(app: FastAPI) -> None:
    """Make `/v1/*` errors OpenAI error objects, and leave every other path alone.

    Registered on the app, not the router: the 401/403 from the auth
    dependencies and the body's `RequestValidationError` are raised before the
    route body, and routing's 404/405 before any route. Outside `/v1/` both
    handlers delegate to FastAPI's own, which is what
    `tests/test_v1_query_isolation.py` pins (PRD-015 Risk 4). Keyed on
    Starlette's `HTTPException`, the key FastAPI's default uses, so routing's
    exceptions are covered too.
    """
    app.add_exception_handler(StarletteHTTPException, _http_exception)
    app.add_exception_handler(RequestValidationError, _validation_exception)
