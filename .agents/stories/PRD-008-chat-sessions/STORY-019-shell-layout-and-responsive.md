---
id: STORY-019
prd: PRD-008
slug: shell-layout-and-responsive
title: "The rail in the shell: full-width masthead kept, collapse at a narrow viewport, one transition"
type: feature
priority: high
complexity: medium
phase: "4 - Surface and hardening"
status: todo
labels: [ui, reflex, layout, design, a11y]
epic_branch: epic/PRD-008-chat-sessions
plan: null
report: null
commit: null
depends_on: [STORY-018]
blocks: [STORY-020, STORY-022]
skills: [frontend-design, reflex-docs]
created: 2026-09-02
updated: 2026-09-02
---

# STORY-019: The rail in the shell: full-width masthead kept, collapse at a narrow viewport, one transition

## Description

As an employee on a laptop or a narrow window, I want the rail to give way to the conversation when there is no room for both, so that the feature that helps me switch chats does not cost me the chat I am reading.

## Acceptance Criteria

- [ ] Given [chat_ui/chat_ui/chat_ui.py](../../../chat_ui/chat_ui/chat_ui.py)'s `index()`, when it renders signed-in, then the layout is masthead across the full width, rail and transcript side by side beneath it, composer along the bottom.
- [ ] Given the masthead, when it renders, then it still spans the full width and still carries the model selector and the signed-in user. PRD Section 6.1: "so the header keeps spanning the full width and stays the one place the session's facts (who is sending, which model) live."
- [ ] Given a narrow viewport, when the page renders, then the rail collapses and the transcript keeps the full width, with a control to bring the rail back.
- [ ] Given the collapse, when it animates, then it is the **only** transition on the surface, and it is disabled under `prefers-reduced-motion`.
- [ ] Given a session switch, when it happens, then nothing animates. PRD Section 6.1: "the skill's warning that *'extra animation contributes to the feeling that the design is AI-generated'* applies hardest to the operation a user will perform thirty times a day."
- [ ] Given the login gate, when an unauthenticated visitor loads the page, then it is unchanged — no rail, no session read, exactly as today.
- [ ] Given the transcript column, when the rail is present, then `theme.COLUMN_MAX` still governs the reading measure and the bubbles do not stretch to fill the reclaimed width.
- [ ] Given keyboard navigation, when the user tabs through the page, then the order is masthead → rail → transcript → composer, with visible focus at every stop.
- [ ] Given the rail with many sessions, when it overflows, then it scrolls **within its own container** and the page body does not scroll horizontally.
- [ ] Given the two admin routes, when they render, then they are untouched — no rail, no chat state, and [tests/test_admin_shell.py](../../../tests/test_admin_shell.py) and [tests/test_register.py](../../../tests/test_register.py) pass unmodified.

## Technical Notes

- Files: [chat_ui/chat_ui/components/shell.py](../../../chat_ui/chat_ui/components/shell.py), [chat_ui/chat_ui/chat_ui.py](../../../chat_ui/chat_ui/chat_ui.py) (the `index()` composition), [chat_ui/chat_ui/theme.py](../../../chat_ui/chat_ui/theme.py) if the breakpoint needs a token — and it does, per [[STORY-017]]'s single-file rule.
- The current `index()` is `rx.cond(user_id != "", vstack(header, cond(has_messages, message_list, empty_state), chat_input), login_gate)`. The rail goes inside the authenticated branch, between the header and the composer, in an `hstack` with the transcript. Keep the `rx.cond` on `user_id` exactly where it is — it is the gate.
- The empty state currently doubles as the legend for the transcript's rail. With a session rail present, confirm during the self-critique pass that two "rails" on one screen do not read as competing devices; PRD Section 6.1 argues they do not, because they operate at different scales and mark different things. If they do compete on screen, the finding belongs in the report.
- The **frontend-design** skill's quality floor, verbatim: "Build to a quality floor without announcing it: responsive down to mobile, visible keyboard focus, reduced motion respected." This story is where that floor is met for the rail.
- And its closing discipline, verbatim: "Consider Chanel's advice: before leaving the house, take a look in the mirror and remove one accessory." Run that pass here, with the rail in place, against the rail's one job — *get me back into the right one, and get out of the way*.
- Per `chat_ui/AGENTS.md`, verbatim: "For anything about Reflex APIs — components, state management, events, styling, database, routing, authentication — use the **reflex-docs** skill rather than relying on memory." Responsive style props and breakpoints in particular: confirm the current Reflex API rather than recalling it.
- Also per `chat_ui/AGENTS.md`: "When you need to compile, run, reload, or debug a Reflex application, follow the **reflex-process-management** skill for the correct sequence and error investigation steps." Take screenshots during this story — the skill notes "a picture is worth 1000 tokens."
- Watch CSS specificity when adding the layout rules to `GLOBAL_CSS`. The **frontend-design** skill warns, verbatim: "It's easy to generate CSS classes that cancel each other out... This can happen often with paddings/margins between sections."

## Dependencies

- **Blocked by**: STORY-018
- **Blocks**: STORY-020, STORY-022

## PRD Reference

Source: [`PRD-008/PRD.md`](../../PRDs/PRD-008-chat-sessions/PRD.md) — Section 4 (Surface), Section 6.1 (Layout, Motion), Section 11 (Quality indicators), Section 12 Phase 4
