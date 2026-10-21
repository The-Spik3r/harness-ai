---
id: PRD-014
slug: test-suite-db-isolation
title: Test Suite Database Isolation — Only the Tests That Need Storage Touch It, and Their Failures Say Why
status: draft
base_branch: main
epic_branch: epic/PRD-014-test-suite-db-isolation
created: 2026-10-20
updated: 2026-10-21
---

## 1. Executive Summary

On this machine the full suite never passes in one run, and the failures are not bugs. Every full run fails one or two tests, a different one each time, and each passes when rerun alone. PRD-013's STORY-001, STORY-002 and STORY-004 reports all record it. So a red run carries no signal. A real regression and an infrastructure hiccup look the same, and the only way to tell them apart is to rerun each failure by hand.

**The cause is outside the code.** Individual TCP connections to the local libSQL server (`harness-libsql-dev`, Docker Desktop on Windows with the WSL2 backend, at `http://127.0.0.1:8080`) stall for 7–21 s. If a stall outlasts the server's ~10 s stream window, the late request gets `STREAM_EXPIRED`. If the stall hits the TCP handshake, the driver gives up after 21 s with `tcp connect error ... (os error 10060)`. The production defence, the idle probe in `_shared_client()` ([app/db/database.py:75-128](../../../app/db/database.py)), cannot catch this. Every failure landed on a client used 0–0.45 s earlier, so the stream died *during* the statement. `_translated()` ([app/db/database.py:588-624](../../../app/db/database.py)) correctly refuses to retry a statement that died mid-transaction. That design stays. This PRD changes nothing in `app/`.

**Two thirds of the suite is exposed for no reason.** The autouse fixture `_never_the_configured_database` ([tests/conftest.py:192-220](../../../tests/conftest.py)) resets the database before *every* test. 2,363 of 3,453 tests request no database fixture, yet each one makes a round trip to Docker before it runs, and several observed stalls landed on exactly those tests. The session-scoped autouse `_libsql_endpoint` ([tests/conftest.py:169-189](../../../tests/conftest.py)) also probes the server at session start, so no subset of the suite can run without Docker.

This PRD adds a `db` marker, applied automatically from the storage fixtures plus an explicit list in `conftest.py`. The reset and the endpoint probe run only for `db` tests. Every other test gets a guard that **fails the test** the first time it reaches storage, names the test and says what to add. That is stricter than today's "reset and allow". Failing `db` tests carry a diagnostics section in the report: the slowest driver call, any call over 10 s, any `STREAM_EXPIRED` or `tcp connect error`, and a one-line verdict. A spike (D5) tests whether Docker Desktop's port forwarding causes the stalls.

**MVP goal:** `pytest -m "not db"` passes with Docker Desktop stopped and issues zero driver calls. A test that reaches storage without declaring it fails with a message naming it. Every failing `db` test's report ends with a verdict line. The total and passing test counts, and every assertion in every pinned suite, are unchanged.

## 2. Mission

Make a red test mean a defect. A test that does not need storage cannot be broken by storage. A test that does need it says, when it fails, whether the infrastructure was involved.

Core principles:

- **Test-only.** Nothing under `app/` or `chat_ui/` changes. The production recovery design (probe before lending, invalidate without retrying mid-transaction) is correct for the failure seen here.
- **Isolation gets stronger, never weaker.** Today's promise holds: no test can reach another test's rows or anyone's real database. The new rule adds that no test can reach storage *without saying so*. "Silently reset and allow" becomes "refuse and explain".
- **Declared once, in one place.** The marker comes from the fixtures a test already requests. The exceptions live in one list in `conftest.py`. No test file is edited to add a marker. The six PRD-006 suites stay untouched, and so does every other suite unless it gains a test.
- **Asserted, not assumed.** "Non-`db` tests issue zero driver calls" is enforced by the guard on every run, not checked once in a story report.
- **Diagnose, don't retry.** A flaky `db` failure is made cheap to classify. It is not hidden by an automatic rerun (D4).
- **No new dependency.** Markers, hooks, a proxy class and `report.sections`, all inside pytest's own API.

## 3. Target Users

**Harness developer running the suite locally (Windows + Docker Desktop).** Today they run 3,453 tests, see one or two failures and rerun each by hand to learn it was a stall. They need a red run they can trust, a fast Docker-free loop for the 68% of the suite that never needed storage, and a report that tells them at a glance whether a `db` failure is theirs.

**Story implementer (agent or human, `/implement`).** Writes new tests under PRD-015 and later. They need the rule to be impossible to break by accident: forget to declare storage and the test fails immediately with the fix in the message, instead of passing on a reset it never asked for.

**Reviewer reading a story report.** Today "1 flaky failure, passed on rerun" is unverifiable prose. They need the verdict line pasted from the report, so "infrastructure" is evidence, not a claim.

**Future CI maintainer.** No CI exists yet. When it does, `-m "not db"` is a job that needs no service container, and `-m db` is the one that does.

## 4. MVP Scope

### In Scope

**Baseline**
- [ ] Characterization: total/pass counts and wall time of a full run, driver calls per run, the storage-fixture census per module, and the list of tests that issue driver calls without a storage fixture (measured with an uncommitted scratch plugin)
- [ ] Audit of every autouse fixture and every non-storage test that spawns a subprocess, recorded in the story report

