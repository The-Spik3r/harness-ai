---
id: STORY-007
prd: PRD-020
slug: pipeline-routing-byok-audit
title: Pipeline step 2 routing, BYOK per provider and per-row provider audit
type: feature
priority: high
complexity: large
phase: "2 - Adapter and routing"
status: in-progress
labels: [backend, security]
epic_branch: epic/PRD-020-provider-registry
plan: .agents/plans/PRD-020-provider-registry/STORY-007-pipeline-routing-byok-audit.plan.md
report: null
commit: null
depends_on: [STORY-004, STORY-005, STORY-006]
blocks: [STORY-008, STORY-009, STORY-010, STORY-011, STORY-012]
skills: []
created: 2026-11-18
updated: 2026-11-18
---

# STORY-007: Pipeline step 2 routing, BYOK per provider and per-row provider audit

## Description

As a security admin, I want the pipeline to resolve the route once at step 2, send the request to that provider only, allow a caller's own key only where the provider accepts it, and record the provider on every later row, so that routing is deterministic and auditable.

## Acceptance Criteria

- [ ] Given any model, when step 2 runs, then `authorize_model` is replaced by `authorize_route` in the same position with the same label (`query:model:<m>`) and reason (`Model not permitted for this role`), and every existing verdict-order test passes unchanged.
- [ ] Given `openrouter_api_key` on a model whose provider has `byok: false`, when the request is sent, then the response is the forbidden verdict `query:byok:<provider>`, nothing goes upstream and nothing is charged; on a `byok: true` provider (the legacy one) it behaves as today.
- [ ] Given two stubs (`openrouter`, `local`) through the file-mode fixture, when `/query` and `/v1` send a model of each, then each request reaches only its own stub with its own key (`auth=yes|no`) and the upstream model is the registry `upstream` name.
- [ ] Given any row written after step 2 (success, pattern/duplicate/limit blocks, redaction error, upstream-error arm), when it is read back, then `provider`, `upstream_model` and `provider_trust` are set from the route (legacy: `openrouter`, `model_used`, `external`), while denial rows at or before step 2 have them NULL.
- [ ] Given an injected `call_openrouter` callable, when the pipeline calls it, then it still receives `(messages, model, api_key, **kw)` (D12) and the suite's stubs with that signature keep working.

## Technical Notes

- Step 2 is at `app/services/query_pipeline.py:404-413` (`authorize_model(identity, model)`; import `:29`), BYOK at `:415-423`; the route is carried in a local like `profile_name` (`:365`). `_deny` (`:257-318`) is the single `log_query` site for the authorization arms.
- The seam: `call_openrouter(redacted_messages, model=model, api_key=openrouter_api_key, **extra)` at `:783-785` (`extra` built at `:776-780`); upstream-error arm `:786-806` must record provider fields too. Every `log_query(` after step 2 in `run_conversation` (`:320`) needs the three fields; PRD-evidence line numbers (`:382-403`, `:750-763`) have drifted, use the ones above.
- The default callable (`call_openrouter` default parameters at `:327` and `run_query` `:1025`) and `/v1`'s `_Upstream` (`app/routers/v1.py:140-171`) must resolve the route from the same snapshot; the pipeline passes the original model id and the adapter maps to `upstream` (D12).
- `charges_budget=openrouter_api_key is None` at `:484` and the BYOK charge skip at `:826` stay as they are; a refused BYOK never reaches `admit` (step 2c is after step 2).
- Orchestrator decision (stories): legacy mode reads settings LIVE. The suite monkeypatches `settings.MODEL_ALLOWLIST`, `V1_TOOL_MODELS` and `OPENROUTER_*` per test (~53 references). The immutable snapshot exists only in file mode; in legacy mode the accessors derive the implicit provider from the current settings on each call (memoizing on those settings values is allowed).
- `tests/test_query_pipeline_authorization.py`, `tests/test_query_pipeline_audit_fields.py`, `tests/test_v1_query_isolation.py` and `tests/test_query_outcomes_regression.py` are the unchanged guards; new two-stub tests use `tests/_providers.py` (OD2). Fixtures from STORY-001 stay green.
- `query:byok:{provider}` is a row label like `query:model:{model}`, not a new entry in `_KNOWN_PERMISSIONS` (section 9.1). The route's `relaxes_input()`, estimation and context checks are consumed by STORIES 008-010.

## Dependencies

- **Blocked by**: STORY-004, STORY-005, STORY-006
- **Blocks**: STORY-008, STORY-009, STORY-010, STORY-011, STORY-012

## PRD Reference

Source: [`PRD-020/PRD.md`](../../PRDs/PRD-020-provider-registry/PRD.md) — Sections 4 (Pipeline), 6.1, 7 F5, 9.1, 9.2 T3, T6, T8; decisions D3, D10, D12, D13
