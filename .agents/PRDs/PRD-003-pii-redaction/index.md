# PRD-003: PII Redaction (Presidio) — Input & Output Masking — Story Board

**PRD**: [PRD.md](./PRD.md)
**Epic Branch**: `epic/PRD-003-pii-redaction` (base: `main`)
**Status**: active

## Progress

10/12 stories done — 83%

## Stories

All stories commit on the epic branch `epic/PRD-003-pii-redaction`. No per-story branches.

| ID | Title | Type | Status | Complexity | Plan | Commit |
|----|-------|------|--------|------------|------|--------|
| STORY-001 | Presidio PII redactor service | feature | ✅ done | medium | [plan](../../plans/PRD-003-pii-redaction/completed/STORY-001-pii-redactor-service.plan.md) | `0495068` |
| STORY-002 | Load Presidio NLP model once at FastAPI startup | technical | ✅ done | small | [plan](../../plans/PRD-003-pii-redaction/completed/STORY-002-startup-nlp-model-loading.plan.md) | `358ddc6` |
| STORY-003 | audit_logs schema: PII telemetry columns | technical | ✅ done | small | [plan](../../plans/PRD-003-pii-redaction/completed/STORY-003-audit-log-pii-schema.plan.md) | `c8b1195` |
| STORY-004 | Audit logger records PII telemetry (raw preview unchanged) | feature | ✅ done | small | [plan](../../plans/PRD-003-pii-redaction/completed/STORY-004-audit-logger-pii-telemetry.plan.md) | `1347e53` |
| STORY-005 | Redact prompt before forwarding to OpenRouter | feature | ✅ done | medium | [plan](../../plans/PRD-003-pii-redaction/completed/STORY-005-pipeline-input-redaction.plan.md) | `c69a656` |
| STORY-006 | Redact model response before returning to caller | feature | ✅ done | medium | [plan](../../plans/PRD-003-pii-redaction/completed/STORY-006-pipeline-output-redaction.plan.md) | `87c7ea8` |
| STORY-007 | POST /query response: pii_redacted signal field | feature | ✅ done | small | [plan](../../plans/PRD-003-pii-redaction/completed/STORY-007-query-response-pii-signal.plan.md) | `61e402c` |
| STORY-008 | Tests: redaction cannot affect dedup/pattern-check behavior | technical | ✅ done | medium | [plan](../../plans/PRD-003-pii-redaction/completed/STORY-008-dedup-pattern-isolation-tests.plan.md) | `58ee0a6` |
| STORY-009 | GET /audit and GET /stats: PII telemetry fields | feature | ✅ done | medium | [plan](../../plans/PRD-003-pii-redaction/completed/STORY-009-audit-stats-pii-endpoints.plan.md) | `fc4804f` |
| STORY-010 | End-to-end PII redaction integration test suite | technical | ✅ done | medium | [plan](../../plans/PRD-003-pii-redaction/completed/STORY-010-pii-pipeline-integration-tests.plan.md) | `306b5cc` |
| STORY-011 | Docker image: install spaCy PII model | technical | ⬜ todo | small | — | — |
| STORY-012 | README, .env.example, and roadmap updates for PII redaction | technical | ⬜ todo | small | — | — |

## Status Icons
- ⬜ todo
- 🟡 in-progress
- ✅ done
- 🔴 blocked

## Dependencies

- STORY-002 blocked by STORY-001
- STORY-004 blocked by STORY-003
- STORY-005 blocked by STORY-001, STORY-002
- STORY-006 blocked by STORY-005, STORY-004
- STORY-007 blocked by STORY-006
- STORY-008 blocked by STORY-006
- STORY-009 blocked by STORY-004
- STORY-010 blocked by STORY-007, STORY-008, STORY-009
- STORY-011 blocked by STORY-002
- STORY-012 blocked by STORY-010, STORY-011
