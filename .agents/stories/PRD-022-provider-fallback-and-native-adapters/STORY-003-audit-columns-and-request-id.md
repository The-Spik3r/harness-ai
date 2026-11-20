---
id: STORY-003
prd: PRD-022
slug: audit-columns-and-request-id
title: PRD-022 audit columns, request_id on every row, attempt=1 on step-7 rows, /audit filter
type: feature
priority: high
complexity: medium
phase: "1 - Foundations"
status: todo
labels: [backend, audit, db]
epic_branch: epic/PRD-022-provider-fallback-and-native-adapters
plan: null
report: null
commit: null
depends_on: [STORY-001]
blocks: [STORY-008, STORY-012]
skills: []
created: 2026-11-20
updated: 2026-11-20
---

# STORY-003: PRD-022 audit columns, request_id on every row, /audit filter

## Description

As a compliance admin, I want every row to carry a per-request `request_id` and every upstream-attempt row to carry its attempt number and the catalogue id that handled it, so that one query reads as one story even when several attempts were made.

## Acceptance Criteria

- [ ] Given an existing database, when the app starts, then `audit_logs` gains `request_id TEXT`, `attempt INTEGER`, `route_model TEXT`, `fallback_reason TEXT`, `skipped_providers TEXT`, `cache_read_tokens INTEGER`, `cache_write_tokens INTEGER` through `AUDIT_LOGS_ADDED_COLUMNS` (idempotent; a fresh DB gets them from `CREATE TABLE`), and the buffered audit writer (PRD-018) persists them
- [ ] Given one `run_conversation` call, when it writes any row (verdict, block, refusal, failure or success), then every row carries the same uuid4 `request_id`; two calls never share one
- [ ] Given a request with no chain (today's single call), when step 7 writes its failure or success row, then `attempt=1` and `route_model=<the requested catalogue id>`; rows written before step 7 have `attempt` and `route_model` NULL; `fallback_reason`, `skipped_providers` are NULL; `cache_*_tokens` come from the result when present, else NULL
- [ ] Given `GET /audit`, when called, then rows include the seven new fields, and `?request_id=<id>` returns only that request's rows (role checks unchanged)
- [ ] Given the existing suite, when run with no chain file, then captured responses are unchanged and rows differ only by the new columns (guard tests such as column censuses updated with a comment citing PRD-022 D10)

## Technical Notes

- `app/db/models.py:71` `AUDIT_LOGS_ADDED_COLUMNS`, `:38` table DDL, `:548` audit entry dataclass; `app/db/database.py:1489` migration, `:1582`/`:1676` insert paths (PRD-018 buffered writes), `:1831` row mapping; `app/services/audit_logger.py` `log_query`; `app/models/schemas.py:293` audit row schema; `app/routers/admin.py` `/audit`.
- `request_id` is minted at the top of `run_conversation` (`query_pipeline.py:439`) and threaded into every `log_query` call, including `_deny` (`:363-430`): make it a **required keyword** on the internal row helper so a forgotten argument is a `TypeError`, not a NULL (PRD 6.9).
- `log_query` callers outside the pipeline (chat UI, scripts) keep working: the new parameters default to None at the public `log_query` boundary.
- Do not implement the chain here; `attempt` is always 1 on step-7 rows.

## Dependencies

- **Blocked by**: STORY-001
- **Blocks**: STORY-008, STORY-012

## PRD Reference

Source: [`PRD-022/PRD.md`](../../PRDs/PRD-022-provider-fallback-and-native-adapters/PRD.md) — Sections 6.7, F8, D10, Phase 1