**`db` marker (`tests/conftest.py`)**
- [ ] `db` registered in `pytest_configure`, beside `benchmark`
- [ ] Applied in `pytest_collection_modifyitems` to every item whose `item.fixturenames` (the transitive closure) includes `temp_db`, `database_url`, `uninitialized_db`, `database_url_factory` or `db_connect`
- [ ] Applied to every item matching the explicit `_DB_NODEIDS` tuple (module paths or full nodeids)
- [ ] Marking runs regardless of `--run-benchmark` (the current hook `return`s early when the flag is set)

**Reset and guard (`tests/conftest.py`)**
- [ ] `_never_the_configured_database` becomes `_storage_policy`: for `db` items it points `settings.DATABASE_URL` at the endpoint and resets, as today. For all others it installs the guard
- [ ] Guard: in non-`db` tests, `database._shared_client` and `libsql.connect` are patched to record the access and raise `pytest.fail.Exception` with an instructive message
- [ ] Teardown check: a recorded access fails the test even if application code swallowed the exception
- [ ] Every test the guard catches is declared, through `_DB_NODEIDS` for the six PRD-006 suites and by fixture, marker or list entry elsewhere, in the same story, so the epic branch is never red

**Docker-free run (`tests/conftest.py`)**
- [ ] `_libsql_endpoint` stops being autouse. It is instantiated only by the `db` path of `_storage_policy` and the storage fixtures
- [ ] `pytest -m "not db"` passes with Docker Desktop stopped

**Diagnostics (`tests/conftest.py`)**
- [ ] For `db` items, `libsql.connect` is wrapped. Every client it returns is a forwarding proxy that times each method call and records driver errors into the *currently running* test's sink
- [ ] `pytest_runtest_makereport` hookwrapper: on a failed `setup`, `call` or `teardown` of a `db` item, appends a `libsql diagnostics` section with call count, slowest call, every call ≥ 10 s, every `STREAM_EXPIRED` / `tcp connect error` / `os error 10060`, and a verdict line
- [ ] Error text in the section passes through `database._redacted()`

**Spike (D5)**
- [ ] `-m db` three times from a Linux container on the same Docker network as `harness-libsql-dev`, addressed by container name, plus three host-side control runs in the same session. Result recorded in a spike report and in this PRD's Appendix

**Documentation**
- [ ] README *Running Tests*: `pytest -m "not db"` (no Docker), `pytest -m db`, how to read the diagnostics section, and what the guard's failure means
- [ ] `tests/conftest.py` module docstring: the isolation mechanism, updated in place

### Out of Scope

- [ ] Any change under `app/` or `chat_ui/`, including `_IDLE_PROBE_AFTER_SECONDS`
- [ ] Automatic retries of failed tests (D4). Revisited only by the conditional STORY-008
- [ ] Parallel runs (`pytest-xdist`). Independent clients contend for one libSQL writer, and STORY-006 of PRD-007 measured 169 of 200 writes lost to `TRANSACTION_TIMEOUT`
- [ ] Replacing Docker Desktop on developer machines
- [ ] Guarding storage access from **child processes**. The in-process guard cannot see them. They are audited in STORY-001 instead (Section 14, R3)
- [ ] Tracing why stalled calls take exactly 15 s inside `libsql` 0.1.11's HTTP stack
- [ ] Setting up CI

## 5. User Stories

1. **As a harness developer, I want `pytest -m "not db"` to run without Docker, so that the 68% of the suite that never needed storage is a fast, reliable loop.**
   *Example:* Docker Desktop is stopped. `pytest tests/ -m "not db" -q` reports about 2,360 passed, about 1,090 deselected, 0 failed, and never prints the "libSQL dev server is unreachable" exit message.

2. **As a story implementer, I want a test that reaches storage without declaring it to fail immediately and tell me what to add, so that I can't write a test that passes on isolation it never asked for.**
   *Example:* a new `test_router_extra.py::test_lists_rows` calls `list_audit_logs()` with no fixture. It fails with `tests/test_router_extra.py::test_lists_rows reached storage (get_connection → _shared_client) without declaring it. Request temp_db (or database_url / uninitialized_db / database_url_factory), add @pytest.mark.db, or — for a suite that must not be edited — add its nodeid to _DB_NODEIDS in tests/conftest.py.`

3. **As a harness developer, I want each failing `db` test to say whether an infrastructure stall was involved, so that I can tell a regression from a hiccup without rerunning it.**
   *Example:* `test_chat_sessions.py::test_rename` fails. The report ends with `libsql verdict: likely infrastructure — execute took 15.04 s and ended in STREAM_EXPIRED (client last used 0.12 s earlier)`. Another failure ends with `libsql verdict: no infrastructure signal (38 calls, slowest 0.021 s)` and is a real bug.

4. **As a reviewer, I want story reports to quote the verdict line for any flaky failure, so that "infrastructure" is evidence I can check.**
   *Example:* a STORY-00N report says "1 error in `test_router.py` setup; verdict: likely infrastructure — connect failed after 21.05 s with tcp connect error (os error 10060)".

