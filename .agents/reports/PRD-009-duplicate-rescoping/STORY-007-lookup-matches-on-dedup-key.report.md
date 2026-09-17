---
story: STORY-007
prd: PRD-009
plan: .agents/plans/PRD-009-duplicate-rescoping/completed/STORY-007-lookup-matches-on-dedup-key.plan.md
epic_branch: epic/PRD-009-duplicate-rescoping
commit: c734df9
status: COMPLETE
completed: 2026-09-17
---

# Implementation Report — STORY-007: check_duplicate(user_id, key) and the lookup match on dedup_key, with the pinned contract tests updated

**Plan**: `.agents/plans/PRD-009-duplicate-rescoping/completed/STORY-007-lookup-matches-on-dedup-key.plan.md`
**Epic Branch**: `epic/PRD-009-duplicate-rescoping`
**Commit**: `c734df9`

## Summary

The duplicate control now checks the key rather than the prompt text.

**Lookup.** `find_duplicate_timestamp(user_id, dedup_key, since)` runs PRD Section 6.3's SQL exactly:
- `WHERE user_id = ? AND dedup_key = ? AND timestamp >= ?`
- `AND success = 1 AND was_duplicate_blocked = 0 AND denied_permission IS NULL`
- `ORDER BY timestamp ASC LIMIT 1`

The string `prompt_hash` no longer appears in the function, including its comment.

**`check_duplicate(user_id, key)`.** It no longer hashes anything. Its `StorageError -> DuplicateCheckError("Duplicate lookup failed: ...")` translation is unchanged, so the router's 500 is unchanged. The parameter is named `key`, not `dedup_key`, so it does not shadow the module's `dedup_key()` function.

**`run_query`.** It passes the `key` it already derives once, before authorization (STORY-006).

**Unchanged:** `prompt_hash` is still written and still means `sha256(prompt)`; the control just no longer reads it (D5). A pre-PRD row has a NULL `dedup_key`, and `NULL = ?` is never true, so it never matches (D6). That needed no code, only the pinning tests named for Risk 3.

**Test changes (Section 6.5):** every contract test was updated in place with a PRD-009 citation. The seed helpers that relied on `prompt_hash` matching now also write the key. No outcome assertion changed.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Contract pin `["user_id", "key"]`; census back to `duplicate_checker.py: 1`; raw-text sequence drops `check_duplicate`'s entry; spy signature (red first) | `tests/test_pii_dedup_isolation.py` | ✅ |
| 2 | Re-seed every lookup case with `user_id` + `dedup_key`; add D5 and D6/Risk 3 cases (red first) | `tests/test_duplicate_checker.py` | ✅ |
| 3 | Lookup matches on `dedup_key` | `app/db/database.py` | ✅ |
| 4 | `check_duplicate(user_id, key)`, no hashing | `app/services/duplicate_checker.py` | ✅ |
| 5 | Pipeline passes `key` | `app/services/query_pipeline.py` | ✅ |
| 6 | Remaining spies: signature only | `tests/test_query_router.py`, `tests/test_query_pipeline_authorization.py` | ✅ |
| 7 | Seed helpers carry the key | `tests/test_query_router.py`, `tests/test_chat_state.py`, `tests/test_duplicate_characterization.py` | ✅ |
| 8 | Index-plan test tied to the function's real SQL | `tests/test_db.py` | ✅ |
| 9 | Stale docstrings/comments | `tests/test_audit_session_id.py`, `tests/test_query_pipeline_dedup_key.py` | ✅ |
| 10 | Full suite, untouched-file diff, residual grep | — | ✅ (see Validation) |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`python -c "from app.main import app"`) | ✅ OK |
| Frontend lint | N/A (no `frontend/`; no UI change) |
| Red before green | ✅ After Tasks 1–2 on unchanged production code: 3 contract failures and 9 lookup failures, including the Risk 3 `run_query` test, which got `BLOCKED` from the old `prompt_hash` lookup. So the new tests pin a real change. |
| Dedup core (`test_duplicate_checker`, `test_pii_dedup_isolation`, `test_dedup_key`, `test_query_pipeline_dedup_key`) | ✅ 83 passed |
| Router, authorization, chat state, characterization | ✅ 188 passed |
| `test_db.py -k "dedup or duplicate or uses_the_index"` | ✅ 24 passed |
| `git diff` on `test_integration.py`, `test_query_outcomes_regression.py`, `test_two_instance_smoke.py` | ✅ empty |
| Removed lines in `test_query_router.py` / `test_chat_state.py` / `test_query_pipeline_authorization.py` | ✅ only imports and the three spy signature/body lines. No assertion line removed. |
| Residual grep (`check_duplicate(...prompt)`, `until STORY-007`, `Still matches on prompt_hash`) | ✅ none |
| Full suite `pytest -q` (pre-commit) | ⚠️ 1930 passed, 25 skipped, 2 failed, 1 error. None is caused by this story; see below. |
| Post-commit re-run of the two story-related items | ✅ `test_the_three_pinned_suites_are_unmodified_in_the_working_tree` + `tests/test_summary.py`: 64 passed |
| E2E (test checklist) | ✅ 25/25 |
| E2E (live `uvicorn`) | ✅ 7/7 |

