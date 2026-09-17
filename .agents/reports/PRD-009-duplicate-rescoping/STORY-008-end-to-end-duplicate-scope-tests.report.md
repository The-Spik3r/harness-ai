---
story: STORY-008
prd: PRD-009
plan: .agents/plans/PRD-009-duplicate-rescoping/completed/STORY-008-end-to-end-duplicate-scope-tests.plan.md
epic_branch: epic/PRD-009-duplicate-rescoping
commit: 7302bd9
status: COMPLETE
completed: 2026-09-17
---

# Implementation Report — STORY-008: End-to-end /query tests for every row of the what-counts table

**Plan**: `.agents/plans/PRD-009-duplicate-rescoping/completed/STORY-008-end-to-end-duplicate-scope-tests.plan.md`
**Epic Branch**: `epic/PRD-009-duplicate-rescoping`
**Commit**: `7302bd9`

## Summary

`tests/test_duplicate_scope.py` proves the rows of PRD-009 Section 6.3's "what counts as a prior query" table through `POST /query`, with real bearer tokens. Each test asserts the HTTP outcome and the audit rows the request left: `dedup_key`, `prompt_hash`, `success`, `was_duplicate_blocked`, `suspicious_pattern` and `denied_permission`. PRD Section 5 stories 1–4 are named tests. The Section 11 items that had no end-to-end test in an allowed module are added here: the 24h boundary, whitespace, all seven call sites, and `prompt_hash`. No production code changed.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Module skeleton, `temp_db` override with Juan and María, `_key`, `_backdate`, `_assert_row_keyed` and the stubs | `tests/test_duplicate_scope.py` | ✅ |
| 2 | Row "Success": story 3; blocked row shares the key; third send still `first_query_at` = the success (D3) | same | ✅ |
| 3 | Row "Suspicious-pattern block" counts (D1); the resend gets the duplicate body | same | ✅ |
| 4 | Row "Duplicate block" does not count: story 4, 23h/25h chaining (D3) | same | ✅ |
| 5 | Row "Policy denial": model allowlist (story 4), BYOK, `query:submit` | same | ✅ |
| 6 | Rows "OpenRouterError" (story 1), "Input/Output PiiRedactorError" | same | ✅ |
| 7 | Row "Router foreign-session refusal" (`dedup_key` NULL) | same | ✅ |
| 8 | Row "Another user_id": story 2, different keys, same `prompt_hash` (D5), no window poisoning (T2) | same | ✅ |
| 9 | Row "Pre-PRD NULL key" (D6, Risk 3) | same | ✅ |
| 10 | Section 11: 24h ± 1 min, whitespace, seven call sites keyed with the raw `prompt_hash` | same | ✅ |
| 11 | Full module, full suite, Section 11 mapping verified by collection | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`python -c "from app.main import app"`) | ✅ |
| Frontend lint | N/A. There is no `frontend/`; the UI is Reflex (`chat_ui/`) and was not touched |
| New module | ✅ 22 passed |
| Full suite (`pytest -q`) | ✅ 1959 passed, 25 skipped, 0 failed (148s) |
| Mutation check | ✅ With `success = 1` and `was_duplicate_blocked = 0` removed from `find_duplicate_timestamp`, 4 tests fail (D3 chaining and the three failure retries); file restored from git |
| `/health` on a running server | ✅ `{"status":"ok"}` (uvicorn against the local libSQL dev server, not the `.env` Turso URL) |
| E2E | ✅ 10/10 plan items, plus a live curl smoke (below) |

### Live smoke (uvicorn + curl, two throwaway users, no model calls)

| # | Request | Response | Row |
|---|---------|----------|-----|
| 1 | Juan, disallowed model | 200 BLOCKED `query:model:not-a-real-model` | `denied_permission` set, key `5dbc…` |
| 2 | Juan, same prompt, allowed model | 200 BLOCKED `Suspicious pattern detected` (the denial did not count) | `suspicious_pattern=override`, key `5dbc…` |
| 3 | María, same prompt | 200 BLOCKED pattern (not a duplicate of Juan) | key `c3a8…`, same `prompt_hash` `b5e0…` |
| 4 | Juan, repeat | 200 BLOCKED duplicate, `first_query_at` = row 2 | `was_duplicate_blocked=1`, key `5dbc…` |
| 5 | Juan, third | 200 BLOCKED duplicate, `first_query_at` still row 2 | `was_duplicate_blocked=1` |
| 6 | No token | 401 | none |

