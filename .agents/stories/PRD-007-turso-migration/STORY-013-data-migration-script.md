---
id: STORY-013
prd: PRD-007
slug: data-migration-script
title: "scripts/migrate_to_turso.py: copy audit_logs and users with verification and a rollback point"
type: feature
priority: high
complexity: medium
phase: "4 - Data migration and cutover"
status: todo
labels: [backend, migration, tooling, compliance]
epic_branch: epic/PRD-007-turso-migration
plan: null
report: null
commit: null
depends_on: [STORY-006]
blocks: [STORY-014]
skills: []
created: 2026-09-01
updated: 2026-09-01
---

# STORY-013: scripts/migrate_to_turso.py: copy audit_logs and users with verification and a rollback point

## Description

As a compliance admin, I want every existing audit row copied into Turso and verified, so that the historical record is not silently truncated by the move that was supposed to protect it.

This is Risk 2. The audit trail is the product; a partial or reordered migration is an unrecoverable compliance failure, and it is the kind of failure that looks like success — the app starts, the console renders, and nobody notices the missing months until someone goes looking for them.

## Acceptance Criteria

- [ ] Given a source `.db` file and a target Turso database, when the script runs, then all rows of `audit_logs` and `users` are copied.
- [ ] Given `audit_logs`, when rows are copied, then their `id` values are **preserved**, not regenerated. `GET /audit/{id}` addresses rows by id, so a renumbered trail silently breaks every existing reference.
- [ ] Given a completed copy, when the script verifies, then it reports source and destination row counts **per table** and compares row content, not only counts. A count match with corrupted content is the failure this criterion exists to catch.
- [ ] Given any mismatch in count or content, when the script finishes, then it exits non-zero and says which table and which check failed.
- [ ] Given a non-empty destination, when the script is run, then it either refuses outright or is genuinely idempotent. Silently appending into a populated table is not an acceptable third option.
- [ ] Given the source `.db` file, when the script completes by any path — success, failure, or interruption — then it is unmodified. It remains authoritative until verification passes.
- [ ] Given the `users` table, when it is copied, then `token_hash` values transfer intact and the unique index on them holds afterward. A corrupted hash silently locks a user out; a collision would have been an `IntegrityError` at write time.
- [ ] Given all five `AUDIT_LOGS_ADDED_COLUMNS` plus `role` and `denied_permission`, when rows are read back through `get_audit_log(...)`, then PII entities, roles, and denied permissions match the source exactly. PRD Section 5 story 4 names these specifically.
- [ ] Given a source database missing some added columns (an older file that predates PRD-003 or PRD-005), when the script runs, then it handles the case explicitly rather than crashing — the additive-migration mechanism in `init_db()` exists precisely because such files are expected.
- [ ] Given the script, when it is tested, then coverage includes: a clean copy, id preservation, a non-empty destination, a count mismatch, an older-schema source, and an empty source.

## Technical Notes

- Files: new `scripts/migrate_to_turso.py`, plus a test module under `tests/`.
- Follow [scripts/manage_users.py](../../../scripts/manage_users.py) for CLI shape, argument handling, and error reporting. It is the only precedent in the repo and `tests/test_manage_users_cli.py` shows how such a script is tested here.
- The script needs **both** drivers at once — stdlib `sqlite3` to read the source file and the libSQL client to write the destination. This is the one place in the codebase permitted to import `sqlite3` after [[STORY-006]]; note it explicitly so the `grep -rn "sqlite3"` check in [[STORY-014]] accounts for it, and confirm whether PRD Section 11's "no module outside `app/db/` imports `sqlite3`" is intended to except this script. If it is not, say so rather than quietly violating it.
- `AUTOINCREMENT` and explicit `id` insertion interact. Verify that inserting explicit ids into an `INTEGER PRIMARY KEY AUTOINCREMENT` column leaves the sequence in a state where the **next** natural insert does not collide. A migration that preserves history and then breaks the first new write has traded one failure for another.
- Batch the inserts. A row-at-a-time copy over the network against a real audit history will be unusably slow; the batch API from [[STORY-001]] applies here too.
- Make the rollback explicit in the script's own output, not only in documentation. PRD Section 7.5: "the source `.db` file is untouched and remains authoritative until verification passes." The operator should finish the run knowing exactly what state they are in.
- Deleting the source file is **not** part of this story. PRD Section 14 Risk 2: "The file is deleted only after verification, in a separate step from the copy." That step is [[STORY-014]].
- `.agents/skills/` was scanned: only `frontend-design` is present, scoped to visual design of UI. This story is a CLI tool. No skill applies.

## Dependencies

- **Blocked by**: STORY-006
- **Blocks**: STORY-014

## PRD Reference

Source: [`PRD-007/PRD.md`](../../PRDs/PRD-007-turso-migration/PRD.md) — Section 5 story 4, Section 7.5, Section 11 (functional requirements), Section 12 Phase 4, Section 14 Risk 2
