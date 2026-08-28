---
id: STORY-007
prd: PRD-006
slug: register-theme-tokens
title: "theme.py register tokens: row height, stamp-margin width, hover ground, micro type step"
type: technical
priority: high
complexity: small
phase: "2 - The register"
status: todo
labels: [ui, design, theme, admin]
epic_branch: epic/PRD-006-admin-console
plan: null
report: null
commit: null
depends_on: []
blocks: [STORY-009, STORY-011, STORY-015, STORY-018]
skills: [frontend-design]
created: 2026-08-28
updated: 2026-08-28
---

# STORY-007: theme.py register tokens: row height, stamp-margin width, hover ground, micro type step

## Description

As an integrating developer, I want every new size and colour the console needs added to `theme.py` and nowhere else, so that the single-file token guarantee PRD-004 established survives a second surface (PRD Section 4, Section 8).

## Acceptance Criteria

- [ ] Given [chat_ui/chat_ui/theme.py](../../../chat_ui/chat_ui/theme.py), when the console's tokens are added, then it gains at least a register row height, a stamp-margin width, a row hover ground and a micro type step — the four PRD Section 12 Phase 2 names — each as a module constant beside the existing ones.
- [ ] Given the console's palette, when the tokens are read, then it reuses `INK_CLEAR`, `INK_HELD`, `INK_DENIED`, `INK_FAULT`, `PAPER`, `CARD`, `RULE`, `RULE_SOFT`, `MUTE`, `SPINE` unchanged, and introduces **no** new hue — no accent colour of the console's own.
- [ ] Given `INK_UPSTREAM` and `INK_SELF`, when the console is inspected, then neither is referenced by any admin module — they stay chat-only (PRD Section 6.1).
- [ ] Given any new ink/ground pairing the console introduces, when [tests/test_contrast.py](../../../tests/test_contrast.py) runs, then that pairing is asserted at or above `AA_NORMAL` (4.5:1) alongside the existing chat pairings.
- [ ] Given the new hover ground, when its contrast against every verdict ink and against `INK` is measured, then each clears WCAG AA and is covered by the contrast test.
- [ ] Given the chat surface, when it is loaded after this change, then it renders identically — no existing token value is altered, only additions are made.

## Technical Notes

- Additions only, in [chat_ui/chat_ui/theme.py](../../../chat_ui/chat_ui/theme.py) beside `RAIL_X`, `GLYPH`, `COLUMN_MAX`, `MEASURE`, `PANEL_MAX` (lines 74-79) and the `TEXT_*` scale (lines 69-72). PRD Section 4: "Every colour, size and face comes from `chat_ui/theme.py`; any new token is added there, preserving the single-file guarantee."
- The **frontend-design** skill, verbatim: "Where the brief pins down a visual direction, follow it exactly — the brief's own words always win, including when it asks for one of these looks." PRD Section 6.1 is that pin — the palette is inherited, not re-proposed. Do not add a new accent.
- The stamp margin continues the chat's rail. PRD Section 6.1: "This is the chat's rail (`RAIL_X`, `GLYPH`, `SPINE` — already in `theme.py`) continued rather than reinvented" — derive the stamp width from the existing rail metrics rather than picking a fresh number.
- The `TINT_*` fills (theme.py:44-48) are **not** used on the register — PRD Section 6.1: "a hundred tinted rows would be a heat map of noise". This story adds no tint token.
- [tests/test_contrast.py](../../../tests/test_contrast.py) already carries a `contrast()` helper and an `_INK_ON_TINT` table; extend it with an ink-on-hover-ground table rather than writing a second helper.

## Dependencies

- **Blocked by**: None
- **Blocks**: STORY-009, STORY-011, STORY-015, STORY-018

## PRD Reference

Source: [`PRD-006/PRD.md`](../../PRDs/PRD-006-admin-console/PRD.md) — Section 4 (design & copy), Section 6.1 (colour, type), Section 8, Section 12 Phase 2
