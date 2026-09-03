---
id: STORY-018
prd: PRD-008
slug: session-rail-component
title: "session_rail.py: the spine as the active mark, three states, no fill and no pill"
type: feature
priority: high
complexity: large
phase: "4 - Surface and hardening"
status: todo
labels: [ui, reflex, component, design]
epic_branch: epic/PRD-008-chat-sessions
plan: null
report: null
commit: null
depends_on: [STORY-012, STORY-013, STORY-016, STORY-017]
blocks: [STORY-019, STORY-020]
skills: [frontend-design, reflex-docs]
created: 2026-09-02
updated: 2026-09-02
---

# STORY-018: session_rail.py: the spine as the active mark, three states, no fill and no pill

## Description

As an employee, I want a list of my conversations that gets me back into the right one and out of the way, so that switching subjects costs a glance and a click rather than a scroll through one endless transcript.

## Acceptance Criteria

- [ ] Given `chat_ui/chat_ui/components/session_rail.py`, when it renders, then it lists `ChatState.sessions` newest-activity-first, each row showing the title and the relative activity time and nothing else.
- [ ] Given the active session, when the rail renders, then it is marked by a solid vertical mark in `SPINE` on the left edge of its row — **and by nothing else**: no fill, no rounded highlight, no bold, no accent.
- [ ] Given the rendered output, when it is inspected, then it contains no `TINT_*` value, no verdict ink, and no border radius beyond `theme.RADIUS`.
- [ ] Given the rail, when it renders, then a **New chat** control sits at its top, calling [[STORY-016]]'s `new_chat()`.
- [ ] Given a user with no sessions, when the rail renders, then the empty state invites them to start one, using [[STORY-017]]'s copy.
- [ ] Given a failed read, when the rail renders, then it shows the fault line naming what failed with a retry — never a silently empty list, which would read as "you have no chats".
- [ ] Given a session row, when it is clicked, then `select_session(...)` runs and the transcript swaps; when a send is in flight, the click is refused per [[STORY-015]]'s guard.
- [ ] Given each row, when the rename and delete affordances are reached, then they are reachable by keyboard with visible focus and are not hover-only.
- [ ] Given delete, when it is activated, then the confirmation names the chat and states that the record is kept, and only a confirmed delete calls `delete_session(...)`.
- [ ] Given `settings.CHAT_HISTORY_ENABLED is False`, when the page renders, then the rail is **absent** — not empty, not disabled. PRD Section 6: "the service returns empty lists and writes nothing, and the rail renders as absent. No caller branches on the flag."
- [ ] Given `CHAT_SESSION_LIMIT` sessions loaded, when the rail renders, then the cap is stated against the true total from `count_chat_sessions(...)`, in the manner PRD-006's register states "100 most recent of 3,180".
- [ ] Given the rendered output, when it is searched for user-facing text, then every string resolves from [chat_ui/chat_ui/copy.py](../../../chat_ui/chat_ui/copy.py) and every size and colour from [chat_ui/chat_ui/theme.py](../../../chat_ui/chat_ui/theme.py).

## Technical Notes

- New file `chat_ui/chat_ui/components/session_rail.py`. Layout integration into [chat_ui/chat_ui/components/shell.py](../../../chat_ui/chat_ui/components/shell.py) is [[STORY-019]]; this story builds the component and its states.
- PRD Section 6.1 pins the signature, verbatim: "The active session is marked by a solid vertical mark in `SPINE` on the left edge of its row, and nothing else: no fill, no rounded highlight, no bold. It is `RAIL_X` / `GLYPH` / `SPINE` — the chat's own rail and PRD-006's stamp margin — appearing a third time, at a third scale. Three surfaces, one structural device, each time encoding *which one of these is the one*."
- And the refusal, verbatim: "The template answer is the assistant-app sidebar: a dark panel, rounded pill rows, a hover-revealed kebab menu, relative timestamps under every title, and a bright 'New chat' button at the top... The chat surface is a light, ruled, hairline record; a dark pill-shaped panel bolted to its left edge would be the one element on screen belonging to a different product."
- The **frontend-design** skill, verbatim, on where boldness goes: "Spend your boldness in one place. Let the signature element be the one memorable thing, keep everything around it quiet and disciplined, and cut any decoration that does not serve the brief." The spine is that one place. Everything else is rules and type.
- Type assignment is fixed by PRD Section 6.1: "`FONT_DISPLAY` at `TEXT_DATA` for session titles, `FONT_DATA` at `TEXT_TAG` for the activity time. Titles are set in the display face rather than the body serif because they are *labels on a shelf*, not prose."
- Three states, not two. PRD Section 4 lists them: "no sessions yet, sessions listed, and a read that failed." An empty list and a failed read must not render the same thing — PRD-006 Risk called out the same conflation for its register.
- Rows read fields off `ChatSessionSummary`; they compute nothing. `activity_info` was precomputed in [[STORY-012]] precisely because "component functions only ever see Vars, so datetime math cannot run at render."
- Per `chat_ui/AGENTS.md`, verbatim: "For anything about Reflex APIs — components, state management, events, styling, database, routing, authentication — use the **reflex-docs** skill rather than relying on memory. It carries current, version-accurate docs." That covers `rx.foreach` over the summaries and `rx.cond` for the active mark.
- Also per `chat_ui/AGENTS.md`: "When you need to compile, run, reload, or debug a Reflex application, follow the **reflex-process-management** skill."
- Do **not** re-emit `rx.el.style(theme.GLOBAL_CSS)` — [chat_ui/chat_ui/chat_ui.py](../../../chat_ui/chat_ui/chat_ui.py)'s `index()` already carries it, and a second copy on the page is the mistake PRD-006's admin components were told not to make.

## Dependencies

- **Blocked by**: STORY-012, STORY-013, STORY-016, STORY-017
- **Blocks**: STORY-019, STORY-020

## PRD Reference

Source: [`PRD-008/PRD.md`](../../PRDs/PRD-008-chat-sessions/PRD.md) — Section 4 (Surface), Section 6.1 (all), Section 7, Section 11, Section 12 Phase 4, Risk 6
