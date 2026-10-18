---
id: STORY-006
prd: PRD-013
slug: audit-and-stats-fields
title: "/audit entry fields and /stats token aggregates"
type: feature
priority: medium
complexity: medium
phase: "1 - The row"
status: in-progress
labels: [backend, api, audit]
epic_branch: epic/PRD-013-audit-and-usage-limits
plan: .agents/plans/PRD-013-audit-and-usage-limits/STORY-006-audit-and-stats-fields.plan.md
report: null
commit: null
depends_on: [STORY-005]
blocks: [STORY-015]
skills: []
created: 2026-10-04
updated: 2026-10-17
---

# STORY-006: /audit entry fields and /stats token aggregates

## Description

As a compliance admin, I want the new audit fields on `GET /audit` and token totals on `GET /stats`, so that I can read cost and grouping without database access.

## Acceptance Criteria

- [ ] Given rows written by STORY-005, when `GET /audit` is called, then each entry carries `ingress`, `message_count`, `input_tokens`, `output_tokens`, `streamed`, `has_tool_calls`, `conversation_key` and `limit_exceeded` as stored.
- [ ] Given a row written before this PRD, when `GET /audit` returns it, then the six nullable fields are `null` and the two flags are `false`.
- [ ] Given rows with and without a token split, when `GET /stats` is called, then `input_tokens` and `output_tokens` equal `SUM` over `audit_logs` with NULL as 0, and `blocked_usage_limits` equals the count of rows with `limit_exceeded IS NOT NULL` (0 until STORY-011).
- [ ] Given the batched read and the figure-by-figure fallback, when both are run against the same data, then all thirteen figures agree, and `SummarySnapshot` still partitions `SUMMARY_FIGURES` exactly.
- [ ] Given the existing `/audit` and `/stats` tests, when they run, then no existing assertion changes and every pre-existing response field keeps its value.

## Technical Notes

- `app/models/schemas.py`: `AuditQueryEntry` gains eight optional or defaulted, unvalidated fields (the `session_id` comment explains why read models do not validate). `StatsResponse` gains three `int = 0` fields.
- `app/routers/admin.py`: verbatim passthrough in `get_audit`; `get_stats` keeps `row_limit=0`.
- `app/db/database.py`: append three named columns to `_SUMMARY_SQL` **after** the existing ten. They take no parameter, so the positional binding `(row_limit, ranked_limit, ranked_limit, ranked_limit)` does not move (PRD Risk 8). Add three standalone functions, three decoders and three `SummarySnapshot` properties.
- `chat_ui/chat_ui/admin_state.py`'s `_READS` is tied to `SUMMARY_FIGURES` by a length test. Add the three `READ_LABEL_*` entries and state fields here so that test stays true; rendering them is STORY-015.
- `conversation_key` is exposed on `/audit`; `dedup_key` still is not (PRD-009 D5).
- Skills: none applicable. No UI surface changes in this story.

## Dependencies

- **Blocked by**: STORY-005
- **Blocks**: STORY-015

## PRD Reference

Source: [`PRD-013-audit-and-usage-limits/PRD.md`](../../PRDs/PRD-013-audit-and-usage-limits/PRD.md) — sections 6.10, 7 (F13), 10, 11 (Audit), 14 (Risk 8)
