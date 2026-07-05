---
id: STORY-005
prd: PRD-002
slug: session-user-id-entry
title: "Session user_id entry field"
type: feature
priority: medium
complexity: small
phase: "4 - Wire chat to the shared pipeline"
status: done
labels: [frontend, reflex, ui]
epic_branch: epic/PRD-002-reflex-chat-ui
plan: .agents/plans/PRD-002-reflex-chat-ui/completed/STORY-005-session-user-id-entry.plan.md
report: .agents/reports/PRD-002-reflex-chat-ui/STORY-005-session-user-id-entry.report.md
commit: PENDING
depends_on: [STORY-004]
blocks: [STORY-006]
skills: []
created: 2026-07-04
updated: 2026-07-05
---

# STORY-005: Session user_id entry field

## Description

As an end user, I want to enter a simple `user_id` once per browser session, so that my chat messages carry the same identity the harness already requires on `POST /query`, without any new login/auth system (PRD Section 4, Section 9).

## Acceptance Criteria

- [ ] Given the chat page loads with no `user_id` set for the session, when the user is prompted, then a simple text field collects a `user_id` before the chat input becomes usable (or is otherwise required before the first send).
- [ ] Given a `user_id` has been entered once, when the user sends subsequent messages in the same browser session, then the same `user_id` is reused automatically — the field is not asked again mid-session.
- [ ] Given no `user_id` is entered (blank/whitespace), when the user attempts to send a message, then the send action is blocked client-side with the same intent as PRD-001's existing presence check (`if not request.user_id.strip()`), consistent with User Story 1 in PRD-001.
- [ ] Given this is explicitly *not* a new identity system (PRD Section 4, Out of Scope: "Full auth/login flow for end users"), when reviewed, then no password, token, or OAuth flow is introduced — this is a plain text field only.
- [ ] Given the field is implemented, when PRD-001's existing test suite runs, then it continues to pass unmodified.

## Technical Notes

- Per PRD Section 4 (In Scope): "Lightweight session identity: a simple text field where the user enters their `user_id` once per session (no OAuth/login) — same trust model as the existing `user_id` presence check in PRD-001 RF-14."
- Per PRD Section 9: "Chat session identity: a free-text `user_id` entered once in the browser, carrying the same trust level as the existing presence-check on `POST /query` (not a new identity system)."
- Store the entered `user_id` in Reflex session/component state (`ChatState`, extended from the stub created in STORY-002) — it does not need to be persisted server-side or across browser sessions, per PRD Section 4 (Out of Scope: "no persisted chat history across sessions or browsers").
- This story only adds the field and session-state storage; STORY-006 is what actually passes this `user_id` into `run_query(...)`.

## Dependencies

- **Blocked by**: STORY-004
- **Blocks**: STORY-006

## PRD Reference

Source: [`PRD-002/PRD.md`](../../PRDs/PRD-002-reflex-chat-ui/PRD.md) — Section 4 (In Scope, Out of Scope), Section 9 (Auth approach)
