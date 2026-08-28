---
id: STORY-015
prd: PRD-004
slug: user-id-validation
title: "Inline validation error on empty user_id submit"
type: enhancement
priority: medium
complexity: small
phase: "4 - Shell, session, and recovery actions"
status: done
labels: [ui, reflex, state, validation]
epic_branch: epic/PRD-004-chat-ui-redesign
plan: .agents/plans/PRD-004-chat-ui-redesign/completed/STORY-015-user-id-validation.plan.md
report: .agents/reports/PRD-004-chat-ui-redesign/STORY-015-user-id-validation.report.md
commit: 950daa0
depends_on: [STORY-014]
blocks: [STORY-019]
skills: []
created: 2026-08-21
updated: 2026-08-25
---

# STORY-015: Inline validation error on empty user_id submit

## Description

As an end user, I want an empty user ID submission to tell me what is wrong, so that the form does not silently do nothing and leave me stuck at the door (PRD Section 4, Section 11).

## Acceptance Criteria

- [ ] Given the `user_id` form, when it is submitted empty or whitespace-only, then a visible validation error appears next to the field, replacing the silent `return` at [state.py:41-43](../../../chat_ui/chat_ui/state.py).
- [ ] Given a visible validation error, when a valid `user_id` is then submitted, then the error clears and the session starts.
- [ ] Given the change-user action in the header ([[STORY-014]]), when an empty value is submitted there, then the same validation applies — one validation path, not two.
- [ ] Given the validation message, when read, then it comes from `copy.py` ([[STORY-007]]).

## Technical Notes

- `chat_ui/chat_ui/state.py` (`submit_user_id`, a `user_id_error` state var) plus the form in `components/chat.py` / `components/shell.py`.
- Listed source defect: `chat_ui/chat_ui/state.py:41-43` — "`submit_user_id` silent return on empty input" (PRD Section 15).
- Success criterion, verbatim: "Submitting an empty `user_id` shows a visible validation error instead of doing nothing" (PRD Section 11).
- Out of scope: any real auth or login beyond the free-text `user_id` (PRD Section 4 Out of Scope). This is field validation only — no identity checks, no persistence.
- Per `chat_ui/AGENTS.md` (verbatim): "For anything about Reflex APIs — components, state management, events, styling, database, routing, authentication — use the **reflex-docs** skill rather than relying on memory. It carries current, version-accurate docs."

## Dependencies

- **Blocked by**: STORY-014
- **Blocks**: STORY-019

## PRD Reference

Source: [`PRD-004/PRD.md`](../../PRDs/PRD-004-chat-ui-redesign/PRD.md) — Section 4 (Metadata & session), Section 11, Section 12 Phase 4, Section 15 (`state.py:41-43`)
