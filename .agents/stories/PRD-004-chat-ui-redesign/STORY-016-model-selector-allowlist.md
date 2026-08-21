---
id: STORY-016
prd: PRD-004
slug: model-selector-allowlist
title: "Model selector driven by a curated allowlist in config.py"
type: feature
priority: medium
complexity: medium
phase: "4 - Shell, session, and recovery actions"
status: todo
labels: [ui, reflex, state, config]
epic_branch: epic/PRD-004-chat-ui-redesign
plan: null
report: null
commit: null
depends_on: [STORY-014]
blocks: [STORY-019]
skills: []
created: 2026-08-21
updated: 2026-08-21
---

# STORY-016: Model selector driven by a curated allowlist in config.py

## Description

As an end user, I want to choose which model answers my message, so that the model shown in the assistant footer is one I picked rather than a hardcoded constant (PRD Section 4, Section 7).

## Acceptance Criteria

- [ ] Given `chat_ui/chat_ui/config.py`, when it is created, then it holds a curated model allowlist and the default selection — a UI-level constant, with no new environment variable (PRD Section 9).
- [ ] Given the header, when it renders, then a model selector offers exactly the allowlist entries and no free-text entry.
- [ ] Given a selected model, when a message is sent, then it is passed as `QueryRequest.model` into `run_query(...)`, replacing the hardcoded `model="gpt-4"` at [state.py:64](../../../chat_ui/chat_ui/state.py).
- [ ] Given a message sent with a selected model, when the resulting audit row is inspected, then its `model_used` matches the selection (PRD Section 11), and the assistant footer ([[STORY-010]]) shows the same value.
- [ ] Given the selector, when the session changes user ([[STORY-014]]), then the selection behavior is unchanged — the model is a session-level UI choice, not persisted state.

## Technical Notes

- New file `chat_ui/chat_ui/config.py` per the file map in PRD Section 6; `state.py` reads the selected model from a state var.
- Risk 7 mitigation, verbatim: "A curated allowlist in `chat_ui/config.py` rather than free text, and the upstream-error card names OpenRouter explicitly as the failing party and offers retry." Section 9 adds: "An arbitrary model string would reach OpenRouter and return an error the user cannot act on; an allowlist keeps `QueryRequest.model` values known-good without adding server-side validation."
- `QueryRequest.model` defaults to `"gpt-4"` in `app/models/schemas.py:10` — the allowlist default should be a value the configured OpenRouter key can actually serve; do not change the schema default.
- This reverses PRD-002's out-of-scope decision on the model picker, now that the footer can show which model answered (PRD Section 7).
- Per `chat_ui/AGENTS.md` (verbatim): "For anything about Reflex APIs — components, state management, events, styling, database, routing, authentication — use the **reflex-docs** skill rather than relying on memory. It carries current, version-accurate docs."
- Validation includes inspecting a real audit row, per PRD Section 12 Phase 4: "audit rows inspected for non-null `device` and a `model_used` matching the selector".

## Dependencies

- **Blocked by**: STORY-014
- **Blocks**: STORY-019

## PRD Reference

Source: [`PRD-004/PRD.md`](../../PRDs/PRD-004-chat-ui-redesign/PRD.md) — Section 4 (Metadata & session), Section 7, Section 9, Section 10 (contract table), Section 12 Phase 4, Risk 7
