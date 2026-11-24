---
story: STORY-011
prd: PRD-023
plan: .agents/plans/PRD-023-mcp-and-skills/completed/STORY-011-northbound-endpoint.plan.md
epic_branch: epic/PRD-023-mcp-and-skills
commit: 121ef12
status: COMPLETE
completed: 2026-11-22
---

# Implementation Report - STORY-011: Northbound `POST /mcp`

**Plan**: `.agents/plans/PRD-023-mcp-and-skills/completed/STORY-011-northbound-endpoint.plan.md`
**Epic Branch**: `epic/PRD-023-mcp-and-skills`
**Commit**: `121ef12`

## Summary

A hand-written, stateless Streamable HTTP endpoint (no SDK server, T17). `app/routers/mcp.py` runs the M0 gate in fixed order (401 with `WWW-Authenticate: Bearer realm="harness"`, break-glass 403, `mcp:connect` 403, Origin 403, 413, 415), parses with a duplicate-key-refusing loader, answers `initialize` / `ping` / notifications locally and routes `tools/*` / `prompts/*` through a `_HANDLERS` table. Mounted only when `MCP_ENABLED`. It never imports `mcp` or `mcp_upstream`, writes no row, sets no `Mcp-Session-Id`.

## Handler seam table (for STORY-012/013/015)

Each handler is `async def(identity, params, request_id) -> dict`, may raise `JsonRpcError(code, message)`; `params` is always a dict (`{}` when absent, a non-object is `-32602` before the handler). Replace by editing the function or `_HANDLERS[name]`.

| Method | Placeholder | Replaced by |
|--------|-------------|-------------|
| `tools/list` | `{"tools": []}` | STORY-012 |
| `tools/call` | `JsonRpcError(-32601)` | STORY-013 |
| `prompts/list` | `{"prompts": []}` | STORY-015 |
| `prompts/get` | `JsonRpcError(-32601)` | STORY-015 |

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Strict JSON loader | `app/services/strict_json.py` | done |
| 2 | Wire shapes | `app/models/mcp_schemas.py` | done |
| 3 | Router | `app/routers/mcp.py` | done |
| 4 | Conditional mount | `app/main.py` | done |
| 5 | Caddy token + census | `Caddyfile`, `tests/test_caddyfile_routes.py` | done |
| 6 | Tests | `tests/test_strict_json.py`, `tests/test_mcp_endpoint.py` | done |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| Targeted tests (`-m "not db"`: strict_json, mcp_endpoint, caddyfile_routes, lb_caddyfile, route_reservations, untouched_app, mcp_upstream_import_graph, auth_dependencies, v1_router, actions_view) | 165 passed, 1 skipped, 26 deselected |
| E2E | `test_enabled_mcp_flow_and_get_delete_405_allow_post` (initialize, notifications/initialized, tools/list on a fresh `MCP_ENABLED=true` app) passes |
| Full suite | GitHub CI on push (user decision) |

DB-marked tests (26 deselected) could not run: Docker is down.

## Files Changed

CREATE: `app/services/strict_json.py`, `app/models/mcp_schemas.py`, `app/routers/mcp.py`, `tests/test_strict_json.py`, `tests/test_mcp_endpoint.py`.
UPDATE: `app/main.py` (+6), `Caddyfile` (`/mcp` exact token), `tests/test_caddyfile_routes.py` (`EXPECTED_MATCHER`, `STATIC_PATHS`, router-path test).

## Deviations from Plan

None of substance. Automatic 405 for GET/DELETE already lists `Allow: POST` only (verified by test), so no explicit 405 routes. `tests/test_lb_caddyfile.py` and `deploy/` hold no second matcher copy. A modern-era `_meta` / `server/discover` refusal is checked before the notification branch, so it also applies to a notification carrying the key. `/mcp/` redirects (307), as planned.

## Acceptance Criteria

- [x] AC1 off = 404 (also `/.well-known/oauth-*`), on = POST mounted, GET/DELETE 405 `Allow: POST`: `test_disabled_mcp_is_not_mounted`, `test_enabled_mcp_flow_and_get_delete_405_allow_post`, `test_get_delete_405_allow_post`
- [x] AC2 M0 statuses, no row/upstream: `test_m0_*` (401 header, break-glass, missing permission, RBAC off, Origin, 413 by header and by stream, 415, ordering, no-log of token/Origin)
- [x] AC3 `-32700` / `-32600` / `-32601`: `test_parse_errors`, `test_invalid_request_variants`, `test_unknown_method`, `test_modern_era_*`, `tests/test_strict_json.py`
- [x] AC4 initialize / ping / notifications: `test_initialize_*`, `test_ping`, `test_notification_202_empty_body`
- [x] AC5 handler seams: `test_seam_*`
