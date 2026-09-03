---
id: STORY-014
prd: PRD-008
slug: transcript-persistence-write
title: "Persist each bubble after it is appended, touch the session, and degrade without losing the turn"
type: feature
priority: high
complexity: medium
phase: "3 - State and restore"
status: todo
labels: [ui, reflex, state, reliability]
epic_branch: epic/PRD-008-chat-sessions
plan: null
report: null
commit: null
depends_on: [STORY-013]
blocks: [STORY-015]
skills: [reflex-docs]
created: 2026-09-02
updated: 2026-09-02
---

# STORY-014: Persist each bubble after it is appended, touch the session, and degrade without losing the turn

## Description

As an employee, I want a blocked or failed turn to still be part of the conversation, so that the transcript is a true account and not just the answers (PRD Section 5, story 5) — and I want a storage problem to cost me the *saving*, never the answer I already paid for.

## Acceptance Criteria

- [ ] Given any send, when a bubble is appended to `self.messages`, then the same bubble is written with `chat_sessions.append_message(...)` **after** the append, not before and not instead.
- [ ] Given all seven bubble kinds, when each is produced, then each is persisted — including `user`, and including the four non-success outcomes and the two error kinds.
- [ ] Given an `assistant` bubble, when it is persisted, then the stored `content` is `QuerySuccessResponse.response` — the redacted text the pipeline released. PRD Section 9: "The raw upstream text is never written to `chat_messages`."
- [ ] Given a successful write, when it completes, then `chat_sessions.touch(...)` updates `updated_at` and the in-state `sessions` list reorders so the active chat is first.
- [ ] Given `append_message` raising, when the exception is caught, then the bubble **stays on screen**, a notice states that the turn was not saved, `self.messages` is not cleared, and `pending` still clears.
- [ ] Given `touch` raising, when it is caught, then the same applies — a failed reorder is cosmetic and must not surface as a lost turn.
- [ ] Given `settings.CHAT_HISTORY_ENABLED is False`, when a send completes, then no write is attempted, no notice appears, and the chat behaves exactly as it does today.
- [ ] Given [tests/test_chat_state.py](../../../tests/test_chat_state.py), when it runs, then a test patches `append_chat_message` to raise and asserts the transcript is intact, the notice is present and `pending` is `False`.
- [ ] Given the audit trail, when a transcript write fails, then the audit row for that send is still present — the two writes are independent and the evidence one already happened inside `run_query`.

## Technical Notes

- File: [chat_ui/chat_ui/state.py](../../../chat_ui/chat_ui/state.py), `_do_send` only.
- PRD Section 6 fixes the order and says why, verbatim: "The audit write happens inside the pipeline, where it always has; the transcript write happens after, in the UI layer, and is allowed to fail without taking the turn with it. Evidence is the thing that must not be lost, and it is not made to depend on a feature the deployment can switch off."
- PRD Risk 5 is the failure this story is written against: "The model answered, the audit row is written, and then the transcript insert fails — a naive implementation raises and the user loses a paid, logged answer."
- There are **eight** places a bubble is appended in the current `_do_send`: the `user` bubble, the invalid-session `internal_error`, the three exception arms, and the four `isinstance` branches plus the unreachable fallback that collapse into one `self.messages.append(bubble)`. Persist at the append, not at each branch — one helper called wherever a bubble is added, so a ninth outcome added later cannot be persisted-by-forgetting.
- The notice is a copy-module string. Per the **frontend-design** skill, verbatim: "Treat failure and emptiness as moments for direction, not mood. Explain what went wrong and how to fix it, in the interface's voice rather than a person's. Errors don't apologize, and they are never vague about what happened." Say the turn was not saved; do not say sorry.
- The catch is a bare `except Exception` around the persistence call, matching PRD-004's "no silent drops" invariant and the catch-all arms already in `_do_send`. A `ChatSessionError`-only catch would let a `StorageError` that escaped wrapping take the turn down.
- `pending` clears in the existing `finally`. Verify by test that the new failure path does not return before it — PRD-004 Risk 3: "a stuck flag locks the composer permanently."
- Per `chat_ui/AGENTS.md`, verbatim: "For anything about Reflex APIs — components, state management, events, styling, database, routing, authentication — use the **reflex-docs** skill rather than relying on memory."
- `.agents/skills/` was scanned: `frontend-design` applies here only to the failure copy, quoted above.

## Dependencies

- **Blocked by**: STORY-013
- **Blocks**: STORY-015

## PRD Reference

Source: [`PRD-008/PRD.md`](../../PRDs/PRD-008-chat-sessions/PRD.md) — Section 4 (Chat state), Section 5 (story 5), Section 6 (send path), Section 9, Section 12 Phase 3, Risk 5
