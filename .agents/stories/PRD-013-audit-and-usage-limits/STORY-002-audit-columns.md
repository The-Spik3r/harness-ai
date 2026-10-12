---
id: STORY-002
prd: PRD-013
slug: audit-columns
title: "Eight additive audit columns: convergence, AuditLog, writer and both read shapes"
type: technical
priority: high
complexity: medium
phase: "1 - The row"
status: in-progress
labels: [backend, database, audit]
epic_branch: epic/PRD-013-audit-and-usage-limits
plan: .agents/plans/PRD-013-audit-and-usage-limits/STORY-002-audit-columns.plan.md
report: null
commit: null
depends_on: [STORY-001]
blocks: [STORY-005, STORY-011]
skills: []
created: 2026-10-04
updated: 2026-10-12
---

# STORY-002: Eight additive audit columns: convergence, AuditLog, writer and both read shapes

## Description

As a compliance admin, I want the audit table able to hold the ingress, size, cost and grouping of a request, so that later stories have somewhere to record them and existing databases converge without a migration step.

## Acceptance Criteria

- [ ] Given `app/db/models.py`, when it is read, then `ingress TEXT`, `message_count INTEGER`, `input_tokens INTEGER`, `output_tokens INTEGER`, `streamed INTEGER NOT NULL DEFAULT 0`, `has_tool_calls INTEGER NOT NULL DEFAULT 0`, `conversation_key TEXT` and `limit_exceeded TEXT` are each declared in both `CREATE_AUDIT_LOGS_TABLE` and `AUDIT_LOGS_ADDED_COLUMNS`.
- [ ] Given a database created before this story with existing rows, when `init_db()` runs, then all eight columns exist, existing rows read `NULL` for the six nullable ones and `0` for `streamed` and `has_tool_calls`, and no row is updated.
- [ ] Given a database already at the current schema, when `init_db()` runs, then no `ALTER` is issued (`test_init_db_issues_no_alter_when_schema_is_current` still passes).
- [ ] Given an `AuditLog` with all eight fields set, when it is written by `insert_audit_log` and read back by `get_audit_log` and by `summary_snapshot().rows`, then both return the same eight values, with the two flags as `bool`.
- [ ] Given the full suite, when it runs, then STORY-001's characterization and every existing test pass with no assertion changed.

## Technical Notes

- `init_db()` needs no new code: the columns ride the existing `_add_missing_columns(conn, "audit_logs", AUDIT_LOGS_ADDED_COLUMNS)` call. Do not add an index.
- `AuditLog` fields go after `profile`, mirroring the table, so `id` stays the trailing field. Defaults: `None` for the six, `False` for the two flags.
- `_SUMMARY_SQL`'s `json_object(...)` must list the eight new keys, or `_row_to_audit_log` raises `KeyError` on the batched path only. The `bool(...)` coercion matters there: `json_object` returns 0/1.
- `tests/test_db.py::test_added_columns_declaring_not_null_also_declare_a_default` covers the two `NOT NULL` entries.
- Nothing sets a non-default value yet. `log_query` is untouched until STORY-005.
- Add a comment block per column in `AUDIT_LOGS_ADDED_COLUMNS`, in the style of the `profile` entry, stating why it is nullable or defaulted (PRD Section 6.2).
- Skills: none applicable. No UI surface changes in this story.

## Dependencies

- **Blocked by**: STORY-001
- **Blocks**: STORY-005, STORY-011

## PRD Reference

Source: [`PRD-013-audit-and-usage-limits/PRD.md`](../../PRDs/PRD-013-audit-and-usage-limits/PRD.md) — sections 4 (Audit columns), 6.2, 7 (F2), 11 (Audit)
