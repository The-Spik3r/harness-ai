---
id: STORY-012
prd: PRD-013
slug: charge-after-upstream
title: "Charge tokens after the upstream call; BYOK and counter-failure rules"
type: feature
priority: high
complexity: medium
phase: "3 - Enforcement"
status: done
labels: [backend, pipeline, limits]
epic_branch: epic/PRD-013-audit-and-usage-limits
plan: .agents/plans/PRD-013-audit-and-usage-limits/completed/STORY-012-charge-after-upstream.plan.md
report: .agents/reports/PRD-013-audit-and-usage-limits/STORY-012-charge-after-upstream.report.md
commit: 01c415d
depends_on: [STORY-003, STORY-011]
blocks: [STORY-017]
skills: []
created: 2026-10-04
updated: 2026-10-19
---

# STORY-012: Charge tokens after the upstream call; BYOK and counter-failure rules

## Description

As a platform operator, I want every token the provider reports charged to the user's day as soon as it is reported, so that the budget reflects real spend even when the response is then lost.

## Acceptance Criteria

- [ ] Given a successful request reporting 120 input and 30 output tokens, when it completes, then the user's `usage_daily` row for the admitted day has those amounts added, and a later request sees `tokens_today` increased by 150.
- [ ] Given an output-redaction failure after the provider answered, when the request fails, then the tokens are still charged; given an upstream error, then nothing is charged.
- [ ] Given a provider response with no split, when the request completes, then `tokens_used` is charged to `unsplit_tokens` and counts toward the budget.
- [ ] Given a BYOK request (`openrouter_api_key` supplied), when it completes, then it consumed one unit of the rate window, was not refused for budget even with the budget exhausted, and charged nothing, while its audit row still records the tokens.
- [ ] Given `charge_usage` raising `StorageError` after a successful upstream call, when the request completes, then the caller receives the normal success response, the success audit row is written, and one `ERROR` log line names the user, day and counts.

## Technical Notes

- Step 7b in PRD Section 6.1: immediately after `call_openrouter` returns and before step 8's output redaction, so the output-redaction error arm cannot skip it. One call site.
- Charge to the `day` the gate returned, so a request that straddles midnight is charged to the day it was admitted.
- Not called when `USAGE_LIMITS_ENABLED` is false or when the request is BYOK.
- The budget is check-then-charge and can be overshot by in-flight requests (PRD Section 6.5). Add a test that documents this rather than hiding it: two admitted requests under a nearly spent budget both complete.
- Extend `tests/test_query_pipeline_usage_limits.py`.
- Skills: none applicable. No UI surface changes in this story.

## Dependencies

- **Blocked by**: STORY-003, STORY-011
- **Blocks**: STORY-017

## PRD Reference

Source: [`PRD-013-audit-and-usage-limits/PRD.md`](../../PRDs/PRD-013-audit-and-usage-limits/PRD.md) — sections 6.1, 6.5 (D8), 7 (F11), 9.2 (T3, T6, T8, T14), 11 (Limits)
