---
id: STORY-007
prd: PRD-001
slug: openrouter-client
title: OpenRouter API client wrapper
type: feature
priority: high
complexity: medium
phase: "3 - OpenRouter Integration"
status: in-progress
labels: [backend, api, integration]
epic_branch: epic/PRD-001-harness-ia
plan: .agents/plans/PRD-001-harness-ia/STORY-007-openrouter-client.plan.md
report: null
commit: null
depends_on: [STORY-003]
blocks: [STORY-008]
skills: []
created: 2026-07-04
updated: 2026-07-04
---

# STORY-007: OpenRouter API client wrapper

## Description

As an integrating developer, I want a thin client wrapping OpenRouter's chat completion API, so that the harness can forward prompts to any model (Claude, GPT, etc.) OpenRouter supports (RF-10, RF-11).

## Acceptance Criteria

- [ ] Given a prompt and a model name, when the client calls OpenRouter, then it returns the model's text response and token usage.
- [ ] Given no `model` is specified upstream, when the client is invoked, then it defaults to `"gpt-4"` per PRD Section 10.
- [ ] Given a per-request `openrouter_api_key` is provided, when the client calls OpenRouter, then it uses that key instead of the `OPENROUTER_API_KEY` env var; given neither is provided, then it raises a clear configuration error.
- [ ] Given OpenRouter returns an error or times out, when the client is invoked, then it surfaces a typed error (not a raw exception) so the caller can log `success=false` with an `error_message`.

## Technical Notes

- Implement `app/services/openrouter_client.py` per PRD Section 6, using `httpx` (PRD Section 8).
- Client must be swappable/mockable for tests — no direct HTTP calls inside route handlers.
- Do not log full API keys; treat them as secrets in any error messages.

## Dependencies

- **Blocked by**: STORY-003
- **Blocks**: STORY-008

## PRD Reference

Source: [`PRD-001/PRD.md`](../../PRDs/PRD-001-harness-ia/PRD.md) — Section 7 (OpenRouter wrapper), Section 10 (API Specification), Section 12 (Phase 3)
