---
id: STORY-004
prd: PRD-022
slug: registry-anthropic-type-and-fields
title: Registry accepts type anthropic and the PRD-022 catalogue fields; adapter dispatch by provider type
type: feature
priority: high
complexity: medium
phase: "2 - Anthropic native adapter"
status: todo
labels: [backend, registry, config]
epic_branch: epic/PRD-022-provider-fallback-and-native-adapters
plan: null
report: null
commit: null
depends_on: [STORY-001]
blocks: [STORY-005, STORY-009]
skills: []
created: 2026-11-20
updated: 2026-11-20
---

# STORY-004: Registry type `anthropic`, PRD-022 catalogue fields, adapter dispatch

## Description

As an operator, I want to declare an Anthropic-native provider and its models in `PROVIDERS_FILE`, so that the harness can route Claude traffic to the Messages API directly.

## Acceptance Criteria

- [ ] Given `PROVIDERS_FILE` with `type: anthropic`, when loaded, then it is accepted with PRD-020's `base_url` transport rule (D5) and `key_env` unchanged; any other unknown type still fails with an error naming the file, provider and the allowed set (now `openai_compatible`, `anthropic`)
- [ ] Given a catalogue model, when it declares `capabilities.forced_tool_choice` / `capabilities.sampling_params` (bool, default false) and model fields `default_max_tokens` (int > 0) and `prompt_cache: off | auto` (default `off`), then they parse into frozen fields; unknown keys are still refused
- [ ] Given a `type: anthropic` provider, when a model lacks `default_max_tokens`, then startup fails naming the file, provider, model and rule; `usage_missing` is accepted but documented as having no effect for `anthropic`; `passthrough: true` on an anthropic provider is refused (catalogue ids only) unless STORY-001 found a reason to allow it
- [ ] Given `call_upstream` / `stream_upstream`, when the route's provider type is `anthropic`, then they instantiate the adapter registered for that type (one small type→adapter mapping in `upstream/__init__.py`); until STORY-005 lands, the `anthropic` entry may raise a non-retryable `UpstreamError(kind="incompatible")` — behaviour for `openai_compatible` is byte-identical
- [ ] Given the legacy registry (no `PROVIDERS_FILE`), when built, then every new field takes its default and nothing changes

## Technical Notes

- `app/services/provider_registry.py:49` `TYPES`, `:61`/`:80`/`:81` key lists, `:86-129` dataclasses, `:297` `_parse_capabilities`, `:315` `_parse_model`, `:346-352` the type refusal (its message names PRD-022; update it), `:533` `_build_legacy`.
- `app/services/upstream/__init__.py:84-127`: today both seams hard-code `OpenAICompatibleAdapter(route.provider, client)`. The `client: httpx.Client` argument is meaningful only for the OpenAI-compatible adapter; keep the seam signatures unchanged.
- Existing registry tests: extend, do not rewrite; the "only type is openai_compatible" assertion changes — comment it citing PRD-022 F1-addition.
- Orchestrator decision (STORY-001 findings): the type->adapter factory keeps `client: httpx.Client` meaningful only for `openai_compatible`; the anthropic adapter builds its own SDK client (see STORY-005's note).

## Dependencies

- **Blocked by**: STORY-001
- **Blocks**: STORY-005, STORY-009

## PRD Reference

Source: [`PRD-022/PRD.md`](../../PRDs/PRD-022-provider-fallback-and-native-adapters/PRD.md) — Sections 4 (Anthropic adapter, registry), 6.5, 9.3 (registry additions)
