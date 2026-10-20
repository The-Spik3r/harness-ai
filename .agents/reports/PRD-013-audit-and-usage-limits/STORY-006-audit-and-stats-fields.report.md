---
story: STORY-006
prd: PRD-013
plan: .agents/plans/PRD-013-audit-and-usage-limits/completed/STORY-006-audit-and-stats-fields.plan.md
epic_branch: epic/PRD-013-audit-and-usage-limits
commit: eb77e8a
status: COMPLETE
completed: 2026-10-18
---

# Implementation Report — STORY-006: /audit entry fields and /stats token aggregates

**Plan**: `.agents/plans/PRD-013-audit-and-usage-limits/completed/STORY-006-audit-and-stats-fields.plan.md`
**Epic Branch**: `epic/PRD-013-audit-and-usage-limits`
**Commit**: `eb77e8a` (plan: `82a3923`)

## Summary

`GET /audit` entries now carry the eight PRD-013 fields: `ingress`, `message_count`, `input_tokens`, `output_tokens`, `streamed`, `has_tool_calls`, `conversation_key` and `limit_exceeded`. Each is copied straight from the `AuditLog` the router already reads. `dedup_key` is still not exposed. `GET /stats` gains `input_tokens`, `output_tokens` and `blocked_usage_limits`.

The three figures come from the same single statement. `_SUMMARY_SQL` now has thirteen columns, and the three new ones come after `top_pii_entities`. None of them takes a parameter, so the positional binding is unchanged (Risk 8). `SUMMARY_FIGURES`, `SummarySnapshot`, `_SUMMARY_DECODERS` and `_summary_figure_by_figure` each grew by the same three entries. The three new standalone reads are `sum_input_tokens()`, `sum_output_tokens()` and `count_blocked_usage_limits()`. They share module-level SQL constants with the batched statement (`COALESCE(SUM(...), 0)` and `limit_exceeded IS NOT NULL`), so the two paths cannot drift apart, and an empty table reads 0, not null.

The console's `_READS`, `READ_LABEL_*` copy and `AdminState` vars gained the same three, so `_READS` still matches `SUMMARY_FIGURES` one to one. Nothing renders them yet; that is STORY-015.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 0 | Preflight: branch, Docker and libSQL up, baseline suite, inventory sweep | — | ✅ |
| 1 | Read models: 8 `AuditQueryEntry` fields, 3 `StatsResponse` fields | `app/models/schemas.py` | ✅ |
| 2 | Thirteen-figure read: constants, 3 standalone reads, figures, properties, SQL, decoders, fallback | `app/db/database.py` | ✅ |
| 3 | Router passthrough and the three `/stats` figures; `row_limit=0` kept | `app/routers/admin.py` | ✅ |
| 4 | Console read table, copy labels and state vars | `chat_ui/chat_ui/admin_copy.py`, `admin_state.py` | ✅ |
| 5 | Story tests (17) | `tests/test_audit_stats_prd013.py` | ✅ |
| 6 | Pinned inventories grown, plus the AC 5 removed-line audit | 8 test files | ✅ |
| 7 | Four mutations, each caught | — | ✅ |
| 8 | Full suite and commit | — | ✅ |
| 9 | Report, plan archive, story and index | this file | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ |
| Frontend lint | n/a (Reflex/Python UI; no npm lint in this repo) |
| `GET /health` | ✅ `{"status":"ok"}` |
| Story tests | ✅ 17 passed |
| Touched suites | ✅ 421 passed (8 files), then 197 passed (copy and untouched-app guard) |
| Full suite | ✅ 3482 passed, 27 skipped, 0 failed; 1 setup-time error that passes alone (see below) |
| E2E | ✅ 4/4 |

**Baseline before any change** (on `a6482da`): 3464 passed, 27 skipped, and 2 setup-time errors (`test_audit_logger.py::test_empty_entity_list_stored_as_none` and `test_history_off_integration.py::test_the_response_and_the_audit_row_are_what_they_were_with_history_on`). Both pass when run alone.

Every full run on the shared libSQL dev server has shown one or two different setup-time errors, each of which passes when run alone. The final run's was `test_two_instance_smoke.py::test_two_instances_booting_on_a_pre_history_trimmed_database_converge`. This is the test-isolation problem the user's pending PRE-PRD-017 (`test-suite-db-isolation`) describes. This story did not cause it and did not change it.

