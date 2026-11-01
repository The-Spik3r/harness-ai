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
from app.middleware.auth import require_permission
from app.models.schemas import QuerySuccessResponse
from app.models.v1_schemas import (
    ChatCompletion,
    ChatCompletionRequest,
    ErrorDetail,
    ErrorResponse,
    ModelEntry,
    ModelList,
)
from app.services import v1_sse
from app.services.authz import PERMISSION_QUERY_SUBMIT
from app.services.duplicate_checker import DuplicateCheckError
from app.services.identity import Identity
from app.services.openrouter_client import OpenRouterError, OpenRouterResult, call_openrouter
from app.services.pii_redactor import PiiRedactorError
from app.services.pipeline_executor import run_in_pipeline
from app.services.query_pipeline import run_conversation
from app.services.usage_limits import UsageLimitError
from app.services.v1_translate import (
    BREAK_GLASS_NOT_PERMITTED,
    DEVICE_HEADER,
    INTERNAL_ERROR,
    INVALID_API_KEY,
    INVALID_REQUEST,
    MODEL_NOT_FOUND,
    PERMISSION_DENIED,
    REDACTION_FAILED,
    UPSTREAM_ERROR,
    UPSTREAM_UNAVAILABLE,
    V1Error,
    V1RequestError,
    translate_device,
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
# one today. The deliberate 5xx are the pipeline faults, which
# `chat_completions` maps itself (`_PIPELINE_FAULTS`).
_HTTP_ERRORS: Dict[int, Tuple[str, str]] = {
    401: ("authentication_error", INVALID_API_KEY),
    403: ("permission_error", PERMISSION_DENIED),
    404: ("invalid_request_error", "not_found"),
    405: ("invalid_request_error", "method_not_allowed"),
}
_OTHER_CLIENT_ERROR = ("invalid_request_error", INVALID_REQUEST)
_SERVER_ERROR = ("api_error", INTERNAL_ERROR)

# What `run_conversation` raises (PRD-015 Section 7.5): `/query`'s chain in
# app/routers/query.py minus `ChatSessionError`, which needs a session and
# `/v1` passes none. Anything else is a bug and stays Starlette's 500.
_PIPELINE_FAULTS = (OpenRouterError, DuplicateCheckError, UsageLimitError, PiiRedactorError)


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
    return _error(
        error.status_code, error.type, error.code, error.message, error.param,
        headers=None if error.retryable else {"x-should-retry": "false"},
        harness=error.harness,
    )


def _fault_code(exc: Exception) -> str:
    """A `_PIPELINE_FAULTS` exception as its Section 7.5 code (D7).

    An upstream fault is retryable exactly when the client says so
    (`_classify_http_error`). A storage fault is transient by nature. A
    redaction failure repeats on the same text. A post-commit fault on a
    stream is the same code, sent as an SSE `error` event (Section 7.6).
    """
    if isinstance(exc, OpenRouterError):
        return UPSTREAM_UNAVAILABLE if exc.retryable else UPSTREAM_ERROR
    if isinstance(exc, (DuplicateCheckError, UsageLimitError)):
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
        return translate_fault(code, str(exc))

    if not isinstance(result, QuerySuccessResponse):
        # A verdict: 400 or 403, never 429 or 5xx (D2, T7). The pipeline has
        # already written the row.
        return translate_verdict(result)

    # A success means step 7 ran, so the wrapper holds its result.
    assert upstream.result is not None
    return translate_result(result, upstream.result, int(time.time()))


def _json_response(pipeline: asyncio.Future, upstream: _Upstream, identity: Identity) -> Any:
    outcome = _outcome(pipeline, upstream, identity)
    if isinstance(outcome, V1Error):
        return _from_v1_error(outcome)
    return JSONResponse(
        outcome.model_dump(mode="json"),
        headers={"X-Harness-Audit-Id": str(outcome.harness.audit_id)},
    )


def _sse_events(
    pipeline: asyncio.Future, upstream: _Upstream, identity: Identity, include_usage: bool
) -> List[str]:
    """A finished pipeline as the events after commit (Section 7.6).

    The `200` is already sent, so there is no status left to fall back on:
    an exception outside `_PIPELINE_FAULTS` (a bug, which the JSON path
    leaves to Starlette's 500) is logged and sent as `internal_error`, so the
    stream ends with an event rather than a torn body.
    """
    try:
        outcome = _outcome(pipeline, upstream, identity)
    except Exception:
        logger.exception(
            "v1 stream failed after commit: user_id=%s code=%s", identity.user_id, INTERNAL_ERROR
        )
        outcome = translate_fault(INTERNAL_ERROR, HTTPStatus.INTERNAL_SERVER_ERROR.phrase)
    if isinstance(outcome, ChatCompletion):
        return v1_sse.completion_events(outcome, include_usage)
    if outcome.harness is not None:
        # Only a verdict carries a pipeline response, and every verdict is
        # decided before step 7 (Risk 5). Sent as the error event regardless.
        logger.warning(
            "v1 verdict after stream commit: user_id=%s code=%s", identity.user_id, outcome.code
        )
    return [v1_sse.error_event(
        _error_body(outcome.type, outcome.code, outcome.message, outcome.param, outcome.harness)
    )]


@router.post("/v1/chat/completions")
async def chat_completions(
    body: ChatCompletionRequest,
    x_harness_device: Optional[str] = Header(default=None, alias=DEVICE_HEADER),
    identity: Identity = Depends(require_permission(PERMISSION_QUERY_SUBMIT)),
) -> Any:
    # Both refusals come before the pipeline, so neither writes a row (T9).
    try:
        device = translate_device(x_harness_device)
        call = translate_request(body)
    except V1RequestError as exc:
        # T9: who and which rule, never the message, param value or body.
        logger.info("v1 request refused: user_id=%s code=%s", identity.user_id, exc.code)
        return _error(400, "invalid_request_error", exc.code, exc.message, exc.param)

    upstream = _Upstream(asyncio.get_running_loop())
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
    ))
    # Whatever happens to this request, the pipeline finishes and its outcome
    # is retrieved.
    v1_sse.detach(pipeline)

    if call.stream:
        await v1_sse.wait_for_commit(pipeline, upstream.started)
    else:
        await asyncio.wait({pipeline})

    # The commit rule (Section 6.4, D8): until the upstream is called, the
    # outcome is a verdict or a pre-upstream fault and keeps its real status.
    # Read from the wrapper's flag, not from which wait finished first.
    if not (call.stream and upstream.called):
        return _json_response(pipeline, upstream, identity)

    # No X-Harness-Audit-Id: the row does not exist yet. Every chunk's id
    # carries it (Section 7.6).
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
    if isinstance(exc.detail, str):
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
