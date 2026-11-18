---
id: STORY-006
prd: PRD-020
slug: audit-provider-columns
title: Five provider columns on the audit table and log_query
type: feature
priority: medium
complexity: medium
phase: "2 - Adapter and routing"
status: done
labels: [backend, database]
epic_branch: epic/PRD-020-provider-registry
plan: .agents/plans/PRD-020-provider-registry/completed/STORY-006-audit-provider-columns.plan.md
report: .agents/reports/PRD-020-provider-registry/STORY-006-audit-provider-columns.report.md
commit: null
depends_on: []
blocks: [STORY-007]
skills: []
created: 2026-11-18
updated: 2026-11-18
---

# STORY-006: Five provider columns on the audit table and log_query

## Description

As an auditor, I want every audit row to carry the provider, upstream model, trust, relaxation and estimation flags as recorded at call time, so that "where did this prompt go" is answerable after the registry changes.

## Acceptance Criteria

- [ ] Given a fresh database, when `init_db()` runs, then `audit_logs` has `provider TEXT`, `upstream_model TEXT`, `provider_trust TEXT`, `pii_input_relaxed INTEGER NOT NULL DEFAULT 0` and `usage_estimated INTEGER NOT NULL DEFAULT 0`, and an old database converges through `AUDIT_LOGS_ADDED_COLUMNS` with existing rows NULL / 0 and no backfill.
- [ ] Given `log_query(..., provider="ollama", upstream_model="qwen2.5-coder:7b", provider_trust="internal", pii_input_relaxed=True, usage_estimated=True)`, when the row is read back through `list_audit_logs`, then `AuditLog` carries the five values (flags as bools), and omitting the arguments yields NULL / NULL / NULL / False / False.
- [ ] Given the summary query, when `_SUMMARY_SQL` runs, then its `json_object` contains the five keys and `_row_to_audit_log` reads them without a `KeyError`.
- [ ] Given `GET /audit` as admin, when rows exist, then each `AuditQueryEntry` gains `provider`, `upstream_model`, `provider_trust`, `pii_input_relaxed` and `usage_estimated` as verbatim passthroughs, and the existing audit-router assertions pass unchanged.
- [ ] Given the DB resilience census (`tests/test_db_resilience_retry.py`), when any new `database.py` function or caller is added, then the census tables are updated with a PRD-020 comment; adding only parameters to `insert_audit_log` and `log_query` leaves the counts unchanged.

## Technical Notes

- Declare each column twice, as the PRD-013/015 path requires: `CREATE_AUDIT_LOGS_TABLE` (`app/db/models.py:4`, `has_tool_calls` at `:35`) and `AUDIT_LOGS_ADDED_COLUMNS` (`:62`, `has_tool_calls` at `:116`). `tests/test_db.py::test_added_columns_declaring_not_null_also_declare_a_default` enforces the default on NOT NULL.
- `AuditLog` dataclass (`app/db/models.py:454`, `has_tool_calls` at `:506`); INSERT column list and placeholders at `app/db/database.py:1575-1585` and the bound tuple `:1660-1672`; `_row_to_audit_log` `:1772-1820` (a missing json key is a `KeyError`); `_SUMMARY_SQL` `:2220`, its `json_object` keys through `'write_id'` at `:2262-2269`; migration `_add_missing_columns` call at `:1489`.
- `log_query` at `app/services/audit_logger.py:45` and its `AuditLog(...)` construction (`has_tool_calls` at `:143`); API entry `AuditQueryEntry` at `app/models/schemas.py:192` and its projection in `app/routers/admin.py:38-100` (passthrough comments there show the house style).
- Census guard: `tests/test_db_resilience_retry.py:696-741` (`_EXPECTED_KINDS` count asserted at `:733`, AST check that each public function calls `_unit_of_work` once). Adding parameters does not change it; adding a function does.
- The admin Register `provider` display is STORY-012; this story only provides the data. Pipeline writers are STORY-007.

## Dependencies

- **Blocked by**: None
- **Blocks**: STORY-007

## PRD Reference

Source: [`PRD-020/PRD.md`](../../PRDs/PRD-020-provider-registry/PRD.md) — Sections 4 (Audit), 7 F5, 10 (Audit read API); decisions D13; threat T8
