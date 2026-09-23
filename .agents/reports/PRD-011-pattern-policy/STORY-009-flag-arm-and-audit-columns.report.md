---
story: STORY-009
prd: PRD-011
plan: .agents/plans/PRD-011-pattern-policy/completed/STORY-009-flag-arm-and-audit-columns.plan.md
epic_branch: epic/PRD-011-pattern-policy
commit: d18a55d
status: COMPLETE
completed: 2026-09-23
---

# Implementation Report — STORY-009: Flag arm, and pattern_role / pattern_action audit columns

**Plan**: `.agents/plans/PRD-011-pattern-policy/completed/STORY-009-flag-arm-and-audit-columns.plan.md`
**Epic Branch**: `epic/PRD-011-pattern-policy`
**Commit**: `d18a55d`

## Summary

**Two audit columns.** `audit_logs` gains `pattern_role` and `pattern_action`, both nullable `TEXT` with no default. They follow the `dedup_key` path: declared in `CREATE_AUDIT_LOGS_TABLE` and in `AUDIT_LOGS_ADDED_COLUMNS`, and carried by:

- `AuditLog`;
- `log_query` (defaulted keyword parameters);
- `insert_audit_log`;
- `_row_to_audit_log`;
- `_SUMMARY_SQL`'s hand-written `json_object`.

`init_db()` needed no new code. Rows written before PRD-011 are not backfilled, so `pattern_action IS NULL` means "block" (D6).

**The block arm** now passes `pattern_role=block.role` and `pattern_action=block.action`. Its body is byte-identical.

**The flag arm.** After the block arm, when there are flags, the pipeline writes one row for `inspection.flags[0]`, the first flag in walk order. That row has `suspicious_pattern`, `success=True`, an explicit `session_id` and a non-NULL `dedup_key`, and no response or model. Execution then continues to redaction and upstream, and that outcome writes its own row, which carries no pattern fields. A flag followed by a block leaves only the block row, because the block arm returns first.

**The duplicate lookup** now excludes flag rows (plan D-E). A flag row is `success=1`, so without this, a flagged request that then failed upstream would be refused as a duplicate on retry. A flagged request that succeeds is still found as a prior query through its own success row.

Counters, `/audit`, the admin entry and `AuditQueryEntry` are unchanged; they belong to STORY-010.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Two columns in CREATE and the added-columns mapping; two `AuditLog` fields before `id` | `app/db/models.py` | ✅ |
| 2 | Insert (22 placeholders), row mapper, `_SUMMARY_SQL` json_object, `init_db` docstring | `app/db/database.py` | ✅ |
| 3 | `find_duplicate_timestamp` excludes flag rows (D-E) | `app/db/database.py` | ✅ |
| 4 | `log_query(..., pattern_role=None, pattern_action=None)` | `app/services/audit_logger.py` | ✅ |
| 5 | Convergence, legacy-fixture migration, round-trip, batched-read, construction and lookup tests; two pinned tests updated | `tests/test_db.py` | ✅ |
| 6 | DDL column pin extended | `tests/test_migrate_to_turso_cli.py` | ✅ |
| 7 | Block arm passes role and action; flag arm | `app/services/query_pipeline.py` | ✅ |
| 8 | Flag-arm pipeline suite; the block row asserts role and action | `tests/test_query_pipeline_patterns.py` | ✅ |
| 9 | `log_query` pass-through and defaults | `tests/test_audit_logger.py` | ✅ |
| 10 | Repository sweep | — | ✅ |
| 11 | Full suite | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ |
| Frontend lint | n/a: there is no `frontend/`, and the Reflex UI is not touched |
| Tests | ✅ 2520 passed, 26 skipped, 0 failed (`pytest tests/`, 246 s; see the note on flakes below) |
| Story suites | ✅ `test_query_pipeline_patterns.py` 24, `test_db.py` + `test_audit_logger.py` + `test_migrate_to_turso_cli.py` 224 |
| Mutation checks | ✅ With the flag arm disabled, 5 flag tests fail. With the D-E predicate removed, the retry test fails. Both were restored. |
| No-change suites | ✅ `git diff` is empty for `test_query_outcomes_regression.py`, `test_chat_outcomes_regression.py`, `test_history_off_integration.py`, `test_query_router.py` and `test_integration.py` |
| E2E | ✅ 5/5 |

**Full-suite flakes, recorded rather than hidden.**

