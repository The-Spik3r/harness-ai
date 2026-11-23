---
story: STORY-012
prd: PRD-023
slug: tools-list-visibility
title: "`tools/list`: visibility by held skills and catalogue injection inspection"
type: NEW_CAPABILITY
complexity: medium
epic_branch: epic/PRD-023-mcp-and-skills
created: 2026-11-22
---

# Plan: `tools/list` visibility and catalogue inspection

## Summary

Create `app/services/mcp_gateway.py` (no `mcp` import, T17) with `async visible_catalogue(identity) -> Catalogue`. It starts from `mcp_config.visible_tools(identity)`, fetches each server's cached upstream list concurrently, keeps held-and-listed tools, injection-inspects them, and returns the northbound tool dicts plus the `callable` map that STORY-013 M5 reuses. `handle_tools_list` in `app/routers/mcp.py` (the STORY-011 seam, `:168`) becomes a thin caller that adds the T4 audit `INFO` line. No DB row (O4).

- Story: `.agents/stories/PRD-023-mcp-and-skills/STORY-012-tools-list-visibility.md`
- PRD sections: 6.5, F5, 9.2 T3/T4, D6, D7, D12, O4, O6
- Systems: `app/services/mcp_gateway.py` (new), `app/routers/mcp.py` (handler body only)

## Design Decisions (orchestrator points are binding; resolutions added)

1. **API.** `@dataclass(frozen=True) class Catalogue: tools: tuple[dict, ...]; callable: Mapping[str, frozenset[str]]` (wrap in `MappingProxyType`, as `mcp_config.visible_tools` does, `app/services/mcp_config.py:205-217`). `callable` = server -> bare names actually emitted (held AND listed AND not withheld); a server with none is absent. `tools` sorted by emitted name, so the order is deterministic whatever the upstream or config order. STORY-013 tests `bare in catalogue.callable.get(server, ())`, so a withheld or unlisted tool is not callable (story note: calling `poisoned` gets -32602).
2. **Fetch.** `await asyncio.gather(*(mcp_upstream.list_tools(sid, identity.user_id) for sid in sorted(visible)), return_exceptions=True)`. An `Exception` result (`McpUpstreamError`, `asyncio.TimeoutError`, anything else) -> that server contributes nothing and one `WARNING` `"mcp tools/list: server=%s failed (%s)"` with `type(exc).__name__` only, never `str(exc)` (T16). Re-raise `asyncio.CancelledError` (a `BaseException`). No second cache: `mcp_upstream.list_tools` already caches per server (`app/services/mcp_upstream.py:452-478`).
3. **Inspection (D12, T3, O6).** D12 names one list, `injection`; it is used for the top-level `description`, for every string value of a `description` key anywhere inside `inputSchema` (recursive walk of dicts/lists, depth-bounded ~64), and for `title`. Build `pattern_config.Profile(name="mcp-catalogue", lists=(injection,), roles={"tool": "block"})` and call `pattern_detector.inspect(messages, profile, max_scan_characters=settings.PATTERN_MAX_SCAN_CHARACTERS)` (`app/services/pattern_detector.py:324`; it reads only `.role` / `.content`, so pass `types.SimpleNamespace(role="tool", content=text)` per text; same structural seam as `:266-290`; production call at `app/services/query_pipeline.py:920-921`). One `inspect` call per tool. List source: `pattern_config.get_policy().lists.get("injection")`, falling back to `pattern_config.BUILT_IN_POLICY.lists["injection"]` if a deployment file lacks it. A `block` hit, any `flags`, or any `truncated` index (text past the ceiling is unscanned: fail closed) withholds the tool. `WARNING` `"mcp tools/list: withheld server=%s tool=%s lists=%s"` with matched `list_name`s joined by `,`; never description text, pattern or phrase. The "lists D12 names" for the top-level description is this same single `injection` list; say so in the module docstring.
4. **Unlisted skill tool.** Held bare name absent from the upstream list: not emitted, `INFO` once per `(server, tool)` per cache period via module dict `_unlisted_logged: dict[tuple, float]` (expiry), clock `_now = time.monotonic` as a module attribute (tests inject it, like `mcp_upstream._now`, `tests/test_mcp_upstream.py:55-61`), TTL `settings.MCP_TOOLS_CACHE_SECONDS`; `0` logs every time. Prune expired keys each call to stay bounded. A failed server logs no per-tool INFO.
5. **Non-object schema.** `inputSchema.get("type") != "object"` (missing counts): emit unchanged, `INFO` (server, tool), same once-per-period dict with a distinct key. Never repaired.
6. **Emitted shape.** `name` (`<server>__<tool>`), `description`, `inputSchema` always; `title`, `outputSchema`, `annotations` only when not None (`UpstreamTool` fields, `app/services/mcp_upstream.py:89-98`). `input_schema` passed through unmodified, so `x-mcp-header` inside it survives. One page, no `nextCursor`.
7. **`icons` / `_meta` DEVIATION (for the orchestrator).** `_tool_from_sdk` (`app/services/mcp_upstream.py:221-230`) drops `icons`, `_meta` and any other top-level field. The story note says `icons` pass through, but the STORY-002 finding (`tests/corpora/mcp/SOURCES.md:439-448`) fixes the safe default: "forward `inputSchema` verbatim and drop `icons` and `_meta`, since no client above reads them" (icons are large `data:` URIs). **Plan: no change to `UpstreamTool` / `_tool_from_sdk`; icons and `_meta` are dropped.** If the orchestrator wants them, the smallest change is `extra: dict = field(default_factory=dict)` on `UpstreamTool`, filled in `_tool_from_sdk` with the unknown top-level keys of `data`, merged after the known keys by the gateway. Not planned.
8. **Audit (O4, T4).** The gateway writes nothing. `handle_tools_list` logs one `INFO`: `"mcp tools/list: user=%s servers=%s tools=%d digest=%s hashes=%s"`: `identity.user_id`, sorted server ids that emitted tools, `len(tools)`, `mcp_config.mcp_config_digest()`, and `name=sha256:<hexdigest of description.encode("utf-8")>` per emitted tool. No `action_audit.record` / `database.*` call; no description text.
9. **Router.** Keep `handle_tools_list` a module-level `async def` with the same signature: `_HANDLERS` binds it at import (`app/routers/mcp.py:192-197`). `params` (a `cursor`) is ignored. M0-M2 code untouched. The router imports `mcp_gateway` and `mcp_config` only, never `mcp_upstream` (guard `tests/test_mcp_endpoint.py:468-481`; the import-graph guard `tests/test_mcp_upstream_import_graph.py` only bans the SDK outside `mcp_upstream.py`). Update the router docstring's table row for `tools/list`.
10. **Off means off (D20).** The router is not mounted with `MCP_ENABLED=false`. With the empty config `visible_tools` is `{}`, so `tools/list` stays `{"tools": []}` and `test_seam_placeholders` (`tests/test_mcp_endpoint.py:413`) passes unmodified.