5. **As a maintainer of a pinned suite, I want the marker applied without editing the file, so that PRD-006's census guards and the `test_admin_auth.py` contract stay untouched.**
   *Example:* `tests/test_admin_auth.py` reaches storage through the app's lifespan without a fixture. It is listed in `_DB_NODEIDS`, `git diff main -- tests/test_admin_auth.py` is empty, and `test_untouched_app.py` passes.

6. **As a harness developer, I want the full-run driver-call count to drop to the `db` tests' share, so that fewer round trips are exposed to stalls at all.**
   *Example:* STORY-001 measures about 40,000 driver calls per full run. After STORY-003, the non-`db` share is 0, asserted by the guard on every run.

7. **As the owner of the local environment, I want to know whether Docker Desktop's port forwarding causes the stalls, so that the next step (move the server, add a retry, accept it) rests on a measurement.**
   *Example:* the spike runs `-m db` three times from `harness-spike` on network `harness-test-net` against `http://harness-libsql-dev:8080`. It records stall counts beside three host runs and states "confirmed", "refuted" or "inconclusive".

## 6. Core Architecture & Patterns

### 6.1 Where each piece sits

```
pytest_configure            registers markers: benchmark, db
pytest_collection_modifyitems
  ├─ mark db   ← item.fixturenames ∩ _STORAGE_FIXTURES  or  nodeid matches _DB_NODEIDS
  └─ skip benchmark unless --run-benchmark          (no longer returns before marking)

per test, autouse (conftest order: _storage_policy → _default_pattern_policy → _default_pii_policy)
  _storage_policy(request, monkeypatch)
    db item     → endpoint = request.getfixturevalue("_libsql_endpoint")   (session probe, lazy)
                  settings.DATABASE_URL = endpoint
                  _driver_recorder.begin(item)      (wraps libsql.connect; sink = this item)
                  _reset_database()                 (unchanged, incl. its one dead-stream retry)
    other item  → settings.DATABASE_URL = _ENDPOINT (no probe, no connection)
                  patch database._shared_client and libsql.connect → _refuse(item)
                  teardown: fail if _refuse recorded anything

pytest_runtest_makereport (hookwrapper)
  failed setup/call/teardown of a db item → report.sections += ("libsql diagnostics", text)
```

### 6.2 The marker (Decision D1)

```python
#: Requesting any of these, directly or through another fixture, makes a test a `db` test.
_STORAGE_FIXTURES = frozenset(
    {"temp_db", "database_url", "uninitialized_db", "database_url_factory", "db_connect"}
)

#: Tests that reach storage without one of the fixtures above, and whose files must not be
#: edited (PRD-006's six suites) or reach it through a path no fixture names (app lifespan,
#: request.getfixturevalue). Module paths match every test in the module.
_DB_NODEIDS: tuple[str, ...] = (
    "tests/test_admin_auth.py",
    # ... populated from STORY-001's list and the guard's catches in STORY-003
)
```

