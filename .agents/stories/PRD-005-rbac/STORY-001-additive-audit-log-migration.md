---
id: STORY-001
prd: PRD-005
slug: additive-audit-log-migration
title: Additive schema-migration mechanism for audit_logs
type: technical
priority: high
complexity: small
phase: "Phase 1 — Identity foundation"
status: in-progress
labels: [backend, database]
epic_branch: epic/PRD-005-rbac
plan: .agents/plans/PRD-005-rbac/STORY-001-additive-audit-log-migration.plan.md
report: null
commit: null
depends_on: []
blocks: [STORY-002, STORY-009]
skills: []
created: 2026-08-28
updated: 2026-08-28
---

# STORY-001: Additive schema-migration mechanism for audit_logs

## Description

As a maintainer, I want `init_db()` to add missing columns to an existing `audit_logs` table, so that schema changes reach deployments that already have a database file instead of breaking every insert.

## Acceptance Criteria

- [ ] Given a database whose `audit_logs` table predates a column listed in `AUDIT_LOGS_ADDED_COLUMNS`, when `init_db()` runs, then the column is added via `ALTER TABLE ... ADD COLUMN` and existing rows take its default
- [ ] Given a database already at the current schema, when `init_db()` runs, then no `ALTER` is issued and the call is a no-op
- [ ] Given an entry declaring `NOT NULL`, when it is applied, then it also declares a non-NULL `DEFAULT`, because SQLite rejects `ADD COLUMN NOT NULL` without one
- [ ] Given `init_db()` is called repeatedly, when it runs, then it stays idempotent — Reflex calls it on every hot reload
- [ ] Given the mapping ships empty, when the suite runs, then a fixture database built from the pre-migration schema proves a synthetic column is added and existing rows survive

## Technical Notes

- `app/db/models.py`: add `AUDIT_LOGS_ADDED_COLUMNS: dict[str, str]` mapping column name → DDL fragment. It starts empty; STORY-009 populates it.
- `app/db/database.py`: `_add_missing_columns(conn)` reads `PRAGMA table_info(audit_logs)` and applies only what is missing; called from `init_db()` after `CREATE TABLE IF NOT EXISTS`.
- `chat_ui/chat_ui/chat_ui.py` calls `init_db()` eagerly on every reload because Reflex's `api_transformer` bypasses `app.main`'s lifespan — the function must stay cheap and idempotent.
- Additive only: no drops, renames, or type changes. This mechanism is built **before** any column is added (PRD Risk 4) — `CREATE TABLE IF NOT EXISTS` is a no-op on an existing table, so without it new columns would never appear and every insert would fail.
- Tests: `tests/test_db.py`.

## Dependencies

- **Blocked by**: None
- **Blocks**: STORY-002, STORY-009

## PRD Reference

Source: [`PRD-005/PRD.md`](../../PRDs/PRD-005-rbac/PRD.md) — sections 6 and 14 (Risk 4)