1. The first full run had 3 failures: two census counts (real, fixed by raising them to nine) and `test_pipeline_concurrency.py::test_eleventh_query_succeeds_while_ten_are_blocked`. That test asserts on wall-clock time and passed 3/3 in isolation.
2. The second run failed 2 different tests, both of which pass in isolation.
3. After restarting `harness-libsql-dev`, as the libSQL memory note advises, the third run had 2 setup ERRORs from the server itself: `Hrana: STREAM_EXPIRED: The stream has expired due to inactivity`. Both tests pass in isolation.
4. A baseline run of unmodified HEAD (story changes stashed) passed 2497/2497.
5. The final run with the story applied passed 2520/2520: the baseline plus 23 new tests.

The failing tests changed from run to run, all passed in isolation, and none touches the code this story changed. So these are attributed to the dev server under long runs, not to this story.

### E2E detail

Everything ran against the local libSQL dev server (`DATABASE_URL=http://127.0.0.1:8080`), never the `.env` database. The app was served with `uvicorn` on port 8765, using a throwaway user `e2e-story009@example.com`. Upstream TLS used an environment-only CA bundle (certifi plus the Windows root store) in the session scratchpad, as in STORY-008. Nothing in the repo changed for this.

| # | Check | Result |
|---|-------|--------|
| 1 | Convergence on a real pre-PRD-011 database. The dev DB was reset and `audit_logs` rebuilt from **HEAD's** `CREATE_AUDIT_LOGS_TABLE` (21 columns), seeded with one legacy pattern row. The app was then started. | `init_db()` brought the table to 23 columns, ending `pattern_role, pattern_action`. The legacy row reads `pattern_role=None, pattern_action=None`: not backfilled. |
| 2 | `POST /query` with `please ignore previous instructions` | `{"status":"BLOCKED","reason":"Suspicious pattern detected","pattern":"ignore previous instructions"}`, byte-identical. Row 2: `pattern_role='user'`, `pattern_action='block'`, `success=1`, non-NULL `dedup_key`. |
| 3 | `POST /query` with a clean prompt | `SUCCESS`, answered upstream (`audit_id` 3). Row 3 has both pattern columns NULL. |
| 4 | `GET /audit`, `GET /stats` | `/audit` entries have the same 14 keys and no `pattern_*` field (STORY-010). `/stats` reports `blocked_suspicious: 2`, counting the legacy NULL-action row and the block row, which is today's predicate unchanged. |
| 5 | Second boot | A second `init_db()` against the converged database, run through a statement-recording connection proxy, issued 11 statements and **no `ALTER`**. The table stayed at 23 columns. |
| — | Flag arm over HTTP | Not reachable from any ingress until PRD-014/PRD-016 (PRD Section 10). It is covered against the real database by the pipeline suite, including a `{user: flag}` profile with no bypass. |

