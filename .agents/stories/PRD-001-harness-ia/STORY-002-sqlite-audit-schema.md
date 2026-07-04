---
id: STORY-002
prd: PRD-001
slug: sqlite-audit-schema
title: SQLite connection & audit_logs schema
type: technical
priority: high
complexity: small
phase: "1 - Setup"
status: todo
labels: [backend, db]
epic_branch: epic/PRD-001-harness-ia
plan: null
report: null
commit: null
depends_on: [STORY-001]
blocks: [STORY-004, STORY-006, STORY-010, STORY-011]
skills: []
created: 2026-07-04
updated: 2026-07-04
---

# STORY-002: SQLite connection & audit_logs schema

## Description

As a compliance officer, I want a persistent `audit_logs` table with the exact fields from the PRD's data model, so that every query can be fully audited without ever having a place to store an IP or location field.

## Acceptance Criteria

- [ ] Given `DATABASE_URL` (e.g. `sqlite:///harness_ai.db`), when the app starts, then `db/database.py` creates the SQLite file and `audit_logs` table if they don't already exist.
- [ ] Given the `audit_logs` schema, when inspected, then it has exactly these columns: `id` (PK, autoincrement), `timestamp` (UTC datetime), `user_id`, `device`, `prompt_hash`, `prompt_preview`, `response_hash`, `response_preview`, `model_used`, `tokens_used`, `was_duplicate_blocked`, `suspicious_pattern`, `success`, `error_message` — and no IP/location column of any kind.
- [ ] Given a test DB session, when a row is inserted via the repository function, then it can be read back with all fields intact.
- [ ] Given the app restarts against an existing DB file, then no schema is duplicated or errors thrown (idempotent creation).

## Technical Notes

- Implement `app/db/database.py` (connection/session setup) and `app/db/models.py` (table definition) per PRD Section 7 (Database) and Section 6 (directory structure).
- Use `sqlite3` stdlib or SQLAlchemy Core — keep it a thin repository layer so services never write raw SQL directly (Repository pattern, PRD Section 6).
- Timestamps must be stored in UTC per PRD Section 7.

## Dependencies

- **Blocked by**: STORY-001
- **Blocks**: STORY-004, STORY-006, STORY-010, STORY-011

## PRD Reference

Source: [`PRD-001/PRD.md`](../../PRDs/PRD-001-harness-ia/PRD.md) — Section 7 (implied via Section 9 config), Section 6 (Architecture), Section 12 (Phase 1)
