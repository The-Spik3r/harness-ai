---
story: STORY-002
prd: PRD-014
plan: .agents/plans/PRD-014-test-suite-db-isolation/completed/STORY-002-db-marker.plan.md
epic_branch: epic/PRD-014-test-suite-db-isolation
commit: 6628c25
status: COMPLETE
completed: 2026-10-20
---

# Implementation Report — STORY-002: `db` marker

**Plan**: `.agents/plans/PRD-014-test-suite-db-isolation/completed/STORY-002-db-marker.plan.md`
**Epic Branch**: `epic/PRD-014-test-suite-db-isolation`
**Commit**: `6628c25`

## Summary

`tests/conftest.py` now registers a `db` marker and applies it at collection. A test gets the marker if its `item.fixturenames` closure includes one of `_STORAGE_FIXTURES` (`temp_db`, `database_url`, `uninitialized_db`, `database_url_factory`, `db_connect`), or if `_in_db_nodeids()` matches it against `_DB_NODEIDS`. That list is seeded with STORY-001's seven in-process undeclared-storage tests. `pytest_collection_modifyitems` marks before the `--run-benchmark` check and is `tryfirst`, so marking always precedes pytest's own `-m` deselection. No test file was edited and behaviour is unchanged: the reset is still autouse for every test.

**`-m db` selects 1,269 of the baseline's 3,854 tests: the 1,262 census tests plus the 7 listed ones.** With this story's new harness test, which reaches storage through `temp_db`, it selects 1,270 of 3,866.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | `_DB_MARKER`, `_STORAGE_FIXTURES`, `_DB_NODEIDS` (7 entries), `_in_db_nodeids()` | `tests/conftest.py` | ✅ |
| 2 | Register `db` in `pytest_configure` | `tests/conftest.py` | ✅ |
| 3 | Restructure `pytest_collection_modifyitems`: mark first, then benchmark skip; `tryfirst` | `tests/conftest.py` | ✅ |
| 4 | Harness self-tests | `tests/test_db_isolation_harness.py` | ✅ |
| 5 | Regression: full suite, PRD-006 diff, `test_untouched_app.py` | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| `import tests.conftest` | ✅ |
| `pytest --markers` lists `db` beside `benchmark` | ✅ |
| `pytest --collect-only -q -m db` | ✅ 1,270 / 3,866 (1,269 before the harness file: 1,262 + 7) |
| `-m db` + `-m "not db"` = total | ✅ 1,269 + 2,585 = 3,854 (pre-harness) |
| `-m db` nodeids with and without `--run-benchmark` | ✅ identical (`diff` differs only in the timing line) |
| Seeded nodeids in `-m db` | ✅ `test_admin_auth.py` ×2 (both params, and no other test from that module), `test_db.py` ×1, `test_main.py` ×1, `test_measure_usage_latency.py` ×3 |
| Benchmark: `test_pii_code_corpus.py -m benchmark` | ✅ 1 skipped (`benchmark: pass --run-benchmark`); with `--run-benchmark`, 1 passed |
| `tests/test_db_isolation_harness.py` | ✅ 12 passed |
| `tests/test_untouched_app.py` | ✅ 9 passed |
| Full suite | ✅ 3,866 collected: 3,838 passed, 1 failed (flake, see below), 27 skipped, 367 s |
| `git diff main` over the six PRD-006 suites | ✅ empty |
| Backend import / frontend lint / `/health` | n/a. The change is test-harness only and touches no `app/` or `chat_ui/` code |

**The full-run failure.** `tests/test_main.py::test_lifespan_pii_policy_reflects_settings` failed with `StorageError: … STREAM_EXPIRED`, the known shared-DB flake from STORY-001 and the test-env notes. Rerun alone, `tests/test_main.py` gave 19 passed. Counting it as a pass, the run is 3,839 passing and 27 skipped, which equals the baseline (3,827 / 27) plus the 12 new tests.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `tests/conftest.py` | UPDATE | +58/-1 |
| `tests/test_db_isolation_harness.py` | CREATE | +98 |

## Deviations from Plan

None. The plan's own decisions were carried out as written:
- All seven tests went in `_DB_NODEIDS` and no test file was edited.
- `test_admin_auth.py` is listed by test-function prefix, not module path, which keeps its 7 storage-free tests out of `db`.
- `test_chat_shell.py`'s 21 child-process tests stay out of the list (deferred to STORY-003/004).
- `getattr(item, "fixturenames", ())` guards non-`Function` items.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_db_isolation_harness.py` | `test_a_fixture_built_on_temp_db_marks_its_test`, `test_a_test_without_storage_is_not_marked`, `test_every_storage_fixture_is_a_conftest_fixture`, `test_every_db_nodeids_entry_names_a_file_that_exists`, `test_a_module_path_matches_every_test_in_the_module`, `test_a_module_path_does_not_match_a_module_it_prefixes`, `test_a_nodeid_matches_itself`, `test_a_nodeid_matches_its_parametrized_ids`, `test_a_class_nodeid_matches_its_methods`, `test_a_nodeid_does_not_match_a_longer_name_it_prefixes`, `test_a_nodeid_does_not_match_other_tests_in_its_module`, `test_no_entries_match_nothing` |

## For later stories

- **STORY-003:** `_DB_NODEIDS` is ready for the guard's catches. The `-m db` baseline to compare against is 1,270 / 3,866. `test_main.py` and `test_measure_usage_latency.py` are editable, so their entries may move to a storage fixture or `@pytest.mark.db` if that reads better.
- **STORY-003/004:** `test_chat_shell.py`'s `probe` tests are still non-`db`, and their child reaches `_ENDPOINT` (STORY-001 report).

## Acceptance Criteria

- [x] Given `tests/conftest.py`, when `pytest --markers` runs, then `db` is listed with a one-line description beside `benchmark`.
- [x] Given a test that requests any of `temp_db`, `database_url`, `uninitialized_db`, `database_url_factory` or `db_connect`, directly or through another fixture, when the suite is collected, then the test carries the `db` marker.
- [x] Given a test whose nodeid, or module path, is in `_DB_NODEIDS`, when collected, then it carries `db`. `_DB_NODEIDS` is seeded with STORY-001's undeclared-storage list.
- [x] Given `--run-benchmark` passed or not, when the suite is collected, then the set of `db`-marked nodeids is identical, and benchmark skipping behaves as before.
- [x] Given the change, when the full suite runs, then total and passing counts match STORY-001's baseline (plus this story's 12 new tests, with the one known flake passing on rerun). `-m db` reports the census count plus the list count (1,262 + 7), and `git diff main` over the six PRD-006 suites is empty.
