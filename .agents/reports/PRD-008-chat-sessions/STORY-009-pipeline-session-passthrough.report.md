---
story: STORY-009
prd: PRD-008
plan: .agents/plans/PRD-008-chat-sessions/completed/STORY-009-pipeline-session-passthrough.plan.md
epic_branch: epic/PRD-008-chat-sessions
commit: PENDING
status: COMPLETE
completed: 2026-09-04
---

# Implementation Report — STORY-009: run_query threads session_id to all seven log_query call sites

**Plan**: `.agents/plans/PRD-008-chat-sessions/completed/STORY-009-pipeline-session-passthrough.plan.md`
**Epic Branch**: `epic/PRD-008-chat-sessions`
**Commit**: `PENDING`

## Summary

`run_query` gained `session_id: Optional[str] = None`, appended after `call_openrouter` so no existing caller — the router's keyword call included — needed editing. All seven `log_query(...)` call sites in `app/services/query_pipeline.py` now pass it: six inline in `run_query` (duplicate-blocked, pattern-blocked, input `PiiRedactorError`, `OpenRouterError`, output `PiiRedactorError`, success) and the seventh in `_deny`, which serves the three authorization arms.

`_deny` takes `session_id` as a **required** parameter rather than a defaulted one or a closure. That is the story's final AC, and it is load-bearing: the helper is called from three arms, and a required parameter makes a forgotten arm a `TypeError` at the call site instead of a `NULL` that only surfaces in a compliance report. The parameter carries a comment saying so.

Nothing else moved. `call_openrouter` is untouched, no validation was added (the UUID check and the 403 are STORY-010, at the router boundary), and omitting `session_id` reproduces the current release exactly — asserted field by field, not assumed.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | `_deny` takes `session_id` as a required parameter; its `log_query` passes it | `app/services/query_pipeline.py` | ✅ |
| 2 | `run_query` signature + the three denial arms pass it by keyword | `app/services/query_pipeline.py` | ✅ |
| 3 | Duplicate-blocked, pattern-blocked and input-redactor arms | `app/services/query_pipeline.py` | ✅ |
| 4 | `OpenRouterError`, output-redactor and success arms | `app/services/query_pipeline.py` | ✅ |
| 5 | Per-arm test suite (9 tests, one per arm) | `tests/test_query_pipeline_session_passthrough.py` | ✅ |
| 6 | Omitted-value cases: NULL on every arm, rest of the row identical | `tests/test_query_pipeline_session_passthrough.py` | ✅ |
| 7 | Census guard: seven call sites, each passing `session_id` | `tests/test_query_pipeline_session_passthrough.py` | ✅ |
| 8 | Pinned suites verified unmodified and green | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| `from app.main import app` | ✅ |
| New suite | ✅ 17 passed |
| Pinned suites (authorization, integration, query_router, route_reservations, audit_logger) — run **unmodified** | ✅ 77 passed |
| Full suite `pytest -q` | ✅ 1350 passed |
| E2E (live libSQL + real HTTP route) | ✅ 13/13 |
| Census guard seen failing under mutation | ✅ (see below) |

**Mutation check.** Task 7 required the guard be observed failing rather than trusted. `session_id=session_id` was removed from the duplicate-blocked arm; both `test_every_log_query_call_site_in_the_pipeline_passes_session_id` and `test_duplicate_blocked_arm_carries_the_session_id` failed, the census naming the offending call site in its message. The line was restored and the suite re-ran green.

**Note on the full-suite run.** The first `pytest -q` reported 695 passed / 655 errors from mass fixture failures. This was the local libSQL dev container degrading, not this change — the container had just been restarted after Docker Desktop stopped mid-session. An unchanged re-run gave 1350 passed, 0 errors.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/services/query_pipeline.py` | UPDATE | +31/-4 |
| `tests/test_query_pipeline_session_passthrough.py` | CREATE | +496 |

No other application file was touched. No pinned test suite was edited.

## Deviations from Plan

1. **The census asserts per call site, not by raw string count.** The plan's Task 7 proposed `source.count("session_id=session_id") == 7`. That is wrong: the three `_deny(...)` call sites pass the same expression, so the string occurs **ten** times while only seven of them are `log_query` arguments. The test now paren-matches each `log_query(...)` call expression and checks each one individually — a stricter assertion than the plan's, and it localizes the failure to the offending arm. The plan's intermediate `grep -c` expectations (4, then 7) were likewise counting artifacts and were superseded by this.

2. **`grep -n "log_query(" ...` reports seven, not the plan's predicted eight.** The plan expected the import line to match; `from app.services.audit_logger import log_query` has no parenthesis, so it does not. AC 2's grep therefore reads exactly seven with no mental subtraction — better than planned.

3. **The input-redactor arm is distinguished by `model_used is None`, not by the plan's suggested assertion.** The plan proposed asserting `model_used == "gpt-4"` on the upstream arm only; the input arm runs before `call_openrouter`, so its row has no model at all, which is the sharper discriminator between the two failure rows. Both assertions are present.

4. **E2E was run twice against a shared database before passing.** The out-of-pytest smoke script has no conftest reset, so a second run saw its own earlier prompts as genuine 24h duplicates, and the first version of it did not authenticate against the route (401). Both were defects in the throwaway script, not in the code; it now uses a per-run nonce and seeds a user the way `tests/test_query_router.py:40` does.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_query_pipeline_session_passthrough.py` | `test_permission_denied_arm_carries_the_session_id`, `test_model_not_permitted_arm_carries_the_session_id`, `test_byok_denied_arm_carries_the_session_id`, `test_duplicate_blocked_arm_carries_the_session_id`, `test_pattern_blocked_arm_carries_the_session_id`, `test_input_redactor_failure_arm_carries_the_session_id`, `test_openrouter_failure_arm_carries_the_session_id`, `test_output_redactor_failure_arm_carries_the_session_id`, `test_success_arm_carries_the_session_id_on_the_row_the_footer_names`, `test_session_id_omitted_writes_null_on_every_arm` (6 params: permission-denied, model-not-permitted, byok-denied, pattern-blocked, duplicate-blocked, success), `test_omitting_session_id_leaves_the_rest_of_the_success_row_identical`, `test_every_log_query_call_site_in_the_pipeline_passes_session_id` |

17 test cases from 12 test functions.

## Acceptance Criteria

- [x] `run_query` accepts `session_id: Optional[str] = None`
- [x] `grep -n "log_query(" app/services/query_pipeline.py` reports **seven** call sites, every one passing `session_id` — six in `run_query`, the seventh in `_deny`
- [x] A duplicate-blocked send carries the `session_id`
- [x] Pattern-blocked, permission-denied, model-not-permitted and BYOK-denied sends all four carry it
- [x] Input `PiiRedactorError`, output `PiiRedactorError` and `OpenRouterError` failure rows all three carry it
- [x] A successful send carries it, on the row whose `audit_id` the UI footer shows
- [x] Called without `session_id`, the row is `NULL` and every other field is identical — `tests/test_query_pipeline_authorization.py` and `tests/test_integration.py` pass unmodified
- [x] `_deny` takes `session_id` explicitly, required, rather than closing over it
- [x] All tasks completed
- [x] Full suite `pytest -q` green (1350 passed)
- [x] `call_openrouter` untouched; no validation added to the pipeline (STORY-010 owns the 403)
- [x] Follows existing patterns (STORY-008's appended-last optional parameter; STORY-023's census guard)
