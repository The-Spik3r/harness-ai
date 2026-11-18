---
id: STORY-010
prd: PRD-020
slug: max-context-tokens
title: Refuse a conversation that exceeds a model's max_context_tokens
type: feature
priority: medium
complexity: small
phase: "3 - Policies that depend on the provider"
status: in-progress
labels: [backend, pipeline]
epic_branch: epic/PRD-020-provider-registry
plan: .agents/plans/PRD-020-provider-registry/STORY-010-max-context-tokens.plan.md
report: null
commit: null
depends_on: [STORY-007]
blocks: [STORY-015]
skills: []
created: 2026-11-18
updated: 2026-11-18
---

# STORY-010: Refuse a conversation that exceeds a model's max_context_tokens

## Description

As a platform operator, I want a model with a small context window to refuse an over-long conversation instead of silently truncating it, so that a local model never drops the system prompt or early turns without anyone knowing.

## Acceptance Criteria

- [ ] Given a model with `max_context_tokens: N` and a conversation whose estimate exceeds N, when step 3 runs, then the response is a `QueryBlockedContextLimitResponse` with `limit="estimated_tokens"`, `maximum=N`, `actual` = the estimate, and nothing goes upstream.
- [ ] Given an estimate equal to N, when step 3 runs, then the request proceeds (the refusal is strictly greater).
- [ ] Given a model without `max_context_tokens`, when any conversation is sent, then step 3 behaves exactly as today (`messages`/`characters` checks only).
- [ ] Given the refusal, when `/v1` receives it, then it maps to the existing `context_length_exceeded` 400 (`_VERDICTS`, detail `estimated_tokens <actual> > <maximum>`), and the audit row has `success=False` and `error_message` `context limit: estimated_tokens <actual> > <maximum>`.
- [ ] Given the `limit` literal, when the schema is read, then `app/models/schemas.py` accepts `estimated_tokens` and the existing `messages | characters | redaction_characters` cases are unchanged.

## Technical Notes

- Step 3 is `_context_limit_exceeded(messages)` at `app/services/query_pipeline.py:122` with its call, row and response at `:530-553` (the row records the reason in `error_message`, `:538`); add the token check after the two character checks so existing verdicts keep their order. The `limit` Literal is at `app/models/schemas.py:150` (docstring `:123-148`).
- Orchestrator decision (stories): the D9 estimate = ceil((chars of the request's messages content + history tool_call arguments + `json.dumps(tools)` when sent) / the provider's `estimate_chars_per_token`), computed at step 3 on the pre-redaction messages, reusing `usage_estimate.estimate_tokens` with received = 0.
- `/v1` mapping of context-limit refusals is `_VERDICTS` at `app/services/v1_translate.py:685-688` (`translate_verdict` `:713`); only `redaction_characters` gets its own code (`_verdict_code` `:700-710`), so `estimated_tokens` falls to `context_length_exceeded`; the chat bubble that renders a context-limit refusal (`tests/test_context_limit_bubble.py`) must tolerate the new `limit` value.
- Uses `route.model.max_context_tokens` (STORY-004/007); the passthrough provider's `passthrough_capabilities` may omit it, in which case the check is skipped.
- T10 is unverified per server (section 15): this check is the mitigation, not a proof of a server's real window.

## Dependencies

- **Blocked by**: STORY-007
- **Blocks**: STORY-015

## PRD Reference

Source: [`PRD-020/PRD.md`](../../PRDs/PRD-020-provider-registry/PRD.md) — Sections 4 (Pipeline step 3), 6.1, 7 F4, 10, 9.2 T10; decisions D9
