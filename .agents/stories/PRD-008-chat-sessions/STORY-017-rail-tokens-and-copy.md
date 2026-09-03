---
id: STORY-017
prd: PRD-008
slug: rail-tokens-and-copy
title: "Rail tokens in theme.py and every rail string in copy.py, adding no new ink"
type: technical
priority: high
complexity: small
phase: "4 - Surface and hardening"
status: todo
labels: [ui, design, theme, copy]
epic_branch: epic/PRD-008-chat-sessions
plan: null
report: null
commit: null
depends_on: []
blocks: [STORY-018]
skills: [frontend-design]
created: 2026-09-02
updated: 2026-09-02
---

# STORY-017: Rail tokens in theme.py and every rail string in copy.py, adding no new ink

## Description

As a maintainer, I want the rail's sizes and words declared before the rail is built, so that the component that follows has nothing left to invent and the single-file guarantee on [chat_ui/chat_ui/theme.py](../../../chat_ui/chat_ui/theme.py) holds.

## Acceptance Criteria

- [ ] Given [chat_ui/chat_ui/theme.py](../../../chat_ui/chat_ui/theme.py), when it is read, then it declares the rail's width, row height and gutter as named tokens, in the style of the existing `RAIL_X`, `ROW_H`, `COLUMN_MAX` group.
- [ ] Given the diff, when it is inspected, then **no new colour value is added**. PRD Section 6.1: "no new inks. The rail is `PAPER` ground against the transcript's `CARD`, separated by the existing `RULE`. The active session is marked with `INK` type against `HOVER`."
- [ ] Given the new tokens, when they are read, then the active mark reuses `SPINE`, `GLYPH` and `RAIL_X` rather than declaring parallel values — the same device at a third scale, not a third device.
- [ ] Given [chat_ui/chat_ui/copy.py](../../../chat_ui/chat_ui/copy.py), when it is read, then it carries every rail string: the **New chat** label, the empty-rail invitation, the read-failure line, the not-saved notice from [[STORY-014]], the delete confirmation, the rename affordance and the fallback title from [[STORY-012]].
- [ ] Given the delete confirmation string, when it is read, then it names the chat and states that the record of what was checked is kept — in the user's words, not in schema terms.
- [ ] Given the empty-rail string, when it is read, then it invites the reader to start a chat rather than reporting that none exist. The **frontend-design** skill, verbatim: "An empty screen is an invitation to act."
- [ ] Given the read-failure string, when it is read, then it names what failed and offers the retry, and it does not apologize. Same skill, verbatim: "Errors don't apologize, and they are never vague about what happened."
- [ ] Given [tests/test_copy.py](../../../tests/test_copy.py), when it runs, then it asserts every new constant exists and is non-empty, following the file's existing pattern.
- [ ] Given [tests/test_contrast.py](../../../tests/test_contrast.py), when it runs, then it passes unmodified — because no new ink/ground pairing was introduced. If one was, this story added a colour it was told not to add.

## Technical Notes

- Files: [chat_ui/chat_ui/theme.py](../../../chat_ui/chat_ui/theme.py), [chat_ui/chat_ui/copy.py](../../../chat_ui/chat_ui/copy.py), [tests/test_copy.py](../../../tests/test_copy.py).
- The single-file rule is PRD-006's and carries forward: any new token is added to `theme.py` and nowhere else. A literal `"0.75rem"` inside [chat_ui/chat_ui/components/session_rail.py](../../../chat_ui/chat_ui/components/session_rail.py) in [[STORY-018]] is a defect this story exists to prevent.
- The **frontend-design** skill's governing rule here, verbatim: *"where the brief pins down a visual direction, follow it exactly — the brief's own words always win."* The brief is PRD Section 6.1 and `theme.py`'s inspection ledger. This story proposes no direction; it declares what the pinned one needs.
- Also verbatim, on the refusal this story enforces: the skill names the three AI-default looks and warns that they "are defaults rather than choices, and they appear regardless of subject." PRD Section 6.1 applies that to this surface: "The template answer is the assistant-app sidebar: a dark panel, rounded pill rows, a hover-revealed kebab menu, relative timestamps under every title, and a bright 'New chat' button at the top."
- The verdict inks stay out. PRD Section 6.1: "The seven verdict inks stay in the transcript, where they mean something: a rail row is not a verdict and must not borrow one." No `TINT_*` token appears in the rail either.
- Every string this story adds is consumed in [[STORY-018]] or by an event handler from [[STORY-014]] and [[STORY-016]]. If a string has no consumer by the end of Phase 4, it should not have been added.
- Per PRD-004 STORY-007's rule, carried into PRD Section 4: no literal user-facing text in a component.

## Dependencies

- **Blocked by**: None
- **Blocks**: STORY-018

## PRD Reference

Source: [`PRD-008/PRD.md`](../../PRDs/PRD-008-chat-sessions/PRD.md) — Section 4 (Surface), Section 6.1 (Color, Copy), Section 11 (Quality indicators), Section 12 Phase 4, Risk 6
