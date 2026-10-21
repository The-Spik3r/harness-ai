---
story: STORY-007
prd: PRD-014
plan: .agents/plans/PRD-014-test-suite-db-isolation/completed/STORY-007-docs-and-regression-sweep.plan.md
epic_branch: epic/PRD-014-test-suite-db-isolation
commit: 57a534c
status: COMPLETE
completed: 2026-10-21
---

# Implementation Report — STORY-007: README and conftest docstring for the db split, plus a three-run regression sweep

**Plan**: `.agents/plans/PRD-014-test-suite-db-isolation/completed/STORY-007-docs-and-regression-sweep.plan.md`
**Epic Branch**: `epic/PRD-014-test-suite-db-isolation`
**Base of this story**: `f39903a` (STORY-006 chore)
**Commit**: `57a534c`

## Summary

- **README *Running Tests*** now covers:
  - the run modes: `pytest tests/` (the default, needs the server), `-m "not db"` (no Docker), `-m db`, and `--collect-only -q -m db`
  - what makes a test `db`
  - what the guard's "reached storage ... without declaring it" failure means, and its three fixes in order of preference
  - an example `libsql diagnostics` section, identical to what `_diagnostics()` renders, and a verdict table (what each verdict means and what to do)
  - a short paragraph pointing at the D5 in-network command, because STORY-006 concluded *confirmed*

  The in-container block and its three warnings are unchanged. *Requirements* now says the libSQL server is needed only for the storage tests.
- **`tests/conftest.py`'s module docstring**: "Where isolation comes from now" describes the marker, the `db`-only reset, the guard and the lazy endpoint, plus one sentence on the diagnostics, and no longer suggests every test is reset. No code line changed.
- **Regression sweep: three consecutive full runs, each 3,910 collected / 3,883 passing / 27 skipped** once flakes count as passes. That is STORY-001's 3,854 / 3,827 / 27 plus the epic's 56 harness tests.
  - Three failures in total, all in `db` tests. Each carries `libsql verdict: likely infrastructure -- execute took 21.0x s and ended in tcp connect error`, and each passes alone.
  - No failure had `no infrastructure signal`. No non-`db` test failed.