The first uvicorn start stopped at `RbacNotBootstrappedError`, because resetting the dev DB removed every user. This is the designed behaviour. Convergence had already run at import, and check 1 was read from that start.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/db/models.py` | UPDATE | +22/-2 |
| `app/db/database.py` | UPDATE | +22/-3 |
| `app/services/audit_logger.py` | UPDATE | +7/-0 |
| `app/services/query_pipeline.py` | UPDATE | +31/-5 |
| `tests/test_db.py` | UPDATE | +245/-3 |
| `tests/test_query_pipeline_patterns.py` | UPDATE | +299/-3 |
| `tests/test_audit_logger.py` | UPDATE | +34/-0 |
| `tests/test_migrate_to_turso_cli.py` | UPDATE | +3/-1 |
| `tests/test_query_pipeline_dedup_key.py` | UPDATE | +3/-2 |
| `tests/test_query_pipeline_session_passthrough.py` | UPDATE | +3/-2 |
| `.agents/plans/.../completed/STORY-009-...plan.md` | CREATE (archived plan) | +404 |

## Deviations from Plan

1. **Two census tests the plan did not list.** `test_query_pipeline_dedup_key.py` and `test_query_pipeline_session_passthrough.py` each pin the number of `log_query` call sites in the pipeline, at 8. Their own comment says "Raise it again with the ninth". The flag arm is the ninth, and it passes both keys, so both counts were raised to 9 with a PRD-011 STORY-009 comment. The content assertions are unchanged.
2. **One extra test for AC 5.** `test_every_pattern_arm_passes_role_and_action` is a source-level census: exactly two call sites pass `suspicious_pattern=`, and both pass `pattern_role=`, `pattern_action=`, `session_id=session_id` and `dedup_key=key`. No other call site passes the pattern fields. It imports the paren-matching helper from `tests/test_query_pipeline_dedup_key.py` by name, which is a third use of it without a third copy.
3. **Legacy-fixture names.** The new fixture's docstring calls itself "the sixth" (the plan said "fifth"), because `_create_pre_history_trimmed_database` already exists as the fifth.
4. **The trace test** asserts `labels[:4] == ["duplicate", "pattern", "log_query:flag", "redact"]` in a single assertion, instead of the plan's two index comparisons. The claim is the same.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_query_pipeline_patterns.py` | `test_block_body_unchanged_with_audit_columns`, `test_tool_flag_under_code_writes_a_flag_row_and_continues`, `test_flag_arm_runs_before_redaction_and_upstream`, `test_flag_then_upstream_failure_leaves_two_rows`, `test_only_the_first_flag_in_walk_order_is_recorded`, `test_flag_then_later_user_block_writes_one_block_row`, `test_flag_arm_through_the_real_guards`, `test_flagged_request_retried_after_upstream_failure_is_not_a_duplicate`, `test_chat_profile_writes_no_flag_row`, `test_every_pattern_arm_passes_role_and_action`; extended: `test_block_writes_one_audited_row_and_never_calls_upstream` |
| `tests/test_db.py` | `test_audit_logs_added_columns_carries_nullable_pattern_role_and_action`, `test_init_db_adds_nullable_pattern_role_and_action_columns` (×2), `test_init_db_migrates_a_pre_pattern_role_database` (new fixture `_create_pre_pattern_role_database`), `test_pattern_role_and_action_default_to_none_when_not_supplied`, `test_pattern_role_and_action_round_trip`, `test_pattern_role_and_action_survive_the_batched_read`, `test_audit_log_carries_pattern_role_and_action_without_breaking_construction`, `test_duplicate_lookup_ignores_a_flag_row` (×3); updated: `test_schema_has_no_ip_or_location_column`, `test_audit_log_carries_session_id_without_breaking_construction`, `_DEDUP_LOOKUP_SQL` (drives the exact-SQL and query-plan tests) |
| `tests/test_audit_logger.py` | `test_pattern_role_and_action_persisted_when_supplied`, `test_pattern_role_and_action_default_to_none_when_omitted` |
| `tests/test_migrate_to_turso_cli.py` | `test_dest_columns_match_the_ddl` extended |

## Notes for Later Stories

- **STORY-010:** until it lands, a flag row would be counted by `count_blocked_suspicious()`, by the snapshot's `blocked_suspicious` and by `suspicious_pattern_detected`. No production request can produce one yet. The predicate the PRD gives, `pattern_action IS NULL OR pattern_action = 'block'`, is the one E2E 4 already shows the data supports.
- **STORY-012:** `_admit_tool_turns` in `tests/test_query_pipeline_patterns.py` is the seam for driving `tool`-turn injections through `run_conversation`, until PRD-016 admits them.
- **PRD-016:** when `tool` turns are admitted, delete `_admit_tool_turns` and run the tool-flag tests straight through. The D-E duplicate predicate is independent of that and stays.

## Acceptance Criteria

- [x] `pattern_role TEXT` and `pattern_action TEXT` are declared in both `CREATE_AUDIT_LOGS_TABLE` and `AUDIT_LOGS_ADDED_COLUMNS`, and `AuditLog` carries both as `Optional[str] = None`. A pre-PRD-011 database gains both on `init_db()` with no backfill (`test_init_db_migrates_a_pre_pattern_role_database`, E2E 1).
- [x] A blocking hit's row has `pattern_role` set to the matched message's role and `pattern_action='block'`. The body is byte-identical (E2E 2, `test_block_body_unchanged_with_audit_columns`).
- [x] A `tool` flag under `code` writes one step-5 row with `suspicious_pattern`, `pattern_role='tool'`, `pattern_action='flag'`, `success=True`, an explicit `session_id` and a non-NULL `dedup_key`. Execution continues: redaction runs, `call_openrouter` is called, and a second row records the success.
- [x] With several flags, only the first in walk order is recorded. A flag with a later block writes one block row, and the flag is not recorded.
- [x] The block and flag arms pass `pattern_role` and `pattern_action` explicitly, beside `session_id` and `dedup_key` (`test_every_pattern_arm_passes_role_and_action`).
- [x] All tasks completed
- [x] Full `pytest tests/` green
- [x] Backend starts without error
- [x] No assertion changed in `test_query_router.py`, `test_integration.py` or `test_query_outcomes_regression.py`. Every modified pre-existing test carries a PRD-011 comment.
- [x] Follows existing patterns (column convergence in both places; explicit `session_id`/`dedup_key` on every audited arm; module-global test seams)
