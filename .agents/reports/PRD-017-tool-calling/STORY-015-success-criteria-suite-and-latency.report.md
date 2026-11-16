---
story: STORY-015
prd: PRD-017
plan: .agents/plans/PRD-017-tool-calling/completed/STORY-015-success-criteria-suite-and-latency.plan.md
epic_branch: epic/PRD-017-tool-calling
commit: pending
status: COMPLETE
completed: 2026-11-16
---

# Implementation Report — STORY-015: In-process success-criteria suite for tool calling; step 7c latency measured

**Plan**: `.agents/plans/PRD-017-tool-calling/completed/STORY-015-success-criteria-suite-and-latency.plan.md`
**Epic Branch**: `epic/PRD-017-tool-calling`
**Commit**: `pending`

## Summary

Tests only. One new file, `tests/test_tool_calling_criteria.py` (13 tests that run by default, 6 of them parametrized into 18 cases, plus 1 benchmark test, skipped without `--run-benchmark`). It drives `/v1/chat/completions` through `TestClient` with `V1_TOOLS_ENABLED=true` and an injected upstream, and proves the brief's success criteria. No app code changed. Fixtures and helpers are imported from `tests/test_v1_tools.py`, `tests/test_query_pipeline_tools.py` and `tests/test_action_corpus.py`.

## Tasks Completed

| # | Task | Status |
|---|------|--------|
| 1 | Skeleton, imports, helpers (`_body`, `_content`, `_released`, `_finish`, `_assert_allowed`) | done |
| 2 | DROP TABLE denied, audited, reported (shell+sqlite3, run_sql, MCP query) x json/sse; mixed response | done |
| 3 | Arguments byte-identical, history to upstream and upstream to client (json, sse, SDK accumulator) | done |
| 4 | `npm test` twice in one session not held; resend held (json, sse resend) | done |
| 5 | T1 deny-all; flag off is PRD-015 | done |
| 6 | Step 7c latency, benchmark-marked | done |
| 7 | Targeted run, benchmark, report | done |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| Targeted: `tests/test_tool_calling_criteria.py tests/test_v1_tools.py` | 746 passed, 1 skipped (the benchmark), 0 failed |
| Benchmark run | 1 passed |
| Full suite | deferred to orchestrator (user decision) |

`test_v1_tools.py` is unedited. `test_untouched_app.py` and `test_pii_redaction_integration.py` were not run (no app file touched, nothing renamed).

## Step 7c latency (target p95 < 5 ms)

Command: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_tool_calling_criteria.py -m benchmark --run-benchmark -s -q -p no:cacheprovider`

```
STORY-015 step 7c over 10 responses (75 calls, <= 8 per response) x 50 rounds: min 0.4692 ms / p50 1.7896 ms / p95 2.9327 ms / max 42.6636 ms; 8-call responses (9): p50 1.8203 ms / p95 2.9712 ms
```

Verdict: p95 2.93 ms over all responses and 2.97 ms over the 8-call responses, both under the 5 ms target. No threshold is asserted (wall-clock gates are flaky; PRD-016 STORY-017 precedent). The one 42.7 ms max is a single outlier sample.

## Fixture import outcome

`--setup-plan` showed the imported `temp_db` override (chained onto conftest's `temp_db`) and the autouse `_flag_state` both resolve in the new module, so no local copy was needed.

## Deviations from Plan

- Benchmark as a marked test, not a `scripts/measure_*` script (as accepted by the orchestrator; no existing script fits a pure-CPU step over a test-module corpus).
- Added `test_tricky_arguments_are_what_the_test_means_them_to_be`: a no-DB guard that the argument literals parse as JSON and differ from their re-dump.
- A plain text answer omits the `tool_calls` key on the JSON body (it is `null` only when calls were all denied), so the loop's final turn asserts `not message.get("tool_calls")`.
- Wire encoding: the raw-substring needle `json.dumps(args, ensure_ascii=False)` held for the httpx request, the Starlette JSON body and the pydantic SSE chunks; no per-layer exception was needed.

## Tests Written

`tests/test_tool_calling_criteria.py`: `test_drop_table_is_denied_recorded_with_the_audit_id_and_reported` (3 calls x json/sse), `test_mixed_response_releases_only_the_allowed_calls` (json/sse), `test_tricky_arguments_are_what_the_test_means_them_to_be`, `test_history_arguments_reach_the_upstream_byte_identical`, `test_response_arguments_reach_the_client_byte_identical` (json/sse), `test_npm_test_twice_in_one_session_is_not_held_but_a_resend_is` (json/sse), `test_no_call_is_released_when_every_call_is_denied` (json/sse), `test_flag_off_refuses_the_whole_tool_request_as_prd_015` (json/sse), `test_step_7c_latency_over_the_synthetic_corpus` (benchmark).

## Acceptance Criteria

- [x] DROP TABLE (shell sqlite3, run_sql, MCP query) denied, recorded with the audit_id (table and `/audit/actions?audit_id=`), reason in content, json and sse; mixed response releases only allowed calls (Task 2 tests)
- [x] PII, unicode and escape-heavy arguments byte-identical at the upstream and at the client, json and sse (Task 3 tests)
- [x] `npm test` / edit / `npm test` loop never held; byte-identical resend held (Task 4 test)
- [x] Deny-all leaves no call in either shape (T1); flag off is `tools_not_supported` (Task 5 tests)
- [x] Step 7c p50/p95 recorded above, p95 2.93 ms (Task 6)
- [x] Backend imports; targeted tests pass; follows existing patterns
