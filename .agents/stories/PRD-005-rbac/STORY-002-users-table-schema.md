---
id: STORY-002
prd: PRD-005
slug: users-table-schema
title: users table schema and CRUD helpers
type: technical
priority: high
complexity: small
phase: "Phase 1 — Identity foundation"
status: todo
labels: [backend, database]
epic_branch: epic/PRD-005-rbac
plan: null
report: null
commit: null
depends_on: [STORY-001]
blocks: [STORY-003, STORY-016]
skills: []
created: 2026-08-28
updated: 2026-08-28
---

# STORY-002: users table schema and CRUD helpers

## Description

As a maintainer, I want a `users` table with CRUD helpers in the existing SQLite database, so that identity has a storage home without adding a dependency or a second service.

## Acceptance Criteria

- [ ] Given a fresh database, when `init_db()` runs, then `users(user_id TEXT PRIMARY KEY, role TEXT NOT NULL, token_hash TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL)` exists
- [ ] Given a `token_hash`, when `find_user_by_token_hash()` is called, then the matching **active** user is returned and a deactivated one is not
- [ ] Given a user id, when `deactivate_user()` is called, then `active` becomes `0` and the row is retained — revocation is not deletion, so historical audit rows keep resolving the id
- [ ] Given an empty table, when `count_active_users()` is called, then it returns `0`
- [ ] Given an index on `token_hash`, when a lookup runs, then it does not table-scan

## Technical Notes

- `CREATE_USERS_TABLE` in `app/db/models.py`, executed by `init_db()` next to the audit table; a `User` dataclass mirroring the shape of `AuditLog`.
- Helpers in `app/db/database.py` follow the existing module convention exactly: one `with get_connection() as conn:` per function, `sqlite3.Row` factory, no ORM, no shared connection.
- `created_at` uses the same `%Y-%m-%dT%H:%M:%SZ` UTC format as `audit_logger.py`.
- Tests: `tests/test_db.py`.

## Dependencies

- **Blocked by**: STORY-001
- **Blocks**: STORY-003, STORY-016

## PRD Reference

Source: [`PRD-005/PRD.md`](../../PRDs/PRD-005-rbac/PRD.md) — sections 4 and 6
