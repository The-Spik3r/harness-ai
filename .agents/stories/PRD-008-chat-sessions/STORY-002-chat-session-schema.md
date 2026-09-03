---
id: STORY-002
prd: PRD-008
slug: chat-session-schema
title: "chat_sessions and chat_messages DDL and dataclasses in app/db/models.py"
type: feature
priority: high
complexity: small
phase: "1 - Schema and store"
status: done
labels: [backend, database, schema]
epic_branch: epic/PRD-008-chat-sessions
plan: .agents/plans/PRD-008-chat-sessions/completed/STORY-002-chat-session-schema.plan.md
report: .agents/reports/PRD-008-chat-sessions/STORY-002-chat-session-schema.report.md
commit: null
depends_on: []
blocks: [STORY-003, STORY-004, STORY-005]
skills: []
created: 2026-09-02
updated: 2026-09-03
---

# STORY-002: chat_sessions and chat_messages DDL and dataclasses in app/db/models.py

## Description

As a maintainer, I want the two transcript tables declared alongside `audit_logs` and `users`, so that a conversation has a shape in the schema before anything tries to write one.

## Acceptance Criteria

- [ ] Given [app/db/models.py](../../../app/db/models.py), when it is read, then `CREATE_CHAT_SESSIONS_TABLE` declares `session_id TEXT PRIMARY KEY NOT NULL`, `user_id TEXT NOT NULL`, `title TEXT NOT NULL`, `created_at TEXT NOT NULL`, `updated_at TEXT NOT NULL`.
- [ ] Given `session_id` and `user_id`, when the DDL is inspected, then both declare `NOT NULL` **explicitly**. The `users` table's comment states the reason verbatim: "outside INTEGER PRIMARY KEY, SQLite lets a PRIMARY KEY column hold NULL, and more than one row of them."
- [ ] Given `CREATE_CHAT_MESSAGES_TABLE`, when it is read, then it declares `id INTEGER PRIMARY KEY AUTOINCREMENT`, `session_id TEXT NOT NULL`, `kind TEXT NOT NULL`, `content TEXT NOT NULL`, `created_at TEXT NOT NULL`, plus one column for each metadata field on [chat_ui/chat_ui/models.py](../../../chat_ui/chat_ui/models.py)'s `ChatMessage` that a restored bubble needs: `prompt`, `model_used`, `tokens_used`, `audit_id`, `pii_redacted`, `pii_entities`, `pattern`, `required_permission`, `first_query_at`, `detail`.
- [ ] Given `duplicate_relative_info` and `duplicate_release_info`, when the DDL is inspected, then **neither has a column**. PRD Section 6: "the humanized copy is recomputed on load, not stored, so it stays relative to *now*" — a stored "2m ago" is wrong the moment it is read back.
- [ ] Given `CREATE_CHAT_SESSIONS_USER_INDEX` and `CREATE_CHAT_MESSAGES_SESSION_INDEX`, when they are read, then they are `CREATE INDEX IF NOT EXISTS` over `chat_sessions(user_id, updated_at DESC)` and `chat_messages(session_id, id)` respectively — the two access paths every read in [[STORY-004]] and [[STORY-005]] takes.
- [ ] Given `AUDIT_LOGS_ADDED_COLUMNS`, when it is read, then `"session_id": "TEXT"` is present — nullable, no default, so `test_added_columns_declaring_not_null_also_declare_a_default` in [tests/test_db.py](../../../tests/test_db.py) continues to hold unmodified.
- [ ] Given `AuditLog`, when it is read, then it carries `session_id: Optional[str] = None`, positioned so no existing positional construction breaks.
- [ ] Given the module, when it is read, then `ChatSession` and `StoredMessage` dataclasses mirror their tables, in the style of `AuditLog` and `User`.
- [ ] Given [tests/test_db.py](../../../tests/test_db.py), when the suite runs, then it passes with the new DDL constants asserted for the `IF NOT EXISTS` clause and for the explicit `NOT NULL` on both key columns.

## Technical Notes

- File: [app/db/models.py](../../../app/db/models.py) only. This story creates no table and executes no SQL — [[STORY-003]] wires `init_db()`.
- **No foreign key on `chat_messages.session_id`.** SQLite enforces foreign keys only when `PRAGMA foreign_keys=ON` is set per connection, and the shared libSQL client from PRD-007 gives no place to guarantee that on every path. A declared-but-unenforced constraint reads as a guarantee and is not one. [[STORY-004]]'s `delete_chat_session` deletes both tables in one transaction instead, which is the enforcement.
- The `AUDIT_LOGS_ADDED_COLUMNS` comment block already states the constraint this story must respect, verbatim: "Additive only: no drops, renames, or type changes. Every NOT NULL entry needs a non-NULL DEFAULT -- SQLite rejects ADD COLUMN NOT NULL without one." `session_id TEXT` is nullable and therefore compliant, and nullable is also correct on the merits: PRD Section 10 requires a request that omits `session_id` to write `NULL`.
- `pii_entities` on `chat_messages` stores the comma-joined string, matching how [app/services/audit_logger.py:45](../../../app/services/audit_logger.py) already persists the same data. Do not invent JSON here; one encoding for one concept.
- `pii_redacted` stores `INTEGER NOT NULL DEFAULT 0`, matching the boolean convention `audit_logs` uses throughout.
- Do **not** add an `archived` column. It appeared in an early scope draft and is not in PRD Section 4's final list; deletion is the only lifecycle operation this PRD ships.
- `.agents/skills/` was scanned: only `frontend-design` is present, scoped to visual design of UI. This story touches no UI. No skill applies.

## Dependencies

- **Blocked by**: None
- **Blocks**: STORY-003, STORY-004, STORY-005

## PRD Reference

Source: [`PRD-008/PRD.md`](../../PRDs/PRD-008-chat-sessions/PRD.md) — Section 4 (Schema), Section 6 (stored message table, Ordering), Section 12 Phase 1, Risk 7
