---
story: STORY-006
prd: PRD-022
plan: .agents/plans/PRD-022-provider-fallback-and-native-adapters/completed/STORY-006-stub-anthropic-mode-and-faults.plan.md
epic_branch: epic/PRD-022-provider-fallback-and-native-adapters
commit: pending
status: COMPLETE
completed: 2026-11-20
---

# Implementation Report - STORY-006: Stub upstream, Anthropic Messages mode and scripted faults

## Summary

`scripts/stub_openrouter.py` serves `POST <anything>/messages` from the same script as Chat: Messages JSON, or SSE when `stream: true`. New additive reply keys: `stop_reason`, `retry_after`, `fault` (`timeout`, `malformed`) and cache usage counts. `server.endpoint_hits()` returns per-endpoint counters. Chat behaviour and its log line are unchanged (the existing 111 stub tests pass unmodified). `server_close` releases held `timeout` connections, so teardown never waits.

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| Tests (stub_anthropic_mode, stub_openrouter, anthropic_adapter, e2e_live, e2e_opencode_script, e2e_cline_script) | 278 passed, 0 failed, 0 skipped |
| E2E (real AnthropicAdapter against the stub) | passed (`test_the_real_adapter_against_the_stub_messages_mode`) |
| Full suite | GitHub CI on push (user decision) |

## Files Changed

| File | Action |
|------|--------|
| `scripts/stub_openrouter.py` | UPDATE |
| `tests/test_stub_anthropic_mode.py` | CREATE (49 cases) |
| `tests/e2e/scripts/README.md` | UPDATE |

## Deviations from Plan

- The plan's risk "a refusal needs non-empty content" no longer applies (orchestrator fix 27e0e91): the e2e refusal case uses EMPTY content through the real adapter and gets `finish_reason == "content_filter"`.
- A `fault` line in the Chat log gets an appended ` fault=<name>` only when scripted; lines of old scripts are byte-identical.
- The README sentence "The stub never streams" was stale since PRD-020 and was corrected.
- STORY-005's ad-hoc loopback server in `tests/test_anthropic_adapter.py` was left alone (per orchestrator); a later cleanup may move those tests onto this stub.
- Flag for STORY-007: JSON `reasoning_blocks` come from the `thinking` block, so a stream-versus-complete property test must count thinking blocks in the stream too.

## Acceptance Criteria

- [x] AC1 Messages JSON (text, tool_use, usage + cache, stop_reason) and SSE event sequence: JSON and SSE cases in `test_stub_anthropic_mode.py`
- [x] AC2 faults on either endpoint (timeout, 503, 429 + Retry-After, 401, 400, malformed, refusal), Chat shapes kept: parametrized fault tests, parse-error tests, adapter E2E
- [x] AC3 first-N faults then normal; per-endpoint hit counter: `test_times_then_normal_on_messages_and_endpoint_hits`, `test_endpoint_hits_count_faulted_and_timed_out_requests`
- [x] AC4 existing tests unchanged; each fault covered; never logs prompt text: unmodified `test_stub_openrouter.py`, `test_messages_traffic_never_reaches_the_log_or_the_console`
