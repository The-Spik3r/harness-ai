---
id: STORY-005
prd: PRD-008
slug: message-store-functions
title: "append_chat_message and list_chat_messages, ordered by id and scoped by owner"
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

# STORY-005: append_chat_message and list_chat_messages, ordered by id and scoped by owner

## Description

As a maintainer, I want messages appended and read back in a fixed order under an ownership check, so that a restored transcript is the same transcript, in the same sequence, and only for the person who wrote it.

## Acceptance Criteria

- [ ] Given [app/db/database.py](../../../app/db/database.py), when it is read, then it declares `append_chat_message(message, session_id, user_id) -> int`, `list_chat_messages(session_id, user_id) -> list[StoredMessage]` and `count_chat_sessions(user_id) -> int`.
- [ ] Given all three signatures, when they are inspected, then `user_id: str` is required and undefaulted, and each statement scopes on ownership — `append_chat_message` writes only after confirming the session belongs to `user_id`, in the same transaction as the insert.
- [ ] Given `list_chat_messages`, when it is called, then the statement reads `ORDER BY id ASC` and **not** by any timestamp column. PRD Section 6: "a transcript that reorders itself on reload would be a visible instance of the same defect."
- [ ] Given twenty messages appended inside one second, when they are read back, then their order is exactly the order they were appended — the case a timestamp sort gets wrong and the reason the criterion above is written as a statement inspection and a behavioural test.
- [ ] Given `list_chat_messages(session_id, foreign_user_id)`, when it is called, then it returns an empty list, not the rows.
- [ ] Given `append_chat_message(message, session_id, foreign_user_id)`, when it is called, then no row is written and the failure is visible to the caller — a silent no-op here would look like a working write in [[STORY-014]]'s degraded arm.
- [ ] Given each of the seven `ChatMessage` kinds — `user`, `assistant`, `duplicate`, `injection`, `forbidden`, `upstream_error`, `internal_error` — when one is appended and read back, then every stored field round-trips unchanged, including `pii_entities` through its comma-joined encoding and `tokens_used`/`audit_id` as integers.
- [ ] Given [tests/test_chat_sessions.py](../../../tests/test_chat_sessions.py), when it runs, then the round trip is asserted per kind rather than once for a representative kind.

## Technical Notes

- File: [app/db/database.py](../../../app/db/database.py). New functions only.
- `StoredMessage` from [[STORY-002]] is the return type. This layer does **not** import from `chat_ui/` — the rehydration into a Reflex `ChatMessage` happens in [[STORY-015]], on the UI side of the boundary. `app/` has never imported `chat_ui/` and this PRD does not start.
- `pii_entities` round-trips through `",".join(...)` / `split(",")`, the encoding [app/services/audit_logger.py:45](../../../app/services/audit_logger.py) already uses. An empty list stores `NULL` and reads back as `[]`, not as `[""]` — the split of an empty string is the classic bug here and deserves its own assertion.
- The ownership check on `append_chat_message` must be part of the same transaction as the insert, not a read followed by a write. Two statements outside a transaction is a TOCTOU gap on a table whose id comes from a client-visible var (PRD Risk 3).
- Do not add a `limit` to `list_chat_messages`. A partial transcript is a wrong transcript, and PRD Section 4 caps sessions, not messages within one. If message volume becomes a problem it is a paging design, not a silent truncation.
- `count_chat_sessions(user_id)` exists so the rail can state its cap against a true total, the way PRD-006's register states "100 most recent of 3,180".
- `.agents/skills/` was scanned: only `frontend-design` is present, scoped to visual design of UI. This story touches no UI. No skill applies.

## Dependencies

- **Blocked by**: STORY-002, STORY-003
- **Blocks**: STORY-006, STORY-007

## PRD Reference

Source: [`PRD-008/PRD.md`](../../PRDs/PRD-008-chat-sessions/PRD.md) — Section 4 (Data access), Section 6 (stored message table, Ordering), Section 12 Phase 1, Risk 2
