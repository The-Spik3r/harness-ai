---
id: STORY-009
prd: PRD-006
slug: admin-shell-and-gate
title: "admin_shell.py: token gate form, masthead, and the two-view switch"
type: feature
priority: high
complexity: medium
phase: "2 - The register"
status: todo
labels: [ui, reflex, component, design, admin]
epic_branch: epic/PRD-006-admin-console
plan: null
report: null
commit: null
depends_on: [STORY-003, STORY-007, STORY-008]
blocks: [STORY-010, STORY-011, STORY-015]
skills: [frontend-design, reflex-docs]
created: 2026-08-28
updated: 2026-08-28
---

# STORY-009: admin_shell.py: token gate form, masthead, and the two-view switch

## Description

As a compliance admin, I want one console shell that asks for the token and then carries the masthead and the switch between the two views, so that both pages are gated the same way and reached the same way (PRD Section 4, Section 6.1 layout).

## Acceptance Criteria

- [ ] Given `chat_ui/chat_ui/components/admin_shell.py`, when it is created, then it exports a gate component, a masthead component and a wrapper that renders the gate when `AdminState.authenticated` is False and its content when True.
- [ ] Given `/admin/stats` reached directly with no session, when it renders, then the gate is shown and no data appears — both pages assert the condition independently (Risk 1).
- [ ] Given a submitted wrong or empty token, when the gate re-renders, then it shows the one generic refusal message from `admin_copy` and the token field is not repopulated.
- [ ] Given the masthead, when it renders, then it carries the console title, the two-view switch (Register / Summary) separated by a rule, and the sign-out control — matching PRD Section 6.1's wireframe, with a hairline under it.
- [ ] Given the sign-out control, when it is activated, then the gate returns and the loaded rows are gone from state ([[STORY-003]]'s `sign_out`).
- [ ] Given the shell, when it is inspected, then it renders no chat component and imports nothing from `chat_ui/components/chat.py` or `bubbles.py` — PRD Section 4's cross-surface separation.
- [ ] Given the shell, when its styling is read, then every colour and size resolves from [theme.py](../../../chat_ui/chat_ui/theme.py) and every string from `admin_copy` — no literal hex, no literal text.
- [ ] Given a keyboard user, when they tab to the token field, the submit, the view switch and sign out, then focus is visible on each.

## Technical Notes

- New file `chat_ui/chat_ui/components/admin_shell.py`, alongside the existing [chat_ui/chat_ui/components/shell.py](../../../chat_ui/chat_ui/components/shell.py) — whose `user_id_gate()` is the closest existing pattern for a full-page gate; follow its structure, not the chat's styling.
- PRD Section 6: "**Gate as state, not as route**: the pages exist unconditionally; the token check decides what they render. Reflex has no server-side route guard here, so the guard is the render condition — and the data is not loaded until it passes."
- PRD Section 6.1 pins the layout: "one column, no sidebar. The two views are peers reached from a rule-separated switch in the header, because there are exactly two and a sidebar for two destinations is furniture."
- The **frontend-design** skill, verbatim: "Spend your boldness in one place. Let the signature element be the one memorable thing, keep everything around it quiet and disciplined, and cut any decoration that does not serve the brief." The signature is the stamp margin ([[STORY-011]]) — the shell stays hairlines and alignment.
- Per `chat_ui/AGENTS.md`, verbatim: "For anything about Reflex APIs — components, state management, events, styling, database, routing, authentication — use the **reflex-docs** skill rather than relying on memory. It carries current, version-accurate docs." `rx.cond` for the gate condition and form submit handling are the APIs to confirm.
- No Radix card. Risk 6: the drift "arrives one reasonable-looking component at a time, usually as a Radix card imported for convenience."

## Dependencies

- **Blocked by**: STORY-003, STORY-007, STORY-008
- **Blocks**: STORY-010, STORY-011, STORY-015

## PRD Reference

Source: [`PRD-006/PRD.md`](../../PRDs/PRD-006-admin-console/PRD.md) — Section 4 (console shell & access), Section 6 (gate as state), Section 6.1 (layout), Section 12 Phase 2, Risks 1 and 6
