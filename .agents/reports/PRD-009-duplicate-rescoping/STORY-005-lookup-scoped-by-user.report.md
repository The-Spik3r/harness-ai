---
story: STORY-005
prd: PRD-009
plan: .agents/plans/PRD-009-duplicate-rescoping/completed/STORY-005-lookup-scoped-by-user.plan.md
epic_branch: epic/PRD-009-duplicate-rescoping
commit: 3d0c86b
status: COMPLETE
completed: 2026-09-17
---

# Implementation Report — STORY-005: Duplicate lookup scoped by the authenticated user_id

**Plan**: `.agents/plans/PRD-009-duplicate-rescoping/completed/STORY-005-lookup-scoped-by-user.plan.md`
**Epic Branch**: `epic/PRD-009-duplicate-rescoping`
**Commit**: `3d0c86b`

## Summary

The duplicate lookup is now per caller. `find_duplicate_timestamp` became `(user_id, prompt_hash, since)` and adds `user_id = ?` to its `WHERE` clause. `check_duplicate` became `(user_id, prompt)`, and `run_query` passes `identity.user_id`, the id resolved from the bearer credential. STORY-004's flag predicates, `ORDER BY timestamp ASC LIMIT 1` and the storage-error path are unchanged. The lookup still matches on `prompt_hash` until STORY-007.

Test changes:
- **Contract test:** re-pinned to `["user_id", "prompt"]`.
- **Spies:** the three `check_duplicate` spies changed their wrapper signature only (two lines each).
- **Characterization test:** the STORY-001 cross-user test is flipped in place.
- **Checker tests:** they pass the seeded user explicitly and gain different-user coverage.

Three pre-existing tests that relied on the global scope with different users were reasoned about one at a time and re-pointed at a single user.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Scope the lookup by `user_id` | `app/db/database.py` | ✅ |
| 2 | `check_duplicate(user_id, prompt)`; pipeline passes `identity.user_id` positionally | `app/services/duplicate_checker.py`, `app/services/query_pipeline.py` | ✅ |
| 3 | Re-pin contract test; adapt three spy wrapper signatures | `tests/test_pii_dedup_isolation.py`, `tests/test_query_router.py`, `tests/test_query_pipeline_authorization.py` | ✅ |
| 4 | Flip cross-user characterization in place; update module docstring | `tests/test_duplicate_characterization.py` | ✅ |
| 5 | Seeded user passed explicitly; different-user store tests; two-user `run_query` test | `tests/test_duplicate_checker.py` | ✅ |
| 6 | PII dedup tests re-pointed at one sender | `tests/test_pii_dedup_isolation.py` | ✅ |
| 7 | `query:submit` denial test keeps one `user_id` across a role change | `tests/test_duplicate_checker.py` | ✅ |
| 8 | Regression, unmodified-file checks, call-site grep, full suite | — | ✅ (see Validation) |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ |
| Frontend lint | N/A: no frontend change, and no linter is configured |
| `duplicate_checker.py:28` still `prompt_hash = hash_prompt(prompt)` | ✅ |
| After Tasks 1–3 | ✅ Only `test_identical_pii_prompt_is_still_blocked_as_duplicate` failed, as the plan predicted |
| Spy diffs | ✅ Only the `def` + `return` lines per spy |
| `test_duplicate_characterization.py` diff | ✅ Hunks only in the module docstring and the cross-user test |
| Tests are real: `user_id = ?` removed temporarily | ✅ All 3 new checker tests and the flipped characterization test failed |
| Tests are real: hashing redacted text on both sides | ✅ `test_distinct_pii_prompts_are_never_duplicates_of_each_other` failed |
| Tests are real: `denied_permission IS NULL` removed temporarily | ✅ `test_retry_after_missing_submit_permission_denial_reaches_model` failed |
| `test_query_outcomes_regression.py` + `test_integration.py` | ✅ 21 passed, and `git diff --stat` is empty |
| Smoke, chat state, session passthrough, dedup key, db, audit session id | ✅ 355 passed, no edits |
| Call-site grep | ✅ Every `check_duplicate` / `find_duplicate_timestamp` call passes a user id |
| Full suite `pytest tests/ -q` | ⚠️ 1910 passed, 25 skipped, 2 failed before commit; after commit, 1 failure remains, pre-existing. See Deviations. |
| E2E | ✅ 5/5 (28 tests run verbosely) |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/db/database.py` | UPDATE | +7/-4 |
| `app/services/duplicate_checker.py` | UPDATE | +2/-2 |
| `app/services/query_pipeline.py` | UPDATE | +4/-1 |
| `tests/test_duplicate_characterization.py` | UPDATE | +30/-12 |
| `tests/test_duplicate_checker.py` | UPDATE | +86/-21 |
| `tests/test_pii_dedup_isolation.py` | UPDATE | +16/-9 |
| `tests/test_query_pipeline_authorization.py` | UPDATE | +2/-2 |
| `tests/test_query_router.py` | UPDATE | +2/-2 |
| `.agents/plans/PRD-009-duplicate-rescoping/completed/STORY-005-lookup-scoped-by-user.plan.md` | CREATE (archived) | +383 |

## Deviations from Plan

1. **Task 5's vacuity check removed only the predicate.** The plan said to `git stash` the three app files. After Task 5, though, every test passes a `user_id`, so the old code would make *all* tests fail with a `TypeError`, which proves nothing. The check instead removed only `user_id = ?` and its bound parameter, keeping the new signature. That isolates the behaviour: exactly the 3 new checker tests and the flipped characterization test failed.
2. **Task 6's vacuity check simulated redacted hashing on both sides.** The plan suggested substituting the redacted hash inside `check_duplicate` only. That passed trivially, because `audit_logger` still stored raw hashes, so nothing could match at all. The faithful simulation temporarily redacted e-mail addresses inside `hash_prompt` itself, which both the lookup and the audit logger use. Under that simulation the same-sender distinct test fails, so it proves raw-text hashing again.
3. **`test_audit_prompt_hashes_are_over_raw_text_not_redacted` was left with María as the second sender.** The plan didn't list it. It sends a *different* prompt as María and asserts stored `prompt_hash` values, never a dedup verdict, so per-user scope can't change what it proves. No edit.
4. **`juan_at` stays in the flipped characterization test.** It is no longer asserted against, because timestamps have one-second resolution and could coincide with `maria_at`. It stays next to the cited "was BLOCKED with first_query_at = juan_at" comment. The "not the other user's timestamp" proof lives in `test_same_prompt_from_two_users_reaches_model_and_each_is_blocked_only_by_their_own_success`, with a row seeded at −3h.
5. **Two full-suite failures, neither a product regression:**
   - **`tests/test_query_session_id.py::test_the_three_pinned_suites_are_unmodified_in_the_working_tree`.** This PRD-008 guard fails while `tests/test_query_router.py` has *uncommitted* changes, because it reads only `git diff` and `git diff --cached`. The spy-signature edit there is required by PRD-009 Section 6.5 and this story's AC 3. The guard passes once the change is committed (re-run after `3d0c86b`: 1 passed).
   - **`tests/test_pii_redaction_integration.py::test_no_pre_epic_test_function_was_removed_or_renamed`.** This failure is pre-existing and was not fixed here (out of scope). It fails on a clean HEAD with this story's changes stashed. The cause is already recorded in the STORY-004 report: `subprocess.run(..., text=True)` decodes `git show` output with cp1252, and `tests/reports_fixture.py` contains the UTF-8 byte `0x9d`.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_duplicate_checker.py` (new) | `test_row_from_a_different_user_is_not_a_prior_query`, `test_own_row_is_found_when_another_users_row_is_earlier`, `test_same_prompt_from_two_users_reaches_model_and_each_is_blocked_only_by_their_own_success` |
