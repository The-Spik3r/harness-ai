---
story: STORY-005
prd: PRD-014-test-suite-db-isolation
slug: libsql-diagnostics
title: "Driver recorder and a libsql diagnostics section with a verdict on every failing db test"
type: NEW_CAPABILITY
complexity: MEDIUM
epic_branch: epic/PRD-014-test-suite-db-isolation
created: 2026-10-20
---

# Plan: Driver recorder and a `libsql diagnostics` section on every failing `db` test

## Summary

`_storage_policy`'s `db` branch wraps `libsql.connect` (through the test's own `monkeypatch`) so every client it returns is a `_RecordedClient`. The proxy forwards every attribute, times each method call, keeps a per-client `last_used` for idle time, and re-raises the driver's original exception object. Every call is recorded into a module-level "current item" that the fixture sets before `_reset_database()` and clears at its teardown. Because recording goes to the current item and not to the item that built the client, a client cached by `_shared_client()` in test A records into test B. The existing `pytest_runtest_makereport` wrapper gains a second job: when a `db` item's `setup`, `call` or `teardown` report failed, it appends a `libsql diagnostics` section. The section comes from two pure functions, `_diagnostics(records)` and `_verdict(records)`. Error text is reduced to the matched infrastructure marker, taken from `database._redacted()` output, so no SQL, parameters or tokens reach the report. Self-tests go in `tests/test_db_isolation_harness.py`. In-process tests use fabricated records and a fake real client. `pytester` child runs use a fake driver, so they need no server and trigger no real stalls. A before/after timing of `test_db.py` + `test_conftest_fixtures.py` and a full run close AC 5.

## User Story

As a harness developer
I want every failing `db` test to report whether an infrastructure stall was involved
So that I can tell a regression from a libSQL hiccup without rerunning the test

## Story Reference

- Story file: `.agents/stories/PRD-014-test-suite-db-isolation/STORY-005-libsql-diagnostics.md`
- PRD: `.agents/PRDs/PRD-014-test-suite-db-isolation/PRD.md` (sections 6.1, 6.6, 7 F5, 9.2, 10, 14 R4, Appendix D3)
- Carried-forward baseline: STORY-004 report (3,883 collected / 3,856 passing / 27 skipped, flakes passing on rerun)

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY (test harness only; no `app/` change) |
| Complexity | MEDIUM |
| Systems Affected | `tests/conftest.py`, `tests/test_db_isolation_harness.py` |
| Story | STORY-005 |
| PRD | PRD-014-test-suite-db-isolation |
| Epic Branch | `epic/PRD-014-test-suite-db-isolation` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | `.agents/skills/` holds only `frontend-design`, which does not apply. Story says "Skills: none applicable". | — |

---

## Decisions

