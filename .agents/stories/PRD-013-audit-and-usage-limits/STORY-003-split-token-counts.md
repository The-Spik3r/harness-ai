---
id: STORY-003
prd: PRD-013
slug: split-token-counts
title: "OpenRouter client returns input and output tokens separately"
type: feature
priority: high
complexity: small
phase: "1 - The row"
status: todo
labels: [backend, openrouter]
epic_branch: epic/PRD-013-audit-and-usage-limits
plan: null
report: null
commit: null
depends_on: [STORY-001]
blocks: [STORY-005, STORY-012]
skills: []
created: 2026-10-04
updated: 2026-10-04
---

# STORY-003: OpenRouter client returns input and output tokens separately

## Description

As a platform operator, I want the provider's prompt and completion token counts kept apart, so that cost can be read as input versus output and not only as a total.

## Acceptance Criteria

- [ ] Given a provider response whose `usage` has `prompt_tokens=120`, `completion_tokens=30`, `total_tokens=150`, when `call_openrouter` returns, then `OpenRouterResult` has `input_tokens=120`, `output_tokens=30` and `tokens_used=150`.
- [ ] Given a response whose `usage` has only `total_tokens`, when `call_openrouter` returns, then it succeeds with `input_tokens=None` and `output_tokens=None`.
- [ ] Given `prompt_tokens` that is a string, a negative number or a `bool`, when `call_openrouter` returns, then that field is `None` and no error is raised.
- [ ] Given a response with no `total_tokens`, when `call_openrouter` runs, then it raises `OpenRouterError` exactly as before (STORY-001's assertion unchanged).
- [ ] Given the existing suite's stubs that build `OpenRouterResult(response, model_used, tokens_used)` positionally, when the suite runs, then every one still constructs and passes.

## Technical Notes

- `app/services/openrouter_client.py`: add `input_tokens: Optional[int] = None` and `output_tokens: Optional[int] = None` after `tokens_used`, so positional construction keeps working.
- Read the two fields with `.get`. `bool` is a subclass of `int`; reject it the way `GenerationParams.max_tokens` does.
- No pipeline change here. `run_conversation` starts passing the split in STORY-005.
- Extend `tests/test_openrouter_client.py`.
- Skills: none applicable. No UI surface changes in this story.

## Dependencies

- **Blocked by**: STORY-001
- **Blocks**: STORY-005, STORY-012

## PRD Reference

Source: [`PRD-013-audit-and-usage-limits/PRD.md`](../../PRDs/PRD-013-audit-and-usage-limits/PRD.md) — sections 4 (OpenRouter client), 7 (F3), 11 (Audit)
