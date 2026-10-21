---
story: STORY-002
prd: PRD-014
slug: db-marker
title: "db marker: registered, applied from the storage fixtures and _DB_NODEIDS, independent of --run-benchmark"
type: REFACTOR
complexity: LOW
epic_branch: epic/PRD-014-test-suite-db-isolation
created: 2026-10-20
---

# Plan: `db` marker

## Summary

Register a `db` marker in `tests/conftest.py`. At collection, apply it to every test whose `item.fixturenames` closure includes one of five storage fixtures (`_STORAGE_FIXTURES`), and to every test matched by an explicit `_DB_NODEIDS` list. That list is seeded with STORY-001's seven in-process undeclared-storage tests. `pytest_collection_modifyitems` is restructured so the `--run-benchmark` early `return` no longer skips marking. Behaviour does not change: the reset stays autouse for every test, and no test file is edited. A new `tests/test_db_isolation_harness.py` holds the PRD's harness self-tests, starting with the marker's.

## User Story

As a harness developer
I want every test that needs storage to carry a `db` marker without any test file being edited
So that `-m db` / `-m "not db"` select the right tests and later stories can key the reset and the guard on it

## Story Reference

- Story file: `.agents/stories/PRD-014-test-suite-db-isolation/STORY-002-db-marker.md`
- PRD: `.agents/PRDs/PRD-014-test-suite-db-isolation/PRD.md` (sections 6.1, 6.2, 7/F2, 11, Appendix D1)
- Input data: `.agents/reports/PRD-014-test-suite-db-isolation/STORY-001-storage-characterization.report.md` (*Undeclared storage*, *For later stories*)

## Metadata

| Field | Value |
|-------|-------|
| Type | REFACTOR (test harness, no behaviour change) |
| Complexity | LOW |
| Systems Affected | `tests/conftest.py`, new `tests/test_db_isolation_harness.py` |
| Story | STORY-002 |
| PRD | PRD-014 |
| Epic Branch | `epic/PRD-014-test-suite-db-isolation` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | Story `skills: []`. `.agents/skills/` holds only `frontend-design`, which doesn't apply to a pytest conftest change | — |

---

## Decisions taken in this plan

1. **All seven undeclared tests go in `_DB_NODEIDS`, and no test file is edited.** The STORY-001 report lists `test_main.py` and `test_measure_usage_latency.py` as editable, but the story's description says "without any test file being edited". Adding `temp_db` to the `bench.main()` tests would also change what they run against, because `init_db()` would run before the benchmark's own call. STORY-003 may still move entries to fixtures or `@pytest.mark.db`.
2. **`test_admin_auth.py` is entered as a test-function prefix, not a module path.** The PRD 6.2 example uses the module path. Seven of the module's nine no-fixture tests make no driver call, so a module path would mark them `db` for nothing, and STORY-003 would then reset them and STORY-004 would exclude them from the Docker-free run. The story AC asks for "census count plus the list count" (7), so the entry is `tests/test_admin_auth.py::test_incorrect_bearer_token_rejected`, which covers both parametrized ids. Expected `-m db` count: **1,262 + 2 + 1 + 1 + 3 = 1,269**.
3. **Prefix matching respects id boundaries.** A nodeid entry matches when the nodeid equals it, or continues with `[` (parametrized) or `::` (a class, or a method under it). A bare `startswith` would let `…::test_a` mark `…::test_ab`. A module-path entry (one with no `::`) matches by `item.nodeid.split("::", 1)[0] == entry`, as the story specifies.
4. **`test_chat_shell.py`'s 21 child-process tests are not listed.** The STORY-001 report defers them to STORY-003/004, which may make the probe storage-free (`DB_BOOTSTRAP_ENABLED=false`) instead of declaring it.
5. **The hook gets `@pytest.hookimpl(tryfirst=True)`.** `-m` is applied by `_pytest/mark`'s own `pytest_collection_modifyitems` (pytest 9.1.1, plain hookimpl). Today the conftest hook already runs first because it registers later (pluggy calls LIFO), but `-m db` only works if marking happens before deselection, so make that order explicit. Note this in the docstring.

---

## Patterns to Follow

### Naming: module constants with `#:` doc comments, private `_UPPER`

```python
# SOURCE: tests/conftest.py:68-69
#: The marker on latency-budget assertions (PRD-012 STORY-013).
_BENCHMARK_MARKER = "benchmark"
```

