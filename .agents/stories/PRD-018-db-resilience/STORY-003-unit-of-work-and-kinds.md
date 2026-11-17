---
id: STORY-003
prd: PRD-018
slug: unit-of-work-and-kinds
title: _unit_of_work retry boundary, statement kinds on every database.py function, _FaultyClient harness
type: technical
priority: high
complexity: large
phase: "2 - Retry safely"
status: todo
labels: [backend, storage, tests]
epic_branch: epic/PRD-018-db-resilience
plan: null
report: null
commit: null
depends_on: [STORY-002]
blocks: [STORY-004, STORY-005]
skills: []
created: 2026-11-17
updated: 2026-11-17
---

# STORY-003: Retry at the unit of work

## Description

As a platform operator, I want each storage function to be re-run from the start on a fresh client when the failure shows that is safe, so that a single dead stream mid-request is absorbed instead of becoming a 500.

## Acceptance Criteria

- [ ] Given `_unit_of_work(name, kind, fn)`, when `fn` fails with a retryable class for its kind (Section 6.3 table: `READ`/`IDEMPOTENT` on `NOT_SENT`, `DEAD_STREAM`, `OUTCOME_UNKNOWN`; `NON_IDEMPOTENT` on `NOT_SENT` and `DEAD_STREAM` on `execute` only), then it runs `fn` again inside a fresh `_session()`, at most `_RETRY_MAX_ATTEMPTS = 3` times, with full-jitter backoff (≤ 50 ms before attempt 2, ≤ 200 ms before attempt 3), and starts no attempt more than `_RETRY_START_DEADLINE_SECONDS = 2.0` after the first. Pure tests with fake `fn`s, an injected sleep and an injected clock cover each kind × class cell.
- [ ] Given a `STATEMENT` failure, or a `NON_IDEMPOTENT` op failing with `OUTCOME_UNKNOWN` or `DEAD_STREAM`@`commit`, when it fails, then it is raised on the first attempt with no retry, as the same exception type as today.
- [ ] Given every public operational function in `database.py` (all `with _session() as conn:` blocks except `init_db()` / `check_database_reachable()`), when this story lands, then each one runs through `_unit_of_work` with the kind of PRD Section 6.3 (`admit_usage`, `charge_usage`, `append_chat_message`, `insert_user` are `NON_IDEMPOTENT`; `create_chat_session` is `IDEMPOTENT`, and an `IntegrityError(chat_sessions.session_id)` on a retry counts as success), with an unchanged signature and return value. A test pins the name → kind map against the module's function list, so a new function cannot skip it.
- [ ] Given a `db` test with `_FaultyClient` (a proxy installed by monkeypatching `libsql.connect`, built on PRD-014's `_RecordedClient` forwarding pattern), when a `DEAD_STREAM` or `NOT_SENT` text is raised **before** forwarding on the first matching `execute` of a `READ`, an `IDEMPOTENT` and a `NON_IDEMPOTENT` function, then each call returns the fault-free result. When an `OUTCOME_UNKNOWN` text is raised **after** forwarding on `admit_usage`, then `usage_daily.requests` moved by exactly 1 and the error propagates.
- [ ] Given each retry, when it happens, then exactly one `INFO` log line `retry op=<name> class=<class> attempt=<n>` is written, and an exhausted budget writes one `WARNING` line, both with redacted driver text and no SQL or parameters. `init_db()` keeps failing fast against an unreachable endpoint (`test_init_db_fails_fast_against_an_unreachable_endpoint` unchanged).

## Technical Notes

- `app/db/database.py`. Move each `with _session() as conn:` body into a local `def _op(conn): ...` passed to `_unit_of_work`. The retry boundary is the start of the block (D1). `_translated()` keeps its no-retry contract and its docstring.
- Constants on the `_IDLE_PROBE_AFTER_SECONDS` precedent (`:78-80`): `_RETRY_MAX_ATTEMPTS`, `_RETRY_START_DEADLINE_SECONDS`. These are not settings (O6, PRD-008 STORY-024 "no knob" rule).
- After a `DEAD_STREAM`, `_translated()` already dropped the client. Make sure the next attempt really gets a fresh one after `NOT_SENT` / `OUTCOME_UNKNOWN` too (an `OUTCOME_UNKNOWN` client may be half-dead): invalidate it in `_unit_of_work` before retrying, never inside `_translated()`.
- `_session().__exit__` runs `rollback()` on an exception. A rollback on a dead stream can itself raise and mask the original error. Make sure the classified exception is the statement's, not the rollback's (the STORY-001 report says what `rollback()` raises).
- Orchestrator decision (STORY-001 spike): `DEAD_STREAM`@`commit` is now `NOT_SENT` (PRD 6.2), so a `NON_IDEMPOTENT` op **is** retried after it; AC 2's "`DEAD_STREAM`@`commit`" no-retry case is superseded. `commit()`/`rollback()` with no open transaction never raise (spike Q2). There is no driver read timeout and a contended first write can take ~2.1 s: the 2 s start deadline still only gates *starting* an attempt (D5).
- Leave a hook for the breaker: STORY-005 adds `before()` / `record_success()` / `record_failure()` to `_unit_of_work`. Do not build the breaker here, and do not create `StorageUnavailableError` here.
- `summary_snapshot` (`:1498-1537`) has its own figure-by-figure fallback. Keep its behaviour and wrap the unit it already has.
- `_FaultyClient` lives in `tests/conftest.py` (or a helper module it imports) next to `_RecordedClient`, so STORY-004, STORY-005 and STORY-013 reuse it. It needs a script form such as "on the Nth `execute` whose SQL starts with `INSERT INTO usage_daily`, raise `ValueError(text)` before/after forwarding". Re-raise a real `ValueError` with the captured text, never a wrapper.
- The full statement-by-statement suite (statements 1–14 at the request level) is STORY-013. This story tests the loop and one function of each kind.
- Tests: `tests/test_db_resilience_retry.py` (pure loop) and `tests/test_db_resilience_faults.py` (`db`, `_FaultyClient`).

## Dependencies

- **Blocked by**: STORY-002
- **Blocks**: STORY-004, STORY-005

## PRD Reference

Source: [`PRD-018-db-resilience/PRD.md`](../../PRDs/PRD-018-db-resilience/PRD.md) — sections 6.1, 6.3, 6.6, 7 (F2), 12 (Testing approach), 15 (D1, D3, D5, D18)
