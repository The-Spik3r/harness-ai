---
story: STORY-001
prd: PRD-018
plan: .agents/plans/PRD-018-db-resilience/completed/STORY-001-driver-failure-surface-spike.plan.md
epic_branch: epic/PRD-018-db-resilience
commit: 07bd37f
status: COMPLETE
completed: 2026-11-17
---

# Implementation Report — STORY-001: Driver failure-surface spike

**Plan**: `.agents/plans/PRD-018-db-resilience/completed/STORY-001-driver-failure-surface-spike.plan.md`
**Epic Branch**: `epic/PRD-018-db-resilience`
**Commit**: `07bd37f`
**Findings report**: `.agents/spikes/PRD-018-driver-failure-surface.md`

## Summary

A throwaway capture script (host orchestrator plus in-container probes) produced every PRD Section 4 fault against
`libsql==0.1.11` and the local libSQL server except a Linux `os error 110`, and answered the three open questions.
No change under `app/`, `tests/`, `scripts/` or `docker-compose.yml`.

Headline results: Q1 DML is not durable before `commit()`; Q2 `commit()`/`rollback()` with no open transaction is a
local no-op that never raises; Q3 a fresh writer waits about 2.1 s (0.7 s behind a dead holder) then succeeds, and
`TRANSACTION_TIMEOUT` was never produced. V1 (DEAD_STREAM@commit -> NOT_SENT): yes, recommended. V2: not testable.
Extra findings: live connect text is `error trying to connect: tcp connect error: ...` (not the repo's `client error
(Connect)` wording); in-network connect timeout surfaces as `Connection refused (os error 111)` after 21 s; two new
restart-time server texts (503 `Namespace store has shutdown`, 404 `Namespace `default` doesn't exist`); no client
read timeout in 60 s of `docker pause`.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 0 | Record starting state | (Setup table in the findings report) | done |
| 1 | Capture script | `.agents/spikes/PRD-018-driver-failure-surface.py` | done |
| 2 | Smoke run (never-written false, committed true) | script | done |
| 3 | F1 refused, F2 connect timeout (in-network and host) | script | done |
| 4 | F3 pause a-d, F4 restart a-c, F5 idle a-e + control | script | done |
| 5 | Q1, Q2, Q3 (a, b, c) | script | done |
| 6 | Findings report with the STORY-002 fixture table and V1/V2 | `.agents/spikes/PRD-018-driver-failure-surface.md` | done |
| 7 | Restore and verify | script `host restore` | done |
| 8 | Diff check | git | done |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | OK |
| Tests | no new tests (spike); smoke `tests/test_conftest_fixtures.py -m db`: 16 passed |
| Full suite | GitHub CI on push (user decision) |
| E2E: restore round trip | server `running paused=false`, networks `bridge`, no `harness-test-net`, `SELECT 1` ok host and in-network, no `prd018_spike_%` table, `harness-ai-harness-ai-1` untouched |
| Reproducibility | 3 repeats per variant (F2 in-network 4); 1189 records, 0 SQL-elided, 0 hung, 0 aborted |

## Files Changed

| File | Action |
|------|--------|
| `.agents/spikes/PRD-018-driver-failure-surface.py` | CREATE |
| `.agents/spikes/PRD-018-driver-failure-surface.md` | CREATE |
| `.agents/plans/PRD-018-db-resilience/completed/STORY-001-...plan.md` | CREATE (archived plan) |
| `.agents/reports/PRD-018-db-resilience/STORY-001-driver-failure-surface-spike.report.md` | CREATE |
| `.agents/stories/PRD-018-db-resilience/STORY-001-...md`, `.agents/PRDs/PRD-018-db-resilience/index.md` | UPDATE (status, plan, commit) |

## Deviations from Plan

1. No `docker restart` graceful variant (all `-t 0`); the baton text matched `database.py:411` byte for byte.
2. `os error 110` not produced (see the findings report, Deviation 4); in-network F2 needed two URLs and ran as
   separate single-repeat discovery runs before the 3-repeat runs.
3. Harness fix mid-run: the driver panics (`BaseException`) on `in_transaction` after `close()`; the script now catches it.
4. `harness-test-net` was created by the spike and removed at restore, per the plan default.

## Tests Written

None (spike). Checks: reproducibility, AC checklist, restore checks, diff check.

## Acceptance Criteria

- [x] Each of the five faults recorded with the call that raised, verbatim `_redacted()` text and `landed` (os error 110 "not produced, observed: Connection refused (os error 111) after 21.0 s")
- [x] Q1 answered: not durable before `commit()`
- [x] Q2 answered: no network request, never raises with no transaction
- [x] Q3 answered: waits about 2.1 s, succeeds; `TRANSACTION_TIMEOUT` not produced
- [x] Fixture table `(message, phase, expected FailureClass)` plus V1 (yes) and V2 (not testable)
- [x] Dev server left running, unpaused, `SELECT 1` ok
- [x] No change under `app/` or `tests/`; `from app.main import app` OK
- [x] Follows existing patterns (re-raise wrapper, `_redacted()`, in-network recipe, PRD-014 report shape)
