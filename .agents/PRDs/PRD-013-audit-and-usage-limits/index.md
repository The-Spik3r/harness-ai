# PRD-013-audit-and-usage-limits: Audit for Conversations and Usage Limits — What Was Attempted, Through Which Door, at What Cost, Within a Bound — Story Board

**PRD**: [PRD.md](./PRD.md)
**Epic Branch**: `epic/PRD-013-audit-and-usage-limits` (base: `main`)
**Status**: active

## Progress

1/18 stories done — 6%

## Stories

All stories commit on the epic branch `epic/PRD-013-audit-and-usage-limits`. No per-story branches.

| ID | Title | Type | Status | Complexity | Plan | Commit |
|----|-------|------|--------|------------|------|--------|
| STORY-001 | Characterize today's audit row per arm and the client's usage parsing | technical | ✅ done | small | [plan](../../plans/PRD-013-audit-and-usage-limits/completed/STORY-001-audit-characterization.plan.md) | `126f0da` |
| STORY-002 | Eight additive audit columns: convergence, AuditLog, writer and both read shapes | technical | 🟡 in-progress | medium | [plan](../../plans/PRD-013-audit-and-usage-limits/STORY-002-audit-columns.plan.md) | — |
| STORY-003 | OpenRouter client returns input and output tokens separately | feature | ⬜ todo | small | — | — |
| STORY-004 | conversation_key derivation | feature | ⬜ todo | small | — | — |
| STORY-005 | log_query and every pipeline arm write the new fields; ingress at every call site | feature | ⬜ todo | large | — | — |
| STORY-006 | /audit entry fields and /stats token aggregates | feature | ⬜ todo | medium | — | — |
| STORY-007 | Limit and break-glass settings with startup validators | technical | ⬜ todo | small | — | — |
| STORY-008 | Per-user limit overrides: users columns, Identity fields and manage_users set-limits | feature | ⬜ todo | medium | — | — |
| STORY-009 | usage_daily table with atomic admit and charge statements; RETURNING verified | spike | ⬜ todo | medium | — | — |
| STORY-010 | usage_limits: limit resolution and the rate and budget checks | feature | ⬜ todo | medium | — | — |
| STORY-011 | Usage gate in the pipeline: response, audited arm and duplicate-lookup exclusion | feature | ⬜ todo | large | — | — |
| STORY-012 | Charge tokens after the upstream call; BYOK and counter-failure rules | feature | ⬜ todo | medium | — | — |
| STORY-013 | Break-glass ingress policy | feature | ⬜ todo | small | — | — |
| STORY-014 | Chat UI usage-limit bubble | feature | ⬜ todo | medium | — | — |
| STORY-015 | Admin console: Register fields, verdict, search and summary figures | feature | ⬜ todo | medium | — | — |
| STORY-016 | Admin console: Usage table | feature | ⬜ todo | medium | — | — |
| STORY-017 | Two-instance limit test and latency measurement | technical | ⬜ todo | medium | — | — |
| STORY-018 | Regression sweep, README and .env docs | technical | ⬜ todo | medium | — | — |

## Status Icons
- ⬜ todo
- 🟡 in-progress
- ✅ done
- 🔴 blocked

## Dependencies

- STORY-002 blocked by STORY-001
- STORY-003 blocked by STORY-001
- STORY-005 blocked by STORY-001, STORY-002, STORY-003, STORY-004
- STORY-006 blocked by STORY-005
- STORY-010 blocked by STORY-007, STORY-008, STORY-009
- STORY-011 blocked by STORY-002, STORY-005, STORY-010
- STORY-012 blocked by STORY-003, STORY-011
- STORY-013 blocked by STORY-005, STORY-007, STORY-008
- STORY-014 blocked by STORY-011
- STORY-015 blocked by STORY-006, STORY-011
- STORY-016 blocked by STORY-008, STORY-009, STORY-011, STORY-015
- STORY-017 blocked by STORY-012
- STORY-018 blocked by STORY-013, STORY-014, STORY-015, STORY-016, STORY-017
