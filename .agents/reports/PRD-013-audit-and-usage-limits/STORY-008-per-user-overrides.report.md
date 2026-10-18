---
story: STORY-008
prd: PRD-013
plan: .agents/plans/PRD-013-audit-and-usage-limits/completed/STORY-008-per-user-overrides.plan.md
epic_branch: epic/PRD-013-audit-and-usage-limits
commit: 162820c
status: COMPLETE
completed: 2026-10-18
---

# Implementation Report — STORY-008: Per-user limit overrides: users columns, Identity fields and manage_users set-limits

**Plan**: `.agents/plans/PRD-013-audit-and-usage-limits/completed/STORY-008-per-user-overrides.plan.md`
**Epic Branch**: `epic/PRD-013-audit-and-usage-limits`
**Commit**: `162820c` (plan committed separately as `5168c48`)

## Summary

`users` gains two nullable INTEGER columns with no default: `token_budget_daily` and `requests_per_minute`. NULL means "use the role's limit" (PRD Section 6.6), which is the true value for every user that existed before this story.

- **Schema.** Both columns are declared in `CREATE_USERS_TABLE` and in a new `USERS_ADDED_COLUMNS` mapping. `init_db()` converges them with a third `_add_missing_columns` pass, placed after `CREATE_USERS_TABLE` for the same reason the `chat_messages` pass sits after its CREATE.
- **User.** `User` gains both fields, declared after `created_at` so positional construction keeps working, and `_row_to_user` maps them.
- **`set_user_limits(user_id, *, token_budget_daily=..., requests_per_minute=...)`.** It writes only the columns passed. A private `_UNCHANGED` sentinel separates "leave alone" from `None`, which writes NULL. Passing no column raises `ValueError`. An unknown user returns `False`.
- **Identity.** `Identity` stays frozen and gains `break_glass: bool = False`, `token_budget_daily` and `requests_per_minute`. Only `resolve()` sets them. `break_glass=True` is set on the `ADMIN_TOKEN` path only. The overrides come from the row `find_user_by_token_hash` already reads, so there is no extra round trip.
- **CLI.** `scripts/manage_users.py set-limits --user-id … [--token-budget N|default] [--requests-per-minute N|default]`. Values are parsed by an argparse `type`, so a bad one fails before `init_db()` and nothing is written. An omitted flag is `argparse.SUPPRESS`, so its column is left alone. `list-users` appends both limits, printing `default` for NULL.

Nothing reads the new `Identity` fields yet; STORY-010 and STORY-013 do.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 0 | Baseline of the four target test files: 272 passed | — | ✅ |
| 1 | Two columns in `CREATE_USERS_TABLE`, `USERS_ADDED_COLUMNS`, two `User` fields | `app/db/models.py` | ✅ |
| 2 | Third convergence pass after `CREATE_USERS_TABLE`; `init_db` docstring; `_row_to_user` | `app/db/database.py` | ✅ |
| 3 | `_UNCHANGED` sentinel and `set_user_limits()` | `app/db/database.py` | ✅ |
| 4 | Three `Identity` fields; `resolve()` sets them | `app/services/identity.py` | ✅ |
| 5 | `set-limits` subcommand, `_limit_value`, `_limit_text`; `list-users` limits | `scripts/manage_users.py` | ✅ |
| 6 | Tests (40 new; 3 updated admin assertions; 3 schema pins updated) | `tests/…` | ✅ |
| 7 | Full suite and the reader grep | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ |
| Frontend lint | N/A. The repo has no `frontend/` and no lint configuration; the UI is Reflex (Python) and was not touched |
| Four target files (`test_db`, `test_identity`, `test_manage_users_cli`, `test_migrate_to_turso_cli`) | ✅ 312 passed (272 + 40) |
| Full suite | ✅ 3561 passed, 27 skipped, plus one setup ERROR that is infrastructure (see Deviation 4) |
| Health check (`GET /health`) | ✅ `{"status":"ok"}` (uvicorn on port 8765, then stopped) |
| E2E | ✅ 5/5 |

E2E detail, run with the CLI against the local libSQL dev server (`http://127.0.0.1:8080`):

