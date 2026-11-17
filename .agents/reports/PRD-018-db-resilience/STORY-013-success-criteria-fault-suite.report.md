---
story: STORY-013
prd: PRD-018
plan: .agents/plans/PRD-018-db-resilience/completed/STORY-013-success-criteria-fault-suite.plan.md
epic_branch: epic/PRD-018-db-resilience
commit: pending
status: COMPLETE
completed: 2026-11-17
---

# Implementation Report — STORY-013: Success-criteria suite (statements 1-14 under fault injection, outage end-to-end, opt-in chaos, latency)

**Plan**: `.agents/plans/PRD-018-db-resilience/completed/STORY-013-success-criteria-fault-suite.plan.md`
**Epic Branch**: `epic/PRD-018-db-resilience`
**Commit**: `pending`

## Summary

Tests and test infrastructure only; no application file changed. `tests/test_db_resilience_mvp.py` proves PRD Section 6.3 at the request level (15 cases, baseline + `DEAD_STREAM` + `NOT_SENT` each), the `OUTCOME_UNKNOWN`-after-the-effect-landed rule (admit, charge, append, plus an audit-row control), and an in-flight request across an outage (plain and breaker-open). `tests/test_db_resilience_chaos.py` adds two opt-in real-fault tests behind a new `--run-chaos` option and `chaos` marker. `tests/db_faults.py` gained `Fault.follows` (aim a commit fault at one statement) and `FaultScript.clear()` (the outage ends). No proof exposed a defect in the resilience code: every mvp case passed on its first run.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | `Fault.follows`, `FaultScript.clear()`, docstring | `tests/db_faults.py` | done |
| 2 | `--run-chaos` option, `chaos` marker, skip-loop entry, docstring | `tests/conftest.py` | done |
| 3 | pytester proof the marker is opt-in | `tests/test_chaos_marker.py` | done |
| 4 | 15 statement cases + 4 pure `follows`/`clear` tests | `tests/test_db_resilience_mvp.py` | done |
| 5 | 3 OUTCOME_UNKNOWN-after tests + 1 control | `tests/test_db_resilience_mvp.py` | done |
| 6 | in-flight outage test (2 parametrizations) | `tests/test_db_resilience_mvp.py` | done |
| 7 | two chaos tests + leave-the-server-running fixture | `tests/test_db_resilience_chaos.py` | done |
| 8 | latency, main vs epic (detached worktree, removed) | scratchpad only | done |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| Targeted run (13 files: new, marker/isolation, every file importing `db_faults`) | 419 passed, 2 skipped (the two chaos tests, no `--run-chaos`), 0 failed, 471 s |
| `test_db_resilience_mvp.py` alone | 25 passed (21 `db` + 4 pure), 235 s |
| `--run-chaos` | one run of both tests: the restart test passed, the refused-connection test failed on a test-wiring assumption (see Deviations); fixed, and that test alone re-run (no restart): passed. Dev server afterwards: `running paused=false` |
| Full suite | GitHub CI on push (user decision) |

Targeted files: `test_db_resilience_mvp`, `test_db_resilience_chaos`, `test_chaos_marker`, `test_e2e_marker`, `test_db_resilience_breaker`, `_drain`, `_faults`, `_release`, `_retry`, `_write_id`, `test_storage_status` (every `grep -l db_faults tests/*.py` hit besides `conftest.py`), `test_db_isolation_harness`, `test_conftest_fixtures`.

## AC coverage

| AC | Test | Result |
|----|------|--------|
| 1 statements 1-14 x {DEAD_STREAM, NOT_SENT} | `test_each_statement_is_absorbed_when_it_provably_did_not_run[s01..s14, s06a, s06b]` (15 ids). Each: response equal to fault-free, per-user row footprint equal, the fault fired exactly where aimed, a fresh client was built | pass |
| 2 OUTCOME_UNKNOWN after admit / charge / append | `test_a_landed_admit_is_counted_once_and_the_request_fails_closed`, `test_a_landed_charge_is_counted_once_and_the_answer_is_released`, `test_a_landed_append_is_one_message_not_two` (control: `test_a_landed_audit_row_is_replayed_to_the_same_row`) | pass |
| 3 in-flight request across an outage | `test_an_in_flight_request_across_an_outage_is_journaled_and_drains_to_one_row[plain, breaker_opened]`: 200, `audit_id` null, `audit_ref` = journal `write_id`, then one row with the original `timestamp` after drain | pass |
| 4 `--run-chaos` | `tests/test_chaos_marker.py` (4), `tests/test_db_resilience_chaos.py` (2, skipped by default, run once with the option) | pass |
| 5 latency < 0.5 ms | measured, see below: +0.04 ms code overhead against a local driver; not resolvable over the network on this host | see below |

## Latency (AC 5)

Method: `git worktree add --detach <scratchpad>/main-wt main`, interleaved main, epic, main, epic, one process at a time, 200 runs each, same `harness-libsql-dev`, never restarted between runs; worktree removed (`git worktree list` shows only the epic checkout). `scripts/measure_usage_latency.py` on the epic still reports one statement for admit and one for charge (the "no extra round trip" check). A scratchpad script (not committed) times the four storage calls a `/query` request makes: `find_user_by_token_hash`, `usage_limits.admit`, `usage_limits.charge`, `audit_logger.log_query`.

Host: Windows 11, Python 3.12.10, Docker Desktop dev server on 127.0.0.1:8080.

`scripts/measure_usage_latency.py --runs 200` (p50 / p95 ms):

