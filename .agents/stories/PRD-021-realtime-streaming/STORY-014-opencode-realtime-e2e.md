---
id: STORY-014
prd: PRD-021
slug: opencode-realtime-e2e
title: OpenCode end-to-end on a real-time stream
type: technical
priority: medium
complexity: medium
phase: "4 - Clients and docs"
status: done
labels: [testing, e2e, v1]
epic_branch: epic/PRD-021-realtime-streaming
plan: .agents/plans/PRD-021-realtime-streaming/completed/STORY-014-opencode-realtime-e2e.plan.md
report: .agents/reports/PRD-021-realtime-streaming/STORY-014-opencode-realtime-e2e.report.md
commit: 5eebd78
depends_on: [STORY-001, STORY-004, STORY-010]
blocks: [STORY-016]
skills: []
created: 2026-11-18
updated: 2026-11-19
---

# STORY-014: OpenCode end-to-end on a real-time stream

## Description

As an integrating developer using OpenCode, I want proof that a real-time stream works in the real client — text, a denied tool call and reasoning display — so that an admin can grant `stream:realtime` to a role whose client is verified.

## Acceptance Criteria

- [ ] Given the opt-in E2E harness from PRD-017 and the stub streaming with delays (STORY-004), when OpenCode runs a scripted session against a harness with the switch on and a role holding `stream:realtime`, then the answer text arrives and the run completes without client errors
- [ ] Given a scripted `DROP TABLE` tool call streamed in fragments, when OpenCode runs, then the call is denied, OpenCode shows the denial note, and no fragment was released (from the harness side)
- [ ] Given a role holding both grants and scripted reasoning, when OpenCode runs, then the report records whether OpenCode displayed the reasoning and never wrote it into a file or into content
- [ ] Given the default suite, when it runs without the E2E opt-in, then these tests are skipped (marker as in PRD-017)

## Technical Notes

- Reuse `tests/test_e2e_opencode_script.py` and the `e2e` marker setup (`tests/test_e2e_marker.py`); OpenCode is installed globally on the dev machine.
- STORY-001's survey says which reasoning field OpenCode reads; the assertion follows it.
- Report the OpenCode version.
- Orchestrator note (STORY-001): OpenCode 2.3.2; for a user-defined provider without `reasoning_field`, which field it reads was inconclusive from the binary — check OpenCode's provider docs/config and record it; set the field explicitly in the E2E config if needed.

## Dependencies

- **Blocked by**: STORY-001, STORY-004, STORY-010
- **Blocks**: STORY-016

## PRD Reference

Source: [`PRD-021/PRD.md`](../../PRDs/PRD-021-realtime-streaming/PRD.md) — Sections 8, 12 Phase 4, User story 5, Risk 4
