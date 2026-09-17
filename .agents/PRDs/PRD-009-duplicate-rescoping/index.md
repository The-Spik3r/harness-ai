# PRD-009-duplicate-rescoping: Duplicate Detection Rescoping — Per-Caller, Conversation-Shaped Keys — Story Board

**PRD**: [PRD.md](./PRD.md)
**Epic Branch**: `epic/PRD-009-duplicate-rescoping` (base: `main`)
**Status**: active

## Progress

4/10 stories done — 40%

## Stories

All stories commit on the epic branch `epic/PRD-009-duplicate-rescoping`. No per-story branches.

| ID | Title | Type | Status | Complexity | Plan | Commit |
|----|-------|------|--------|------------|------|--------|
| STORY-001 | Characterization tests of today's duplicate lookup and the six-outcome /query baseline, on untouched production code | technical | ✅ done | medium | [plan](../../plans/PRD-009-duplicate-rescoping/completed/STORY-001-characterization-and-outcome-baseline.plan.md) | `9abef61` |
| STORY-002 | audit_logs.dedup_key column and idx_audit_logs_dedup, converged by init_db() and round-tripped by AuditLog | technical | ✅ done | small | [plan](../../plans/PRD-009-duplicate-rescoping/completed/STORY-002-dedup-key-column-and-index.plan.md) | `c8b303b` |
| STORY-003 | dedup_key(user_id, turns): a pure, versioned key over a conversation, with single-turn as the empty-prefix case | feature | ✅ done | small | [plan](../../plans/PRD-009-duplicate-rescoping/completed/STORY-003-conversation-dedup-key-function.plan.md) | `2603805` |
| STORY-004 | Duplicate lookup ignores failed, policy-denied and duplicate-blocked rows | bug | ✅ done | medium | [plan](../../plans/PRD-009-duplicate-rescoping/completed/STORY-004-lookup-excludes-non-verdict-rows.plan.md) | `dde39d9` |
| STORY-005 | Duplicate lookup scoped by the authenticated user_id | bug | ⬜ todo | small | — | — |
| STORY-006 | run_query computes dedup_key once and log_query writes it on all seven arms | feature | ⬜ todo | medium | — | — |
| STORY-007 | check_duplicate(user_id, key) and the lookup match on dedup_key, with the pinned contract tests updated | feature | ⬜ todo | medium | — | — |
| STORY-008 | End-to-end /query tests for every row of the what-counts table: two users, retry after failure, denial, chaining | technical | ⬜ todo | medium | — | — |
| STORY-009 | Six-outcome regression and /audit, /stats and admin-console invariance verified on the finished epic | technical | ⬜ todo | small | — | — |
| STORY-010 | README documents the rescoped control, its trade-offs and the resolved multi-turn blocker; .env.example confirmed unchanged | technical | ⬜ todo | small | — | — |

## Status Icons
- ⬜ todo
- 🟡 in-progress
- ✅ done
- 🔴 blocked

## Dependencies

- STORY-002 blocked by STORY-001
- STORY-003 blocked by STORY-001
- STORY-004 blocked by STORY-001
- STORY-005 blocked by STORY-004
- STORY-006 blocked by STORY-002, STORY-003
- STORY-007 blocked by STORY-005, STORY-006
- STORY-008 blocked by STORY-007
- STORY-009 blocked by STORY-008
- STORY-010 blocked by STORY-007, STORY-009
