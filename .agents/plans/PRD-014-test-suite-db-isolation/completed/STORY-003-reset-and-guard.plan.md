---
story: STORY-003
prd: PRD-014
slug: reset-and-guard
title: "Reset only db tests, refuse storage in every other test, and declare every test the guard catches"
type: REFACTOR
complexity: MEDIUM
epic_branch: epic/PRD-014-test-suite-db-isolation
created: 2026-10-20
---

# Plan: Reset only `db` tests; guard every other test

## Summary

Replace the autouse `_never_the_configured_database` in `tests/conftest.py` with `_storage_policy(request, monkeypatch)`. A `db` test (marker from STORY-002) gets the current behaviour: the endpoint from `request.getfixturevalue("_libsql_endpoint")`, `settings.DATABASE_URL` patched to it, and `_reset_database()` unchanged. Any other test gets `settings.DATABASE_URL = _ENDPOINT` (no probe) and has `database._shared_client` and `libsql.connect` replaced by `_refuse(item, sink)`. That raises `pytest.fail.Exception` (a `BaseException`) with the PRD Section 10 message and records the access, so a teardown check still fails a test that swallowed the exception or hit the guard in a worker thread. A small `pytest_runtest_makereport` wrapper stops a guard hit that already failed the test from being reported a second time at teardown. STORY-001 measured exactly 7 in-process undeclared tests and STORY-002 already declared all 7, so the expected number of new catches is **zero**. The full run before and after confirms that, and any catch it finds is declared in the same commit. Self-tests go in `tests/test_db_isolation_harness.py`. In-process tests check the message, and `pytester` subprocess runs cover the swallow, thread, teardown, cached-client, `TestClient` and no-network cases.

## User Story

As a story implementer
I want a test that reaches storage without declaring it to fail immediately with a message saying what to add, and every test that doesn't need storage to stay off the network
So that isolation is enforced instead of assumed and two thirds of the suite stops being exposed to libSQL stalls

## Story Reference

- Story file: `.agents/stories/PRD-014-test-suite-db-isolation/STORY-003-reset-and-guard.md`
- PRD: `.agents/PRDs/PRD-014-test-suite-db-isolation/PRD.md` (sections 6.1, 6.3, 6.4, 7/F3, 9.1, 10, 11, 14 R1/R2/R6, Appendix D2)
- Input data: STORY-001 report (*Undeclared storage*, *Autouse audit*, *Subprocess audit*), STORY-002 report (*For later stories*)

## Metadata

| Field | Value |
|-------|-------|
| Type | REFACTOR (test harness; behaviour changes only for tests that reach storage undeclared) |
| Complexity | MEDIUM |
| Systems Affected | `tests/conftest.py`, `tests/test_db_isolation_harness.py`, `tests/test_migrate_to_turso_cli.py` (docstring only) |
| Story | STORY-003 |
| PRD | PRD-014 |
| Epic Branch | `epic/PRD-014-test-suite-db-isolation` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | `.agents/skills/` holds only `frontend-design`. This story changes no frontend code | — |

Environment notes from the test-env memory apply: venv `C:\Users\tobip\.venvs\harness-ai\Scripts\python.exe`, container `harness-libsql-dev` (start Docker Desktop first), full suite ~6 min in the background, and `STREAM_EXPIRED` / `10060` flakes are rerun before they are blamed on the change.

---

## Decisions taken in this plan