Afterwards the server was stopped and the smoke users and rows were deleted.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `tests/test_duplicate_scope.py` | CREATE | +852 |
| `.agents/plans/PRD-009-duplicate-rescoping/completed/STORY-008-end-to-end-duplicate-scope-tests.plan.md` | CREATE (archived) | +415 |
| `.agents/reports/PRD-009-duplicate-rescoping/STORY-008-end-to-end-duplicate-scope-tests.report.md` | CREATE | this file |
| `.agents/stories/.../STORY-008-end-to-end-duplicate-scope-tests.md`, `.agents/PRDs/PRD-009-duplicate-rescoping/index.md`, `PRD.md` | UPDATE | status, index, `updated` |

## Deviations from Plan

1. **Pre-existing uncommitted test-infra edits were committed first, in their own commit (`9649816`).** Phase 2 of `/implement` stops on a dirty tree, and the user chose "commit them first". The files were `tests/conftest.py` (the dead-stream retry in `_reset_database`), `tests/test_conftest_fixtures.py`, `tests/test_pii_redaction_integration.py` and `tests/test_query_session_id.py`. They are not part of STORY-008. The untracked `pre-prds/` stays uncommitted.
2. **A seeded `query:submit` denial row** (Task 5, planned, recorded here as required). AC 1 allows seeds only for backdated or NULL-key rows. `_deny`'s `query:submit` arm cannot be reached through `/query`, because `require_permission` returns 403 and writes no row first. The test asserts that fact (403, 0 rows). It then seeds one row for Juan with his real key and hash, to prove the lookup excludes it.
3. **`_backdate` ages rows that `/query` wrote** (Tasks 2, 3, 8, 10, planned). It runs an `UPDATE` of `timestamp` only. Timestamps have one-second resolution, so without it the `first_query_at` assertions in AC 4 and T2 would pass vacuously.
4. **The seven-call-site test's denial case covers only the model-allowlist arm.** The three denials share one `_deny` call site; BYOK is also driven over HTTP in its own row test.
5. **Plan metadata.** The plan's Task 11 grep pattern was replaced by a per-name collection check. Same intent, exact matches.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_duplicate_scope.py` | `test_story_3_juan_repeat_at_1400_is_blocked_with_first_query_at_his_0900_success`, `test_resend_after_suspicious_pattern_block_is_blocked_as_a_duplicate_d1`, `test_story_4_row_blocked_at_23h_no_longer_keeps_prompt_blocked_at_25h_d3`, `test_story_4_juan_denied_a_disallowed_model_then_resends_with_an_allowed_one_and_reaches_the_model_d1`, `test_retry_after_byok_denial_reaches_the_model_d1`, `test_missing_query_submit_is_refused_at_the_router_and_leaves_no_prior_query_d1`, `test_story_1_juan_retries_draft_the_q3_vendor_summary_after_a_502_and_reaches_the_model`, `test_retry_after_input_redactor_failure_reaches_the_model`, `test_retry_after_output_redactor_failure_reaches_the_model_again_risk_4`, `test_retry_after_foreign_session_refusal_reaches_the_model`, `test_story_2_maria_at_0900_and_juan_at_0905_both_reach_the_model_with_different_keys`, `test_pre_prd009_row_with_null_dedup_key_does_not_block_the_same_prompt_risk_3`, `test_success_at_23h59m_still_blocks_the_same_prompt`, `test_success_at_24h01m_no_longer_blocks_the_same_prompt`, `test_trailing_whitespace_is_a_different_prompt`, `test_every_call_site_writes_the_credentials_key_and_the_raw_prompt_hash[deny, duplicate, pattern, input-redactor, openrouter, output-redactor, success]` |

## Section 11 functional requirements → named tests (AC 5)

Every item maps to this module, STORY-003's `tests/test_dedup_key.py`, or STORY-002's schema tests in `tests/test_db.py`. `pytest --collect-only` confirmed that every name exists.

