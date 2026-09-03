---
id: STORY-020
prd: PRD-008
slug: rail-design-guards
title: "Palette-drift and contrast assertions so the sidebar default fails a test, not a review"
type: technical
priority: high
complexity: small
phase: "4 - Surface and hardening"
status: todo
labels: [tests, ui, design, a11y]
epic_branch: epic/PRD-008-chat-sessions
plan: null
report: null
commit: null
depends_on: [STORY-018, STORY-019]
blocks: []
skills: [frontend-design]
created: 2026-09-02
updated: 2026-09-02
---

# STORY-020: Palette-drift and contrast assertions so the sidebar default fails a test, not a review

## Description

As a maintainer, I want the rail's design refusals enforced by the suite, so that the drift toward a rounded, filled, accented sidebar is caught by CI rather than by whoever happens to review the pull request.

PRD-006 Risk 6 established this move for the register and it carries forward: the refusals are "written into Section 4's scope and Section 11's quality bar as checkable items, not left as taste."

## Acceptance Criteria

- [ ] Given a test over [chat_ui/chat_ui/components/session_rail.py](../../../chat_ui/chat_ui/components/session_rail.py)'s rendered output, when it runs, then it asserts no `TINT_*` value appears.
- [ ] Given the same test, when it runs, then it asserts none of the seven verdict inks (`INK_CLEAR`, `INK_HELD`, `INK_DENIED`, `INK_FORBIDDEN`, `INK_UPSTREAM`, `INK_FAULT`, `INK_SELF`) appears in the rail.
- [ ] Given the same test, when it runs, then it asserts no border radius other than `theme.RADIUS` appears — the pill row is the drift's most likely first step.
- [ ] Given the same test, when it runs, then it asserts every colour in the rail resolves to one of the ground tokens (`PAPER`, `CARD`, `INK`, `MUTE`, `RULE`, `RULE_SOFT`, `HOVER`, `SPINE`).
- [ ] Given a deliberate violation added during implementation — a `TINT_HELD` background on the active row — when the suite runs, then this test fails; the violation is then removed.
- [ ] Given [tests/test_contrast.py](../../../tests/test_contrast.py), when it runs, then every ink/ground pairing the rail actually uses is covered and clears WCAG AA, including the active row's `INK` on `HOVER`.
- [ ] Given [tests/test_render_invariants.py](../../../tests/test_render_invariants.py), when it runs, then it passes with the rail present, and any invariant it encodes for the chat surface still holds.
- [ ] Given [tests/test_copy.py](../../../tests/test_copy.py), when it runs, then it asserts no literal user-facing string appears in the rail component — every one resolves from [chat_ui/chat_ui/copy.py](../../../chat_ui/chat_ui/copy.py).

## Technical Notes

- Files: [tests/test_contrast.py](../../../tests/test_contrast.py), [tests/test_copy.py](../../../tests/test_copy.py), and a new or extended render-invariant test. No production code — if a guard fails, the fix belongs in [[STORY-017]], [[STORY-018]] or [[STORY-019]], with the reason recorded in this story's report.
- Follow whatever mechanism [tests/test_admin_palette.py](../../../tests/test_admin_palette.py) already uses for PRD-006's equivalent guard rather than inventing a second way to inspect rendered output.
- PRD Risk 6 is the whole justification, verbatim: "'Chat with a session list' is the most templated pattern in current UI, and the drift arrives one reasonable component at a time — a card for a row, a rounded highlight for the active one, an accent for the button. *Mitigation*: ... a component test asserts the rail renders no `TINT_*` value, no verdict ink and no border radius beyond `theme.RADIUS` — the drift fails a test rather than a review."
- The **frontend-design** skill's calibration is what these assertions encode, verbatim: the three AI-default looks "are legitimate for some briefs, but they are defaults rather than choices, and they appear regardless of subject."
- Adding the violation and watching it fail is not optional. A guard that has never been red is a guard nobody has verified.
- `tests/test_contrast.py` should need **no new pairing** if [[STORY-017]] held the line on colours. A new pairing appearing here is a signal worth recording, not a routine addition.

## Dependencies

- **Blocked by**: STORY-018, STORY-019
- **Blocks**: None

## PRD Reference

Source: [`PRD-008/PRD.md`](../../PRDs/PRD-008-chat-sessions/PRD.md) — Section 6.1, Section 11 (Quality indicators), Section 12 Phase 4, Risk 6
