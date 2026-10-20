---
story: STORY-004
prd: PRD-014-test-suite-db-isolation
slug: docker-free-run
title: "Lazy _libsql_endpoint: pytest -m \"not db\" passes with Docker stopped"
type: REFACTOR
complexity: LOW
epic_branch: epic/PRD-014-test-suite-db-isolation
created: 2026-10-20
---

# Plan: Lazy `_libsql_endpoint` — `pytest -m "not db"` passes with Docker stopped

## Summary

Drop `autouse=True` from the session-scoped `_libsql_endpoint` in `tests/conftest.py` so the reachability probe runs only when a `db` test (through `_storage_policy`'s `db` branch) or a storage fixture (`database_url`, `database_url_factory`) asks for it. Its `pytest.exit(..., returncode=1)` message stays as it is. The docstring gains a note that, with Docker stopped, a full run now exits at the first `db` test instead of before the first test (PRD 6.5).

The story notes call this a one-line change, but STORY-001 and STORY-003 both found that it is not enough on its own. `tests/test_chat_shell.py`'s module-scoped `probe` (21 non-`db` tests) starts a child that imports `chat_ui.chat_ui.index`. That import runs `init_db()` against the inherited `DATABASE_URL`, which is `_ENDPOINT`, so with Docker stopped those 21 tests fail. The fix makes them storage-free: add `DB_BOOTSTRAP_ENABLED=false` to the probe's env, as `tests/test_reports_pages.py:300` already does. Two `pytester` self-tests in `tests/test_db_isolation_harness.py` prove the laziness against the real conftest with `HARNESS_TEST_LIBSQL_URL=http://127.0.0.1:9`. Then a manual run with Docker Desktop stopped, and a full run with it started, close the ACs.

## User Story

As a harness developer
I want `pytest -m "not db"` to run with Docker Desktop stopped
So that I have a fast, reliable loop for the tests that never needed storage

## Story Reference

- Story file: `.agents/stories/PRD-014-test-suite-db-isolation/STORY-004-docker-free-run.md`
- PRD: `.agents/PRDs/PRD-014-test-suite-db-isolation/PRD.md` (sections 6.5, 7 F4, 10, 11)
- Upstream evidence: STORY-001 report, *Follow-ups* (`test_chat_shell.py` will break `-m "not db"`); STORY-003 report line 116 (still open)

## Metadata

| Field | Value |
|-------|-------|
| Type | REFACTOR (test harness only; no `app/` change) |
| Complexity | LOW |
| Systems Affected | `tests/conftest.py`, `tests/test_db_isolation_harness.py`, `tests/test_chat_shell.py` |
| Story | STORY-004 |
| PRD | PRD-014-test-suite-db-isolation |
| Epic Branch | `epic/PRD-014-test-suite-db-isolation` (commit directly on this branch) |
| Depends on | STORY-003 ✅ (`241fae0`) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | The story says "Skills: none applicable". `.agents/skills/` has only `frontend-design`, which has nothing to do with test-harness work | — |

---

## Decisions taken in this plan

| # | Decision | Why |
|---|----------|-----|
| P1 | Fix `test_chat_shell.py`'s `probe` with `DB_BOOTSTRAP_ENABLED=false` in its child env. Do **not** declare it in `_DB_NODEIDS` | The probe is about layout, not storage. `test_reports_pages.py:300` is the existing precedent, with the same comment. Declaring it would make 21 layout tests pay a reset and need Docker for no reason. The file is not in `_UNMODIFIED_SUITES` (`tests/test_untouched_app.py:71-78`), so the edit is allowed. This is the option both upstream reports recommend |
| P2 | Leave `_slot_with_flag` (`tests/test_chat_shell.py:613`) alone unless Task 4 shows it fails with Docker stopped | STORY-001 reran the module against a dead URL, and only the 21 `probe` users failed. `_FLAG_SCRIPT` imports component modules, not the app module |
| P3 | The new self-tests use a prelude **without** the `_libsql_endpoint` override | The existing `_CHILD_PRELUDE` overrides the fixture, so a child built on it would pass whether or not the real fixture is lazy. These two tests must run the real fixture |
| P4 | The `db` arm asserts on `result.ret == 1` and the stdout message, not `assert_outcomes` | Checked in scratch before writing this plan: `pytest.exit` from a lazily requested session fixture prints `!! _pytest.outcomes.Exit: <msg> !!!` on stdout and returns 1. Earlier tests still pass, later ones never run, and there is no normal outcome summary to parse |
| P5 | Count parity in AC 4 means "STORY-003's after-run plus this story's new tests" | STORY-002 and STORY-003 read "equals STORY-001's baseline" the same way. Expected: 3,881 + 2 = **3,883 collected**, 27 skipped, the rest passing apart from known flakes that pass on rerun |

---

## Patterns to Follow

### The fixture, as it stands (the only line that changes is the decorator)
```python
# SOURCE: tests/conftest.py:327-346
@pytest.fixture(scope="session", autouse=True)
def _libsql_endpoint() -> str:
    """Proves the endpoint is reachable once, and says how to start it if not.

    A hard failure rather than a skip: a suite that quietly stops exercising
    storage still reports green, which is worse than a red one.
    """
    try:
        libsql.connect(_ENDPOINT).execute("SELECT 1").fetchone()
    except Exception as exc:  # noqa: BLE001 -- any failure means "no database"
        pytest.exit(
            f"The libSQL dev server at {_ENDPOINT} is unreachable ({exc}).\n"
            ...
            returncode=1,
        )
    return _ENDPOINT
```

### Who already requests it (nothing new needs to)
```python
# SOURCE: tests/conftest.py:404-406  (_storage_policy, db branch only)
if item.get_closest_marker(_DB_MARKER) is not None:
    monkeypatch.setattr(settings, "DATABASE_URL", request.getfixturevalue("_libsql_endpoint"))
# SOURCE: tests/conftest.py:461   def database_url(_libsql_endpoint, monkeypatch)
# SOURCE: tests/conftest.py:493   def database_url_factory(_libsql_endpoint)
```
The non-`db` branch uses the module constant `_ENDPOINT` (`conftest.py:408`) and never the fixture, so a `not db` session never instantiates it.

### A storage-free app import in a child
```python
# SOURCE: tests/test_reports_pages.py:293-301
env={
    **os.environ,
    "PYTHONPATH": os.pathsep.join(_PYTHONPATH),
    ...
    # Importing the app calls init_db(); this probe is about pages, and
    # must not need (or write to) a database.
    "DB_BOOTSTRAP_ENABLED": "false",
},
```
`init_db()` returns before `check_database_reachable()` when the flag is off (`app/db/database.py:713-716`).

### Child runs of the real conftest
```python
# SOURCE: tests/test_db_isolation_harness.py:233-238
def _run_child(pytester, monkeypatch, body: str):
    monkeypatch.setenv("PYTHONPATH", str(_REPO_ROOT))
    monkeypatch.setenv("HARNESS_TEST_LIBSQL_URL", "http://127.0.0.1:9")
    pytester.makeconftest((_REPO_ROOT / "tests" / "conftest.py").read_text(encoding="utf-8"))
    pytester.makepyfile(test_child=_CHILD_PRELUDE + textwrap.dedent(body))
    return pytester.runpytest_subprocess("-p", "no:cacheprovider")
```
Test naming in this file is a sentence about behaviour (`test_a_test_that_touches_no_storage_does_not_hear_from_the_guard`). Section banners are `# --- <name> ---…`. The docstrings say *why*, in the conftest's voice.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `tests/conftest.py` | UPDATE | Drop `autouse=True` from `_libsql_endpoint`. Extend its docstring (who instantiates it, full run with Docker stopped exits at the first `db` test) |
| `tests/test_chat_shell.py` | UPDATE | `probe()` child env gets `DB_BOOTSTRAP_ENABLED="false"` plus the one-line reason, mirroring `test_reports_pages.py:300` |
| `tests/test_db_isolation_harness.py` | UPDATE | `_run_child` takes a `prelude`. Add `_LAZY_PRELUDE` and two self-tests under a new `# --- The lazy endpoint ---` section. Correct the `_CHILD_PRELUDE` comment and the module docstring's "add their tests … as they land" |
| `.agents/reports/PRD-014-test-suite-db-isolation/STORY-004-docker-free-run.report.md` | CREATE (by `/implement`) | Commands, output tails, wall times, counts |

No `app/` change. No PRD-006 suite is touched (`git diff main -- $(_UNMODIFIED_SUITES)` must stay empty).

---

## Tasks

Execute in order. Each task is atomic and verifiable. Python is `C:\Users\tobip\.venvs\harness-ai\Scripts\python.exe` (no Python on PATH). Run from the repo root.

### Task 0: Pre-flight

- Confirm the branch is `epic/PRD-014-test-suite-db-isolation` and the working tree is clean apart from this plan and the story/index edits.
- Start Docker Desktop and `docker start harness-libsql-dev` if needed.
- Record `pytest --collect-only -q -m "not db"` and `-m db` counts (expected 3,881 total before this story). These are the "before" numbers for AC 3.
- **Validate**: `python -m pytest --collect-only -q -m "not db" tests/ | tail -1` and the same with `-m db` add up to the full collect count.

### Task 1: Make `_libsql_endpoint` lazy

- **File**: `tests/conftest.py:327-346`
- **Action**: UPDATE
- **Implement**:
  - `@pytest.fixture(scope="session", autouse=True)` → `@pytest.fixture(scope="session")`.
  - Leave the body, the `pytest.exit` message and `returncode=1` byte-for-byte unchanged.
  - Extend the docstring with a paragraph in the file's voice. **Since PRD-014 STORY-004 it is not autouse.** Only `_storage_policy`'s `db` branch and the storage fixtures (`database_url`, `database_url_factory`) instantiate it, so a `-m "not db"` session never probes and runs with Docker stopped. The cost is that a full run with Docker stopped exits at the *first `db` test*, not before the first test. The non-`db` tests that ran before it have already reported, and the rest never run. It is still a hard exit and still names the fix.
- **Mirror**: the "Since PRD-014 STORY-003 …" paragraph in `_storage_policy`'s docstring (`conftest.py:388-397`).
- **Validate**: `python -m pytest tests/test_db_isolation_harness.py tests/test_conftest_fixtures.py -q -p no:cacheprovider` → all pass (Docker running).

### Task 2: Make `test_chat_shell.py`'s probe storage-free

- **File**: `tests/test_chat_shell.py:211-229` (`probe`)
- **Action**: UPDATE
- **Implement**: add `DB_BOOTSTRAP_ENABLED="false",` to the `dict(os.environ, ...)` call with a two-line comment: importing `chat_ui.chat_ui` calls `init_db()`; this probe is about layout and must not need (or write to) a database. Keep `DATABASE_URL=` as is, because `Settings()` still requires a value.
- **Mirror**: `tests/test_reports_pages.py:298-300`.
- **Validate**: `python -m pytest tests/test_chat_shell.py -q -p no:cacheprovider` → 38 passed, with Docker running. Docker-stopped proof comes in Task 4.

### Task 3: Self-tests for the lazy endpoint

- **File**: `tests/test_db_isolation_harness.py`
- **Action**: UPDATE
- **Implement**:
  1. `_run_child(pytester, monkeypatch, body: str, prelude: str = _CHILD_PRELUDE)`, using `prelude + textwrap.dedent(body)`. Existing callers are unchanged.
  2. A `_LAZY_PRELUDE` with only `import pytest` and `from app.config import settings`, and **no** `_libsql_endpoint` override, with a `#:` comment saying why (decision P3).
  3. Reword the `_CHILD_PRELUDE` comment (lines 207-210). Since STORY-004 no non-`db` child would probe anyway, so the override is now belt-and-braces: it keeps a child's `db` arm (if one is ever added) off the network. The dead-port env var still makes any real connect fail loudly.
  4. New section `# --- The lazy endpoint, in a child run of the real conftest ---` with:
     - `test_a_test_that_is_not_db_runs_with_the_endpoint_unreachable`: body `def test_it(): assert settings.DATABASE_URL == "http://127.0.0.1:9"` with `_LAZY_PRELUDE`. Assert `result.assert_outcomes(passed=1)` and `"is unreachable" not in result.stdout.str()`.
     - `test_a_db_test_exits_the_run_with_the_unreachable_message`: body `@pytest.mark.db\ndef test_it(): pass` with `_LAZY_PRELUDE`. Assert `result.ret == 1`. `result.stdout.fnmatch_lines(["*The libSQL dev server at http://127.0.0.1:9 is unreachable*"])` and `"Start it with:" in result.stdout.str()`. Assert `"1 passed" not in` the output (decision P4).
  5. Module docstring: "the lazy endpoint and the recorder add their tests to this file as they land" → the lazy endpoint's are here (STORY-004), and the recorder adds its own when it lands.
- **Mirror**: `test_a_test_that_touches_no_storage_does_not_hear_from_the_guard` (`test_db_isolation_harness.py:357-361`), `_assert_no_network`.
- **Validate**: `python -m pytest tests/test_db_isolation_harness.py -q -p no:cacheprovider` → all pass. The `db`-arm child should finish in a few seconds, because port 9 refuses fast. If it takes more than ~10 s, check that the URL is `127.0.0.1`, not `localhost`.
- **Negative check (scratch, not committed)**: temporarily restore `autouse=True` and rerun only the two new tests. `..._not_db_runs_with_the_endpoint_unreachable` must FAIL (the run exits before the test). Revert, then confirm with `git diff tests/conftest.py`.

### Task 4: Docker-stopped `not db` run (AC 3)

- **Action**: manual run, recorded in the report.
- **Implement**:
  1. Stop the container, then quit Docker Desktop (tray → Quit, or `taskkill /IM "Docker Desktop.exe"` after asking the user if another session might be using it; see the memory note about shared containers). Confirm with `docker info` failing and with `curl -s -m 2 http://127.0.0.1:8080` refusing.
  2. Run `python -m pytest tests/ -m "not db" -q -rfEs -p no:cacheprovider` and time it (shell `date` around it plus pytest's own line).
  3. Expect **0 failed, 0 errors**. Expected passed = `not db` collected (Task 0) minus the `not db` skips (the 25 `test_reports_e2e.py`, 1 benchmark and 1 slow smoke, if they are non-`db`; take the real figure from `-rs`). Also `grep -c "reached storage ("` = 0.
  4. If collection hangs or errors, look for a module that builds a client at import time (story note). If a non-`db` test fails on the network, find the child process or import behind it, fix it the way Task 2 did, or declare it, and record which you chose.
- **Validate**: report records the command, the last ~15 lines of output, the wall time, and the count arithmetic.

### Task 5: Docker running, full suite (AC 4)

- **Action**: restart Docker Desktop and `docker start harness-libsql-dev`, then run `python -m pytest tests/ -q -rfEs -p no:cacheprovider` in the background (about 5.5 min).
- **Expect**: 3,883 collected (3,881 + 2 new), 27 skipped, the rest passing. Rerun any `STREAM_EXPIRED` / `10060` / bare `/query` 500 failure alone and count it as a pass only if it passes then (memory: shared-DB flakes). `grep -c "reached storage ("` = 0.
- **Also**: `python -m pytest --collect-only -q -m db tests/ | tail -1` is unchanged from Task 0. The new `db`-arm test runs in a child, so it adds nothing to the parent's `db` set.
- **Validate**: `git diff main -- tests/test_admin_auth.py tests/test_audit_router.py tests/test_stats_router.py tests/test_db.py tests/test_route_reservations.py tests/test_chat_state.py` is empty.

---

## End-to-End Tests

- [ ] `HARNESS_TEST_LIBSQL_URL=http://127.0.0.1:9`, `pytester` child, one non-`db` test → 1 passed, no "unreachable" in the output (automated, Task 3)
- [ ] The same, one `db` test → `ret == 1`, "The libSQL dev server at http://127.0.0.1:9 is unreachable" plus "Start it with:" (automated, Task 3)
- [ ] With `autouse=True` temporarily restored, the non-`db` child test fails, which proves the test can catch a regression (scratch, Task 3)
- [ ] Docker Desktop stopped: `pytest tests/ -m "not db" -q` → 0 failed, 0 errors, pass count as computed (manual, Task 4)
- [ ] Docker Desktop stopped, `test_chat_shell.py` alone → 38 passed (falls out of Task 4)
- [ ] Docker running: full suite → 3,883 collected, 27 skipped, the rest passing after flake reruns (Task 5)

---

## Validation

```bash
PY=/c/Users/tobip/.venvs/harness-ai/Scripts/python.exe
$PY -m pytest tests/test_db_isolation_harness.py tests/test_conftest_fixtures.py tests/test_chat_shell.py tests/test_untouched_app.py -q -p no:cacheprovider
grep -n '@pytest.fixture(scope="session")' tests/conftest.py   # _libsql_endpoint, no autouse
grep -n 'autouse=True' tests/conftest.py                       # only _storage_policy, _default_pattern_policy, _default_pii_policy
# Docker stopped:
$PY -m pytest tests/ -m "not db" -q -rfEs -p no:cacheprovider
# Docker running:
$PY -m pytest tests/ -q -rfEs -p no:cacheprovider
```

---

## Risks

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| A non-`db` test other than `test_chat_shell.py`'s probe needs the network through a child, which STORY-001's dead-URL rerun missed because it excluded `test_spike_pii_placeholders.py` | Low | Task 4 is the real check. Fix like Task 2, or declare, and record it in the report |
| A module builds a libSQL client at import, so collection fails with Docker stopped | Low (STORY-001 found none) | Task 4, step 4. Collection errors show up as errors in `-q -rfEs` |
| A refused connect on Windows is slow (~2 s on `localhost`), which slows the `db`-arm child | Medium | Use `127.0.0.1:9`, as in the story note and the existing `_CHILD_PRELUDE` |
| Quitting Docker Desktop disrupts another Claude session sharing `harness-libsql-dev` | Medium | Ask before quitting Docker Desktop. Restart it and the container straight after Task 4 |
| `pytest.exit` output format changes between pytest versions | Low | Match with `fnmatch_lines` on the message text, not on the `!!` banner |
| The `_CHILD_PRELUDE` override hides a regression | Removed | The new tests use `_LAZY_PRELUDE` (P3), and the scratch negative check proves they catch it |

---

## Acceptance Criteria

(Copied from story `STORY-004`)

- [ ] Given `_libsql_endpoint`, when `conftest.py` is read, then it is `scope="session"` without `autouse=True`. It is instantiated only by `_storage_policy`'s `db` branch and by the storage fixtures, and it keeps its `pytest.exit(...)` message and `returncode=1`.
- [ ] Given `HARNESS_TEST_LIBSQL_URL` pointing at a port with nothing listening, when a `pytester` subprocess run collects one non-`db` test, then it passes. When it collects one `db` test, then the run exits with the "libSQL dev server ... is unreachable" message.
- [ ] Given Docker Desktop stopped, when `pytest tests/ -m "not db" -q` runs, then it reports 0 failed and 0 errors. The pass count equals STORY-001's non-storage count adjusted by STORY-003's declarations, and the report records the command, output tail and wall time.
- [ ] Given Docker running, when the full suite runs, then total and passing counts equal STORY-001's baseline (read as STORY-003's 3,881 + this story's 2 new tests; decision P5).
- [ ] All tasks completed
- [ ] `git diff main` over the six PRD-006 suites is empty
- [ ] Follows existing patterns (`test_reports_pages.py:300` for the probe, `_run_child` for the self-tests)