1. `create-user dana` then `set-limits --user-id dana --token-budget 5000000` exits 0. `list-users` prints `dana user True … 5000000 default`.
2. `--requests-per-minute 30`, then `--token-budget default`. `list-users` prints `… default 30`.
3. `--token-budget 0` exits 2 with "must be at least 1 or 'default', got 0". `--token-budget abc` exits 2 with "expected a whole number of at least 1 or 'default', got 'abc'". `--user-id ghost` exits 1 with "Error: no user with user_id 'ghost'." `list-users` is unchanged afterwards.
4. `users` was rebuilt in its five-column pre-story shape with two rows, one active and one revoked. `list-users`, which runs `init_db()`, added both columns, and both rows print `default default` with every other field intact.
5. `resolve(settings.ADMIN_TOKEN)` returns `break_glass=True, token_budget_daily=None, requests_per_minute=None`.

The reader grep (`token_budget_daily|requests_per_minute|break_glass` over `app chat_ui scripts`) matches only `models.py`, `database.py`, `identity.py`, `manage_users.py`, and `config.py` (STORY-007's `BREAK_GLASS_INGRESSES`). No pipeline code reads the fields.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/db/models.py` | UPDATE | +29/-1 |
| `app/db/database.py` | UPDATE | +52/-0 |
| `app/services/identity.py` | UPDATE | +25/-2 |
| `scripts/manage_users.py` | UPDATE | +85/-1 |
| `tests/test_db.py` | UPDATE | +270/-5 |
| `tests/test_identity.py` | UPDATE | +71/-4 |
| `tests/test_manage_users_cli.py` | UPDATE | +129/-1 |
| `tests/test_migrate_to_turso_cli.py` | UPDATE | +2/-0 |
| `tests/test_two_instance_smoke.py` | UPDATE | +4/-0 |

## Deviations from Plan

1. **Two more schema pins than the plan listed.** The plan expected `test_migrate_to_turso_cli.py:179` to need updating. Two more tests also pin the five-column `users` shape:
   - `tests/test_db.py::test_users_schema_matches_expected_columns` asserted NOT NULL on *every* column. It now names seven columns, asserts NOT NULL on the original five only, and asserts the new two are nullable with no default.
   - `tests/test_two_instance_smoke.py::test_both_instances_boot_simultaneously_against_one_database` compared the sorted `users` columns. It now lists seven, so it also proves the third pass converges when two instances boot at once.
2. **The E2E database was the local dev server, not `file:./tmp_s008.db`.** `app/config.py` rejects `file:` URLs (PRD-007). `DATABASE_URL=http://127.0.0.1:8080` was passed explicitly. That is the server the suite's `_reset_database` drops between tests, and `.env` points at it too, so nothing durable lived there. The two leftover E2E rows were deleted afterwards.
3. **The "neither flag" check sits in `_set_limits`, via `args.subparser.error(...)`.** The plan left the placement open. The subparser is stored with `set_defaults(subparser=...)`, so the check exits 2 with the subcommand's usage line and stays reachable through `main()`.
4. **The working tree was not clean at the gate (Phase 2.1).** `pre-prds/README.md` (modified) and `pre-prds/PRE-PRD-017-test-suite-db-isolation.md` (untracked) were present. This time they were not stashed. They were left untouched and every commit staged explicit paths, so neither is in any STORY-008 commit. Both are still in the working tree as they were.
5. **The full suite needed a rerun.** The first full run had 2 failures:
   - The `users` schema pin in the smoke test (Deviation 1).
   - `test_chat_state.py::test_run_query_openrouter_error_raises_and_logs_failure`, which failed with libSQL `STREAM_EXPIRED` during an `audit_logs` insert.

   The second full run had 3561 passed and 1 setup ERROR: a TCP connect timeout to the dev server in `test_db.py::test_chat_sessions_key_columns_declare_not_null_explicitly`. Both transient tests pass when run alone, and neither touches this story's code. That flakiness is the subject of the untracked PRE-PRD-017.
6. **Docker Desktop and the libSQL dev container were started.** The suite needs `harness-libsql-dev`, which `tests/conftest.py` names and pins by digest. It was not running, so it was started; it is still running.
7. **Commit message amended once, before anything else built on it.** "Four tests" was corrected to "Three tests". The SHA moved from `61c0ea2` to `162820c`. Nothing was pushed.

## Findings for later stories

- **F-1 (STORY-010).** `limits_for(identity)` can read `identity.token_budget_daily` and `identity.requests_per_minute` directly, with `None` meaning "fall through to the role's entry". There is no `unlimited` override value. PRD 6.6 puts `unlimited` in the role settings only, and `set-limits` rejects it.
- **F-2 (STORY-013).** `identity.break_glass` is the flag to branch on. A `role="admin"` user token is `break_glass=False` (tested), and `Identity("admin", "admin")` built directly in tests is also `False`, which matches the fail-closed note in PRD 6.8.
- **F-3 (STORY-016).** `list_users()` already returns both overrides, so the Usage view can show "override vs role default" without another query.
- **F-4 (STORY-018).** The README's `manage_users.py` section does not document `set-limits` yet.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_db.py` | `test_users_added_columns_carries_two_nullable_limits`, `test_every_users_added_column_is_also_declared_in_the_create`, `test_users_added_columns_declaring_not_null_also_declare_a_default`, `test_user_carries_limit_overrides_without_breaking_construction`, `test_init_db_migrates_a_pre_user_limits_database`, `test_init_db_adds_the_user_limit_columns_after_creating_the_table`, `test_init_db_adds_no_user_limit_alter_to_a_fresh_database`, `test_set_user_limits_sets_one_column_and_leaves_the_other`, `test_set_user_limits_none_clears_to_null`, `test_set_user_limits_sets_both_in_one_call`, `test_set_user_limits_unknown_user_returns_false_and_writes_nothing`, `test_set_user_limits_with_nothing_to_set_raises`, `test_find_user_by_token_hash_carries_the_overrides`; updated `test_users_schema_matches_expected_columns` and the race-test docstring; new fixture `_create_pre_user_limits_database` |
| `tests/test_identity.py` | `test_resolve_admin_token_sets_break_glass_and_no_overrides`, `test_resolve_admin_role_user_token_is_not_break_glass`, `test_resolve_carries_the_users_limit_overrides`, `test_resolve_user_without_overrides_carries_none`, `test_identity_two_positional_args_still_construct`, `test_identity_new_fields_are_frozen_too`; three admin-token assertions now expect `break_glass=True` |
| `tests/test_manage_users_cli.py` | `test_set_limits_token_budget_sets_it_and_reaches_resolve`, `test_set_limits_default_clears_the_column_to_null` (2 flags × 2 spellings), `test_set_limits_rejects_a_bad_value_and_writes_nothing` (2 flags × 6 values: `0`, `-5`, `abc`, `1.5`, `unlimited`, empty), `test_set_limits_unknown_user_exits_nonzero_and_writes_nothing`, `test_set_limits_with_neither_flag_exits_nonzero`, `test_list_users_prints_default_for_unset_limits`, `test_list_users_prints_the_overrides_once_set` |
| `tests/test_migrate_to_turso_cli.py` | `test_dest_columns_match_the_ddl`: the users list gains two names |
| `tests/test_two_instance_smoke.py` | `test_both_instances_boot_simultaneously_against_one_database`: the users columns gain two names |

## Acceptance Criteria

- [x] Given a `users` table created before this story, when `init_db()` runs, then `token_budget_daily INTEGER` and `requests_per_minute INTEGER` exist, both NULL on every existing row, converged through a new `USERS_ADDED_COLUMNS` mapping and the existing `_add_missing_columns`.
- [x] Given `python scripts/manage_users.py set-limits --user-id dana --token-budget 5000000`, when it runs, then Dana's row has `token_budget_daily=5000000`, her `requests_per_minute` is unchanged, and `resolve(dana_token)` returns an `Identity` with `token_budget_daily=5000000`.
- [x] Given `--token-budget default` or `--requests-per-minute default`, when it runs, then that column is set to NULL; given a value below 1, a non-number, or an unknown user, then the command exits non-zero with a message and writes nothing.
- [x] Given `list-users`, when it runs, then each line shows both limits, printing `default` for NULL.
- [x] Given `resolve(settings.ADMIN_TOKEN)`, when it returns, then the identity has `break_glass=True` and both overrides `None`; given a user token whose role is `admin`, then `break_glass` is `False`.
