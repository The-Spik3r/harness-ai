---
id: STORY-005
prd: PRD-004
slug: send-populates-outcome-metadata
title: "send() populates every metadata field from each pipeline outcome"
type: feature
priority: high
complexity: medium
phase: "2 - Typed message model"
status: done
labels: [ui, reflex, state, model]
epic_branch: epic/PRD-004-chat-ui-redesign
plan: .agents/plans/PRD-004-chat-ui-redesign/completed/STORY-005-send-populates-outcome-metadata.plan.md
report: .agents/reports/PRD-004-chat-ui-redesign/STORY-005-send-populates-outcome-metadata.report.md
commit: 1f7c642
depends_on: [STORY-004]
blocks: [STORY-006, STORY-009, STORY-010, STORY-011, STORY-018]
skills: []
created: 2026-08-21
updated: 2026-08-21
---

# STORY-005: send() populates every metadata field from each pipeline outcome

## Description

As an integrating developer, I want `send()` to carry every field the pipeline already returns onto the appended `ChatMessage`, so that the UI stops discarding five of the six response fields (PRD Section 10 contract table, Section 12 Phase 2).

## Acceptance Criteria

- [ ] Given a `QuerySuccessResponse`, when the assistant message is appended, then `content == result.response`, `model_used`, `tokens_used`, `audit_id`, `pii_redacted` and `pii_entities` (from `pii_entities_masked`) all land on the message — 6 of 6 response fields consumed, versus 1 of 6 today (PRD Section 11).
- [ ] Given a `QueryBlockedDuplicateResponse`, when the duplicate message is appended, then `kind == "duplicate"`, `content == result.reason` (unformatted) and `first_query_at == result.first_query_at` as the raw timestamp string, not inlined into prose as at [state.py:77](../../../chat_ui/chat_ui/state.py).
- [ ] Given a `QueryBlockedSuspiciousResponse`, when the injection message is appended, then `kind == "injection"`, `content == result.reason` and `pattern == result.pattern` — the `pattern` currently discarded at [state.py:80](../../../chat_ui/chat_ui/state.py).
- [ ] Given any of the four exception paths, when the error message is appended, then `detail` carries the exception text and `content` carries the copy key/label rather than a pre-formatted `f"Error: {exc}"` string.
- [ ] Given every appended non-user message, when inspected, then `prompt` holds the original prompt text, so retry and edit-and-resend ([[STORY-018]]) have something to resend.

## Technical Notes

- `chat_ui/chat_ui/state.py` only; `chat_ui/chat_ui/models.py` is already in place from [[STORY-004]].
- Field mapping is the PRD Section 10 table, row by row. `pii_entities_masked` (schema name, `app/models/schemas.py:21`) maps onto `ChatMessage.pii_entities` (model name, PRD Section 6) — the rename is deliberate; do not rename the schema field.
- Keep formatting *out* of state: humanized relative time ([[STORY-011]]), badge copy ([[STORY-009]]) and footer layout ([[STORY-010]]) are rendering concerns. State stores raw values; this is what makes the migrated tests structural rather than string-based (Risk 1).
- `QuerySuccessResponse` field names to read verbatim: `response`, `audit_id`, `model_used`, `tokens_used`, `pii_redacted`, `pii_entities_masked` (`app/models/schemas.py:14-21`).
- Per `chat_ui/AGENTS.md` (verbatim): "For anything about Reflex APIs — components, state management, events, styling, database, routing, authentication — use the **reflex-docs** skill rather than relying on memory. It carries current, version-accurate docs."

## Dependencies

- **Blocked by**: STORY-004
- **Blocks**: STORY-006, STORY-009, STORY-010, STORY-011, STORY-018

## PRD Reference

Source: [`PRD-004/PRD.md`](../../PRDs/PRD-004-chat-ui-redesign/PRD.md) — Section 6 (flow diagram), Section 10 (contract table), Section 12 Phase 2
