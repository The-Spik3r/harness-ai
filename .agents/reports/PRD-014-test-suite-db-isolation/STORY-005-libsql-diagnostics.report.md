---
story: STORY-005
prd: PRD-014
plan: .agents/plans/PRD-014-test-suite-db-isolation/completed/STORY-005-libsql-diagnostics.plan.md
epic_branch: epic/PRD-014-test-suite-db-isolation
commit: 16402fa
status: COMPLETE
completed: 2026-10-20
---

# Implementation Report — STORY-005: Driver recorder and a `libsql diagnostics` section with a verdict on every failing `db` test

**Plan**: `.agents/plans/PRD-014-test-suite-db-isolation/completed/STORY-005-libsql-diagnostics.plan.md`
**Epic Branch**: `epic/PRD-014-test-suite-db-isolation`
**Commit**: `16402fa`

## Summary

In a `db` test, `_storage_policy` wraps `libsql.connect` with `_recorded_connect()`. It does this through the test's own `monkeypatch`, after the session probe. Every client the wrapper returns is a `_RecordedClient`. The proxy forwards every attribute. For each method call it records duration, client number, idle time and any infrastructure marker, and it re-raises the driver's own exception object. `connect` is recorded too. Records go to the item in the module-level `_current`, not to the item that built the client. That pointer is set before `_reset_database()` and cleared in a `finally` at the fixture's teardown. As a result, a client cached by `_shared_client()` records into the test that uses it, and teardown calls from the test's own fixtures are recorded. `pytest_runtest_makereport` appends a `libsql diagnostics` section to any failed `setup`, `call` or `teardown` report of a `db` item. Two pure functions build the section: `_diagnostics()` and `_verdict()`, which follows the PRD 6.6 table. No `app/` file changed.

What a real failing `db` test now shows, against the live dev server (temporary E2E file, deleted afterwards):

```
----------------------------- libsql diagnostics ------------------------------
calls: 19 on 1 client, 1 connect
slowest: execute 0.016 s (client idle 0.00 s before)
over 10 s: none
driver errors: none
libsql verdict: no infrastructure signal (19 calls, slowest 0.02 s)
```

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 0 | Pre-flight and the timing without the recorder | — | ✅ 250 passed, 31.62 s / 32.74 s (clean runs) |
| 1 | `_Call`, `_RECORDS`, `_current`/`_begin`/`_end`/`_record`, `_infra_error`, `_verdict`, `_diagnostics` | `tests/conftest.py` | ✅ |
| 2 | `_RecordedClient`, `_recorded_connect` | `tests/conftest.py` | ✅ |
| 3 | Install in `_storage_policy`'s `db` branch, report section, docstrings | `tests/conftest.py` | ✅ 45 passed |
| 4 | In-process self-tests (21) | `tests/test_db_isolation_harness.py` | ✅ 50 passed |
| 5 | `pytester` child runs with a fake driver (6) | `tests/test_db_isolation_harness.py` | ✅ 56 passed |
| 6 | Timing with the recorder, plus the tests that patch `libsql.connect` and the `monkeypatch.undo()` tests | — | ✅ 250 passed, 31.37 s / 29.38 s; 11/11 spot tests |
| 7 | Full suite | — | ✅ 3,910 collected / 3,883 passed / 27 skipped, 0 failures |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import / frontend lint | n/a (test harness only, no `app/` or frontend change; `git diff main --stat -- app/` empty) |
| `test_db_isolation_harness.py` | ✅ 56 passed (29 before + 27 new) |
| `test_db_isolation_harness.py` + `test_conftest_fixtures.py` | ✅ passed after Task 3 (45) and after Task 5 |
| AC 5 timing pair, with and without the recorder | ✅ same counts, best-of-two 29.38 s vs 31.62 s (−7%, within 10%) |
| `-m "not db"`, libSQL container stopped | ✅ 2,613 passed, 26 skipped, 1,271 deselected in 77.6 s |
| Full suite, Docker running | ✅ 3,883 passed, 27 skipped in 360.9 s; no `libsql verdict` lines (nothing failed) |
| E2E | ✅ 5/5 |

### AC 5 timing detail

Command: `pytest tests/test_db.py tests/test_conftest_fixtures.py -q -p no:cacheprovider`

| Run | Without the recorder (Task 0) | With the recorder (Task 6) |
|-----|-------------------------------|------------------------------|
| 1 | 249 passed, 1 error, 47.36 s *(flake)* | 250 passed, 31.37 s |
| 2 | 1 failed, 249 passed, 53.86 s *(flake)* | 250 passed, 29.38 s |
| 3 | 250 passed, 31.62 s | — |
| 4 | 250 passed, 32.74 s | — |
| 5 | 249 passed, 1 error, 48.73 s *(flake)* | — |

The baseline runs that flaked each took about 15 s longer than the clean ones, which looks like a single libSQL stall. Those are the failures this story now labels. The comparison uses clean runs only. The 250 count is higher than the brief's 234 because PRD-013 added tests since.

