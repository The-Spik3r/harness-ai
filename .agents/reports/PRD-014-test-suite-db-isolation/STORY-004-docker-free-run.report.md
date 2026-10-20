---
story: STORY-004
prd: PRD-014
plan: .agents/plans/PRD-014-test-suite-db-isolation/completed/STORY-004-docker-free-run.plan.md
epic_branch: epic/PRD-014-test-suite-db-isolation
commit: 96de11b
status: COMPLETE
completed: 2026-10-20
---

# Implementation Report — STORY-004: Lazy `_libsql_endpoint`, so `pytest -m "not db"` passes with Docker stopped

**Plan**: `.agents/plans/PRD-014-test-suite-db-isolation/completed/STORY-004-docker-free-run.plan.md`
**Epic Branch**: `epic/PRD-014-test-suite-db-isolation`
**Commit**: `96de11b`

## Summary

`_libsql_endpoint` in `tests/conftest.py` is still `scope="session"`, but it is no longer autouse. Its body, its `pytest.exit(...)` message and `returncode=1` are byte-for-byte unchanged. Three places request it, and all three did before this story:

- `_storage_policy`'s `db` branch, through `getfixturevalue`
- `database_url`
- `database_url_factory`

The non-`db` branch uses the module constant `_ENDPOINT`. So a `-m "not db"` session never probes the endpoint. The docstring now says what that costs: a full run with Docker stopped exits at the first `db` test instead of before the first test.

Making the fixture lazy was not enough on its own, as the STORY-001 and STORY-003 reports predicted. `tests/test_chat_shell.py`'s module-scoped `probe` (21 non-`db` tests) imports the app in a child process, and that import runs `init_db()` against the inherited `DATABASE_URL`. The probe's env now sets `DB_BOOTSTRAP_ENABLED=false`, the same as `tests/test_reports_pages.py`'s `pages_probe`. That makes these tests storage-free rather than declaring them `db`. With Docker stopped, no other test needed anything.

**Results**:
- Docker Desktop stopped: `-m "not db"` gave **2,586 passed, 26 skipped, 0 failed, 0 errors in 60 s**.
- Docker running: the full suite gave **3,883 collected, 3,856 passing, 27 skipped** once two `STREAM_EXPIRED` setup flakes were rerun alone.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 0 | Pre-flight: branch, Docker, before-counts | — | ✅ 3,881 = 1,271 `db` + 2,610 `not db` |
| 1 | Drop `autouse=True` and extend the docstring | `tests/conftest.py` | ✅ |
| 2 | `DB_BOOTSTRAP_ENABLED="false"` in `probe()`'s child env | `tests/test_chat_shell.py` | ✅ 38 passed |
| 3 | `_run_child(prelude=…)`, `_LAZY_PRELUDE`, two self-tests, comment and docstring corrections | `tests/test_db_isolation_harness.py` | ✅ 29 passed |
| 3b | Negative check: `autouse=True` restored temporarily | scratch, reverted | ✅ the non-`db` child test FAILED as it should |
| 4 | Docker Desktop stopped: `-m "not db"` run | — | ✅ 0 failed / 0 errors |
| 5 | Docker running: full suite | — | ✅ 3,883 / 3,856 / 27 after flake reruns |

## Validation Results

| Check | Result |
|-------|--------|
| App import (`python -c "from app.main import app"`) | ✅ OK. No `backend/` or `frontend/` exists in this repo, so there is no lint step |
| `_libsql_endpoint` decorator | ✅ `@pytest.fixture(scope="session")` (`conftest.py:327`). The 3 remaining `autouse=True` are `_storage_policy`, `_default_pattern_policy` and `_default_pii_policy` |
| `test_db_isolation_harness.py` + `test_conftest_fixtures.py` | ✅ 45 passed (43 before the new tests were added) |
| `test_chat_shell.py` | ✅ 38 passed, with Docker both running and stopped |
| `test_untouched_app.py` | ✅ 9 passed |
| `git diff main` over the six PRD-006 suites | ✅ empty (0 lines) |
| `-m db` collect count | ✅ 1,271 before and after. The new `db` test runs in a child, so the parent's `db` set doesn't change |
| Guard catches in either run (`grep -c "reached storage ("`) | ✅ 0 and 0 |
| E2E | ✅ 6/6 |

### Docker-stopped `not db` run (AC 3)

**Preconditions:**
- `docker stop harness-libsql-dev`, then Docker Desktop quit. The user approved this, because the container may be shared with another session.
- `docker info` failed, `tasklist` showed no Docker process, and `curl -m 3 http://127.0.0.1:8080` exited 7 (connection refused).

**Command**: `python -m pytest tests/ -m "not db" -q -rfEs -p no:cacheprovider`
**Wall time**: 61 s by shell `date`; pytest's own figure was 60.24 s. Exit code 0.

Output tail:

```
....................                                                     [100%]
============================== warnings summary ===============================
..\..\..\..\.venvs\harness-ai\Lib\site-packages\fastapi\testclient.py:1
  StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
=========================== short test summary info ===========================
SKIPPED [1] tests\test_pii_code_corpus.py:376: benchmark: pass --run-benchmark
SKIPPED [1] tests\test_reports_e2e.py:229: set REPORTS_E2E_URL to a running server
… (24 more test_reports_e2e.py skips, same reason)
SKIPPED [1] tests\test_reports_e2e.py:479: set REPORTS_E2E_URL to a running server
2586 passed, 26 skipped, 1271 deselected, 1 warning in 60.24s (0:01:00)
```