| Section 11 item | Named test(s) |
|---|---|
| Retry after `OpenRouterError` (502) not blocked | `test_duplicate_scope.py::test_story_1_juan_retries_draft_the_q3_vendor_summary_after_a_502_and_reaches_the_model` |
| Retry after input `PiiRedactorError` (500) not blocked | `test_duplicate_scope.py::test_retry_after_input_redactor_failure_reaches_the_model` |
| Retry after policy denial (model allowlist, BYOK, missing `query:submit`) not blocked | `test_duplicate_scope.py::test_story_4_juan_denied_a_disallowed_model_then_resends_with_an_allowed_one_and_reaches_the_model_d1`, `::test_retry_after_byok_denial_reaches_the_model_d1`, `::test_missing_query_submit_is_refused_at_the_router_and_leaves_no_prior_query_d1` |
| Same prompt from two users not blocked for either | `test_duplicate_scope.py::test_story_2_maria_at_0900_and_juan_at_0905_both_reach_the_model_with_different_keys` |
| Same user within 24h after success blocked, `first_query_at` = success | `test_duplicate_scope.py::test_story_3_juan_repeat_at_1400_is_blocked_with_first_query_at_his_0900_success` |
| Same user within 24h after suspicious-pattern block blocked (D1) | `test_duplicate_scope.py::test_resend_after_suspicious_pattern_block_is_blocked_as_a_duplicate_d1` |
| Only duplicate-blocked in-window matches → not blocked (D3) | `test_duplicate_scope.py::test_story_4_row_blocked_at_23h_no_longer_keeps_prompt_blocked_at_25h_d3` |
| Boundary at 24h ± 1 minute unchanged | `test_duplicate_scope.py::test_success_at_23h59m_still_blocks_the_same_prompt`, `::test_success_at_24h01m_no_longer_blocks_the_same_prompt` |
| Whitespace sensitivity unchanged | `test_duplicate_scope.py::test_trailing_whitespace_is_a_different_prompt`; `test_dedup_key.py::test_whitespace_is_significant` |
| `dedup_key` non-NULL on every row `run_query` writes, all seven arms | `test_duplicate_scope.py::test_every_call_site_writes_the_credentials_key_and_the_raw_prompt_hash` (7 params) |
| `prompt_hash` on every new row equals `hash_prompt(prompt)` | same parametrized test (`_assert_row_keyed`); `::test_story_2_maria_at_0900_and_juan_at_0905_both_reach_the_model_with_different_keys` |
| `init_db()` converges column + index: fresh DB, pre-PRD DB, concurrent-add race; no `ALTER` when current | `test_db.py::test_init_db_adds_a_nullable_dedup_key_column`, `::test_init_db_creates_the_dedup_index_with_its_columns_in_order` (fresh); `::test_init_db_migrates_a_pre_dedup_key_database`, `::test_init_db_creates_the_dedup_index_after_adding_the_column` (pre-PRD); `::test_two_init_db_calls_racing_on_dedup_key_both_converge` (race); `::test_init_db_issues_no_alter_when_schema_is_current` |
| `dedup_key` raises `ValueError` for empty input, final non-user turn, any `tool` turn | `test_dedup_key.py::test_empty_conversation_is_refused`, `::test_final_turn_that_is_not_user_is_refused`, `::test_tool_turn_anywhere_is_refused_naming_prd_016` |
| `dedup_key(u, [user(x)])` ≠ `dedup_key(u, [user(y), assistant(z), user(x)])` | `test_dedup_key.py::test_single_turn_differs_from_multi_turn_with_same_last_turn` |

## Findings for later stories

- **STORY-009 (invariance).** `test_story_3_…`'s third-send assertion is only meaningful together with the D3 predicate. The mutation check showed that removing `was_duplicate_blocked = 0` alone leaves it green, because the success is still the earliest row. D3's teeth are in `test_story_4_row_blocked_at_23h_…`, which does fail. That is expected, and noted so nobody reads the story 3 test as the D3 guard.
- **Running the app locally.** `/implement`'s smoke test must set `DATABASE_URL` to the dev server. `.env` points at Turso, and on an empty database the app refuses to boot until a user exists (`RbacNotBootstrappedError`).

## Acceptance Criteria

- [x] Given a new `tests/test_duplicate_scope.py`, when it runs, then it has one end-to-end test per row of PRD Section 6.3's table, each driving real `POST /query` requests with bearer tokens. There are no seeded fakes, except for rows that need a backdated timestamp or a pre-PRD NULL key, plus the one documented `query:submit` seed (Deviation 2). Each test asserts both the HTTP outcome and the resulting audit rows.
- [x] Given PRD Section 5 stories 1–4 and their examples, when the module is read, then each example exists as a named test (`test_story_1_…`, `test_story_2_…`, `test_story_3_…`, `test_story_4_…` ×2).
- [x] Given two users sending the same prompt, when both succeed, then their rows carry different `dedup_key` values and the same `prompt_hash` (D5).
- [x] Given a same-user repeat after a success, when it is blocked, then the blocked row's `dedup_key` equals the success row's and `was_duplicate_blocked=1`; a third send is still `BLOCKED` with `first_query_at` = the success, not the blocked row (D3).
- [x] Given the full suite, when it runs, then everything passes (1959 passed, 25 skipped). Every Section 11 item maps to a named test (table above).
- [x] All tasks completed
- [x] No production code changed
- [x] Follows existing patterns
