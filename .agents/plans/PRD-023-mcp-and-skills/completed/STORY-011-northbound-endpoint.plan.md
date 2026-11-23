---
story: STORY-011
prd: PRD-023
slug: northbound-endpoint
title: "Northbound `POST /mcp`: auth, Origin, JSON-RPC parsing, `initialize` / `ping` / notifications"
type: NEW_CAPABILITY
complexity: medium
epic_branch: epic/PRD-023-mcp-and-skills
created: 2026-11-22
---

# Plan: Northbound `POST /mcp`

## Summary

A hand-written, stateless Streamable HTTP endpoint (no SDK server, T17). `app/routers/mcp.py` runs the fixed M0 gate, parses one JSON-RPC object with a duplicate-key-refusing loader, answers `initialize` / `ping` / notifications locally and sends `tools/*` / `prompts/*` to named async seams that later stories fill. Mounted only when `MCP_ENABLED`. It never calls `mcp_upstream`, writes no row and sets no `Mcp-Session-Id`.

- Story: `.agents/stories/PRD-023-mcp-and-skills/STORY-011-northbound-endpoint.md`
- PRD sections: 6.3 (M0-M3), 7 F1, 9.1, 9.2 (T7, T11), 10; D3, D17, D19
- Systems: `app/routers`, `app/models`, `app/services` (loader), `app/main.py`, `Caddyfile`, tests

## Design Decisions (binding, from the orchestrator)

1. **M0 order, short-circuiting, no row, no `mcp_upstream`**: (a) `require_identity` -> 401 with exactly `WWW-Authenticate: Bearer realm="harness"`; (b) `identity.break_glass` -> 403; (c) `authorize(identity, PERMISSION_MCP_CONNECT)` -> 403; (d) `Origin` present and not in `settings.mcp_allowed_origins` -> 403 (absent allowed); (e) body bounded by `settings.MCP_MAX_REQUEST_BYTES`: refuse on `Content-Length` above the limit AND on bytes actually read above it -> 413; (f) media type (before `;`, case-insensitive, stripped) != `application/json` -> 415. Unknown query params ignored.
2. **JSON-RPC (M1/M2)**: one parse with the strict loader. Not JSON / bad UTF-8 / duplicate key -> `-32700`, `id: null`. Array, non-object, `jsonrpc != "2.0"`, `id` not `str`/`int` (bool and null count as bad), `method` missing or non-string -> `-32600` (id echoed only when it is a valid type, else null). Unknown method -> `-32601`. JSON-RPC errors are HTTP 200 `application/json`, EXCEPT the modern-era refusal (`params._meta["io.modelcontextprotocol/protocolVersion"]` on a method other than `initialize`, or method `server/discover`) = HTTP 400 with a `-32600` body. No `id` key (any `notifications/*`) -> 202, empty body. Plain JSON responses, never SSE; never set `Mcp-Session-Id`; inbound `Mcp-Session-Id` (any case) ignored.
3. **`initialize`**: module constant `SUPPORTED_PROTOCOL_VERSIONS = ("2025-03-26", "2025-06-18", "2025-11-25")`; echo the client's `params.protocolVersion` if listed, else the newest (last); `capabilities: {tools: {listChanged: false}, prompts: {listChanged: false}}`; `serverInfo: {name: "harness", version: request.app.version}` (FastAPI's existing version; `app/main.py:41` passes none, so `"0.1.0"`; add no new constant); no `instructions`. `ping` -> `{}`. No session state: `tools/call` with no prior `initialize` reaches its seam.
4. **Seams** in `app/routers/mcp.py`: `_HANDLERS: Dict[str, Callable]` mapping `tools/list`, `tools/call`, `prompts/list`, `prompts/get` to `async def handle_tools_list(identity, params, request_id)` etc., returning a result dict or raising local `JsonRpcError(code, message)`. Placeholders: `tools/list` -> `{"tools": []}`, `prompts/list` -> `{"prompts": []}`, `tools/call` and `prompts/get` raise `JsonRpcError(-32601, ...)`. STORY-012/015 replace the bodies. `params` is passed as a dict (absent -> `{}`; non-object -> `-32602` raised by the dispatcher). The report must document this table.
5. **Mounting**: `if settings.MCP_ENABLED: app.include_router(mcp_router.router)` after the `V1_ENABLED` block (`app/main.py:51-53`). Disabled: `/mcp` and `/.well-known/oauth-*` are 404 (nothing mounted).

