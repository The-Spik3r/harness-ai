---
id: STORY-002
prd: PRD-017
slug: tool-settings
title: V1_TOOLS_ENABLED and V1_TOOL_MODELS settings with startup validation
type: technical
priority: high
complexity: small
phase: "1 - Survey and foundations"
status: in-progress
labels: [backend, config]
epic_branch: epic/PRD-017-tool-calling
plan: .agents/plans/PRD-017-tool-calling/STORY-002-tool-settings.plan.md
report: null
commit: null
depends_on: []
blocks: [STORY-008, STORY-010]
skills: []
created: 2026-11-15
updated: 2026-11-15
---

# STORY-002: V1_TOOLS_ENABLED and V1_TOOL_MODELS settings with startup validation

## Description

As a platform operator, I want one switch that turns tool calling on and an optional list of the models allowed to receive tools, so that upgrading changes nothing until I opt in and agents get a clear refusal for a model that cannot call tools.

## Acceptance Criteria

- [ ] Given no configuration, when settings load, then `V1_TOOLS_ENABLED` is `False` and `V1_TOOL_MODELS` is `""` (an empty parsed list).
- [ ] Given `V1_TOOL_MODELS="openai/gpt-4o, anthropic/claude-3.5-sonnet"` with both in `MODEL_ALLOWLIST`, when settings load, then a `v1_tool_models_list` property returns the two stripped names in order.
- [ ] Given `V1_TOOL_MODELS` naming a model that is not in `MODEL_ALLOWLIST`, when settings load, then startup fails with a message naming the setting, the offending entry and an example, in the style of the existing `V1_SSE_KEEPALIVE_SECONDS` validator.
- [ ] Given `.env.example`, when read, then it is unchanged in this story (STORY-018 documents both settings).

## Technical Notes

- `app/config.py`: the `V1_*` block (`V1_ENABLED` near line 370, `V1_SSE_KEEPALIVE_SECONDS` and its validator near 645-660, `model_allowlist_list` near 685). Follow the same comment density, citing PRD-017 D3, D10, D16.
- The cross-field check needs both settings: use a `model_validator(mode="after")` if a `field_validator` cannot see `MODEL_ALLOWLIST`; look for an existing cross-field validator in `config.py` and match it.
- Nothing reads the settings yet; STORY-008 and STORY-010 do, per request (the `_context_limit_exceeded` rule).
- Tests: `tests/test_config.py`.
- Skills: none applicable. No UI.

## Dependencies

- **Blocked by**: None
- **Blocks**: STORY-008, STORY-010

## PRD Reference

Source: [`PRD-017-tool-calling/PRD.md`](../../PRDs/PRD-017-tool-calling/PRD.md) — sections 4 (Feature flag and settings), 6.7, 9.3, 15 (D3, D10, D16)
