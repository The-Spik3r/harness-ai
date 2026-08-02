---
id: STORY-009
prd: PRD-003
slug: audit-stats-pii-endpoints
title: "GET /audit and GET /stats: PII telemetry fields"
type: feature
priority: medium
complexity: medium
phase: "3 - Isolation Testing"
status: done
labels: [backend, api, pii, admin]
epic_branch: epic/PRD-003-pii-redaction
plan: .agents/plans/PRD-003-pii-redaction/completed/STORY-009-audit-stats-pii-endpoints.plan.md
report: .agents/reports/PRD-003-pii-redaction/STORY-009-audit-stats-pii-endpoints.report.md
commit: fc4804f
depends_on: [STORY-004]
blocks: [STORY-010]
skills: []
created: 2026-07-24
updated: 2026-08-02
---

# STORY-009: GET /audit and GET /stats — PII telemetry fields

## Description

As a compliance admin, I want `/audit` and `/stats` to expose PII redaction telemetry (whether PII was detected, which entity types, and aggregate counts), so I can monitor redaction activity without those endpoints exposing the masked values as a new leak surface (PRD Section 10, RF-8).

## Acceptance Criteria

- [ ] Given `GET /audit` (admin token required, unchanged auth), when called, then each entry includes `pii_detected_input`, `pii_detected_output`, and `pii_entities` (list of entity type strings) alongside the existing unchanged `prompt_preview` field, matching PRD Section 10's example.
- [ ] Given `GET /stats` (admin token required), when called, then the response includes `pii_detected_queries` (count of audit rows where either input or output PII was detected) and `top_pii_entities` (most frequent entity types across all rows).
- [ ] Given no query has ever triggered PII detection, when `GET /stats` is called, then `pii_detected_queries` is `0` and `top_pii_entities` is `[]` (no errors on empty data).
- [ ] Given the existing `tests/test_audit_router.py` and `tests/test_stats_router.py`, when run, then they still pass, extended with assertions for the new fields.

## Technical Notes

- Extend `AuditQueryEntry` and `StatsResponse` in `app/models/schemas.py` ([schemas.py:39-62](../../../app/models/schemas.py)) with the new fields per PRD Section 10's `GET /audit`/`GET /stats` examples.
- Extend `app/routers/admin.py` ([admin.py](../../../app/routers/admin.py)): `get_audit()` needs to map `log.pii_detected_input`/`log.pii_detected_output`/`log.pii_entities` (parsed back from the comma-joined string per [[STORY-003]]) onto `AuditQueryEntry`; `get_stats()` needs new aggregate queries.
- Add new query helpers to `app/db/database.py` (alongside `count_blocked_duplicates`, `top_models`, etc. — [database.py](../../../app/db/database.py)): `count_pii_detected_queries()` (`WHERE pii_detected_input = 1 OR pii_detected_output = 1`) and `top_pii_entities(limit=5)` (requires splitting the comma-joined `pii_entities` column — either via SQLite string functions or in Python after fetching rows, whichever keeps the query layer simple).
- This story does not touch `/query`'s response shape — that's [[STORY-007]].

## Dependencies

- **Blocked by**: STORY-004
- **Blocks**: STORY-010

## PRD Reference

Source: [`PRD-003/PRD.md`](../../PRDs/PRD-003-pii-redaction/PRD.md) — Section 10 (`GET /audit`, `GET /stats` additions), RF-8