**The three full-suite items:**
1. **`tests/test_query_session_id.py::test_the_three_pinned_suites_are_unmodified_in_the_working_tree`.**
   - This PRD-008 guard fails while `tests/test_query_router.py` has *uncommitted* edits.
   - Section 6.5 requires this story to edit that file (the spy and the seed helper), and STORY-005 did the same.
   - It passes on the committed tree (re-run above).
2. **`tests/test_pii_redaction_integration.py::test_no_pre_epic_test_function_was_removed_or_renamed`.** This is a pre-existing Windows-environment failure, already recorded in STORY-006's report.
   - `git show` output for `tests/reports_fixture.py` is decoded as `cp1252` and hits byte `0x9d`.
   - I reproduced the same failure in a clean detached worktree at `daf9878` (before this story), then removed the worktree.
3. **`tests/test_summary.py::test_every_figure_var_reaches_the_sheet[blocked_figures]` (error).** This looks flaky: it passed on an isolated re-run and again after the commit. No file it touches is in this diff.

## E2E

**Test checklist (plan's E2E section), 25 passed:**
- `test_integration.py::test_duplicate_query_blocked_and_openrouter_never_called` (unmodified)
- all of `test_query_outcomes_regression.py` (six outcomes, unmodified)
- the three new Risk 3 / D5 tests
- `test_duplicate_check_storage_failure_returns_500`
- `test_duplicate_sent_via_chat_blocks_identical_prompt_via_api`
- both `test_db` plan/SQL tests
- all of `test_two_instance_smoke.py` (unmodified)

**Live app.** Real `uvicorn app.main:app` against the local libSQL dev server (`http://127.0.0.1:8080`), not the `.env` Turso database. `HTTPS_PROXY` pointed at a dead local port, so no prompt left the machine. A 502 therefore means "passed the duplicate check and reached the model call".

| Check | Result |
|-------|--------|
| `GET /health` | ✅ 200 |
| Same prompt twice, both upstream failures | ✅ 502 then 502 (retry not held) |
| Those rows' `dedup_key` equals `dedup_key(user, [user: prompt])` | ✅ 2/2 |
| Keyed same-user success seeded 2h ago | ✅ 200 `{"status":"BLOCKED","reason":"Duplicate query within 24 hours","first_query_at":<seeded>}` |
| NULL-key pre-PRD success seeded 2h ago (Risk 3) | ✅ 502, reached the model call |
| Another user's keyed success | ✅ 502, reached the model call |
| Same `prompt_hash`, different key (D5) | ✅ 502, reached the model call |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/db/database.py` | UPDATE | +8/-4 |
| `app/services/duplicate_checker.py` | UPDATE | +4/-3 |
| `app/services/query_pipeline.py` | UPDATE | +3/-2 |
| `tests/test_duplicate_checker.py` | UPDATE | +119/-62 |
| `tests/test_pii_dedup_isolation.py` | UPDATE | +41/-19 |
| `tests/test_db.py` | UPDATE | +35/-9 |
| `tests/test_query_router.py` | UPDATE | +26/-4 |
| `tests/test_duplicate_characterization.py` | UPDATE | +18/-2 |
| `tests/test_chat_state.py` | UPDATE | +17/-1 |
| `tests/test_audit_session_id.py` | UPDATE | +5/-4 |
| `tests/test_query_pipeline_authorization.py` | UPDATE | +5/-3 |
| `tests/test_query_pipeline_dedup_key.py` | UPDATE | +4/-4 |
| `.agents/plans/PRD-009-duplicate-rescoping/completed/STORY-007-lookup-matches-on-dedup-key.plan.md` | CREATE (archived) | +366 |

## Deviations from Plan

1. **Spy key-to-prompt mapping uses `.get(key, key)`.** An unmapped key is recorded as itself, so the unchanged assertion fails with a readable diff. The alternative, a `KeyError` inside the pipeline, would surface as an unrelated 500.
2. **`_seed_row` in `test_duplicate_checker.py` uses `setdefault` for `prompt_hash` and `dedup_key`.** The D5 and D6 cases override one column (`prompt_hash="unrelated"`, `dedup_key=None`, or another prompt's key) without a second helper.
3. **`test_chat_state.py` needed the local `_Turn`/`_key` helper, not just the import.** It uses `@dataclasses.dataclass` to match that module's existing `import dataclasses` style. The first scripted pass missed this; it was caught by collection/runtime and fixed before any green run was counted.
4. **The lookup's new comment avoids the literal `prompt_hash`** ("the evidence column"). The new `test_find_duplicate_timestamp_sql_is_the_planned_shape` can then assert the string is absent from the whole function source, which is AC 1's wording.
5. **Live E2E added beyond the plan's list.** The `/implement` hard gate requires starting the app. The plan's checklist tests use `TestClient` or pipe-driven children, so a real `uvicorn` run was added (see E2E).

## Findings for later stories

- **`test_two_instance_smoke.py::test_a_prompt_outside_the_window_is_not_blocked_by_the_other_instance` no longer tests the window.** `do_plant_audit_row` plants a NULL-key row, which can never match whatever its age. PRD Section 11 requires the file to pass *unmodified*, so it was left alone.
  - For STORY-009 (invariance pass) to decide.
  - The 24h boundary itself is still pinned by `test_boundary_just_inside_24h` / `test_boundary_just_outside_24h` on keyed rows.
- **`test_duplicate_sent_via_chat_blocks_identical_prompt_via_api` and `test_query_pipeline_session_passthrough.py:150-181` rely on the single-turn key ignoring `session_id`.** That is correct for PRD-009. PRD-010 must expect them to change when chat starts keying on real turns.
- **`.env.example`:** no setting was added or read by this story (STORY-010 confirms it formally).

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_duplicate_checker.py` | `test_lookup_matches_on_dedup_key_not_prompt_hash`, `test_same_prompt_hash_with_a_different_key_is_not_a_prior_query`, `test_pre_prd009_row_with_null_dedup_key_is_not_a_prior_query_risk_3`, `test_pre_prd009_row_does_not_block_the_same_prompt_through_run_query_risk_3`; all 17 existing lookup cases re-seeded on the key; whitespace case also asserts distinct keys |
| `tests/test_db.py` | `test_find_duplicate_timestamp_sql_is_the_planned_shape` (new); `test_dedup_lookup_shape_uses_the_dedup_index` now also calls the real function |
| `tests/test_pii_dedup_isolation.py` | contract, census and raw-text sequence updated (Section 6.5) |

## Acceptance Criteria

- [x] `find_duplicate_timestamp(user_id: str, dedup_key: str, since: str)`: SQL is exactly Section 6.3's, and `prompt_hash` no longer appears in it. Pinned by `test_find_duplicate_timestamp_sql_is_the_planned_shape`.
- [x] `check_duplicate(user_id: str, key: str) -> DuplicateCheckResult`; `run_query` passes the STORY-006 key. `check_duplicate` does not call `hash_prompt` (census = 1), and it still raises `DuplicateCheckError` on `StorageError` (`test_malformed_db_raises_duplicate_check_error`, `test_duplicate_check_storage_failure_returns_500`).
- [x] `EXPLAIN QUERY PLAN` on the lookup uses `idx_audit_logs_dedup` with no `SCAN`, following `test_find_user_by_token_hash_uses_the_index`.
- [x] Section 6.5 contract tests updated in place with PRD-009 citations:
  - signature pin `["user_id", "key"]`
  - census `duplicate_checker.py: 1`
  - raw-text sequence drops the second `duplicate_checker` entry
  - spies adapt signature only
  - `test_duplicate_checker.py` re-seeded, all window/boundary/whitespace/earliest cases kept
  - `test_audit_session_id.py` docstring corrected
- [x] A pre-PRD NULL-key row for the same user and prompt within 24h does not block, and the send reaches the model (D6, T8). Pinned by the two `..._risk_3` tests and the live E2E. The regression module and `test_integration.py` are unmodified, and no assertion in `test_query_router.py` changed.
- [x] All tasks completed
- [x] Full suite passes, apart from the pre-existing Windows `cp1252` failure (reproduced at `daf9878`) and one flaky error
- [x] Follows existing patterns
