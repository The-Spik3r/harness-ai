---
id: STORY-010
prd: PRD-001
slug: get-audit-endpoint
title: "GET /audit endpoint"
type: feature
priority: medium
complexity: medium
phase: "4 - Admin Endpoints & Testing"
status: done
labels: [backend, api]
epic_branch: epic/PRD-001-harness-ia
plan: .agents/plans/PRD-001-harness-ia/completed/STORY-010-get-audit-endpoint.plan.md
report: .agents/reports/PRD-001-harness-ia/STORY-010-get-audit-endpoint.report.md
commit: abcfda3
depends_on: [STORY-002, STORY-009]
blocks: [STORY-012]
skills: []
created: 2026-07-04
updated: 2026-07-04
---

# STORY-010: GET /audit endpoint

## Description

As a compliance officer, I want to see the last 100 logged queries via an admin-only endpoint, so that I can review activity without direct DB access (Section 6.2 of the source spec).

## Acceptance Criteria

- [ ] Given a valid admin token, when `GET /audit` is called, then it returns the total count and the last 100 entries matching PRD Section 10's shape exactly (`audit_id`, `user_id`, `timestamp`, `model`, `prompt_hash`, `was_duplicate_blocked`, `suspicious_pattern_detected`, `device`).
- [ ] Given fewer than 100 rows exist, when `GET /audit` is called, then it returns all existing rows without error.
- [ ] Given an invalid/missing admin token, when `GET /audit` is called, then it is rejected (via STORY-009's middleware) before touching the DB.
- [ ] Given the response payload, when inspected, then it never includes an IP field, a full (non-hashed) prompt, or a full (non-hashed) response.

## Technical Notes

- Implement in `app/routers/admin.py` per PRD Section 6, reading via the repository layer from STORY-002.
- Order by `timestamp DESC LIMIT 100`.

## Dependencies

- **Blocked by**: STORY-002, STORY-009
- **Blocks**: STORY-012

## PRD Reference

Source: [`PRD-001/PRD.md`](../../PRDs/PRD-001-harness-ia/PRD.md) — Section 5 (User Story 4), Section 10 (GET /audit), Section 12 (Phase 4)
