---
story: STORY-003
prd: PRD-008
plan: .agents/plans/PRD-008-chat-sessions/completed/STORY-003-init-db-tables-and-audit-column.plan.md
epic_branch: epic/PRD-008-chat-sessions
commit: PENDING
status: COMPLETE
completed: 2026-09-03
---

# Implementation Report — STORY-003: init_db() creates both transcript tables and converges the audit_logs.session_id column

**Plan**: `.agents/plans/PRD-008-chat-sessions/completed/STORY-003-init-db-tables-and-audit-column.plan.md`
**Epic Branch**: `epic/PRD-008-chat-sessions`
**Commit**: `PENDING`

## Summary

`init_db()` now executes the four DDL constants STORY-002 declared and left unreferenced, inside the **same** `_session()` block that already creates `audit_logs` and `users`. The production diff is four imports, four `conn.execute(...)` lines and one docstring paragraph — 20 lines in [app/db/database.py](../../../app/db/database.py). Everything else in this story is evidence.

`_add_missing_columns()` was not touched, exactly as the story instructed. It iterates `AUDIT_LOGS_ADDED_COLUMNS`, and STORY-002 put `session_id` there, so the column has been converging since `e3bb0c7`. AC 3 and AC 4 were therefore already *true* when this story started; the work on them was assertion, not implementation, which is what "Assert it, do not assume it" asked for. Two new tests name `session_id` specifically against a fixture where it is the only missing column, so the guarantee can no longer pass by riding along with four other columns in a set comparison.

Verified by direct inspection after a fresh `init_db()`: four tables (`audit_logs`, `chat_sessions`, `chat_messages`, `users`), three indexes, and 15 columns on `chat_messages`.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Import the four chat DDL constants | `app/db/database.py` | ✅ |
| 2 | Execute them in `init_db()`'s existing `_session()` block, + docstring | `app/db/database.py` | ✅ |
| 3 | PRAGMA-level, migration, race and bootstrap-off coverage | `tests/test_db.py` | ✅ |
| 4 | Correct the boot-time table pin | `tests/test_two_instance_smoke.py` | ✅ |
| 5 | Full-suite regression check against the measured baseline | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`app.db.database` + `app.main`) | ✅ |
| `tests/test_db.py` | ✅ 137 passed (124 pre-existing + 13 new) |
| `tests/test_two_instance_smoke.py` | ✅ 7 passed |
| `tests/test_migrate_to_turso_cli.py` | ✅ passed, with no edit |
| Full suite `pytest -q` | ✅ 1183 passed, 7 failed — **all 7 pre-existing**, identical to the measured baseline |
| E2E | ✅ 7/7 |
| Lint | n/a — the repo has no linter or formatter; CI runs `pip install -r requirements.txt` then `pytest -q` |

### The 7 failures, measured rather than asserted

All 7 live in `tests/test_untouched_app.py` and are the same 7 STORY-002 recorded. Established the same way rather than taken on trust: the three changed files were stashed with `git stash push -- app/db/database.py tests/test_db.py tests/test_two_instance_smoke.py`, `tests/test_untouched_app.py` was run against the clean tree, and it produced the identical 7 failures by name. The stash was then popped. The new-failure set is empty, and the full-suite pass count rose from STORY-002's 1170 to 1183 — exactly the 13 cases added here.

They are PRD-006-scoped guards asserting files are unchanged since PRD-006's baseline commit; PRD-007 and PRD-008 have legitimately changed those files since. As STORY-002 already flagged, one of them is `test_the_pinned_suites_are_byte_unmodified[tests/test_db.py]`, which pins the very file this story extends — it was failing before this story touched anything, so it hid no regression, but it can no longer detect an unintended edit to `tests/test_db.py`. That is PRD-006's guard to rescope, not this story's.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/db/database.py` | UPDATE | +20 |
| `tests/test_db.py` | UPDATE | +352/-4 |
| `tests/test_two_instance_smoke.py` | UPDATE | +22/-3 |

## Deviations from Plan

1. **A test assertion the plan specified was wrong, and was corrected to a narrower true claim.** Plan Task 3(9) said `test_init_db_migrates_a_pre_chat_sessions_database` should "insert a new `AuditLog` carrying a `session_id` and read it back", mirroring what `test_init_db_migrates_pre_rbac_database` does for `role`. That mirror does not hold: `insert_audit_log()`'s INSERT names 18 columns and `session_id` is not among them ([app/db/database.py:549-555](../../../app/db/database.py#L549-L555)) — **STORY-008** is the story that adds it. The test failed on exactly that, which is the honest signal. It now asserts the insert succeeds and that the new row's `session_id` **is None**, with a comment naming STORY-008 as the story that must come back and change the line. Pinned as `None` rather than left unasserted on purpose: an unasserted value is one STORY-008 could satisfy without noticing.

   The claim the test exists for is unaffected — the migration's job is that inserts do not die with "table audit_logs has no column named ...", and that is what is asserted.

2. **The race test was placed with its siblings, not in the new section.** Plan Task 3 listed test (10) inside the new STORY-003 section. It lives instead in the concurrency section at the end of the file, immediately before `test_add_missing_columns_propagates_a_failure_that_is_not_a_duplicate_column`, beside the two existing forced-race tests whose `_GatedConnection` / `_install` / `_run_concurrently` machinery it reuses and whose caveats its docstring answers directly. A reader looking for "what proves the ALTER race converges" looks there.