| # | Decision | Why |
|---|----------|-----|
| P1 | **Extend the existing `pytest_runtest_makereport`** (`tests/conftest.py:163`, new-style `@pytest.hookimpl(wrapper=True)`). Do not add a second `hookwrapper=True` impl as the story's note sketches. | A module cannot define two functions with one name, and the conftest already uses the new-style form (`report = yield; return report`). The story's `outcome.get_result()` belongs to the old style. |
| P2 | **One record per call**, written in `finally`, carrying the error label if there was one. The PRD sketch records an error and then a call. | Counting stays trivial (`len(records)`), and "slowest call ended in X" is one record. |
| P3 | **Catch `Exception`, record it, bare `raise`.** | The driver raises bare `ValueError`, but a broader catch loses nothing because the original object is re-raised. `pytest.fail.Exception` (a `BaseException`) passes straight through. |
| P4 | **Error text is shown as the matched marker only** (e.g. `STREAM_EXPIRED`, `tcp connect error`), sliced from `database._redacted(str(exc))`. Errors that match no marker get no label. | AC 2 lists only matching errors, and AC 4 / PRD 9.2 forbid SQL and parameters. A `SQLite error: near "…"` message quotes SQL, so printing whole messages would break 9.2. A slice of redacted text cannot carry a token. |
| P5 | **Marker order**: `"stream_expired"` first, then the rest of `database._DEAD_STREAM`, then `"tcp connect error"`, `"os error 10060"`. Matching is case-insensitive, and the label is the span as it appears in the text. | The live expiry message contains both `stream has expired` and `STREAM_EXPIRED`. The PRD example labels it `STREAM_EXPIRED`. Reuses `_DEAD_STREAM` as AC 3 asks. |
| P6 | **ASCII `->` instead of `→`** in the `slowest:` line. Keep the em dash `—` in verdicts, because AC 3 spells it. | Piped or `tee`d pytest output on Windows uses cp1252, which has `—` and `×` but not `→`. Task 5 checks this with redirected output. |
| P7 | **Pointer set before `_reset_database()`, cleared in a `finally` that wraps both reset and `yield`.** `_end(item)` clears only if `_current is item`. | A reset failure must still clear it (the code after `yield` never runs then). The test's own fixtures tear down before `_storage_policy` (first autouse, so last finalized among function fixtures), so their teardown calls still record (story's technical note). |
| P8 | **The real `connect` is captured at fixture time** (`real = libsql.connect`, then `monkeypatch.setattr`). | Inside a `pytester` child a module-level fake is already installed when the fixture runs, so the recorder wraps it. In the main suite this is the real driver, because `monkeypatch` restored it after the previous test. |
| P9 | **"Without the recorder" baseline = the same command run before Task 1** (Task 0), not an env toggle. | PRD 9.3: no new environment variables or options. |

---

## Patterns to Follow

### Naming / module constants with `#:` docs
```python
# SOURCE: tests/conftest.py:357-360
#: Set on an item whose setup or call already failed through the guard, so the
#: teardown check does not report the same access a second time.
_REFUSED = pytest.StashKey[bool]()
```

### Proxy over the real client (forward everything, intercept a little)
```python
# SOURCE: tests/test_db.py:4057-4080
class _StandInClient:
    """A client that fails its first `execute()` and delegates afterwards.
    ...
    def __init__(self, real, message: str, failures: int = 1) -> None:
        self._real = real
    ...
    def __getattr__(self, name):
        return getattr(self._real, name)
```

### Error classification by message text
```python
# SOURCE: app/db/database.py:413-428, 486-500
_DEAD_STREAM = ("stream has expired", "stream_expired", "invalid baton")

def _is_dead_stream(message: str) -> bool:
    haystack = message.lower()
    return any(marker in haystack for marker in _DEAD_STREAM)

def _redacted(message: str) -> str:
    scrubbed = _AUTH_TOKEN_IN_URL.sub(rf"\1{_REDACTED}", message)
    ...
```

### Hook (new-style wrapper)
```python
# SOURCE: tests/conftest.py:163-182
@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item, call):
    report = yield
    if (report.when in ("setup", "call") and report.failed and ...):
        item.stash[_REFUSED] = True
    return report
```

