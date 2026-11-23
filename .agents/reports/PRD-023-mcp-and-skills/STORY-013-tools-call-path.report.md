---
story: STORY-013
prd: PRD-023
plan: .agents/plans/PRD-023-mcp-and-skills/completed/STORY-013-tools-call-path.plan.md
epic_branch: epic/PRD-023-mcp-and-skills
commit: bfe7c9b
status: COMPLETE
completed: 2026-11-23
---

# Implementation Report - STORY-013: `tools/call` path

**Plan**: `.agents/plans/PRD-023-mcp-and-skills/completed/STORY-013-tools-call-path.plan.md`
**Epic Branch**: `epic/PRD-023-mcp-and-skills`
**Commit**: bfe7c9b

## Summary

`mcp_gateway.call(identity, params, request_id)` implements M3-M9: params shape (-32602, no row), usage admit (`charges_budget=False`, only when `USAGE_LIMITS_ENABLED`; refusal is HTTP 429 with `Retry-After` and a JSON-RPC `-32000` body), `visible_catalogue(...).callable`, `action_policy.evaluate(surface=McpSurface)`, the decision row via `action_audit.record(mcp=)` BEFORE any forward, a deny note or `mcp_upstream.call_tool`, and a best-effort `record_outcome`. Not-callable names are one recorded -32602. `handle_tools_call` is a thin adapter; the dispatcher gained an `HttpRefusal` arm.

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| `tests/test_mcp_tools_call.py -m "not db"` | 34 passed, 5 deselected (db) |
| gateway, endpoint, audit, usage_limits, import graph, untouched_app, caddyfile routes `-m "not db"` | 139 passed, 11 deselected |
| `test_usage_limits.py` + `test_pii_redaction_integration.py` `-m "not db"` (rerun after a guard fix) | 39 passed, 15 deselected |
| db-marked variants | NOT RUN (Docker Desktop down); run in CI |
| Full suite | GitHub CI on push (user decision) |

## Files Changed

app/services/mcp_gateway.py (call, GatewayRpcError, UsageRefused, result_digest, _correlate seam), app/routers/mcp.py (handle_tools_call, HttpRefusal, `_rpc_error(headers=)`), app/services/usage_limits.py (`retry_after_seconds`), app/models/mcp_schemas.py (`USAGE_LIMITED`), app/services/action_audit.py (`McpRecord.mcp_server: Optional[str]`), tests/test_mcp_tools_call.py (CREATE), tests/test_usage_limits.py, tests/test_mcp_endpoint.py (placeholder updated).

## Deviations from Plan

- `retry_after_seconds` reads the clock with `time.time()` because a PRD-013 guard test forbids the datetime wall-clock call in `usage_limits.py`.
- `tests/test_mcp_endpoint.py`: the `tools/call` -32601 placeholder became a `{}` params call expecting -32602 (M3, no database needed), with a PRD-023 STORY-013 comment.
- The INFO line is split: one after the decision (user, server, tool, decision, rule) and one after the forward (outcome, duration, `detail`).

## Tests Written

`tests/test_mcp_tools_call.py`: 34 non-db tests (DDL deny vs dba allow, five unresolvable names, bad name/arguments, absent arguments, record failure and zero-row result, outcome failure incl. real `record_outcome`, 429, usage fail-closed, usage off, call order, one parse and hash, skills/digest/id, timeout text and no replay, upstream error hides detail, tool_error, result digest, workflow-path deny, flagged PR, log hygiene, adapter shape, SDK import guard, no leftover task) and 5 `db` tests (rows for deny/allow, NULL server, 429 no row, failed outcome leaves NULL, timeout and deny rows). `tests/test_usage_limits.py`: 3 `retry_after_seconds` cases.

## Acceptance Criteria

AC1 DDL deny/allow: `test_ddl_denied_without_grant_allowed_for_dba` (+ db). AC2 not_in_skill and args shape: `test_unresolvable_names_share_one_recorded_32602`, `test_non_object_arguments_*`, `test_absent_arguments_*`. AC3 record/outcome failure: `test_record_failure_is_32603_and_not_forwarded`, `test_record_outcome_failure_still_returns_the_result`. AC4 429: `test_usage_refusal_is_429_with_retry_after_and_no_row`. AC5 forwarding: `test_one_parse_*`, `test_slow_timeout_text_and_no_retry`, `test_upstream_error_text_hides_detail`, tool_error, push_files, create_pull_request tests. All pass locally except the db-marked ones, which were not run.