- `item.fixturenames` is the **transitive closure**, so a module-local fixture that depends on `temp_db` marks its tests too. Nothing is enumerated by hand that pytest already knows.
- `db_connect` is added to the brief's four. It opens a raw connection (`tests/conftest.py`, the pre-migration schema builders in `test_db.py`), so a test that used it alone would be a storage test without the marker.
- A fixture requested dynamically (`request.getfixturevalue("temp_db")`) is invisible at collection. The guard catches it and it goes into `_DB_NODEIDS`.
- `@pytest.mark.db` written in a test file also works (pytest's own semantics). New tests should prefer a storage fixture. The explicit marker is for tests that reach storage some other way and whose file *may* be edited.
- **Brief correction.** The brief calls the PRD-006 suites "pinned byte-for-byte". Since PRD-006 STORY-023, `test_untouched_app.py` asserts them **by census**: adding a test passes, removing one fails. The rule here is still to leave them unedited, which is stricter than the census requires and keeps the marker decision in one file.

### 6.3 The guard (Decision D2)

```python
def _refuse(item, sink: list[str]) -> Callable[..., NoReturn]:
    def refused(*args, **kwargs):
        where = _first_app_frame()            # e.g. "app/db/database.py:list_audit_logs"
        sink.append(where)
        pytest.fail(_UNDECLARED.format(nodeid=item.nodeid, where=where), pytrace=False)
    return refused
```

- **Two patch points.** `database._shared_client` catches every path through `get_connection()` *and* a client cached by an earlier `db` test, which a `libsql.connect` patch alone would miss. `libsql.connect` catches direct construction (`_proved()`, `check_database_reachable()`, any test helper).
- **`pytest.fail.Exception` derives from `BaseException`**, so an application `except Exception:` (for example a router turning `StorageError` into a `503`) cannot swallow it and pass the test.
- **The teardown check is the backstop** for `except BaseException`, worker threads (`asyncio.to_thread` in `chat_ui/chat_ui/admin_state.py`) and background tasks. If the sink is non-empty at teardown, the test fails with the same message.
- **Not "point at an unreachable URL".** On Windows a refused localhost connect costs ~2 s of SYN retries per test and reads as a network error, the very ambiguity this PRD removes.
- `settings.DATABASE_URL` still gets a valid value (`_ENDPOINT`), so code that only *reads* the setting (config validation, `_safe_endpoint()`, startup-guard formatting) behaves as today.

### 6.4 Reset only for `db` tests

`_reset_database()` and `_drop_every_table_and_index()` are unchanged, including the one retry on a dead stream. Only the selection changes. The ordering guarantee the current docstring relies on still holds: autouse fixtures instantiate before requested ones, so `database_url`'s own `setattr` still wins and `temp_db`'s `init_db()` still runs on an empty database.

**Why isolation still holds.** A `db` test starts empty because it is reset. A non-`db` test cannot see rows because it cannot reach storage at all. Rows a non-`db` test might leave behind cannot exist for the same reason. No pair of tests can observe each other through storage.

### 6.5 Lazy endpoint

`_libsql_endpoint` keeps `scope="session"` and its `pytest.exit(...)` message, and loses `autouse=True`. The first `db` test to run instantiates it. A `-m "not db"` session never does. A full run with Docker stopped still exits with the same instructive message, at the first `db` test rather than before the first test.

### 6.6 Diagnostics (Decision D3)

```python
class _RecordedClient:
    """Forwards every attribute to the real client; times callables and records driver errors."""
    def __init__(self, real, recorder): ...
    def __getattr__(self, name):
        attr = getattr(self._real, name)
        if not callable(attr):
            return attr
        def timed(*args, **kwargs):
            started = time.monotonic()
            try:
                return attr(*args, **kwargs)
            except ValueError as exc:
                self._recorder.error(name, time.monotonic() - started, exc)
                raise
            finally:
                self._recorder.call(name, time.monotonic() - started, idle=...)
        return timed
```

- **The sink is the running test, not the creating test.** `_shared_client()` caches a client across tests, so a client built in test A and used in test B must record into B. The recorder holds a module-level "current item" pointer set in `_storage_policy` setup and cleared at teardown.
- **`connect` is recorded too.** The 21 s `tcp connect error` happens at construction (runs 3 and 5 of the brief's evidence), during *setup*, so the report hook covers `setup`, `call` and `teardown`.
- **Exceptions pass through unchanged.** `_translated()` classifies by message text and `_is_dead_stream()` by marker, so the proxy re-raises the original `ValueError` object.
- **Tests that patch `libsql.connect` themselves** (`tests/test_db.py:4084` onward) keep working. `monkeypatch` layers over the wrapper and restores it. Those tests see their own fake, unrecorded, which is correct.
- **`monkeypatch.undo()`** in `test_db.py` (seven call sites) reverts the wrapper for the rest of that test. Diagnostics for those tests may be partial. That is accepted and documented in the hook's docstring.

**Report section:**

```
----------------------------- libsql diagnostics -----------------------------
calls: 212 on 2 clients, 1 connect
slowest: execute 15.047 s (client idle 0.12 s before) → STREAM_EXPIRED
over 10 s: execute 15.047 s
driver errors: 1 × STREAM_EXPIRED
libsql verdict: likely infrastructure — execute took 15.05 s and ended in STREAM_EXPIRED
```

**Verdict rules** (a pure function `_verdict(records) -> str`, unit-tested):

| Condition | Verdict |
|---|---|
| any error matching `stream_expired` / `stream has expired` / `invalid baton` (reuse `database._DEAD_STREAM`), or `tcp connect error` / `os error 10060` | `likely infrastructure — <op> took <s> s and ended in <error>` |
| no such error, but a call ≥ 10.0 s | `likely infrastructure — <op> took <s> s (no driver error)` |
| neither | `no infrastructure signal (<n> calls, slowest <s> s)` |
| zero calls recorded (e.g. after `monkeypatch.undo()`) | `no driver calls recorded` |

### 6.7 Directory structure (files touched)

```
tests/
  conftest.py                         # markers, _DB_NODEIDS, _storage_policy, guard, recorder, report hook
  test_db_isolation_harness.py        # NEW: marker, guard, lazy endpoint, recorder, verdict
  test_conftest_fixtures.py           # extended only if a docstring reference must follow the rename
  test_migrate_to_turso_cli.py        # docstring mentions _never_the_configured_database (comment only)
README.md                             # Running Tests
.agents/spikes/PRD-014-docker-network-stalls.md   # NEW: D5 result
```

### 6.8 Patterns followed

- **The conftest is the seam** (PRD-007 STORY-006). Isolation mechanics live in one file, and consumers are not edited.
- **Docstrings record the why and the measurement**, in the house style of `_reset_database()` and `_shared_client()`.
- **Characterize before changing** (every PRD since PRD-009 opens with a baseline story).
- **The epic branch is never red.** The guard and the marks it forces land in one commit (STORY-003).

## 7. Tools/Features

### F1 — Characterization (STORY-001)
Full run on `main`: total, pass, wall time. A scratch plugin (not committed, kept in the story's scratch notes) counts driver calls per test and records whether the test requested a storage fixture. Outputs: calls per full run (expected ~40,000), the census (expected 1,090 / 2,363 across 47 / 91 modules, 27 mixed), and **the list of tests with ≥ 1 driver call and no storage fixture**. That list is STORY-003's input. Also an audit table of every autouse fixture (expected: none but `_never_the_configured_database` touches storage) and of every non-storage test that spawns a subprocess, with whether the child reaches storage.

### F2 — `db` marker (STORY-002)
Register `db`. Mark from `_STORAGE_FIXTURES` and `_DB_NODEIDS` (seeded with STORY-001's list). Restructure `pytest_collection_modifyitems` so the benchmark early return does not skip marking. No behaviour change: the reset is still autouse for all. Tests: `pytest --collect-only -m db -q` count equals the census plus the list. A module-local fixture depending on `temp_db` marks its test. A nodeid in the list marks its test.

### F3 — Reset only for `db`, guard everywhere else (STORY-003)
Replace `_never_the_configured_database` with `_storage_policy` (Section 6.3–6.4). Run the full suite and add every guard catch to `_DB_NODEIDS` or (in editable files) a fixture. Full run before and after, same total and pass counts. Tests: a non-`db` test calling `get_connection()` raises `pytest.fail.Exception` whose message contains its nodeid and `_DB_NODEIDS`. An `except Exception` around the call does not swallow it. A guard hit inside `asyncio.to_thread` still fails the test at teardown. A cached client from an earlier `db` test is not lent.

### F4 — Docker-free `not db` run (STORY-004)
`_libsql_endpoint` loses `autouse`. Tests: with `HARNESS_TEST_LIBSQL_URL=http://127.0.0.1:9` (nothing listening), a `pytester` subprocess run of a non-`db` test passes and a `db` test exits with the unreachable message. Manual: Docker Desktop stopped, `pytest -m "not db"` green, recorded in the report.

### F5 — Driver recorder and diagnostics (STORY-005)
`_RecordedClient`, the current-item sink, the report hook, `_verdict()`. Tests: `_verdict` table cases. The proxy forwards attributes and re-raises the original exception object. A cached client records into the test that uses it. A failing `db` test (via `pytester`) shows the section with a verdict line, and a passing one shows none. `test_db.py` and `test_conftest_fixtures.py` pass in about the same time with and without the recorder (the brief measured 234 passed both ways).

### F6 — Spike: stalls inside the Docker network (STORY-006)
Section 12, Phase 3. Writes `.agents/spikes/PRD-014-docker-network-stalls.md` and copies the conclusion into Appendix "D5 result".

### F7 — Documentation and regression sweep (STORY-007)
README, conftest module docstring, and three full runs whose results (with every verdict line) go in the report.

### F8 — Conditional follow-up (STORY-008)
Created only if D5 says so: either a documented in-network test recipe (if confirmed) or `pytest-rerunfailures --only-rerun "STREAM_EXPIRED|os error 10060"` scoped to `-m db` (if stalls are unavoidable on Docker Desktop). Section 13.

## 8. Technology Stack

| Component | Version | Role here |
|---|---|---|
| Python | 3.11 | unchanged |
| pytest | 9.1.1 (from the cached `.pyc` tags; `requirements.txt` is unpinned) | markers, `pytest_collection_modifyitems`, `pytest_runtest_makereport` hookwrapper, `report.sections`, `pytester` for harness self-tests |
| pytest-asyncio | unpinned, as today | unchanged |
| `libsql` | 0.1.11 (pinned) | wrapped, never modified |
| libSQL server | `ghcr.io/tursodatabase/libsql-server@sha256:6dd3eb27…` (sqld 0.24.33) | unchanged |
| Docker Desktop | 29.8.2, WSL2, kernel 6.18.54.1 | environment under study (D5) |

**No new dependencies.** `pytester` ships with pytest. It is enabled per module with `pytest_plugins = ["pytester"]` in `test_db_isolation_harness.py`, and its runs use `runpytest_subprocess` so an inner session cannot disturb the outer one's shared client.

## 9. Security & Configuration

### 9.1 Isolation guarantees (the security-relevant property)

- **Unchanged:** a `db` test runs against `HARNESS_TEST_LIBSQL_URL` (default `http://127.0.0.1:8080`), never the configured `DATABASE_URL`, and starts empty.
- **New:** a non-`db` test cannot open a driver connection in-process at all. The README's in-container hazard (`monkeypatch.undo()` in `tests/test_db.py` reverting the redirect) stays confined to `test_db.py`, a `db` module where the redirect is reinstated by `database_url`. The README warning about passing `DATABASE_URL` stays as it is.
- **Child processes are not guarded** (Out of Scope). STORY-001 audits them. A non-`db` test whose child inherits `{**os.environ}` gets `DATABASE_URL=_ENDPOINT`, the local dev server, never a configured database, because `conftest.py` sets it with `setdefault` before any import.

### 9.2 Diagnostics output

- Driver error text goes through `database._redacted()` before it reaches the report, so a token-bearing message (a hosted endpoint pointed at by `HARNESS_TEST_LIBSQL_URL`) is not printed.
- The section prints method names, durations and error text, **not SQL statements or parameters**.

### 9.3 Configuration

| Variable | Default | Change |
|---|---|---|
| `HARNESS_TEST_LIBSQL_URL` | `http://127.0.0.1:8080` | none. Read only when a `db` test runs |
| `DATABASE_URL` | set to the endpoint by `conftest.py` | none |
| `TURSO_AUTH_TOKEN` | unset | none |

No new environment variables or CLI options. The recorder is always on for `db` tests (D3: measured overhead indistinguishable from zero).

### 9.4 Out of scope (security)

Production storage behaviour, auth, and anything a deployment runs.

## 10. API Specification

No HTTP API changes. The interface this PRD defines is the test runner's:

| Command | Needs Docker | Runs |
|---|---|---|
| `pytest tests/` | yes | everything, as today (D6) |
| `pytest tests/ -m "not db"` | **no** | the ~2,360 tests that never touch storage |
| `pytest tests/ -m db` | yes | the storage tests, with diagnostics on failure |
| `pytest --collect-only -q -m db` | no | lists what counts as `db` |

**Guard failure message** (exact wording settled in STORY-003, must contain the nodeid, the first app frame, the five fixture names, `@pytest.mark.db` and `_DB_NODEIDS`):

```
tests/test_x.py::test_y reached storage (app/db/database.py:list_audit_logs) without declaring it.
Request temp_db (or database_url / uninitialized_db / database_url_factory / db_connect),
add @pytest.mark.db, or — for a suite that must not be edited — add its nodeid to
_DB_NODEIDS in tests/conftest.py.
```

**Report section title:** `libsql diagnostics`. **Last line prefix:** `libsql verdict: `, so it can be found with `grep "libsql verdict"`.

## 11. Success Criteria

### MVP definition

The brief's six criteria, all measured:

- [x] `pytest -m "not db"` passes with Docker Desktop stopped *(evidence: STORY-007 report, Section 11 checklist)*
- [x] Every non-`db` test issues zero in-process driver calls, enforced by the guard on every run *(evidence: STORY-007 report, Section 11 checklist)*
- [x] A test that reaches storage without declaring it fails with a message naming it and what to add *(evidence: STORY-007 report, Section 11 checklist)*
- [x] Every `db` failure (setup, call or teardown) carries a `libsql diagnostics` section ending in a verdict line *(evidence: STORY-007 report, Section 11 checklist)*
- [x] Total and passing counts equal STORY-001's baseline (3,453 collected at brief time; the baseline run is authoritative), and no assertion in any pinned suite changes *(evidence: STORY-007 report, Section 11 checklist)*
- [x] Driver calls per full run drop from STORY-001's figure (~40,000) to the `db` tests' own share, measured again in STORY-007 with the same scratch plugin *(evidence: STORY-007 report, Section 11 checklist)*

### Functional requirements

- [x] `db` is registered, so `--strict-markers` would accept it, and `pytest --markers` lists it with a one-line description *(evidence: STORY-007 report, Section 11 checklist)*
- [x] Marking is identical with and without `--run-benchmark` *(evidence: STORY-007 report, Section 11 checklist)*
- [x] A test requesting a storage fixture only transitively is marked *(evidence: STORY-007 report, Section 11 checklist)*
- [x] `git diff main -- tests/test_admin_auth.py tests/test_audit_router.py tests/test_stats_router.py tests/test_db.py tests/test_route_reservations.py tests/test_chat_state.py` is empty at the epic's end *(evidence: STORY-007 report, Section 11 checklist)*
- [x] `tests/test_untouched_app.py` passes *(evidence: STORY-007 report, Section 11 checklist)*
- [x] The guard's exception is not caught by `except Exception`, and an access swallowed by `except BaseException` or made in a worker thread still fails the test at teardown *(evidence: STORY-007 report, Section 11 checklist)*
- [x] A client cached by a `db` test is never lent to a non-`db` test *(evidence: STORY-007 report, Section 11 checklist)*
- [x] `_reset_database()`'s dead-stream retry and its three tests in `test_conftest_fixtures.py` are unchanged and pass *(evidence: STORY-007 report, Section 11 checklist)*
- [x] Diagnostics re-raise the driver's original exception object, so `_translated()` and `_is_dead_stream()` behave identically *(evidence: STORY-007 report, Section 11 checklist)*
- [x] Diagnostics never print SQL or parameters, and error text is redacted *(evidence: STORY-007 report, Section 11 checklist)*
- [x] A passing test's report has no diagnostics section *(evidence: STORY-007 report, Section 11 checklist)*

### Quality indicators

- [x] `-m "not db"` wall time recorded in STORY-004 (expected: well under the full run, since it skips ~2,360 resets) *(evidence: STORY-007 report, Section 11 checklist)*
- [x] Full-run wall time not worse than STORY-001's baseline *(evidence: STORY-007 report, Section 11 checklist)*
- [x] Three consecutive full runs in STORY-007: every failure, if any, carries `libsql verdict: likely infrastructure`. Any `no infrastructure signal` failure is a defect and blocks the story *(evidence: STORY-007 report, Section 11 checklist)*
- [x] Spike report states a conclusion (confirmed / refuted / inconclusive) with stall counts for both arms *(evidence: STORY-007 report, Section 11 checklist)*

## 12. Implementation Phases

### Phase 1 — Measure and mark (Stories 1–2)
**Goal:** know exactly which tests touch storage, and label them without changing behaviour.
**Deliverables:** STORY-001 baseline and lists. `db` marker and `_DB_NODEIDS` seeded.
**Validation:** `--collect-only -m db` count = census + list. Full suite unchanged.

### Phase 2 — Enforce (Stories 3–4)
**Goal:** reset only `db` tests, refuse storage everywhere else, and run without Docker.
**Deliverables:** `_storage_policy`, guard, teardown check, every catch declared, lazy `_libsql_endpoint`.
**Validation:** full run before and after STORY-003 with equal counts. `-m "not db"` green with Docker stopped. Pinned-suite diff empty.

### Phase 3 — Diagnose and investigate (Stories 5–6)
**Goal:** every `db` failure classifies itself, and the stall hypothesis is tested.
**Deliverables:** recorder, report section, `_verdict()`, spike report.
**Spike procedure (D5):**
```bash
docker network create harness-test-net
docker network connect harness-test-net harness-libsql-dev
docker compose build harness-ai          # image already carries en_core_web_lg
for i in 1 2 3; do
  docker compose run --rm --network harness-test-net \
    -e HARNESS_TEST_LIBSQL_URL=http://harness-libsql-dev:8080 \
    -e DATABASE_URL=http://harness-libsql-dev:8080 -e TURSO_AUTH_TOKEN= \
    harness-ai pytest tests/ -m db -q -rA | tee spike-in-net-$i.log
done
for i in 1 2 3; do pytest tests/ -m db -q -rA | tee spike-host-$i.log; done   # control arm
grep -c "libsql verdict: likely infrastructure" spike-*.log
```
Both arms run with the STORY-005 recorder. The spike also counts calls ≥ 10 s, not only failures, since the fixture's retry absorbs some stalls. **Confirmed:** zero stalls in-network, ≥ 1 on host. **Refuted:** stalls in-network at a comparable rate. **Inconclusive:** zero in both arms, so repeat until the host arm stalls or record that it could not be reproduced.
**Validation:** report exists, with logs summarized and a conclusion stated.

### Phase 4 — Document and prove (Stories 7–8)
**Goal:** the workflow is written down and three full runs show the outcome.
**Deliverables:** README, conftest docstring, regression sweep, and STORY-008 if D5 calls for it.
**Validation:** Section 11 checklist ticked with evidence in the STORY-007 report.

## 13. Future Considerations

- **If D5 confirms the hypothesis:** document running `-m db` from inside the Docker network as the reliable local recipe, or move the dev server into WSL2 directly. Possibly `scripts/test-db-in-network.sh`.
- **If stalls are unavoidable on Docker Desktop:** `pytest-rerunfailures` with `--only-rerun "STREAM_EXPIRED|os error 10060"`, limited to `db` tests, with the diagnostics section kept on the first attempt's report.
- **CI:** two jobs, `-m "not db"` with no services and `-m db` with the libSQL image as a service container.
- **Guarding child processes:** for example a `sitecustomize` hook injected through `PYTHONPATH` for non-`db` tests, if STORY-001 finds a child that touches storage.
- **Tracing the 15 s** inside `libsql` 0.1.11's HTTP stack, which may lead to a client-side timeout setting.
- **`--strict-markers`** in a `pytest.ini`, once one exists.

## 14. Risks & Mitigations

| # | Risk | Mitigation |
|---|---|---|
| R1 | Tests depend on storage without saying so and start failing | Intended (D2). STORY-001 lists them in advance, STORY-003 declares every one in the same commit as the guard, and the full run is compared before and after |
| R2 | An autouse fixture or session fixture touches storage before the guard is installed | STORY-001 audits every autouse fixture. `_storage_policy` is declared first in `conftest.py`, so it instantiates before `_default_pattern_policy` and `_default_pii_policy` (same scope, definition order). A storage access during collection or session setup fails loudly regardless, since `_libsql_endpoint` is no longer autouse |
| R3 | A non-`db` test's child process reaches storage, invisible to the guard | STORY-001 audits all subprocess-spawning non-`db` tests and declares any that reach storage. The child can only reach the local dev server (Section 9.1). Process-level guarding is listed in Section 13 |
| R4 | The recorder changes driver behaviour | It forwards every attribute and re-raises the original exception. The brief's instrumentation left `test_db.py` + `test_conftest_fixtures.py` at 234 passed at the same speed. STORY-005 repeats that comparison. Tests that patch `libsql.connect` layer over it through `monkeypatch` |
| R5 | `db` tests still flake | Expected until D5 is acted on. The verdict line makes each one a ten-second classification instead of a rerun. STORY-008 exists for the follow-up |
| R6 | Editing the six PRD-006 suites by accident | `_DB_NODEIDS` lives in `conftest.py`. Section 11 requires an empty `git diff main` over the six, and `test_untouched_app.py` keeps its census |

## 15. Appendix

### Source

[pre-prds/PRE-PRD-017-test-suite-db-isolation.md](../../../pre-prds/PRE-PRD-017-test-suite-db-isolation.md). The brief targeted "PRD-017". IDs are assigned max+1 at promotion, and PRE-PRD-014 to 016 have not been promoted yet, so this is PRD-014.

### Decisions (resolved from the brief's open decisions)

| # | Decision |
|---|---|
| D1 | Brief default, plus `db_connect` as a fifth storage fixture and the transitive closure via `item.fixturenames`. Explicit list `_DB_NODEIDS` in `conftest.py`. No per-file edits to pinned suites |
| D2 | Brief default, made robust: patch `database._shared_client` **and** `libsql.connect`, raise `pytest.fail.Exception` (a `BaseException`), and fail at teardown on any recorded access |
| D3 | `conftest.py`, report section via `pytest_runtest_makereport` covering setup/call/teardown. No new dependency. Always on for `db` tests |
| D4 | No automatic retry. Revisited in conditional STORY-008 |
| D5 | Spike in STORY-006 with a host-side control arm (Section 12, Phase 3) |
| D6 | `pytest` runs everything by default. `-m` filters are documented, not required |

### D5 result

**Confirmed, on thin evidence** (STORY-006, 2026-10-21; [spike report](../../spikes/PRD-014-docker-network-stalls.md)). Over three interleaved `-m db` runs per arm, about 143,500 driver calls each, the in-network arm (`harness-test-net` → `http://harness-libsql-dev:8080`) recorded **0 stall events** and the host arm (`127.0.0.1:8080`, through Docker Desktop's port forwarding) **2**: a 21.05 s `tcp connect error` (`os error 10060`) that errored one test's setup, and a `STREAM_EXPIRED` in the next test that `_reset_database()`'s retry absorbed. A fourth host run was discarded because Windows slept mid-run. If both arms stalled at the host's rate, zero in-network events would still happen about 13.5% of the time.

**Recommendation for STORY-008.** Take the "confirmed" branch of Section 13: document an in-network `-m db` recipe (possibly `scripts/test-db-in-network.sh`) as the reliable local way to run storage tests, keeping the host-side run supported with its verdict line. The recipe must use `docker run --network` (`docker compose run` has no `--network`), and must handle the three `tests/test_measure_usage_latency.py` tests, which refuse the non-local hostname `harness-libsql-dev` by design. Because the sample is small, repeat a few in-network runs while validating the recipe and treat any in-network stall as reopening D5. A scoped rerun policy is not needed now. If one is added later, its pattern must match `tcp connect error` and `STREAM_EXPIRED` (the recorder's labels on both platforms), not only `os error 10060`.

### Assumptions

- The brief's counts (3,453 tests; 1,090 with a storage fixture; ~40,000 driver calls per run) were measured on 2026-10-14. PRD-013 work landed afterwards, so STORY-001's baseline is authoritative and the criteria in Section 11 refer to it.
- pytest is 9.1.x (inferred from cached bytecode). `pytester.runpytest_subprocess` and hookwrapper `report.sections` behave as documented there.
- Child processes that need storage already receive an explicit URL through `child_db_env()` (for example `test_chat_ui_startup_guard.py`) and therefore already request `database_url_factory`, so they are `db` tests.

### Evidence (verified against `main` @ `c3f0ed5`)

- `_never_the_configured_database` is autouse and resets every test ([tests/conftest.py:192-220](../../../tests/conftest.py)).
- `_libsql_endpoint` is `scope="session", autouse=True` and connects at session start ([tests/conftest.py:169-189](../../../tests/conftest.py)), which is why no subset runs without Docker today.
- `pytest_collection_modifyitems` returns early under `--run-benchmark` ([tests/conftest.py:85-100](../../../tests/conftest.py)).
- `_shared_client()` caches one client across tests, keyed by URL and token, so a guard on `libsql.connect` alone would miss it ([app/db/database.py:78-127](../../../app/db/database.py)).
- `libsql.connect` is called only from `app/db/database.py:122` and `:168` in application code. `tests/test_db.py:4084` patches it.
- `monkeypatch.undo()` appears seven times in `tests/test_db.py` (lines 3475–4625).
- The six PRD-006 suites are asserted by census in [tests/test_untouched_app.py:70-77](../../../tests/test_untouched_app.py).

### Tentative story breakdown (to be generated by `/create-stories`)

| # | Story | Type | Size |
|---|---|---|---|
| 1 | Characterize: baseline run, driver calls per test, storage census, undeclared-storage list, autouse and subprocess audit | technical | small |
| 2 | `db` marker: registration, automatic from storage fixtures, `_DB_NODEIDS`, benchmark-hook fix | technical | small |
| 3 | Reset only `db` tests, guard every other test, declare every test it catches (one commit) | technical | medium |
| 4 | Lazy `_libsql_endpoint`: `-m "not db"` with Docker stopped | technical | small |
| 5 | Driver recorder and `libsql diagnostics` section with verdict | feature | medium |
| 6 | Spike: `-m db` from inside the Docker network vs host (D5) | spike | small |
| 7 | README, conftest docstring, three-run regression sweep | docs | small |
| 8 | (Conditional on D5) in-network recipe or scoped rerun policy | technical | small |

### Related documents

- PRD-007 (Turso migration): STORY-005 (autouse reset origin), STORY-006 (one client per process; 169/200 `TRANSACTION_TIMEOUT`)
- PRD-008 STORY-024: idle probe, 10–12 s stream window
- PRD-006 STORY-023: pinned suites asserted by census
- PRD-013 STORY-001/002/004 reports: recorded flakes
- README [Running Tests](../../../README.md#running-tests)

### Dependencies

None. Independent of the OpenAI-compatible endpoint track. It should land before PRD-015's stories so their reports benefit from a trustworthy red/green.

Skills referenced: none (`.agents/skills/` holds only `frontend-design`, which does not apply to a test-harness PRD).