| `tests/test_duplicate_checker.py` (updated) | 15 existing `check_duplicate` calls pass `_SEEDED_USER`; `_seed_row` accepts a `user_id` override; `test_retry_after_missing_submit_permission_denial_reaches_model` uses one `user_id` across two roles |
| `tests/test_duplicate_characterization.py` (flipped) | `test_pre_prd009_row_from_one_user_blocks_same_prompt_from_another_user`: María now gets `SUCCESS` (model called twice), and her resend gets `BLOCKED` against her own row |
| `tests/test_pii_dedup_isolation.py` (updated) | `test_check_duplicate_public_contract_is_stable` (re-pinned); `test_identical_pii_prompt_is_still_blocked_as_duplicate` and `test_distinct_pii_prompts_are_never_duplicates_of_each_other` (same sender); `test_pipeline_runs_both_checks_before_any_redaction` (spy signature) |
| `tests/test_query_router.py`, `tests/test_query_pipeline_authorization.py` | Spy wrapper signature only |

## Acceptance Criteria

- [x] `find_duplicate_timestamp(user_id: str, prompt_hash: str, since: str)` and `check_duplicate(user_id: str, prompt: str)`: the lookup adds `user_id = ?`, and `run_query` passes `identity.user_id`, the credential-resolved id and never the body's. The router's 403 on a mismatch is still pinned by `test_body_user_id_mismatch_returns_403_without_overriding`.
- [x] If María has a successful send, Juan's identical send reaches the model. Juan's resend is `BLOCKED` with `first_query_at` equal to his own success, and `!=` María's seeded timestamp.
- [x] The contract test pins `["user_id", "prompt"]` (both `str`, no defaults), with a comment citing PRD-009 Section 6.5 and STORY-007's `prompt -> key` swap. The three spies change their wrapper signature only, and every assertion is unchanged.
- [x] The STORY-001 cross-user characterization test is flipped in place, citing PRD-009 T1/T2 and STORY-005.
- [x] `tests/test_query_outcomes_regression.py` and `tests/test_integration.py` pass unmodified.
- [x] Reliance on the global scope with different users was reasoned about per test (Tasks 6–7, Deviation 3), not bulk-edited.
- [x] All tasks completed.
- [~] Full test suite green, except one pre-existing, environment-only failure (Deviation 5).
- [x] Follows existing patterns.