**Count arithmetic**:
- STORY-002 found 2,585 non-storage tests in STORY-001's baseline.
- STORY-003 declared no new tests (its guard caught 0), and the harness tests added since bring `not db` to the 2,610 measured in Task 0. This story adds 2 more, so `not db` is now 2,612.
- 2,612 = 2,586 passed + 26 skipped.
- 26 of the suite's 27 skips are `not db`: the benchmark plus 25 `test_reports_e2e.py`. The 27th, the `HARNESS_SLOW_SMOKE` smoke test, is `db`.
- "is unreachable" appears 0 times, and so does "reached storage (".

For comparison, STORY-003's full run with Docker took 320 s.

### Full suite, Docker running (AC 4)

Docker Desktop and `harness-libsql-dev` were restarted straight after the Docker-stopped run. Command: `python -m pytest tests/ -q -rfEs -p no:cacheprovider`.

| Collected | Passed | Errors | Skipped | Wall |
|---:|---:|---:|---:|---:|
| 3,883 | 3,854 | 2 | 27 | 327 s |

Both errors are infrastructure flakes in `db` tests, and both passed when rerun alone (`2 passed in 1.18s`):

| Test | Phase | Signature |
|---|---|---|
| `tests/test_audit_router.py::test_audit_entry_carries_session_id_when_present_and_null_when_absent` | setup | `StorageError: Hrana … "The stream has expired due to inactivity","code":"STREAM_EXPIRED"` (`app/db/database.py:623`) |
| `tests/test_query_pipeline_authorization.py::test_forbidden_identity_writes_exactly_one_audit_row` | setup | same `STREAM_EXPIRED` |

Counting those as passes gives **3,856 passing, 27 skipped, 3,883 collected**. That is STORY-003's after-run (3,881 / 3,854 / 27) plus this story's 2 tests, which is the plan's decision P5.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `tests/conftest.py` | UPDATE | +9/−1 |
| `tests/test_chat_shell.py` | UPDATE | +3/−0 |
| `tests/test_db_isolation_harness.py` | UPDATE | +49/−8 |
| `.agents/plans/PRD-014-test-suite-db-isolation/completed/STORY-004-docker-free-run.plan.md` | CREATE (archived) | +254 |
| `.agents/reports/PRD-014-test-suite-db-isolation/STORY-004-docker-free-run.report.md` | CREATE | this file |

## Deviations from Plan

- **Phase 3.3 / 4 validation commands.** The generic `cd backend …` and `cd frontend && npm run lint` don't apply: neither directory exists in this repo. They were replaced by `python -c "from app.main import app"` and the plan's own Validation block.
- **How Docker Desktop was stopped.** It was quit with `Stop-Process` on `Docker Desktop.exe`, because `docker desktop stop` was not available at the path tried. The daemon was confirmed down.
- Otherwise the work matched the plan. `_slot_with_flag` needed no change, as decision P2 expected: it passed with Docker stopped.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_db_isolation_harness.py` | `test_a_test_that_is_not_db_runs_with_the_endpoint_unreachable`, `test_a_db_test_exits_the_run_with_the_unreachable_message` |

Both run the real `tests/conftest.py` in a `pytester` subprocess with `HARNESS_TEST_LIBSQL_URL=http://127.0.0.1:9` and the new `_LAZY_PRELUDE`, which has no `_libsql_endpoint` override. The `db` arm takes 2.7 s, which is the refused-connect cost on Windows. It asserts on `ret == 1` and the message, because `pytest.exit` leaves no outcome summary to parse.

## Acceptance Criteria

- [x] Given `_libsql_endpoint`, when `conftest.py` is read, then it is `scope="session"` without `autouse=True`. It is instantiated only by `_storage_policy`'s `db` branch and by the storage fixtures, and it keeps its `pytest.exit(...)` message and `returncode=1`.
- [x] Given `HARNESS_TEST_LIBSQL_URL` pointing at a port with nothing listening, when a `pytester` subprocess run collects one non-`db` test, then it passes. When it collects one `db` test, then the run exits with the "libSQL dev server ... is unreachable" message.
- [x] Given Docker Desktop stopped, when `pytest tests/ -m "not db" -q` runs, then it reports 0 failed and 0 errors. The pass count equals STORY-001's non-storage count adjusted by STORY-003's declarations (2,612 = 2,586 + 26 skipped), and the report records the command, output tail and wall time.
- [x] Given Docker running, when the full suite runs, then total and passing counts equal the baseline as carried forward (3,883 / 3,856 / 27, flakes passing on rerun).

## Follow-ups

- **STORY-007:** the module docstring still says "Running these tests needs the local libSQL dev server". It should now say only `db` tests need it, and that `-m "not db"` runs without Docker in about 60 s. The README needs the same change. Both belong to STORY-007, so they weren't touched here.
- **STORY-005:** the two flakes in this run are the same `STREAM_EXPIRED` at reset setup that STORY-001 to STORY-003 recorded. They are what the recorder's verdict line is for.
