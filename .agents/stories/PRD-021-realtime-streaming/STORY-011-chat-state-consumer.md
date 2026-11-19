---
id: STORY-011
prd: PRD-021
slug: chat-state-consumer
title: Chat UI state consumes the pipeline's events
type: feature
priority: high
complexity: medium
phase: "3 - Ingresses"
status: done
labels: [chat-ui, reflex, streaming]
epic_branch: epic/PRD-021-realtime-streaming
plan: .agents/plans/PRD-021-realtime-streaming/completed/STORY-011-chat-state-consumer.plan.md
report: .agents/reports/PRD-021-realtime-streaming/STORY-011-chat-state-consumer.report.md
commit: 153c56f
depends_on: [STORY-009]
blocks: [STORY-012]
skills: [frontend-design]
created: 2026-11-18
updated: 2026-11-19
---

# STORY-011: Chat UI state consumes the pipeline's events

## Description

As a chat user, I want the chat to receive the harness's progress and, when I am granted it, the live answer and reasoning, so that a long wait stops looking like a hang.

## Acceptance Criteria

- [ ] Given `_do_send`, when a message is sent, then `ChatState` passes a `QueueSink` to `run_conversation` (ingress `chat`) and a background consumer drains the queue in batches of at most 100 ms, applying each batch in one `async with self` block: `progress_stage`, `progress_phase`, `progress_since` always; `live_text` only from content events; `live_reasoning` only from reasoning events
- [ ] Given the pipeline returns, when the consumer has drained the queue, then the final bubble is built from `result.response` exactly as today, `live_*` and `progress_*` are cleared and the bubble is persisted once via `_append_and_persist`; reasoning is held only in state and never persisted (D8)
- [ ] Given an upstream fault mid-stream, when the pipeline fails, then the live entry is replaced by today's `upstream_error` bubble and no partial text is persisted (D16)
- [ ] Given no grant (switch on, streaming model), when a scripted stream runs, then the progress phases follow the scripted order and no content or reasoning event reaches `ChatState`; with the switch off, stage words still update and the final bubble is identical to today's (O6)
- [ ] Given a 200-token/s scripted stream, when measured, then `ChatState` applies at most 10 state updates per second; the Reflex flush-on-exit of `async with self` for background events is verified against the pinned Reflex version and recorded in the report (fallback per Risk 5: a timer-driven poll of a server-side buffer)

## Technical Notes

- `chat_ui/chat_ui/state.py:950-1320` (`_do_send` ~`:1120-1158`, `:1311`; bubble built `:1200-1221`); the token is resolved fresh per send (`:965-967`). Line numbers predate PRD-020; grep.
- Per `chat_ui/AGENTS.md`, Reflex APIs are checked against the pinned version (the `reflex-docs` skill if available; otherwise the installed package source), not from memory.
- Rendering (progress line, live entry, reasoning block, copy) is STORY-012; this story adds state vars and the consumer only.
- frontend-design (verbatim): "Write from the end user's side of the screen. Name things by what people control and recognize, never by how the system is built".
- Chat probe: run `tests/test_chat_ui_startup_guard.py` when touching `chat_ui/`.

## Dependencies

- **Blocked by**: STORY-009
- **Blocks**: STORY-012

## PRD Reference

Source: [`PRD-021/PRD.md`](../../PRDs/PRD-021-realtime-streaming/PRD.md) — Sections 6.7, D8, D16, D19, O6, Risk 5, Quality indicators