### Tests: `pytester` child over a copy of the real conftest
```python
# SOURCE: tests/test_db_isolation_harness.py:242-247, 255-268
def _run_child(pytester, monkeypatch, body: str, prelude: str = _CHILD_PRELUDE):
    monkeypatch.setenv("PYTHONPATH", str(_REPO_ROOT))
    monkeypatch.setenv("HARNESS_TEST_LIBSQL_URL", "http://127.0.0.1:9")
    pytester.makeconftest((_REPO_ROOT / "tests" / "conftest.py").read_text(encoding="utf-8"))
    pytester.makepyfile(test_child=prelude + textwrap.dedent(body))
    return pytester.runpytest_subprocess("-p", "no:cacheprovider")
...
    result.assert_outcomes(failed=1)
    output = result.stdout.str()
    assert _GET_CONNECTION_REFUSED in output
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `tests/conftest.py` | UPDATE | `_Call`, `_RECORDS`, `_current`/`_begin`/`_end`, `_RecordedClient`, `_recorded_connect`, `_infra_error`, `_verdict`, `_diagnostics`; install in `_storage_policy`'s `db` branch; section in `pytest_runtest_makereport`; docstrings |
| `tests/test_db_isolation_harness.py` | UPDATE | In-process recorder/verdict/section tests, `_FAKE_DRIVER_PRELUDE` and the child runs; module docstring |
| `.agents/reports/PRD-014-test-suite-db-isolation/STORY-005-libsql-diagnostics.report.md` | CREATE (by `/implement`) | Before/after timings, full-run counts |

No change to `app/`, `tests/test_db.py`, `tests/test_conftest_fixtures.py` or the six PRD-006 suites.

---

## Tasks

Execute in order. Each task is atomic and verifiable. Python is `C:\Users\tobip\.venvs\harness-ai\Scripts\python.exe` (written `py` below). Docker Desktop and `harness-libsql-dev` must be running for Tasks 0, 6 and 7.

### Task 0: Pre-flight and the "without recorder" timing

- **Action**: none to code
- **Implement**: confirm branch `epic/PRD-014-test-suite-db-isolation` and a clean tree. Start Docker and run `docker start harness-libsql-dev`. Run the AC 5 pair **twice** on the unchanged tree and record counts and pytest's wall figure for each run:
  `py -m pytest tests/test_db.py tests/test_conftest_fixtures.py -q -p no:cacheprovider`
- **Validate**: both runs green, same counts. Note them for the report. If a run stalls (`STREAM_EXPIRED` / `10060`), `docker restart harness-libsql-dev` and repeat it, and note that in the report.

### Task 1: Records, sink and pure formatting

- **File**: `tests/conftest.py`
- **Action**: UPDATE. New block after `_drop_every_table_and_index()`, headed by a short comment naming PRD-014 STORY-005 / Section 6.6. Add `import itertools`, `import time` and `from dataclasses import dataclass`.
- **Implement**:
  - `_STALL_SECONDS = 10.0` (`#:` doc: the brief's stalls were 15–21 s, and no healthy call measured near 10 s).
  - `_INFRA_MARKERS = ("stream_expired", *(m for m in database._DEAD_STREAM if m != "stream_expired"), "tcp connect error", "os error 10060")` (P5).
  - `@dataclass(frozen=True) class _Call`: `op: str`, `seconds: float`, `client: Optional[int]`, `idle: Optional[float]` (None for `connect`), `error: Optional[str]` (the marker label, or None).
  - `_RECORDS = pytest.StashKey[list[_Call]]()`.
  - `_current: Optional[pytest.Item] = None`, `_begin(item)`, `_end(item)` (clears only if `_current is item`), `_record(call: _Call)`: if `_current` is not None, `_current.stash.setdefault(_RECORDS, []).append(call)`, otherwise drop it. A client used outside any `db` test, e.g. by a later module-scoped fixture, forwards and records nothing.
  - `_infra_error(message: str) -> Optional[str]`: `text = database._redacted(message)`. For each marker, a case-insensitive search returns the matched span of `text`. None if nothing matches.
  - `_verdict(records: list[_Call]) -> str`, implementing the PRD 6.6 table in priority order:
    1. no records → `no driver calls recorded`
    2. any record with `error` → take the slowest such → `likely infrastructure — {op} took {seconds:.2f} s and ended in {error}`
    3. any `seconds >= _STALL_SECONDS` → slowest → `likely infrastructure — {op} took {seconds:.2f} s (no driver error)`
    4. else → `no infrastructure signal ({n} calls, slowest {seconds:.2f} s)`
  - `_diagnostics(records) -> str`, lines joined by `\n`, last line prefixed `libsql verdict: `:
    ```
    calls: 212 on 2 clients, 1 connect
    slowest: execute 15.047 s (client idle 0.12 s before) -> STREAM_EXPIRED
    over 10 s: execute 15.047 s, connect 21.004 s          | over 10 s: none
    driver errors: 1 × STREAM_EXPIRED, 1 × tcp connect error | driver errors: none
    libsql verdict: …
    ```
    The client count is distinct non-None `client` values, and connects are records with `op == "connect"`. The `(client idle …)` part is omitted when `idle` is None. ` -> {error}` appears only if the slowest call has one. With zero records, emit `calls: 0` and the verdict line only.
  - Docstring on `_diagnostics`: prints method names, durations and marker labels only, never SQL, parameters or whole messages (PRD 9.2, P4).
