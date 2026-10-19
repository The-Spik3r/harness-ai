---
id: STORY-013
prd: PRD-013
slug: break-glass-ingress-policy
title: "Break-glass ingress policy"
type: feature
priority: high
complexity: small
phase: "3 - Enforcement"
status: in-progress
labels: [backend, pipeline, security, identity]
epic_branch: epic/PRD-013-audit-and-usage-limits
plan: .agents/plans/PRD-013-audit-and-usage-limits/STORY-013-break-glass-ingress-policy.plan.md
report: null
commit: null
depends_on: [STORY-005, STORY-007, STORY-008]
blocks: [STORY-018]
skills: []
created: 2026-10-04
updated: 2026-10-19
---

# STORY-013: Break-glass ingress policy

## Description

As a security admin, I want `ADMIN_TOKEN` refused on ingresses where agents connect, so that pasting the break-glass credential into an agent's configuration does not work.

## Acceptance Criteria

- [ ] Given the identity `resolve(ADMIN_TOKEN)` returns, when `run_conversation(..., ingress="v1")` or `run_conversation(...)` with no ingress runs, then it returns `QueryBlockedForbiddenResponse(reason="Break-glass credential not permitted on this ingress", required_permission="ingress:break_glass")`, writes one row with `denied_permission="ingress:break_glass"`, and makes no upstream call.
- [ ] Given the default `BREAK_GLASS_INGRESSES`, when the break-glass identity sends through `POST /query` or the chat UI, then the request proceeds exactly as before this story.
- [ ] Given `BREAK_GLASS_INGRESSES="chat"`, when the break-glass identity calls `POST /query`, then it gets the `200` policy-refusal body; given `""`, then the chat UI refuses it too.
- [ ] Given a user token whose role is `admin`, or an `Identity("admin", "admin")` built directly, when it runs under `ingress="v1"`, then this arm does not fire.
- [ ] Given the admin console, when `ADMIN_TOKEN` is submitted at its gate, then sign-in works as before, and spies show this arm runs after the three authorization arms and before the usage gate.

## Technical Notes

- Step 2b in PRD Section 6.1. Reuse `_deny` with `PermissionDenied("ingress:break_glass")`: no new response class, and the chat UI's forbidden bubble already renders it.
- Fail closed: `ingress=None` is in no allowed set. Read `settings.break_glass_ingresses` per call.
- Define `Ingress = Literal["query", "chat", "v1"]` where the pipeline's other literals live, if STORY-005 did not already.
- `"ingress:break_glass"` is not an RBAC permission and must not be added to `_KNOWN_PERMISSIONS`; it is a label on the row, as `query:model:{model}` is.
- This does not change the admin role's model-allowlist bypass (PRD Section 6.8).
- New file `tests/test_query_pipeline_break_glass.py`.
- Skills: none applicable. No UI surface changes in this story.

## Dependencies

- **Blocked by**: STORY-005, STORY-007, STORY-008
- **Blocks**: STORY-018

## PRD Reference

Source: [`PRD-013-audit-and-usage-limits/PRD.md`](../../PRDs/PRD-013-audit-and-usage-limits/PRD.md) — sections 6.8 (D4), 7 (F12), 9.2 (T9), 11 (Break-glass, Refinement of the brief's criteria)
