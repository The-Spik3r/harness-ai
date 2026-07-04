---
id: STORY-011
prd: PRD-001
slug: get-stats-endpoint
title: "GET /stats endpoint"
type: feature
priority: medium
complexity: medium
phase: "4 - Admin Endpoints & Testing"
status: todo
labels: [backend, api]
epic_branch: epic/PRD-001-harness-ia
plan: null
report: null
commit: null
depends_on: [STORY-002, STORY-009]
blocks: [STORY-012]
skills: []
created: 2026-07-04
updated: 2026-07-04
---

# STORY-011: GET /stats endpoint

## Description

As a security admin, I want an aggregate stats view, so that I can monitor system health and spot abuse trends without reading raw logs.

## Acceptance Criteria

- [ ] Given any amount of history in `audit_logs`, when `GET /stats` is called with a valid admin token, then it returns `total_queries`, `blocked_duplicates`, `blocked_suspicious`, `unique_users`, `success_rate`, `top_models`, `top_users` matching PRD Section 10's shape.
- [ ] Given `success_rate`, when computed, then it is `(successful queries / total queries) * 100`, formatted as a percentage string (e.g. `"98.4%"`).
- [ ] Given `top_models`/`top_users`, when computed, then they are ranked by query count, descending.
- [ ] Given an invalid/missing admin token, when `GET /stats` is called, then it is rejected before any aggregation query runs.
- [ ] Given zero rows exist in `audit_logs`, when `GET /stats` is called, then it returns zeroed/empty values without dividing by zero or erroring.

## Technical Notes

- Implement in `app/routers/admin.py` alongside STORY-010, reading via the repository layer from STORY-002.
- Aggregate via SQL (`COUNT`, `GROUP BY`) rather than pulling all rows into Python where practical.

## Dependencies

- **Blocked by**: STORY-002, STORY-009
- **Blocks**: STORY-012

## PRD Reference

Source: [`PRD-001/PRD.md`](../../PRDs/PRD-001-harness-ia/PRD.md) — Section 5 (User Story 5), Section 10 (GET /stats), Section 12 (Phase 4)
