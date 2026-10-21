---
story: STORY-003
prd: PRD-014
plan: .agents/plans/PRD-014-test-suite-db-isolation/completed/STORY-003-reset-and-guard.plan.md
epic_branch: epic/PRD-014-test-suite-db-isolation
commit: 241fae0
status: COMPLETE
completed: 2026-10-20
---

# Implementation Report — STORY-003: Reset only `db` tests; guard every other test

**Plan**: `.agents/plans/PRD-014-test-suite-db-isolation/completed/STORY-003-reset-and-guard.plan.md`
**Epic Branch**: `epic/PRD-014-test-suite-db-isolation`
**Commit**: `241fae0`

## Summary

`tests/conftest.py`'s autouse `_never_the_configured_database` is replaced by `_storage_policy(request, monkeypatch)`.

- **`db` test:** `settings.DATABASE_URL` is set to `request.getfixturevalue("_libsql_endpoint")`, then `_reset_database()` runs. That function is unchanged, including its one dead-stream retry.
- **Any other test:**
  - `DATABASE_URL` is set to `_ENDPOINT` without a probe.
  - `database._shared_client` and `libsql.connect` are both replaced by `_refuse(item, sink)`. It raises `pytest.fail.Exception` with the PRD Section 10 message and records the access in `sink`.
  - If `sink` is non-empty at teardown, the test fails there. That catches an access that was swallowed, or that happened in a worker thread.
- **Report hook:** a new `pytest_runtest_makereport` wrapper notes when the guard's exception already failed setup or call. The teardown check then doesn't report the same test a second time.

**The guard caught no new test in the full run.** STORY-001 measured 7 in-process tests that reach storage without declaring it, and STORY-002 had already listed all 7 in `_DB_NODEIDS`. So no `_DB_NODEIDS` entry, marker or fixture had to be added.

**`TestClient` finding (requested by the story):** `TestClient` **re-raises** the refusal. `ServerErrorMiddleware` catches only `Exception`, and the client re-raises server exceptions by default. The test is reported FAILED in the call phase, with no 500 and no second error at teardown. Two places show this: the `pytester` case, and the real pinned suite `test_admin_auth.py` with its entry removed temporarily (E2E 3).

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 0 | Pre-flight and "before" full run | — | ✅ |
| 1 | `_UNDECLARED`, `_REPO`/`_APP_ROOTS`, `_where()`, `_first_app_frame()`, `_refuse()` | `tests/conftest.py` | ✅ |
| 2 | `_storage_policy` replaces `_never_the_configured_database`, plus the `_REFUSED` stash key | `tests/conftest.py` | ✅ |
| 3 | `pytest_runtest_makereport` wrapper; module and `database_url_factory` docstrings corrected | `tests/conftest.py` | ✅ |
| 4 | Docstring rename | `tests/test_migrate_to_turso_cli.py` | ✅ |
| 5 | Harness self-tests: 7 in-process, 8 `pytester` | `tests/test_db_isolation_harness.py` | ✅ |
| 6 | "After" full run, triage, declaring catches (none found) | — | ✅ |
| 7 | Regression gates | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| `import tests.conftest`, `from app.main import app` | ✅ |
| `test_conftest_fixtures.py` + `test_db_isolation_harness.py` + `test_untouched_app.py` | ✅ 52 passed (includes the three `_reset_database` tests) |
| `--collect-only -m db` | ✅ 1,270 before → 1,271 after (+1: the new `@pytest.mark.db` harness test) |
| `git diff main` over the six PRD-006 suites | ✅ empty |
| Assertions changed outside the harness file | ✅ none (the only `assert` match in the diff is docstring prose in `test_conftest_fixtures.py`) |
| `_never_the_configured_database` left in code | ✅ only in `_storage_policy`'s history paragraph, on purpose |
| Frontend lint / `/health` | n/a: no `app/`, `chat_ui/` or `scripts/` file changed |
| E2E | ✅ 4/4 (below) |

### Full suite, before and after

