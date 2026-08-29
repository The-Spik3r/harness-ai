# PRD-005: Role-Based Access Control (RBAC) — Story Board

**PRD**: [PRD.md](./PRD.md)
**Epic Branch**: `epic/PRD-005-rbac` (base: `main`)
**Status**: active

## Progress

11/18 stories done — 61%

## Stories

All stories commit on the epic branch `epic/PRD-005-rbac`. No per-story branches.

| ID | Title | Type | Status | Complexity | Plan | Commit |
|----|-------|------|--------|------------|------|--------|
| STORY-001 | Additive schema-migration mechanism for audit_logs | technical | ✅ done | small | [plan](../../plans/PRD-005-rbac/completed/STORY-001-additive-audit-log-migration.plan.md) | `936cff8` |
| STORY-002 | users table schema and CRUD helpers | technical | ✅ done | small | [plan](../../plans/PRD-005-rbac/completed/STORY-002-users-table-schema.plan.md) | `903dee8` |
| STORY-003 | Identity resolution — token hashing, Identity value object, ADMIN_TOKEN break-glass | feature | ✅ done | medium | [plan](../../plans/PRD-005-rbac/completed/STORY-003-identity-resolution.plan.md) | `cadaebd` |
| STORY-004 | Bootstrap CLI — scripts/manage_users.py | technical | ✅ done | small | [plan](../../plans/PRD-005-rbac/completed/STORY-004-manage-users-cli.plan.md) | `10e63fc` |
| STORY-005 | RBAC configuration settings and env vars | technical | ✅ done | small | [plan](../../plans/PRD-005-rbac/completed/STORY-005-rbac-configuration-settings.plan.md) | `c2aca34` |
| STORY-006 | authz service — permission constants, default role matrix, deny-by-default authorize() | feature | ✅ done | medium | [plan](../../plans/PRD-005-rbac/completed/STORY-006-authz-permission-matrix.plan.md) | `5d5281a` |
| STORY-007 | Role matrix loaded from RBAC_ROLES_FILE at startup | feature | ✅ done | small | [plan](../../plans/PRD-005-rbac/completed/STORY-007-roles-file-override.plan.md) | `9769412` |
| STORY-008 | QueryBlockedForbiddenResponse joins the QueryResponse union | technical | ✅ done | small | [plan](../../plans/PRD-005-rbac/completed/STORY-008-forbidden-response-schema.plan.md) | `6e9e773` |
| STORY-009 | audit_logs gains role and denied_permission columns | technical | ✅ done | small | [plan](../../plans/PRD-005-rbac/completed/STORY-009-audit-rbac-columns.plan.md) | `320d2d2` |
| STORY-010 | run_query() requires an Identity and authorizes as step 0 | feature | ✅ done | medium | [plan](../../plans/PRD-005-rbac/completed/STORY-010-pipeline-identity-authorization.plan.md) | `b222be8` |
| STORY-011 | Server-side model allowlist and BYOK as a privilege | feature | ✅ done | medium | [plan](../../plans/PRD-005-rbac/completed/STORY-011-model-allowlist-and-byok.plan.md) | `PENDING` |
| STORY-012 | require_identity and require_permission FastAPI dependencies | technical | ⬜ todo | medium | — | — |
| STORY-013 | POST /query bearer authentication and status-code mapping | feature | ⬜ todo | medium | — | — |
| STORY-014 | Chat UI login replaces the free-text user_id prompt | feature | ⬜ todo | medium | — | — |
| STORY-015 | /audit scoping and /stats gating by permission | feature | ⬜ todo | medium | — | — |
| STORY-016 | Fail-fast startup guard when RBAC is enabled with no seeded users | technical | ⬜ todo | small | — | — |
| STORY-017 | RBAC test suite — full matrix coverage and ingress parity | technical | ⬜ todo | medium | — | — |
| STORY-018 | README, .env.example, and roadmap updates for RBAC | technical | ⬜ todo | small | — | — |

## Status Icons
- ⬜ todo
- 🟡 in-progress
- ✅ done
- 🔴 blocked

## Dependencies

- STORY-002 blocked by STORY-001
- STORY-003 blocked by STORY-002
- STORY-004 blocked by STORY-003
- STORY-006 blocked by STORY-003, STORY-005
- STORY-007 blocked by STORY-006
- STORY-009 blocked by STORY-001
- STORY-010 blocked by STORY-006, STORY-008, STORY-009
- STORY-011 blocked by STORY-010, STORY-005
- STORY-012 blocked by STORY-003, STORY-006
- STORY-013 blocked by STORY-010, STORY-011, STORY-012
- STORY-014 blocked by STORY-010, STORY-008
- STORY-015 blocked by STORY-012, STORY-009
- STORY-016 blocked by STORY-002, STORY-004, STORY-005
- STORY-017 blocked by STORY-013, STORY-014, STORY-015
- STORY-018 blocked by STORY-016, STORY-017

STORY-001 through STORY-011 are done. STORY-012 and STORY-016 remain unblocked and ready to plan.
