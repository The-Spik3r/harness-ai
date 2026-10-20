---
id: STORY-011
prd: PRD-013
slug: usage-gate-in-pipeline
title: "Usage gate in the pipeline: response, audited arm and duplicate-lookup exclusion"
type: feature
priority: high
complexity: large
phase: "3 - Enforcement"
status: done
labels: [backend, pipeline, limits, api, security]
epic_branch: epic/PRD-013-audit-and-usage-limits
plan: .agents/plans/PRD-013-audit-and-usage-limits/completed/STORY-011-usage-gate-in-pipeline.plan.md
report: .agents/reports/PRD-013-audit-and-usage-limits/STORY-011-usage-gate-in-pipeline.report.md
commit: 8dc6b4d
depends_on: [STORY-002, STORY-005, STORY-010]
blocks: [STORY-012, STORY-014, STORY-015, STORY-016]
skills: []
created: 2026-10-04
updated: 2026-10-19
---

# STORY-011: Usage gate in the pipeline: response, audited arm and duplicate-lookup exclusion

## Description

As a platform operator, I want an authorized request over its rate or budget refused before any content check and recorded like any other block, so that a looping agent is bounded and the refusal is evidence.

## Acceptance Criteria

- [ ] Given an identity over its rate limit or its budget, when `run_conversation` runs, then it returns `QueryBlockedUsageLimitResponse(reason="Usage limit reached", limit=..., maximum=..., actual=..., resets_at=...)`, `call_openrouter` is not called, and exactly one row is written with `success=1`, `limit_exceeded` set, `role` set and a non-NULL `dedup_key`.
- [ ] Given spies on each step, when a request runs, then the order is authorization, usage gate, context limit, duplicate, patterns; a caller without `query:submit` never reaches the gate and has no `usage_daily` row; a duplicate-blocked request and a context-limit refusal each consume one unit of the rate window.
- [ ] Given a prompt refused for a usage limit, when the same prompt is sent again after the window resets, then it is answered and not held as a duplicate; `test_duplicate_scope.py` and STORY-001 pass with no assertion changed.
- [ ] Given `POST /query` over a limit, when it is called, then the status is `200` with the usage-limit body; given `admit` raising `UsageLimitError`, then the status is `500` and no upstream call is made.
- [ ] Given `USAGE_LIMITS_ENABLED=false`, when any request runs, then no statement touches `usage_daily`, and `tests/test_query_outcomes_regression.py` gains row 8 (usage limit) with rows 1-7 unchanged.

## Technical Notes

- Step 2c in PRD Section 6.1: after the three authorization arms (and after STORY-013's arm once it exists), before `_context_limit_exceeded`. Existing step numbers in comments are kept; this one is lettered.
- `charges_budget = openrouter_api_key is None` (D8). Keep the `Admission` in a local; STORY-012 uses its `day`.
- `app/models/schemas.py`: add `QueryBlockedUsageLimitResponse` to `QueryResponse`; add it to `QueryPipelineResult`.
- `find_duplicate_timestamp` gains `AND limit_exceeded IS NULL`, with a comment in the style of the flag exclusion. NULL passes, so pre-PRD rows behave as before (PRD Risk 5).
- `app/routers/query.py`: one more `except UsageLimitError` arm mapping to 500, beside `DuplicateCheckError`.
- `ChatState._do_send` handles every result type exhaustively. Until STORY-014 adds the bubble, route the new result through an existing generic bubble so no send is silently dropped, and route `UsageLimitError` through the internal-error bubble.
- Most existing pipeline tests run with limits on by default. They stay green because the defaults are far above what a test sends, but each now writes a `usage_daily` row; check fixtures that assert on table contents.
- New file `tests/test_query_pipeline_usage_limits.py`.
- Skills: none applicable. No UI surface changes in this story.

## Dependencies

- **Blocked by**: STORY-002, STORY-005, STORY-010
- **Blocks**: STORY-012, STORY-014, STORY-015, STORY-016

## PRD Reference

Source: [`PRD-013-audit-and-usage-limits/PRD.md`](../../PRDs/PRD-013-audit-and-usage-limits/PRD.md) — sections 6.1 (D7), 6.7 (D5, D6), 7 (F10), 9.2, 10, 11 (Limits, Eight outcomes)