Command for both runs: `python -m pytest tests/ -q -rfEs -p no:cacheprovider`. Docker container `harness-libsql-dev` was running and no other pytest session was on it.

| Run | Commit | Collected | Passed | Failed | Skipped | Wall | Guard catches |
|---|---|---:|---:|---:|---:|---:|---:|
| Before | `494abc4` | 3,866 | 3,837 | 2 | 27 | 342 s | — |
| After | working tree → `241fae0` | 3,881 | 3,853 | 1 | 27 | 320 s | **0** (`grep -c "reached storage ("` = 0) |

All failures were infrastructure, and each one passed when rerun:

| Run | Test | Signature | Rerun |
|---|---|---|---|
| Before | `test_query_pipeline_pii_profiles.py::test_every_arm_records_the_resolved_profile[chat-pattern-block]` | `os error 10060` (`UsageLimitError` / `StorageError`) | passed (alone, on the unchanged base) |
| Before | `test_query_router.py::test_byok_without_permission_returns_200_blocked_with_required_permission` | `os error 10060` | passed |
| After | `test_audit_session_id.py::test_three_sends_in_one_session_share_one_session_id_in_the_audit` (`db`, via `temp_db`) | `/query` returned **500**. Every 500 branch in `app/routers/query.py:20-41` translates a storage-layer error. No error text was captured | passed in 16 of 17 reruns. The one failing rerun took 23 s against a normal 8 s, which is a stall. A scratch plugin that printed 5xx bodies never caught it in 16 runs |