1. **Expected new catches: zero.** STORY-001's instrumented run found 7 in-process tests with driver calls and no storage fixture (`test_admin_auth.py` ×2 params, `test_db.py` ×1, `test_main.py` ×1, `test_measure_usage_latency.py` ×3), and STORY-002's `_DB_NODEIDS` holds all of them. The story's note expecting "the six tests from PRD-007 STORY-005" predates that measurement. Those lifespan tests request `temp_db` today, except the two already listed. The full run is still the authority: any catch is declared in this commit.
2. **The guard uses the test's own `monkeypatch`, not a private `MonkeyPatch`.** Patches undo in LIFO order on one stack, so a test that patches `libsql.connect` or `_shared_client` itself gets restored correctly. A separate `MonkeyPatch` would tear down before the test's `monkeypatch` and leave `refused` installed for later tests. The cost is that `monkeypatch.undo()` in a non-`db` test would lift the guard. All seven `undo()` calls in `tests/test_db.py` (lines 3475–4625) are in `db` tests (`uninitialized_db` / `temp_db`), so this cannot happen today. See Risks.
3. **No double report.** If the guard's exception already failed setup or call, the teardown check must not add an ERROR to the same test. Otherwise one undeclared test reads "1 failed, 1 error" and the counts drift. A `pytest_runtest_makereport` wrapper (`wrapper=True`, pytest 9 new style) marks the item in `item.stash` when a setup or call report failed with a `pytest.fail.Exception` that the guard raised. The teardown check fires only when the sink is non-empty and that mark is absent. STORY-005 adds its diagnostics to this same hook.
4. **`_first_app_frame()` resolves `app/` and `chat_ui/` from the repo root derived from `database.__file__`**, not from `request.config.rootpath`. Then it reads the same in a `pytester` child, whose rootdir is a temp directory. Format: `app/db/database.py:get_connection` (path relative to the repo, POSIX separators, `:` + function name), as in PRD Section 10. The fallback is the innermost frame in the test's own file (`item.path`), then the innermost frame outside `conftest.py`.
5. **`test_chat_shell.py`'s 21 child-process tests stay out of scope.** The guard is in-process (PRD 9.1, Out of Scope). Their child reaches only `_ENDPOINT`, and they pass while Docker is up. STORY-004 decides between `DB_BOOTSTRAP_ENABLED=false` in the probe env and declaring them, because that is the story they break.
6. **The two docstrings that name the old fixture are corrected now, minimally:** the `database_url_factory` docstring ("after `_never_the_configured_database` has emptied the database") and the module docstring's "every test starts empty whether it asked for a database or not". STORY-007 still owns the full README and docstring rewrite. This story only stops them from being wrong.
7. **Harness `pytester` children load the real conftest by copying its text** (`pytester.makeconftest(Path("tests/conftest.py").read_text())`), with `PYTHONPATH` set to the repo root so `app` imports. Each child module overrides `_libsql_endpoint` with a session fixture of the same name that returns `_ENDPOINT` without probing. Name resolution picks the closest definition, so the child makes no network call and the harness tests stay non-`db`. `pytester` is enabled with `pytest_plugins = ("pytester",)` **in the harness test module**. A non-root conftest is not allowed to declare it, and the suite is often run as `pytest` from the repo root with no `testpaths`.

---

## Patterns to Follow

### Naming: `#:` doc comments on private module constants
```python
# SOURCE: tests/conftest.py:71-79
#: The marker on tests that reach storage (PRD-014 STORY-002), applied at collection.
_DB_MARKER = "db"

#: Requesting any of these, directly or through another fixture, makes a test a `db` test.
_STORAGE_FIXTURES = frozenset(
    {"temp_db", "database_url", "uninitialized_db", "database_url_factory", "db_connect"}
)
```
→ `_UNDECLARED` (the message template) and `_REFUSED` (the `StashKey[bool]`) follow this form.

### The fixture being replaced (body and docstring style)
```python
# SOURCE: tests/conftest.py:249-277
@pytest.fixture(autouse=True)
def _never_the_configured_database(_libsql_endpoint, monkeypatch) -> None:
    """Every test starts on an empty database, whether it asked for one or not.
    ... (history: STORY-005's six tests in test_main.py / test_admin_auth.py,
    why the fix lives in conftest -- PRD-006 pinned suites; STORY-006 isolation
    is a reset; explicit fixtures still win because autouse instantiates first)
    """
    monkeypatch.setattr(settings, "DATABASE_URL", _libsql_endpoint)
    _reset_database()
```
→ Keep all four paragraphs as history. Add a fifth: since PRD-014 STORY-003 only `db` tests reach storage and are reset, and every other test is refused. Explain the two patch points, `BaseException`, the teardown backstop, and why there is no unreachable URL (PRD 6.3).