**AC 5 removed-line audit**: `git diff -U0` over pre-existing tests shows exactly 9 removed lines:
- eight `== 10` → `== 13` counts (`_READS` ×3, `reads.calls` ×3, `seen`, `statements`)
- one docstring wording ("ten-figure" → "thirteen-figure")

No expected value was removed.

**Mutation results (Task 7):**

| Mutation | Caught by |
|---|---|
| M1: delete the `conversation_key=` passthrough | `test_prd013_audit_entry_carries_all_eight_fields_as_stored`, `test_prd013_a_pipeline_row_reads_back_what_story_005_wrote` |
| M2: `SUM(input_tokens)` without the COALESCE | `test_prd013_token_totals_are_zero_when_no_row_has_a_split`, `test_prd013_new_figures_are_zero_on_an_empty_table`, and 7 more, including `test_summary_snapshot_on_an_empty_database` |
| M3: a parameterized column inserted before `top_models`, its value appended to the tuple | `test_prd013_limits_still_bind_to_their_own_columns`, `test_summary_snapshot_limits_are_parameters`, and 2 more |
| M4: drop one figure-by-figure fallback read | `test_prd013_batched_read_and_fallback_agree_on_all_thirteen`, `test_summary_snapshot_isolation_names_the_one_broken_figure` |

**E2E (real servers, real libSQL dev database):**

1. `POST /query` → `GET /audit` on port 8010, run twice:
   - **Upstream-error arm.** The real OpenRouter call returned 401 because the `.env` key is rejected. The row has `ingress='query'`, `message_count=1`, a `conversation_key`, both flags `false`, `limit_exceeded=null`, null tokens (correct for this arm) and no `dedup_key`.
   - **Success arm.** The same app on port 8012, with the upstream URL pointed at a local stub returning an OpenRouter-shaped body. The row has `input_tokens=2140` and `output_tokens=312`, and every other field is as above.
