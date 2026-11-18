---
id: STORY-001
prd: PRD-019
slug: readiness-settings-and-check-ready
title: Readiness settings and database.check_ready() — a bounded, breaker-neutral SELECT 1
type: feature
priority: high
complexity: medium
phase: "1 - Probes"
status: in-progress
labels: [backend, storage, config]
epic_branch: epic/PRD-019-multi-instance-deployment
plan: .agents/plans/PRD-019-multi-instance-deployment/STORY-001-readiness-settings-and-check-ready.plan.md
report: null
commit: null
depends_on: []
blocks: [STORY-002]
skills: []
created: 2026-11-17
updated: 2026-11-17
---

# STORY-001: Readiness settings and `database.check_ready()`

## Description

As a platform operator, I want a non-raising runtime readiness check that reads PRD-018's breaker and sends at most one bounded `SELECT 1`, so that a balancer can take an instance out of rotation without the probe traffic itself deciding the breaker.

## Acceptance Criteria

- [ ] Given `app/config.py`, when settings load, then `DRAIN_FILE` (default `/tmp/harness-drain`, must be a non-empty absolute path, POSIX or Windows — orchestrator decision: STORY-002 tests use a Windows tmp_path) and `READY_DB_TIMEOUT_SECONDS` (default `2.0`, `> 0` and `<= 10`) exist, and an invalid value fails at startup with a message that names the setting and the rule.
- [ ] Given `database.check_ready()`, when the breaker (`storage_status().breaker`) is `open` or `half_open`, then it returns a classification `breaker_open` carrying the breaker state and `retry_after_seconds` (minimum 1) and makes **no** driver call (asserted with a client spy).
- [ ] Given the breaker is `closed`, when `check_ready()` runs, then it sends one `SELECT 1` outside `_unit_of_work` on a single-slot executor with a deadline of `READY_DB_TIMEOUT_SECONDS`; success → `ready`; `DatabaseAuthError` from `_classify_startup_failure` → `database_auth`; anything else, including the deadline → `database_unreachable`. It never raises, and it logs the detail at `WARNING` with no token.
- [ ] Given a probe is still stuck (blackholed endpoint), when `check_ready()` is called again, then it returns `database_unreachable` without starting a second statement, and every call returns within `READY_DB_TIMEOUT_SECONDS + 0.5 s`.
- [ ] Given the breaker with an injected clock, when a hundred `check_ready()` failures occur, then `consecutive_failures` is unchanged; when the breaker is open and `check_ready()` would succeed, then the breaker stays open (no `record_success`, no `record_failure`, no retry).

## Technical Notes

- Runtime twin of `check_database_reachable()` (`app/db/database.py:750`), which stays the boot guard unchanged (PRD Section 6.5). Reuse `_classify_startup_failure` (`database.py:720`) and `_safe_endpoint`.
- Breaker contract: `BreakerStatus(state, since, consecutive_failures, last_failure_class, retry_after_seconds)` in `app/services/circuit_breaker.py:62`; `retry_after_seconds` is 1 while half-open.
- Return a small frozen dataclass or closed-vocabulary value (`ready | draining | breaker_open | database_unreachable | database_auth`); `draining` is decided by the route (STORY-002), not here, but the vocabulary may live here.
- The single-slot executor is process-wide; an abandoned future keeps the slot "busy" until the driver call returns.
- Tests: `tests/test_db_check_ready.py` (or the existing DB test module's naming) with the libSQL dev server for the happy path and a blackholed URL (e.g. a non-routable address / a local socket that accepts and never answers) for the deadline.
- Files: `app/config.py`, `app/db/database.py`, new tests; `tests/test_config*.py` for the validators.

## Dependencies

- **Blocked by**: None
- **Blocks**: STORY-002

## PRD Reference

Source: [`PRD-019/PRD.md`](../../PRDs/PRD-019-multi-instance-deployment/PRD.md) — Sections 4 (Readiness), 7 F1, 9.3, 11; decisions D3, D5