| tree | admit | charge | admit + charge p50 |
|---|---|---|---|
| main #1 | 188.15 / 232.33 | 177.57 / 222.74 | 365.72 |
| epic #1 | 188.28 / 259.99 | 187.69 / 270.10 | 375.97 |
| main #2 | 188.15 / 262.76 | 177.76 / 280.97 | 365.91 |
| epic #2 | 166.26 / 200.08 | 165.80 / 210.48 | 332.06 |

Four storage calls per request, over the network, 200 runs, p50 ms (SUM = sum of the four p50s):

| tree | identity | admit | charge | audit | SUM p50 |
|---|---|---|---|---|---|
| main #1 | 4.005 | 183.126 | 177.313 | 178.030 | 542.47 |
| epic #1 | 4.335 | 180.997 | 177.962 | 178.393 | 541.69 |
| main #2 | 4.239 | 181.004 | 177.750 | 177.777 | 540.77 |
| epic #2 | 2.986 | 185.144 | 177.287 | 177.722 | 543.14 |

Mean SUM p50: main 541.62, epic 542.42, delta +0.80 ms, with a 1.70 ms spread between the two main runs. **Over this network the 0.5 ms budget cannot be resolved**: each write costs about 180 ms here (the Docker Desktop volume's commit), so the noise floor is above the budget, and the official script's own p50 swings by 20-30 ms between runs of the same tree.

To measure the code's own overhead (`_unit_of_work`, breaker `before()`/`record_success()`, counters, keyed audit insert) the same four calls were run against a local file database (`libsql.connect` patched to a temp file: no network, no Docker), 1000 runs, interleaved:

| tree | identity | admit | charge | audit | SUM p50 |
|---|---|---|---|---|---|
| main #1 | 0.169 | 5.023 | 5.023 | 5.404 | 15.619 |
| epic #1 | 0.174 | 4.987 | 4.927 | 5.344 | 15.432 |
| main #2 | 0.173 | 4.875 | 4.786 | 5.111 | 14.944 |
| epic #2 | 0.181 | 4.941 | 4.848 | 5.246 | 15.216 |

Mean SUM p50: main 15.28, epic 15.32, delta **+0.04 ms** (spread between the two main runs 0.68 ms; the identity read, the one call without a commit, moves by +0.005 ms). Verdict: the added healthy-path latency is well under 0.5 ms and not distinguishable from noise; the network measurement is reported as unresolvable rather than as a pass.

## Files Changed

| File | Action |
|------|--------|
| `tests/test_db_resilience_mvp.py` | CREATE |
| `tests/test_db_resilience_chaos.py` | CREATE |
| `tests/test_chaos_marker.py` | CREATE |
| `tests/conftest.py` | UPDATE (`--run-chaos`, `chaos` marker, skip-loop entry, docstring) |
| `tests/db_faults.py` | UPDATE (`Fault.follows`, `FaultScript.clear()`, docstring) |
| plan archive, story file, index, this report | `.agents/` |

## Deviations from Plan

- **Row 6a nth.** The plan's table says `nth` 2 for the refusal row and also says the fault is armed between the two requests; `nth` counts only matches after `add`, so the case uses `nth=1` (the `fired` assertion proves it hit the refusal row).
- **Append count.** The first send of a chat saves only its assistant bubble (no session yet when the user bubble is shown), so a two-send baseline is 3 appends, asserted in the append test.
- **Chaos test 1 (`127.0.0.1:1`).** The plan expected three `retry op=` lines. On this Windows host a refused connect takes about 2 s, not instant, so the retry deadline (D1, `reason=deadline`) stops the budget after one attempt. The test asserts the invariant instead: one `retry exhausted ... class=not_sent` line with 1-3 attempts, the breaker opening within five operations, the next refusal returning in under 0.5 s with no attempt and `retry_after_seconds >= 1`, and the Section 6.7 503 with no driver text. Found by the single `--run-chaos` run; only that test was re-run afterwards (no restart involved).
- **Chaos test 2** asserts "absorbed, or refused with `StorageUnavailableError`" for the first calls after the restart, and that `usage_daily.requests` is never above 1. It prints the retry lines (`-s`). It passed in the single run.
- **Latency.** Added a local-driver measurement because the network one cannot resolve 0.5 ms on this host. Nothing from the scratchpad is committed.
- `Fault.follows` uses the last `execute` on the same client; fine for the single-request scenarios here (documented in the `db_faults.py` docstring).

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_db_resilience_mvp.py` | 15 statement cases (`s01_identity` .. `s14_session_reread`, `s06a`, `s06b`); `follows` x3 and `clear` pure tests; 3 landed-OUTCOME_UNKNOWN tests + 1 control; in-flight outage x2 |
| `tests/test_chaos_marker.py` | skipped by default; `--run-chaos` runs and leaves others skipped; `--run-e2e` does not un-skip chaos; marker registered |
| `tests/test_db_resilience_chaos.py` | connection refused then breaker; server restart under a live client (both `chaos`) |

## Acceptance Criteria

- [x] AC 1: statements 1-14 under `DEAD_STREAM`/`NOT_SENT`, response and rows equal to fault-free
- [x] AC 2: `OUTCOME_UNKNOWN` after `admit_usage`, `charge_usage`, `append_chat_message` landed: never replayed
- [x] AC 3: in-flight outage: released, journaled, one row with original `timestamp` and `write_id` after drain
- [x] AC 4: `--run-chaos` / `chaos`, skipped by default; refused connection and server restart exercised once
- [x] AC 5: latency recorded: +0.04 ms code overhead (local driver); over the network unresolvable on this host (+0.80 ms inside a 1.7 ms spread). `scripts/test-db-in-network.sh` is the orchestrator's/CI's run