3. **The extended no-ALTER test asserts two connections, not one.** Plan Task 3's closing paragraph said to assert the run "used exactly one connection". It uses two, and that is correct: `check_database_reachable()` opens its own connection for its single `SELECT 1` before the bootstrap block ([app/db/database.py:437](../../../app/db/database.py)), which `test_guard_issues_exactly_one_extra_statement` already pins. The assertion is `len(connections) == 2` plus `statements.count("SELECT 1") == 1`, with a comment saying why two is right and three would mean the block was split. The claim the plan wanted — one `_session()` for the whole schema — is what is actually enforced.

4. **`tests/test_two_instance_smoke.py` was modified**, as the plan predicted and pre-authorized. `assert schema["tables"] == ["audit_logs", "users"]` is an exact-equality pin on a table set this story deliberately changes; no implementation choice keeps it true. It now lists the four sorted names and adds a sorted-column assertion for `chat_sessions` plus a containment assertion for `chat_messages`' five required columns. This is the one departure from story AC 7's "every other suite passes unmodified" — sanctioned because the file is absent from both PRD Section 15's unmodified list and `tests/test_untouched_app.py`'s byte-equality pin, and because STORY-021 already owns extending it.

Nothing else deviated. `_add_missing_columns()` is byte-unchanged, `app/db/models.py` was not touched, `scripts/migrate_to_turso.py` needed nothing (verified — its `_TABLES` drives what it copies, not what must exist), and no new function was added.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_db.py` | `test_init_db_creates_the_chat_tables[×2]` (AC 1) · `test_init_db_creates_the_chat_indexes[×2]` (AC 1) · `test_chat_sessions_table_matches_its_ddl` (AC 6) · `test_chat_messages_table_matches_its_ddl` (AC 6) · `test_chat_messages_table_stores_no_humanized_duplicate_copy[×2]` (AC 6) · `test_init_db_is_idempotent_for_the_chat_tables` (AC 2) · `test_init_db_adds_the_chat_tables_to_a_pre_chat_database` (AC 1) · `test_init_db_migrates_a_pre_chat_sessions_database` (AC 3) · `test_two_init_db_calls_racing_on_session_id_both_converge` (AC 4) · `test_bootstrap_disabled_creates_no_chat_tables` (AC 5) · `_create_pre_chat_sessions_database` (new fixture helper) · `test_init_db_issues_no_alter_when_schema_is_current` **extended** (AC 1, AC 2) |
| `tests/test_two_instance_smoke.py` | `test_both_instances_boot_simultaneously_against_one_database` **extended** — four-table boot schema, `chat_sessions` columns, `chat_messages` containment |

11 new functions, 13 collected cases after parametrization, plus two existing tests strengthened.

The three that earn their place most:

- **`test_two_init_db_calls_racing_on_session_id_both_converge`** is AC 4's whole point. The two pre-existing race tests assert `set(AUDIT_LOGS_ADDED_COLUMNS) <= set(columns)` against a fixture missing five columns, so they began covering `session_id` the moment STORY-002 grew the mapping — without anyone deciding they should, and in a way that would keep passing if `session_id` ever left the migration path. The new `_create_pre_chat_sessions_database` fixture is `main`'s current 19-column shape, so `session_id` is the *only* column in flight and the assertion is `columns.count("session_id") == 1`.
- **`test_chat_messages_table_matches_its_ddl`** compares `PRAGMA table_info` against `_declared_columns(CREATE_CHAT_MESSAGES_TABLE)` in declaration order rather than against a second hand-typed fifteen-name literal. The long-run risk is the constant and the built table drifting; this fails on drift rather than needing a reader to spot it.
- **`test_bootstrap_disabled_creates_no_chat_tables`** covers the half of AC 5 the existing bootstrap test structurally cannot: that test points at a dead endpoint, proving the guard was skipped but leaving no database to interrogate. This one runs against the reachable endpoint on an empty database and asserts the table set is empty.

## End-to-End Verification

| # | Check | Result |
|---|-------|--------|
| 1 | Empty database → all four tables and three indexes present | ✅ |
| 2 | `init_db()` ×3 issues no `ALTER` and raises nothing | ✅ |
| 3 | Pre-PRD-008 database gains `session_id`; existing row takes `NULL`, is not rewritten | ✅ |
| 4 | Two threads racing `ADD COLUMN session_id` from one stale PRAGMA both return; column exists once | ✅ |
| 5 | `DB_BOOTSTRAP_ENABLED=False` creates no table against a reachable, empty database | ✅ |
| 6 | `python -c "import chat_ui.chat_ui"` with the flag off and no reachable database | ✅ — ran directly, not via a test |
| 7 | Two child instances record the same four-table boot schema | ✅ |

## Acceptance Criteria

- [x] `init_db()` executes `CREATE_CHAT_SESSIONS_TABLE`, `CREATE_CHAT_MESSAGES_TABLE` and both indexes inside the **same** `_session()` block that creates `audit_logs` and `users` — enforced by the connection count in `test_init_db_issues_no_alter_when_schema_is_current`, not just written that way
- [x] A current schema issues **no `ALTER`** on a re-run — `test_init_db_issues_no_alter_when_schema_is_current` passes with `session_id` present
- [x] A pre-PRD-008 database gains `session_id`; the existing row takes `NULL` and keeps its other fields
- [x] Two processes racing the `session_id` `ALTER` converge through the existing `_is_duplicate_column` path, which was not changed
- [x] `DB_BOOTSTRAP_ENABLED=False` returns before touching the database; `chat_ui.chat_ui` imports with no reachable database
- [x] `PRAGMA table_info(chat_messages)` matches STORY-002's DDL exactly, in order; `duplicate_relative_info` / `duplicate_release_info` absent
- [x] `tests/test_db.py` passes with new coverage for both tables and the new column; every other suite passes unmodified **except `tests/test_two_instance_smoke.py`** (Deviation 4)
- [x] All tasks completed
- [x] Backend imports without error
- [x] Follows existing patterns
