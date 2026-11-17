# PRD-018-db-resilience: Database Resilience — Retry, Circuit Breaker and Buffered Audit Writes — Story Board

**PRD**: [PRD.md](./PRD.md)
**Epic Branch**: `epic/PRD-018-db-resilience` (base: `main`)
**Status**: active

## Progress

1/14 stories done — 7%

## Stories

All stories commit on the epic branch `epic/PRD-018-db-resilience`. No per-story branches.

| ID | Title | Type | Status | Complexity | Plan | Commit |
|----|-------|------|--------|------------|------|--------|
| STORY-001 | Driver failure-surface spike — verbatim errors, failing call, and the three open questions | spike | ✅ done | small | [plan](../../plans/PRD-018-db-resilience/completed/STORY-001-driver-failure-surface-spike.plan.md) | `07bd37f` |
| STORY-002 | _classify(exc, phase), FailureClass and per-call phase tracking in _Connection | technical | ⬜ todo | small | — | — |
| STORY-003 | _unit_of_work retry boundary, statement kinds on every database.py function, _FaultyClient harness | technical | ⬜ todo | large | — | — |
| STORY-004 | write_id columns, unique indexes, idempotent insert_audit_log and insert_action_decisions | technical | ⬜ todo | medium | — | — |
| STORY-005 | Reusable CircuitBreaker class, the storage instance, StorageUnavailableError | technical | ⬜ todo | medium | — | — |
| STORY-006 | Ingress mapping — require_identity, POST /query and /v1 storage_unavailable with Retry-After | feature | ⬜ todo | medium | — | — |
| STORY-007 | Chat UI — resolve() inside the send's try/finally, sign-in storage notice, fixed storage_unavailable copy | bug | ⬜ todo | small | — | — |
| STORY-008 | Audit journal — append/fsync JSON Lines, exclusive lock, checksum, torn-tail recovery, adoption, bounds | technical | ⬜ todo | medium | — | — |
| STORY-009 | Journal drainer thread and lifespan wiring (FastAPI and Reflex) | technical | ⬜ todo | medium | — | — |
| STORY-010 | AuditRef, journaled release of step 8, PRD-017 D13 decisions path, audit_ref response fields | feature | ⬜ todo | large | — | — |
| STORY-011 | Duplicate overlay over journaled rows and the admission headroom check | technical | ⬜ todo | small | — | — |
| STORY-012 | GET /storage/status, in-memory counters, and the admin console Storage panel | feature | ⬜ todo | medium | — | — |
| STORY-013 | Success-criteria suite — statements 1–14 under fault injection, outage end-to-end, opt-in chaos, latency | technical | ⬜ todo | medium | — | — |
| STORY-014 | Docs, compose volume, .env.example, roadmap, and PRD close-out | technical | ⬜ todo | small | — | — |

## Status Icons
- ⬜ todo
- 🟡 in-progress
- ✅ done
- 🔴 blocked

## Dependencies

- STORY-002 blocked by STORY-001
- STORY-003 blocked by STORY-002
- STORY-004 blocked by STORY-003
- STORY-005 blocked by STORY-003
- STORY-006 blocked by STORY-005
- STORY-007 blocked by STORY-005, STORY-006
- STORY-008 blocked by STORY-004
- STORY-009 blocked by STORY-005, STORY-008
- STORY-010 blocked by STORY-004, STORY-006, STORY-008, STORY-009
- STORY-011 blocked by STORY-006, STORY-008, STORY-009, STORY-010
- STORY-012 blocked by STORY-005, STORY-008, STORY-009
- STORY-013 blocked by STORY-010, STORY-011
- STORY-014 blocked by STORY-012, STORY-013