### Marker registration

```python
# SOURCE: tests/conftest.py:81-82
def pytest_configure(config) -> None:
    config.addinivalue_line("markers", f"{_BENCHMARK_MARKER}: latency-budget assertion; skipped unless --run-benchmark")
```

### The hook being restructured

```python
# SOURCE: tests/conftest.py:85-100
def pytest_collection_modifyitems(config, items) -> None:
    """Skip `@pytest.mark.benchmark` tests unless `--run-benchmark` is given.
    ...
        pytest tests/test_pii_code_corpus.py -m benchmark --run-benchmark -s
    """
    if config.getoption("--run-benchmark"):
        return
    skip = pytest.mark.skip(reason=f"{_BENCHMARK_MARKER}: pass --run-benchmark")
    for item in items:
        if _BENCHMARK_MARKER in item.keywords:
            item.add_marker(skip)
```

### Tests: a module docstring giving the why, conftest helpers imported directly, and test docstrings stating the contract

```python
# SOURCE: tests/test_conftest_fixtures.py:1-28
"""The database fixtures' own contract, asserted rather than assumed.
...
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")
...
from tests.conftest import _reset_database
```

```python
# SOURCE: tests/test_conftest_fixtures.py:40-44
def test_the_fixture_yields_a_url_string_not_a_path(temp_db):
    """A `Path` return would bake "the database is a file" into 19 files, which
    is the assumption the migration removes. ..."""
    assert isinstance(temp_db, str)
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `tests/conftest.py` | UPDATE | `_DB_MARKER`, `_STORAGE_FIXTURES`, `_DB_NODEIDS`, `_in_db_nodeids()`, marker registration, restructured hook |
| `tests/test_db_isolation_harness.py` | CREATE | Self-tests: transitive fixture marking, unmarked non-storage test, matching rule, seed entries point at real files |

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: Constants and the matching helper

- **File**: `tests/conftest.py`
- **Action**: UPDATE (insert after `_BENCHMARK_MARKER`, line 69)
- **Implement**:
  - `#: The marker on tests that reach storage (PRD-014 STORY-002).` → `_DB_MARKER = "db"`
  - `_STORAGE_FIXTURES = frozenset({"temp_db", "database_url", "uninitialized_db", "database_url_factory", "db_connect"})`, with the PRD 6.2 comment: requesting any of these, directly or through another fixture, makes a test a `db` test, because `item.fixturenames` is the transitive closure.
  - `_DB_NODEIDS: tuple[str, ...]`. Its comment covers what belongs here (tests reaching storage without a storage fixture: PRD-006 suites that must not be edited, app lifespan, in-process scripts, `request.getfixturevalue`), cites STORY-001 as the source, and states the matching rule from Decision 3. Seed it, one group comment per module, in this order:
    - `"tests/test_admin_auth.py::test_incorrect_bearer_token_rejected"` (PRD-006; `require_admin_token` → `identity.resolve()`, both params)
    - `"tests/test_db.py::test_init_db_fails_fast_against_an_unreachable_endpoint"` (PRD-006; `init_db()` against a dead port)
    - `"tests/test_main.py::test_lifespan_fails_when_the_database_is_unreachable"` (lifespan, same)
    - the three `tests/test_measure_usage_latency.py` tests: `test_a_short_run_reports_both_calls_and_cleans_up`, `test_a_refused_admit_ends_the_run_without_a_report`, `test_a_changed_statement_count_ends_the_run_without_a_report` (in-process `bench.main()`)
  - `def _in_db_nodeids(nodeid: str, entries: tuple[str, ...] = _DB_NODEIDS) -> bool`. If an entry has no `::`, it is a module path and matches `nodeid.split("::", 1)[0] == entry`. Otherwise it matches `nodeid == entry or nodeid.startswith((entry + "[", entry + "::"))`. Exposing `entries` as a parameter lets the self-test exercise the rule without touching the real list.
- **Mirror**: `tests/conftest.py:68-69` (`#:` comments and the private-constant style)
- **Validate**: `C:/Users/tobip/.venvs/harness-ai/Scripts/python.exe -c "import tests.conftest"` from the repo root imports without error

### Task 2: Register `db`

- **File**: `tests/conftest.py`
- **Action**: UPDATE `pytest_configure` (line 81)
- **Implement**: add a second `config.addinivalue_line("markers", f"{_DB_MARKER}: reaches storage (a storage fixture, or listed in _DB_NODEIDS); applied at collection")` after the benchmark line.
- **Validate**: `python -m pytest --markers | grep -E "^@pytest.mark.(db|benchmark)"` prints both lines

