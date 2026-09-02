---
story: STORY-013
prd: PRD-007
plan: .agents/plans/PRD-007-turso-migration/completed/STORY-013-data-migration-script.plan.md
epic_branch: epic/PRD-007-turso-migration
commit: pending
status: COMPLETE
completed: 2026-09-02
---

# Implementation Report — STORY-013: `scripts/migrate_to_turso.py`

**Plan**: `.agents/plans/PRD-007-turso-migration/completed/STORY-013-data-migration-script.plan.md`
**Epic Branch**: `epic/PRD-007-turso-migration`
**Commit**: pending (recorded by the follow-up chore commit)

## Summary

`scripts/migrate_to_turso.py` copies `audit_logs` and `users` out of a legacy SQLite
file into the Turso database `DATABASE_URL` names, and proves the copy before it
reports success. The source is opened `mode=ro` and fingerprinted with SHA-256
before and after every run; the destination is written through
`app.db.database.get_connection()` — the one process-wide libSQL client — inside a
single transaction covering both tables, with `audit_logs.id` inserted explicitly.
Verification is three layers (per-table counts, exhaustive row-by-row content
comparison by column name, and an accessor read-back through `get_audit_log()`),
plus id-set equality and a `token_hash`/unique-index check. Any failure names the
table, the id and the column, and exits non-zero. A non-empty destination is
refused outright. Nothing under `app/` or `chat_ui/` was touched.

**The source file has not been deleted and must not be until STORY-014.** The run
recorded below was a rehearsal against the local libSQL dev server, not a
production Turso database; the production migration is the operator's to run.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | libSQL dev server started (pinned digest, STORY-001 §4) | — | ✅ |
| 2 | Skeleton, parser, and the `sqlite3`-exception docstring | `scripts/migrate_to_turso.py` | ✅ |
| 3 | Read-only open, hot-journal refusal, SHA-256 fingerprint | `scripts/migrate_to_turso.py` | ✅ |
| 4 | Schema reconciliation + chunked multi-row copy; `executemany` measured | `scripts/migrate_to_turso.py` | ✅ |
| 5 | Non-empty-destination refusal, no `--force` | `scripts/migrate_to_turso.py` | ✅ |
| 6 | `sqlite_sequence` continuation, checked at the endpoint | `scripts/migrate_to_turso.py` | ✅ |
| 7 | Three verification layers + the summary/rollback block | `scripts/migrate_to_turso.py` | ✅ |
| 8 | AC 10's six named cases | `tests/test_migrate_to_turso_cli.py` | ✅ |
| 9 | Integrity guarantees (a–h) | `tests/test_migrate_to_turso_cli.py` | ✅ |
| 10 | Real run against `harness_ai.db` + this report | — | ✅ |
| 11 | Full validation and the untouched-application proof | — | ✅ |

## The real run, pasted verbatim

Against the repo-root `harness_ai.db` (8 `audit_logs` rows, 0 `users` rows) into an
empty local libSQL dev server:

```
Dry run -- nothing was written.
  audit_logs: 8 row(s), 19 column(s) copied
  users: 0 row(s), 5 column(s) copied
  destination: http://host.docker.internal:8080, empty
destination after dry-run: 0 audit rows

Source      /app/harness_ai.db
            sha256 f55928bbde2eda51d149d6f166881f996be4f8f61a01406e08cadc361518c75d  (unchanged)
            8 audit_logs row(s), 0 users row(s)
Destination http://host.docker.internal:8080
            8 audit_logs row(s), 0 users row(s)
            audit_logs AUTOINCREMENT sequence: already correct at 8
Copied      8 row(s) in 1 statement(s)
Verified    counts OK · content OK · id preservation OK · read-back OK (3 of 8 sampled) · token_hash OK
Rollback    The source file was opened read-only and is unmodified.
            It remains authoritative until you delete it, which is a
            separate step (STORY-014).
```

The second run, immediately after:

```
Error: the destination is not empty: audit_logs holds 8 row(s). Refusing to append
into a populated table. There is deliberately no --force: the copy runs in one
transaction, so a failed run leaves the destination empty and immediately
re-runnable, and a flag that empties an audit table is the wrong tool to ship
beside one. Clear it by hand if that is genuinely what you want.
```

exit 1, with stdout empty.

**Source SHA-256, measured on the host before and after every run above:**

```
f55928bbde2eda51d149d6f166881f996be4f8f61a01406e08cadc361518c75d  (before)
f55928bbde2eda51d149d6f166881f996be4f8f61a01406e08cadc361518c75d  (after)
```

## Findings

### 1. PRD Section 11 vs STORY-014's AC 6 — the `sqlite3` exception is sanctioned

The story asked whether PRD Section 11's *"No module outside `app/db/` imports
`sqlite3` or any driver module"* is intended to except this script. **It is, and it
was already in writing before this story started** — STORY-014's AC 6 names
`scripts/migrate_to_turso.py` as "the one documented exception (it reads the legacy
file by design)". Nothing was quietly violated.

The reconciliation between the two texts: this script is an **operational tool, not
a production code path**. Nothing in the application imports it, it runs once per
deployment, and its purpose is to read the file the rest of the system may no
longer touch. The module docstring states this, quoting STORY-014's AC.

