---
id: STORY-014
prd: PRD-004
slug: shell-header-empty-state
title: "Redesigned shell: header with session identity, and empty state"
type: feature
priority: medium
complexity: medium
phase: "4 - Shell, session, and recovery actions"
status: done
labels: [ui, reflex, components, layout]
epic_branch: epic/PRD-004-chat-ui-redesign
plan: .agents/plans/PRD-004-chat-ui-redesign/completed/STORY-014-shell-header-empty-state.plan.md
report: .agents/reports/PRD-004-chat-ui-redesign/STORY-014-shell-header-empty-state.report.md
commit: 07f100e
depends_on: [STORY-007, STORY-008]
blocks: [STORY-015, STORY-016]
skills: []
created: 2026-08-21
updated: 2026-08-24
---

# STORY-014: Redesigned shell — header with session identity, and empty state

## Description

As an end user, I want a proper chat shell with a header showing who I am in this session and a real empty state, so that the page explains itself instead of opening on a hardcoded fake greeting (PRD Section 4 Layout, Section 12 Phase 4).

## Acceptance Criteria

- [ ] Given `chat_ui/chat_ui/components/shell.py`, when it is created, then it provides the header (harness identity, session `user_id`, slot for the model selector) and the empty state, and `chat_ui/chat_ui.py` composes header → message area → composer.
- [ ] Given an active session, when the header renders, then the current `user_id` is visible and there is an action to change it without reloading the page.
- [ ] Given the change-user action, when used, then the session `user_id` is replaced and subsequent sends pass the new value to `run_query(...)`.
- [ ] Given a conversation with no messages, when the page renders, then a designed empty state is shown and the hardcoded `WELCOME_MESSAGE` dict at [state.py:8-11](../../../chat_ui/chat_ui/state.py) is gone — the app no longer fakes an assistant turn that the pipeline never produced.
- [ ] Given every string in the shell, when grepped, then it comes from `copy.py` ([[STORY-007]]).

## Technical Notes

- New file `chat_ui/chat_ui/components/shell.py`; `chat_ui/chat_ui.py` changes to page-shell composition only, per the file map in PRD Section 6.
- The model selector itself is [[STORY-016]] and `user_id` validation is [[STORY-015]] — this story lays out the header and leaves their slots.
- Removing `WELCOME_MESSAGE` changes `ChatState.messages`' initial value; check `tests/test_chat_state.py` helpers that index `messages[-2]`/`messages[-1]` still hold ([[STORY-006]] migrated them).
- `chat_ui/chat_ui.py:26-36` currently branches the whole page on `ChatState.user_id != ""` between the chat and `user_id_prompt()`; keep that gate intact while adding the header.
- Do not touch the `api_transformer`, `init_db()` or `register_lifespan_task(pii_redactor.load)` wiring at `chat_ui/chat_ui.py:22,39-47` — those carry load-bearing comments about Reflex's lifespan bypass.
- Per `chat_ui/AGENTS.md` (verbatim): "For anything about Reflex APIs — components, state management, events, styling, database, routing, authentication — use the **reflex-docs** skill rather than relying on memory. It carries current, version-accurate docs."
- This PRD adds no routes, so `tests/test_route_reservations.py` must keep passing (PRD Section 9).

## Dependencies

- **Blocked by**: STORY-007, STORY-008
- **Blocks**: STORY-015, STORY-016

## PRD Reference

Source: [`PRD-004/PRD.md`](../../PRDs/PRD-004-chat-ui-redesign/PRD.md) — Section 4 (Metadata & session, Layout), Section 6 (file map), Section 7, Section 12 Phase 4
