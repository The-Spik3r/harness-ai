---
id: STORY-008
prd: PRD-006
slug: admin-copy-module
title: "admin_copy.py: every admin-facing string in one module"
type: technical
priority: high
complexity: small
phase: "2 - The register"
status: done
labels: [ui, copy, admin]
epic_branch: epic/PRD-006-admin-console
plan: .agents/plans/PRD-006-admin-console/completed/STORY-008-admin-copy-module.plan.md
report: .agents/reports/PRD-006-admin-console/STORY-008-admin-copy-module.report.md
commit: cc857e7
depends_on: []
blocks: [STORY-009, STORY-011, STORY-012, STORY-013, STORY-014, STORY-015, STORY-016, STORY-017]
skills: [frontend-design]
created: 2026-08-28
updated: 2026-08-30
---

# STORY-008: admin_copy.py: every admin-facing string in one module

## Description

As an integrating developer, I want every user-facing string on the console to resolve from one copy module, so that no literal text lives in a component and the wording of a figure's label can be asserted in a test (PRD Section 4, Section 11).

## Acceptance Criteria

- [ ] Given `chat_ui/chat_ui/admin_copy.py`, when it is created, then it holds every admin-facing string: the masthead, the two view-switch labels, the sign-out label, the gate prompt and its single refusal message, the column heads, the four verdict labels, the scope lines, the refresh label and refreshed stamp template, the fault panel, and the three empty states.
- [ ] Given any admin component, when it is grepped for quoted user-facing text, then none is found — every string resolves through `admin_copy`.
- [ ] Given a label with a value in it, when it is defined, then it is a template constant (as [chat_ui/chat_ui/copy.py](../../../chat_ui/chat_ui/copy.py)'s `PII_BADGE_TEMPLATE` is) rather than string concatenation at the call site — including "100 most recent of {total}" and "Refreshed {time}".
- [ ] Given the refresh control and the post-refresh line, when both are read, then they share the same verb — the control labeled **Refresh** produces the line **Refreshed 14:22:07**, and **Sign out** returns the gate rather than a "session ended" notice.
- [ ] Given the gate refusal string, when it is read, then it states that access was refused and does not say why — one message for empty, malformed and wrong tokens alike.
- [ ] Given `admin_copy.py`, when [tests/test_copy.py](../../../tests/test_copy.py) is extended, then each constant is asserted non-empty, matching the existing test's pattern.

## Technical Notes

- New file `chat_ui/chat_ui/admin_copy.py`, modelled on [chat_ui/chat_ui/copy.py](../../../chat_ui/chat_ui/copy.py) (PRD-004 STORY-007). Keep it a separate module rather than extending `copy.py` — PRD Section 6 lists it as a new file, and the surfaces stay separate.
- The **frontend-design** skill, verbatim: "Errors don't apologize, and they are never vague about what happened." and "An empty screen is an invitation to act." and "An action keeps the same name through the whole flow, so the button that says 'Publish' produces a toast that says 'Published.'"
- PRD Section 6.1 fixes the register's copy jobs: "The fault panel names the read that failed and offers the retry; the gate says access was refused without saying why; the no-matches state names the filter that produced it and offers to clear it."
- The completion-figure label is the one string with a correctness requirement — PRD Section 4: "`success_rate` labeled for what it counts — rows the pipeline completed without raising, blocked rows included — not as an answer rate." Define it here; the test that pins its wording is [[STORY-016]].
- PRD Section 4 out of scope: "A full i18n framework — copy centralization only, as in PRD-004." Constants, not a catalogue.

## Dependencies

- **Blocked by**: None
- **Blocks**: STORY-009, STORY-011, STORY-012, STORY-013, STORY-014, STORY-015, STORY-016, STORY-017

## PRD Reference

Source: [`PRD-006/PRD.md`](../../PRDs/PRD-006-admin-console/PRD.md) — Section 4 (design & copy), Section 6 (files), Section 6.1 (copy), Section 11
