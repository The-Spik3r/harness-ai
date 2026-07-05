---
id: STORY-006
prd: PRD-002
slug: wire-chatstate-to-pipeline
title: "Wire ChatState.send() to the shared query pipeline"
type: feature
priority: high
complexity: medium
phase: "4 - Wire chat to the shared pipeline"
status: done
labels: [frontend, backend, integration]
epic_branch: epic/PRD-002-reflex-chat-ui
plan: .agents/plans/PRD-002-reflex-chat-ui/completed/STORY-006-wire-chatstate-to-pipeline.plan.md
report: .agents/reports/PRD-002-reflex-chat-ui/STORY-006-wire-chatstate-to-pipeline.report.md
commit: 682ee14
depends_on: [STORY-001, STORY-005]
blocks: [STORY-007]
skills: []
created: 2026-07-04
updated: 2026-07-05
---

# STORY-006: Wire ChatState.send() to the shared query pipeline

## Description

As an integrating developer, I want the chat UI's send action to call the exact same `run_query(...)` function `POST /query` uses, with distinct rendering for success vs. both blocked variants, so that duplicate detection, pattern blocking, and audit logging behave identically regardless of entry point (PRD Section 4, User Story 2 and User Story 3).

## Acceptance Criteria

- [ ] Given `ChatState.send()` is invoked with the session's `user_id` (from STORY-005) and the typed prompt, when it runs, then it calls `run_query(...)` (from STORY-001) directly in-process — a plain Python call, not an HTTP round-trip, per PRD Section 10.
- [ ] Given `run_query(...)` returns a `SUCCESS` result, when `ChatState` updates, then the model's response renders as a distinct assistant-style chat bubble (User Story 1).
- [ ] Given `run_query(...)` returns a duplicate-blocked result, when `ChatState` updates, then a distinct system-style bubble renders showing the same `reason` text `POST /query` already returns (e.g. "Blocked — duplicate query within 24 hours (first sent at ...)"), per User Story 2's example.
- [ ] Given `run_query(...)` returns a suspicious-pattern-blocked result, when `ChatState` updates, then a distinct system-style bubble renders showing the same `reason` text `POST /query` already returns for that case.
- [ ] Given a prompt is sent via the chat UI and the identical prompt is sent via `curl -X POST /query`, when both audit rows are compared, then they have the same schema and are subject to the same 24h duplicate window (they count against each other) — per User Story 3's example.
- [ ] Given a duplicate prompt sent via the chat UI within 24h and a suspicious-pattern prompt sent via the chat UI, when compared against PRD-001's `/query` behavior for the same inputs, then the blocked reasons match 100% (PRD Section 11 Quality Indicators: "Blocked-reason parity (chat vs API)").

## Technical Notes

- Per PRD Section 6: "`ChatState` holds `messages: list[dict]` and `input_text: str`; `send()` is the sole event handler that appends the user message, calls `run_query(...)`, and appends the resulting bubble (success or blocked)." Implement in `chat_ui/chat_ui/state.py` (stubbed in STORY-002, extended in STORY-005 for `user_id`).
- Per PRD Section 10: "The `ChatState.send()` handler calls the shared `run_query(...)` function in-process (a direct Python call, not an HTTP round-trip), then updates the Reflex state, which pushes the new chat bubble to the browser over the existing WebSocket connection."
- Per PRD Section 14 Risk 4: keep `ChatState.send()` "a thin wrapper with no logic beyond calling `run_query(...)`" — do not duplicate duplicate-check/pattern-check/audit-logging logic in the Reflex layer.
- Reuse the bubble components from STORY-004, extending them (or adding new variants) to render the three distinct outcomes: success, duplicate-blocked, suspicious-blocked — using the exact `reason` strings `run_query(...)` returns, no rewording.
- Validation per PRD Section 12 Phase 4: demonstrate User Stories 1–3 manually, and verify audit rows are identical for chat vs. `curl` calls of the same prompt.

## Dependencies

- **Blocked by**: STORY-001, STORY-005
- **Blocks**: STORY-007

## PRD Reference

Source: [`PRD-002/PRD.md`](../../PRDs/PRD-002-reflex-chat-ui/PRD.md) — Section 4 (User Stories 1, 2, 3), Section 6 (State pattern), Section 10 (API Specification), Section 11 (Success Criteria), Section 12 Phase 4, Section 14 Risk 4
