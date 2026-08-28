---
id: STORY-018
prd: PRD-004
slug: retry-and-edit-resend
title: "Retry on error cards and edit-and-resend on duplicate cards"
type: feature
priority: high
complexity: medium
phase: "4 - Shell, session, and recovery actions"
status: done
labels: [ui, reflex, state, components]
epic_branch: epic/PRD-004-chat-ui-redesign
plan: .agents/plans/PRD-004-chat-ui-redesign/completed/STORY-018-retry-and-edit-resend.plan.md
report: .agents/reports/PRD-004-chat-ui-redesign/STORY-018-retry-and-edit-resend.report.md
commit: null
depends_on: [STORY-005, STORY-008, STORY-011]
blocks: [STORY-019]
skills: []
created: 2026-08-21
updated: 2026-08-25
---

# STORY-018: Retry on error cards and edit-and-resend on duplicate cards

## Description

As an end user, I want a way out of a blocked or failed message, so that a dead-end bubble is not the end of the conversation (PRD User Story 5, Section 2 "Every dead end has an exit").

## Acceptance Criteria

- [ ] Given an `upstream_error` or `internal_error` card, when its Retry action is used, then the original prompt is re-submitted unchanged through the same `send()` path, producing a new bubble for whatever outcome results.
- [ ] Given a `duplicate` card, when its "Edit and resend" action is used, then the composer is repopulated with the original prompt and focused, without sending anything automatically.
- [ ] Given `pending` is `True`, when a Retry or edit-and-resend action is triggered, then it is ignored — the single in-flight guard from [[STORY-003]] applies to recovery actions too.
- [ ] Given the duplicate card, when the edit-and-resend action is shown, then it is paired with copy stating the text must change to go through, so resending the identical prompt is not silently invited into a block loop (Risk 4).
- [ ] Given any recovery action, when it runs, then it uses the `prompt` field stored on the message ([[STORY-005]]) — no re-derivation from rendered bubble text.

## Technical Notes

- `chat_ui/chat_ui/components/bubbles.py` (buttons) plus event handlers in `chat_ui/chat_ui/state.py`; labels come from `copy.py` ([[STORY-007]]).
- Risk 4 verbatim: "Edit-and-resend on a duplicate bubble invites the user to resend the identical prompt, which is blocked again — a loop that makes the affordance feel broken." Mitigation: "The action repopulates and focuses the composer with the original text and pairs it with copy stating the text must change to go through."
- The underlying cause — `check_duplicate(prompt)` hashing the prompt with no `user_id` filter — is a Section 13 backend follow-up and must not be worked around in the UI.
- Retry re-enters the same `send()` code path so that all six outcomes, `pending` handling and the `finally` reset apply unchanged; do not fork a second send implementation.
- Focusing an input from an event handler is framework-specific — per `chat_ui/AGENTS.md` (verbatim): "For anything about Reflex APIs — components, state management, events, styling, database, routing, authentication — use the **reflex-docs** skill rather than relying on memory. It carries current, version-accurate docs."
- Validation: PRD Section 12 Phase 4 — "User Stories 5–8 demonstrated manually".

## Dependencies

- **Blocked by**: STORY-005, STORY-008, STORY-011
- **Blocks**: STORY-019

## PRD Reference

Source: [`PRD-004/PRD.md`](../../PRDs/PRD-004-chat-ui-redesign/PRD.md) — Section 4 (Error handling, Metadata & session), Section 7, Section 12 Phase 4, User Story 5, Risk 4