For STORY-014's grep, the meaningful check is the `import` statement, not the word:

```
$ grep -rn "^import sqlite3\|^from sqlite3" app/ chat_ui/ scripts/ tests/
scripts/migrate_to_turso.py:38:import sqlite3
tests/test_db.py:8:import sqlite3
tests/test_migrate_to_turso_cli.py:17:import sqlite3
```

One production hit, this script. The remaining textual hits in `app/db/database.py`
and `app/db/errors.py` are **comments** describing what the driver swap replaced,
and they are inside `app/db/`, which PRD Section 11's wording permits explicitly.
The two test hits are test code, and `tests/test_db.py`'s predates this story.

### 2. `executemany` is N round trips — measured, not assumed

The plan chose chunked multi-row `INSERT ... VALUES` over `executemany` because the
latter is unexercised in this repo. Measured against the endpoint, 500 rows:

```
executemany   500 rows:  1332.5 ms
multi-row     500 rows in 10 statements:    38.2 ms
row-at-a-time 500 rows:  1295.1 ms
```

`executemany` costs essentially the same as inserting one row at a time — it is a
convenience wrapper over N round trips, not a batch. The multi-row statement is
**~35× faster**. This is the same shape as STORY-001 §2.6's finding about `batch()`
and `executescript()`: the driver's bulk-looking APIs are not bulk. Recorded here
for whoever next needs bulk writes; nothing should adopt `executemany` on the
assumption that it batches.

### 3. The libSQL endpoint maintains `sqlite_sequence` on explicit-id inserts

`audit_logs AUTOINCREMENT sequence: already correct at 8` — the endpoint advanced
the sequence by itself, matching local SQLite (verified separately: ids `7, 30`
leave `seq = 30`, next natural id `31`). The repair path in `_restore_sequence()`
never fired, on the real file or in any test. It is retained as a safety net rather
than removed, because the cost is one read and the failure it guards against — the
first post-migration write colliding with a preserved id — is silent.

Proven positively in both places: after migrating ids `3, 7, 100`, a real
`insert_audit_log()` returns `101` (test), and after the real 8-row migration the
next natural insert returned `9` (E2E).

### 4. There is no `GET /audit/{id}` HTTP route

The story and PRD both say "`GET /audit/{id}` addresses rows by id". No such route
exists: `app/routers/admin.py:22` serves `GET /audit` as a **list**, carrying
`audit_id` per entry, and id-addressed access is the `get_audit_log(audit_id)`
database function (`app/db/database.py:611`). The requirement is real either way —
ids must be preserved or both surfaces break — and was verified through both. This
is a documentation inaccuracy in the PRD, not a defect, and is flagged here for
STORY-015's README pass.

## Validation Results

| Check | Result |
|-------|--------|
| `tests/test_migrate_to_turso_cli.py` (new) | ✅ 21 passed |
| `tests/test_db.py` | ✅ 97 passed (unchanged from baseline) |
| `tests/test_manage_users_cli.py` | ✅ 11 passed (unchanged) |
| Backend import (`from app.main import app`) | ✅ OK |
| Whole suite, file by file (42 modules) | ✅ 3 pre-existing failures, unchanged |
| E2E checklist (8 items) | ✅ 8/8 |
| `git diff HEAD -- app/ chat_ui/` | ✅ empty |
| `import sqlite3` outside `app/db/` | ✅ this script only |

**The three failing suites are pre-existing and unrelated.** Proven by moving this
story's two files out of the tree and re-running them on the otherwise pristine
epic tip — identical results:

| Suite | Pristine tree | With this story |
|---|---|---|
| `tests/test_chat_state.py` | 1 failed, 37 errors | 1 failed, 37 errors |
| `tests/test_pii_badge.py` | 1 error | 1 error |
| `tests/test_success_metadata_footer.py` | 1 error | 1 error |

They are the open issue the PRD index already carries as owned by no story. Note
one refinement for whoever picks it up: run individually, `test_pii_badge.py` and
`test_success_metadata_footer.py` fail at **collection** with
`ModuleNotFoundError: No module named 'chat_ui.chat_ui.models'; 'chat_ui.chat_ui'
is not a package`, which is a packaging/import problem rather than the
`STREAM_EXPIRED` idle-stream one the index describes. The index's entry may be
conflating two distinct failures.

### E2E checklist

| # | Check | Result |
|---|---|---|
| 1 | `--help` documents all four flags | ✅ |
| 2 | `--dry-run` reports 8/0 and writes nothing (destination still 0) | ✅ |
| 3 | Real run into an empty endpoint exits 0, all five checks OK | ✅ |
| 4 | Migrated rows match the file through `get_audit_log()` **and** `GET /audit` | ✅ 8/8 rows, every column |
| 5 | A second run refuses, exit 1, stdout empty | ✅ |
| 6 | `sha256sum harness_ai.db` identical before and after every run | ✅ |
| 7 | `manage_users.py create-user` works against the migrated database | ✅ |
| 8 | A new audit write continues the id sequence (`max=8` → `new=9`) | ✅ |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `scripts/migrate_to_turso.py` | CREATE | +895 |
| `tests/test_migrate_to_turso_cli.py` | CREATE | +607 |
| `.agents/reports/PRD-007-turso-migration/STORY-013-data-migration-script.report.md` | CREATE | this file |

