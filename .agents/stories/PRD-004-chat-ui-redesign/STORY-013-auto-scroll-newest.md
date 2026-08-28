---
id: STORY-013
prd: PRD-004
slug: auto-scroll-newest
title: "Auto-scroll the message area to the newest message on append"
type: enhancement
priority: medium
complexity: small
phase: "3 - Bubble redesign & PII badge"
status: done
labels: [ui, reflex, components]
epic_branch: epic/PRD-004-chat-ui-redesign
plan: .agents/plans/PRD-004-chat-ui-redesign/STORY-013-auto-scroll-newest.plan.md
report: .agents/reports/PRD-004-chat-ui-redesign/STORY-013-auto-scroll-newest.report.md
commit: null
depends_on: [STORY-008]
blocks: [STORY-019]
skills: []
created: 2026-08-21
updated: 2026-08-24
---

# STORY-013: Auto-scroll the message area to the newest message on append

## Description

As an end user, I want the conversation to scroll to the newest message automatically, so that a reply that lands below the fold is not invisible (PRD Section 4, Section 7).

## Acceptance Criteria

- [x] Given a message list taller than the viewport, when any message is appended, then the newest message is scrolled into view without manual scrolling.
- [x] Given all six message kinds, when each is appended, then the scroll happens for every one — a blocked or error card scrolls into view exactly as an assistant reply does.
- [x] Given the pending indicator is visible ([[STORY-012]]), when it appears, then it too is scrolled into view, so "the model is thinking" is never hidden below the fold.
- [x] Given the message area, when the change lands, then the bare `overflow_y="auto"` with no scroll-into-view at [chat.py:56-65](../../../chat_ui/chat_ui/components/chat.py) is replaced by a real scroll behavior.

## Technical Notes

- PRD Section 8 names the candidate APIs: "`rx.scroll_area` / scroll-into-view for auto-scroll — all APIs to be confirmed against the **reflex-docs** skill before implementation, per `chat_ui/AGENTS.md`". Do not pick one from memory.
- Per `chat_ui/AGENTS.md` (verbatim): "For anything about Reflex APIs — components, state management, events, styling, database, routing, authentication — use the **reflex-docs** skill rather than relying on memory. It carries current, version-accurate docs."
- The trigger point is bubble append inside `ChatState.send()`, which happens inside `async with self` blocks in a background event — confirm how the chosen scroll mechanism is invoked from that context.
- Listed source defect: `chat_ui/chat_ui/components/chat.py:56` — "`overflow_y="auto"` with no scroll-into-view" (PRD Section 15).
- Verify in a running app per `chat_ui/AGENTS.md` (verbatim): "When you need to compile, run, reload, or debug a Reflex application, follow the **reflex-process-management** skill for the correct sequence and error investigation steps."

## Dependencies

- **Blocked by**: STORY-008
- **Blocks**: STORY-019

## PRD Reference

Source: [`PRD-004/PRD.md`](../../PRDs/PRD-004-chat-ui-redesign/PRD.md) — Section 4 (Async & pending state), Section 7, Section 8, Section 12 Phase 3, Section 15 (`chat.py:56`)