### Task 3: Restructure `pytest_collection_modifyitems`

- **File**: `tests/conftest.py`
- **Action**: UPDATE (lines 85-100)
- **Implement**:
  - Decorate with `@pytest.hookimpl(tryfirst=True)` (Decision 5).
  - Docstring: keep the benchmark paragraph and its command verbatim. Add a `db` paragraph covering: marked from `_STORAGE_FIXTURES` ∩ `item.fixturenames` (the transitive closure, so a module-local fixture over `temp_db` counts) or `_in_db_nodeids(item.nodeid)`; marked before the benchmark check so `--run-benchmark` can't change the set; `tryfirst` so `-m db` sees it; `@pytest.mark.db` written in a test works natively.
  - Body:
    ```python
    db = pytest.mark.db  # or getattr(pytest.mark, _DB_MARKER)
    for item in items:
        if _STORAGE_FIXTURES.intersection(item.fixturenames) or _in_db_nodeids(item.nodeid):
            item.add_marker(db)
    if config.getoption("--run-benchmark"):
        return
    skip = ...  # unchanged
    ```
    Use `getattr(pytest.mark, _DB_MARKER)` so the name is spelled once, the way `_BENCHMARK_MARKER` is.
  - Doctest-like items (`DoctestItem`) have `fixturenames` too. If a non-`Function` item without the attribute ever turns up, `getattr(item, "fixturenames", ())` guards it. Use that form.
- **Mirror**: the existing hook body, lines 95-100
- **Validate**:
  - `python -m pytest --collect-only -q -m db | tail -1` → `1269/3854 tests collected (2585 deselected)` (or the equivalent wording)
  - `python -m pytest --collect-only -q -m db > a.txt; python -m pytest --collect-only -q -m db --run-benchmark > b.txt; diff a.txt b.txt` → empty (write the files to the scratchpad)
  - `python -m pytest --collect-only -q -m "db and benchmark"` / `-m benchmark` with and without `--run-benchmark`: benchmark collection is unchanged from before the edit

### Task 4: Harness self-tests

- **File**: `tests/test_db_isolation_harness.py`
- **Action**: CREATE
- **Implement**:
  - Module docstring: PRD-014's harness self-tests (marker now; guard, lazy endpoint and recorder land here in STORY-003 to STORY-005), asserted rather than assumed, in the house style of `test_conftest_fixtures.py`.
  - Same env `setdefault` prologue as `test_conftest_fixtures.py:15-18`, then `from tests.conftest import _DB_NODEIDS, _STORAGE_FIXTURES, _in_db_nodeids`.
  - `@pytest.fixture def _through_temp_db(temp_db): return temp_db`, a module-local fixture that is storage only transitively.
  - `test_a_fixture_built_on_temp_db_marks_its_test(_through_temp_db, request)`: `assert request.node.get_closest_marker("db") is not None`.
  - `test_a_test_without_storage_is_not_marked(request)`: `assert request.node.get_closest_marker("db") is None`. (This test is not in the list, so if it fails, a fixture leaked into every test.)
  - Don't parametrize a marked test over all five fixtures, since that would open five databases. Instead add `test_every_storage_fixture_is_a_conftest_fixture(request)`, which checks that each name in `_STORAGE_FIXTURES` resolves via `request.session._fixturemanager.getfixturedefs(name, request.node)`. If that private API proves awkward, use `name in dir(tests.conftest)`. This catches a typo or a rename silently unmarking a fixture's tests.
  - Matching-rule unit tests on `_in_db_nodeids(nodeid, entries=(...))`, one per case: a module path matches every test in the module, including a class method; an exact nodeid matches; a parametrized id matches its function entry; a class entry matches its methods; `…::test_a` does **not** match `…::test_ab`; a module path does not match another module sharing its prefix (`tests/test_db.py` vs `tests/test_db_extra.py::t`); empty entries match nothing.
  - `test_every_db_nodeids_entry_names_a_file_that_exists(request)`: for each entry, `(request.config.rootpath / entry.split("::", 1)[0]).is_file()`. This catches a module rename that would silently unmark it.
- **Mirror**: `tests/test_conftest_fixtures.py:1-44`
- **Validate**: `python -m pytest tests/test_db_isolation_harness.py -v` all pass (needs the libSQL container for the `temp_db` test)

