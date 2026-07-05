---
id: STORY-004
prd: PRD-002
slug: chat-ui-components
title: "Claude-like chat UI components (static)"
type: feature
priority: medium
complexity: medium
phase: "3 - Chat UI components"
status: done
labels: [frontend, reflex, ui]
epic_branch: epic/PRD-002-reflex-chat-ui
plan: .agents/plans/PRD-002-reflex-chat-ui/completed/STORY-004-chat-ui-components.plan.md
report: .agents/reports/PRD-002-reflex-chat-ui/STORY-004-chat-ui-components.report.md
commit: 4cc0018
depends_on: [STORY-003]
blocks: [STORY-005]
skills: []
created: 2026-07-04
updated: 2026-07-05
---

# STORY-004: Claude-like chat UI components (static)

## Description

As an end user, I want a chat window that looks and feels like Claude — a message list with alternating bubble alignment and avatars, plus an input box — so that the interface is immediately familiar even before it's wired to the real pipeline (PRD Section 4, User Story 1).

## Acceptance Criteria

- [ ] Given the chat page loads, when rendered, then it shows a message list area and an input bar with a send button/action, styled to approximate Claude's chat layout (avatars, alternating bubble alignment for user vs. assistant messages).
- [ ] Given a user types text and sends it, when the static component handles the interaction, then a new user-aligned bubble appears in the message list (no backend call yet — this story is presentation-only, wiring to `run_query(...)` is STORY-006).
- [ ] Given the component structure in PRD Section 6, when implemented, then it lives in `chat_ui/chat_ui/components/chat.py` as message bubble + input bar components, consumed by `chat_ui/chat_ui/chat_ui.py`.
- [ ] Given a manual UI walkthrough (PRD Section 12 Phase 3 validation), when a message is sent, then a user bubble renders and a visual review confirms it approximates the Claude-like reference style (avatars, bubble alignment, spacing).
- [ ] Given this story is presentation-only, when PRD-001's existing test suite runs, then it continues to pass unmodified.

## Technical Notes

- Per PRD Section 6 suggested structure: `chat_ui/chat_ui/components/chat.py` — "message bubble + input bar (Claude-like styling)".
- Per PRD Section 12 Phase 3: "Goal: Claude-like chat interface (static, not yet wired to the pipeline)." Deliverables are message list, input bar, avatar/bubble styling based on Reflex's chat-bot template. Validation is a manual UI walkthrough plus visual review — no pipeline wiring in this story.
- Per PRD Section 4 (In Scope): "Single-page chat UI: message list + input box, Claude-like visual style (avatars, alternating bubble alignment)."
- Do not implement blocked-state rendering yet (distinct `SUCCESS`/`BLOCKED` bubble styles) — that requires the real pipeline responses and belongs to STORY-006, which depends on this story's bubble components existing first.
- Reflex ships an official chat-bot template/example that can be adapted for the message list + input bar pattern — reuse its structure rather than building bubble layout from scratch where reasonable.

## Dependencies

- **Blocked by**: STORY-003
- **Blocks**: STORY-005

## PRD Reference

Source: [`PRD-002/PRD.md`](../../PRDs/PRD-002-reflex-chat-ui/PRD.md) — Section 4 (User Story 1, In Scope), Section 6 (suggested directory additions), Section 12 Phase 3 (Chat UI components)
