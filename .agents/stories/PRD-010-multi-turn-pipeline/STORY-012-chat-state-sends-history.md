---
id: STORY-012
prd: PRD-010
slug: chat-state-sends-history
title: "ChatState sends session history through run_conversation; flag-off path unchanged"
type: feature
priority: high
complexity: large
phase: "3 - Chat sends history"
status: done
labels: [chat-ui, backend, history]
epic_branch: epic/PRD-010-multi-turn-pipeline
plan: .agents/plans/PRD-010-multi-turn-pipeline/completed/STORY-012-chat-state-sends-history.plan.md
report: .agents/reports/PRD-010-multi-turn-pipeline/STORY-012-chat-state-sends-history.report.md
commit: e5bf0e0
depends_on: [STORY-006, STORY-007, STORY-010, STORY-011]
blocks: [STORY-013, STORY-014, STORY-015, STORY-017]
skills: []
created: 2026-09-17
updated: 2026-09-18
---

# STORY-012: ChatState sends session history through run_conversation; flag-off path unchanged

## Description

As an end user, I want each send in an existing chat to include that chat's earlier answered exchanges, so that the model can answer "what did I just ask?" and follow-ups like "shorten that".

## Acceptance Criteria

- [ ] Given `CHAT_HISTORY_ENABLED=true` and an active session with one prior answered exchange ("What is 2+2?"), when the user sends "what did I just ask?", then the injected upstream records `[user("What is 2+2?"), assistant(<stored redacted reply>), user("what did I just ask?")]`, via `run_in_pipeline(chat_history.assemble, …)`, `fit(...)` with `settings.CONTEXT_MAX_*`, and `run_in_pipeline(run_conversation, …)`.
- [ ] Given the **first** send of a new chat (no `session_id` before send), or `CHAT_HISTORY_ENABLED=false`, when the user sends, then `run_query` is called through `run_in_pipeline` with exactly today's keyword arguments (`prompt=text`, …) and `chat_history.assemble` is **never** called. [tests/test_history_off_integration.py](../../../tests/test_history_off_integration.py) passes unmodified, and a tripwire on `assemble` proves the off path.
- [ ] Given a session whose history must be trimmed (limits monkeypatched small), when a send succeeds, then the assistant `ChatMessage` carries `history_trimmed=<dropped count>`, `_to_stored_message` persists it, and `_to_chat_message` restores it on reload. A send with no trimming stores `0` or `None`, never a misleading positive number.
- [ ] Given a prior turn that was held as duplicate, blocked as suspicious or failed upstream, when the next send is made, then that turn's text is absent from the upstream messages (end-to-end through `temp_db`, D4).
- [ ] Given `ChatMessage` in [chat_ui/chat_ui/models.py](../../../chat_ui/chat_ui/models.py), when it is read, then it has `history_trimmed: int = 0`. The full suite, including [tests/test_chat_state.py](../../../tests/test_chat_state.py) and [tests/test_session_rail.py](../../../tests/test_session_rail.py), is green.

## Technical Notes

- Follow PRD F8's branch exactly: `if session_id and settings.CHAT_HISTORY_ENABLED:` selects the pipeline **input**, not persistence. The explicit flag read keeps the off path provably identical (same function, same arguments, no extra read).
- Read history from the database, never from `self.messages`. The in-memory list can hold unpersisted bubbles, including the current user bubble just appended. The current user bubble is not yet an answered exchange, so `assemble` naturally excludes it.
- `assemble` and the pipeline call both run through `run_in_pipeline` (STORY-006). Neither holds the Reflex state lock while waiting (read locals inside `async with self`, as `_do_send` already does for `model` and `session_id`).
- A `ChatSessionError` from `assemble` should degrade to sending **without** history and set `sessions_error`, mirroring how a failed `create` sends the turn unattached. The composer is never blocked (PRD-004 Risk 3). Test it.
- The footer copy and the `context_limit` bubble are STORY-013. This story only carries the number.
- Two tabs on one session may see each other's writes on the next send; accepted (README *Limitations*).
- Skills: none applicable. There is no visual change in this story; STORY-013 owns the UI surfaces.

## Dependencies

- **Blocked by**: STORY-006, STORY-007, STORY-010, STORY-011
- **Blocks**: STORY-013, STORY-014, STORY-015, STORY-017

## PRD Reference

Source: [`PRD-010-multi-turn-pipeline/PRD.md`](../../PRDs/PRD-010-multi-turn-pipeline/PRD.md) — sections 4 (Chat UI), 5 (stories 1, 3), 6.1, 6.4, 7 (F8), 9.3, 11 (MVP definition, functional requirements)