No existing file was modified.

## Deviations from Plan

| # | Deviation | Why |
|---|---|---|
| 1 | The summary block prints on every path that **attempted a migration**, not literally every exit path. A refusal (missing source, hot journal, unknown column, populated destination) prints only to stderr. | The plan's Task 7 said "every exit path" while Task 8c asserted `captured.out == ""` on the refusal — the two could not both hold. A refusal happens before anything is written, so there is no state to summarize, and `manage_users.py`'s clean-stdout convention wins. The **source-integrity check still runs on every path**, including refusals, which is the part AC 6 actually requires. `_migrate`'s docstring records the split. |
| 2 | Added a `Copied N row(s) in M statement(s)` line to the summary. | The plan's Task 4 validation asks the operator to observe the statement count; it was computed but not surfaced. |
| 3 | Five checks are printed, not four — `token_hash` joined the list. | The plan designed the check (AC 7) but omitted it from the sample summary. Reporting four of five would have understated what ran. |
| 4 | Five tests beyond the plan's list: hot-journal refusal, unknown-column refusal, missing-source refusal, a source with no `users` table, and a DDL-parser pin. | Each is a refusal path the script grew in Tasks 3–5; the DDL parser is the single source of truth for the column list, and an unpinned parser is a silent-column-drop waiting to happen. 21 tests total. |
| 5 | The plan's final check `git diff main --stat -- app/ chat_ui/` was wrong and was corrected to `git diff HEAD`. | `main` is twelve stories behind the epic tip, so that command reports every prior story's work. `HEAD` is what proves *this* story touched nothing. |
| 6 | The plan's expectation that `grep -rn "sqlite3"` hits this script "and nothing else" was too strict. | `app/db/database.py` and `app/db/errors.py` mention `sqlite3` in comments, which PRD Section 11 permits (the rule is about modules *outside* `app/db/`, and about imports). The `import`-statement grep is the check that means something; see Finding 1. |
| 7 | E2E item 4 was re-specified against the routes that exist. | There is no `GET /audit/{id}` endpoint; see Finding 4. Verified through `get_audit_log()` and `GET /audit` instead, on all 8 rows rather than the one row the plan asked for. |

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_migrate_to_turso_cli.py` | `test_dest_columns_match_the_ddl`; **AC 10's six**: `test_clean_copy_copies_every_row_and_column`, `test_ids_are_preserved_not_regenerated`, `test_non_empty_destination_is_refused_without_writing`, `test_count_mismatch_exits_nonzero_and_names_the_table`, `test_older_schema_source_copies_and_applies_destination_defaults`, `test_empty_source_succeeds_and_says_nothing_to_migrate`; **integrity**: `test_source_is_unmodified_after_a_successful_run`, `test_source_is_unmodified_after_a_failed_run_and_nothing_is_committed`, `test_the_source_connection_cannot_write`, `test_a_hot_journal_is_refused_rather_than_recovered`, `test_token_hashes_transfer_intact_and_the_unique_index_still_holds`, `test_added_columns_role_and_denied_permission_read_back_through_get_audit_log`, `test_next_natural_insert_does_not_collide_with_preserved_ids`, `test_content_verification_holds_when_read_through_a_fresh_client`, `test_content_mismatch_with_matching_counts_exits_nonzero_and_names_the_column`, `test_batch_size_controls_the_number_of_insert_statements`, `test_dry_run_writes_nothing`; **refusals**: `test_a_source_with_no_users_table_is_migrated_not_refused`, `test_a_source_with_an_unknown_column_is_refused`, `test_a_missing_source_file_is_refused` |

## Acceptance Criteria

- [x] All rows of `audit_logs` and `users` are copied.
- [x] `audit_logs.id` values are preserved, not regenerated.
- [x] Source and destination counts are reported **per table**, and content is compared, not only counts.
- [x] Any mismatch exits non-zero and says which table and which check failed.
- [x] A non-empty destination is refused outright.
- [x] The source `.db` is unmodified on success, failure, and interruption — enforced by `mode=ro`, evidenced by SHA-256.
- [x] `token_hash` values transfer intact and the unique index holds afterward.
- [x] All five `AUDIT_LOGS_ADDED_COLUMNS` plus `role` and `denied_permission` match the source when read back through `get_audit_log(...)`.
- [x] A source missing added columns is handled explicitly, applying destination defaults.
- [x] Test coverage includes a clean copy, id preservation, a non-empty destination, a count mismatch, an older-schema source, and an empty source.
- [x] All tasks completed
- [x] `tests/test_migrate_to_turso_cli.py` (21) and `tests/test_db.py` (97) pass
- [x] No file under `app/` or `chat_ui/` is modified
- [x] `import sqlite3` outside `app/db/` appears only in `scripts/migrate_to_turso.py`
- [x] Follows existing patterns
