---
id: STORY-008
prd: PRD-005
slug: forbidden-response-schema
title: QueryBlockedForbiddenResponse joins the QueryResponse union
type: technical
priority: high
complexity: small
phase: "Phase 3 — Pipeline and ingress wiring"
status: done
labels: [backend, api]
epic_branch: epic/PRD-005-rbac
plan: .agents/plans/PRD-005-rbac/completed/STORY-008-forbidden-response-schema.plan.md
report: .agents/reports/PRD-005-rbac/STORY-008-forbidden-response-schema.report.md
commit: 6e9e773
depends_on: []
blocks: [STORY-010, STORY-014]
skills: []
created: 2026-08-28
updated: 2026-08-28
---

# STORY-008: QueryBlockedForbiddenResponse joins the QueryResponse union

## Description

As an integrating developer, I want a distinct response type for a policy-refused query, so that a forbidden outcome is a first-class member of the contract instead of being folded into an existing block reason.

## Acceptance Criteria

- [ ] Given `QueryBlockedForbiddenResponse`, when defined, then it carries `status: Literal["BLOCKED"]`, `reason: str`, and `required_permission: str`
- [ ] Given the `QueryResponse` union, when the fourth member is added, then FastAPI's `response_model` still discriminates all four members correctly
- [ ] Given the existing three response models, when this ships, then their shapes are byte-for-byte unchanged and `tests/test_schemas.py` passes unmodified for them
- [ ] Given the new model, when serialized, then `status == "BLOCKED"`, so clients that branch only on `status` keep working

## Technical Notes

- `app/models/schemas.py` only.
- Adding a fourth member makes every `isinstance` chain over the union incomplete. `ChatState.send()` currently ends in a catch-all `else` that treats anything not success-or-duplicate as the suspicious-pattern case — STORY-014 replaces it with an explicit branch (PRD Risk 5). Ship these two close together.
- Keeping `status: "BLOCKED"` rather than inventing a new status value is deliberate: the refusal is in-band by design (PRD Section 9), so the chat UI renders it as a bubble like any other block.

## Dependencies

- **Blocked by**: None
- **Blocks**: STORY-010, STORY-014

## PRD Reference

Source: [`PRD-005/PRD.md`](../../PRDs/PRD-005-rbac/PRD.md) — sections 9, 10, 14 (Risk 5)
