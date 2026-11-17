---
id: STORY-005
prd: PRD-018
slug: circuit-breaker-and-storage-unavailable
title: Reusable CircuitBreaker class, the storage instance, StorageUnavailableError
type: technical
priority: high
complexity: medium
phase: "3 - Fail fast and say so"
status: todo
labels: [backend, storage]
epic_branch: epic/PRD-018-db-resilience
plan: null
report: null
commit: null
depends_on: [STORY-003]
blocks: [STORY-006, STORY-007, STORY-009, STORY-012]
skills: []
created: 2026-11-17
updated: 2026-11-17
---

# STORY-005: Circuit breaker and StorageUnavailableError

## Description

As a security admin, I want a process-local breaker that stops sending traffic to a database that is down and fails fast with a `StorageError` subclass, so that an outage is refused by the existing fail-closed arms and never waved through.

## Acceptance Criteria

- [ ] Given `app/services/circuit_breaker.py`, when `CircuitBreaker(name, failure_threshold, open_seconds, clock=time.monotonic, probe=None)` is driven with an injected clock, then pure tests cover `closed → open` after `failure_threshold` consecutive `record_failure()` calls, `before()` raising `BreakerOpen(retry_after_seconds)` while open (≥ 1, rounded up), `open → half_open` after `open_seconds`, and closing or reopening on the probe result. `record_success()` resets the count. `force_open(seconds)` opens immediately. `status()` returns a frozen `BreakerStatus(state, since, consecutive_failures, last_failure_class, retry_after_seconds)` with no lock, client or callable in it.
- [ ] Given `probe` set, when half-open, then exactly one caller runs the probe (under the breaker's own lock) while every other caller gets `BreakerOpen`. Given `probe=None`, when half-open, then exactly one live caller is admitted as the probe and the others get `BreakerOpen` until it records success or failure. A threaded test pins each mode.
- [ ] Given `database.py`, when it imports, then it holds exactly one `_storage_breaker = CircuitBreaker("storage", _BREAKER_FAILURE_THRESHOLD=5, _BREAKER_OPEN_SECONDS=10.0, probe=_probe_fresh_client)`. `_unit_of_work` calls `before()` first (open → `StorageUnavailableError(retry_after_seconds=...)` with **no** call to `_shared_client()`), `record_success()` on success, and `record_failure(cls)` once per **operation** that exhausted its retries on an infrastructure class. A `STATEMENT` failure leaves the count unchanged. A `NON_IDEMPOTENT` op refused a retry on `OUTCOME_UNKNOWN` counts exactly **once** (one operation, an infrastructure class), never once per refused retry.
- [ ] Given `app/db/errors.py`, when imported, then `StorageUnavailableError(StorageError)` carries `retry_after_seconds: int`, and exhausting the retry budget on an infrastructure class raises it with `retry_after_seconds=1` while the breaker is closed. With the breaker open, `check_duplicate` raises `DuplicateCheckError`, `usage_limits.admit` raises its fail-closed error, and `find_user_by_token_hash`'s `MissingRelationError` arm does not catch it, all with no code change in those modules (tests assert each).
- [ ] Given the half-open probe, when it runs, then it issues one `SELECT 1` on a brand-new client under `_client_lock`, never through `get_connection()` (the `_proved()` rule, `database.py:145-151`). On success the new client replaces the cached one. `init_db()` and `check_database_reachable()` bypass retry and breaker (D17). Every breaker transition writes exactly one structured log line (`breaker name=storage from=<s> to=<s> class=<c>`).

## Technical Notes

- `CircuitBreaker` is reused by PRD-022, one per upstream provider (PRD Section 15 "Cross-PRD consumers"): thresholds are constructor arguments with **no** defaults that encode storage's numbers; `force_open` exists even though storage does not use it; `last_failure_class` is a free string. PRD-019's `/ready` reads `status().state` and `retry_after_seconds`, so treat the `BreakerStatus` shape as a contract.
- `since` is wall-clock UTC in `_TIMESTAMP_FORMAT` (display only); the state machine uses the injected monotonic clock.
- `app/services/circuit_breaker.py` imports no settings and does no I/O (pure module); `database.py` translates `BreakerOpen` into `StorageUnavailableError`.
- Orchestrator decision (story creation): PRD Section 6.5 read "a `NON_IDEMPOTENT` operation refused retry on `OUTCOME_UNKNOWN` also leave[s] the count unchanged ... counted once", which contradicts itself. Resolved as "counts once" (it is an infrastructure failure, and a breaker blind to it would never open on an outage that only `admit_usage` sees). The PRD text is amended.
- `AuditUnavailableError` belongs to STORY-008. Do not add it here.
- Tests that use a real database must not leave the module breaker open for the next test: add an autouse fixture (or a reset in the storage fixtures in `tests/conftest.py`) that resets `_storage_breaker` between tests, and say so in the brief.
- Ingress mapping (503 + `Retry-After`) is STORY-006. This story stops at the exception.
- Tests: `tests/test_circuit_breaker.py` (pure), `tests/test_db_resilience_breaker.py` (`db` with `_FaultyClient` and a non-`db` part with PRD-014's no-driver-call guard asserting the open breaker issues no driver call).

## Dependencies

- **Blocked by**: STORY-003
- **Blocks**: STORY-006, STORY-007, STORY-009, STORY-012

## PRD Reference

Source: [`PRD-018-db-resilience/PRD.md`](../../PRDs/PRD-018-db-resilience/PRD.md) — sections 4 (Circuit breaker), 6.5, 7 (F4), 9.2 (T1, T10), 10 (Internal API), 15 (D6, D7, D17)