## Skills In Use

None (`skills: []`; `.agents/skills/` holds only `frontend-design`, not applicable).

## Patterns to Follow

| Category | Source | What to mirror |
|----------|--------|----------------|
| Auth | `app/middleware/auth.py:15-33` | `require_identity` raises `HTTPException(401)` with no header; 503 + Retry-After on storage outage. The router wraps it (Task 3) to add `WWW-Authenticate`; 503 passes through |
| Break-glass | `app/routers/v1.py:612-631` (`_refuse_break_glass`) | Test `identity.break_glass`; log at info with `user_id` only; no row. `/mcp` answers `HTTPException(403, "Break-glass credential not permitted on this ingress: ingress:break_glass")` (plain `detail`, not the `/v1` envelope) |
| RBAC | `app/services/authz.py:68,227`; `auth.py:36-43` | `PERMISSION_MCP_CONNECT`; `authorize()` raises `PermissionDenied`; map to 403 `Permission denied: mcp:connect`; open when `RBAC_ENABLED=false` |
| Origins | `app/config.py:1112-1116` (`mcp_allowed_origins`), `_normalize_mcp_origin` at `config.py:123-160` | Normalise the request `Origin` with the same function and compare; `ValueError` or `null` -> 403. Default ports are dropped, so `https://a.com:443` == `https://a.com` |
| Settings | `app/config.py:457-465` | `MCP_ENABLED`, `MCP_MAX_REQUEST_BYTES` (>= 1024) read per request |
| Strict loader | `app/services/strict_yaml.py:62-69` | Pure module, no `app` import. No JSON sibling exists, so add one |
| Mounting | `app/main.py:48-53` | Read once at import; off = no router |
| Router style | `app/routers/v1.py:1-24,100-110` | Docstring citing PRD sections; `logger = logging.getLogger(__name__)`; `router = APIRouter()` |
| Tests | `tests/test_v1_router.py:330-352`, `tests/test_caddyfile_routes.py` | Fresh-module load with the setting off; Caddy matcher census |

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/strict_json.py` | CREATE | `loads(text)` refusing duplicate keys (T7) |
| `app/models/mcp_schemas.py` | CREATE | Northbound pydantic shapes, no `mcp` import |
| `app/routers/mcp.py` | CREATE | M0-M2, dispatch table, seams |
| `app/main.py` | UPDATE | Import + conditional `include_router` |
| `Caddyfile` | UPDATE | `/mcp` exact token in `@backend_routes` (line 5) |
| `tests/test_caddyfile_routes.py` | UPDATE | `EXPECTED_MATCHER` += `"/mcp"` (PRD-023 comment); `STATIC_PATHS` += `/mcpx`, `/mcp/`; test that the router's path is matched |
| `tests/test_strict_json.py` | CREATE | Loader unit tests |
| `tests/test_mcp_endpoint.py` | CREATE | M0/M1/M2, initialize, seams, mounting; all `not db` |

## Tasks

### Task 1: strict JSON loader
- **File**: `app/services/strict_json.py` (CREATE)
- **Implement**: `loads(text: str) -> Any` = `json.loads(text, object_pairs_hook=_no_duplicates, parse_constant=_refuse)`. The hook raises `ValueError(f"duplicate key {key!r}")` at any depth; `parse_constant` refuses `NaN`/`Infinity`. Pure, no settings. Callers catch `ValueError` (`JSONDecodeError` is one) and `RecursionError` (deep nesting) -> `-32700`.
- **Mirror**: `app/services/strict_yaml.py:1-24` docstring style (cite PRD-023 T7).
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_strict_json.py`

