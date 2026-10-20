---
story: STORY-017
prd: PRD-013-audit-and-usage-limits
plan: .agents/plans/PRD-013-audit-and-usage-limits/completed/STORY-017-two-instance-limits-and-latency.plan.md
epic_branch: epic/PRD-013-audit-and-usage-limits
commit: 5df7c69
status: COMPLETE
completed: 2026-10-20
---

# Implementation Report — STORY-017: Two-instance limit test and latency measurement

**Plan**: `.agents/plans/PRD-013-audit-and-usage-limits/completed/STORY-017-two-instance-limits-and-latency.plan.md`
**Epic Branch**: `epic/PRD-013-audit-and-usage-limits`
**Commit**: `5df7c69`

## Summary

`tests/test_two_instance_smoke.py` now proves PRD-013 T5 ("a second instance doubles the limit") end-to-end, using two real processes on one database:

- **Rate.** With a limit of 5, 10 requests alternated A, B, A, B… and all sent before any reply was read. Exactly 5 are admitted. The 5 refusals carry `limit="requests"`, `maximum=5` and the counts `actual` = 6, 7, 8, 9, 10, each exactly once, all with the same `resets_at`. Distinct counts under concurrency show the counter is one shared row changed atomically, not one counter per process.
- **Budget.** With a budget of 7 tokens (one answered query at the child stub's `tokens_used=7`), instance A answers once and instance B then refuses with `limit="tokens"`, `maximum=actual=7`, `resets_at` at the next 00:00 UTC. B never answered for this user, so the 7 can only have come from A's charge in the shared row.
- **Second user.** Admitted through both instances during and after each scenario.

`scripts/measure_usage_latency.py` times the two service calls, `usage_limits.admit` and `usage_limits.charge`, not the pipeline. It prints p50/p95 over a stated number of runs and checks which storage variant is in force before it reports.

## Measured numbers

**Variant measured: STORY-009 Path A.** `admit` is one `INSERT … ON CONFLICT … DO UPDATE … RETURNING` and `charge` is one `UPDATE usage_daily`. The upsert-plus-`SELECT` fallback (PRD Risk 2) was never built, so its cost doesn't appear here. The script observed one statement per call on every run.

**Local libSQL dev server** (`http://127.0.0.1:8080`, Docker container `harness-libsql-dev`, same host, Windows 11, Python 3.11.17). 50 timed runs per call after one discarded warm-up pair. p50 is the median; p95 is nearest-rank, `sorted[ceil(0.95·n)−1]`.

| Run | admit min | admit p50 | admit p95 | charge min | charge p50 | charge p95 | admit + charge p50 | admit + charge p95 |
|-----|-----------|-----------|-----------|------------|------------|------------|--------------------|--------------------|
| 1 (first run, Task 5) | 7.68 | 8.50 | 9.49 | 6.70 | 7.53 | 8.39 | 16.03 | 17.88 |
| 2 | 7.58 | 8.49 | 9.10 | 6.63 | 7.58 | 8.34 | 16.07 | 17.44 |
| 3 | 7.67 | 8.52 | 9.02 | 7.10 | 7.39 | 8.41 | 15.91 | 17.43 |
| 4 | 7.95 | 8.44 | 9.20 | 7.09 | 7.55 | 8.21 | 15.98 | 17.42 |

All figures are milliseconds. Each request pays about **8.5 ms for admit and 7.5 ms for charge (≈16 ms p50, ≈17.5 ms p95)**, for **2 added round trips per request** (3 → 5 statements, also pinned by `test_round_trip_cost_is_measured_and_reported`). Runs are consistent to within about 0.2 ms at p50. In the smoke test, a whole warm `POST /query` on this machine took about 45 ms in-process, so the counter is roughly a third of it. That figure is printed by the test and asserted nowhere. Same-host figures understate a remote endpoint, the same caveat STORY-011 and STORY-016 recorded.

**Remote endpoint: none was available.** This machine's `.env` points `DATABASE_URL` at the local dev server, `TURSO_AUTH_TOKEN` is empty, and no Turso CLI is installed. AC 4 allows this outcome. To record a remote figure later (STORY-018 or before deployment):

```bash
TURSO_AUTH_TOKEN=<token> PYTHONPATH=. python scripts/measure_usage_latency.py \
  --database-url libsql://<db>-<org>.turso.io --allow-remote-database --runs 50
```

The script writes one `usage_daily` row for a nonce-suffixed bench user and deletes it on exit.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Rate-window guard (`_db_second`, `_fresh_rate_window`) and helpers (`_insert_other_user`, `_usage_row`, `_is_usage_refusal`) | `tests/test_two_instance_smoke.py` | ✅ |
| 2 | Rate limit of 5 admits exactly 5 of 10 alternating requests (AC 1, AC 3) | `tests/test_two_instance_smoke.py` | ✅ |
| 3 | Budget exhausted through A is refused on B (AC 2, AC 3) | `tests/test_two_instance_smoke.py` | ✅ |
| 4 | Module docstring ("Four epics.") and invariant 1 names its one exception | `tests/test_two_instance_smoke.py` | ✅ |
| 5 | Latency script | `scripts/measure_usage_latency.py` | ✅ |
| 6 | Script tests | `tests/test_measure_usage_latency.py` | ✅ |
| 7 | Measure and write this report | this file | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ |
| Frontend lint | n/a. No UI surface and no frontend in this repo (Reflex `chat_ui/` untouched) |
| Python lint | n/a. No linter configured. `py_compile` on all three files ✅ |
| Related suites (smoke, script, usage_limits, usage_storage, pipeline usage limits) | ✅ 111 passed |
| Full suite (final code) | ✅ 3822 passed, 27 skipped |
| E2E | ✅ 7/7 (remote run: none available, as AC 4 allows) |

An earlier full run with `-x` hit one `STREAM_EXPIRED` in `tests/test_query_pipeline_audit_fields.py`. That is the known shared-DB flake (PRE-PRD-017), in a file this story doesn't touch. The file passed on rerun (38/38), and the full suite without `-x` was then green twice.

## E2E Results

| Check | Result |
|-------|--------|
| `pytest tests/test_two_instance_smoke.py -v` | 16 passed: the 14 existing scenarios untouched (AC 5), plus 2 new |
| Rate test alone, 3× with cold children | 3/3 passed, ~3.2 s each. The guard didn't trigger (starts at seconds 11, 15, 19) |
| Forced guard (`_FRESH_WINDOW_MARGIN_S = 60`, temporary copy) | Passed. The wait took about 28 s (started at second 30), under the ≤ 61 s ceiling |
| Mutation: instance B given its own per-process counter (temporary copy) | Rate test **failed** with `assert 8 == 5` (A admitted 3, B admitted 5). The test catches the T5 failure. The budget test still passed, as expected, since the mutation touches only the rate count |
| `measure_usage_latency.py --runs 50`, 3× | Numbers above, `1 statement` per call, Path A line, cleanup `1 row(s)` |
| Leftover rows `user_id LIKE 'story017-bench%'` | 0 |
| `--database-url https://x.turso.io` without the flag | Refused with the guard message, exit 1, no traceback (after deviation 2) |
| Remote run | None available (see above) |

Temporary copies were created in `tests/`, run, and deleted. None is committed.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `tests/test_two_instance_smoke.py` | UPDATE | +269/−2 |
| `scripts/measure_usage_latency.py` | CREATE | +421 |
| `tests/test_measure_usage_latency.py` | CREATE | +156 |

## Deviations from Plan

1. **Post-wait assertion in `_fresh_rate_window`.** The plan's `assert _db_second() < 60 - margin` was tied to the margin, so the plan's own forced-wait E2E (margin 60) could never have passed it. It now asserts what matters, `_db_second() < second` (the database's minute rolled over), which holds for any margin.
2. **The script guard also runs before the `app.` imports when invoked as a program.** E2E 6 showed that, without a token, `Settings()` rejected the remote URL first with a pydantic traceback, which hid the guard's message. The same holds for `measure_history_latency.py`, which wasn't changed. The guard still runs in `_measure_command`. Importing the module (as the tests do) does nothing at import. Pinned by `test_run_as_a_program_a_remote_endpoint_is_refused_before_settings_load`.
3. **`database.init_db()` at the start of a run.** This creates `usage_daily` on a database that predates STORY-009, and is a no-op otherwise. It also lets the script test run on the suite's freshly reset database.
4. **Mutation-check shape.** The plan suggested a per-process dict. In the version used, B still writes the shared row but reads its own count, so A sees B's attempts and B doesn't see A's. That gives 8 admitted, not 10. It's the same class of failure and it fails the same assertion.
5. **Additional script tests** beyond the plan's list: a refused admit aborts with exit 1 and prints no report; a changed statement count aborts with exit 1, prints no report and leaves no row; `--runs 0` is refused.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_two_instance_smoke.py` | `test_a_rate_limit_of_five_admits_five_of_ten_alternating_requests`, `test_a_budget_exhausted_through_instance_a_is_refused_on_instance_b` |
| `tests/test_measure_usage_latency.py` | import opens no connection (fresh interpreter); p95 is nearest-rank (n = 20, 50, 1); guard passes local hosts (×2); guard refuses remote unless allowed; as a program, a remote endpoint is refused before settings load; a short run reports both calls, the variant and 1 statement each, and cleans up; a refused admit ends the run without a report; a changed statement count ends the run without a report; zero runs refused (12 cases) |

## Acceptance Criteria

- [x] Given two application processes on one database and a user with a rate limit of 5, when 10 requests alternate between the processes within one minute, then exactly 5 are admitted and 5 return the usage-limit body.
- [x] Given a user whose budget is exhausted by requests through instance A, when the next request goes to instance B, then it is refused with `limit="tokens"`.
- [x] Given a second user during both scenarios, when they send through either instance, then they are admitted.
- [x] Given `python scripts/measure_usage_latency.py`, when it runs against the local libSQL dev server, then it prints p50 and p95 for `admit` and for `charge` over a stated number of runs, and the story report records those numbers plus one run against a remote endpoint (or states that none was available). **None was available, as stated above.**
- [x] Given the existing two-instance smoke scenarios, when the file runs, then they pass with no assertion changed.
- [x] All tasks completed
- [x] Follows existing patterns (harness pipe protocol; history-script bootstrap, `Samples`, guard)
- [x] Measured variant (Path A) stated in the script output and in this report

## Notes for STORY-018

- README figure: **2 added round trips per request; about 16 ms p50 / 17.5 ms p95 combined, local same-host**. Remote not yet measured. Use the command above.
- `USAGE_LIMITS_ENABLED=false` restores the 3-statement path. That is already asserted by STORY-011/012's tests.
