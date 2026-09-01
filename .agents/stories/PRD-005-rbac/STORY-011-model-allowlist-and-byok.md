---
id: STORY-011
prd: PRD-005
slug: model-allowlist-and-byok
title: Server-side model allowlist and BYOK as a privilege
type: feature
priority: high
complexity: medium
phase: "Phase 3 — Pipeline and ingress wiring"
status: done
labels: [backend, security]
epic_branch: epic/PRD-005-rbac
plan: .agents/plans/PRD-005-rbac/completed/STORY-011-model-allowlist-and-byok.plan.md
report: .agents/reports/PRD-005-rbac/STORY-011-model-allowlist-and-byok.report.md
commit: df72f13
depends_on: [STORY-010, STORY-005]
blocks: [STORY-013]
skills: []
created: 2026-08-28
updated: 2026-08-28
---

# STORY-011: Server-side model allowlist and BYOK as a privilege

## Description

As a security admin, I want the requested model and any caller-supplied OpenRouter key checked against the caller's role, so that the allowlist is a real control rather than a frontend convenience.

## Acceptance Criteria

- [ ] Given a role whose allowlist is `*`, when any model is requested, then it is allowed
- [ ] Given a `user`-role caller requesting a model outside `MODEL_ALLOWLIST`, when `run_query()` runs, then it returns `QueryBlockedForbiddenResponse` with `required_permission="query:model:<model>"` and never calls OpenRouter
- [ ] Given a request carrying `openrouter_api_key` from an identity without `query:byok`, when `run_query()` runs, then it is refused before the OpenRouter call
- [ ] Given the same request from an identity holding `query:byok`, when it runs, then the supplied key is used exactly as today
- [ ] Given either refusal, when it happens, then an audit row records the role and the missing permission

## Technical Notes

- Both checks live in the same step-0 block as STORY-010, evaluated after `query:submit`.
- Today `QueryRequest.model` accepts any string and nothing server-side validates it; the only allowlist is `MODEL_ALLOWLIST` in `chat_ui/chat_ui/config.py` (on `epic/PRD-004-chat-ui-redesign`), which is frontend-only. That list stays as a UI affordance but is explicitly not the control (PRD Appendix).
- `openrouter_api_key` in the request body is currently an unrestricted override of the server's key — the gap this story closes.

## Dependencies

- **Blocked by**: STORY-010, STORY-005
- **Blocks**: STORY-013

## PRD Reference

Source: [`PRD-005/PRD.md`](../../PRDs/PRD-005-rbac/PRD.md) — sections 4, 7, 9
