---
id: STORY-007
prd: PRD-002
slug: chat-pipeline-test-suite
title: "Chat pipeline unit test suite"
type: technical
priority: medium
complexity: medium
phase: "4 - Wire chat to the shared pipeline"
status: todo
labels: [testing]
epic_branch: epic/PRD-002-reflex-chat-ui
plan: null
report: null
commit: null
depends_on: [STORY-006]
blocks: [STORY-008]
skills: []
created: 2026-07-04
updated: 2026-07-04
---

# STORY-007: Chat pipeline unit test suite

## Description

As a devops engineer, I want unit tests covering the `run_query(...)` extraction and `ChatState.send()`, so that chat-vs-API parity (audit rows, blocked reasons) is verified automatically rather than only by manual walkthrough, and regressions are caught before Docker packaging (PRD Section 8, Section 11).

## Acceptance Criteria

- [ ] Given `app/services/query_pipeline.py::run_query(...)` (STORY-001), when unit tested, then tests cover the success path, duplicate-blocked path, suspicious-pattern-blocked path, and OpenRouter-error path, asserting the same outcomes PRD-001's existing integration suite (STORY-012) already asserts against `POST /query`.
- [ ] Given `ChatState.send()` (STORY-006), when unit tested, then tests verify it calls `run_query(...)` with the session's `user_id` and prompt, and appends the correct bubble type (success/duplicate-blocked/suspicious-blocked) to `messages` for each outcome.
- [ ] Given a prompt sent through `run_query(...)` directly and the same prompt sent through `POST /query`, when audit rows are compared in a test, then they have identical schema and field values (User Story 3 / Section 11 "Chat-vs-API audit row parity").
- [ ] Given the new test file `tests/test_chat_state.py` (per PRD Section 6 suggested structure), when the full test suite runs (`pytest`), then both the new chat tests and PRD-001's existing integration test suite (STORY-012) pass together, unmodified for the latter.
- [ ] Given the route-collision assertion added in STORY-003, when this test suite runs, then that assertion is included/exercised here (or confirmed already covered) so reserved-route safety is part of the regular test run, not a one-off manual check.

## Technical Notes

- Per PRD Section 6 suggested directory additions: `tests/test_chat_state.py` — "NEW: unit tests for `ChatState.send()`".
- Per PRD Section 8 (Testing): "`pytest` (existing) + new unit tests for `run_query(...)` extraction and `ChatState.send()`" and "Existing integration test suite (PRD-001 STORY-012) must continue to pass unmodified against `POST /query`, `GET /audit`, `GET /stats`."
- Reuse existing test fixtures/patterns from PRD-001's integration suite ([`tests/`](../../../tests/)) for DB setup/teardown rather than inventing a new test harness.
- This story is the automated-test gate before Docker packaging (STORY-008) — packaging validation in PRD Section 12 Phase 5 assumes the full chat flow already works, and this suite is what proves it beyond manual walkthroughs.

## Dependencies

- **Blocked by**: STORY-006
- **Blocks**: STORY-008

## PRD Reference

Source: [`PRD-002/PRD.md`](../../PRDs/PRD-002-reflex-chat-ui/PRD.md) — Section 6 (suggested directory additions), Section 8 (Testing), Section 11 (Success Criteria — audit row parity, blocked-reason parity)