**Counted with reruns:** before, 3,866 / 3,839 passing / 27 skipped (= STORY-002's figure). After, 3,881 / 3,854 / 27. The difference is exactly the 15 new harness tests. The after-run failure is in a `db` test, whose path through `_storage_policy` is the old fixture's code unchanged, so it cannot be a guard effect. It is the flake this PRD is about, and STORY-005's diagnostics will classify failures like it.

## E2E

| # | Check | Result |
|---|---|---|
| 1 | Full suite before and after | ✅ counts above |
| 2 | Docker **stopped** (`docker stop harness-libsql-dev`): a scratch non-`db` test calling `get_connection()` under a copy of the real conftest | ✅ `1 failed in 0.02s` with the full guard message, no connect error. Container restarted right after |
| 3 | Removed `test_admin_auth.py`'s `_DB_NODEIDS` entry temporarily (scratch, restored from a copy, not committed) | ✅ both params FAILED with `… reached storage (app/db/database.py:get_connection) without declaring it.` With the entry restored, 9 passed |
| 4 | `test_main.py::test_lifespan_fails_when_the_database_is_unreachable` | ✅ passed (declared; calls `libsql.connect` against port 1 on purpose) |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `tests/conftest.py` | UPDATE | +149/-8 |
| `tests/test_db_isolation_harness.py` | UPDATE | +267/-4 |
| `tests/test_conftest_fixtures.py` | UPDATE | +4/-3 (docstring only) |
| `tests/test_migrate_to_turso_cli.py` | UPDATE | +1/-1 (docstring only) |
| `.agents/plans/…/completed/STORY-003-reset-and-guard.plan.md` | MOVE | archived |

## Deviations from Plan

1. **`tests/test_conftest_fixtures.py:150-153` docstring also renamed.** The plan's grep step found a second docstring naming `_never_the_configured_database`, in `test_factory_yields_a_distinct_url_on_every_call`. Only comment lines changed. PRD 6.7 lists this file as "extended only if a docstring reference must follow the rename".
2. **`_first_app_frame()` falls back to an absolute path** when a frame is outside the repo (a `pytester` child's test file, for example), instead of the plan's `os.path.relpath`. The message still names the file, and a relative path from a temp directory would be less readable.
3. **Harness test count:** 15 instead of the plan's sketch of 14. `test_without_an_app_frame_the_test_itself_is_named` was split out from the frame test.
4. **One extra diagnosis step.** The after-run's single failure was a 500, not a recognisable flake signature. So the audit modules were rerun 13 times (once with a scratch plugin in `%TEMP%\prd014-story003\` that prints 5xx bodies) before it was accepted as infrastructure.
5. **E2E 2 was run against a stopped container, not via `pytester`:** a scratch directory with a copy of the conftest, the container stopped, then started again. That is stronger than the plan asked for. The `pytester` children already cover the dead-endpoint case on every run.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_db_isolation_harness.py` (reset) | `test_a_db_test_runs_on_the_endpoint_against_an_empty_database` |
| `tests/test_db_isolation_harness.py` (guard, in-process) | `test_a_test_that_is_not_db_has_both_patch_points_refused`, `test_the_refusal_names_the_test_the_frame_and_every_way_to_declare`, `test_the_refusal_is_not_caught_by_except_exception`, `test_the_first_app_frame_is_the_innermost_app_frame`, `test_without_an_app_frame_the_test_itself_is_named`, `test_the_teardown_check_recognises_the_message_by_its_first_words` |
| `tests/test_db_isolation_harness.py` (guard, `pytester` child) | `test_reaching_storage_undeclared_fails_once_with_the_whole_message`, `test_an_except_exception_in_the_test_does_not_swallow_the_refusal`, `test_an_access_swallowed_by_except_baseexception_fails_at_teardown`, `test_an_access_in_a_worker_thread_fails_at_teardown`, `test_a_direct_libsql_connect_is_refused_and_names_the_test`, `test_a_client_cached_by_an_earlier_test_is_not_lent`, `test_a_refusal_inside_a_testclient_request_fails_the_test`, `test_a_test_that_touches_no_storage_does_not_hear_from_the_guard` |

The `pytester` children copy `tests/conftest.py`, set `PYTHONPATH` to the repo, and override `_libsql_endpoint` with a session fixture that doesn't probe. `HARNESS_TEST_LIBSQL_URL` points at a dead port. The whole file runs in about 5 s.

## For later stories

- **STORY-004:** making `_libsql_endpoint` lazy is now a one-line change (drop `autouse=True`). `_storage_policy` already asks for it through `getfixturevalue`, and only on the `db` branch. `test_chat_shell.py`'s 21 `probe` tests are still not `db`, and their child still runs `init_db()` against `_ENDPOINT`. They will fail `-m "not db"` with Docker stopped. Options are in STORY-001's report.
- **STORY-005:** add the `libsql diagnostics` section to the `pytest_runtest_makereport` wrapper (`wrapper=True`) that this story added. `_REFUSED` lives in `item.stash` alongside it.
- **STORY-007:** the module docstring and `_storage_policy`'s docstring were corrected, not rewritten. Wall time after was 320 s, against 342 s before (one run each, so this is noise-level, not a measurement).

## Acceptance Criteria

- [x] Given a `db` test, when it starts, then `settings.DATABASE_URL` is the test endpoint and the database is empty. `_reset_database()` and its one dead-stream retry are unchanged, and the three reset tests in `tests/test_conftest_fixtures.py` pass.
- [x] Given a non-`db` test that calls `get_connection()` (or anything that reaches `database._shared_client` or `libsql.connect`), when it runs, then it fails with a message containing its nodeid, the first `app/` frame, the five storage fixture names, `@pytest.mark.db` and `_DB_NODEIDS`. It makes no network call (child against a dead port and E2E 2 with the container stopped: 0.02 s, no connect error).
- [x] Given the same access wrapped in `except Exception:` inside the test, or made inside `asyncio.to_thread`, or swallowed by `except BaseException:`, when the test ends, then it still fails, through the raised `pytest.fail.Exception` (`except Exception`) or through the teardown check (`to_thread`, `except BaseException`).
- [x] Given a `db` test that left a cached client in `app.db.database._client`, when a non-`db` test runs next and reaches storage, then the guard refuses. The cached client is not lent.
- [x] Given the full suite before and after this story, when both run, then the total and passing counts equal STORY-001's baseline plus the new harness tests (3,839 → 3,854 passing, +15). Every guard catch is declared in this same commit (there were none). No assertion changes in any test, and `git diff main` over the six PRD-006 suites is empty.