### Task 5: Regression

- **Action**: run only, no file changes
- **Validate**:
  - Start Docker Desktop and run `docker start harness-libsql-dev` if they aren't up (see the test-env memory).
  - Full suite in the background (~5.5 min): `C:/Users/tobip/.venvs/harness-ai/Scripts/python.exe -m pytest tests/ -q -p no:cacheprovider`. Expect **3,854 + N collected** (N = tests added in Task 4), 3,827 + N passing and 27 skipped. `STREAM_EXPIRED` / 10060 setup errors are known flakes, so rerun those files alone before counting them.
  - `python -m pytest tests/test_untouched_app.py -q` passes.
  - `git diff main -- tests/test_admin_auth.py tests/test_audit_router.py tests/test_stats_router.py tests/test_db.py tests/test_route_reservations.py tests/test_chat_state.py` is empty.
  - `-m db` count: 1,269 + the harness tests that are `db` (one, `test_a_fixture_built_on_temp_db_marks_its_test`), so 1,270 after Task 4. Record both figures in the report.

---

## End-to-End Tests

- [ ] `pytest --markers` lists `db` beside `benchmark`
- [ ] `pytest --collect-only -q -m db` → 1,270 (1,262 census + 7 listed + 1 new harness test)
- [ ] `pytest --collect-only -q -m "not db"` + `-m db` = total collected
- [ ] `-m db` nodeid set is byte-identical with and without `--run-benchmark`
- [ ] `pytest tests/test_pii_code_corpus.py -m benchmark` still skips and `--run-benchmark` still runs (collection-level check: skip marker present/absent)
- [ ] Each of the 7 seeded nodeids appears in `-m db` output; the other 7 `test_admin_auth.py` no-fixture tests do not
- [ ] Full suite counts match the baseline plus the new tests

---

## Validation

```bash
PY=C:/Users/tobip/.venvs/harness-ai/Scripts/python.exe
$PY -m pytest --markers | grep -E "^@pytest.mark.(db|benchmark)"
$PY -m pytest --collect-only -q -m db | tail -1
$PY -m pytest tests/test_db_isolation_harness.py tests/test_conftest_fixtures.py tests/test_untouched_app.py -q
$PY -m pytest tests/ -q          # background, ~5.5 min
git diff main -- tests/test_admin_auth.py tests/test_audit_router.py tests/test_stats_router.py tests/test_db.py tests/test_route_reservations.py tests/test_chat_state.py
```

---

## Risks

| Risk | Mitigation |
|------|-----------|
| Hook order: marking must run before `_pytest.mark` deselects by `-m` | `tryfirst=True`; the `-m db` count in Task 3 proves it |
| Parametrized ids or boundary bugs over- or under-match | Unit tests on `_in_db_nodeids`, plus a check that each seeded id shows up in `-m db` |
| Nodeids depend on rootdir (`tests/…` relative to repo root) | Always run from the repo root; the harness test uses `config.rootpath` |
| Shared-DB flakes muddy the full-run count | Rerun the errored files alone (memory: known `STREAM_EXPIRED` / 10060 signatures) |

---

## Acceptance Criteria

(Copied from story `STORY-002`)

- [ ] Given `tests/conftest.py`, when `pytest --markers` runs, then `db` is listed with a one-line description beside `benchmark`.
- [ ] Given a test that requests any of `temp_db`, `database_url`, `uninitialized_db`, `database_url_factory` or `db_connect`, directly or through another fixture (its `item.fixturenames` closure), when the suite is collected, then the test carries the `db` marker.
- [ ] Given a test whose nodeid, or module path, is in `_DB_NODEIDS`, when collected, then it carries `db`. `_DB_NODEIDS` is seeded with STORY-001's undeclared-storage list.
- [ ] Given `--run-benchmark` passed or not, when the suite is collected, then the set of `db`-marked nodeids is identical (the hook no longer `return`s before marking), and benchmark skipping behaves as before.
- [ ] Given the change, when the full suite runs, then total and passing counts match STORY-001's baseline (the reset is still autouse for every test, so behaviour is unchanged). `pytest --collect-only -q -m db` reports the census count plus the list count from STORY-001, and `git diff main` over the six PRD-006 suites is empty.
- [ ] All tasks completed
- [ ] Follows existing patterns (`#:` constants, docstrings recording the why)
