---
id: STORY-011
prd: PRD-020
slug: v1-capabilities-and-models
title: /v1 tool capability from the registry and per-role GET /v1/models
type: feature
priority: high
complexity: medium
phase: "3 - Policies that depend on the provider"
status: todo
labels: [backend, api]
epic_branch: epic/PRD-020-provider-registry
plan: null
report: null
commit: null
depends_on: [STORY-007, STORY-004]
blocks: [STORY-014]
skills: []
created: 2026-11-18
updated: 2026-11-18
---

# STORY-011: /v1 tool capability from the registry and per-role GET /v1/models

## Description

As an integrating developer, I want `GET /v1/models` to list only the models I can use with their capabilities, and a tools request to a model without tool support to be refused clearly, so that my coding agent is configured correctly.

## Acceptance Criteria

- [ ] Given file mode and a `tools` request to a model with `tools: false`, when sent to `/v1/chat/completions`, then the response is `400 tools_not_supported` with `param: "tools"` and message `model is not enabled for tool calling`; in legacy mode the message stays `model is not enabled for tool calling (V1_TOOL_MODELS)`.
- [ ] Given file mode, when a `user` calls `GET /v1/models`, then only catalogued models the role may use are listed, each with `owned_by` = provider name and `harness: {provider, capabilities: {tools, streaming, reasoning, max_context_tokens}}`; passthrough models are not listed.
- [ ] Given legacy mode (no `PROVIDERS_FILE`), when `GET /v1/models` and `GET /v1/models/{id}` are called, then the bodies are byte-identical to the STORY-001 fixtures (no `harness` key, every role sees `MODEL_ALLOWLIST`).
- [ ] Given `GET /v1/models/{id}` in file mode, when the id is not catalogued or not visible to the caller, then it returns `404 model_not_found` with the same body for both cases.
- [ ] Given `V1_TOOLS_ENABLED=false`, when a tools request is sent, then the flag-off behaviour is unchanged.

## Technical Notes

- Translator check: `app/services/v1_translate.py:529-530` (`if tools is not None and tool_models and body.model not in tool_models`), rule text `_TOOL_MODEL_RULE` at `:166`; the translator reads no settings, so the router passes the capability in. Router read `app/routers/v1.py:353-358` (`tool_models=settings.v1_tool_models_list`). Replace by `supports_tools(model)` in file mode; legacy mode keeps the `V1_TOOL_MODELS` list semantics (empty list = no extra restriction, a set list binds admin too, `app/config.py:745-770`).
- Models routes: `app/routers/v1.py:448-458` and `:461-475`; `_model_entry` `:420-423`; schema `ModelEntry` at `app/models/v1_schemas.py:274-280` gains an optional `harness` object, serialized only in file mode so legacy bodies stay identical.
- The 404 for not-visible must not reveal existence (T3): same code and message as not-catalogued (`MODEL_NOT_FOUND`, message today `model is not in MODEL_ALLOWLIST`, `:476-479`; use a mode-neutral message in file mode).
- Orchestrator decision (stories): legacy mode reads settings LIVE. The suite monkeypatches `settings.MODEL_ALLOWLIST`, `V1_TOOL_MODELS` and `OPENROUTER_*` per test (~53 references). The immutable snapshot exists only in file mode; in legacy mode the accessors derive the implicit provider from the current settings on each call (memoizing on those settings values is allowed).
- Tests: `tests/test_v1_models.py` and `tests/test_v1_tools.py` stay unchanged for legacy; file-mode cases use `tests/_providers.py` (OD2).

## Dependencies

- **Blocked by**: STORY-007, STORY-004
- **Blocks**: STORY-014

## PRD Reference

Source: [`PRD-020/PRD.md`](../../PRDs/PRD-020-provider-registry/PRD.md) — Sections 4 (Ingresses), 7 F4, 10; decisions D6, D14; threat T3
