---
id: STORY-003
prd: PRD-008
slug: init-db-tables-and-audit-column
title: "init_db() creates both transcript tables and converges the audit_logs.session_id column"
type: technical
priority: high
complexity: small
phase: "1 - Schema and store"
status: todo
labels: [backend, database, migration]
epic_branch: epic/PRD-008-chat-sessions
plan: null
report: null
commit: null
depends_on: [STORY-002]
blocks: [STORY-004, STORY-005, STORY-008]
skills: []
created: 2026-09-02
updated: 2026-09-02
---

# STORY-003: init_db() creates both transcript tables and converges the audit_logs.session_id column

## Description

As a maintainer, I want the new schema created by the same idempotent bootstrap every other table uses, so that a hot reload, a second instance, and a fresh database all converge on the same shape without a migration tool.

## Acceptance Criteria

- [ ] Given [app/db/database.py](../../../app/db/database.py)'s `init_db()`, when it runs, then it executes `CREATE_CHAT_SESSIONS_TABLE`, `CREATE_CHAT_MESSAGES_TABLE` and both indexes inside the **same** `_session()` block that already creates `audit_logs` and `users`.
- [ ] Given a database that already has every table, when `init_db()` runs again, then it issues **no `ALTER`** — the assertion `test_init_db_issues_no_alter_when_schema_is_current` in [tests/test_db.py](../../../tests/test_db.py) passes with the new column present.
- [ ] Given a database created before this PRD, when `init_db()` runs, then `_add_missing_columns` adds `session_id` to `audit_logs`, every existing row takes `NULL`, and no row is rewritten.
- [ ] Given two processes calling `init_db()` against one database at the same moment, when both attempt the `session_id` `ALTER`, then the loser converges rather than crashing — the existing `_is_duplicate_column` path handles it and needs no change. Assert it, do not assume it.
- [ ] Given `settings.DB_BOOTSTRAP_ENABLED=False`, when `init_db()` is called, then it returns before touching the database, exactly as today — the Dockerfile builder stage still imports `chat_ui.chat_ui` with no reachable database.
- [ ] Given `PRAGMA table_info(chat_messages)` after a fresh `init_db()`, when it is read, then the column set matches [[STORY-002]]'s DDL exactly, and `duplicate_relative_info` / `duplicate_release_info` are absent.
- [ ] Given the full suite, when it runs, then [tests/test_db.py](../../../tests/test_db.py) passes with new coverage for both tables and the new column, and every other suite passes unmodified.

## Technical Notes

- File: [app/db/database.py](../../../app/db/database.py), `init_db()` only. No new function in this story — the CRUD lands in [[STORY-004]] and [[STORY-005]].
- `_add_missing_columns` needs **no edit**: it iterates `AUDIT_LOGS_ADDED_COLUMNS`, and [[STORY-002]] put `session_id` there. If you find yourself editing that function, stop and ask why.
- The docstring on `_add_missing_columns` already records why the concurrent case is safe, verbatim: "`ALTER TABLE ADD COLUMN` has no `IF NOT EXISTS` form, so this is the one non-idempotent step in `init_db()` -- the rest is `CREATE ... IF NOT EXISTS` by construction... So the loser treats that one condition as success and converges." This story adds a column to that path; it does not change the rule.
- PRD Risk 7 is what this story discharges: "`init_db()` gains two more `CREATE TABLE` statements and one more `ALTER` candidate. It runs at import time on every Reflex hot reload and on every instance boot."
- Note the two entry points that call `init_db()` and rely on this being cheap in steady state: [app/main.py](../../../app/main.py)'s lifespan and [chat_ui/chat_ui/chat_ui.py:33](../../../chat_ui/chat_ui/chat_ui.py) at import time, the latter on every Reflex hot reload.
- `.agents/skills/` was scanned: only `frontend-design` is present, scoped to visual design of UI. This story touches no UI. No skill applies.

## Dependencies

- **Blocked by**: STORY-002
- **Blocks**: STORY-004, STORY-005, STORY-008

## PRD Reference

Source: [`PRD-008/PRD.md`](../../PRDs/PRD-008-chat-sessions/PRD.md) — Section 4 (Schema), Section 8, Section 11 (init_db assertions), Section 12 Phase 1, Risk 7
