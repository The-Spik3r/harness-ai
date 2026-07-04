---
id: STORY-003
prd: PRD-001
slug: request-response-schemas
title: Pydantic request/response schemas
type: technical
priority: high
complexity: small
phase: "1 - Setup"
status: done
labels: [backend, api]
epic_branch: epic/PRD-001-harness-ia
plan: .agents/plans/PRD-001-harness-ia/completed/STORY-003-request-response-schemas.plan.md
report: .agents/reports/PRD-001-harness-ia/STORY-003-request-response-schemas.report.md
commit: 1b71812
depends_on: [STORY-001]
blocks: [STORY-004, STORY-005, STORY-006, STORY-007]
skills: []
created: 2026-07-04
updated: 2026-07-04
---

# STORY-003: Pydantic request/response schemas

## Description

As an integrating developer, I want strongly-typed request/response models matching the PRD's API specification, so that `/query`, `/audit`, and `/stats` validate input and produce consistent, documented output shapes.

## Acceptance Criteria

- [ ] Given the `POST /query` request schema, when a payload is missing `user_id` or `prompt`, then Pydantic validation rejects it with a 422 before any business logic runs.
- [ ] Given the `POST /query` response schemas, when serialized, then they match the three shapes in PRD Section 10 exactly: `SUCCESS` (`status`, `response`, `audit_id`, `model_used`, `tokens_used`), `BLOCKED` duplicate (`status`, `reason`, `first_query_at`), `BLOCKED` suspicious (`status`, `reason`, `pattern`).
- [ ] Given `model` and `openrouter_api_key` are omitted from a request, then the schema applies the documented defaults/optionality (`model` defaults to `"gpt-4"`; `openrouter_api_key` is optional).
- [ ] Given the `/audit` and `/stats` response schemas, when serialized, then they match the shapes in PRD Section 10 field-for-field.

## Technical Notes

- Implement `app/models/schemas.py` per PRD Section 6 directory structure.
- Keep request and response models separate (e.g. `QueryRequest`, `QuerySuccessResponse`, `QueryBlockedResponse`, `AuditResponse`, `StatsResponse`).
- These schemas are consumed by every service/router story that follows — no business logic here, just shape + validation.

## Dependencies

- **Blocked by**: STORY-001
- **Blocks**: STORY-004, STORY-005, STORY-006, STORY-007

## PRD Reference

Source: [`PRD-001/PRD.md`](../../PRDs/PRD-001-harness-ia/PRD.md) — Section 10 (API Specification), Section 6 (Architecture)
