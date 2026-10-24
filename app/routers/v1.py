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
pipeline's exceptions, STORY-012 adds `/v1/models`, STORY-013 the buffered
stream.
"""

import logging
import time
from http import HTTPStatus
from typing import Any, Dict, Optional, Sequence, Tuple, Union

from fastapi import APIRouter, Depends, FastAPI, Header, Request
from fastapi.exception_handlers import (
    http_exception_handler,
    request_validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.middleware.auth import require_permission
from app.models.schemas import QuerySuccessResponse
from app.models.v1_schemas import ChatCompletionRequest, ErrorDetail, ErrorResponse
from app.services.authz import PERMISSION_QUERY_SUBMIT
from app.services.identity import Identity
from app.services.openrouter_client import OpenRouterResult, call_openrouter
from app.services.pipeline_executor import run_in_pipeline
from app.services.query_pipeline import run_conversation
from app.services.v1_translate import (
    DEVICE_HEADER,
    INVALID_API_KEY,
    INVALID_REQUEST,
    PERMISSION_DENIED,
    V1Error,
    V1RequestError,
    translate_device,
    translate_request,
    translate_result,
    translate_verdict,
)

logger = logging.getLogger(__name__)

router = APIRouter()

_V1_PREFIX = "/v1/"

# An `HTTPException` under `/v1/` as (type, code), by status (PRD-015 Section
# 7.5). 401 and 403 are `require_identity` / `require_permission`; 404 and 405
# are routing (an unknown path, a wrong method). Any other 4xx is
# `_OTHER_CLIENT_ERROR`, any 5xx `_SERVER_ERROR`: nothing under `/v1/` raises
# one today, and STORY-011 owns the deliberate 5xx mapping.
_HTTP_ERRORS: Dict[int, Tuple[str, str]] = {
    401: ("authentication_error", INVALID_API_KEY),
    403: ("permission_error", PERMISSION_DENIED),
    404: ("invalid_request_error", "not_found"),
    405: ("invalid_request_error", "method_not_allowed"),
}
_OTHER_CLIENT_ERROR = ("invalid_request_error", INVALID_REQUEST)
_SERVER_ERROR = ("api_error", "internal_error")


class _Upstream:
    """The `call_openrouter` the pipeline is handed, capturing its result.

    `QuerySuccessResponse` carries neither the finish reason nor the token
    split, and `/query`'s body must not change for them (STORY-001), so the
    router keeps the `OpenRouterResult` itself (PRD-015 Section 6.4).
    `call_openrouter` is looked up at call time, so a test's replacement
    applies. `kwargs` is forwarded as received: `params=` reaches the client
    only when the pipeline passed it, and the suite's stubs with signature
    (messages, model, api_key) keep working (PRD-010 STORY-005). STORY-013
    adds the start signal here.
    """

    def __init__(self) -> None:
        self.result: Optional[OpenRouterResult] = None

    def __call__(self, messages, model, api_key, **kwargs) -> OpenRouterResult:
        self.result = call_openrouter(messages, model=model, api_key=api_key, **kwargs)
        return self.result


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
    body = ErrorResponse(
        error=ErrorDetail(message=message, type=type_, param=param, code=code, harness=harness)
    )
    if status_code < 500:
        headers = {**(headers or {}), "x-should-retry": "false"}
    return JSONResponse(body.model_dump(mode="json"), status_code=status_code, headers=headers)


def _from_v1_error(error: V1Error) -> JSONResponse:
    return _error(
        error.status_code, error.type, error.code, error.message, error.param,
        harness=error.harness,
    )


def _placeholder(message: str) -> JSONResponse:
    # STORY-013 replaces this placeholder. `x-should-retry: false` because
    # the OpenAI SDKs retry a 5xx by default, and each retry would run the
    # pipeline again.
    return _error(
        501, "api_error", "not_implemented", message, headers={"x-should-retry": "false"}
    )


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

    if call.stream:
        # STORY-013 replaces this placeholder with the buffered stream.
        return _placeholder("streaming is not available yet")

    upstream = _Upstream()
    result = await run_in_pipeline(
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
        streamed=False,
        ignored_params=call.ignored_params,
    )

    if not isinstance(result, QuerySuccessResponse):
        # A verdict: 400 or 403, never 429 or 5xx (D2, T7). The pipeline has
        # already written the row.
        return _from_v1_error(translate_verdict(result))

    # A success means step 7 ran, so the wrapper holds its result.
    assert upstream.result is not None
    completion = translate_result(result, upstream.result, int(time.time()))
    return JSONResponse(
        completion.model_dump(mode="json"),
        headers={"X-Harness-Audit-Id": str(result.audit_id)},
    )


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
