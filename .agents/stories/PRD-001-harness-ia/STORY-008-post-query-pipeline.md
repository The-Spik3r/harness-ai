---
id: STORY-008
prd: PRD-001
slug: post-query-pipeline
title: "POST /query endpoint: full interception pipeline"
type: feature
priority: high
complexity: medium
phase: "3 - OpenRouter Integration"
status: done
labels: [backend, api, security]
epic_branch: epic/PRD-001-harness-ia
plan: .agents/plans/PRD-001-harness-ia/completed/STORY-008-post-query-pipeline.plan.md
report: .agents/reports/PRD-001-harness-ia/STORY-008-post-query-pipeline.report.md
commit: 8da10c0
depends_on: [STORY-004, STORY-005, STORY-006, STORY-007]
blocks: [STORY-012, STORY-013]
skills: []
created: 2026-07-04
updated: 2026-07-04
---

# STORY-008: POST /query endpoint — full interception pipeline

## Description

As an integrating developer, I want a single `POST /query` endpoint that runs the full 8-step harness pipeline, so that every prompt is verified, checked for duplicates/injection, forwarded to OpenRouter, and logged before a response reaches the user (RF-1, RF-2, RF-12, RF-14).

## Acceptance Criteria

- [ ] Given a request missing `user_id`, when posted to `/query`, then it is rejected before any hashing/forwarding occurs (RF-14).
- [ ] Given a novel, clean prompt, when posted to `/query`, then the pipeline runs in order — hash → duplicate check → pattern check → OpenRouter call → log → respond — and returns the `SUCCESS` shape from PRD Section 10, matching the happy-path flow in PRD Section 5.1.
- [ ] Given a prompt identical to one submitted within the last 24h, when posted to `/query`, then OpenRouter is never called and the `BLOCKED` duplicate shape is returned (PRD Section 5.2).
- [ ] Given a prompt containing a suspicious pattern, when posted to `/query`, then OpenRouter is never called and the `BLOCKED` suspicious-pattern shape is returned (PRD Section 5.3).
- [ ] Given any outcome (success or blocked), when the request completes, then exactly one audit row is written via the audit logging service.
- [ ] Given the full pipeline runs end-to-end, when measured, then total added latency (excluding the upstream model call itself) stays within the <500ms NFR budget.

## Technical Notes

- Implement `app/routers/query.py` per PRD Section 6, composing the services from STORY-004/005/006/007 in the exact order from Section 6's "Request pipeline."
- This is the integration point — keep the route handler thin, delegating to services (no business logic inline).
- Order matters: duplicate check and pattern check must both happen *before* the OpenRouter call, per PRD Section 5.2/5.3.

## Dependencies

- **Blocked by**: STORY-004, STORY-005, STORY-006, STORY-007
- **Blocks**: STORY-012, STORY-013

## PRD Reference

Source: [`PRD-001/PRD.md`](../../PRDs/PRD-001-harness-ia/PRD.md) — Section 5 (Flujos Principales), Section 6 (Request pipeline), Section 10 (POST /query), Section 12 (Phase 3)
