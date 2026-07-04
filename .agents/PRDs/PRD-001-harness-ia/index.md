# PRD-001: Harness IA - MVP — Story Board

**PRD**: [PRD.md](./PRD.md)
**Epic Branch**: `epic/PRD-001-harness-ia` (base: `main`)
**Status**: active

## Progress

5/14 stories done — 36%

## Stories

All stories commit on the epic branch `epic/PRD-001-harness-ia`. No per-story branches.

| ID | Title | Type | Status | Complexity | Plan | Commit |
|----|-------|------|--------|------------|------|--------|
| STORY-001 | Project scaffolding & configuration loading | technical | ✅ done | small | [plan](../../plans/PRD-001-harness-ia/completed/STORY-001-project-scaffolding.plan.md) | `d94c67a` |
| STORY-002 | SQLite connection & audit_logs schema | technical | ✅ done | small | [plan](../../plans/PRD-001-harness-ia/completed/STORY-002-sqlite-audit-schema.plan.md) | `069c3ac` |
| STORY-003 | Pydantic request/response schemas | technical | ✅ done | small | [plan](../../plans/PRD-001-harness-ia/completed/STORY-003-request-response-schemas.plan.md) | `1b71812` |
| STORY-004 | Duplicate detection service (24h exact-match) | feature | ✅ done | medium | [plan](../../plans/PRD-001-harness-ia/completed/STORY-004-duplicate-detection-service.plan.md) | `f4b431f` |
| STORY-005 | Suspicious pattern detection service | feature | ✅ done | small | [plan](../../plans/PRD-001-harness-ia/completed/STORY-005-pattern-detection-service.plan.md) | `42724a4` |
| STORY-006 | Audit logging service | feature | ⬜ todo | medium | — | — |
| STORY-007 | OpenRouter API client wrapper | feature | ⬜ todo | medium | — | — |
| STORY-008 | POST /query endpoint: full interception pipeline | feature | ⬜ todo | medium | — | — |
| STORY-009 | Admin token authentication middleware | technical | ⬜ todo | small | — | — |
| STORY-010 | GET /audit endpoint | feature | ⬜ todo | medium | — | — |
| STORY-011 | GET /stats endpoint | feature | ⬜ todo | medium | — | — |
| STORY-012 | End-to-end integration test suite | technical | ⬜ todo | medium | — | — |
| STORY-013 | Docker & docker-compose packaging | technical | ⬜ todo | medium | — | — |
| STORY-014 | README & usage documentation | technical | ⬜ todo | small | — | — |

## Status Icons
- ⬜ todo
- 🟡 in-progress
- ✅ done
- 🔴 blocked

## Dependencies

- STORY-002 blocked by STORY-001
- STORY-003 blocked by STORY-001
- STORY-004 blocked by STORY-002, STORY-003
- STORY-005 blocked by STORY-003
- STORY-006 blocked by STORY-002, STORY-003
- STORY-007 blocked by STORY-003
- STORY-008 blocked by STORY-004, STORY-005, STORY-006, STORY-007
- STORY-009 blocked by STORY-001
- STORY-010 blocked by STORY-002, STORY-009
- STORY-011 blocked by STORY-002, STORY-009
- STORY-012 blocked by STORY-008, STORY-010, STORY-011
- STORY-013 blocked by STORY-012
- STORY-014 blocked by STORY-013