## Skills In Use

None (`.agents/skills/` holds only `frontend-design`; no UI).

## Patterns to Follow

| Category | Source | What to mirror |
|----------|--------|----------------|
| Naming/docstrings | `app/services/mcp_config.py:195-217` | PRD-citing docstrings, `MappingProxyType`, frozen dataclasses |
| Errors/logging | `app/services/mcp_upstream.py:445-478` | server id in messages, no exception text |
| Inspection seam | `app/services/query_pipeline.py:920-921` | `inspect(messages, profile, max_scan_characters=...)` |
| Router seam | `app/routers/mcp.py:168-196` | handler signature, `_HANDLERS` lookup at call time |
| Stub tests | `tests/test_mcp_upstream.py:36-70` | `_go` bounded `asyncio.run`, `_cfg` putting an `McpConfig` in force, autouse `_fresh` |
| HTTP tests | `tests/test_mcp_endpoint.py:34-80` | monkeypatched `app.middleware.auth.resolve`, `_rpc`/`_post`, app with only the router |

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/mcp_gateway.py` | CREATE | `Catalogue`, `visible_catalogue`, inspection helpers, unlisted-INFO dict |
| `app/routers/mcp.py` | UPDATE | `handle_tools_list` body, docstring row, imports |
| `tests/test_mcp_gateway.py` | CREATE | unit, stub and HTTP tests |

## Tasks

### Task 1: `app/services/mcp_gateway.py`
- **Implement**: decisions 1-6. Helpers `_schema_descriptions(schema) -> list[str]`, `_withheld_by(server, tool) -> tuple[str, ...]` (matched list names, empty = clean), `_log_once(key, msg, *args)`. Settings read only for `MCP_TOOLS_CACHE_SECONDS` and `PATTERN_MAX_SCAN_CHARACTERS`. Module docstring cites 6.5, D6/D7/D12, O4, T3/T4, "no `mcp` import (T17)" and that STORY-013 reuses `callable`.
- **Validate**: `.venv/Scripts/python -c "from app.services import mcp_gateway"`

### Task 2: wire the router
- **File**: `app/routers/mcp.py`. Replace the placeholder body (`:168-170`): `catalogue = await mcp_gateway.visible_catalogue(identity)`; the T4 `INFO` (decision 8); `return {"tools": list(catalogue.tools)}`. Touch nothing else except imports and the docstring row.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_mcp_endpoint.py`

