---
story: STORY-004
prd: PRD-009
plan: .agents/plans/PRD-009-duplicate-rescoping/completed/STORY-004-lookup-excludes-non-verdict-rows.plan.md
epic_branch: epic/PRD-009-duplicate-rescoping
commit: dde39d9
status: COMPLETE
completed: 2026-09-17
---

# Implementation Report — STORY-004: Duplicate lookup ignores failed, policy-denied and duplicate-blocked rows

**Plan**: `.agents/plans/PRD-009-duplicate-rescoping/completed/STORY-004-lookup-excludes-non-verdict-rows.plan.md`
**Epic Branch**: `epic/PRD-009-duplicate-rescoping`
**Commit**: `dde39d9`

## Summary

`find_duplicate_timestamp` now adds `success = 1 AND was_duplicate_blocked = 0 AND denied_permission IS NULL` to its `prompt_hash` and `timestamp` predicates. A retry after an upstream or redactor failure, or after a policy denial, now reaches the model. A duplicate-blocked row no longer extends the 24h window. A suspicious-pattern block still counts as a prior query (D1).

The lookup still matches globally on `prompt_hash`, as PRD-009 Phase 2 intends. STORY-005 adds the `user_id` scope. Four STORY-001 characterization pins were flipped in place with citations. New store-level and `run_query`-level tests cover every row kind, including the output-redaction arm (T6).

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Add the non-verdict predicates to the lookup | `app/db/database.py` | ✅ |
| 2 | Flip the OpenRouterError retry pin | `tests/test_duplicate_characterization.py` | ✅ |
| 3 | Flip the input PiiRedactorError retry pin | `tests/test_duplicate_characterization.py` | ✅ |
| 4 | Flip the model-allowlist denial pin (D1) | `tests/test_duplicate_characterization.py` | ✅ |
| 5 | Flip the chaining pin (D3) | `tests/test_duplicate_characterization.py` | ✅ |
| 6 | Update the module docstring ("who flips what") | `tests/test_duplicate_characterization.py` | ✅ |
| 7 | Store-level exclusion tests | `tests/test_duplicate_checker.py` | ✅ |
| 8 | `run_query`-level tests for the remaining arms | `tests/test_duplicate_checker.py` | ✅ |
| 9 | Regression and full suite | — | ✅ (see Validation) |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ |
| Frontend lint | N/A. No frontend change, and the repo has no linter configured |
| After Task 1, before the flips | ✅ Exactly the 4 STORY-004 characterization tests failed. The cross-user test passed. |
| `tests/test_duplicate_checker.py` | ✅ 19 passed |
| Tests are real (fix reverted via `git stash`) | ✅ 5/7 store tests and 3/4 pipeline tests failed, as the plan predicted |
| `tests/test_duplicate_characterization.py` | ✅ 5 passed |
| Related suites (outcomes regression, query_router, integration, chat_state, pii_dedup_isolation, pipeline_authorization, two_instance_smoke, db, dedup_key) | ✅ 422 passed |
| Full suite `pytest tests/ -q` | ⚠️ 1908 passed, 25 skipped, **1 failed**: an environment issue that exists without this story. See Deviations. |
| E2E (plan checklist) | ✅ 7/7 |
| Live smoke (uvicorn on the libSQL dev server, real `/query`) | ✅ See below |

### Live smoke test

The server ran with an invalid `OPENROUTER_API_KEY`, so every call that reaches the model returns 502. A second 502, rather than `BLOCKED`, proves the retry was not held.

