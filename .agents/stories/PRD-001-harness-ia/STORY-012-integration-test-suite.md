---
id: STORY-012
prd: PRD-001
slug: integration-test-suite
title: End-to-end integration test suite
type: technical
priority: high
complexity: medium
phase: "4 - Admin Endpoints & Testing"
status: done
labels: [testing]
epic_branch: epic/PRD-001-harness-ia
plan: .agents/plans/PRD-001-harness-ia/completed/STORY-012-integration-test-suite.plan.md
report: .agents/reports/PRD-001-harness-ia/STORY-012-integration-test-suite.report.md
commit: 44266dc
depends_on: [STORY-008, STORY-010, STORY-011]
blocks: [STORY-013]
skills: []
created: 2026-07-04
updated: 2026-07-04
---

# STORY-012: End-to-end integration test suite

## Description

As a devops engineer, I want a pytest suite that exercises the full API surface end-to-end, so that regressions in the pipeline, admin endpoints, or auth are caught before deployment.

## Acceptance Criteria

- [ ] Given the happy-path flow from PRD Section 5.1, when run as a test, then it asserts a `SUCCESS` response and exactly one new `audit_logs` row.
- [ ] Given the duplicate-blocked flow from PRD Section 5.2, when run as a test, then it asserts OpenRouter is never called (mocked) and the `BLOCKED` duplicate shape is returned.
- [ ] Given the suspicious-pattern flow from PRD Section 5.3, when run as a test, then it asserts OpenRouter is never called and the `BLOCKED` suspicious shape is returned, for each of the 7 patterns.
- [ ] Given `/audit` and `/stats`, when tested with and without a valid admin token, then both the authorized and unauthorized paths are covered.
- [ ] Given the full suite, when run in CI, then it passes without requiring a real OpenRouter API key (the client is mocked/stubbed).

## Technical Notes

- Use `pytest` + FastAPI `TestClient`/`httpx.AsyncClient` per PRD Section 8.
- Mock `openrouter_client` so tests don't make real network calls.
- Use a temporary/in-memory SQLite DB per test run to keep tests isolated and repeatable.

## Dependencies

- **Blocked by**: STORY-008, STORY-010, STORY-011
- **Blocks**: STORY-013

## PRD Reference

Source: [`PRD-001/PRD.md`](../../PRDs/PRD-001-harness-ia/PRD.md) — Section 5 (all flows), Section 11 (Success Criteria), Section 12 (Phase 4)
