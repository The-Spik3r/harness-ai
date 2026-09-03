---
id: STORY-013
prd: PRD-008
slug: chat-state-session-list-and-lazy-create
title: "ChatState holds the session list, creates lazily on first send, and passes session_id to run_query"
type: feature
priority: high
complexity: large
phase: "3 - State and restore"
status: todo
labels: [ui, reflex, state, backend]
epic_branch: epic/PRD-008-chat-sessions
plan: null
report: null
commit: null
depends_on: [STORY-006, STORY-009, STORY-012]
blocks: [STORY-014, STORY-016, STORY-018]
skills: [reflex-docs, reflex-process-management]
created: 2026-09-02
updated: 2026-09-02
---

# STORY-013: ChatState holds the session list, creates lazily on first send, and passes session_id to run_query

## Description

As an employee, I want to keep separate conversations for separate subjects, so that starting a new line of enquiry does not bury the previous one (PRD Section 5, story 2).

This story gives `ChatState` the concept of a current conversation. It does not yet write a transcript ([[STORY-014]]) or read one back ([[STORY-015]]) — it establishes which session a send belongs to, and proves that an idle tab creates nothing.

## Acceptance Criteria

- [ ] Given [chat_ui/chat_ui/state.py](../../../chat_ui/chat_ui/state.py), when `ChatState` is read, then it declares `sessions: list[ChatSessionSummary]`, `active_session_id: str` and `sessions_error: str`.
- [ ] Given a successful sign-in, when `login()` completes, then the session list is loaded through `chat_sessions.list_for(identity)` and the rail's data is in state — with the read offloaded via `asyncio.to_thread(...)`.
- [ ] Given a user who opens the app and sends nothing, when the database is inspected, then **no `chat_sessions` row exists**. PRD Section 4: "a session row is written on the first send, never on page load — an opened-and-abandoned tab leaves nothing behind."
- [ ] Given the first send in a new chat, when it runs, then exactly one session is created, titled from that prompt, and `active_session_id` is set before `run_query` is called.
- [ ] Given a second send in the same chat, when it runs, then **no** session is created and the existing `active_session_id` is reused.
- [ ] Given any send, when `run_query(...)` is invoked, then it receives `session_id=self.active_session_id` — so the audit row carries it on every outcome, including the blocked and failed ones from [[STORY-009]].
- [ ] Given `settings.CHAT_HISTORY_ENABLED is False`, when a send runs, then no session is created, `active_session_id` stays empty, `run_query` receives `None`, and the send otherwise behaves exactly as it does today.
- [ ] Given a `ChatSessionError` while loading or creating, when it is raised, then `sessions_error` is set and **the send still proceeds** — a broken rail does not block the composer.
- [ ] Given the in-flight guard, when session creation is added, then the `pending` flag still clears on every path — the `try/finally` that PRD-004 Risk 3 exists to protect is not broken by the new failure mode.
- [ ] Given [tests/test_chat_state.py](../../../tests/test_chat_state.py), when it runs, then the existing assertions pass and new ones drive the state directly: one send creates one session, two sends create one, an idle mount creates none, and the flag-off path creates none.

## Technical Notes

- File: [chat_ui/chat_ui/state.py](../../../chat_ui/chat_ui/state.py). `_do_send` is where the lazy creation goes — after the `pending` claim and after `resolve(token)`, before the `run_query` call.
- `ChatState` calls `app/services/chat_sessions.py`, **never** [app/db/database.py](../../../app/db/database.py) directly. PRD Section 6 fixes that boundary, and it is the same one `ChatState` already holds by calling `run_query(...)` rather than the pipeline's internals.
- The Identity is re-resolved on every send and must be the one passed to the service. Do not add a `user_id` field to the service call from `self.user_id`: PRD-005 Risk 5 is explicit that a role read from a state var is cosmetic, and the same reasoning applies to an owner read from one. The class docstring already records the rule: "every send() re-derives the Identity -- and so the role -- from `_token` via resolve(), fresh, on every call."
- `active_session_id` is a **client-visible** var, unlike `_token`. That is deliberate and safe only because the server re-checks ownership on every read (PRD Risk 3, and [[STORY-010]]'s 403). Do not "fix" it by making it a backend var — the rail needs to render which row is active.
- Every database call goes through `asyncio.to_thread(...)`, and every state mutation stays inside `async with self`. Both rules are already load-bearing in `_do_send`; adding a call that violates either will deadlock or race rather than fail loudly.
- Per `chat_ui/AGENTS.md`, verbatim: "For anything about Reflex APIs — components, state management, events, styling, database, routing, authentication — use the **reflex-docs** skill rather than relying on memory." And for any run/compile cycle: "When you need to compile, run, reload, or debug a Reflex application, follow the **reflex-process-management** skill for the correct sequence and error investigation steps."
- Do **not** write transcript rows here. [[STORY-014]] owns the write and its degraded arm; mixing them makes it impossible to see, in one diff, that a failed transcript write cannot take the turn with it.
- `.agents/skills/` was scanned: `frontend-design` applies to the rail's visual design ([[STORY-017]], [[STORY-018]]). This story renders nothing.

## Dependencies

- **Blocked by**: STORY-006, STORY-009, STORY-012
- **Blocks**: STORY-014, STORY-016, STORY-018

## PRD Reference

Source: [`PRD-008/PRD.md`](../../PRDs/PRD-008-chat-sessions/PRD.md) — Section 4 (Chat state), Section 5 (story 2), Section 6 (send path, Design patterns), Section 12 Phase 3, Risk 3
