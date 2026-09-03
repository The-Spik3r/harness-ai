---
id: STORY-015
prd: PRD-008
slug: transcript-restore
title: "Restore a transcript on sign-in and on switch, rehydrating all seven bubble kinds"
type: feature
priority: high
complexity: large
phase: "3 - State and restore"
status: todo
labels: [ui, reflex, state]
epic_branch: epic/PRD-008-chat-sessions
plan: null
report: null
commit: null
depends_on: [STORY-014]
blocks: [STORY-016, STORY-021]
skills: [reflex-docs]
created: 2026-09-02
updated: 2026-09-02
---

# STORY-015: Restore a transcript on sign-in and on switch, rehydrating all seven bubble kinds

## Description

As an employee, I want my conversation to still be there after I reload the page, so that a stray refresh does not cost me an afternoon of work (PRD Section 5, story 1).

This is the story the PRD exists for. Everything before it makes a transcript exist; this one makes it come back.

## Acceptance Criteria

- [ ] Given a signed-in user with sessions, when the page loads, then the most recently active session becomes active and its transcript is rendered.
- [ ] Given `select_session(session_id)`, when it runs, then `self.messages` is replaced by that session's stored messages, in `id ASC` order, and `active_session_id` moves.
- [ ] Given a switch, when it completes, then `selected_model`, `user_id` and `_token` are untouched. PRD Section 11: "the model selector and the signed-in user are untouched."
- [ ] Given each of the seven kinds — `user`, `assistant`, `duplicate`, `injection`, `forbidden`, `upstream_error`, `internal_error` — when it is stored and restored, then the rendered bubble is indistinguishable from the live one: same ink, same tag, same detail, same actions.
- [ ] Given a restored `duplicate` bubble, when it renders, then `duplicate_relative_info` and `duplicate_release_info` are **recomputed** from the stored `first_query_at` through `format_duplicate_info`, not read from storage — so "already sent 2m ago" reads correctly hours later.
- [ ] Given a restored `assistant` bubble, when it renders, then its footer shows the same `model_used`, `tokens_used` and `#audit_id`, and its PII badge shows the same entity list.
- [ ] Given a restored `duplicate`, `injection` or error bubble, when it renders, then **Retry** and **Edit and resend** work — `prompt` survived the round trip, which is what those actions consume.
- [ ] Given a switch while `pending` is true, when it is attempted, then it is refused, matching the guard `edit_and_resend` already applies — swapping the transcript out from under an in-flight send would append the answer to the wrong conversation.
- [ ] Given a read that raises, when it is caught, then `sessions_error` is set, `self.messages` is left as it was, and the composer stays usable.
- [ ] Given `settings.CHAT_HISTORY_ENABLED is False`, when the page loads, then no read is attempted and the chat opens empty, exactly as today.
- [ ] Given [tests/test_chat_state.py](../../../tests/test_chat_state.py), when it runs, then a store/restore round trip is asserted **per kind**, not once for a representative kind.

## Technical Notes

- File: [chat_ui/chat_ui/state.py](../../../chat_ui/chat_ui/state.py). Rehydration — `StoredMessage` → `ChatMessage` — happens **here**, on the UI side of the boundary, because `app/` does not import from `chat_ui/` ([[STORY-005]] Technical Notes).
- The restored objects must be the same `ChatMessage` type a live send produces. PRD Section 6, verbatim: "a restored bubble must render through the same `rx.match` in `components/chat.py` as a live one — a second, lossier model would produce transcripts that read differently after a reload, which is exactly the bug this PRD exists to remove." No new component and no new arm in [chat_ui/chat_ui/components/chat.py](../../../chat_ui/chat_ui/components/chat.py).
- The duplicate copy is recomputed, never stored — [[STORY-002]] deliberately gave those two fields no column. Call `format_duplicate_info` during rehydration, in the backend, for the reason [chat_ui/chat_ui/models.py](../../../chat_ui/chat_ui/models.py) already records: "component functions only ever see Vars, so datetime math cannot run at render."
- Reflex loads page state through an `on_load` event; confirm the exact API and its interaction with `rx.event(background=True)` against the **reflex-docs** skill rather than from memory, per `chat_ui/AGENTS.md`. A background event has no exclusive access to state outside an `async with self` block — the comment in `send()` says so, and it applies to every load added here.
- Reads are offloaded with `asyncio.to_thread(...)` and go through `app/services/chat_sessions.py`, so the ownership check runs server-side on every switch. `active_session_id` arriving from the client is exactly the case PRD Risk 3 covers: "The server re-checks ownership on every read against the freshly resolved Identity, never against the var."
- A foreign or unknown `session_id` yields an empty list, not an error — the caller cannot distinguish the two, and the UI treats both as "nothing here".
- Do not implement rename or delete here. That is [[STORY-016]].
- `.agents/skills/` was scanned: `frontend-design` applies to the rail ([[STORY-017]], [[STORY-018]]). This story renders no new component.

## Dependencies

- **Blocked by**: STORY-014
- **Blocks**: STORY-016, STORY-021

## PRD Reference

Source: [`PRD-008/PRD.md`](../../PRDs/PRD-008-chat-sessions/PRD.md) — Section 4 (Chat state), Section 5 (stories 1, 5), Section 6 (stored message table), Section 11, Section 12 Phase 3