### Task 2: schemas
- **File**: `app/models/mcp_schemas.py` (CREATE)
- **Implement**: pydantic models `ServerInfo`, `InitializeResult` (`protocolVersion`, `capabilities`, `serverInfo`), `JsonRpcErrorBody(code, message)`, `JsonRpcErrorResponse(jsonrpc, id, error)`, `JsonRpcResult(jsonrpc, id, result)`; constants `JSONRPC_VERSION`, `PARSE_ERROR=-32700`, `INVALID_REQUEST=-32600`, `METHOD_NOT_FOUND=-32601`, `INVALID_PARAMS=-32602`, `INTERNAL_ERROR=-32603`. Request validation stays hand-written in the router: a pydantic request model would surface type faults as 422, not a `-32600` body. No `mcp` import (`tests/test_mcp_upstream_import_graph.py` scans `app/`).
- **Mirror**: `app/models/v1_schemas.py` (naming, `model_dump(mode="json")`).

### Task 3: router
- **File**: `app/routers/mcp.py` (CREATE)
- **Implement**:
  - `@router.post("/mcp")` only. GET/DELETE get Starlette's automatic 405; verify its `Allow` is exactly `POST`. If it is not, register explicit GET/DELETE routes returning 405 with `Allow: POST`.
  - `_mcp_identity(credentials=Depends(HTTPBearer(auto_error=False)))` calls `require_identity(credentials)` directly (`auth.py`'s `_bearer_scheme` is private) and re-raises a 401 `HTTPException` with `headers={"WWW-Authenticate": 'Bearer realm="harness"'}`; other statuses pass through. Do not use `Depends(require_identity)`: its 401 has no header.
  - In the handler, in order: break-glass 403; `authorize` 403; Origin 403; `Content-Length` above the limit 413 (a non-integer value is treated as absent); bounded read with `async for chunk in request.stream()` accumulating and aborting with 413 above the limit; media type 415. Refusals are `HTTPException` with a plain `detail`; log only `user_id` and the rule, never the token, body or full Origin value.
  - Then M1/M2 per Design 2-4. Helpers `_rpc_error(id, code, message, status=200)` and `_rpc_result(id, result)` return `JSONResponse`; notifications return `Response(status_code=202)` with no body. Never read or write `Mcp-Session-Id`.
  - A non-`JsonRpcError` exception from a seam -> `-32603 "internal error"`, HTTP 200, `logger.exception`, nothing from the request in the message.
- **Mirror**: `app/routers/v1.py:612-631`, `app/middleware/auth.py:36-43`.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider -m "not db" tests/test_mcp_endpoint.py`

### Task 4: mount
- **File**: `app/main.py` (UPDATE). Add `from app.routers import mcp as mcp_router` beside line 12 and, after line 53, a comment citing PRD-023 D20/F1 plus `if settings.MCP_ENABLED: app.include_router(mcp_router.router)`. No error handlers.

### Task 5: Caddy
- `Caddyfile:5`: add `/mcp` after `/v1/*` (exact token; `/mcpx` stays static; nothing for `/.well-known`).
- `tests/test_caddyfile_routes.py`: `EXPECTED_MATCHER` gets `"/mcp"` with a comment (PRD-023 STORY-011, exact token). `test_every_harness_route_is_proxied_by_caddy` reads `app.routes`, which lacks `/mcp` while off, so add a test that imports the router and asserts each of its paths is matched by the tokens. `test_untouched_app.py` and `test_route_reservations.py` need no edit (dynamic census; `/mcp` is not Reflex-reserved). Run `grep -rn "backend_routes" . -l` to find any second Caddyfile copy (`deploy/`, `tests/test_lb_caddyfile.py`) and update it with its test.

### Task 6: tests (all `not db`)
- **Identities without a database**: `tests/test_v1_models.py:58-64` seeds a user row (DB test). For `/mcp` instead `monkeypatch.setattr("app.middleware.auth.resolve", fake)`: `fake` returns `Identity(user_id=..., role="user")` for one token, `role="auditor"` for another, `Identity(..., role="admin", break_glass=True)` for the admin token, else `None`. `require_identity` calls `resolve` through the module global (`auth.py:19`), so no storage is touched; `authorize()` uses the real built-in matrix (`user` has `mcp:connect`, `auditor` does not).
- **App under test**: `FastAPI()` + `include_router(mcp.router)`, since the root `app` has no `/mcp` while `MCP_ENABLED` is off. Plus a fresh-module test mirroring `tests/test_v1_router.py:333-352`: setting off -> `POST /mcp` 404, `/.well-known/oauth-protected-resource` and `/.well-known/oauth-authorization-server` 404, `/query` still 401; setting on -> `/mcp` in the routes and GET/DELETE 405 `Allow: POST`. No lifespan is entered.
- **No row / no upstream**: for the M0 tests monkeypatch `action_audit.record`, `database.insert_action_decisions` and the `mcp_upstream` entry points to raise; assert none was reached.
- **Cases**: every item of Design 1-4 and each Risk: 401 header exact; break-glass/auditor 403; `RBAC_ENABLED=false`; Origin (absent, unlisted, listed, `:443`, `null`); 413 by Content-Length and by streamed bytes; 415 and charset accepted; `?codemode=false`; `-32700` (nested duplicates, bad UTF-8, `id: null`); `-32600` variants (array, scalar, bad version, bool/null/object id, bad method); `-32601`; modern-era 400 (but `initialize` with `_meta` passes); version echo/newest; exact result shape; no session header; `ping`; 202 empty; seams reached via a patched `_HANDLERS`; placeholders.

## End-to-End Tests
- [ ] The fresh-module `MCP_ENABLED=true` `TestClient` flow: `initialize` -> `notifications/initialized` -> `tools/list` -> `{"tools": []}`, all HTTP 2xx, no session header.
- [ ] `chat_ui/` untouched: no UI check.

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider -m "not db" tests/test_strict_json.py tests/test_mcp_endpoint.py tests/test_caddyfile_routes.py tests/test_lb_caddyfile.py tests/test_route_reservations.py tests/test_untouched_app.py tests/test_mcp_upstream_import_graph.py tests/test_auth_dependencies.py tests/test_v1_router.py
```
Full suite: GitHub CI on push. DB-marked cases in those files run there.

## Acceptance Criteria -> Tasks -> Tests

| AC | Task(s) | Test |
|----|---------|------|
| AC1 off = 404, on = POST mounted, GET/DELETE 405 | 3, 4 | `test_mcp_endpoint.py::test_disabled_*`, `::test_get_delete_405_allow_post` |
| AC2 M0 statuses, no row/upstream | 3, 5 | `::test_m0_*` (401 header, break-glass, rbac, origin, 413, 415) |
| AC3 `-32700` / `-32600` / `-32601` | 1, 3 | `::test_parse_*`, `::test_invalid_request_*`, `::test_unknown_method`, `test_strict_json.py` |
| AC4 initialize / ping / notifications | 2, 3 | `::test_initialize_*`, `::test_ping`, `::test_notification_202` |
| AC5 handler seams | 3 | `::test_seams_*` |

## Risks
- A lying or absent `Content-Length` (chunked): the bounded stream read is the real guard; both are tested.
- `HTTPBearer(auto_error=False)` reads only the `Bearer` scheme; any other reads as no credential (401), as elsewhere.
- The Origin normaliser raises `ValueError` on junk: map to 403, never 500.
- Automatic 405 `Allow` may list more than `POST`: fallback in Task 3.
- `/mcp/` (trailing slash) redirects with 307 by default; accepted, not mounted separately.
