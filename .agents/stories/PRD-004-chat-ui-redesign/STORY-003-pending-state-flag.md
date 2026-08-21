---
id: STORY-003
prd: PRD-004
slug: pending-state-flag
title: "pending state var with finally-reset and single in-flight send guard"
type: technical
priority: high
complexity: small
phase: "1 - Correctness foundation"
status: todo
labels: [ui, reflex, state, async]
epic_branch: epic/PRD-004-chat-ui-redesign
plan: null
report: null
commit: null
depends_on: [STORY-001]
blocks: [STORY-012]
skills: []
created: 2026-08-21
updated: 2026-08-21
---

# STORY-003: pending state var with finally-reset and single in-flight send guard

## Description

As an end user, I want the harness to track that my request is in flight, so that the UI can show progress and refuse to queue a second concurrent send from the same session (PRD Section 4, Section 12 Phase 1).

## Acceptance Criteria

- [ ] Given `ChatState`, when a send starts, then a `pending: bool` state var flips to `True` inside an `async with self` block and flips back to `False` before `send()` returns.
- [ ] Given any of the six outcomes — three result types plus `OpenRouterError`, `PiiRedactorError`, `DuplicateCheckError` and an arbitrary exception — when `send()` completes, then `pending is False`, because the reset lives in a `finally` block.
- [ ] Given `pending is True`, when `send()` is invoked again from the same session, then the second invocation returns immediately without calling `run_query(...)` and without appending a user bubble.
- [ ] Given a test per outcome, when it asserts after `send()`, then `pending is False` in every case, including the catch-all arm.

## Technical Notes

- `chat_ui/chat_ui/state.py` only. The visible consequences — typing indicator, disabled input and send button — are [[STORY-012]]; this story is the state-level flag plus its guarantees, so it is testable with no rendering in place.
- Risk 3 mitigation, verbatim from the PRD: "All state mutation stays inside `async with self` blocks; `pending = False` is set in a `finally` block so no exception path can leave the composer locked. A test asserts `pending is False` after each of the six outcomes, including the catch-all arm."
- The guard is an early return when `self.pending` is already `True`, checked in the same `async with self` block that sets it, so check-and-set is not interleaved with another event.
- Per `chat_ui/AGENTS.md` (verbatim): "For anything about Reflex APIs — components, state management, events, styling, database, routing, authentication — use the **reflex-docs** skill rather than relying on memory. It carries current, version-accurate docs."

## Dependencies

- **Blocked by**: STORY-001
- **Blocks**: STORY-012

## PRD Reference

Source: [`PRD-004/PRD.md`](../../PRDs/PRD-004-chat-ui-redesign/PRD.md) — Section 4 (Async & pending state), Section 12 Phase 1, Risk 3
