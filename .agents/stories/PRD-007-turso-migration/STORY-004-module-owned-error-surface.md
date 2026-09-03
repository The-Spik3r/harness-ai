---
id: STORY-004
prd: PRD-007
slug: module-owned-error-surface
title: "app/db/errors.py: a module-owned exception surface, decoupling the three catch sites from sqlite3"
type: technical
priority: high
complexity: small
phase: "2 - Storage layer swap"
status: done
labels: [backend, database, errors, rbac]
epic_branch: epic/PRD-007-turso-migration
plan: .agents/plans/PRD-007-turso-migration/completed/STORY-004-module-owned-error-surface.plan.md
report: .agents/reports/PRD-007-turso-migration/STORY-004-module-owned-error-surface.report.md
commit: 2961f33
depends_on: [STORY-002]
blocks: [STORY-006]
skills: []
created: 2026-09-01
updated: 2026-09-01
---

# STORY-004: app/db/errors.py: a module-owned exception surface, decoupling the three catch sites from sqlite3

## Description

As a maintainer, I want `app/db/` to raise its own exceptions rather than leaking the driver's, so that swapping the driver in [[STORY-006]] cannot silently break a `catch` clause somewhere else in the codebase.

`app/db/database.py` is already the only module that knows how data is stored — except for its exception types, which two other modules import `sqlite3` specifically to catch. This story closes that last leak **while still running on `sqlite3`**, so the change is verifiable against the characterization tests from [[STORY-002]] before anything else moves.

## Acceptance Criteria

- [ ] Given `app/db/errors.py`, when it is read, then it declares an exception surface covering the three conditions the codebase distinguishes today: an integrity violation (duplicate `user_id` or `token_hash`), a missing-relation condition (the `users` table does not exist), and a general storage failure. The integrity error carries enough information for a caller to tell a duplicate `user_id` from a duplicate `token_hash`.
- [ ] Given `app/db/database.py`, when any driver exception escapes a query, then it is translated to a `app/db/errors.py` type at the module boundary. No driver exception reaches a caller.
- [ ] Given [app/services/duplicate_checker.py:32](../../../app/services/duplicate_checker.py), when it is read, then it no longer imports `sqlite3` and catches the module-owned storage error instead. Its behavior is unchanged: a storage failure degrades the duplicate check without failing the query.
- [ ] Given [scripts/manage_users.py:37](../../../scripts/manage_users.py), when it is read, then it no longer imports `sqlite3` and catches the module-owned integrity error instead, still reporting duplicate `user_id` and duplicate `token_hash` distinguishably.
- [ ] Given [app/db/database.py:289](../../../app/db/database.py), when `find_user_by_token_hash(...)` runs against a database with no `users` table, then it still returns `None` — **401, not 500** — now via the module-owned missing-relation type.
- [ ] Given `grep -rn "import sqlite3" app/ chat_ui/ scripts/`, when it runs, then the only hit is inside `app/db/`.
- [ ] Given the [[STORY-002]] characterization tests, when they run after this change, then all pass **unmodified**. If one needs editing, the behavior changed and the story is not done.

## Technical Notes

- Files: new `app/db/errors.py`; modified `app/db/database.py`, `app/services/duplicate_checker.py`, `scripts/manage_users.py`. Possibly `app/db/__init__.py` for the export.
- Keep the surface small. PRD Section 7.2 specifies exactly three conditions; do not invent a taxonomy the codebase does not use. Every exception type that exists must have a caller that catches it specifically.
- `insert_user()`'s existing docstring documents the contract this story formalizes: it "raises `sqlite3.IntegrityError` on a duplicate `user_id` or `token_hash` -- deliberately not caught here; `app/db/` has no error handling anywhere and the caller needs to tell those two cases apart." Update that docstring to name the new type, and preserve "deliberately not caught here" — the translation happens at the boundary, the *handling* stays with the caller.
- The missing-relation arm exists for one reason, stated at [app/db/database.py](../../../app/db/database.py): "A `users` table that hasn't been created yet (`init_db()` never ran against this connection) is folded into the same 'no match' outcome rather than raised -- callers resolving a credential need a closed door, not a 500." Do not broaden that catch while translating it. Catching more than the missing-relation case here would turn a real storage outage into a silent 401.
- Translation belongs at the `app/db/database.py` boundary, not inside `errors.py`. `errors.py` should be importable without importing a driver.
- This story deliberately runs on `sqlite3` still. That is the point: it isolates a refactor with a verifiable green baseline from the driver swap that has none.
- `.agents/skills/` was scanned: only `frontend-design` is present, scoped to visual design of UI. This story touches no UI. No skill applies.

## Dependencies

- **Blocked by**: STORY-002
- **Blocks**: STORY-006

## PRD Reference

Source: [`PRD-007/PRD.md`](../../PRDs/PRD-007-turso-migration/PRD.md) — Section 6 Pattern 6, Section 7.2, Section 11 (functional requirements), Section 12 Phase 2
