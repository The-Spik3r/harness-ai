---
id: STORY-013
prd: PRD-021
slug: audit-api-and-register
title: GET /audit real-time fields, completion_id filter and Register LIVE marker
type: feature
priority: medium
complexity: small
phase: "3 - Ingresses"
status: done
labels: [backend, api, audit, chat-ui]
epic_branch: epic/PRD-021-realtime-streaming
plan: .agents/plans/PRD-021-realtime-streaming/completed/STORY-013-audit-api-and-register.plan.md
report: .agents/reports/PRD-021-realtime-streaming/STORY-013-audit-api-and-register.report.md
commit: 5313d70
depends_on: [STORY-009]
blocks: [STORY-016]
skills: [frontend-design]
created: 2026-11-18
updated: 2026-11-19
---

# STORY-013: GET /audit real-time fields, completion_id filter and Register LIVE marker

## Description

As an auditor, I want the audit API and the admin Register to show how each response was delivered and to find a row by its stream id, so that a client log line leads straight to its row.

## Acceptance Criteria

- [ ] Given `GET /audit`, when rows are returned, then each has `streamed_realtime`, `reasoning_shown`, `stream_redaction_divergence` (booleans) and `completion_id`
- [ ] Given `GET /audit?completion_id=chatcmpl-harness-rt-…`, when called, then only the exact match is returned, scoped by `audit:read:own` / `audit:read:all` as today (another user's row is not visible with `own`)
- [ ] Given the admin Register, when a row has `streamed_realtime=1`, then a `LIVE` marker is shown beside it; other rows are unchanged
- [ ] Given existing audit API and Register tests, when they run, then they pass (any modified assertion cites PRD-021 F7)

## Technical Notes

- The audit router and query API; the filter goes through the same parameterized query path as existing filters (no string interpolation). Grep for how PRD-020 added `provider` to the API and the Register's provider column (PRD-020 STORY-012, 11 tracks).
- Register copy follows the chat UI copy rules; `LIVE` is a tag in the Register's existing tag vocabulary style.
- OpenAPI schema updated if the repo pins it.

## Dependencies

- **Blocked by**: STORY-009
- **Blocks**: STORY-016

## PRD Reference

Source: [`PRD-021/PRD.md`](../../PRDs/PRD-021-realtime-streaming/PRD.md) — Sections F7, 10 (GET /audit), User story 6