- **Mirror**: `#:` constants (`tests/conftest.py:71-103`). Classification by text (`app/db/database.py:413-428`).
- **Validate**: `py -c "import tests.conftest"` is not enough because of the bootstrap order, so run `py -m pytest tests/test_db_isolation_harness.py -q -m "not db"` and expect the existing tests green.

### Task 2: `_RecordedClient` and `_recorded_connect`

- **File**: `tests/conftest.py`
- **Action**: UPDATE
- **Implement**:
  - `_client_numbers = itertools.count(1)`.
  - `class _RecordedClient`: `__init__(self, real)` sets `_real`, `_number = next(_client_numbers)` and `_last_used = time.monotonic()`. `__getattr__(name)`: `attr = getattr(self._real, name)`, and a non-callable is returned as-is. Otherwise it returns `timed(*args, **kwargs)`: `started = time.monotonic()`, `idle = started - self._last_used`, `error = None`. Then `try: return attr(...)`. `except Exception as exc: error = _infra_error(str(exc)); raise`. `finally: self._last_used = time.monotonic(); _record(_Call(name, self._last_used - started, self._number, idle, error))`.
  - Docstring: forwards every attribute and re-raises the original object, because `_translated()` and `_is_dead_stream()` classify the message, so a wrapped exception would change behaviour (R4). Idle time is what showed the brief's failures were not idle streams (0–0.45 s). Records go to the *running* test, because `_shared_client()` caches across tests. No `__setattr__` forwarding: nothing in `app/` assigns to a client (checked with `grep`).
  - `_recorded_connect(real) -> Callable`: `connect(*args, **kwargs)` times `real(*args, **kwargs)`. On success it wraps the result in `_RecordedClient`, records `_Call("connect", s, client._number, None, None)` and returns the client. On exception it records `_Call("connect", s, None, None, _infra_error(str(exc)))` and does a bare `raise`.
- **Mirror**: `tests/test_db.py:4057-4080` (`_StandInClient`).
- **Validate**: same as Task 1.

### Task 3: Install in `_storage_policy` and add the report section

- **File**: `tests/conftest.py`
- **Action**: UPDATE
- **Implement**:
  - `db` branch (`tests/conftest.py:416-420`) becomes:
    ```python
    monkeypatch.setattr(settings, "DATABASE_URL", request.getfixturevalue("_libsql_endpoint"))
    monkeypatch.setattr(libsql, "connect", _recorded_connect(libsql.connect))
    _begin(item)
    try:
        _reset_database()
        yield
    finally:
        _end(item)
    return
    ```
    The session probe in `_libsql_endpoint` runs before the wrapper exists and is not recorded, as the story says.
  - `_storage_policy` docstring: one paragraph on the recorder (P7 ordering; tests that patch `libsql.connect` themselves layer over it and see their own fake, unrecorded).
  - `pytest_runtest_makereport`: after the existing `_REFUSED` block and before `return report`:
    ```python
    if report.failed and item.get_closest_marker(_DB_MARKER) is not None:
        report.sections.append(("libsql diagnostics", _diagnostics(item.stash.get(_RECORDS, []))))
    ```
    Replace the docstring's "STORY-005 adds…" sentence with the section's contract: which phases it covers, that it is absent on a pass, and the `libsql verdict: ` prefix for `grep`. It must also say that diagnostics **may be partial** after `monkeypatch.undo()`, which removes the wrapper for the rest of that test (the seven sites in `tests/test_db.py`), and that a client built while undone is never recorded.
- **Validate**: `py -m pytest tests/test_db_isolation_harness.py tests/test_conftest_fixtures.py -q` green.

### Task 4: In-process self-tests