### Task 3: `tests/test_mcp_gateway.py`
Sync tests, one bounded `asyncio.run` each (copy `_go`, `_cfg`, `_fresh` from `tests/test_mcp_upstream.py`; `aclose_all()` in `finally`, `invalidate_tools_cache()` before and after, clear `mcp_gateway._unlisted_logged`). Put `McpConfig(servers=..., skills=(Skill(...),))` into `mcp_config._config`; for "role holds the skill" reuse the idiom of `tests/test_mcp_config.py` for `held_skills` (monkeypatch `authz.ROLE_PERMISSIONS`/`holds`). Cases:
- a. stub, skill `open-pull-request` with `create_branch`, `push_files`, `create_pull_request`: exactly those three prefixed names, sorted, description/inputSchema equal to the stub's, optional keys only when present upstream, no `nextCursor`; `callable == {"github": frozenset({...})}`. Plain `user` -> no tools; `RBAC_ENABLED=False` + built-in matrix -> none.
- b. `poisoned` in a held skill: omitted, absent from `callable`; `caplog` WARNING holds server id, tool name, `injection` and not `INJECTION_PHRASE` (`scripts/stub_mcp_server.py:58`); other tools still listed.
- c. unit cases through a monkeypatched async `mcp_upstream.list_tools`: phrase only in nested `inputSchema.properties.x.description`, only in `title`, only in an `items`/`oneOf` description -> withheld; clean tool kept; text over `PATTERN_MAX_SCAN_CHARACTERS` -> withheld; phrase in a property name or `default` is not inspected (documents scope).
- d. two servers, one stopped (`stub.stop()`, cache invalidated) or a fake raising `McpUpstreamError` / `asyncio.TimeoutError` / `RuntimeError("SECRET-MSG")`: the other server's tools returned, one WARNING with the class name and without `SECRET-MSG`, call succeeds. Unlisted skill tool: omitted, one INFO; repeat inside the period logs none; advancing injected `mcp_gateway._now` past the TTL logs again; TTL `0` logs every call.
- e. `inputSchema` `{"type": "string"}` and `{}`: emitted unchanged, INFO.
- f. reversed skill/tool order in config -> identical `tools`.
- g. HTTP: FastAPI app with only the router, `resolve` monkeypatched; `tools/list` result names as in a; `action_audit.record` and `database.insert_action_decisions` monkeypatched to raise (as `no_side_effects`, `tests/test_mcp_endpoint.py:59-67`) so a row would fail the test; `caplog` INFO contains user id, server id, count, `mcp_config_digest()`, `sha256` of an emitted description, and no description text.
- h. AST check: `mcp_gateway` has no `mcp` / `mcp.*` import (style of `tests/test_mcp_endpoint.py:468`).
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_mcp_gateway.py`

## End-to-End Tests

- [ ] Case g: real router + real stub subprocess + real `mcp_upstream`; `tools/list` over HTTP returns the 3 tools for a skill-holding role and `[]` for `user`.
- [ ] Case b over HTTP: `poisoned` is never in `result.tools`.

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider -m "not db" tests/test_mcp_gateway.py tests/test_mcp_endpoint.py tests/test_mcp_upstream_import_graph.py tests/test_untouched_app.py
```
No `-m db` locally (Docker down). No `database.py` change (no census edits), no new route (Caddyfile unchanged), no renamed or removed test.

## Acceptance Criteria -> Tasks -> Tests

| AC | Task(s) | Test that proves it |
|----|---------|---------------------|
| AC1 held skill -> 3 tools; user `[]`; RBAC off `[]` | 1, 2 | `test_mcp_gateway.py` case a, g |
| AC2 poisoned withheld, WARNING without text; schema/title inspected, injection only | 1 | cases b, c |
| AC3 down/timeout tolerated; unlisted INFO once per period | 1 | case d |
| AC4 no `action_decisions` row; INFO with user, servers, count, digest, hashes | 2 | case g |

## Open risks

- A non-object schema is passed through per the story; OpenCode drops it client-side (INFO only).
- Failing closed on scan truncation and on a missing `injection` list are additions of mine (decision 3); both only withhold more.
- `callable` is recomputed per call from the cached list, so a T4 rug pull appears at the next cache refresh in both `tools/list` and STORY-013.
