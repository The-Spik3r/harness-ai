---
id: STORY-005
prd: PRD-006
slug: filter-and-sort-vars
title: "Client-side filter and sort as computed vars over the loaded rows"
type: feature
priority: high
complexity: medium
phase: "1 - Access and data"
status: todo
labels: [ui, reflex, state, admin]
epic_branch: epic/PRD-006-admin-console
plan: null
report: null
commit: null
depends_on: [STORY-004]
blocks: [STORY-006, STORY-013, STORY-014]
skills: [reflex-docs]
created: 2026-08-28
updated: 2026-08-28
---

# STORY-005: Client-side filter and sort as computed vars over the loaded rows

## Description

As a compliance admin, I want to narrow the register to one verdict or one user and to reorder it, so that investigating a specific report does not mean re-reading the whole window (PRD Section 5, stories 4 and 5).

## Acceptance Criteria

- [ ] Given `AdminState`, when the filter state is inspected, then it holds a verdict multi-select (`selected_verdicts`), a free-text `search` and a `sort_key` / `sort_descending` pair — all plain state vars.
- [ ] Given `visible_rows`, when it is defined, then it is a computed var over `rows` plus the filter and sort state, and evaluating it performs **no** database read.
- [ ] Given a free-text value, when it is applied, then it matches case-insensitively against `user_id`, `model_used` and `audit_id`, and typing `127` isolates the row whose `audit_id` is 127 (PRD Section 5, story 5).
- [ ] Given a verdict multi-select with `denied` selected and the text `a.torres`, when both are applied, then the two filters compose as AND and the row count narrows accordingly.
- [ ] Given `sort_key` set to timestamp, user, or verdict, when the register reads `visible_rows`, then the ordering changes and the default is timestamp, newest first — the order `list_audit_logs` returned.
- [ ] Given an empty verdict selection, when `visible_rows` is evaluated, then all rows pass the verdict filter — an empty selection means "no verdict filter", not "no rows".
- [ ] Given the filter and sort state, when `sign_out()` runs, then they are reset along with the rows.

## Technical Notes

- PRD Section 6: "the visible rows are an `rx.var` over the loaded rows plus the filter state, so filtering never re-reads the database." Per `chat_ui/AGENTS.md`, verbatim: "For anything about Reflex APIs — components, state management, events, styling, database, routing, authentication — use the **reflex-docs** skill rather than relying on memory. It carries current, version-accurate docs." Confirm the current computed-var decorator (`rx.var`) and its dependency-tracking rules there.
- The verdict constants come from [[STORY-002]]'s `admin_formatting.py`; do not re-declare the four strings here.
- Risk 5: "Every keystroke in the filter re-evaluates a computed var over the full row list." The mitigation is that 100 rows is the hard ceiling and the data is already in state. If it proves heavy, debouncing the input is "a UI-local change requiring nothing under `app/`" — do not pre-optimize with a database-side filter, which is explicitly out of scope.
- `audit_id` is an int on `AuditRow`; matching it against free text needs a string coercion — do it in the var, not in the component.
- This story delivers the state and the vars. The filter and sort **controls** are [[STORY-013]] and the no-matches empty state is [[STORY-014]].

## Dependencies

- **Blocked by**: STORY-004
- **Blocks**: STORY-006, STORY-013, STORY-014

## PRD Reference

Source: [`PRD-006/PRD.md`](../../PRDs/PRD-006-admin-console/PRD.md) — Section 4 (register), Section 5 (stories 4, 5), Section 6 (filtering as a computed var), Risk 5
