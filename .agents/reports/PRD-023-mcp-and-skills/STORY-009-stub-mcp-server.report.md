---
story: STORY-009
prd: PRD-023
plan: .agents/plans/PRD-023-mcp-and-skills/completed/STORY-009-stub-mcp-server.plan.md
epic_branch: epic/PRD-023-mcp-and-skills
commit: 823a8bf
status: COMPLETE
completed: 2026-11-22
---

# Implementation Report - STORY-009: The scripted stub MCP server and its fixture

## Summary

`scripts/stub_mcp_server.py` is a real Streamable HTTP MCP peer on the SDK's `MCPServer` (mcp 2.3.0) served by uvicorn, with nine tools, `--require-bearer` / `--require-header` (401 before the MCP layer), `--page-size`, and a side channel (`/__stub/stats`, `/__stub/reset`) recording counts, last `Authorization` and header names, never arguments or results. `tests/mcp_stub.py` launches it as a subprocess on a runtime port and provides `mcp_stub` / `mcp_stub_factory` (registered in `tests/conftest.py`). No `app/` change, no DB.

## Validation

| Check | Result |
|-------|--------|
| Backend import | OK |
| tests/test_stub_mcp_server.py | 15 passed |
| + test_prd023_mcp_sdk_facts, test_untouched_app, test_stub_openrouter | 153 passed total, 0 failed, 0 skipped |
| Manual smoke (`--port 9301`, curl stats, stop) | port closed afterwards |
| Orphan check after last pytest | 0 python processes with `stub_mcp_server` in the command line |
| Full suite | GitHub CI on push (user decision) |

## Files Changed

| File | Action |
|------|--------|
| `scripts/stub_mcp_server.py` | CREATE |
| `tests/mcp_stub.py` | CREATE |
| `tests/test_stub_mcp_server.py` | CREATE |
| `tests/conftest.py` | UPDATE (one import line) |

## Deviations from Plan

- `tests/mcp_stub.py` imports `tests/e2e/_live.py` lazily (inside `_live()`), not at module top: `_live` imports `tests.conftest`, and conftest now imports `mcp_stub`, so a top-level import is circular.
- The 401 gate and side channel are one pure-ASGI wrapper (`_Gate`) around the SDK's Starlette app rather than `add_route`; same behaviour.
- Pagination: overriding `_handle_list_tools` on an `MCPServer` subclass worked; no fallback to the low-level `Server` was needed.
- Sampling verified against the real client: no callback gives `-32600 "Sampling not supported"` (tool text `sampling:error:-32600 ...`); a callback gives `sampling:result:CreateMessageResult`. `create_message` is marked deprecated in the SDK (SEP-2577) but emits no failing warning.

## Acceptance Criteria

- [x] AC1 tools + sampling trigger: `test_lists_the_scripted_tools`, `test_huge_returns_requested_size_and_inject_returns_phrase`, `test_sample_sends_server_to_client_request`
- [x] AC2 counts, Authorization + header names, no argument logging: `test_calls_are_counted_per_tool_and_reset`, `test_side_channel_records_authorization_and_header_names_never_arguments`, `test_require_bearer_and_require_header_answer_401_and_count_zero`
- [x] AC3 fixture ready, always stopped: `test_teardown_leaves_no_orphan`, `test_two_stubs_in_one_test_...`, `test_fixture_stopped_the_previous_stub` (Linux: CI)
- [x] AC4 `app/` never imports the stub: `test_nothing_under_app_imports_the_stub`, `test_the_script_imports_nothing_from_app`
