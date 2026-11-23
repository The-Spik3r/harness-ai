"""Northbound `POST /mcp`: the harness as an MCP server (PRD-023 Sections 6.3, 7 F1, 9.1, 9.2).

A hand-written, stateless Streamable HTTP endpoint. It does not use the SDK's
server classes (T17: only `app/services/mcp_upstream.py` imports `mcp`), and
this module never calls `mcp_upstream`. Every request is one JSON-RPC object in,
one plain `application/json` response out: no SSE, no `Mcp-Session-Id` (an
inbound one is ignored), and no state between requests, so `tools/call` with no
prior `initialize` reaches its handler.

The gate (M0) runs in a fixed order and stops at the first refusal, before the
body is parsed and before any row or upstream call: credential (401 with
`WWW-Authenticate: Bearer realm="harness"`), break-glass (403), `mcp:connect`
(403), `Origin` (403), body size (413), media type (415). Then the strict JSON
parse (M1) and the JSON-RPC checks (M2). `initialize`, `ping` and notifications
are answered here; `tools/*` and `prompts/*` go through the `_HANDLERS` table,
whose bodies STORY-012 (`tools/list`), STORY-013 (`tools/call`) and STORY-015
(`prompts/*`) replace.

Handler table (each is `async def(identity, params, request_id) -> dict` and may
raise `JsonRpcError`; `params` is always a dict, `{}` when absent):

    tools/list     -> the visible catalogue          (STORY-012, `mcp_gateway`)
    tools/call     -> JsonRpcError(-32601)           (STORY-013 replaces)
    prompts/list   -> {"prompts": []}                (STORY-015 replaces)
    prompts/get    -> JsonRpcError(-32601)           (STORY-015 replaces)

JSON-RPC errors are HTTP 200, except the modern-era refusal (400). The router
is mounted only when `MCP_ENABLED` is true (`app/main.py`), so off means 404.
"""

import hashlib
import logging
from typing import Any, Awaitable, Callable, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import _normalize_mcp_origin, settings
from app.middleware.auth import require_identity
from app.models import mcp_schemas as schemas
from app.services import mcp_config, mcp_gateway, strict_json
from app.services.authz import PERMISSION_MCP_CONNECT, PermissionDenied, authorize
from app.services.identity import Identity

logger = logging.getLogger(__name__)

router = APIRouter()

# Northbound handshakes the endpoint speaks (PRD-023 D17). The newest is the
# fallback when a client asks for a version not listed.
SUPPORTED_PROTOCOL_VERSIONS = ("2025-03-26", "2025-06-18", "2025-11-25")

# The 2026-era stateless handshake is not supported (PRD-023 D17): a request
# carrying this `_meta` key, or `server/discover`, is refused with HTTP 400.
_MODERN_META_KEY = "io.modelcontextprotocol/protocolVersion"
_MODERN_DISCOVER_METHOD = "server/discover"

_WWW_AUTHENTICATE = 'Bearer realm="harness"'
_JSON_MEDIA_TYPE = "application/json"

_bearer_scheme = HTTPBearer(auto_error=False)


