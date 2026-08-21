---
id: STORY-007
prd: PRD-004
slug: copy-module
title: "Centralize all user-facing copy in chat_ui/copy.py"
type: technical
priority: medium
complexity: small
phase: "3 - Bubble redesign & PII badge"
status: todo
labels: [ui, copy, i18n]
epic_branch: epic/PRD-004-chat-ui-redesign
plan: null
report: null
commit: null
depends_on: []
blocks: [STORY-008, STORY-011, STORY-014]
skills: []
created: 2026-08-21
updated: 2026-08-21
---

# STORY-007: Centralize all user-facing copy in chat_ui/copy.py

## Description

As an integrating developer, I want every user-facing string in one module, so that changing display language is a single-file edit rather than a hunt through components (PRD Section 4, Section 13 "Full i18n").

## Acceptance Criteria

- [ ] Given `chat_ui/chat_ui/copy.py`, when it is created, then it holds every user-facing string the chat renders: the six bubble labels, the PII badge template, the footer separators, the retry and edit-and-resend labels, the empty state, the composer placeholder and the `user_id` prompt and validation messages.
- [ ] Given any component module under `chat_ui/`, when grepped for quoted user-facing text, then no display string is defined outside `copy.py` (component-local styling values such as colors and sizes are not copy).
- [ ] Given the PII badge copy, when read, then it says the masking applies to the exchange (e.g. "masked in this exchange"), never wording that implies only the user's prompt (Risk 5).
- [ ] Given the duplicate-bubble copy, when read, then it states that the text must change for the resend to go through (Risk 4).

## Technical Notes

- New file `chat_ui/chat_ui/copy.py`, per the file map in PRD Section 6. Plain module-level constants or a simple dict — no framework, since "A full i18n framework (only copy centralization is in scope)" is explicitly out of scope (PRD Section 4).
- Copy that carries a correctness obligation, straight from the PRD:
  - Risk 5 mitigation (verbatim): "Copy is explicit that it covers the whole exchange (\"masked in this exchange\"), not the prompt alone."
  - Risk 4 mitigation (verbatim): "The action repopulates and focuses the composer with the original text and pairs it with copy stating the text must change to go through."
  - Section 4: the badge "reports the union across the exchange, because `run_query(...)` does not separate input from output entities".
  - Risk 7 mitigation: "the upstream-error card names OpenRouter explicitly as the failing party".
- Strings that take values (relative time, entity list, pattern, `model_used`/`tokens_used`/`audit_id`) are templates here; the formatting logic lives with its own story ([[STORY-009]], [[STORY-010]], [[STORY-011]]).
- This story has no dependency on the rendering work and can land first in Phase 3, so [[STORY-008]] can import it from the start.

## Dependencies

- **Blocked by**: None
- **Blocks**: STORY-008, STORY-011, STORY-014

## PRD Reference

Source: [`PRD-004/PRD.md`](../../PRDs/PRD-004-chat-ui-redesign/PRD.md) — Section 4 (Layout), Section 6 (file map), Section 12 Phase 3, Risks 4 and 5
