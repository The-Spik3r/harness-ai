---
id: STORY-002
prd: PRD-018
slug: classifier-and-phase-tracking
title: _classify(exc, phase), FailureClass and per-call phase tracking in _Connection
type: technical
priority: high
complexity: small
phase: "2 - Retry safely"
status: todo
labels: [backend, storage]
epic_branch: epic/PRD-018-db-resilience
plan: null
report: null
commit: null
depends_on: [STORY-001]
blocks: [STORY-003]
skills: []
created: 2026-11-17
updated: 2026-11-17
---

# STORY-002: Failure classifier and phase tracking

## Description

As a platform operator, I want every storage failure sorted into "never sent", "dead stream", "outcome unknown" or "statement refused", using both the message text and the driver call that raised it, so that the retry loop can tell a safe replay from a dangerous one.

## Acceptance Criteria

- [ ] Given every verbatim string in the STORY-001 report and in `database.py`'s comments, when `_classify(exc, phase)` runs, then a table test asserts the expected `FailureClass` (`NOT_SENT`, `DEAD_STREAM`, `OUTCOME_UNKNOWN`, `STATEMENT`) for each `(message, phase)` pair.
- [ ] Given an unrecognised `Hrana:` message, when classified, then the result is `OUTCOME_UNKNOWN`, never `NOT_SENT`. Given a dead-stream marker on `commit`, the result is `OUTCOME_UNKNOWN` unless STORY-001 proved otherwise (and then the orchestrator decision recorded in the PRD is cited).
- [ ] Given `IntegrityError` or `MissingRelationError` (or a duplicate-column failure), when classified, then the result is `STATEMENT`.
- [ ] Given a statement on the shared client, when the driver raises, then `_Connection` (and `_Cursor` for `fetch*`) records the failing call as the phase and re-raises **the same exception object**, so `_translated()` and `_is_dead_stream()` behave exactly as now. A test asserts `_translated()` still re-raises with no second `execute` (PRD Section 11).
- [ ] Given the healthy path, when the existing storage tests run (`tests/test_db.py` subset that covers `_translated`, the idle probe and STORY-024's AC 3), then they pass unchanged.

## Technical Notes

- `app/db/database.py`: `_classify` sits beside `_translated()` (`:593-628`), `_is_dead_stream()` (`:421-433`) and `_DEAD_STREAM` (`:418`): one seam for the driver's failure shape (PRD Section 6.10). `FailureClass` is a closed vocabulary (an `Enum` or `Literal`) whose string values are the lower-case names used in logs and in `storage_status()` (`not_sent`, `dead_stream`, `outcome_unknown`, `statement`).
- `_classify` is **pure**: a function of the exception and the phase only. No I/O, no settings, no client.
- How the phase reaches `_classify`: `_translated()` raises a `StorageError` built from the driver `ValueError`. Carry the phase on the raised `StorageError` (e.g. an attribute set where it is built) or keep it in a thread-local that `_unit_of_work` (STORY-003) reads. Choose the one that does not change `_translated()`'s docstring contract or the exception types/messages existing tests assert. `NOT_SENT` connect failures can also be raised from `_shared_client()` / `_proved()` while building a client: classify that path as phase `connect`.
- Thin wrapper only: record `"execute"`, `"fetchone"`, `"fetchall"`, `"commit"`, `"rollback"`, `"connect"`; do not wrap or replace the exception (the PRD-014 `_RecordedClient` rule, `tests/conftest.py:375`).
- Nothing calls `_classify` yet outside tests; STORY-003 wires it.
- Tests: a new `tests/test_db_resilience_classify.py` (non-`db`, pure).

## Dependencies

- **Blocked by**: STORY-001
- **Blocks**: STORY-003

## PRD Reference

Source: [`PRD-018-db-resilience/PRD.md`](../../PRDs/PRD-018-db-resilience/PRD.md) — sections 6.2, 7 (F2), 11 (Functional), 15 (D2)