class JsonRpcError(Exception):
    """A handler's JSON-RPC error. The dispatcher turns it into an HTTP 200 body."""

    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _mcp_identity(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> Identity:
    """`require_identity`, with the `WWW-Authenticate` header a 401 here must carry.

    `Depends(require_identity)` would answer 401 with no header; the MCP
    authorization spec has the client read it to learn the scheme. Any other
    status (the 503 storage refusal) passes through unchanged."""
    try:
        return require_identity(credentials)
    except HTTPException as exc:
        if exc.status_code == 401:
            raise HTTPException(
                status_code=401, detail=exc.detail, headers={"WWW-Authenticate": _WWW_AUTHENTICATE}
            ) from exc
        raise


def _refuse(identity: Identity, status: int, rule: str, detail: str) -> HTTPException:
    """One M0 refusal. Logs the user and the rule, never the token, body or Origin."""
    logger.info("mcp request refused: user_id=%s rule=%s", identity.user_id, rule)
    return HTTPException(status_code=status, detail=detail)


def _check_origin(identity: Identity, origin: Optional[str]) -> None:
    """403 for an `Origin` that is present and not in `MCP_ALLOWED_ORIGINS` (M0d).

    Absent is allowed: a non-browser client sends none. The value is normalized
    exactly as the setting's entries are, so `https://a.com:443` matches
    `https://a.com`; `null` or junk does not normalize and is refused."""
    if origin is None:
        return
    try:
        normalized = _normalize_mcp_origin(origin.strip())
    except ValueError:
        raise _refuse(identity, 403, "origin_not_allowed", "Origin not allowed")
    if normalized not in settings.mcp_allowed_origins:
        raise _refuse(identity, 403, "origin_not_allowed", "Origin not allowed")


async def _read_bounded_body(request: Request, identity: Identity) -> bytes:
    """The request body, refused with 413 above `MCP_MAX_REQUEST_BYTES` (M0e).

    `Content-Length` is checked first (a non-integer value counts as absent),
    but the bytes actually read are the real guard: a lying or absent length
    (chunked) cannot get past the loop."""
    limit = settings.MCP_MAX_REQUEST_BYTES
    declared = request.headers.get("content-length")
    if declared is not None:
        try:
            too_large = int(declared) > limit
        except ValueError:
            too_large = False
        if too_large:
            raise _refuse(identity, 413, "body_too_large", "Request body too large")
    received = bytearray()
    async for chunk in request.stream():
        received.extend(chunk)
        if len(received) > limit:
            raise _refuse(identity, 413, "body_too_large", "Request body too large")
    return bytes(received)


def _rpc_result(request_id: Any, result: Dict[str, Any]) -> JSONResponse:
    body = schemas.JsonRpcResult(id=request_id, result=result)
    return JSONResponse(body.model_dump(mode="json"))


def _rpc_error(request_id: Any, code: int, message: str, status: int = 200) -> JSONResponse:
    body = schemas.JsonRpcErrorResponse(
        id=request_id, error=schemas.JsonRpcErrorBody(code=code, message=message)
    )
    return JSONResponse(body.model_dump(mode="json"), status_code=status)


def _valid_id(value: Any) -> bool:
    """A JSON-RPC id here is a string or an integer; bool and null are not (M2)."""
    return isinstance(value, (str, int)) and not isinstance(value, bool)


def _initialize_result(params: Dict[str, Any], app_version: str) -> Dict[str, Any]:
    requested = params.get("protocolVersion")
    version = (
        requested
        if isinstance(requested, str) and requested in SUPPORTED_PROTOCOL_VERSIONS
        else SUPPORTED_PROTOCOL_VERSIONS[-1]
    )
    result = schemas.InitializeResult(
        protocolVersion=version,
        capabilities={"tools": {"listChanged": False}, "prompts": {"listChanged": False}},
        serverInfo=schemas.ServerInfo(name="harness", version=app_version),
    )
    return result.model_dump(mode="json")


async def handle_tools_list(identity: Identity, params: Dict[str, Any], request_id: Any) -> Dict[str, Any]:
    """The visible, prefixed, inspected catalogue (PRD-023 F5, D6, D7, D12, T4).

    One page, no cursor (`params` is ignored). Writes no row (O4): one INFO line
    carries the user, the servers, the count, the config digest and a hash per
    description, never description text."""
    catalogue = await mcp_gateway.visible_catalogue(identity)
    hashes = ",".join(
        f"{t['name']}=sha256:{hashlib.sha256(t['description'].encode('utf-8')).hexdigest()}"
        for t in catalogue.tools
    )
    logger.info(
        "mcp tools/list: user=%s servers=%s tools=%d digest=%s hashes=%s",
        identity.user_id, ",".join(sorted(catalogue.callable)), len(catalogue.tools),
        mcp_config.mcp_config_digest(), hashes,
    )
    return {"tools": list(catalogue.tools)}


async def handle_tools_call(identity: Identity, params: Dict[str, Any], request_id: Any) -> Dict[str, Any]:
    """Placeholder: STORY-013 owns the call path (decision row, then forward)."""
    raise JsonRpcError(schemas.METHOD_NOT_FOUND, "Method not found: tools/call")


async def handle_prompts_list(identity: Identity, params: Dict[str, Any], request_id: Any) -> Dict[str, Any]:
    """Placeholder: STORY-015 returns the skill prompts."""
    return {"prompts": []}


async def handle_prompts_get(identity: Identity, params: Dict[str, Any], request_id: Any) -> Dict[str, Any]:
    """Placeholder: STORY-015 renders one skill prompt."""
    raise JsonRpcError(schemas.METHOD_NOT_FOUND, "Method not found: prompts/get")


Handler = Callable[[Identity, Dict[str, Any], Any], Awaitable[Dict[str, Any]]]

# Looked up by method name at call time through this dict, so a later story
# (or a test) replaces a body by name without touching the dispatcher.
_HANDLERS: Dict[str, Handler] = {
    "tools/list": handle_tools_list,
    "tools/call": handle_tools_call,
    "prompts/list": handle_prompts_list,
    "prompts/get": handle_prompts_get,
}


@router.post("/mcp")
async def mcp_endpoint(request: Request, identity: Identity = Depends(_mcp_identity)) -> Response:
    # M0: the gate, in order. Unknown query parameters are ignored.
    if identity.break_glass:
        raise _refuse(
            identity, 403, "break_glass",
            "Break-glass credential not permitted on this ingress: ingress:break_glass",
        )
    try:
        authorize(identity, PERMISSION_MCP_CONNECT)
    except PermissionDenied:
        raise _refuse(
            identity, 403, "permission_denied", f"Permission denied: {PERMISSION_MCP_CONNECT}"
        )
    _check_origin(identity, request.headers.get("origin"))
    raw = await _read_bounded_body(request, identity)
    media_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if media_type != _JSON_MEDIA_TYPE:
        raise _refuse(
            identity, 415, "unsupported_media_type", "Content-Type must be application/json"
        )

    # M1: one strict parse. Bad UTF-8, bad JSON and a repeated key are all -32700.
    try:
        message = strict_json.loads(raw.decode("utf-8"))
    except (ValueError, RecursionError):
        return _rpc_error(None, schemas.PARSE_ERROR, "Parse error")

    # M2: the JSON-RPC envelope. The id is echoed only when it is a valid type.
    if not isinstance(message, dict):
        return _rpc_error(None, schemas.INVALID_REQUEST, "Invalid Request")
    is_notification = "id" not in message
    request_id = None if is_notification else message["id"]
    echo_id = request_id if _valid_id(request_id) else None
    if (
        message.get("jsonrpc") != schemas.JSONRPC_VERSION
        or (not is_notification and not _valid_id(request_id))
        or not isinstance(message.get("method"), str)
    ):
        return _rpc_error(echo_id, schemas.INVALID_REQUEST, "Invalid Request")
    method: str = message["method"]
    params = message["params"] if "params" in message else {}

    # D17: the 2026-era stateless handshake is refused, not translated.
    meta = params.get("_meta") if isinstance(params, dict) else None
    if method == _MODERN_DISCOVER_METHOD or (
        method != "initialize" and isinstance(meta, dict) and _MODERN_META_KEY in meta
    ):
        return _rpc_error(
            echo_id, schemas.INVALID_REQUEST,
            "Unsupported protocol version: this server speaks "
            + ", ".join(SUPPORTED_PROTOCOL_VERSIONS),
            status=400,
        )

    if is_notification:
        return Response(status_code=202)

    if method == "ping":
        return _rpc_result(request_id, {})
    if method != "initialize" and method not in _HANDLERS:
        return _rpc_error(request_id, schemas.METHOD_NOT_FOUND, f"Method not found: {method}")
    if not isinstance(params, dict):
        return _rpc_error(request_id, schemas.INVALID_PARAMS, "Invalid params: expected an object")

    if method == "initialize":
        return _rpc_result(request_id, _initialize_result(params, request.app.version))
    try:
        result = await _HANDLERS[method](identity, params, request_id)
    except JsonRpcError as exc:
        return _rpc_error(request_id, exc.code, exc.message)
    except Exception:
        # Nothing from the request goes into the message or the log line.
        logger.exception("mcp handler failed: method=%s", method)
        return _rpc_error(request_id, schemas.INTERNAL_ERROR, "internal error")
    return _rpc_result(request_id, result)
