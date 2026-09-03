---
id: STORY-004
prd: PRD-008
slug: session-crud-functions
title: "Six user-scoped chat_sessions functions in database.py, with delete as one transaction"
type: feature
priority: high
complexity: medium
phase: "1 - Schema and store"
status: todo
labels: [backend, database, security]
epic_branch: epic/PRD-008-chat-sessions
plan: null
report: null
commit: null
depends_on: [STORY-002, STORY-003]
blocks: [STORY-006, STORY-007]
skills: []
created: 2026-09-02
updated: 2026-09-02
---

# STORY-004: Six user-scoped chat_sessions functions in database.py, with delete as one transaction

## Description

As a maintainer, I want the session table reachable through functions that cannot be called without naming an owner, so that the first row-level authorization in this codebase is a property of the signatures rather than a habit callers have to keep.

## Acceptance Criteria

- [ ] Given [app/db/database.py](../../../app/db/database.py), when it is read, then it declares `create_chat_session`, `get_chat_session`, `list_chat_sessions`, `rename_chat_session`, `touch_chat_session` and `delete_chat_session`.
- [ ] Given every one of those six signatures, when it is inspected, then `user_id: str` is **required and undefaulted**, and every statement they issue carries `WHERE ... user_id = ?`. PRD Risk 2: "a missing `WHERE user_id = ?` returns data rather than an error."
- [ ] Given `get_chat_session(session_id, user_id)` where the row exists but belongs to another user, when it is called, then it returns `None` — not the row, and not an exception that distinguishes "yours but missing" from "someone else's".
- [ ] Given `list_chat_sessions(user_id, limit)`, when it is called, then it returns that user's sessions ordered `updated_at DESC`, capped at `limit`, and never a row belonging to anyone else.
- [ ] Given `rename_chat_session` and `touch_chat_session`, when the target exists and is owned, then each returns `True`; when it does not exist, or exists under another user, then each returns `False` — the zero-row case, which PRD-007 STORY-006 already flagged as the one that regresses silently.
- [ ] Given `delete_chat_session(session_id, user_id)`, when it is called on an owned session, then the session row and every one of its `chat_messages` rows are removed **inside one `_session()` block**, and `count_audit_logs()` is identical before and after.
- [ ] Given `delete_chat_session` called with a foreign `user_id`, when it returns, then it returns `False` and **no message row is deleted** — the message delete is scoped by the same ownership check, not merely by `session_id`.
- [ ] Given `create_chat_session`, when it returns, then the new `session_id` is a UUID4 string and `get_chat_session` retrieves the same row through a separate call.
- [ ] Given [tests/test_chat_sessions.py](../../../tests/test_chat_sessions.py), when it runs, then two users are created and every read and write path is driven with the other user's id, asserting empty or `False` in each case.

## Technical Notes

- File: [app/db/database.py](../../../app/db/database.py). New functions only — do not touch the existing 22, and do not reorganize the module.
- Follow the established shape exactly: `with _session() as conn:`, `?` placeholders, `_row_to_chat_session(row)` mapping in the style of `_row_to_user` at [app/db/database.py:1081](../../../app/db/database.py).
- Ids are generated **here**, with `uuid.uuid4()`, not by the caller. A caller-supplied id is a caller-chosen id, and the UI's `active_session_id` is a client-visible Reflex var (PRD Risk 3) — letting it name a new row would let a client pick primary keys.
- Timestamps use the module's existing `"%Y-%m-%dT%H:%M:%SZ"` format, so `updated_at` sorts lexically. Note the known consequence, already recorded in PRD-006 Section 13: second-resolution TEXT timestamps tie. For the rail's ordering a tie is cosmetic; for the transcript it is not, which is why [[STORY-005]] orders by `id` instead.
- `rename_chat_session` sets `title` and leaves `updated_at` alone — renaming is not activity, and a rename that reordered the rail would move the row the user was just looking at.
- `delete_chat_session` deletes `chat_messages` first, then `chat_sessions`, in one transaction. [[STORY-002]] deliberately declared no foreign key; this transaction is the enforcement, and the story that removes it must replace it with something.
- **`audit_logs` is not touched by any function in this story.** PRD Section 9: "the orphaned `session_id` on those rows is expected, and it is what preserves the evidence when a user tidies their list." Assert `count_audit_logs()` across the delete rather than trusting the absence of a statement.
- `.agents/skills/` was scanned: only `frontend-design` is present, scoped to visual design of UI. This story touches no UI. No skill applies.

## Dependencies

- **Blocked by**: STORY-002, STORY-003
- **Blocks**: STORY-006, STORY-007

## PRD Reference

Source: [`PRD-008/PRD.md`](../../PRDs/PRD-008-chat-sessions/PRD.md) — Section 4 (Data access), Section 6 (Ownership as a signature rule), Section 9 (Deletion semantics), Section 12 Phase 1, Risk 2
