---
id: STORY-012
prd: PRD-004
slug: pending-indicator-composer-lock
title: "Typing indicator and disabled composer while a request is in flight"
type: feature
priority: high
complexity: small
phase: "3 - Bubble redesign & PII badge"
status: done
labels: [ui, reflex, components, async]
epic_branch: epic/PRD-004-chat-ui-redesign
plan: .agents/plans/PRD-004-chat-ui-redesign/completed/STORY-012-pending-indicator-composer-lock.plan.md
report: .agents/reports/PRD-004-chat-ui-redesign/STORY-012-pending-indicator-composer-lock.report.md
commit: null
depends_on: [STORY-003, STORY-008]
blocks: [STORY-019]
skills: []
created: 2026-08-21
updated: 2026-08-24
---

# STORY-012: Typing indicator and disabled composer while a request is in flight

## Description

As an end user, I want visible feedback while the model is thinking, so that a 30-second OpenRouter call does not look like a frozen page (PRD User Story 4).

## Acceptance Criteria

- [x] Given `ChatState.pending` is `True`, when the message area renders, then a typing/loading indicator is visible at the end of the list.
- [x] Given `ChatState.pending` is `True`, when the composer renders, then both the text input and the send button are disabled.
- [x] Given a request that ends in any of the six outcomes, when its bubble is appended, then the indicator disappears and the composer re-enables — including on every error path, since `pending` resets in a `finally` block ([[STORY-003]], Risk 3).
- [x] Given the indicator, when a slow `run_query(...)` is in flight, then it animates — which is only possible because the call is off the event loop ([[STORY-001]], PRD Section 7).

## Technical Notes

- Consumes the `pending` var from [[STORY-003]]; this story is purely its rendering, in `chat_ui/chat_ui/components/chat.py` (composer) and the message list.
- PRD Section 7 states the dependency plainly: `asyncio.to_thread` offload is the "prerequisite for any loading indicator to animate".
- The composer form is `chat_input()` at [chat.py:91-111](../../../chat_ui/chat_ui/components/chat.py); it currently uses `reset_on_submit=True` — verify the disabled state does not interfere with that behavior.
- Reflex's `disabled` prop binding on `rx.input` / `rx.icon_button` against a state Var must be confirmed against the docs — per `chat_ui/AGENTS.md` (verbatim): "For anything about Reflex APIs — components, state management, events, styling, database, routing, authentication — use the **reflex-docs** skill rather than relying on memory. It carries current, version-accurate docs."
- Manual validation per `chat_ui/AGENTS.md` (verbatim): "When you need to compile, run, reload, or debug a Reflex application, follow the **reflex-process-management** skill for the correct sequence and error investigation steps."

## Dependencies

- **Blocked by**: STORY-003, STORY-008
- **Blocks**: STORY-019

## PRD Reference

Source: [`PRD-004/PRD.md`](../../PRDs/PRD-004-chat-ui-redesign/PRD.md) — Section 4 (Async & pending state), Section 7, Section 11, Section 12 Phase 3, User Story 4
