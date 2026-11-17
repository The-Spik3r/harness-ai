---
id: STORY-013
prd: PRD-018
slug: success-criteria-fault-suite
title: Success-criteria suite — statements 1–14 under fault injection, outage end-to-end, opt-in chaos, latency
type: technical
priority: high
complexity: medium
phase: "5 - Visible and documented"
status: todo
labels: [tests, storage]
epic_branch: epic/PRD-018-db-resilience
plan: null
report: null
commit: null
depends_on: [STORY-010, STORY-011]
blocks: [STORY-014]
skills: []
created: 2026-11-17
updated: 2026-11-17
---

# STORY-013: Prove the MVP definition

## Description

As a platform operator, I want the PRD's MVP definition pinned by tests at the request level, so that a blip is provably absorbed, an unsafe replay provably never happens and an outage provably loses no row.

## Acceptance Criteria

- [ ] Given `_FaultyClient`, when a single `DEAD_STREAM` or `NOT_SENT` fault is injected on each of statements 1–14 (PRD Section 6.3 table) of a `/query` or chat-UI request (parametrized, one case per statement), then the response equals the fault-free response and exactly one row per expected row lands.
- [ ] Given an `OUTCOME_UNKNOWN` fault injected **after** `admit_usage`, `charge_usage` and `append_chat_message` executed, when the request finishes, then `usage_daily.requests` and the token columns moved by exactly one call's worth and the transcript holds one message (never replayed).
- [ ] Given a request in flight when the database goes down (faults on every statement after step 4), when it finishes, then the response is released, the row is journaled, and after recovery and drain exactly one row with the original `timestamp` and `write_id` exists.
- [ ] Given `--run-chaos` (a new opt-in option in `tests/conftest.py`, skipped by default like `--run-benchmark`), when run, then real faults are exercised: `http://127.0.0.1:1` for connection refused and `docker restart harness-libsql-dev` under a live process for `invalid baton`, each absorbed or refused as the classifier says.
- [ ] Given `scripts/measure_usage_latency.py`'s method, when the healthy path is measured before and after (`main` vs epic), then the p50 added latency per request is under 0.5 ms, recorded in the report. The suite and `scripts/test-db-in-network.sh` stay green (the in-network runs are executed by the orchestrator/CI, not three times locally).

## Technical Notes

- Reuse STORY-003's `_FaultyClient` and STORY-010/011 helpers. Statements 2, 3, 11–14 are chat-UI / session paths: drive them through the same functions the chat UI calls (`_do_send` pieces or `chat_sessions` services) rather than a browser.
- `tests/conftest.py` `pytest_addoption` (`:144`): add `--run-chaos` and a `chaos` marker the same way `--run-e2e` is done. Chaos tests restart the shared dev server: they must never run in the default suite or in CI.
- Do not run the full suite locally (brief rule). The latency measurement may need its own script run; keep it short.
- Tests: `tests/test_db_resilience_mvp.py` (`db`), `tests/test_db_resilience_chaos.py` (`chaos`).

## Dependencies

- **Blocked by**: STORY-010, STORY-011
- **Blocks**: STORY-014

## PRD Reference

Source: [`PRD-018-db-resilience/PRD.md`](../../PRDs/PRD-018-db-resilience/PRD.md) — sections 1 (MVP goal), 11 (MVP definition, Quality indicators), 12 (Testing approach), 15 (D18)
