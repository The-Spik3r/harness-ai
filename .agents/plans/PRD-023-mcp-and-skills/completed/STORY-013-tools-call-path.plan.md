---
story: STORY-013
prd: PRD-023
slug: tools-call-path
title: "`tools/call`: usage, visibility, evaluation, record before forward, forward, outcome"
type: NEW_CAPABILITY
complexity: large
epic_branch: epic/PRD-023-mcp-and-skills
created: 2026-11-23
---

# Plan: `tools/call` path (M3-M9)

## Summary

`handle_tools_call` (`app/routers/mcp.py:188`) becomes a thin adapter over a new `mcp_gateway.call(identity, params, request_id)` (`app/services/mcp_gateway.py`, after `visible_catalogue` at :138). Order: M3 params, M4 `usage_limits.admit(charges_budget=False)`, M5 `visible_catalogue(identity).callable`, M6 `action_policy.evaluate(..., surface=McpSurface)`, M7 `action_audit.record(..., mcp=McpRecord)` without `audit_ref`, M8 deny note or `mcp_upstream.call_tool`, M9 `record_outcome` best effort. Results are returned unmodified (STORY-014 adds inspection/caps; STORY-016 fills correlation).

- Story: `.agents/stories/PRD-023-mcp-and-skills/STORY-013-tools-call-path.md` (AC text lives there)
- PRD sections: 6.3, 9.2 (T6 T7 T9 T10 T16), 10, D8 D9 D13 D14 D15
- Systems: `app/routers/mcp.py`, `app/services/mcp_gateway.py`, `app/services/usage_limits.py`, `app/services/action_audit.py` (one annotation), `app/models/mcp_schemas.py`

## Design Decisions

The orchestrator's design points 1-5 are binding and implemented as written. What the code adds or refines:

- **HTTP answers from a handler.** `mcp_gateway` cannot import the router (the router imports it). The gateway defines `GatewayRpcError(code, message)` and `UsageRefused(retry_after_seconds, limit)`. `handle_tools_call` maps the first to `JsonRpcError` and the second to a new router exception `HttpRefusal(status, code, message, headers)`. The dispatcher (`mcp.py:282-289`) gets one `except HttpRefusal` arm returning `_rpc_error(..., status=429, headers=...)`; `_rpc_error` (:142) gains an optional `headers`. The 429 body is a JSON-RPC error, code `-32000` (new `schemas.USAGE_LIMITED`), fixed text `Usage limit reached` (my choice; the PRD fixes only status and header).
- **No `/v1` helper for `Retry-After` from `resets_at` exists** (deviation from the brief). `/v1` answers a usage refusal as HTTP 403 with no header (`v1_translate.py:755`); the `Retry-After` helpers (`storage_faults.py:45-66`) serve storage 503s. Add a pure `usage_limits.retry_after_seconds(refusal, now=None) -> int`: parse `resets_at` with `_TIMESTAMP_FORMAT`, `ceil` the difference, minimum 1 (the breaker's rule, `circuit_breaker.py:66`).
- **`USAGE_LIMITS_ENABLED` is the caller's switch** (`usage_limits.py` docstring, `query_pipeline.py:758`): call `admit` only when it is true. `UsageLimitError` (fail closed) -> `-32603` "usage could not be checked", no row, no forward.
- **Names.** `name` not a `str` -> -32602, not recorded. Resolve with `mcp_config.split_tool` (`mcp_config.py:178`, raises `ValueError`). The engine's `ToolCall.name` is the BARE tool, because it tests membership in `McpSurface.visible` (`action_policy.py:205`); `McpSurface(server, callable.get(server, frozenset()))`. Unresolvable name: `ToolCall(id, name[:256], canonical)` with `McpSurface("", frozenset())`, so the engine returns `deny / tool.not_in_skill` (`action_policy.py:349-352`). A configured server missing from `callable` (nothing held, or `list_tools` raised `McpUpstreamError`, swallowed at `mcp_gateway.py:153-158`) gets an empty `visible`: the call is a recorded -32602 (outage hidden from the agent; `visible_catalogue` logs the WARNING).
- **`mcp_server` with no configured-server prefix: NULL.** Column is nullable (`app/db/models.py:497`, `Optional[str]` at :787) and `/v1` rows read NULL; storing a caller-chosen prefix would pollute `?server=`. A configured prefix is stored even when the tool is hidden. `McpRecord.mcp_server` is annotated `str` (`action_audit.py:241`) but only passed through; widen to `Optional[str]` (no behaviour change).
- **One -32602 text** for hidden / unlisted / withheld / nonexistent / unconfigured (T6): constant `UNKNOWN_TOOL_MESSAGE`. M3 messages (`INVALID_NAME_MESSAGE`, `INVALID_ARGUMENTS_MESSAGE`) are separate and unrecorded.
- **T7.** `canonical = action_audit.canonical_json(arguments)` (:228) once; the engine gets that string; the hash is `sha256(canonical.encode()).hexdigest()` from the same string (not `arguments_canonical_hash`, which would serialize again; a test asserts equality). `call_tool` gets the same dict object `strict_json` produced (`mcp.py:239`). `ValueError`/`RecursionError` while serializing -> -32602, unrecorded. `ACTION_MAX_ARGUMENT_CHARACTERS` applies in the engine (over-long -> recorded deny).
- **Deny text.** Import `DENIAL_NOTE_TEMPLATE`, `NOTE_FIELD_CAP` (`tool_release.py:41,45`); `format(name=sent_name[:NOTE_FIELD_CAP], id=str(request_id)[:NOTE_FIELD_CAP], reason=decision.reason)`, `name` = prefixed name as sent. Result `{"isError": True, "content": [{"type": "text", "text": note}]}`; `outcome` stays NULL.
- **Failure texts** (constants, §10, T16): `TIMEOUT_TEXT = "[harness] {name} ({id}) timed out after {n}s; the call may have run"` (`n` = the server's `timeout_seconds`, `mcp_config.py:133`); `UPSTREAM_ERROR_TEXT = "[harness] {name} ({id}) failed on server {server}; the call may have run"`. `CallOutcome.detail` (`mcp_upstream.py:102`) is only logged (user, server, tool). Mapping: `ok` and not `is_error` -> `ok`; `error` -> `tool_error` (content/structured returned as-is, `isError: true`); `timeout`; `upstream_error`. Never retried.
- **Result digest, defined once for STORY-014:** `result = {"content": [...], "isError": bool, + "structuredContent" if present}`; `mcp_gateway.result_digest(result) -> (len(canonical_json(result).encode()), sha256 hex of it)`; `result_flags=()`. `duration_ms` wraps `call_tool` only. Harness-made isError texts are digested the same way.
- **`skills` column:** `f"{s.id}@{s.version}"` for each `mcp_config.held_skills(identity)` whose `tools` contains `server__tool`, config order; empty when hidden.
- **M7 seam:** `_correlate(identity, server, tool, args_hash) -> (audit_id, linked_decision_id)` returns `(None, None)`; STORY-016 replaces its body. `mcp_config_digest=mcp_config.mcp_config_digest()`, `jsonrpc_id=request_id`.
- **Write failures.** `record` raising anything (`StorageError` propagates by design, `action_audit.py:299-303`) or returning `len != 1` -> `GatewayRpcError(-32603, "decision could not be recorded")`, WARNING with class name only, nothing forwarded. `record_outcome` already swallows and logs ERROR (`action_audit.py:361-402`); the gateway also wraps it in `try/except Exception` -> `logger.error("mcp outcome not recorded: user_id=%s row_id=%s: %s", ..., type(exc).__name__)`.
- **Round trips: at most 3** (admit, insert, outcome); refused = 1, denied = 2. The sync DB calls run through `pipeline_executor.run_in_pipeline` (`pipeline_executor.py:45`), not on the event loop. No `database.py` change, so no census edit. `visible_catalogue` costs no DB trip.
- One INFO line per call: user, server, tool, decision, rule, outcome, duration. Never arguments, URLs or results.

## Skills In Use

None (`skills: []`; nothing in `.agents/skills/` matches).

## Patterns to Follow

| Category | Source | What to mirror |
|---|---|---|
| Handler seam | `app/routers/mcp.py:169-212` | `async def(identity, params, request_id) -> dict`; `_HANDLERS` looked up at call time |
| Dispatcher | `app/routers/mcp.py:282-289` | `except JsonRpcError` before the generic arm; add `HttpRefusal` |
| Module style | `app/services/mcp_gateway.py:1-26,138-188` | docstring cites PRD ids; WARNINGs log class names only |
| Usage gate | `app/services/query_pipeline.py:755-760` | `USAGE_LIMITS_ENABLED` guard around `admit` |
| Audit | `app/services/action_audit.py:265-402` | `mcp=` forbids `audit_ref`; ids in order |
| Tests | `tests/test_mcp_gateway.py:44-100,287-320`; `tests/mcp_stub.py:49-170` | `_cfg`, autouse `_fresh`, `http` fixture, `mcp_stub_factory`, `stub.calls(tool)` |
| Policy in tests | `tests/test_action_config.py:523` | `_load_text`-style tmp policy file |

## Files to Change

| File | Action | Purpose |
|---|---|---|
| `app/services/mcp_gateway.py` | UPDATE | `call()`, constants, `result_digest`, `_correlate`, `GatewayRpcError`, `UsageRefused` |
| `app/routers/mcp.py` | UPDATE | `handle_tools_call`, `HttpRefusal`, dispatcher arm, `_rpc_error(headers=)`, docstring row |
| `app/services/usage_limits.py` | UPDATE | `retry_after_seconds` |
| `app/models/mcp_schemas.py` | UPDATE | `USAGE_LIMITED = -32000` |
| `app/services/action_audit.py` | UPDATE | `McpRecord.mcp_server: Optional[str]` |
| `tests/test_mcp_tools_call.py` | CREATE | every AC (non-DB and `db`) |
| `tests/test_usage_limits.py` | UPDATE | `retry_after_seconds` cases |
| `tests/test_mcp_endpoint.py` | UPDATE | any `tools/call` -> -32601 placeholder assertion (grep; PRD-023 STORY-013 comment) |

## Tasks

1. **Usage helper + constant** (`usage_limits.py`, `mcp_schemas.py`). Validate: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_usage_limits.py -m "not db"`.
2. **`mcp_gateway.call`** with the order above and the constants; no `mcp` import (guard `tests/test_mcp_gateway.py:343`). Validate: `tests/test_mcp_gateway.py -m "not db"`.
3. **Router adapter** (`handle_tools_call`, `HttpRefusal`, dispatcher arm, docstring table). Validate: `tests/test_mcp_endpoint.py -m "not db"`.
4. **`McpRecord` annotation.** Validate: `tests/test_mcp_audit.py -m "not db"`.
5. **Tests** (`tests/test_mcp_tools_call.py`). Setup: bare `FastAPI` + `mcp_router.router` in a `TestClient` context, `client.portal.call(mcp_upstream.aclose_all)` at teardown (`test_mcp_gateway.py:292-306`), stub from `mcp_stub_factory`; tmp action policy with `mcp_tools: {stub: {query: {kind: sql, target: sql}, push_files: {kind: fs_write, target: "files[].path"}}}` and `mcp_opaque_tools: {stub: {create_pull_request: flag}}`; roles via `monkeypatch.setattr(authz, "ROLE_PERMISSIONS", ...)` (a `dev` without and a `dba` with `action:sql:ddl`). Any "no task left" assertion first does `asyncio.wait(others, timeout=5)`.
   - **Non-DB** (local): monkeypatch `action_audit.record` (capture `(decisions, identity, mcp)`, return `[42]`) and `record_outcome` (capture args), plus `usage_limits.admit`; real stub for forwarded paths.
   - **`db`-marked** (CI): the same scenarios reading `action_decisions` rows (surface, decision, rule, outcome, skills, hash, duration, result columns); a 429 leaves the row count unchanged; failed outcome update leaves `outcome IS NULL`.
   - Scenarios: DDL deny vs `dba` allow (note equals `DENIAL_NOTE_TEMPLATE.format(...)`, counter 0 then 1); hidden / unlisted / no-`__` / unconfigured-server / withheld names give one identical -32602 and a `tool.not_in_skill` row (`mcp_server` NULL only for the unconfigured prefix, counter 0); non-str name, list/string/null `arguments` -> -32602 with `record` uncalled; absent `arguments` forwards `{}`; `record` raising `StorageUnavailableError` -> -32603, counter 0; `record_outcome` raising (and the real one with `update_action_outcome` patched to raise) -> result returned, ERROR in `caplog`; `admit` refused -> 429, `Retry-After` equals `retry_after_seconds`, `record`/`call_tool` uncalled, spy order proves `admit` before catalogue/`evaluate`, `charges_budget is False`; T7: the dict passed to `call_tool` `is` the parsed one, `ToolCall.arguments` equals the canonical string, shuffled key order gives the same hash as `arguments_canonical_hash`; `slow` against a 1 s server timeout -> exact text, `outcome='timeout'`, `stub.calls("slow") == 1`; upstream error (fake `call_tool`) -> "may have run" text, a sentinel URL in `detail` absent from the response, present nowhere in the row; stub `isError` -> `tool_error`; `push_files` `.github/workflows/ci.yml` -> `fs.write_protected`; `create_pull_request` -> forwarded, `flag`, `tool.opaque`; call order spy `admit < catalogue < evaluate < record < call_tool < record_outcome`; `skills == ["open-pull-request@1.0.0"]`; `USAGE_LIMITS_ENABLED=false` skips `admit`; at most 3 DB-calling steps.

## End-to-End Tests

- [ ] `TestClient` on `mcp_router.router` against the real stub: allow, flag, deny, not_in_skill, 429, timeout, each through `POST /mcp`.
- [ ] No `chat_ui/` change.

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_mcp_tools_call.py tests/test_mcp_gateway.py tests/test_mcp_endpoint.py tests/test_mcp_audit.py tests/test_usage_limits.py tests/test_mcp_upstream_import_graph.py tests/test_untouched_app.py -m "not db"
```
No new route (no Caddyfile change); no rename of tests; grep `tests/` for `-32601` placeholders on `tools/call` before running.

## Acceptance Criteria -> Tasks -> Tests

| AC | Task(s) | Test (`tests/test_mcp_tools_call.py::`) |
|---|---|---|
| AC1 DDL deny vs dba allow | 2, 5 | `test_ddl_denied_without_grant_allowed_for_dba` (+ `_db`) |
| AC2 not_in_skill, args shape | 2, 5 | `test_unresolvable_names_share_one_recorded_32602`, `test_non_object_and_absent_arguments` |
| AC3 record / outcome failure | 2, 5 | `test_record_failure_is_32603_and_not_forwarded`, `test_record_outcome_failure_still_returns_result` |
| AC4 429 | 1, 2, 3, 5 | `test_usage_refusal_is_429_with_retry_after_and_no_row` |
| AC5 forwarding | 2, 5 | `test_one_parse_forwarded_object_is_parsed_object`, `test_slow_timeout_text_and_no_retry`, `test_upstream_error_text_hides_detail`, `test_tool_error`, `test_push_files_workflow_path`, `test_create_pull_request_flagged` |

## Risks

- Brief said "reuse the /v1 Retry-After helper": none exists; a small pure helper is added.
- `-32000` for the 429 body, and widening `McpRecord.mcp_server`, are my choices; flagged for the orchestrator.
- An unlistable server turns every call to it into a recorded -32602 (design point 2).