- **File**: `tests/test_db_isolation_harness.py`
- **Action**: UPDATE. New section `# --- The recorder and the verdict (STORY-005) ---` before the child-run sections. Import `_Call`, `_RECORDS`, `_RecordedClient`, `_STALL_SECONDS`, `_diagnostics`, `_verdict` and the conftest module itself (`from tests import conftest as harness`) for `_current`.
- **Implement** (records fabricated, no real stalls):
  - `_verdict` table: no records, then dead stream, then `tcp connect error` on `connect`, then `os error 10060`, then a ≥ 10 s call without error, then all-fast. One case shows an error beating a slower error-free stall (rule priority). One shows that 9.99 s is not a stall. Exact strings asserted, em dash included.
  - `_diagnostics`: counts line (`on 2 clients, 1 connect`), idle shown on the slowest line, `over 10 s: none` / `driver errors: none`, the last line starts `libsql verdict: `, and zero records gives the `no driver calls recorded` verdict.
  - Redaction and no-SQL: `_infra_error("Hrana: `http error: … ?authToken=s3cret … tcp connect error …`")` returns `tcp connect error`. Feed a `_RecordedClient` whose fake `execute` raises `ValueError` with that text and SQL text in the message. The rendered section contains neither `s3cret` nor the SQL string.
  - Proxy: a non-callable attribute is forwarded. A fake whose `execute` raises `ValueError("Hrana: … STREAM_EXPIRED …")`: `pytest.raises(ValueError)` gets `excinfo.value is` the same object, and the item's records end in `error == "STREAM_EXPIRED"`.
  - Current-item sink: two `SimpleNamespace(stash=pytest.Stash())` items. One proxy is called under A, then `monkeypatch.setattr(harness, "_current", B)` and it is called again. Each item holds exactly its own call. With `_current = None`, a call forwards and records nothing.
  - `_end(other)` does not clear a pointer set for a different item.
- **Validate**: `py -m pytest tests/test_db_isolation_harness.py -q` green.

### Task 5: `pytester` child runs with a fake driver

- **File**: `tests/test_db_isolation_harness.py`
- **Action**: UPDATE
- **Implement**: `_FAKE_DRIVER_PRELUDE` has a fake cursor/client good enough for `_Connection`, `_Cursor` and `_drop_every_table_and_index()` (check `app/db/database.py:300-350` for exactly which cursor methods are needed). It also has a module-level switch to raise a given `ValueError` text from `execute`, and `libsql.connect = _fake_connect` assigned at import, so the recorder wraps it (P8). The `_libsql_endpoint` override returns `http://127.0.0.1:9`. Run each child through `_run_child(..., prelude=_FAKE_DRIVER_PRELUDE)`. Cases:
  1. A failing `db` test (`get_connection()` then `assert False`): `failed=1`, output contains `libsql diagnostics`, `calls: `, `1 connect` and `libsql verdict: no infrastructure signal (`.
  2. A passing `db` test, run with `-rA` added (extend `_run_child` with `*args`): `passed=1`, `libsql diagnostics` absent.
  3. `STREAM_EXPIRED` raised during `call`: verdict `likely infrastructure — execute took ` … ` and ended in STREAM_EXPIRED`.
  4. Fake connect raises the `tcp connect error … (os error 10060)` text containing `authToken=s3cret`: `errors=1` at setup, verdict names `connect`, and `s3cret` does not appear in the section. Because `_assert_no_network` would reject `10060`, do not call it for this case.
  5. A fixture whose **teardown** hits `STREAM_EXPIRED`: `passed=1, errors=1`, `ERROR at teardown`, and the section shows the teardown's call.
  6. A non-`db` failing test: no section (the guard path is untouched).
  - Also run case 3 with the child's output piped (`runpytest_subprocess` already pipes) and assert the verdict line survives intact. This covers P6.
- **Validate**: `py -m pytest tests/test_db_isolation_harness.py -q` green, and `-m "not db"` green with Docker **stopped**, because the children use the fake driver.

### Task 6: AC 5 timing and patched-connect regression

