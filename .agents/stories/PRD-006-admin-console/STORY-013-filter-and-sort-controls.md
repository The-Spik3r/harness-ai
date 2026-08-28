---
id: STORY-013
prd: PRD-006
slug: filter-and-sort-controls
title: "Verdict multi-select, free-text filter and sort controls on the register"
type: feature
priority: high
complexity: medium
phase: "2 - The register"
status: todo
labels: [ui, reflex, component, admin]
epic_branch: epic/PRD-006-admin-console
plan: null
report: null
commit: null
depends_on: [STORY-005, STORY-008, STORY-011]
blocks: [STORY-014]
skills: [frontend-design, reflex-docs]
created: 2026-08-28
updated: 2026-08-28
---

# STORY-013: Verdict multi-select, free-text filter and sort controls on the register

## Description

As a compliance admin, I want to filter the register to one verdict or one user and to look up an `audit_id` a user quoted, so that a support report resolves to a specific row instead of a paraphrase (PRD Section 5, stories 4 and 5).

## Acceptance Criteria

- [ ] Given the register header, when it renders, then it carries a verdict multi-select over the four verdicts and a free-text field over `user_id` / `model_used` / `audit_id`, positioned as PRD Section 6.1's wireframe shows.
- [ ] Given the verdict multi-select, when a verdict is toggled, then the table narrows without a database read and the selected verdicts are visibly marked.
- [ ] Given the free-text field, when `127` is typed, then the row whose `audit_id` is 127 is isolated — closing PRD-004's chat-footer loop.
- [ ] Given both filters active, when the table renders, then they compose as AND and the row count shown reflects the filtered set, distinct from the "100 most recent of {total}" scope line.
- [ ] Given active filters, when a clear action is used, then all filters reset and the full window returns.
- [ ] Given the sort controls, when timestamp, user or verdict is chosen, then the table reorders and the active sort is visibly indicated; timestamp descending remains the default.
- [ ] Given a keyboard user, when they tab through the filter and sort controls, then each is reachable and operable with visible focus.
- [ ] Given every label on these controls, when grepped, then each resolves from `admin_copy`.

## Technical Notes

- The state and the computed var are [[STORY-005]]; this story is the controls only. No filtering logic belongs in the component.
- PRD Section 6.1's wireframe places the verdict filter on the scope line and the text filter under it, beside the refreshed stamp — follow that placement.
- Risk 5: "Every keystroke in the filter re-evaluates a computed var over the full row list." If it proves heavy in practice, debounce the input — "a UI-local change requiring nothing under `app/`". Do not add a server-side filter; PRD Section 4 puts it out of scope.
- Per `chat_ui/AGENTS.md`, verbatim: "For anything about Reflex APIs — components, state management, events, styling, database, routing, authentication — use the **reflex-docs** skill rather than relying on memory. It carries current, version-accurate docs." Confirm the current multi-select / toggle-group component and its event signature there — do not recall it.
- The **frontend-design** skill, verbatim: "A control should say exactly what happens when it's used: 'Save changes,' not 'Submit.'"
- Keep the controls in the register's hairline system: no accent colour, no filled buttons (Risk 6). The verdict chips may carry their verdict ink as text, not as a fill.

## Dependencies

- **Blocked by**: STORY-005, STORY-008, STORY-011
- **Blocks**: STORY-014

## PRD Reference

Source: [`PRD-006/PRD.md`](../../PRDs/PRD-006-admin-console/PRD.md) — Section 4 (register), Section 5 (stories 4, 5), Section 6.1 (layout), Section 7, Section 12 Phase 2, Risk 5
