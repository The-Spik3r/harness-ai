---
id: STORY-016
prd: PRD-008
slug: session-rename-delete-logout
title: "New chat, rename, delete, and a logout that clears state without deleting rows"
type: feature
priority: high
complexity: medium
phase: "3 - State and restore"
status: todo
labels: [ui, reflex, state, security]
epic_branch: epic/PRD-008-chat-sessions
plan: null
report: null
commit: null
depends_on: [STORY-013, STORY-015]
blocks: [STORY-018, STORY-021]
skills: [reflex-docs]
created: 2026-09-02
updated: 2026-09-02
---

# STORY-016: New chat, rename, delete, and a logout that clears state without deleting rows

## Description

As an employee, I want to delete a conversation I no longer want on screen, so that the list stays mine (PRD Section 5, story 4) — and I want signing out on a shared machine to take my transcripts off the screen without taking them out of my account.

## Acceptance Criteria

- [ ] Given `new_chat()`, when it runs, then `active_session_id` and `messages` are cleared and **no row is written** — the next send creates the session, per [[STORY-013]]'s lazy rule.
- [ ] Given `new_chat()` called twice with no send in between, when the database is inspected, then no session exists.
- [ ] Given `rename_session(session_id, title)`, when it runs on an owned session, then the title persists, the rail updates, and `updated_at` is **not** touched — a rename is not activity and must not reorder the rail under the user's cursor.
- [ ] Given a rename to an empty or whitespace title, when it is submitted, then it is refused and the existing title stands.
- [ ] Given `delete_session(session_id)`, when it is confirmed, then the session and its messages are removed, the rail drops the row, and `count_audit_logs()` is unchanged.
- [ ] Given the active session being deleted, when the delete completes, then the UI lands on the next most recent session, or on the empty state if none remains — never on a transcript belonging to a deleted id.
- [ ] Given a delete, when the user is asked to confirm, then the prompt names the chat by title and states that the audit record is unaffected.
- [ ] Given `logout()`, when it runs, then `sessions`, `active_session_id`, `messages`, `_token`, `user_id` and `sessions_error` are all cleared, and **every row survives in the database** — asserted by counting sessions and messages across the logout.
- [ ] Given a signed-out user, when they sign back in, then their sessions are listed again.
- [ ] Given a foreign `session_id` submitted to `rename_session` or `delete_session`, when it runs, then nothing changes in the database and the rail is unaffected.
- [ ] Given [tests/test_chat_state.py](../../../tests/test_chat_state.py), when it runs, then each of the above is asserted at state level, including the row counts across logout.

## Technical Notes

- File: [chat_ui/chat_ui/state.py](../../../chat_ui/chat_ui/state.py). The confirmation UI itself is [[STORY-018]]; this story provides the event handlers and the copy it will call.
- `logout()`'s existing docstring already states the principle this story extends, verbatim: "Ends the session. The transcript goes with it: the header names who is sending, so leaving one user's prompts on screen under another's ID would misattribute them in a surface people read as a record." Clearing the *rail* is the same argument — a session list is a list of one person's subjects.
- The distinction that must be explicit in the code and in the report: `logout()` clears state, `delete_session()` deletes rows. Conflating them is the destructive bug in this story's neighbourhood.
- PRD Section 9, verbatim, governs the confirmation copy: "`delete_chat_session` removes rows from `chat_sessions` and `chat_messages` only. `audit_logs` is append-only and stays so... The confirmation copy says this in the user's words." Per the **frontend-design** skill: "Write from the end user's side of the screen. Name things by what people control and recognize, never by how the system is built" — so the copy says the record of what was checked is kept, not that `audit_logs` rows are retained.
- Also per that skill, verbatim: "An action keeps the same name through the whole flow, so the button that says 'Publish' produces a toast that says 'Published.'" The control is **New chat** and what it produces is a chat; **Delete** confirms with **Delete** and not with **Remove**.
- Rename must not call `derive_title` again. [[STORY-012]] derives once, at creation; a rename that re-derives on the next send would silently undo the user's edit.
- Per `chat_ui/AGENTS.md`, verbatim: "For anything about Reflex APIs — components, state management, events, styling, database, routing, authentication — use the **reflex-docs** skill rather than relying on memory."
- All service calls go through `asyncio.to_thread(...)`; all state mutation inside `async with self`.
- `.agents/skills/` was scanned: `frontend-design` applies to the copy quoted above; the rail's visual design is [[STORY-017]] and [[STORY-018]].

## Dependencies

- **Blocked by**: STORY-013, STORY-015
- **Blocks**: STORY-018, STORY-021

## PRD Reference

Source: [`PRD-008/PRD.md`](../../PRDs/PRD-008-chat-sessions/PRD.md) — Section 4 (Chat state), Section 5 (story 4), Section 6.1 (Copy), Section 9 (Deletion semantics), Section 12 Phase 3