- **Action**: none to code
- **Implement**: run Task 0's command twice with the recorder in place. Compare counts (must be equal) and wall time (best-of-two within 10%). Spot-run the `_counting_connect` tests and the seven `monkeypatch.undo()` tests, which are all in `test_db.py` and covered by the pair. Record them in the report.
- **Validate**: counts identical to Task 0, and timing within 10%. If not, profile `_RecordedClient.__getattr__`. One closure per attribute access is expected to be negligible against a network round-trip.

### Task 7: Full suite

- **Action**: none to code
- **Implement**: in the background, `py -m pytest tests/ -q -p no:cacheprovider`, about 5.5 min. Rerun any `db` errors alone. Each failing `db` test's output should now carry a verdict line, so note it, which is the first real use of the feature. Expected: 3,883 + N new tests collected, 3,856 + N passing, 27 skipped (STORY-001 baseline as carried forward by STORY-004's P5 convention).
- **Validate**: counts as expected, every remaining failure an infrastructure verdict that passes on rerun, and `git diff main -- <six PRD-006 suites>` empty.

---

## End-to-End Tests

- [ ] Child run: failing `db` test shows `----- libsql diagnostics -----` and `libsql verdict: ` (Task 5.1)
- [ ] Child run: passing `db` test with `-rA` shows no section (Task 5.2)
- [ ] Child runs: STREAM_EXPIRED in call, connect error in setup, STREAM_EXPIRED in teardown each produce the right verdict (Task 5.3–5.5)
- [ ] `grep "libsql verdict"` over a full-run log finds one line per failing `db` test (Task 7)
- [ ] `-m "not db"` with Docker stopped is still green (Task 5 validate)

---

## Validation

```bash
py -m pytest tests/test_db_isolation_harness.py tests/test_conftest_fixtures.py -q
py -m pytest tests/test_db.py tests/test_conftest_fixtures.py -q -p no:cacheprovider   # x2, timed
py -m pytest tests/ -m "not db" -q                                                    # Docker stopped
py -m pytest tests/ -q -p no:cacheprovider                                            # full, background
git diff main --stat -- app/
```

---

## Risks

| Risk | Mitigation |
|------|------------|
| Proxy changes driver behaviour (R4) | Forwards every attribute, re-raises the same object (asserted with `is`), and has no `__setattr__` because nothing assigns to a client. Task 6 compares counts. |
| `→` / em dash mangled in cp1252 output | P6, plus a piped child assertion (Task 5). |
| Pointer leaks into the next test after a setup failure | `try/finally` around reset and `yield` (P7), plus a unit test of `_end`. |
| Timing noise from libSQL stalls masks the 10% comparison | Best of two runs on each side, and a restart of the container before a rerun (memory: shared-DB flakes). |
| Another session resets the shared container mid-run | Rerun the errored files only. In-process and child tests need no server. |

---

## Acceptance Criteria

(Copied from story `STORY-005`)

- [ ] Given a `db` test, when it runs, then every client `libsql.connect` returns is a `_RecordedClient` that forwards every attribute, times every method call (including `connect` itself) and re-raises the driver's **original** exception object. Calls are recorded into the *currently running* test's sink, including on a client built by an earlier test and cached by `_shared_client()`.
- [ ] Given a `db` test that fails in `setup`, `call` or `teardown`, when its report is produced, then it has a `libsql diagnostics` section listing call and client counts, the slowest call (with the client's idle time before it), every call ≥ 10 s, every driver error matching `database._DEAD_STREAM`, `tcp connect error` or `os error 10060`, and a last line starting `libsql verdict: `. A passing test's report has no such section.
- [ ] Given `_verdict(records)`, when unit-tested, then it returns the four outcomes in PRD Section 6.6's table.
- [ ] Given driver error text, when it is written into the section, then it has passed through `database._redacted()`, and the section contains no SQL text or parameters.
- [ ] Given `tests/test_db.py` and `tests/test_conftest_fixtures.py`, when run with and without the recorder, then both pass with the same counts and within 10% of the same wall time (recorded in the report). Tests that patch `libsql.connect` themselves and the seven `monkeypatch.undo()` sites still pass, and the full suite's counts equal STORY-001's baseline.
- [ ] All tasks completed
- [ ] Follows existing patterns
