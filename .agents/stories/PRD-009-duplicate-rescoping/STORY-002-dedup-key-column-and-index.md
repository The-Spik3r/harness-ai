---
id: STORY-002
prd: PRD-009
slug: dedup-key-column-and-index
title: "audit_logs.dedup_key column and idx_audit_logs_dedup, converged by init_db() and round-tripped by AuditLog"
type: technical
priority: high
complexity: small
phase: "1 - Pin and prepare"
status: todo
labels: [backend, database, migration]
epic_branch: epic/PRD-009-duplicate-rescoping
plan: null
report: null
commit: null
depends_on: [STORY-001]
blocks: [STORY-006]
skills: []
created: 2026-09-16
updated: 2026-09-16
---

# STORY-002: audit_logs.dedup_key column and idx_audit_logs_dedup, converged by init_db() and round-tripped by AuditLog

## Description

As a maintainer, I want the `dedup_key` column and its lookup index to arrive through the same idempotent bootstrap every other schema change used, so that a fresh database, a pre-PRD database, a hot reload and two instances booting together all converge without a migration tool. Nothing reads or writes a real key yet.

## Acceptance Criteria

- [ ] Given [app/db/models.py](../../../app/db/models.py), when it is read, then `dedup_key TEXT` appears in **both** `CREATE_AUDIT_LOGS_TABLE` and `AUDIT_LOGS_ADDED_COLUMNS` (nullable, no default), `CREATE_AUDIT_LOGS_DEDUP_INDEX` is `CREATE INDEX IF NOT EXISTS idx_audit_logs_dedup ON audit_logs(user_id, dedup_key, timestamp)`, and `AuditLog` gains `dedup_key: Optional[str] = None`. `test_every_added_column_is_also_declared_in_the_create` passes.
- [ ] Given `init_db()`, when it runs on a fresh database and on a database created before this PRD, then the column exists, existing rows read `NULL`, and `PRAGMA index_list(audit_logs)` includes `idx_audit_logs_dedup` with columns `(user_id, dedup_key, timestamp)` in that order. The index statement runs **after** `_add_missing_columns(conn)`, inside the same `_session()` block.
- [ ] Given a schema that is already current, when `init_db()` runs again, then `test_init_db_issues_no_alter_when_schema_is_current` passes. Given two `init_db()` calls racing on the `dedup_key` `ALTER`, then both converge, asserted the way `test_two_init_db_calls_racing_on_session_id_both_converge` asserts it for `session_id`.
- [ ] Given `insert_audit_log(AuditLog(..., dedup_key="k"))`, when the row is read back through `get_audit_log` **and** through `summary_snapshot().rows`, then `dedup_key == "k"`. An entry built without it reads back `None`.
- [ ] Given `GET /audit` and `GET /stats`, when called, then their response shapes are unchanged: `AuditQueryEntry` gains no field (D5). The full suite passes, including [tests/test_stats_router.py](../../../tests/test_stats_router.py) and [tests/test_audit_router.py](../../../tests/test_audit_router.py) unmodified.

## Technical Notes

- Follow PRD-008 STORY-003 exactly: [.agents/stories/PRD-008-chat-sessions/STORY-003-init-db-tables-and-audit-column.md](../PRD-008-chat-sessions/STORY-003-init-db-tables-and-audit-column.md). `_add_missing_columns` already iterates the mapping and tolerates `_is_duplicate_column`, so it should need no code change. Assert that, don't assume it.
- **Two read shapes share one mapper.** `_row_to_audit_log` in [app/db/database.py](../../../app/db/database.py) serves both the `SELECT *` row and the `json_object(...)` list inside `summary_snapshot()`'s SQL (~line 1111). Add `'dedup_key', dedup_key` to that `json_object` in the same commit, or the summary path raises `KeyError`. Update the `AuditLog.session_id` comment block's pattern with a PRD-009 note.
- `insert_audit_log`'s column list and `VALUES` placeholder count both grow by one.
- Index order is the lookup's access path (PRD Section 6.3): equality on `user_id`, equality on `dedup_key`, range on `timestamp`. It is **not UNIQUE**, since the same key legitimately repeats (blocked rows, failures).
- Add index/column coverage to [tests/test_db.py](../../../tests/test_db.py), next to `test_init_db_creates_the_chat_indexes` and `test_audit_logs_added_columns_carries_a_nullable_session_id`.
- Skills: none applicable.

## Dependencies

- **Blocked by**: STORY-001
- **Blocks**: STORY-006

## PRD Reference

Source: [`PRD-009-duplicate-rescoping/PRD.md`](../../PRDs/PRD-009-duplicate-rescoping/PRD.md) — sections 4 (Schema), 6.7, 7 (F2), 11, 14 (Risk 2)
