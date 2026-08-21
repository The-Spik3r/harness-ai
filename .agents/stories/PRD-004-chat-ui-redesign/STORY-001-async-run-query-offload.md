---
id: STORY-001
prd: PRD-004
slug: async-run-query-offload
title: "Offload run_query(...) to a worker thread via asyncio.to_thread"
type: bug
priority: high
complexity: medium
phase: "1 - Correctness foundation"
status: done
labels: [ui, reflex, state, async]
epic_branch: epic/PRD-004-chat-ui-redesign
plan: .agents/plans/PRD-004-chat-ui-redesign/completed/STORY-001-async-run-query-offload.plan.md
report: .agents/reports/PRD-004-chat-ui-redesign/STORY-001-async-run-query-offload.report.md
commit: f7e482a
depends_on: []
blocks: [STORY-002, STORY-003, STORY-017]
skills: []
created: 2026-08-21
updated: 2026-08-21
---

# STORY-001: Offload run_query(...) to a worker thread via asyncio.to_thread

## Description

As an end user, I want the harness to stay responsive while my message is being processed, so that a slow OpenRouter call does not freeze the whole page for every session (PRD Section 2, Section 12 Phase 1).

## Acceptance Criteria

- [ ] Given `ChatState.send()`, when it calls the pipeline, then it does so as `await asyncio.to_thread(run_query, ...)` instead of the blocking direct call at [state.py:59](../../../chat_ui/chat_ui/state.py) — the arguments passed (`user_id`, `prompt`, `device`, `model`, `openrouter_api_key`, `call_openrouter`) are unchanged in this story.
- [ ] Given a `run_query(...)` that blocks for several seconds, when one session has a request in flight, then a second browser session can still navigate and interact — the Reflex event loop is not blocked (PRD Section 11: "Event-loop blocking during a request — 0 ms").
- [ ] Given the three result types and the two currently-caught exceptions, when they are produced by the threaded call, then the appended bubbles are identical to today's — this story has no visible change (PRD Section 12 Phase 1: "no visual change yet").
- [ ] Given all state mutation in `send()`, when it happens, then it remains inside `async with self` blocks, per Reflex's background-event contract (PRD Section 6, Risk 3).
- [ ] Given `tests/test_chat_state.py`, when the suite runs, then it passes unmodified.

## Technical Notes

- Single file: `chat_ui/chat_ui/state.py`. Add `import asyncio` and wrap the existing call; `run_query` is invoked with keyword arguments today and `asyncio.to_thread(run_query, user_id=..., prompt=..., ...)` forwards `**kwargs` unchanged.
- The `try/except` around the call moves with it — `asyncio.to_thread` re-raises the worker's exception at the `await`, so the existing `except (DuplicateCheckError, OpenRouterError)` arm keeps working as-is. Widening those arms is [[STORY-002]], not this story.
- `asyncio.to_thread` requires Python 3.9+, already the project's declared floor (PRD Section 8) — no new dependency in either `requirements.txt`.
- Nothing under `app/` changes: `run_query(...)` stays synchronous and the UI adapts to it (PRD Section 6, "Thread-offloaded blocking work").
- Per `chat_ui/AGENTS.md` (verbatim): "For anything about Reflex APIs — components, state management, events, styling, database, routing, authentication — use the **reflex-docs** skill rather than relying on memory. It carries current, version-accurate docs."
- Per `chat_ui/AGENTS.md` (verbatim): "When you need to compile, run, reload, or debug a Reflex application, follow the **reflex-process-management** skill for the correct sequence and error investigation steps."

## Dependencies

- **Blocked by**: None
- **Blocks**: STORY-002, STORY-003, STORY-017

## PRD Reference

Source: [`PRD-004/PRD.md`](../../PRDs/PRD-004-chat-ui-redesign/PRD.md) — Section 4 (Async & pending state), Section 6, Section 12 Phase 1, Section 15 (`state.py:59`)
