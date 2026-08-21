---
id: STORY-010
prd: PRD-004
slug: success-metadata-footer
title: "Assistant bubble footer with model_used, tokens_used and audit_id"
type: feature
priority: medium
complexity: small
phase: "3 - Bubble redesign & PII badge"
status: todo
labels: [ui, reflex, components]
epic_branch: epic/PRD-004-chat-ui-redesign
plan: null
report: null
commit: null
depends_on: [STORY-005, STORY-008]
blocks: [STORY-019]
skills: []
created: 2026-08-21
updated: 2026-08-21
---

# STORY-010: Assistant bubble footer with model_used, tokens_used and audit_id

## Description

As an end user, I want to see which model answered and what it cost, so that my usage is not invisible — and so that a support request can quote an audit row ID instead of a paraphrase (PRD User Story 6, Section 3 Security/Compliance Admin).

## Acceptance Criteria

- [ ] Given a successful exchange, when the assistant bubble renders, then a subdued footer shows `model_used`, `tokens_used` and `audit_id` — for example `gpt-4 · 45 tokens · #127` (PRD User Story 6).
- [ ] Given the footer, when rendered, then it is visually subdued relative to the response text and does not compete with it for attention.
- [ ] Given a non-assistant message kind, when rendered, then no metadata footer appears — the three fields only exist on `QuerySuccessResponse`.
- [ ] Given `audit_id`, when displayed, then it matches the `audit_id` of the row `run_query(...)` wrote for that exchange, so an admin can look it up via `GET /audit`.

## Technical Notes

- Renders in the assistant bubble in `chat_ui/chat_ui/components/bubbles.py`; separators and labels come from [[STORY-007]]'s `copy.py`; values are already on the message from [[STORY-005]].
- These three fields are returned today and discarded today (PRD Section 10 table: `model_used`, `tokens_used`, `audit_id` — "discarded" → "rendered in footer"); no backend change is needed or permitted.
- The admin persona gets nothing else from this PRD: "This PRD does **not** add an admin UI... Their interest here is that the chat displays `audit_id` on successful exchanges" (PRD Section 3). The chat still never holds the admin token and adds no path to `/audit` or `/stats` (PRD Section 9).
- Coexists with the PII badge from [[STORY-009]] on the same bubble — decide their relative placement once, in `bubbles.py`, so both stay quiet.
- Per `chat_ui/AGENTS.md` (verbatim): "For anything about Reflex APIs — components, state management, events, styling, database, routing, authentication — use the **reflex-docs** skill rather than relying on memory. It carries current, version-accurate docs."

## Dependencies

- **Blocked by**: STORY-005, STORY-008
- **Blocks**: STORY-019

## PRD Reference

Source: [`PRD-004/PRD.md`](../../PRDs/PRD-004-chat-ui-redesign/PRD.md) — Section 4 (Metadata & session), Section 10 (contract table), Section 11, User Story 6
