---
story: STORY-005
prd: PRD-018
plan: .agents/plans/PRD-018-db-resilience/completed/STORY-005-circuit-breaker-and-storage-unavailable.plan.md
epic_branch: epic/PRD-018-db-resilience
commit: pending
status: COMPLETE
completed: 2026-11-17
---

# Implementation Report — STORY-005: Reusable CircuitBreaker class, the storage instance, StorageUnavailableError

**Plan**: `.agents/plans/PRD-018-db-resilience/completed/STORY-005-circuit-breaker-and-storage-unavailable.plan.md`
**Epic Branch**: `epic/PRD-018-db-resilience`
**Commit**: `pending`

## Summary

New pure `app/services/circuit_breaker.py` (`BreakerStatus`, `BreakerOpen`, `CircuitBreaker`) with an injected clock and a pluggable half-open probe. `StorageUnavailableError(StorageError)` with `retry_after_seconds` in `app/db/errors.py`. `database.py` gains `_BREAKER_FAILURE_THRESHOLD = 5`, `_BREAKER_OPEN_SECONDS = 10.0`, `_probe_fresh_client()` and exactly one `_storage_breaker`, wired into `_unit_of_work` (entry `before()`, one `record_failure` per infrastructure-failed operation, `record_success`). An autouse conftest fixture gives every test a fresh breaker.

## Orchestrator rulings applied

1. A refused `NON_IDEMPOTENT` retry and an exhausted budget both raise `StorageUnavailableError` `from` the original `StorageError`, keeping its message. The breaker-open error carries fixed text with no driver text.
2. The half-open probe is claimed under the breaker's lock and run outside it; no thread holds both the breaker lock and `_client_lock`. Stated in the class and module docstrings (refines the AC's "holding the breaker's own lock").
3. The trial lease in `probe=None` mode is kept and documented as protecting PRD-022's per-provider breakers.
4. Transition logging lives in the class (stdlib logger): `breaker name=<n> from=<s> to=<s> class=<c>`.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | `StorageUnavailableError` | `app/db/errors.py` | done |
| 2 | `CircuitBreaker` | `app/services/circuit_breaker.py` | done |
| 3 | Constants, `_probe_fresh_client`, `_storage_breaker` | `app/db/database.py` | done |
| 4 | Three hooks in `_unit_of_work` + docstring | `app/db/database.py` | done |
| 5 | Pure tests P1-P13 | `tests/test_circuit_breaker.py` | done |
| 6 | Wiring tests N1-N8, B1-B6 | `tests/test_db_resilience_breaker.py` | done |
| 7 | Autouse fixture; two pinned assertions | `tests/conftest.py`, `tests/test_db_resilience_retry.py` | done |
| 8 | Targeted regression sweep | (see below) | done |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| Tests (new + changed + neighbours, one process) | 516 passed, 1 failed (`test_query_router.py::test_full_pipeline_latency_within_budget`, see note) |
| `tests/test_db.py` -k subset + isolation harness subset | 101 passed, 196 deselected |
| `tests/test_db_isolation_harness.py` alone | 56 passed |
| Full suite | GitHub CI on push (user decision) |

Note on the one failure: the benchmark asserts `/query` under 0.5 s and measured 0.58-0.63 s here. The same test fails identically on an untouched checkout of `HEAD` (0.559 s and 0.561 s in a temporary worktree), so it is this machine's dev-server latency (slowest commit 0.265 s), not this story. The breaker adds two uncontended lock acquisitions per operation.

## Files Changed

| File | Action |
|------|--------|
| `app/services/circuit_breaker.py` | CREATE |
| `app/db/errors.py` | UPDATE (+25) |
| `app/db/database.py` | UPDATE (+88/-11; `_translated()` untouched; CRLF kept) |
| `tests/conftest.py` | UPDATE (+33) |
| `tests/test_db_resilience_retry.py` | UPDATE (two assertions, import) |
| `tests/test_circuit_breaker.py` | CREATE (27 tests) |
| `tests/test_db_resilience_breaker.py` | CREATE (17 tests) |

## Deviations from Plan

- The probe `try` also wraps `libsql.connect` (plan note: lazy connect, but a raising connect is handled the same way).
- `BreakerOpen` is raised from the probe path after a failed probe with `retry_after` measured from the probe time.
- Test module reuses `_World`, `_UNIQUE`, `_NO_TABLE`, `_top_level_functions`, `_calls_to` from `tests/test_db_resilience_retry.py`.
- No other deviation.

## Acceptance Criteria

- [x] Pure state machine: P1-P10 (`tests/test_circuit_breaker.py`)
- [x] One probe caller, others refused; `probe=None` trial: P11, P12
- [x] Exactly one `_storage_breaker`; `before()` first with no `_shared_client()` call; one record per operation; STATEMENT neutral; refused NON_IDEMPOTENT counted once: N1, N2, N4, N5, B1, B3, B4
- [x] `StorageUnavailableError`, consumers unchanged: N3, N4
- [x] Probe on a new client under `_client_lock`, boot bypass (D17), one log line per transition: N6, N7, B2, B5, B6, P9