2. `GET /stats` returned `input_tokens=2140`, `output_tokens=312` and `blocked_usage_limits=0`. Direct SQL against the database returned `(2140, 312, 0)`. ✅
3. The baseline app (`a6482da`, served from a `git archive` export) and the new app ran against the same database. All pre-existing `/stats` and `/audit` values were identical; only the 3 and 8 new keys were added. The baseline response had no `input_tokens`, which confirms it really was the old code. ✅
4. `reflex run`, then the admin console signed in, and Register and Summary both loaded with no fault panel and no console errors. ✅

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/db/database.py` | UPDATE | +86/-16 |
| `app/models/schemas.py` | UPDATE | +27 |
| `app/routers/admin.py` | UPDATE | +25/-5 |
| `chat_ui/chat_ui/admin_copy.py` | UPDATE | +9/-1 |
| `chat_ui/chat_ui/admin_state.py` | UPDATE | +28/-5 |
| `tests/test_audit_stats_prd013.py` | CREATE | +427 |
| `tests/test_admin_state.py` | UPDATE | +28/-7 |
| `tests/test_audit_router.py` | UPDATE | +10 |
| `tests/test_copy.py` | UPDATE | +12 |
| `tests/test_db.py` | UPDATE | +17/-1 |
| `tests/test_pii_redaction_integration.py` | UPDATE | +11 |
| `tests/test_reporting_invariance.py` | UPDATE | +8 |
| `tests/test_schemas.py` | UPDATE | +14 |
| `tests/test_stats_router.py` | UPDATE | +22/-1 |

## Deviations from Plan

1. **Copy wording.** The plan named the label `READ_LABEL_USAGE_LIMITS = "the usage-limit refusals"`. That broke the PRD-006 Section 9 no-oracle rule, which `test_admin_copy.py::test_exactly_one_refusal_constant_exists` and `test_copy.py::test_admin_copy_states_one_refusal_and_says_nothing_about_why` enforce: `GATE_REFUSED_MESSAGE` must be the only copy value containing "refus". The label is now "the usage-limit blocks", which matches "the blocked duplicates" and "the blocked patterns". A comment beside it gives the reason. The code was fixed and the tests were left alone.
2. **Inventory additions the plan's F-1 table missed:**
   - `test_copy.py`'s constant census. It is one of the suites allowed to grow, and `test_untouched_app.py` only checks that no test function disappears from it.
   - Two more `len(reads.calls) == 10` sites in `test_admin_state.py` (lines 1066 and 1765).
   - `_populate` and `_loaded_record` in `test_admin_state.py`. These were optional additive extensions, so the sign-out and failed-load tests now cover the new vars.
   - Task 0's sweep found all of these except the copy census, which the full suite caught.
3. **Mutation M3 replaced.** The plan's M3, moving the parameterless columns before `top_models`, can't misbind anything, because `?` placeholders bind in SQL text order, not by column position. The run used the actual Risk 8 failure instead: a column with a `?` inserted mid-statement while its value is appended to the end of the tuple.
4. **Local test seed.** The plan suggested importing `_seed_summary_fixture` and `_individually` from `tests/test_db.py`. The suite convention (`tests/test_audit_session_id.py`'s docstring) is to copy rather than import across suites, so both are local to the new file.
5. **E2E environment:**
   - The real OpenRouter key returns 401, so the live success arm used a local upstream stub (`scratchpad/e2e_stub_launcher.py`). It overrides `_API_URL` in-process and does not change the codebase.
   - The console E2E ran with a throwaway `ADMIN_TOKEN` exported only into the Reflex process, so the real token never left `.env`.
   - The dev database is the one the test suite resets. It now holds the E2E user `e2e-story006` and two audit rows, and the next test run will drop them.
   - `reflex run` changed `chat_ui/reflex.lock/package.json` and created `package-lock.json`. Both were reverted and are not in the commit.
6. **Working tree.** The unrelated `pre-prds/` changes (README edit and the untracked PRE-PRD-017) were stashed for the run, as the user chose. They were restored after the story's commits.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_audit_stats_prd013.py` | `test_prd013_audit_entry_carries_all_eight_fields_as_stored`, `test_prd013_pre_prd_row_reports_null_fields_and_false_flags`, `test_prd013_a_pipeline_row_reads_back_what_story_005_wrote`, `test_prd013_token_totals_sum_with_null_as_zero`, `test_prd013_token_totals_are_zero_when_no_row_has_a_split`, `test_prd013_new_figures_are_zero_on_an_empty_table`, `test_prd013_blocked_usage_limits_counts_rows_naming_a_limit`, `test_prd013_blocked_usage_limits_is_zero_until_a_refusal_is_written`, `test_prd013_stats_reports_the_batched_figures_unchanged`, `test_prd013_summary_figures_are_the_ten_plus_three_in_order`, `test_prd013_batched_read_and_fallback_agree_on_all_thirteen`, `test_prd013_new_figures_have_the_standalone_type`, `test_prd013_snapshot_still_partitions_the_thirteen_exactly`, `test_prd013_limits_still_bind_to_their_own_columns`, `test_prd013_one_bad_new_figure_fails_alone_and_stats_still_500s`, `test_prd013_console_read_table_matches_summary_figures`, `test_prd013_console_state_declares_the_three_figures_with_zero_defaults` |

## Acceptance Criteria

- [x] Given rows written by STORY-005, when `GET /audit` is called, then each entry carries the eight fields as stored. Tested on hand-written rows and on a row written by `POST /query`, and confirmed in the E2E.
- [x] Given a row written before this PRD, when `GET /audit` returns it, then the six nullable fields are `null` and the two flags are `false`.
- [x] `GET /stats` `input_tokens` and `output_tokens` equal `SUM` with NULL as 0, and `blocked_usage_limits` equals the count of rows where `limit_exceeded IS NOT NULL`, which is 0 today. Checked against direct SQL in both the tests and the E2E.
- [x] The batched read and the figure-by-figure fallback agree on all thirteen figures, and `SummarySnapshot` still partitions `SUMMARY_FIGURES` exactly.
- [x] Existing `/audit` and `/stats` tests pass, and every pre-existing response field keeps its value. Inventory assertions were extended, as in the STORY-002 F-2 precedent, and no value assertion changed. The E2E diff against `a6482da` confirms the values are identical.
- [x] All tasks completed
- [x] Backend server starts without error
- [x] Follows existing patterns
