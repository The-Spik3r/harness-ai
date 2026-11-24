---
id: STORY-019
prd: PRD-023
slug: mcp-corpus-and-latency
title: "`tests/corpora/mcp/` decision corpus and the gateway latency measurement"
type: technical
priority: high
complexity: medium
phase: "4 - Bridge, evidence and clients"
status: done
labels: [tests, mcp, corpus]
epic_branch: epic/PRD-023-mcp-and-skills
plan: .agents/plans/PRD-023-mcp-and-skills/completed/STORY-019-mcp-corpus-and-latency.plan.md
report: .agents/reports/PRD-023-mcp-and-skills/STORY-019-mcp-corpus-and-latency.report.md
commit: 3903631
depends_on: [STORY-014, STORY-015, STORY-016]
blocks: [STORY-020]
skills: []
created: 2026-11-22
updated: 2026-11-24
---

# STORY-019: `tests/corpora/mcp/` decision corpus and the gateway latency measurement

## Description

As a security admin, I want a corpus of gateway calls with their declared decision and outcome per role, run against the stub server, so that the MVP definition is a test.

## Acceptance Criteria

- [ ] Given `tests/corpora/mcp/` with at least 30 calls (every outcome, every visibility case, the four MVP-goal calls, alias and correlation cases) in the PRD-016 corpus format plus `server:`, when the suite runs against the stub, then each produces its declared decision and outcome for every role it names
- [ ] Given every denied corpus call, when run, then the stub's counter for it does not increase; given every forwarded call, then its row exists before the stub sees it
- [ ] Given the gateway against the stub on a local libSQL file, when measured, then the p95 of M0–M9 excluding the upstream round trip is recorded in the story report with the target ≤ 25 ms, and the DB round trips per call are at most three

## Technical Notes

- Follow `tests/corpora/actions/` and its loader for format.
- Report the latency honestly even if the target is missed.

## Dependencies

- **Blocked by**: STORY-014, STORY-015, STORY-016
- **Blocks**: STORY-020

## PRD Reference

Source: [`PRD-023/PRD.md`](../../PRDs/PRD-023-mcp-and-skills/PRD.md) — Sections 11 (MVP definition, Quality), F12
