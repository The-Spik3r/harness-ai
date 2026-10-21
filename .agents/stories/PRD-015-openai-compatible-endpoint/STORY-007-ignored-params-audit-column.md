---
id: STORY-007
prd: PRD-015
slug: ignored-params-audit-column
title: "audit_logs.ignored_params: column, writer, every pipeline arm and the /audit field"
type: feature
priority: high
complexity: medium
phase: "1 - Foundations"
status: todo
labels: [backend, audit, pipeline, db]
epic_branch: epic/PRD-015-openai-compatible-endpoint
plan: null
report: null
commit: null
depends_on: []
blocks: [STORY-009]
skills: []
created: 2026-10-21
updated: 2026-10-21
---

# STORY-007: audit_logs.ignored_params: column, writer, every pipeline arm and the /audit field

## Description

As a compliance admin, I want every `/v1` row to name the client parameters the harness did not forward, so that "what did the client ask for that it did not get" is answerable from the audit alone.

## Acceptance Criteria

- [ ] Given an existing database without the column, when `init_db()` runs, then `audit_logs.ignored_params` exists as nullable TEXT, existing rows read NULL, and a second `init_db()` is a no-op.
- [ ] Given `run_conversation(..., ignored_params="seed,user")`, when each arm writes its row (the three authorization denials, break-glass, usage limit, context limit, duplicate, pattern block, flag, redaction limit, redaction error, upstream error, output-redaction error, success), then every row carries `"seed,user"`; given the keyword omitted, then every row carries NULL.
- [ ] Given `_deny` called without `ignored_params`, when it runs, then it raises `TypeError` (required, as `session_id`, `dedup_key`, `profile` and `ingress` are).
- [ ] Given `GET /audit`, when a row has the column set, then `AuditQueryEntry.ignored_params` returns it; rows written by `/query` and the chat UI return `null`, and every existing `/audit` and `/stats` assertion is unchanged.
- [ ] Given the production sources, when the call-site scans run (`tests/test_query_pipeline_audit_fields.py`, `tests/test_query_pipeline_pii_profiles.py`), then every direct `log_query` call inside `run_conversation` passes `ignored_params`.

## Technical Notes

- Column through `app/db/models.py` and `_add_missing_columns` in `app/db/database.py`, as PRD-013 STORY-002 did; never backfilled.
- `log_query(..., ignored_params: Optional[str] = None)`, defaulted with the comment style used for `profile` ("defaulted here but never omitted in the pipeline").
- `run_conversation(..., *, ignored_params: Optional[str] = None)`, keyword-only beside `ingress` and `streamed`; `run_query` passes nothing. Thread it to all fourteen `log_query` / `_deny` sites; follow PRD-013 STORY-005's diff shape.
- `/query`'s foreign-session refusal (`app/routers/query.py`) keeps writing NULL by default; no change there.
- `AuditQueryEntry.ignored_params: Optional[str] = None`, unvalidated, for `session_id`'s reasons (comment in that style). Update the reports/read shape in `app/services/reports.py` only if it projects every column explicitly.
- The admin console is out of scope (PRD Section 4).
- Tests: extend the audit-fields scan; add per-arm assertions to `tests/test_query_pipeline_audit_fields.py`; `db` marker applies.
- Skills: none applicable. No UI change.

## Dependencies

- **Blocked by**: None
- **Blocks**: STORY-009

## PRD Reference

Source: [`PRD-015-openai-compatible-endpoint/PRD.md`](../../PRDs/PRD-015-openai-compatible-endpoint/PRD.md) — sections 4 (Audit), 6.3, 7.3, 10 (`/audit` change), 15 (D1, D3)
