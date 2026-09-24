# PRD-012-pii-for-code: PII Redaction for Code — Policy by Profile, Role and Direction, Within a Latency Budget — Story Board

**PRD**: [PRD.md](./PRD.md)
**Epic Branch**: `epic/PRD-012-pii-for-code` (base: `main`)
**Status**: active

## Progress

3/14 stories done — 21%

## Stories

All stories commit on the epic branch `epic/PRD-012-pii-for-code`. No per-story branches.

| ID | Title | Type | Status | Complexity | Plan | Commit |
|----|-------|------|--------|------------|------|--------|
| STORY-001 | PII corpora: code, prose and JSON samples as checked-in files | technical | ✅ done | medium | [plan](../../plans/PRD-012-pii-for-code/completed/STORY-001-pii-corpora.plan.md) | `beeb0b9` |
| STORY-002 | Characterize today's redact() and pipeline steps 6 and 8 before anything moves | technical | ✅ done | small | [plan](../../plans/PRD-012-pii-for-code/completed/STORY-002-pii-characterization.plan.md) | `5e93b18` |
| STORY-003 | Benchmark harness, baseline numbers, pinned versions and tokenizer-only analyzer feasibility | spike | ✅ done | large | [plan](../../plans/PRD-012-pii-for-code/completed/STORY-003-pii-benchmark-baseline.plan.md) | `ddf6596` |
| STORY-004 | Extract strip_fenced_blocks; rebuild strip_code_spans on it | technical | 🟡 in-progress | small | [plan](../../plans/PRD-012-pii-for-code/STORY-004-strip-fenced-blocks.plan.md) | — |
| STORY-005 | Six PII code-profile settings with startup validators | technical | ⬜ todo | small | — | — |
| STORY-006 | Pattern-only analyzer, selected by the entity list | feature | ⬜ todo | medium | — | — |
| STORY-007 | pii_policy: built-in chat and code policies, profile fallback, load() in both lifespans | feature | ⬜ todo | medium | — | — |
| STORY-008 | redact_for_policy: fence skipping, structure-safe replacement, JSON-aware mode | feature | ⬜ todo | large | — | — |
| STORY-009 | Pipeline steps 6 and 8 redact per the resolved policy | feature | ⬜ todo | medium | — | — |
| STORY-010 | Size limit and the redaction_characters refusal arm | feature | ⬜ todo | medium | — | — |
| STORY-011 | audit_logs.profile on every arm; /audit and the Register show it | feature | ⬜ todo | medium | — | — |
| STORY-012 | Placeholder spike and decisions/D5-placeholders.md | spike | ⬜ todo | medium | — | — |
| STORY-013 | Code round-trip suite and the latency-budget assertion | technical | ⬜ todo | medium | — | — |
| STORY-014 | chat regression sweep, README and .env docs, pre-PRD promoted | technical | ⬜ todo | medium | — | — |

## Status Icons
- ⬜ todo
- 🟡 in-progress
- ✅ done
- 🔴 blocked

## Dependencies

- STORY-003 blocked by STORY-001
- STORY-005 blocked by STORY-003
- STORY-006 blocked by STORY-003, STORY-005
- STORY-007 blocked by STORY-005
- STORY-008 blocked by STORY-001, STORY-004, STORY-006, STORY-007
- STORY-009 blocked by STORY-002, STORY-007, STORY-008
- STORY-010 blocked by STORY-009
- STORY-011 blocked by STORY-010
- STORY-012 blocked by STORY-009
- STORY-013 blocked by STORY-001, STORY-003, STORY-008, STORY-009
- STORY-014 blocked by STORY-002, STORY-011, STORY-012, STORY-013
