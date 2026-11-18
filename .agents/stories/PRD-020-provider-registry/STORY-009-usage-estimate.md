---
id: STORY-009
prd: PRD-020
slug: usage-estimate
title: Estimate usage when a provider reports none
type: feature
priority: high
complexity: medium
phase: "3 - Policies that depend on the provider"
status: done
labels: [backend, usage]
epic_branch: epic/PRD-020-provider-registry
plan: .agents/plans/PRD-020-provider-registry/completed/STORY-009-usage-estimate.plan.md
report: .agents/reports/PRD-020-provider-registry/STORY-009-usage-estimate.report.md
commit: 3b12ec1
depends_on: [STORY-007, STORY-005]
blocks: [STORY-013, STORY-014]
skills: []
created: 2026-11-18
updated: 2026-11-18
---

# STORY-009: Estimate usage when a provider reports none

## Description

As a security admin, I want a provider that reports no usage to still count against the daily budget through a documented estimate, so that a local model can never be used to escape it and the audit says the figure is an estimate.

## Acceptance Criteria

- [ ] Given `estimate_tokens(sent, received, chars_per_token)`, when called with messages, history tool_call arguments, tools and a response, then it returns `ceil(sent_chars/cpt) + ceil(received_chars/cpt)` per section 6.7, is pure (no I/O, no settings) and has table-driven tests including tools and empty strings.
- [ ] Given a provider with `usage_missing: estimate` and a stub reply with `"usage": null`, when the request completes, then the result carries `usage_estimated=True`, `tokens_used` = the estimate, no split, and the user's `unsplit_tokens` grows by exactly that amount at step 7b.
- [ ] Given the section 6.7 table, when usage is absent, `null`, or has no `total_tokens` but both splits valid, then the adapter returns total = split sum when both are valid and otherwise the estimate; with `usage_missing: error` (legacy) it raises today's `OpenRouter returned an unexpected response shape: ...` error unchanged.
- [ ] Given an estimated usage, when the audit row is written, then `usage_estimated=1`, `tokens_used` = the estimate, and `input_tokens` / `output_tokens` are NULL.
- [ ] Given an estimated usage through `/v1`, when the body is built, then `usage` is `0/0/estimate` and `harness.usage_estimated: true` is present; when usage was reported, the key is absent and the legacy body is byte-identical.

## Technical Notes

- New pure module `app/services/usage_estimate.py`. Today a missing `usage`/`total_tokens` raises at `app/services/openrouter_client.py:311-316` and the split is optional via `_token_count` (`:119`, `:318-319`); the adapter (STORY-005) applies the table in section 6.7 there. `UpstreamResult` gains a `usage_estimated: bool = False`.
- Sent chars are measured after step 6 (what is actually sent), received chars from the response; the pipeline passes the messages/tools to the adapter via the request. Step 7b charge: `app/services/query_pipeline.py:826-835` passes `(input_tokens, output_tokens, tokens_used)`; with a None split it lands in `unsplit_tokens` (`app/services/usage_limits.py:191-212`, `app/db/models.py:224-230`), so `usage_daily` needs no change.
- `/v1` usage mapping `app/services/v1_translate.py:634-649` (a missing split already reports `0`); `HarnessCompletionInfo` is built at `:650-656` and declared at `app/models/v1_schemas.py:175`, add the optional `usage_estimated` to both, emitted only when true so legacy bodies are unchanged.
- Estimate uses the provider's `estimate_chars_per_token` (default 4, O7 adopted).
- Orchestrator decision (stories): PRD open decisions O1-O8 are adopted as proposed.
- Orchestrator decision (STORY-005 verify): in `app/services/upstream/openai_compatible.py` (`complete`, the `usage = data["usage"]` block) a `"usage": null` or any non-object usage raises a bare `TypeError` (`None["total_tokens"]`), inherited unchanged from `call_openrouter`; only `KeyError/IndexError/ValueError` are caught. This story must route null / non-object usage through the D8 table (estimate, or `UpstreamError` with today's message under `usage_missing: error`), never a `TypeError`. The stub already supports `"usage": null` (STORY-005).

## Dependencies

- **Blocked by**: STORY-007, STORY-005
- **Blocks**: STORY-013, STORY-014

## PRD Reference

Source: [`PRD-020/PRD.md`](../../PRDs/PRD-020-provider-registry/PRD.md) — Sections 4 (Adapter, Pipeline step 7b), 6.7, 9.2 T5; decisions D8
