---
id: STORY-018
prd: PRD-006
slug: render-invariant-tests
title: "Render invariant tests: no previews in output, no tint or stray colour on the console"
type: technical
priority: high
complexity: medium
phase: "4 - Hardening"
status: todo
labels: [tests, security, design, admin]
epic_branch: epic/PRD-006-admin-console
plan: null
report: null
commit: null
depends_on: [STORY-007, STORY-011, STORY-012, STORY-015]
blocks: [STORY-020]
skills: []
created: 2026-08-28
updated: 2026-08-28
---

# STORY-018: Render invariant tests: no previews in output, no tint or stray colour on the console

## Description

As an integrating developer, I want the two invariants that are easiest to break silently — the unrendered previews and the no-cards palette — asserted by tests, so that both fail a test run rather than a review (PRD Risks 2 and 6).

## Acceptance Criteria

- [ ] Given a seeded database whose rows carry distinctive `prompt_preview` and `response_preview` strings, when the register is rendered, then neither string appears anywhere in the rendered output.
- [ ] Given `AuditRow`, when its attributes are enumerated, then it has no preview field — the boundary assertion complementing the render assertion (Risk 2).
- [ ] Given the register and the summary, when their rendered output is inspected, then no `TINT_*` value from [theme.py](../../../chat_ui/chat_ui/theme.py) appears (Risk 6).
- [ ] Given the console's rendered output, when its colour values are collected, then every one resolves to a token in `theme.py` and falls within the allowed set: the four verdict inks plus the ground tokens — no `INK_UPSTREAM`, no `INK_SELF`, no colour outside `theme.py`.
- [ ] Given a new hard-coded hex added to any admin component, when the suite runs, then the palette test fails.
- [ ] Given [tests/test_contrast.py](../../../tests/test_contrast.py), when the suite runs, then every pairing the console introduced clears `AA_NORMAL`.

## Technical Notes

- Risk 2 mitigation, verbatim: "A test asserts `AuditRow` has no preview attribute, and a render test asserts seeded preview text appears nowhere in the output."
- Risk 6 mitigation, verbatim: "A component test asserts the register renders no element carrying a `TINT_*` value and no colour outside the four verdict inks plus the ground tokens, so the drift fails a test rather than a review."
- [tests/test_pii_badge.py](../../../tests/test_pii_badge.py) and [tests/test_success_metadata_footer.py](../../../tests/test_success_metadata_footer.py) are the existing precedent for asserting over a rendered Reflex component — read how they reach the rendered output and reuse that approach rather than inventing a second one.
- Collect the allowed colour set from `theme.py` by name, not by copying hex literals into the test — otherwise a token change requires editing the test and the guard rots.
- Extend [tests/test_contrast.py](../../../tests/test_contrast.py) rather than duplicating its `contrast()` helper; it already carries the maths and the `AA_NORMAL` floor.
- No new dependency: PRD Section 8, "No new dependencies in either `requirements.txt`."

## Dependencies

- **Blocked by**: STORY-007, STORY-011, STORY-012, STORY-015
- **Blocks**: STORY-020

## PRD Reference

Source: [`PRD-006/PRD.md`](../../PRDs/PRD-006-admin-console/PRD.md) — Section 9, Section 11 (quality indicators), Section 12 Phase 4, Risks 2 and 6