### Full-suite counts against the baseline

STORY-004 carried the baseline forward as 3,883 collected / 3,856 passing / 27 skipped. This story adds 27 tests, all non-`db`: 3,910 / 3,883 / 27. That is exactly the result. `-m "not db"`: 2,612 + 27 = 2,639 = 2,613 passed + 26 skipped. `db` count unchanged at 1,271.

## End-to-End Tests

- [x] Child run: a failing `db` test shows the section and `libsql verdict: ` (`test_a_failing_db_test_reports_libsql_diagnostics`), and so does a real-server failing test (above).
- [x] Child run: a passing `db` test with `-rA` shows no section (`test_a_passing_db_test_has_no_section`), and so does the real-server passing test (`-rA`, exactly one verdict line in the log).
- [x] Child runs: `STREAM_EXPIRED` during call, a connect error during setup, and `STREAM_EXPIRED` during teardown each produce the right verdict.
- [x] `grep "libsql verdict"` over a run log finds one line per failing `db` test: one in the E2E log and zero in the full-run log (no failures).
- [x] `-m "not db"` is green with storage down.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `tests/conftest.py` | UPDATE | +212/−5 |
| `tests/test_db_isolation_harness.py` | UPDATE | +389/−3 |
| `.agents/plans/PRD-014-test-suite-db-isolation/completed/STORY-005-libsql-diagnostics.plan.md` | CREATE (archived) | +308 |

## Deviations from Plan

1. **The section is pure ASCII, so the verdict reads `likely infrastructure -- …` and the error count `1 x STREAM_EXPIRED`.** AC 3 and the PRD spell `—` and `×`. The plan (P6) kept the em dash and dropped only `→`. Task 5 then showed that cp1252 output breaks a UTF-8 reader on `×` (0xD7), and on `—` (0x97) too: `pytester` raised `UnicodeDecodeError` on the child's output. The same thing would happen to any log parser reading a `tee`d run. STORY-003 already set this precedent: `_UNDECLARED` writes `--` where PRD Section 10 has `—`. The `grep` prefix STORY-006 depends on (`libsql verdict: likely infrastructure`) is unchanged. The `_diagnostics` docstring records why.
2. **The libSQL container was stopped for the `-m "not db"` check instead of all of Docker Desktop.** From the tests' side it's the same (port 8080 closed), it was quicker, and the container was restarted straight after. STORY-004 already did the full Docker-Desktop-stopped run.
3. **Statements run on a raw `client.cursor()` are not timed.** Only the `cursor` call itself is recorded. Nothing in `app/` does that: `_Connection.cursor()` is the only caller, and the five other `.cursor()` sites are pass-through test or script proxies. The plan did not mention this, so it is noted here.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_db_isolation_harness.py` (in-process, 21) | the verdict for each of the four PRD 6.6 outcomes, plus `os error 10060`, error-beats-stall priority and the 9.99 s boundary; the full section, the quiet section and the empty section; marker labelling (`STREAM_EXPIRED`, `invalid baton`, `tcp connect error`, `os error 10060`) and no label for a statement error; no token, SQL or parameter in the section; plain attribute forwarding; the same exception object re-raised and recorded; a cached client recording into the test that uses it; no recording outside a `db` test; `connect` recorded on success and failure; `_end` of another item leaves the pointer |
| `tests/test_db_isolation_harness.py` (`pytester`, 6) | failing `db` test has the section; passing `db` test with `-rA` has none; `STREAM_EXPIRED` in call; connect error in setup, redacted; teardown failure recorded; failing non-`db` test has no section |

## Acceptance Criteria

- [x] Given a `db` test, when it runs, then every client `libsql.connect` returns is a `_RecordedClient` that forwards every attribute, times every method call (including `connect` itself) and re-raises the driver's **original** exception object. Calls are recorded into the *currently running* test's sink, including on a client built by an earlier test and cached by `_shared_client()`.
- [x] Given a `db` test that fails in `setup`, `call` or `teardown`, when its report is produced, then it has a `libsql diagnostics` section listing call and client counts, the slowest call (with the client's idle time before it), every call ≥ 10 s, every driver error matching `database._DEAD_STREAM`, `tcp connect error` or `os error 10060`, and a last line starting `libsql verdict: `. A passing test's report has no such section.
- [x] Given `_verdict(records)`, when unit-tested, then it returns the four outcomes in PRD Section 6.6's table. *(With `--` for `—`, deviation 1.)*
- [x] Given driver error text, when it is written into the section, then it has passed through `database._redacted()`, and the section contains no SQL text or parameters.
- [x] Given `tests/test_db.py` and `tests/test_conftest_fixtures.py`, when run with and without the recorder, then both pass with the same counts and within 10% of the same wall time. Tests that patch `libsql.connect` themselves and the seven `monkeypatch.undo()` sites still pass, and the full suite's counts equal STORY-001's baseline as carried forward.
