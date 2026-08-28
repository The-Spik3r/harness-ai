---
id: STORY-009
prd: PRD-005
slug: audit-rbac-columns
title: audit_logs gains role and denied_permission columns
type: technical
priority: high
complexity: small
phase: "Phase 3 — Pipeline and ingress wiring"
status: todo
labels: [backend, database]
epic_branch: epic/PRD-005-rbac
plan: null
report: null
commit: null
depends_on: [STORY-001]
blocks: [STORY-010, STORY-015]
skills: []
created: 2026-08-28
updated: 2026-08-28
---

# STORY-009: audit_logs gains role and denied_permission columns

## Description

As a compliance admin, I want the audit schema to carry the acting role and the missing permission, so that a denial is recorded with the same rigor as a served request.

## Acceptance Criteria

- [ ] Given a fresh database, when `init_db()` runs, then `CREATE_AUDIT_LOGS_TABLE` includes `role TEXT` and `denied_permission TEXT`, both nullable so historical rows stay valid
- [ ] Given a pre-RBAC database file, when `init_db()` runs, then both columns are added through `AUDIT_LOGS_ADDED_COLUMNS` and existing rows keep their data with `NULL` in the new fields
- [ ] Given `log_query()` is called with `role` and `denied_permission`, when the row is read back, then both values round-trip through `_row_to_audit_log`
- [ ] Given `log_query()` is called without them, when it runs, then behavior is identical to today and every existing caller and test is unmodified

## Technical Notes

- Both places must change: `CREATE_AUDIT_LOGS_TABLE` (for fresh databases) **and** `AUDIT_LOGS_ADDED_COLUMNS` (for existing ones). Editing only the first is the failure mode PRD Risk 4 describes — `CREATE TABLE IF NOT EXISTS` is a no-op against an existing table.
- `AuditLog` gains two `Optional[str]` fields; `insert_audit_log` and `_row_to_audit_log` updated in lockstep.
- `log_query()` gains two optional keyword arguments with `None` defaults, exactly how PRD-003 added the PII telemetry arguments.
- Tests: `tests/test_db.py`, `tests/test_audit_logger.py`, plus a migration test against a fixture built from the pre-RBAC schema.

## Dependencies

- **Blocked by**: STORY-001
- **Blocks**: STORY-010, STORY-015

## PRD Reference

Source: [`PRD-005/PRD.md`](../../PRDs/PRD-005-rbac/PRD.md) — sections 6 and 14 (Risk 4)
