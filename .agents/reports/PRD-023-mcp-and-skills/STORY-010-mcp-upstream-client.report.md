---
story: STORY-010
prd: PRD-023
plan: .agents/plans/PRD-023-mcp-and-skills/completed/STORY-010-mcp-upstream-client.plan.md
epic_branch: epic/PRD-023-mcp-and-skills
commit: pending
status: COMPLETE
completed: 2026-11-22
---

# Implementation Report - STORY-010: mcp_upstream southbound client

## Summary

`app/services/mcp_upstream.py` is the only module importing `mcp` and `httpx2`. Public API: `list_tools`, `call_tool`, `aclose_all`, `invalidate_tools_cache`, plus `UpstreamTool`, `CallOutcome`, `McpUpstreamError`. One owner asyncio task per `(server_id, user_id)` session; headers only from `mcp_config.upstream_auth_headers`; no SDK callbacks; timeouts via the SDK's `read_timeout_seconds` plus a bounded caller guard; `call_tool` is never replayed; `list_tools` retries once on a session dropped under it. Nothing is mounted or called yet (MCP off untouched).

## Validation

| Check | Result |
|-------|--------|
| Backend import | OK |
| Targeted tests (`-m "not db"`) | 139 passed: test_mcp_upstream (21), import_graph (2), stub_mcp_server (16), sdk_facts, mcp_config, untouched_app, caddyfile_routes |
| E2E | `test_end_to_end_list_then_call_against_a_bearer_stub` passed |
| Full suite | GitHub CI on push (user decision) |

## Files

- CREATE `app/services/mcp_upstream.py`, `tests/test_mcp_upstream.py`, `tests/test_mcp_upstream_import_graph.py`
- UPDATE `scripts/stub_mcp_server.py` (`initializes`, `session_404`, `POST /__stub/expire-sessions`), `tests/mcp_stub.py` (`expire_sessions()`), `tests/test_stub_mcp_server.py` (one test), `tests/test_prd023_mcp_sdk_facts.py::test_app_never_imports_mcp` (allows only `app/services/mcp_upstream.py`, T17 / STORY-010 comment)

## Deviations

- AC4 says `-32601` for sampling; the SDK answers `-32600` (STORY-003 facts); the tests assert `-32600`.
- AC2 "retries that call" is superseded by T10 (amended): `call_tool` is reported, not replayed. `list_tools` (read-only) retries once: a judgement accepted by the orchestrator.
- Caller guard is `2 * timeout + 5s` (a request may wait for `initialize` and then run), not `timeout + 5s`.
- Sentinel test asserts the secret is absent; the literal word `Bearer` appears in httpcore debug traces of the stub's own `WWW-Authenticate` header.

## Acceptance Criteria

- [x] AC1 credentials: `test_bearer_and_header_auth_come_only_from_config`, `test_sentinel_token_never_logged_or_returned`, `test_public_api_accepts_no_headers`
- [x] AC2 sessions, idle reap, re-init, no replay: `test_sessions_keyed_by_server_and_user`, `test_idle_session_is_reaped`, `test_unknown_session_reinitializes_next_call_without_replay`
- [x] AC3 timeout, cancel: `test_timeout_outcome_and_slow_counted_once`, `test_caller_cancel_keeps_session`
- [x] AC4 sampling, redirects: `test_sampling_refused_and_no_callbacks`, `test_redirect_not_followed`
- [x] AC5 pagination, cache, T17: `test_pagination_reads_all_pages`, `test_tools_cache_ttl_zero_and_invalidate`, `test_only_mcp_upstream_imports_mcp_and_httpx2`
