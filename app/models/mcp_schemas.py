"""The northbound `/mcp` wire shapes (PRD-023 Sections 7 F1, 9.1).

What the harness writes back on the Streamable HTTP endpoint: the JSON-RPC
result and error envelopes and the `initialize` result. Request validation is
hand-written in the router, on purpose: a pydantic request model would surface
a type fault as a 422, not as the `-32600` body JSON-RPC requires.

Pure on purpose: no I/O, no settings, no `app` import, and no `mcp` import
(T17: only `app/services/mcp_upstream.py` imports the SDK). Serialize with
`model_dump(mode="json")`.
"""

from typing import Any, Dict, Optional, Union

from pydantic import BaseModel

JSONRPC_VERSION = "2.0"

# The JSON-RPC 2.0 reserved codes the endpoint uses.
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

RequestId = Union[str, int, None]


class ServerInfo(BaseModel):
    name: str
    version: str


class InitializeResult(BaseModel):
    protocolVersion: str
    capabilities: Dict[str, Any]
    serverInfo: ServerInfo


class JsonRpcErrorBody(BaseModel):
    code: int
    message: str


class JsonRpcErrorResponse(BaseModel):
    jsonrpc: str = JSONRPC_VERSION
    id: RequestId = None
    error: JsonRpcErrorBody


class JsonRpcResult(BaseModel):
    jsonrpc: str = JSONRPC_VERSION
    id: RequestId = None
    result: Dict[str, Any]
