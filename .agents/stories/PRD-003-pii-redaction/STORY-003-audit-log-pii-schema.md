---
id: STORY-003
prd: PRD-003
slug: audit-log-pii-schema
title: "audit_logs schema: PII telemetry columns"
type: technical
priority: high
complexity: small
phase: "2 - Pipeline Wiring"
status: done
labels: [backend, db, pii]
epic_branch: epic/PRD-003-pii-redaction
plan: .agents/plans/PRD-003-pii-redaction/completed/STORY-003-audit-log-pii-schema.plan.md
report: .agents/reports/PRD-003-pii-redaction/STORY-003-audit-log-pii-schema.report.md
commit: c8b1195
depends_on: []
blocks: [STORY-004, STORY-009]
skills: []
created: 2026-07-24
updated: 2026-07-31
---

# STORY-003: audit_logs schema — PII telemetry columns

## Description

As a compliance admin, I want the `audit_logs` table to record whether PII was detected on input/output and which entity types, so `/stats` and `/audit` can report redaction activity without exposing the masked values themselves (PRD Section 4, RF-8).

## Acceptance Criteria

- [ ] Given the `audit_logs` table is created, when inspected, then it has three new nullable/defaulted columns: `pii_detected_input` (boolean, default 0), `pii_detected_output` (boolean, default 0), `pii_entities` (text, stores a serialized list of entity type strings, nullable).
- [ ] Given the `AuditLog` dataclass, when constructed, then it accepts `pii_detected_input: bool = False`, `pii_detected_output: bool = False`, `pii_entities: Optional[str] = None` fields matching the new columns.
- [ ] Given `insert_audit_log()` is called with the new fields populated, when read back via `get_audit_log()`/`list_audit_logs()`, then the values round-trip correctly.
- [ ] Given existing PRD-001 tests that construct `AuditLog`/call `insert_audit_log()` without the new fields, when run, then they still pass unmodified (new fields must have safe defaults).

## Technical Notes

- Extend `CREATE_AUDIT_LOGS_TABLE` and the `AuditLog` dataclass in `app/db/models.py` ([db/models.py](../../../app/db/models.py)) — append the three new columns/fields with defaults so no existing call site breaks.
- Update `app/db/database.py`'s `insert_audit_log()` INSERT statement and `_row_to_audit_log()` to include the new columns (this file has no migration framework — the table is created fresh via `CREATE TABLE IF NOT EXISTS`, consistent with PRD-001's approach).
- Store `pii_entities` as a comma-joined string (mirrors how `PII_ENTITIES` env var is parsed in [[STORY-001]]) rather than adding a JSON column type, to stay consistent with this schema's existing all-TEXT/INTEGER simplicity.
- This story only touches `app/db/models.py` and `app/db/database.py` — do not touch `duplicate_checker.py` or its hash logic (PRD Section 9, RF-6).

## Dependencies

- **Blocked by**: None
- **Blocks**: STORY-004, STORY-009

## PRD Reference

Source: [`PRD-003/PRD.md`](../../PRDs/PRD-003-pii-redaction/PRD.md) — Section 4 (In Scope), Section 6 (Changes to existing modules — `app/db/models.py`), Section 10 (`GET /audit` additions)