### Error handling: a hard, instructive failure instead of a skip
```python
# SOURCE: tests/conftest.py:233-245
    except Exception as exc:  # noqa: BLE001 -- any failure means "no database"
        pytest.exit(
            f"The libSQL dev server at {_ENDPOINT} is unreachable ({exc}).\n"
            "Start it with:\n"
            ...
```
→ `_UNDECLARED` is likewise multi-line, says what to do, and names the file to edit.

### Saving state monkeypatch can't undo
```python
# SOURCE: tests/conftest.py:280-303 (_default_pattern_policy)
    original = pattern_config._policy
    yield
    pattern_config._policy = original
```
→ `_storage_policy` is a generator fixture. The teardown check runs after `yield`.

### Tests: a docstring stating the contract, conftest helpers imported directly
```python
# SOURCE: tests/test_db_isolation_harness.py:17-34
from tests.conftest import _DB_NODEIDS, _STORAGE_FIXTURES, _in_db_nodeids
...
def test_a_fixture_built_on_temp_db_marks_its_test(_through_temp_db, request):
    """The test names no storage fixture itself. It is `db` only because ..."""
    assert request.node.get_closest_marker("db") is not None
```

### Client-cache test helpers (the reset tests that must keep passing)
```python
# SOURCE: tests/test_conftest_fixtures.py:249-303
@pytest.fixture
def _client_cache_restored(): ...
def test_reset_recovers_from_a_stream_expired_between_probe_and_statement(temp_db, _client_cache_restored): ...
def test_reset_still_raises_a_failure_that_is_not_a_dead_stream(temp_db, _client_cache_restored): ...
def test_reset_retries_once_not_in_a_loop(temp_db, monkeypatch, _client_cache_restored): ...
```
→ All three are `db` (via `temp_db`) and call `_reset_database()` directly. They must pass unchanged.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `tests/conftest.py` | UPDATE | `_UNDECLARED`, `_REFUSED`, `_first_app_frame()`, `_refuse()`, `_storage_policy` (replaces `_never_the_configured_database`), `pytest_runtest_makereport` wrapper, two docstring corrections, and any `_DB_NODEIDS` entries the full run demands |
| `tests/test_db_isolation_harness.py` | UPDATE | Guard self-tests (in-process plus `pytester`), `pytest_plugins = ("pytester",)` |
| `tests/test_migrate_to_turso_cli.py` | UPDATE | Line 6 docstring: `_never_the_configured_database` → `_storage_policy` (comment only) |
| editable test files caught by the guard (expected: none) | UPDATE | A storage fixture or `@pytest.mark.db`, only if the full run catches one. Never one of the six PRD-006 suites |

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 0: Pre-flight and "before" run

