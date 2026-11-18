---
id: STORY-004
prd: PRD-020
slug: route-resolution-and-authorize-route
title: Route resolution, visible models and authorize_route
type: feature
priority: high
complexity: medium
phase: "2 - Adapter and routing"
status: todo
labels: [backend, security]
epic_branch: epic/PRD-020-provider-registry
plan: null
report: null
commit: null
depends_on: [STORY-003]
blocks: [STORY-007, STORY-011, STORY-012]
skills: []
created: 2026-11-18
updated: 2026-11-18
---

# STORY-004: Route resolution, visible models and authorize_route

## Description

As a security admin, I want a model id resolved to exactly one provider by exact catalogue lookup, and checked against per-role access, so that a caller can never choose a host and an unknown model and a forbidden one are indistinguishable.

## Acceptance Criteria

- [ ] Given a catalogue and one passthrough provider, when `resolve(model)` is called, then an exact catalogued id returns its `Route` (provider, `upstream` name, capabilities), an uncatalogued id returns the passthrough route with `upstream` = the id as sent, and with no passthrough it returns `None`; `openai/gpt-4o` never routes to a provider named `openai` (no prefix parsing).
- [ ] Given roles on model and provider, when `authorize_route(identity, model)` is called, then the effective roles are `model.roles`, else `provider.roles`, else every role (F2); a role outside the set raises `PermissionDenied("query:model:<model>")`, the same exception for an unknown model.
- [ ] Given `MODEL_ALLOWLIST_WILDCARD_ROLES` (admin), when admin requests a catalogued model its roles exclude or an uncatalogued model, then it is permitted; a non-wildcard role requesting an uncatalogued (passthrough) model is denied (OD3).
- [ ] Given `RBAC_ENABLED=false`, when `authorize_route` is called with an unresolvable model, then it still raises `query:model:<model>` (there is nowhere to send it), and with a resolvable model it returns the route without a role check.
- [ ] Given a `Route`, when `route.relaxes_input()` is called, then it is true iff `PII_REDACTION_ENABLED` and `provider.trust == "internal"` and `provider.pii == "relaxed"`, and `visible_models(identity)` / `supports_tools(model)` return the role-filtered catalogue and the model's `tools` capability with no I/O.

## Technical Notes

- Add `Route`, `resolve`, `visible_models`, `supports_tools` to `app/services/provider_registry.py` and `authorize_route` to `app/services/authz.py` beside `authorize_model` (`authz.py:188-203`, wildcard roles `:76-78`, RBAC bypass `:194-195`). Keep `authorize_model` in place; STORY-007 switches the pipeline to the new function.
- The denial must be indistinguishable: same exception text as `authorize_model`'s `PermissionDenied(f"query:model:{model}")` (T3). The `chat`/`code` redaction switch read for `relaxes_input()` is `settings.PII_REDACTION_ENABLED`, read per call (legacy mode reads settings live, OD1).
- Orchestrator decision (stories): legacy mode reads settings LIVE. The suite monkeypatches `settings.MODEL_ALLOWLIST`, `V1_TOOL_MODELS` and `OPENROUTER_*` per test (~53 references). The immutable snapshot exists only in file mode; in legacy mode the accessors derive the implicit provider from the current settings on each call (memoizing on those settings values is allowed).
- Orchestrator decision (stories): uncatalogued (passthrough) models are permitted only to `MODEL_ALLOWLIST_WILDCARD_ROLES`; `provider.roles` / `model.roles` apply to catalogued models. This is what keeps legacy (`passthrough: true`) identical.
- Pure functions over the snapshot: tests build registries through `tests/_providers.py` (STORY-003, OD2). The legacy implicit provider must satisfy the same API so `authorize_route` in legacy mode reproduces `authorize_model`: non-admin allowed iff the model is in `settings.model_allowlist_list`, admin anything.
- Existing tests to keep unchanged: `tests/test_authz.py` and `tests/test_rbac.py` (they patch `settings.MODEL_ALLOWLIST`).

## Dependencies

- **Blocked by**: STORY-003
- **Blocks**: STORY-007, STORY-011, STORY-012

## PRD Reference

Source: [`PRD-020/PRD.md`](../../PRDs/PRD-020-provider-registry/PRD.md) — Sections 6.3, 6.6, 7 F2, 9.2 T3; decisions D3, D4