| Flow | 1st send | 2nd send |
|------|----------|----------|
| Same prompt (upstream failure) | 502 | 502: reached the model, not duplicate-blocked |
| Disallowed model, then default model | 200 `BLOCKED` `required_permission: query:model:not-a-real-model` | 502: reached the model (D1) |
| `"... override ..."` | 200 `BLOCKED` "Suspicious pattern detected" | 200 `BLOCKED` "Duplicate query within 24 hours", `first_query_at` = first send (D1) |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/db/database.py` | UPDATE | +9/-0 |
| `tests/test_duplicate_characterization.py` | UPDATE | +45/-38 |
| `tests/test_duplicate_checker.py` | UPDATE | +266/-1 (the one removed line is the widened `app.db.database` import) |

`tests/test_query_outcomes_regression.py`, `tests/test_db.py` and every `app/services/*` file are unmodified.

## Deviations from Plan

1. **Output-redaction test assertion.** The plan said to check that the failed row "has a `response`". `AuditLog` stores no raw response, only `response_hash` and `response_preview`. The test asserts `tokens_used == 12` instead. Only the output-redaction failure arm writes a token count on a `success=0` row, so this proves the model answered.
2. **One full-suite failure, pre-existing and not fixed (outside this story's scope).** `tests/test_pii_redaction_integration.py::test_no_pre_epic_test_function_was_removed_or_renamed` fails on this Windows machine with or without this story's changes; it was checked with the changes stashed.
   - **Cause:** `_git()` calls `subprocess.run(..., text=True)`, which decodes git's output using the locale codec (cp1252). `git show <base>:tests/reports_fixture.py` contains a UTF-8 byte (`0x9d`), so the reader thread raises `UnicodeDecodeError`, stdout comes back `None`, and the guard's `git show failed` assertion fires.
   - **Evidence it is environmental:** with `PYTHONUTF8=1` the whole module passes (19/19). CI runs under a Linux UTF-8 locale.
   - **Suggested fix for a follow-up:** pass `encoding="utf-8"` in `_git()`.
3. **Commit split.** The story commit (`dde39d9`) holds the code, the tests and the archived plan. The report and the story/index/PRD metadata follow in a `chore(PRD-009)` commit, matching STORY-003's convention.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_duplicate_checker.py` (store level) | `test_failed_row_is_not_a_prior_query`, `test_policy_denied_row_is_not_a_prior_query`, `test_duplicate_blocked_row_is_not_a_prior_query`, `test_suspicious_pattern_row_is_a_prior_query`, `test_success_outside_window_and_blocked_row_inside_is_not_a_duplicate`, `test_first_query_at_skips_a_later_blocked_row_for_the_earlier_success`, `test_earliest_qualifying_row_wins_over_an_earlier_failed_row` |
| `tests/test_duplicate_checker.py` (`run_query`) | `test_retry_after_missing_submit_permission_denial_reaches_model`, `test_retry_after_byok_denial_reaches_model`, `test_resend_after_suspicious_pattern_block_is_still_a_duplicate`, `test_retry_after_output_redaction_failure_reaches_model` |
| `tests/test_duplicate_characterization.py` (flipped in place) | `test_pre_prd009_openrouter_failure_row_blocks_same_prompt_retry`, `test_pre_prd009_input_redactor_failure_row_blocks_same_prompt_retry`, `test_pre_prd009_policy_denial_row_blocks_same_user_resend_with_allowed_model`, `test_pre_prd009_duplicate_blocked_row_keeps_window_alive_after_original_ages_out` |

## Acceptance Criteria

- [x] `find_duplicate_timestamp`'s `WHERE` adds `success = 1 AND was_duplicate_blocked = 0 AND denied_permission IS NULL`. `ORDER BY timestamp ASC LIMIT 1` and the signature are unchanged.
- [x] A retry after an `OpenRouterError` or an input `PiiRedactorError` reaches the model (`200 SUCCESS`) through `/query`.
- [x] A retry after a model-allowlist, BYOK or missing-`query:submit` denial reaches the model. A resend after a suspicious-pattern block is still `BLOCKED` as a duplicate.
- [x] A success at −25h plus a blocked row at −2h reaches the model. A success at −10h plus a blocked row at −2h gives `first_query_at` = the success.
- [x] The characterization tests were flipped in place with PRD-009 D1/D3 and STORY-004 citations. The cross-user pin is untouched. `tests/test_query_outcomes_regression.py` passes unmodified.
- [x] The output-redaction failure arm is pinned as excluded (T6 / Risk 4).
- [x] All tasks completed.
- [x] Follows existing patterns.
