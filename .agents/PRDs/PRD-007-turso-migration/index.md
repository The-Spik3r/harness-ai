# PRD-007-turso-migration: Turso / libSQL Migration — Story Board

**PRD**: [PRD.md](./PRD.md)
**Epic Branch**: `epic/PRD-007-turso-migration` (base: `main`)
**Status**: active

## Progress

7/16 stories done — 44%

## Stories

All stories commit on the epic branch `epic/PRD-007-turso-migration`. No per-story branches.

| ID | Title | Type | Status | Complexity | Plan | Commit |
|----|-------|------|--------|------------|------|--------|
| STORY-001 | Spike: verify the six risky libSQL client behaviors and record the driver decision | spike | ✅ done | medium | [plan](../../plans/PRD-007-turso-migration/completed/STORY-001-libsql-driver-spike.plan.md) | `6e6b1c4` |
| STORY-002 | Characterization tests pinning the three driver-exception behaviors against current SQLite | technical | ✅ done | small | [plan](../../plans/PRD-007-turso-migration/completed/STORY-002-exception-characterization-tests.plan.md) | `403b191` |
| STORY-003 | Centralize the 27 DATABASE_URL test sites behind one conftest fixture, still SQLite-backed | technical | ✅ done | medium | [plan](../../plans/PRD-007-turso-migration/completed/STORY-003-centralize-database-url-fixture.plan.md) | `eebfc71` |
| STORY-004 | app/db/errors.py: a module-owned exception surface, decoupling the three catch sites from sqlite3 | technical | ✅ done | small | [plan](../../plans/PRD-007-turso-migration/completed/STORY-004-module-owned-error-surface.plan.md) | `2961f33` |
| STORY-005 | Config: TURSO_AUTH_TOKEN, libSQL DATABASE_URL semantics, and no file fallback | feature | ✅ done | small | [plan](../../plans/PRD-007-turso-migration/completed/STORY-005-turso-configuration.plan.md) | `907eb6c` |
| STORY-006 | Swap app/db/database.py onto a shared libSQL client, preserving all 22 public signatures | feature | ✅ done | large | [plan](../../plans/PRD-007-turso-migration/completed/STORY-006-libsql-connection-layer.plan.md) | `86ece73` |
| STORY-007 | Make init_db() and _add_missing_columns() converge under concurrent multi-instance startup | technical | ✅ done | medium | [plan](../../plans/PRD-007-turso-migration/completed/STORY-007-concurrent-safe-init-db.plan.md) | `pending` |
| STORY-008 | Fail fast and legibly when the database is unreachable or the token is missing | feature | ⬜ todo | small | — | — |
| STORY-009 | Aggregate top_pii_entities() in SQL instead of transferring every PII-bearing row | enhancement | ⬜ todo | small | — | — |
| STORY-010 | One batched database read returning all ten summary figures in a single round trip | feature | ⬜ todo | medium | — | — |
| STORY-011 | GET /stats consumes the batched read instead of nine sequential calls | enhancement | ⬜ todo | small | — | — |
| STORY-012 | AdminState._READS consumes the batched read, preserving per-figure failure attribution | enhancement | ⬜ todo | medium | — | — |
| STORY-013 | scripts/migrate_to_turso.py: copy audit_logs and users with verification and a rollback point | feature | ⬜ todo | medium | — | — |
| STORY-014 | Cutover: remove the harness_data volume, the build placeholder, and harness_ai.db | technical | ⬜ todo | small | — | — |
| STORY-015 | README: correct the persistence claim, the env table, and document multi-instance deployment | technical | ⬜ todo | small | — | — |
| STORY-016 | Prove two instances share one database: concurrent writes, cross-instance duplicate detection, no lost rows | technical | ⬜ todo | medium | — | — |

## Status Icons
- ⬜ todo
- 🟡 in-progress
- ✅ done
- 🔴 blocked

## Dependencies

- STORY-004 blocked by STORY-002
- STORY-005 blocked by STORY-001
- STORY-006 blocked by STORY-001, STORY-003, STORY-004, STORY-005
- STORY-007 blocked by STORY-006
- STORY-008 blocked by STORY-006
- STORY-009 blocked by STORY-006
- STORY-010 blocked by STORY-006, STORY-009
- STORY-011 blocked by STORY-010
- STORY-012 blocked by STORY-010
- STORY-013 blocked by STORY-006
- STORY-014 blocked by STORY-006, STORY-008, STORY-013
- STORY-015 blocked by STORY-014
- STORY-016 blocked by STORY-007, STORY-014

STORY-001 through STORY-007 are done. The driver swap has landed and `init_db()` now converges under concurrent multi-instance startup, which leaves STORY-008 (startup guard), STORY-009 (top_pii_entities in SQL), STORY-010 (batched read), STORY-013 (migration script) and STORY-014 (cutover) ready to start. STORY-016 still waits on STORY-014.

## Phases

| Phase | Stories |
|-------|---------|
| 1 — Driver verification and behavior pinning | STORY-001, STORY-002, STORY-003 |
| 2 — Storage layer swap | STORY-004, STORY-005, STORY-006, STORY-007, STORY-008 |
| 3 — Network-cost remediation | STORY-009, STORY-010, STORY-011, STORY-012 |
| 4 — Data migration and cutover | STORY-013, STORY-014, STORY-015, STORY-016 |

## Skills

| Story | Skills |
|-------|--------|
| STORY-012 | `reflex-docs` — mandated by [chat_ui/AGENTS.md](../../../chat_ui/AGENTS.md) for any change to Reflex state, events, or the database read path |

All other stories: none. `.agents/skills/` holds only `frontend-design`, scoped to visual design of new or reshaped UI; this epic is required to leave rendered output identical.