- **Action**: none to the code
- **Implement**:
  - `git status` clean on `epic/PRD-014-test-suite-db-isolation` @ `494abc4`. Docker Desktop is running and `docker start harness-libsql-dev`.
  - Start the "before" full run in the background on the unchanged tip: `python -m pytest tests/ -q -rfEs -p no:cacheprovider` → record collected, passed, failed, errors, skipped and wall time. Expected: **3,866 collected, 3,839 passing, 27 skipped** (STORY-002's run with its flake counted as a pass). Rerun any `STREAM_EXPIRED` / `10060` failure alone before accepting the number.
  - Record `pytest --collect-only -q -m db | tail -1` (expected 1,270).
- **Validate**: numbers written into the report draft.

### Task 1: Message, frame finder and `_refuse`

- **File**: `tests/conftest.py`
- **Action**: UPDATE, placed after `_drop_every_table_and_index()` and before `_libsql_endpoint`
- **Implement**:
  - `from pathlib import Path`, `import traceback`, and `NoReturn` from `typing`.
  - `#:` `_UNDECLARED`, a `str.format` template with `{nodeid}` and `{where}`, matching PRD Section 10. It names all five storage fixtures by joining `sorted(_STORAGE_FIXTURES)` **or** spelling them out. Prefer spelling them out in the PRD's order (`temp_db (or database_url / uninitialized_db / database_url_factory / db_connect)`), and add a harness test asserting every member of `_STORAGE_FIXTURES` appears in the message, so a rename cannot leave it stale. It also contains `@pytest.mark.db`, `_DB_NODEIDS` and `tests/conftest.py`.
  - `#:` `_REPO = Path(database.__file__).resolve().parents[2]` and `_APP_ROOTS = (_REPO / "app", _REPO / "chat_ui")`.
  - `_first_app_frame(test_path: Path | None = None) -> str` walks `traceback.extract_stack()` from the innermost frame outwards. It returns the first frame whose resolved file is under an `_APP_ROOTS` entry, formatted `f"{path.relative_to(_REPO).as_posix()}:{frame.name}"`. Failing that, it returns the innermost frame in `test_path`. Failing that, the innermost frame not in `tests/conftest.py`, formatted the same way (with `os.path.relpath` fallback when outside `_REPO`).
  - `_refuse(item, sink: list[str]) -> Callable[..., NoReturn]`, as in PRD 6.3: `refused(*args, **kwargs)` computes `where = _first_app_frame(item.path)`, appends it to `sink`, and calls `pytest.fail(_UNDECLARED.format(nodeid=item.nodeid, where=where), pytrace=False)`.
  - Docstrings in house style: why `BaseException`, why not an unreachable URL (~2 s of SYN retries on Windows, and it reads as a network error).
- **Mirror**: `tests/conftest.py:226-246` (instructive failure text), `tests/conftest.py:71-100` (`#:` constants)
- **Validate**: `python -c "import tests.conftest"` from the repo root (with the venv).

### Task 2: `_storage_policy` replaces `_never_the_configured_database`

- **File**: `tests/conftest.py`
- **Action**: UPDATE, in the same position (still the first function-scoped autouse fixture, above `_default_pattern_policy` and `_default_pii_policy`, PRD R2)
- **Implement**:
  ```python
  #: Set on an item whose setup or call already failed through the guard, so the
  #: teardown check does not report the same access twice.
  _REFUSED = pytest.StashKey[bool]()

  @pytest.fixture(autouse=True)
  def _storage_policy(request, monkeypatch):
      """<old four paragraphs kept> + PRD-014 STORY-003 paragraph"""
      item = request.node
      if item.get_closest_marker(_DB_MARKER) is not None:
          monkeypatch.setattr(settings, "DATABASE_URL", request.getfixturevalue("_libsql_endpoint"))
          _reset_database()
          yield
          return
      monkeypatch.setattr(settings, "DATABASE_URL", _ENDPOINT)
      sink: list[str] = []
      refused = _refuse(item, sink)
      monkeypatch.setattr(database, "_shared_client", refused)
      monkeypatch.setattr(libsql, "connect", refused)
      yield
      if sink and not item.stash.get(_REFUSED, False):
          pytest.fail(_UNDECLARED.format(nodeid=item.nodeid, where=sink[0]), pytrace=False)
  ```
  - `libsql` is the module object conftest already imports (`tests/conftest.py:59`), which is the same object `app/db/database.py:12` binds. Patch the attribute and never rebind.
  - `getfixturevalue` keeps STORY-004 a one-line change (drop `autouse=True` from `_libsql_endpoint`).
  - Delete `_never_the_configured_database`. Grep `tests/` for the name afterwards. Only `test_migrate_to_turso_cli.py:6` (Task 4) and conftest's own docstrings (Task 3) should match.
- **Mirror**: `tests/conftest.py:249-277`, `tests/conftest.py:280-303`
- **Validate**: `python -m pytest tests/test_conftest_fixtures.py tests/test_db_isolation_harness.py -q` → all pass (the three reset tests included).

### Task 3: Report hook and docstring corrections

- **File**: `tests/conftest.py`
- **Action**: UPDATE
- **Implement**:
  - Below `pytest_collection_modifyitems`:
    ```python
    @pytest.hookimpl(wrapper=True)
    def pytest_runtest_makereport(item, call):
        report = yield
        if report.when in ("setup", "call") and report.failed and call.excinfo is not None \
                and call.excinfo.errisinstance(pytest.fail.Exception) \
                and str(call.excinfo.value).startswith(f"{item.nodeid} reached storage"):
            item.stash[_REFUSED] = True
        return report
    ```
    The docstring says STORY-005 adds the diagnostics section here. Keep the prefix check tied to `_UNDECLARED`'s first words. A harness test asserts the template starts with `"{nodeid} reached storage"`.
  - `database_url_factory` docstring: "after `_never_the_configured_database` has emptied the database" → "after `_storage_policy` has emptied the database (requesting this fixture makes the test `db`)".
  - Module docstring, "Where isolation comes from now": replace "from an autouse fixture, so every test starts empty whether it asked for a database or not" with "from the autouse `_storage_policy`, for every `db` test. Since PRD-014 a test that is not `db` cannot reach storage at all, so it has nothing to start empty". Keep the rest. STORY-007 rewrites this fully.
- **Validate**: `python -m pytest tests/test_db_isolation_harness.py -q`

### Task 4: `test_migrate_to_turso_cli.py` docstring

- **File**: `tests/test_migrate_to_turso_cli.py`
- **Action**: UPDATE (line 6, comment only)
- **Implement**: "emptied before every test by the autouse `_never_the_configured_database` fixture" → "emptied before every test by the autouse `_storage_policy` fixture".
- **Validate**: `git diff tests/test_migrate_to_turso_cli.py` shows the docstring line only.

### Task 5: Harness self-tests

- **File**: `tests/test_db_isolation_harness.py`
- **Action**: UPDATE (new section `# --- The guard, and the reset for db tests ---`, and update the module docstring's "later stories add" sentence)
- **Implement**:
  - Module level: `pytest_plugins = ("pytester",)`. Extend the `from tests.conftest import ...` with `_ENDPOINT, _UNDECLARED, _refuse, _first_app_frame`.
  - **In-process. Never call the installed guard here, or this test's own teardown check fires:**
    - `test_a_db_test_runs_on_the_endpoint_against_an_empty_database`: `@pytest.mark.db`. Assert `settings.DATABASE_URL == _ENDPOINT` and that `sqlite_master` has no user tables via `get_connection()` (AC 1; also proves the explicit marker works).
    - `test_a_test_that_is_not_db_has_both_patch_points_refused`: assert `database._shared_client` and `libsql.connect` are not the originals (compare with `inspect.getsourcefile` / `__qualname__ == "_refuse.<locals>.refused"`), and that `settings.DATABASE_URL == _ENDPOINT`. Call neither.
    - `test_the_refusal_names_the_test_the_frame_and_every_way_to_declare`: build `refused = _refuse(request.node, sink := [])` and call it inside `pytest.raises(pytest.fail.Exception)`. Assert the message contains `request.node.nodeid`, every name in `_STORAGE_FIXTURES`, `@pytest.mark.db` and `_DB_NODEIDS`, and that `sink` has one entry.
    - `test_the_refusal_is_not_caught_by_except_exception`: `try: refused() except Exception: pytest.fail("swallowed")` inside an outer `pytest.raises(pytest.fail.Exception)`, plus `assert not issubclass(pytest.fail.Exception, Exception)`.
    - `test_the_first_app_frame_is_the_innermost_app_frame`: call `refused` through a function in `app/` without a network call. `database._shared_client` is not the real one in this test, so patch `database._shared_client` locally with `monkeypatch.setattr(database, "_shared_client", _refuse(request.node, sink))` and call `database.get_connection()` inside `pytest.raises`. Assert `sink == ["app/db/database.py:get_connection"]`. Without an app frame, assert the fallback is this test file.
    - `test_the_teardown_prefix_matches_the_message`: `_UNDECLARED.startswith("{nodeid} reached storage")`.
  - **`pytester` children** (one helper `_run_child(pytester, monkeypatch, body: str, *args)` that copies `tests/conftest.py`, sets `PYTHONPATH` to the repo root, writes a module with the `_libsql_endpoint` override plus `body`, and returns `pytester.runpytest_subprocess("-p", "no:cacheprovider", *args)`). Use `HARNESS_TEST_LIBSQL_URL=http://127.0.0.1:9` in the child env so any real connect would fail loudly rather than reach the dev server:
    - direct `get_connection()` → `assert_outcomes(failed=1)` and **no** error (dedupe). Output contains the nodeid, `app/db/database.py:get_connection`, the five fixture names, `@pytest.mark.db` and `_DB_NODEIDS`. It must not contain `10060`, `refused`, `Cannot reach` or `DatabaseUnreachableError` (no network: AC 2).
    - `try: get_connection() except Exception: pass` → `failed=1`.
    - `try: get_connection() except BaseException: pass` → `errors=1` (teardown) with the message.
    - `asyncio.run(asyncio.to_thread(swallowing_get_connection))`, where the thread function catches `BaseException` → `errors=1` with the message.
    - direct `libsql.connect(_ENDPOINT)` → `failed=1`, frame falls back to the test file.
    - cached client: set `database._client = object()`, `database._client_key = (settings.DATABASE_URL, settings.TURSO_AUTH_TOKEN)` (exactly `_shared_client`'s key, `app/db/database.py:117`) and `_client_used_at = time.monotonic()`, then `get_connection()` → `failed=1`. The cached object is never returned (AC 4).
    - `TestClient` on a tiny FastAPI app whose route calls `get_connection()`, default `raise_server_exceptions` → assert the child outcome is `failed=1` (raised through) **or** `errors=1` (teardown only), and that the message appears. Record which one in the report. Prefer pinning the observed one once known (story note).
    - a non-`db` test that touches nothing → `passed=1` (the guard is silent).
  - Each child test asserts the outcome and also `"_DB_NODEIDS" in result.stdout.str()` where relevant.
- **Mirror**: `tests/test_db_isolation_harness.py:1-98`
- **Validate**: `python -m pytest tests/test_db_isolation_harness.py -q -p no:cacheprovider` → all pass. `pytest --collect-only -q -m db tests/test_db_isolation_harness.py` lists exactly the `temp_db` marker test and the new `@pytest.mark.db` test.

### Task 6: "After" full run and declaring every catch

- **Action**: run, triage, declare
- **Implement**:
  - Full suite in the background, same command as Task 0.
  - Grep the output for `reached storage (`. For each catch:
    - in one of the six PRD-006 suites (`test_admin_auth.py`, `test_audit_router.py`, `test_stats_router.py`, `test_db.py`, `test_route_reservations.py`, `test_chat_state.py`): add a nodeid entry to `_DB_NODEIDS` with a one-line `#` comment on the path, as the existing entries have.
    - elsewhere: a storage fixture when the test then needs nothing else, `@pytest.mark.db` when it reaches storage by another path, or a `_DB_NODEIDS` module entry when most of a module needs it (story note).
  - Rerun the caught files, then the full suite again if anything was declared.
  - Flakes: `STREAM_EXPIRED` / `10060` at `db` setup → rerun alone. `docker restart harness-libsql-dev` if the suite slows sharply.
- **Validate**: total collected = before + the new harness tests. Passing = before passing + new harness tests. Skipped = 27. Zero guard failures.

### Task 7: Regression gates

- **Implement / Validate**:
  - `git diff main -- tests/test_admin_auth.py tests/test_audit_router.py tests/test_stats_router.py tests/test_db.py tests/test_route_reservations.py tests/test_chat_state.py` → empty.
  - `python -m pytest tests/test_untouched_app.py tests/test_conftest_fixtures.py -q` → pass.
  - `git diff main -- tests/ | grep '^[-+].*assert'` → no assertion added or changed outside `test_db_isolation_harness.py`.
  - `pytest --collect-only -q -m db | tail -1` → the Task 0 count plus the harness's new `db` test (plus any catches declared).
  - No `app/`, `chat_ui/` or `scripts/` file changed, so backend start and frontend lint are n/a (as in STORY-002).

---

## End-to-End Tests

This is a harness change. The "E2E" is the test runner itself:

- [ ] Full suite before (Task 0) and after (Task 6): equal totals and passing counts once the new harness tests are accounted for
- [ ] A scratch non-`db` test calling `get_connection()`, run with Docker **stopped** and `-p no:cacheprovider`, still fails with the guard message, not a connect error. `_libsql_endpoint` is still autouse in this story, so run it through the `pytester` override (Task 5) rather than the real conftest. Docker-stopped runs of the real conftest are STORY-004
- [ ] `pytest tests/test_admin_auth.py -q`: the two declared params pass. Temporarily removing their `_DB_NODEIDS` entry (scratch, reverted, not committed) makes both fail with the guard message. This proves the declared list is load-bearing and records the `TestClient` behaviour on a real pinned suite
- [ ] `pytest tests/test_main.py::test_lifespan_fails_when_the_database_is_unreachable -q` passes (declared, reaches `libsql.connect` against port 1 on purpose)

---

## Validation

```bash
PY=/c/Users/tobip/.venvs/harness-ai/Scripts/python.exe
$PY -c "import tests.conftest"
$PY -m pytest tests/test_db_isolation_harness.py tests/test_conftest_fixtures.py tests/test_untouched_app.py -q -p no:cacheprovider
$PY -m pytest --collect-only -q -m db -p no:cacheprovider | tail -1
$PY -m pytest tests/ -q -rfEs -p no:cacheprovider          # background, ~6 min
git diff main -- tests/test_admin_auth.py tests/test_audit_router.py tests/test_stats_router.py tests/test_db.py tests/test_route_reservations.py tests/test_chat_state.py
grep -rn "_never_the_configured_database" tests/ app/ chat_ui/ README.md   # expect: none
```

---

## Risks

| Risk | Mitigation |
|---|---|
| `monkeypatch.undo()` in a non-`db` test lifts the guard (Decision 2) | All seven sites in `test_db.py` are `db` tests today. Note it in the `_storage_policy` docstring. A later non-`db` `undo()` would only loosen enforcement, never break a test |
| A non-`db` test patches `libsql.connect` / `_shared_client` with a fake and relied on the old reset | Same `monkeypatch` stack, so restores are LIFO-correct. Such a test never calls `refused`. STORY-001 grep: the only patchers are `db` tests (`test_db.py`, `test_conftest_fixtures.py`) |
| Module- or session-scoped fixture touches storage before the function-scoped guard exists | STORY-001 autouse and subprocess audits: none in a non-`db` module. `fresh_schema` is out of process and its module is `db` |
| `TestClient` wraps the `BaseException` (anyio `BaseExceptionGroup`) so the call phase fails with a different type and the dedupe mark misses | The teardown check then adds an ERROR. The `pytester` `TestClient` case records the real behaviour. If it is wrapped, extend the hook to unwrap `BaseExceptionGroup` (`excinfo.group_contains`) |
| `pytester` child imports `app` with `.env` absent and its own cwd | The copied conftest's `setdefault`s cover `DATABASE_URL`, `OPENROUTER_API_KEY` and `ADMIN_TOKEN`. `PYTHONPATH` = repo root. Exclude `test_spike_pii_placeholders.py`'s env leak by never importing it in a child |
| Flakes muddy the before/after comparison | Rerun failures alone. Compare counts after reruns, as STORY-001 and STORY-002 did |

---

## Acceptance Criteria

(Copied from story `STORY-003`)

- [ ] Given a `db` test, when it starts, then `settings.DATABASE_URL` is the test endpoint and the database is empty. `_reset_database()` and its one dead-stream retry are unchanged, and the three reset tests in `tests/test_conftest_fixtures.py` pass.
- [ ] Given a non-`db` test that calls `get_connection()` (or anything that reaches `database._shared_client` or `libsql.connect`), when it runs, then it fails with a message containing its nodeid, the first `app/` frame, the five storage fixture names, `@pytest.mark.db` and `_DB_NODEIDS`. It makes no network call.
- [ ] Given the same access wrapped in `except Exception:` inside the test, or made inside `asyncio.to_thread`, or swallowed by `except BaseException:`, when the test ends, then it still fails, through the raised `pytest.fail.Exception` or through the teardown check of the recorded access.
- [ ] Given a `db` test that left a cached client in `app.db.database._client`, when a non-`db` test runs next and reaches storage, then the guard refuses. The cached client is not lent.
- [ ] Given the full suite before and after this story, when both run, then the total and passing counts equal STORY-001's baseline. Every guard catch is declared in this same commit (in `_DB_NODEIDS` for the six PRD-006 suites, by fixture, `@pytest.mark.db` or `_DB_NODEIDS` elsewhere). No assertion changes in any test, and `git diff main` over the six PRD-006 suites is empty.
- [ ] All tasks completed
- [ ] Follows existing patterns (conftest is the seam; docstrings record the why)
- [ ] Backend server start / frontend lint: n/a (no `app/` or `chat_ui/` change)
