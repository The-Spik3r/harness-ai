---
id: STORY-001
prd: PRD-018
slug: driver-failure-surface-spike
title: Driver failure-surface spike — verbatim errors, failing call, and the three open questions
type: spike
priority: high
complexity: small
phase: "1 - Measure the driver"
status: todo
labels: [backend, storage, spike]
epic_branch: epic/PRD-018-db-resilience
plan: null
report: null
commit: null
depends_on: []
blocks: [STORY-002]
skills: []
created: 2026-11-17
updated: 2026-11-17
---

# STORY-001: Driver failure-surface spike

## Description

As a platform operator, I want the driver's real failure text and the call that raised it captured live, so that every retry rule in this PRD rests on measured facts and not on guesses about `libsql==0.1.11`.

## Acceptance Criteria

- [ ] Given `harness-libsql-dev` reached from inside `harness-test-net` (the PRD-014 D5 recipe), when each fault is injected — connection refused (`http://127.0.0.1:1`), connect timeout (an unroutable address), `docker pause` mid-statement (read timeout), `docker restart` mid-transaction (`invalid baton`) and idle expiry (`STREAM_EXPIRED`) — then `.agents/spikes/PRD-018-driver-failure-surface.md` records, for each one, the fault, the call that raised (`connect` / `execute` / `fetchone` / `commit` / `rollback`), the verbatim message passed through `database._redacted()`, and whether the effect landed.
- [ ] Given a remote endpoint, when an `INSERT` runs and the client is abandoned without `commit()`, then the report says whether the row is durable (question 1: does the driver autocommit DML on a remote endpoint?).
- [ ] Given no open transaction, when `commit()` is called, then the report says whether it issues a network request and what it raises against a dead stream (question 2).
- [ ] Given a stream abandoned mid-transaction, when a fresh client writes to the same table, then the report says whether that write waits, fails with `TRANSACTION_TIMEOUT` (verbatim text), or succeeds, and how long it takes (question 3, Risk 3).
- [ ] Given the captures, when the report closes, then it contains a ready-to-paste fixture table `(message, phase, expected FailureClass)` for STORY-002, and states explicitly whether `DEAD_STREAM`@`commit` may move to `NOT_SENT` (PRD Phase 1 validation) and whether `TRANSACTION_TIMEOUT` is `NOT_SENT`.

## Technical Notes

- Spike only: the deliverables are the report and a throwaway capture script under `.agents/spikes/` (e.g. `PRD-018-driver-failure-surface.py`). No change under `app/` or `tests/`.
- Run the capture in a throwaway container on `harness-test-net`, as `scripts/test-db-in-network.sh` does (`docker run --network harness-test-net`, reaching `harness-libsql-dev:8080` by name). Host-side runs are allowed for comparison, but the classification must cite in-network evidence (PRD-014 spike: port-forwarding stalls muddy the result).
- `docker pause` / `docker restart harness-libsql-dev` interrupt the shared dev server. Run nothing else against it during the spike, and **always** leave it running and unpaused at the end (`docker unpause`, then a `SELECT 1` check).
- Use a scratch table (`prd018_spike_*`), never the application tables, and drop it at the end.
- Pass every message through `app.db.database._redacted()` before writing it to the report (PRD-014 rule: no credentials and no SQL in a report).
- Existing captures to reuse rather than re-derive: `app/db/database.py:405-418` (`STREAM_EXPIRED`, `invalid baton`), `:514-515` (connection refused), `.agents/spikes/PRD-014-docker-network-stalls.md` (`os error 10060` / `110`).
- If a fault cannot be produced reliably (e.g. a read timeout), say so and record what was observed. Do not invent text. An uncaptured class stays `OUTCOME_UNKNOWN` by the PRD's default rule.

## Dependencies

- **Blocked by**: None
- **Blocks**: STORY-002

## PRD Reference

Source: [`PRD-018-db-resilience/PRD.md`](../../PRDs/PRD-018-db-resilience/PRD.md) — sections 4 (Characterization), 6.2, 7 (F1), 12 (Phase 1), 14 (Risk 3), 15 (Assumptions)
