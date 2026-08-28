---
id: STORY-010
prd: PRD-005
slug: pipeline-identity-authorization
title: run_query() requires an Identity and authorizes as step 0
type: feature
priority: high
complexity: medium
phase: "Phase 3 — Pipeline and ingress wiring"
status: done
labels: [backend, security]
epic_branch: epic/PRD-005-rbac
plan: .agents/plans/PRD-005-rbac/completed/STORY-010-pipeline-identity-authorization.plan.md
report: .agents/reports/PRD-005-rbac/STORY-010-pipeline-identity-authorization.report.md
commit: b222be8
depends_on: [STORY-006, STORY-008, STORY-009]
blocks: [STORY-011, STORY-013, STORY-014]
skills: []
created: 2026-08-28
updated: 2026-08-28
---

# STORY-010: run_query() requires an Identity and authorizes as step 0

## Description

As a security admin, I want `run_query()` to require a verified identity and authorize before anything else, so that both ingresses are covered by one check that cannot be forgotten.

## Acceptance Criteria

- [ ] Given `run_query(...)`, when its signature is defined, then `identity: Identity` is a **required** parameter and the free-standing `user_id: str` input is removed — the audited user id comes from `identity.user_id`
- [ ] Given an identity lacking `query:submit`, when `run_query()` is called, then it returns `QueryBlockedForbiddenResponse` before `check_duplicate()` runs, and `call_openrouter` is never invoked
- [ ] Given that denial, when it happens, then exactly one audit row is written carrying `role` and `denied_permission="query:submit"`, with `success=1`
- [ ] Given an authorized identity, when `run_query()` runs, then steps 1-6 behave exactly as today and every existing pipeline test passes with only the identity argument added
- [ ] Given a caller that omits `identity`, when the call is made, then it fails outright rather than proceeding unauthorized

## Technical Notes

- `app/services/query_pipeline.py`. Authorization is **step 0**, ahead of `check_duplicate()`, so a forbidden request never reaches the dedup lookup, the pattern check, Presidio, or OpenRouter.
- This is the mitigation for PRD Risk 1: the enforcement point is the pipeline, **not** a router `Depends(...)`, because `ChatState.send()` calls `run_query()` in-process and never traverses FastAPI's dependency chain. Making `Identity` a required argument is what turns "remember to authorize" into "cannot call without authorizing".
- The denial follows the shape the existing blocks already use — `log_query(...)` then `return` — so the audit trail treats a refusal like a duplicate or injection block.
- Callers updated in this story or the ones that follow: `app/routers/query.py` (STORY-013) and `chat_ui/chat_ui/state.py` (STORY-014).

## Dependencies

- **Blocked by**: STORY-006, STORY-008, STORY-009
- **Blocks**: STORY-011, STORY-013, STORY-014

## PRD Reference

Source: [`PRD-005/PRD.md`](../../PRDs/PRD-005-rbac/PRD.md) — sections 1, 6, 14 (Risk 1)
