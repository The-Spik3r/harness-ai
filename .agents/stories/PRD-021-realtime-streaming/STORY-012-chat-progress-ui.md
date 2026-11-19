---
id: STORY-012
prd: PRD-021
slug: chat-progress-ui
title: Progress line, live answer and reasoning block in the chat UI
type: feature
priority: high
complexity: medium
phase: "3 - Ingresses"
status: in-progress
labels: [chat-ui, frontend, copy]
epic_branch: epic/PRD-021-realtime-streaming
plan: .agents/plans/PRD-021-realtime-streaming/STORY-012-chat-progress-ui.plan.md
report: null
commit: null
depends_on: [STORY-011]
blocks: [STORY-016]
skills: [frontend-design]
created: 2026-11-18
updated: 2026-11-19
---

# STORY-012: Progress line, live answer and reasoning block in the chat UI

## Description

As a chat user, I want the pending entry to say truthfully what the harness is doing and for how long, and, when granted, to show the answer and reasoning as they arrive, so that I know the request is alive without being misled.

## Acceptance Criteria

- [ ] Given `copy.py`, when inspected, then the progress vocabulary of Section 7.1 is defined in English keyed by event name (`waiting` reuses `PENDING_INDICATOR_TEXT`), including the `preparing_action` template over the closed kind set and the reasoning labels `Model reasoning — not checked as an answer` and `Not saved with the chat`; a test asserts every progress string the UI can render is a `copy.py` constant or that template (T4)
- [ ] Given the pending entry, when progress state changes, then its evidence line shows the current word plus elapsed seconds since send (`Thinking · 14 s`), a word replaces the visible one only if its stage is still current 300 ms after it started, the seconds tick once a second, and the word sits in an `aria-live="polite"` region that changes only when the word changes
- [ ] Given `stream:realtime`, when `live_text` grows, then the entry occupies `render_pending_indicator`'s slot, keeps tag `SENDING`, renders text with `_prose` (`white-space: pre-wrap`), and the final bubble replaces it without the transcript jumping
- [ ] Given `reasoning:view`, when reasoning exists, then a collapsible block in the data face shows it (live while streaming, collapsed by default after the answer arrives) with the two labels; a restored transcript shows no reasoning
- [ ] Given the frontend-design floor, when checked, then the reasoning toggle has visible keyboard focus, the existing `hx-pulse` is reused and stopped by the reduced-motion block, and the entry is usable at 360 px width; no new animation is added

## Technical Notes

- Orchestrator decision (STORY-011 plan): ChatState exposes seven vars: `progress_stage`, `progress_phase`, `progress_action` (raw `PhaseEvent.action_kind`; the word mapping is this story's copy), `progress_since` (epoch seconds the current stage/phase started; drives the 300 ms no-flicker rule), `progress_sent_at` (epoch seconds of the send; drives the elapsed `· 14 s` counter), `live_text`, `live_reasoning`. All reset to idle defaults when the final bubble lands.

- `chat_ui/chat_ui/components/bubbles.py:495-503` pending indicator, `:61-71` `_prose`, `:74-80` `_evidence`/`FONT_DATA`; `components/chat.py:57` `render_pending_indicator` slot; `copy.py:1-9` voice and single-file language rule, `:44`, `:51-52`, `:56-68` tags; `components/shell.py:33-35` reduced motion. Line numbers predate PRD-020; grep.
- Language: English (user decision 2026-11-18, O1).
- frontend-design rules (verbatim): "Write from the end user's side of the screen. Name things by what people control and recognize, never by how the system is built"; "Use active voice as default"; "Let each element do exactly one job"; "Build to a quality floor without announcing it: responsive down to mobile, visible keyboard focus, reduced motion respected"; "sometimes less is more, and extra animation contributes to the feeling that the design is AI-generated".
- Words name the control, not the code ("Masking personal data", never "Running Presidio"); no percentage, no ETA.

## Dependencies

- **Blocked by**: STORY-011
- **Blocks**: STORY-016

## PRD Reference

Source: [`PRD-021/PRD.md`](../../PRDs/PRD-021-realtime-streaming/PRD.md) — Sections 7.1, D11, D12, T4, Quality indicators
