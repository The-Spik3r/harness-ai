---
id: STORY-007
prd: PRD-007
slug: concurrent-safe-init-db
title: "Make init_db() and _add_missing_columns() converge under concurrent multi-instance startup"
type: technical
priority: high
complexity: medium
phase: "2 - Storage layer swap"
status: done
labels: [backend, database, migration, concurrency]
epic_branch: epic/PRD-007-turso-migration
plan: .agents/plans/PRD-007-turso-migration/completed/STORY-007-concurrent-safe-init-db.plan.md
report: .agents/reports/PRD-007-turso-migration/STORY-007-concurrent-safe-init-db.report.md
commit: null
depends_on: [STORY-006]
blocks: [STORY-016]
skills: []
created: 2026-09-01
updated: 2026-09-01
---

# STORY-007: Make init_db() and _add_missing_columns() converge under concurrent multi-instance startup

## Description

As a platform engineer, I want N application instances booting simultaneously against one shared database to converge on the correct schema, so that scaling past one container does not produce a container that will not start or a half-migrated `audit_logs` table.

`_add_missing_columns()` reads the current schema with `PRAGMA table_info(audit_logs)` and then conditionally issues `ALTER TABLE ... ADD COLUMN` for each of the five `AUDIT_LOGS_ADDED_COLUMNS`. Under one process against one file that read-then-write sequence is trivially safe. Against a shared database it is a race: two instances can both observe a column as missing, and the loser's `ALTER` fails. Because `init_db()` runs at **import time** (noted at [tests/test_admin_shell.py:697](../../../tests/test_admin_shell.py)), that failure presents as a container that will not boot.

## Acceptance Criteria

- [ ] Given an empty database and N concurrent `init_db()` calls, when they all complete, then the schema is correct and complete and **every** call returns successfully. No caller crashes because another won the race.
- [ ] Given a database whose `audit_logs` table exists but is missing a subset of `AUDIT_LOGS_ADDED_COLUMNS`, when N concurrent `init_db()` calls run, then all five columns are present exactly once afterward and every call returns successfully.
- [ ] Given an `ALTER TABLE ADD COLUMN` that fails because the column already exists, when `_add_missing_columns()` handles it, then that specific condition is treated as success. Any other failure still propagates — swallowing a genuine schema error here would hide a broken migration behind a healthy-looking boot.
- [ ] Given a database already at the current schema, when `init_db()` runs, then it is a no-op: no `ALTER` is issued and no error is raised.
- [ ] Given the five columns are added, when their definitions are checked, then each matches `AUDIT_LOGS_ADDED_COLUMNS` in [app/db/models.py](../../../app/db/models.py) — including that every `NOT NULL` entry carries a non-NULL `DEFAULT`, the invariant `tests/test_db.py::test_added_columns_declaring_not_null_also_declare_a_default` already enforces.
- [ ] Given `PRAGMA table_info(audit_logs)` executed against the libSQL endpoint, when `_add_missing_columns()` reads it, then the column names are extracted correctly. If the result shape differs from `sqlite3`'s, the difference is handled here and recorded in the report.
- [ ] Given the concurrency tests, when they run in CI, then they are deterministic — a test that passes because the race happened not to occur is not evidence.

## Technical Notes

- Files: [app/db/database.py](../../../app/db/database.py) (`init_db()`, `_add_missing_columns()`), `tests/test_db.py`.
- PRD Section 6 Pattern 5 states the required shape directly: "The MVP makes this convergent — the losing instance must treat 'column already exists' as success, not as a startup crash."
- The `CREATE TABLE IF NOT EXISTS` and `CREATE UNIQUE INDEX IF NOT EXISTS` statements are already idempotent by construction. The race is specifically in the read-then-`ALTER` sequence, because `ALTER TABLE ADD COLUMN` has no `IF NOT EXISTS` form. Scope the fix there rather than restructuring `init_db()` wholesale.
- Be precise about what is caught. "Column already exists" is one specific error; catching a broad storage error around the `ALTER` would let a genuine failure — a permissions problem, an unreachable endpoint — pass as a completed migration. Use the module-owned error surface from [[STORY-004]] and narrow the condition.
- The existing docstring on `_add_missing_columns()` states the standing constraint: "Additive only: existing rows keep their data and take the column default." That is unchanged. This story adds concurrency safety, not migration capability.
- Writing the concurrency test: threads against one shared endpoint are the natural approach given the synchronous client from [[STORY-006]]. Make the race actually happen — start the workers from a barrier rather than sequentially — otherwise the test proves nothing.
- The two-instance end-to-end proof is [[STORY-016]]. This story proves it at the function level, where the failure is diagnosable.
- `.agents/skills/` was scanned: only `frontend-design` is present, scoped to visual design of UI. This story touches no UI. No skill applies.

## Dependencies

- **Blocked by**: STORY-006
- **Blocks**: STORY-016

## PRD Reference

Source: [`PRD-007/PRD.md`](../../PRDs/PRD-007-turso-migration/PRD.md) — Section 6 Pattern 5, Section 11 (functional requirements), Section 12 Phase 2, Section 14 Risk 3
