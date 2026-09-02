---
id: STORY-012
prd: PRD-007
slug: admin-console-batched-reads
title: "AdminState._READS consumes the batched read, preserving per-figure failure attribution"
type: enhancement
priority: high
complexity: medium
phase: "3 - Network-cost remediation"
status: done
labels: [ui, reflex, state, admin, performance]
epic_branch: epic/PRD-007-turso-migration
plan: .agents/plans/PRD-007-turso-migration/completed/STORY-012-admin-console-batched-reads.plan.md
report: .agents/reports/PRD-007-turso-migration/STORY-012-admin-console-batched-reads.report.md
commit: 784567a
depends_on: [STORY-010]
blocks: []
skills: [reflex-docs]
created: 2026-09-01
updated: 2026-09-02
---

# STORY-012: AdminState._READS consumes the batched read, preserving per-figure failure attribution

## Description

As a compliance admin, I want the console's ten summary figures to arrive in one round trip **without** losing the per-figure error messages, so that the register loads quickly and a partial failure still tells me which read broke instead of blanking the page.

This is the only place the migration is permitted to change code outside `app/db/`, and it is the most delicate change in the epic. `_READS` at [chat_ui/chat_ui/admin_state.py:229](../../../chat_ui/chat_ui/admin_state.py) is not merely a loop over ten functions — it exists so that each figure carries **its own** `READ_LABEL_*` failure copy. Batching naively turns ten legible partial failures into one blank page.

## Acceptance Criteria

- [ ] Given `AdminState.load()`, when it runs, then the ten summary figures are obtained in **one** database round trip via the batched read from [[STORY-010]].
- [ ] Given one figure's underlying statement failing, when the console renders, then the fault names that figure using its existing `READ_LABEL_*` copy, and the figures that succeeded are still displayed. The all-or-nothing failure mode is not acceptable.
- [ ] Given `tests/test_admin_shell.py`, when it runs, then its `len(_READS) == 10` assertion passes **unmodified**. If `_READS` changes shape, the ten-entry registry and its labels survive in whatever form the assertion checks.
- [ ] Given the database read, when it executes, then it is still off the event loop via `asyncio.to_thread(...)`, and state mutation still happens inside `async with self` — the Reflex background-event contract PRD-006 STORY-004 established.
- [ ] Given a load in flight, when the page is observed, then `loading` is True for its duration and False afterwards, **including on the failure path**, and `last_refreshed` is set only on success. Unchanged from PRD-006 STORY-004.
- [ ] Given any failure, when `load()` handles it, then previously loaded rows and figures are left untouched rather than cleared. Unchanged from PRD-006 STORY-004.
- [ ] Given the rendered console, when it is compared to `main` for the same data, then the output is identical — same figures, same shares, same ranked lines, same copy. `tests/test_admin_state.py`, `tests/test_summary.py`, `tests/test_admin_shell.py`, and `tests/test_render_invariants.py` pass with their assertions unchanged.
- [ ] Given an unauthenticated state, when `load()` is called, then it returns immediately and performs no database read — PRD-006 STORY-003's guard is unchanged.

## Technical Notes

- Files: [chat_ui/chat_ui/admin_state.py](../../../chat_ui/chat_ui/admin_state.py) (`_READS` and the consuming loop at [line 1018](../../../chat_ui/chat_ui/admin_state.py)). Tests: `tests/test_admin_shell.py`, `tests/test_admin_state.py`, `tests/test_summary.py`.
- Per [chat_ui/AGENTS.md](../../../chat_ui/AGENTS.md), verbatim: "For anything about Reflex APIs — components, state management, events, styling, database, routing, authentication — use the **reflex-docs** skill rather than relying on memory. It carries current, version-accurate docs." This story touches state management, event handlers, and the database read path. Consult `reflex-docs` for the background-event decorator and the `async with self` mutation rule before writing code. The same file also requires confirming `reflex-docs`, `setup-python-env`, and `reflex-process-management` are available before editing any Reflex code — do that first.
- **The `_READS` table is the specification, not an implementation detail.** Read its full comment block starting at [line 216](../../../chat_ui/chat_ui/admin_state.py) before changing anything. It records why the table lives at module level rather than in the class body: "three of the field names below are also declared as vars on `AdminState`, and inside the class body those declarations would shadow the imported functions." That constraint survives this story.
- The mechanism to preserve is the label. PRD Section 4 (PRD-006, quoted in this PRD's Risk 6): "A failed read renders a fault panel naming what failed — never a silently empty table." One batched call with per-statement results still lets you map each result to its `READ_LABEL_*`; one batched call with a single combined exception does not. [[STORY-010]] is required to deliver the former.
- Preferred shape: keep `_READS` as the ten-entry `(field, label, ...)` registry and change only what supplies each field's value — from ten separate callables to ten slots of one batched result. That keeps the label mapping, the field names, and the existing test surface intact.
- The `asyncio.to_thread` offload is still required and its rationale changes slightly. PRD-006 STORY-004 noted "a `sqlite3.Connection` is not shareable across threads ... each read function opens its own connection, so the offload is per-call." After [[STORY-006]] there is one shared client, so re-derive the threading story from that story's report rather than reusing the old comment. If the comment is now wrong, fix it.
- One batched call means one `to_thread` hop instead of ten — a real simplification of `load()`. Take it, but do not let it quietly change the `loading` / `last_refreshed` / error-arm behavior the PRD-006 tests pin.
- `.agents/skills/` was scanned: it contains only `frontend-design`, scoped to "distinctive, intentional visual design when building new UI or reshaping an existing one." This story changes no visual design — the rendered output must be identical — so `frontend-design` does not apply. The applicable skill is `reflex-docs`, mandated by `chat_ui/AGENTS.md`.

## Dependencies

- **Blocked by**: STORY-010
- **Blocks**: None

## PRD Reference

Source: [`PRD-007/PRD.md`](../../PRDs/PRD-007-turso-migration/PRD.md) — Section 6 Pattern 3, Section 7.3, Section 5 story 5, Section 12 Phase 3, Section 14 Risk 6
