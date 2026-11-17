---
story: STORY-008
prd: PRD-018
plan: .agents/plans/PRD-018-db-resilience/completed/STORY-008-audit-journal.plan.md
epic_branch: epic/PRD-018-db-resilience
commit: b319788
status: COMPLETE
completed: 2026-11-17
---

# Implementation Report - STORY-008: The on-disk audit journal

## Summary

New `app/db/audit_journal.py` (filesystem only; no database, thread, settings import or import-time effect): `AuditJournal` with fsynced JSON Lines append, exclusive OS lock (flock on POSIX; `msvcrt.locking` on one byte at offset 2**40 on Windows), sha256 per line, rollback by truncation on a failed write, `AUDIT_BUFFER_MAX_BYTES` bound, checkpoint sidecar and compaction, adoption of unlocked sibling journals, per-(user, dedup_key) index, depth/headroom queries, and a module slot (`open_journal`/`current`/`close_journal`/`append`). `AuditUnavailableError(StorageError)` added. `AUDIT_BUFFER_DIR` and `AUDIT_BUFFER_MAX_BYTES` settings with validators; `var/` gitignored.

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| Targeted tests | 526 passed, 0 failed, 1 skipped (the POSIX 0700/0600 test, skipped on Windows) |
| Full suite | GitHub CI on push (user decision) |

Run: test_audit_journal, test_config, test_untouched_app, test_conftest_fixtures, test_pii_dedup_isolation, test_chat_sessions, test_query_pipeline_audit_fields, test_db_resilience_write_id (673 s).

## Files Changed

`app/db/audit_journal.py` (new), `app/db/errors.py`, `app/config.py`, `.gitignore`, `tests/test_audit_journal.py` (new, 24 test functions plus parametrization), `tests/test_config.py` (+6 test functions).

## Deviations from Plan (orchestrator rulings, also in the module docstring)

- Accepted as planned: `pending_audit_rows` (predicate left to STORY-011); `bytes()` counts own + held adopted files; `oldest_timestamp()` = oldest pending `appended_at`; journal never mints write_ids; `AuditUnavailableError` also for an unwritable dir at open; config imports the reserve constant from audit_journal (test asserts importing audit_journal does not import app.config).
- CHANGED 4: only a corrupt LAST line (or a last line without newline) is a torn tail (discarded, one ERROR reason=torn_tail). A corrupt non-last line, or a checksum-valid undecodable line, leaves the whole file on disk untouched, not adopted, with one ERROR (reason=corrupt / undecodable, file, line, write_id if parseable). Counted as `held_back_files` in `JournalStatus` (small addition).
- `ftruncate` on the O_APPEND handle was confirmed working on Windows (spike first, then the tests); no close-truncate-reopen needed.
- A duplicate `write_id` on `append` raises ValueError; a duplicate seen on adoption is skipped (replay is idempotent).

## Acceptance Criteria

- [x] append: one checksummed line, flush then fsync before return; I/O failure raises AuditUnavailableError (test_append_writes_one_checksummed_line..., test_append_flushes_then_fsyncs..., test_a_failed_fsync...)
- [x] max bytes refusal writes nothing; bytes/entries/oldest_timestamp/headroom_ok (test_append_that_would_exceed..., test_depth_queries_and_headroom)
- [x] file name, exclusive lock (two handles + subprocess), POSIX modes (test_file_name_and_second_opener_cannot_lock, test_adopt_skips_a_file_locked_by_a_live_process, POSIX test skipped here, runs on Linux CI)
- [x] torn tail discard with one ERROR, adoption, locked skip (torn tail x2, corrupt non-last, undecodable, adoption tests, test_logs_never_contain_contents)
- [x] settings and validators; unwritable dir error at open (tests/test_config.py block; test_unwritable_directory...)
- [x] entry round trip over dataclasses.fields (test_entry_round_trips_every_dataclass_field)
