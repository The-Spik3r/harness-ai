---
id: STORY-006
prd: PRD-007
slug: libsql-connection-layer
title: "Swap app/db/database.py onto a shared libSQL client, preserving all 22 public signatures"
type: feature
priority: high
complexity: large
phase: "2 - Storage layer swap"
status: done
labels: [backend, database, turso, libsql, tests]
epic_branch: epic/PRD-007-turso-migration
plan: .agents/plans/PRD-007-turso-migration/completed/STORY-006-libsql-connection-layer.plan.md
report: .agents/reports/PRD-007-turso-migration/STORY-006-libsql-connection-layer.report.md
commit: 86ece73
depends_on: [STORY-001, STORY-003, STORY-004, STORY-005]
blocks: [STORY-007, STORY-008, STORY-009, STORY-010, STORY-013, STORY-014]
skills: []
created: 2026-09-01
updated: 2026-09-01
---

# STORY-006: Swap app/db/database.py onto a shared libSQL client, preserving all 22 public signatures

## Description

As a maintainer, I want `app/db/database.py` running on libSQL with an unchanged public surface, so that the ~40 call sites across routers, services, chat UI, and the CLI need no edits and the migration stays confined to one module.

This is the atomic heart of the epic. Every prior story exists to make this one verifiable: [[STORY-001]] answered what the driver can do, [[STORY-002]] and [[STORY-004]] pinned and relocated the error behavior, [[STORY-003]] put the test database behind one fixture, and [[STORY-005]] made the configuration libSQL-shaped.

## Acceptance Criteria

- [ ] Given [app/db/database.py](../../../app/db/database.py), when it is read, then `_db_path()` and the `sqlite3`-based `get_connection()` are gone, replaced by a **process-wide client constructed once and reused**. PRD Section 6 Pattern 1: against a remote endpoint each construction is a TCP + TLS handshake, so "a single admin console load would pay ten handshakes."
- [ ] Given the module's 22 public functions, when their signatures are compared to `main`, then every name, parameter, default, and return type is identical. No caller outside `app/db/` is modified by this story.
- [ ] Given any read, when a row is consumed, then column access by name still works — `row["timestamp"]`, `row["n"]`, `row["model_used"]` — and `_row_to_audit_log()` and `_row_to_user()` map their full field sets correctly, including the boolean coercions (`bool(row["success"])`, `bool(row["active"])`) and the five PRD-003/PRD-005 columns.
- [ ] Given any `INSERT`, `UPDATE`, or `ALTER`, when the operation returns, then the write is durably committed — verified by reading it back **through a separate, freshly constructed client**, not through the writing one. This is Risk 1 and the single most dangerous failure mode in the epic: a lost `insert_audit_log()` is invisible until someone reads an empty audit trail.
- [ ] Given `insert_audit_log(entry)`, when it returns, then the value is the new `audit_logs.id` and `get_audit_log(that_id)` retrieves the same row.
- [ ] Given `deactivate_user(user_id)` and `set_user_token_hash(user_id, hash)`, when the target exists, then each returns `True`; when it does not, each returns `False`. The zero-row case is the one that regresses silently if the driver reports affected rows differently.
- [ ] Given `tests/conftest.py` from [[STORY-003]], when the fixture is flipped to provision a **local libSQL server** database, then every test obtains an isolated, empty database over that endpoint, and no test reads or writes a `.db` file.
- [ ] Given the full suite, when it runs with no network access and no Turso account, then it passes. Offline and account-free are non-negotiable properties, not aspirations.
- [ ] Given the [[STORY-002]] characterization tests, when they run, then all pass **unmodified**.
- [ ] Given `grep -rn "sqlite3" app/ chat_ui/ scripts/`, when it runs, then there are no hits.
- [ ] Given [requirements.txt](../../../requirements.txt), when it is read, then the libSQL client is present, pinned to the exact version named in [[STORY-001]]'s decision record.

## Technical Notes

- Files: [app/db/database.py](../../../app/db/database.py) (the bulk), `tests/conftest.py` (fixture implementation flip), [requirements.txt](../../../requirements.txt). No other production file.
- **This story is `large` and cannot be split further.** The swap is atomic: `get_connection()` is a single chokepoint used by all 22 functions, so there is no intermediate commit where half the module speaks libSQL and the suite is green. Splitting it would trade one large green commit for two red ones. Budget accordingly and lean on [[STORY-001]]'s decision record instead of discovering behavior here.
- Use the **synchronous** client interface. PRD Section 6 Pattern 2 is explicit about why: every consumer is already synchronous — [app/routers/admin.py:30](../../../app/routers/admin.py) and `:70` and [app/routers/query.py:16](../../../app/routers/query.py) are plain `def` endpoints that FastAPI dispatches to a threadpool, `run_query(...)` at [app/services/query_pipeline.py:45](../../../app/services/query_pipeline.py) is `def`, and `scripts/manage_users.py` is a CLI. Going async "would force `async` through all 22 database functions and every caller — a change an order of magnitude larger than the migration itself."
- One consequence of the shared client to check deliberately: [chat_ui/chat_ui/admin_state.py](../../../chat_ui/chat_ui/admin_state.py) calls these functions from `asyncio.to_thread(...)` (PRD-006 STORY-004), so the client is reached from worker threads. `sqlite3` connections were per-call and thread-confined precisely because a connection is not shareable across threads. Confirm the libSQL client's thread-safety before hoisting it to module scope — if it is not thread-safe, the correct answer is a thread-local or pooled client, not a per-call one.
- Do **not** implement `init_db()` concurrency safety here. That is [[STORY-007]], and keeping it separate keeps this story's diff readable. Getting `init_db()` merely working single-process is sufficient for this commit.
- Do **not** batch reads or rewrite `top_pii_entities()` here. Those are [[STORY-009]] and [[STORY-010]]. This story is a like-for-like swap; the network-cost work follows it.
- `app/db/models.py` should need no changes — the DDL (`INTEGER PRIMARY KEY AUTOINCREMENT`, `TEXT`, `CREATE UNIQUE INDEX`, `ALTER TABLE ADD COLUMN`) is libSQL-compatible as-is. If it does need changing, that is a finding worth recording in the report.
- Every statement already uses `?` placeholders, so no SQL text needs rewriting. If you find yourself editing a `SELECT`, stop and ask why.
- `.agents/skills/` was scanned: only `frontend-design` is present, scoped to visual design of UI. This story touches no UI. No skill applies.

## Dependencies

- **Blocked by**: STORY-001, STORY-003, STORY-004, STORY-005
- **Blocks**: STORY-007, STORY-008, STORY-009, STORY-010, STORY-013, STORY-014

## PRD Reference

Source: [`PRD-007/PRD.md`](../../PRDs/PRD-007-turso-migration/PRD.md) — Section 6 Patterns 1 & 2, Section 7.1, Section 7.6, Section 8, Section 12 Phase 2, Section 14 Risk 1
