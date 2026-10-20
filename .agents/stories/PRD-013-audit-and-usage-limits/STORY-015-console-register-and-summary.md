---
id: STORY-015
prd: PRD-013
slug: console-register-and-summary
title: "Admin console: Register fields, verdict, search and summary figures"
type: feature
priority: medium
complexity: medium
phase: "4 - See it and prove it"
status: done
labels: [frontend, admin-console, audit]
epic_branch: epic/PRD-013-audit-and-usage-limits
plan: .agents/plans/PRD-013-audit-and-usage-limits/completed/STORY-015-console-register-and-summary.plan.md
report: .agents/reports/PRD-013-audit-and-usage-limits/STORY-015-console-register-and-summary.report.md
commit: b6085a4
depends_on: [STORY-006, STORY-011]
blocks: [STORY-016, STORY-018]
skills: [frontend-design]
created: 2026-10-04
updated: 2026-10-19
---

# STORY-015: Admin console: Register fields, verdict, search and summary figures

## Description

As a compliance admin, I want the Register and summary to show the new audit fields and to find a conversation by its key, so that I can read an agent's work as one thing and see what was refused for usage.

## Acceptance Criteria

- [ ] Given a row with a token split, when the Register renders it, then the tokens cell reads input / output (for example `2,140 / 312`); given a row with only a total, then it shows the total; given neither, then the absent mark.
- [ ] Given a row's disclosure, when it is opened, then it shows ingress, message count, conversation key, streamed, tool calls and limit, each with the absent mark when NULL, and `AuditRow` still has no preview field (`tests/test_admin_models.py` passes).
- [ ] Given a `conversation_key` or an ingress name typed into the search, when the Register filters, then only rows with that key or ingress remain, without a database read.
- [ ] Given a row with `limit_exceeded` set, when its verdict is derived, then it is **denied**, and every existing row's verdict is unchanged (existing `derive_verdict` tests pass unmodified).
- [ ] Given the summary, when it loads, then it shows total input tokens, total output tokens and the usage-limit refusal count, each with its scope line, and a failure of one of those reads names that figure and leaves the others rendered.

## Technical Notes

- `frontend-design`, verbatim: *"Structure is information. Structural devices, numbering, eyebrows, dividers, labels, should encode something true about the content, not decorate it."* The Register gains no column: the tokens cell changes format and the rest is disclosure. New labels name what an admin recognises ("Ingress", "Messages", "Conversation"), not column names.
- Follow the existing register and summary components and `theme.py`; no new visual direction (PRD Section 6.10).
- `admin_formatting.py`: `derive_verdict` gains one line for `limit_exceeded`, placed after `was_duplicate_blocked` and before the `success` check; update the precedence comment above the constants. A permission refusal reading **cleared** today is noted in the PRD's Evidence and is not changed here.
- `admin_models.py`: `AuditRow` gains plain pre-formatted string fields. `to_audit_row` formats them once; components do not compute.
- `admin_state.py`: `_matches` adds `conversation_key` and `ingress` to the needle's haystack. The three summary state fields and read labels were declared in STORY-006; this story renders them in `components/summary.py` and adds copy to `admin_copy.py`.
- Every new state var needs a falsy default so `sign_out()` clears it (`test_sign_out_clears_every_declared_var`).
- Tests: `tests/test_admin_formatting.py`, `tests/test_register.py`, `tests/test_summary.py`, `tests/test_admin_state.py`.

## Dependencies

- **Blocked by**: STORY-006, STORY-011
- **Blocks**: STORY-016, STORY-018

## PRD Reference

Source: [`PRD-013-audit-and-usage-limits/PRD.md`](../../PRDs/PRD-013-audit-and-usage-limits/PRD.md) — sections 6.10, 7 (F15), 11 (Surfaces), 14 (Risk 6)
