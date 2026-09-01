# PRD-006: Admin Console — Audit Register & Summary — Story Board

**PRD**: [PRD.md](./PRD.md)
**Epic Branch**: `epic/PRD-006-admin-console` (base: `main`)
**Status**: active

## Progress

19/20 stories done — 95%

## Stories

All stories commit on the epic branch `epic/PRD-006-admin-console`. No per-story branches.

| ID | Title | Type | Status | Complexity | Plan | Commit |
|----|-------|------|--------|------------|------|--------|
| STORY-001 | AuditRow and SummaryFigure models — a projection with no preview fields | technical | ✅ done | small | [plan](../../plans/PRD-006-admin-console/completed/STORY-001-audit-row-model.plan.md) | `577a285` |
| STORY-002 | admin_formatting.py: verdict derivation, relative time, device and shares | technical | ✅ done | medium | [plan](../../plans/PRD-006-admin-console/completed/STORY-002-verdict-derivation-formatting.plan.md) | `0fe6c69` |
| STORY-003 | AdminState token gate: compare_digest, one generic error, sign-out clears state | feature | ✅ done | medium | [plan](../../plans/PRD-006-admin-console/completed/STORY-003-admin-token-gate.plan.md) | `048a873` |
| STORY-004 | AdminState.load(): all ten read functions via asyncio.to_thread, with a catch-all fault arm | feature | ✅ done | medium | [plan](../../plans/PRD-006-admin-console/completed/STORY-004-threaded-database-read.plan.md) | `e8c331e` |
| STORY-005 | Client-side filter and sort as computed vars over the loaded rows | feature | ✅ done | medium | [plan](../../plans/PRD-006-admin-console/completed/STORY-005-filter-and-sort-vars.plan.md) | `631bbff` |
| STORY-006 | tests/test_admin_state.py: gate, sign-out, failed read, four verdicts, no leak | technical | ✅ done | medium | [plan](../../plans/PRD-006-admin-console/completed/STORY-006-admin-state-tests.plan.md) | `3d6474e` |
| STORY-007 | theme.py register tokens: row height, stamp-margin width, hover ground, micro type step | technical | ✅ done | small | [plan](../../plans/PRD-006-admin-console/completed/STORY-007-register-theme-tokens.plan.md) | `a650a97` |
| STORY-008 | admin_copy.py: every admin-facing string in one module | technical | ✅ done | small | [plan](../../plans/PRD-006-admin-console/completed/STORY-008-admin-copy-module.plan.md) | `cc857e7` |
| STORY-009 | admin_shell.py: token gate form, masthead, and the two-view switch | feature | ✅ done | medium | [plan](../../plans/PRD-006-admin-console/completed/STORY-009-admin-shell-and-gate.plan.md) | `5a35ce3` |
| STORY-010 | Register /admin, /admin/audit and /admin/stats without touching a reserved route | technical | ✅ done | small | [plan](../../plans/PRD-006-admin-console/completed/STORY-010-admin-route-registration.plan.md) | `b030618` |
| STORY-011 | register.py: the audit table, the verdict column and the stamp margin | feature | ✅ done | large | [plan](../../plans/PRD-006-admin-console/completed/STORY-011-register-table-stamp-margin.plan.md) | `9228979` |
| STORY-012 | Row detail disclosure: error_message, prompt_hash, PII entities, full User-Agent, pattern | feature | ✅ done | medium | [plan](../../plans/PRD-006-admin-console/completed/STORY-012-row-detail-disclosure.plan.md) | `0d1c15b` |
| STORY-013 | Verdict multi-select, free-text filter and sort controls on the register | feature | ✅ done | medium | [plan](../../plans/PRD-006-admin-console/completed/STORY-013-filter-and-sort-controls.plan.md) | `32efec0` |
| STORY-014 | Three distinct register states: nothing recorded, nothing matching, rows shown | feature | ✅ done | small | [plan](../../plans/PRD-006-admin-console/completed/STORY-014-three-empty-states.plan.md) | `3fe5dda` |
| STORY-015 | summary.py: nine StatsResponse figures as a ruled tally sheet with stated scopes | feature | ✅ done | large | [plan](../../plans/PRD-006-admin-console/completed/STORY-015-summary-tally-sheet.plan.md) | `d8a9a9d` |
| STORY-016 | Copy test pinning the completion label so it cannot regress to "success rate" | technical | ✅ done | small | [plan](../../plans/PRD-006-admin-console/completed/STORY-016-completion-label-copy-test.plan.md) | `5e41346` |
| STORY-017 | Manual refresh with a last-refreshed stamp, and a fault panel with retry on both pages | feature | ✅ done | medium | [plan](../../plans/PRD-006-admin-console/completed/STORY-017-refresh-and-fault-panel.plan.md) | `3a64c47` |
| STORY-018 | Render invariant tests: no previews in output, no tint or stray colour on the console | technical | ✅ done | medium | [plan](../../plans/PRD-006-admin-console/completed/STORY-018-render-invariant-tests.plan.md) | `ec7515e` |
| STORY-019 | Quality floor pass: keyboard, focus, narrow viewport — and a design self-critique | enhancement | ✅ done | medium | [plan](../../plans/PRD-006-admin-console/completed/STORY-019-quality-floor-and-critique.plan.md) | `7cd66b4` |
| STORY-020 | Full-suite regression and the proof that nothing under app/ changed | technical | ⬜ todo | small | — | — |

## Status Icons
- ⬜ todo
- 🟡 in-progress
- ✅ done
- 🔴 blocked

## Phases

| Phase | Stories |
|-------|---------|
| 1 — Access and data | STORY-001 … STORY-006 |
| 2 — The register | STORY-007 … STORY-014 |
| 3 — The summary | STORY-015, STORY-016 |
| 4 — Hardening | STORY-017 … STORY-020 |

## Dependencies

- STORY-002 blocked by STORY-001
- STORY-004 blocked by STORY-001, STORY-002, STORY-003
- STORY-005 blocked by STORY-004
- STORY-006 blocked by STORY-002, STORY-003, STORY-004, STORY-005
- STORY-009 blocked by STORY-003, STORY-007, STORY-008
- STORY-010 blocked by STORY-009
- STORY-011 blocked by STORY-001, STORY-002, STORY-004, STORY-007, STORY-008, STORY-009, STORY-010
- STORY-012 blocked by STORY-008, STORY-011
- STORY-013 blocked by STORY-005, STORY-008, STORY-011
- STORY-014 blocked by STORY-005, STORY-008, STORY-011, STORY-013
- STORY-015 blocked by STORY-002, STORY-004, STORY-007, STORY-008, STORY-009, STORY-010
- STORY-016 blocked by STORY-008, STORY-015
- STORY-017 blocked by STORY-004, STORY-008, STORY-011, STORY-015
- STORY-018 blocked by STORY-007, STORY-011, STORY-012, STORY-015
- STORY-019 blocked by STORY-017
- STORY-020 blocked by STORY-006, STORY-016, STORY-017, STORY-018, STORY-019

STORY-001, STORY-003, STORY-007 and STORY-008 have no blockers and can start in parallel.