- **Census plugin rerun** (STORY-001's instrument, two documented deltas): **0 driver calls from non-`db` tests**, and **47,903 per full run**, against STORY-001's 52,980 (−5,077, −9.6%).
- **Diffs**: `git diff main` over the six PRD-006 suites, and over `app/` and `chat_ui/`, is empty across the epic.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 0 | Pre-flight: branch, container, no other pytest, collection counts, keep-awake wrapper | scratch `sweep.ps1` | ✅ |
| 1 | Module docstring: "Where isolation comes from now", "Running the `db` tests needs ..." | `tests/conftest.py` | ✅ |
| 2 | README *Running Tests* (four commands, guard, diagnostics, D5) and *Requirements* | `README.md` | ✅ |
| 3 | Stale-text grep | — | ✅ (1 expected hit, see below) |
| 4 | Three-run regression sweep | scratch `run{1,2,3}.{log,xml}` | ✅ |
| 5 | Scratch census plugin rerun | scratch `storage_census.py`, `census.json`, `analysis.md`, `db_split.py` | ✅ |
| 6 | Docker-free `-m "not db"` on the final tree (dead endpoint) | scratch `notdb.log` | ✅ |
| 7 | Diff checks and the Section 11 checklist | this report | ✅ |
| 8 | Commits | `57a534c` + chore | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ OK |
| Frontend lint | n/a (no `frontend/` in this repo, no UI change) |
| Docstring-only diff in `tests/conftest.py` | ✅ one hunk, lines 20-46, inside the module docstring |
| `test_db_isolation_harness.py` + `test_conftest_fixtures.py` after the docstring edit | ✅ 72 passed in 11.8 s |
| README diff | ✅ only two lines removed (the single `pytest tests/ -v` and the old *Requirements* line). No line of the in-container block or the collection-error paragraph changed |
| Guard message quoted in README = real output | ✅ throwaway non-`db` test calling `database.list_audit_logs()` printed the same four lines (`app/db/database.py:get_connection` as the frame) |
| Example diagnostics section = real output | ✅ `_diagnostics()` on matching synthetic `_Call` records renders the README's five lines byte for byte (CR-stripped diff) |
| Three full runs | ✅ 3,910 / 3,883 / 27 each, apart from flakes (table below) |
| Census plugin run | ✅ 3,883 passed / 27 skipped; non-`db` calls 0 |
| `-m "not db"` with `HARNESS_TEST_LIBSQL_URL=http://127.0.0.1:9` | ✅ 2,613 passed, 26 skipped, 1,271 deselected, 0 failed in 78.1 s; no "unreachable" exit |
| `tests/test_untouched_app.py` | ✅ 9 passed (alone), and passed inside all four full runs |
| Tests written | n/a, see *Tests Written* |
| E2E | ✅ 6/6 (below) |

## Environment

| Item | Value |
|---|---|
| Python | 3.11.17 (`C:\Users\tobip\.venvs\harness-ai`) |
| pytest | 9.1.1 |
| libsql | 0.1.11 |
| libSQL server | `ghcr.io/tursodatabase/libsql-server@sha256:6dd3eb27…3a67`, container `harness-libsql-dev` at `http://127.0.0.1:8080` (up 5 h at start) |
| Docker Desktop | engine 29.9.1 |
| Other pytest sessions on the container | None (process list: only the markitdown MCP server's two `python.exe`) |
| Sleep | Each run wrapped in `SetThreadExecutionState(ES_CONTINUOUS \| ES_SYSTEM_REQUIRED)`. No Kernel-Power 42/107/506/507 event between 00:52 and 01:10 |
| Collection | 3,910 tests. `-m db` 1,271, `-m "not db"` 2,639 |
| Command (each full run) | `python -m pytest tests/ -q -rfEs -p no:cacheprovider --junitxml=<scratch>/runN.xml`, output to `<scratch>/runN.log` |
| Scratch directory | `C:\Users\tobip\AppData\Local\Temp\prd014-story007\` (outside the repo, not committed) |

## Regression sweep (AC 3)

Three consecutive runs on `57a534c`'s tree (the docs edits were in the working tree; the commit came after), 00:52 to 01:09.

| Run | Collected | Passed | Failed | Errors | Skipped | Wall (pytest) | After flakes |
|---|---:|---:|---:|---:|---:|---:|---|
| 1 | 3,910 | 3,881 | 1 | 1 | 27 | 354.1 s | 3,883 passing ✅ |
| 2 | 3,910 | 3,883 | 0 | 0 | 27 | 307.7 s | 3,883 passing ✅ |
| 3 | 3,910 | 3,882 | 1 | 0 | 27 | 334.3 s | 3,883 passing ✅ |
| STORY-001 baseline + 56 | 3,910 | 3,883 | — | — | 27 | 339.6 s (Run A) / 302.4 s (Run B) | — |

Every failure, with its verdict line pasted from the log:

| Run | Nodeid | Phase | Error | Verdict line | Alone |
|---|---|---|---|---|---|
| 1 | `tests/test_db.py::test_prd013_fields_round_trip` | setup | `StorageError: Hrana: http error: error trying to connect: tcp connect error: A connection attempt failed because the connected party did not properly respond after a period of time ...` | `libsql verdict: likely infrastructure -- execute took 21.06 s and ended in tcp connect error` | 1 passed |
| 1 | `tests/test_integration.py::test_admin_route_accepts_valid_token[/audit]` | call | same `tcp connect error` | `libsql verdict: likely infrastructure -- execute took 21.03 s and ended in tcp connect error` | 1 passed |
| 3 | `tests/test_manage_users_cli.py::test_issue_token_rotates_credential` | call | same `tcp connect error` | `libsql verdict: likely infrastructure -- execute took 21.06 s and ended in tcp connect error` | 1 passed |

The full sections:

```
# run 1, test_prd013_fields_round_trip (setup)
calls: 16 on 1 client, 0 connects
slowest: execute 21.062 s (client idle 0.00 s before) -> tcp connect error
over 10 s: execute 21.062 s
driver errors: 1 x tcp connect error
libsql verdict: likely infrastructure -- execute took 21.06 s and ended in tcp connect error

# run 1, test_admin_route_accepts_valid_token[/audit] (call)
calls: 33 on 1 client, 0 connects
slowest: execute 21.031 s (client idle 0.00 s before) -> tcp connect error
over 10 s: execute 21.031 s
driver errors: 1 x tcp connect error
libsql verdict: likely infrastructure -- execute took 21.03 s and ended in tcp connect error

# run 3, test_issue_token_rotates_credential (call)
calls: 56 on 1 client, 0 connects
slowest: execute 21.063 s (client idle 0.00 s before) -> tcp connect error
over 10 s: execute 21.063 s
driver errors: 1 x tcp connect error
libsql verdict: likely infrastructure -- execute took 21.06 s and ended in tcp connect error
```

`grep -c "libsql verdict"`: run 1 → 2, run 2 → 0, run 3 → 1. These equal the failure counts, so every `db` failure carried a section, and no passing test got one. The three tests were also rerun together, outside a full run: 3 passed.

**Verdict on AC 3: met.** Every failure is `likely infrastructure`. None is `no infrastructure signal`, and no non-`db` test failed.

**Wall time against STORY-001.**
- The median of the three runs is 334.3 s, under Run A's 339.6 s. The fastest, 307.7 s, is near Run B's 302.4 s.
- Run 1 is 14.5 s slower than Run A. It contains two 21 s stalls (≈42 s), which accounts for that and more.

## Driver calls on the final tree (AC 4)

STORY-001's appendix instrument was rebuilt by extracting both code blocks from its report verbatim, then applying only the two deltas in plan P7. The `diff` against the extracted appendix text:

```
28c28
< POLICY = {"_never_the_configured_database": "reset", "_libsql_endpoint": "endpoint"}
---
> POLICY = {"_storage_policy": "reset", "_libsql_endpoint": "endpoint"}
128a129
>             "db": item.get_closest_marker("db") is not None,
```

`analyze.py` is unchanged. A new scratch `db_split.py` sums `census.json` calls by the `db` flag and lists every non-`db` test with ≥ 1 call. Run at 01:10-01:15 with keep-awake: **3,883 passed, 27 skipped in 318.8 s**, the same counts as the sweep, so the instrument changed nothing. Its terminal line: `storage_census: 47903 driver calls (47903 round trips)`.

| Bucket | STORY-001 (`728dd60`) | STORY-007 (final tree) | Change |
|---|---:|---:|---:|
| reset | 18,014 | 12,898 | −5,116 |
| test | 34,964 | 35,003 | +39 |
| endpoint | 2 | 2 | 0 |
| **total per run** | **52,980** | **47,903** | **−5,077 (−9.6%)** |

| Kind of test | Tests | Driver calls |
|---|---:|---:|
| `db` | 1,271 | 47,903 |
| not `db` | 2,639 | **0** |
| outside any test | — | 0 |

`not-db tests with >= 1 call: 0`.

Where the figures come from:
- **The drop is the resets STORY-001 predicted would go.** It counted 5,838 resets on no-fixture tests. The 2,639 non-`db` tests now get none.
- **What remains is the `db` share.** STORY-001's storage-fixture share was 47,044, against 47,903 now. The difference is the 7 `_DB_NODEIDS` tests and the 1 explicit-marker harness test (8 tests, now reset), plus the `db` harness tests added by the epic.
- **The `db` count breaks down as 1,263 by storage fixture + 8 by `_DB_NODEIDS` or marker = 1,271.** The 8 are `test_admin_auth.py::test_incorrect_bearer_token_rejected[/fake-audit]` and `[/fake-stats]`, `test_db.py::test_init_db_fails_fast_against_an_unreachable_endpoint`, `test_main.py::test_lifespan_fails_when_the_database_is_unreachable`, the three `test_measure_usage_latency.py` tests, and `test_db_isolation_harness.py::test_a_db_test_runs_on_the_endpoint_against_an_empty_database`.

**Limits of this measurement.**
- In a non-`db` test the guard replaces `libsql.connect` over the plugin's wrapper, and replaces `_shared_client` too. An attempted call would be refused, never counted, and would fail the test.
- So the zero rests on two facts together: the census records no non-`db` call, and the run is green. A green run means no guard fired.
- `pytester` children and other subprocesses are out of process and are not counted, as in STORY-001.

Flake-signature calls in this run, all absorbed or intended:
- two intended `tcp connect error`s against `http://127.0.0.1:1` (2.03 s each, `test_db.py` / `test_main.py`)
- two fast `STREAM_EXPIRED`s in `reset`, which `_reset_database()`'s one retry absorbed (`test_duplicate_characterization.py::test_pre_prd009_openrouter_failure_row_blocks_same_prompt_retry`, `test_pipeline_concurrency.py::test_health_answers_while_ten_query_calls_are_blocked`; both passed)

The slowest call in the run was 2.031 s. There was no stall ≥ 10 s.

## Docker-free run on the final tree

`HARNESS_TEST_LIBSQL_URL=http://127.0.0.1:9 python -m pytest tests/ -m "not db" -q -p no:cacheprovider` gave **2,613 passed, 26 skipped, 1,271 deselected in 78.1 s**, exit 0, with no "unreachable" message. That matches STORY-005's container-stopped run exactly (2,613 / 26 / 1,271, 77.6 s). The dead endpoint is stricter than a stopped container. `DATABASE_URL` was unset in the shell, so `conftest.py`'s `setdefault` points it, and every child that inherits it, at the dead port. `scripts/spike_pii_placeholders.py`'s import-time rewrite reads `HARNESS_TEST_LIBSQL_URL` too, so it does the same. `harness-libsql-dev` was left running, because other sessions share it (plan P9).

## Stale-text grep

```
$ grep -rn --include=*.py --include=*.md "_never_the_configured_database\|every test starts on an empty database" tests README.md
tests/conftest.py:577:    Until PRD-014 STORY-003 this fixture was `_never_the_configured_database`,
```

The one hit is the history sentence in `_storage_policy`'s docstring (plan P6): "Until PRD-014 STORY-003 this fixture was ..., and it reset the database before every test". It describes the past, so it is not stale. A wider grep for "before each/every test" and "reset ... every test" in `README.md` and `tests/conftest.py` returns only its continuation line 578.

## PRD Section 11 checklist (AC 5)

### MVP definition

- [x] `pytest -m "not db"` passes with Docker Desktop stopped. STORY-004 report (*Results*: Docker Desktop stopped, 2,586 passed / 26 skipped / 0 failed, 60 s); STORY-005 report (*Validation*: container stopped, 2,613 passed); this report, *Docker-free run on the final tree*.
- [x] Every non-`db` test issues zero in-process driver calls, enforced by the guard on every run. The enforcement is `_storage_policy`'s non-`db` branch (`tests/conftest.py`), tested by `test_a_test_that_is_not_db_has_both_patch_points_refused`, `test_a_direct_libsql_connect_is_refused_and_names_the_test` and `test_a_client_cached_by_an_earlier_test_is_not_lent`. Measured here as 0 of 47,903 (*Driver calls on the final tree*).
- [x] A test that reaches storage without declaring it fails with a message naming it and what to add. `test_the_refusal_names_the_test_the_frame_and_every_way_to_declare` and `test_reaching_storage_undeclared_fails_once_with_the_whole_message`; the throwaway check in *Validation Results*; STORY-003 report.
- [x] Every `db` failure (setup, call or teardown) carries a `libsql diagnostics` section ending in a verdict line. `test_a_failing_db_test_reports_libsql_diagnostics`, `test_a_connect_error_in_setup_is_classified_and_redacted` (setup), `test_a_dead_stream_during_the_call_is_classified_as_infrastructure` (call), `test_a_teardown_failure_records_the_teardowns_calls` (teardown). In this sweep, 3 of 3 real failures (1 setup, 2 call) carried one.
- [x] Total and passing counts equal STORY-001's baseline, and no assertion in any pinned suite changes. *Regression sweep*: 3,910 / 3,883 / 27 = 3,854 / 3,827 / 27 + the 56 harness tests. The six-suite `git diff main` is empty (*Diff checks*).
- [x] Driver calls per full run drop from STORY-001's figure to the `db` tests' own share, measured with the same plugin. 52,980 → 47,903, of which non-`db` is 0 (*Driver calls on the final tree*).

### Functional requirements

- [x] `db` is registered, so `--strict-markers` accepts it, and `pytest --markers` lists it. `pytest --markers` prints `@pytest.mark.db: reaches storage (a storage fixture, or listed in _DB_NODEIDS); applied at collection`. `pytest --collect-only -q --strict-markers -m db tests/` collects 1,271 with no error (run in this story).
- [x] Marking is identical with and without `--run-benchmark`. The sorted `--collect-only -q -m db` nodeid lists with and without the flag are byte-identical (1,271 each, `cmp`, run in this story); STORY-002 report.
- [x] A test requesting a storage fixture only transitively is marked. `test_a_fixture_built_on_temp_db_marks_its_test`.
- [x] `git diff main` over the six PRD-006 suites is empty at the epic's end. *Diff checks*.
- [x] `tests/test_untouched_app.py` passes. 9 passed alone, and inside all four full runs.
- [x] The guard's exception is not caught by `except Exception`, and an access swallowed by `except BaseException` or made in a worker thread still fails the test at teardown. `test_the_refusal_is_not_caught_by_except_exception`, `test_an_except_exception_in_the_test_does_not_swallow_the_refusal`, `test_an_access_swallowed_by_except_baseexception_fails_at_teardown`, `test_an_access_in_a_worker_thread_fails_at_teardown`.
- [x] A client cached by a `db` test is never lent to a non-`db` test. `test_a_client_cached_by_an_earlier_test_is_not_lent`.
- [x] `_reset_database()`'s dead-stream retry and its three tests in `test_conftest_fixtures.py` are unchanged and pass. `_reset_database` and `_drop_every_table_and_index` have identical bodies on `main` and the final tree (diffed in this story). The epic's only edit to `test_conftest_fixtures.py` is one docstring in `test_factory_yields_a_distinct_url_on_every_call`. `test_reset_recovers_from_a_stream_expired_between_probe_and_statement`, `test_reset_still_raises_a_failure_that_is_not_a_dead_stream` and `test_reset_retries_once_not_in_a_loop` passed in Task 1 (72 passed) and in every full run.
- [x] Diagnostics re-raise the driver's original exception object. `test_the_proxy_reraises_the_drivers_own_exception_and_records_it`, `test_a_failed_connect_is_recorded_and_reraised_unchanged`.
- [x] Diagnostics never print SQL or parameters, and error text is redacted. `test_the_section_carries_neither_the_token_nor_sql`, `test_a_statement_error_gets_no_label`, `test_a_connect_error_in_setup_is_classified_and_redacted`.
- [x] A passing test's report has no diagnostics section. `test_a_passing_db_test_has_no_section`, `test_a_failing_test_that_is_not_db_has_no_section`. Run 2 (green) printed 0 sections.

### Quality indicators

- [x] `-m "not db"` wall time recorded in STORY-004. 60 s there (2,612 tests), 77.6 s in STORY-005, 78.1 s here (2,639 tests), against ~5-6 min for a full run.
- [x] Full-run wall time not worse than STORY-001's baseline. The median of three is 334.3 s, against Run A's 339.6 s. One run of three (354.1 s) was slower, and it contained two 21 s stalls (*Regression sweep*). Ticked on the median; the slower run is stated, not hidden.
- [x] Three consecutive full runs in STORY-007: every failure carries `libsql verdict: likely infrastructure`, and none is `no infrastructure signal`. *Regression sweep*: 3 of 3.
- [x] Spike report states a conclusion with stall counts for both arms. `.agents/spikes/PRD-014-docker-network-stalls.md` and PRD Appendix *D5 result*: confirmed, 0 in-network vs 2 host.

### Diff checks

```
$ git diff --stat main -- app chat_ui                       # (empty)
$ git diff main -- tests/test_admin_auth.py tests/test_audit_router.py tests/test_stats_router.py \
    tests/test_db.py tests/test_route_reservations.py tests/test_chat_state.py | wc -l
0
$ git diff --stat main -- tests
 tests/conftest.py                  | 461 +++++++++++++++++++++-
 tests/test_chat_shell.py           |   3 +
 tests/test_conftest_fixtures.py    |   7 +-
 tests/test_db_isolation_harness.py | 788 +++++++++++++++++++++++++++++++++++++
 tests/test_migrate_to_turso_cli.py |   2 +-
```

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `README.md` | UPDATE | +44/-2 |
| `tests/conftest.py` | UPDATE (module docstring only) | +25/-9 |
| `.agents/reports/PRD-014-test-suite-db-isolation/STORY-007-docs-and-regression-sweep.report.md` | CREATE | this file |
| `.agents/plans/PRD-014-test-suite-db-isolation/completed/STORY-007-docs-and-regression-sweep.plan.md` | CREATE + MOVE | archived |
| `.agents/stories/…/STORY-007-docs-and-regression-sweep.md`, `.agents/PRDs/…/index.md`, `PRD.md` | UPDATE | status, report, commit; PRD Section 11 ticks (plan P10) |

No file under `app/`, `chat_ui/` or `scripts/` changed. The scratch files stay in `%TEMP%\prd014-story007\`.

## Deviations from Plan

1. **`-m db` count is 1,271, not the plan's guess of "~1,297".** The guess misread STORY-005's "1,271 deselected" (by `not db`), which *is* the `db` count. Nothing depends on it.
2. **The sweep ran from a PowerShell keep-awake script (`sweep.ps1`), not the plan's bash `for … | tee` loop.** The pytest arguments are the same. Output went through `cmd /c … > runN.log 2>&1`, because a PowerShell pipe would re-encode the log. The background job reported "exit 1" only because run 3's pytest exited 1.
3. **README guard and diagnostics checks.** The guard message was checked with a throwaway test file, run once and deleted before anything was staged. The diagnostics example was checked by rendering `_diagnostics()` on synthetic records. The sweep's real sections (`tcp connect error`, idle 0.00 s, 0 connects) confirm the same line format.
4. **The README's D5 paragraph says "A documented recipe is to follow" without naming STORY-008.** README readers don't follow story IDs. The pointer to the spike report carries the command and both caveats.
5. **The stale-grep hit moved from line 561 (plan) to line 577,** because the module docstring grew by 16 lines.
6. **Reruns were done one by one (each 1 passed), and also all three together (3 passed).**
7. **The plan was committed in the chore commit, after being moved to `completed/`,** rather than in a separate plan commit.

## Tests Written

None. The story changes documentation only: README text and a module docstring, with no new function or behaviour. The `/implement` rule "every new function needs ≥ 1 test" has nothing to apply to. What the documentation states is backed by the existing 56 harness self-tests, cited by name in the Section 11 checklist, and by the README checks in *Validation Results*.

## End-to-End Tests

- [x] The README's four commands each run: `--collect-only -q -m db` (1,271) and `--collect-only -q -m "not db"` (2,639) in Task 0; a full `-m "not db"` in Task 6; full `pytest tests/` four times.
- [x] The quoted guard message matches a deliberately undeclared test's output (throwaway file, deleted).
- [x] The README's example diagnostics section matches `_diagnostics()`'s real format (byte-identical render; the sweep's three real sections match the same format).
- [x] Three full runs: 3,910 / 3,883 / 27 apart from flakes, every failure `likely infrastructure`.
- [x] Plugin run: non-`db` calls = 0, total 47,903 beside 52,980.
- [x] Dead-endpoint `-m "not db"` run is green.

## Observations (recorded, not fixed)

1. **Host-side stalls kept coming, at about one per full run.** Over four host full runs there were three test-failing 21 s `tcp connect error`s (runs 1 and 3) and two absorbed `STREAM_EXPIRED`s (census run). That is 5 events in 4 full runs, somewhat more than STORY-006's host arm (2 in 3 `-m db` runs), though both samples are small. It supports STORY-008's in-network recipe, and the verdict line made each failure a ten-second classification, which is what the PRD was for.
2. **All three stalls were labelled on `execute`, not `connect`, with `0 connects` and idle 0.00 s.** The client had just been used, so the idle probe in `_shared_client()` could not have caught it, as the PRD's evidence says. That a 21 s TCP timeout lands on a statement suggests the libsql HTTP client opens a new socket per request when it needs one. This is inferred from the labels, not traced.
3. `tests/conftest.py`'s working copy is LF while `core.autocrlf` would write CRLF (git's warning). The index is LF, so the commit is unaffected.

## Acceptance Criteria

- [x] Given README *Running Tests*, when read, then it documents `pytest tests/` (everything, the default, needs Docker), `pytest tests/ -m "not db"` (no Docker) and `pytest tests/ -m db`. It explains what the guard's failure means and the three ways to resolve it, shows an example `libsql diagnostics` section, and says what each verdict means and what to do about it. The existing in-container overrides and their warnings are unchanged. (*Summary*, *Validation Results*: README diff)
- [x] Given `tests/conftest.py`'s module docstring, when read, then "Where isolation comes from now" describes the marker, the `db`-only reset, the guard and the lazy endpoint, without stating that every test is reset. (Task 1; *Stale-text grep*)
- [x] Given three consecutive full runs, when they complete, then each run's counts are recorded and equal STORY-001's baseline, apart from flakes. Every failure, if any, carries `libsql verdict: likely infrastructure`. A failure with `no infrastructure signal` is a defect that blocks the story. (*Regression sweep*: 3 of 3 failures infrastructure, 0 defects)
- [x] Given STORY-001's scratch plugin rerun once on the final tree, when the driver-call count is compared, then non-`db` tests issue 0 calls and the total per run is recorded beside STORY-001's figure. (*Driver calls on the final tree*: 0; 47,903 vs 52,980)
- [x] Given PRD Section 11, when this story's report is written, then every checkbox is ticked with a pointer to the evidence (story report, command output, or test name). `git diff main` over the six PRD-006 suites is empty, and no file under `app/` or `chat_ui/` changed across the epic. (*PRD Section 11 checklist*, *Diff checks*)
