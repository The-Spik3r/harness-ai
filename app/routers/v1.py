"""The OpenAI-compatible ingress (PRD-015 Sections 6.1, 6.4, 7.2, 7.4).

`POST /v1/chat/completions` authenticates exactly as `/query` does, turns the
body into pipeline arguments with `v1_translate`, and runs `run_conversation`
on the dedicated pipeline executor. The call site names the profile and the
door -- the literals `profile="code"` and `ingress="v1"` -- never a request
field (PRD-011 Section 6.6, PRD-013 Section 6.9).

`call_openrouter` is imported by name into this module so tests replace
`app.routers.v1.call_openrouter`, the binding rule `app/routers/query.py`
follows.

This story (STORY-009) ships the non-streaming success path only. STORY-010
maps verdicts and the 401/422 handlers, STORY-011 the pipeline's exceptions,
STORY-012 `/v1/models`, STORY-013 the buffered stream.
"""

import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse

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
    V1RequestError,
    translate_device,
    translate_request,
    translate_result,
)

router = APIRouter()


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
) -> JSONResponse:
    body = ErrorResponse(error=ErrorDetail(message=message, type=type_, param=param, code=code))
    return JSONResponse(body.model_dump(mode="json"), status_code=status_code, headers=headers)


def _placeholder(message: str) -> JSONResponse:
    # STORY-010/013 replace this placeholder. `x-should-retry: false` because
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
        # STORY-010 replaces this placeholder with the verdict's error object.
        # The pipeline has already written the row.
        return _placeholder("this outcome is not translated yet")

    # A success means step 7 ran, so the wrapper holds its result.
    assert upstream.result is not None
    completion = translate_result(result, upstream.result, int(time.time()))
    return JSONResponse(
        completion.model_dump(mode="json"),
        headers={"X-Harness-Audit-Id": str(result.audit_id)},
    )
