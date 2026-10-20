---
story: STORY-001
prd: PRD-014
slug: storage-characterization
title: "Characterize the suite's storage use: baseline run, driver calls per test, census and undeclared-storage list"
type: REFACTOR
complexity: LOW
epic_branch: epic/PRD-014-test-suite-db-isolation        # all stories commit here, no per-story branch
created: 2026-10-20
---

# Plan: Characterize the suite's storage use

## Summary

This story measures and changes nothing. It runs the full suite twice on the epic branch's base and writes one report.

- **Run A (baseline):** the plain suite, nothing loaded. It gives the collected, passed, failed, errored and skipped counts and the wall time. Every later PRD-014 story compares against these numbers.
- **Run B (instrumented):** the same suite with an uncommitted scratch plugin loaded through `-p`. The plugin wraps `libsql.connect`, so every client it returns, and every cursor those clients hand out, is a counting proxy. It charges each call to the test that is *running*, not to the test that built the client, because `_shared_client()` caches one client across tests. It also records each test's storage fixtures from `item.fixturenames`.

A small scratch script turns Run B's JSON into the report's tables: driver calls per run, the census per module, mixed modules, and **the list of tests that issue driver calls without a storage fixture**. That list is STORY-002's seed for `_DB_NODEIDS` and STORY-003's input. Two read-only audits finish the report: every autouse fixture, and every subprocess-spawning test that requests no storage fixture.

The only committed file is the report. The plugin and the analysis script live outside the repo. Their source is quoted in the report's appendix so STORY-007 can rerun the same instrument (see Design, D-3).

## User Story

As the PRD-014 implementer
I want to know which tests reach storage and how, measured on untouched `main`
So that the marker, the guard and the explicit list are built from data, and the "counts unchanged" criteria have a baseline

## Story Reference

- Story file: `.agents/stories/PRD-014-test-suite-db-isolation/STORY-001-storage-characterization.md`
- PRD: `.agents/PRDs/PRD-014-test-suite-db-isolation/PRD.md` (Sections 4 *Baseline*, 6.2, 6.6, 7/F1, 11 *MVP definition*, 14 R1–R3)

## Metadata

| Field | Value |
|-------|-------|
| Type | REFACTOR safety net (story type `technical`: measurement only) |
| Complexity | LOW |
| Systems Affected | None. One new report under `.agents/reports/`. No file under `tests/`, `app/` or `chat_ui/` changes (AC 6) |
| Story | STORY-001 |
| PRD | PRD-014 |
| Epic Branch | `epic/PRD-014-test-suite-db-isolation` (commit directly on this branch. **It does not exist yet**, and Task 0 creates it from `main`) |

---

## Skills In Use

None. `.agents/skills/` holds only `frontend-design`, which covers UI. The story says the same (`skills: []`, "No UI surface").

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | — | — |

---

## Findings from Exploration

**F-1. `main` does not contain PRD-013 yet.** When this plan was written, `main` was at `b184614` (the PRD-012 merge). The PRD-013 epic (`c3f0ed5`, 43 test files changed, +7,784 lines) was not merged. The PRD's "Evidence" section says "verified against `main` @ `c3f0ed5`", but that commit is the PRD-013 epic tip. `tests/conftest.py` is identical in both, so every conftest line reference in the PRD holds. The test counts do not: a baseline on `b184614` would miss every PRD-013 test, and PRD-014 is meant to land on top of it. **Task 0 gates on this** (see Risks, R-1).

**F-2. The conftest is imported as `tests.conftest`.** `tests/__init__.py` exists, and five modules import from it by that name (`tests/test_conftest_fixtures.py:28` imports `_reset_database`; `test_admin_shell.py:48`, `test_chat_ui_startup_guard.py:39`, `test_render_invariants.py:69` and `test_two_instance_smoke.py:84` import `child_db_env`).

**F-3. The driver is reached through one module attribute.** `app/db/database.py:12` does `import libsql` and calls `libsql.connect(...)` at `:122` (`_shared_client`) and `:168` (`_proved`). `tests/conftest.py:59` does the same, at `:177` (`_libsql_endpoint`). The name is looked up at call time, so replacing `libsql.connect` on the module once, in `pytest_configure`, catches every construction, including the ones inside the cached client.

**F-4. Cursors issue round trips too.** `_Connection.cursor()` (`app/db/database.py:325-326`) returns `_Cursor(self._client.cursor())`, and `_Cursor.execute` (`:274`) calls the driver cursor's `execute`. A proxy that counted only connection methods would miss those statements, so the cursor returned by `cursor()` is wrapped as well. The driver connection's surface is `close, commit, cursor, execute, executemany, executescript, in_transaction, isolation_level, rollback, sync` (`app/db/database.py:1268`).

**F-5. Where the reset's calls come from.** `_never_the_configured_database` (`tests/conftest.py:192-220`) calls `_reset_database()` (`:119-156`) by its global name. The cleanest way to tell its calls apart from the test's own is a `pytest_fixture_setup` hookwrapper that keeps a stack of the fixture names being set up (see D-2). The story's note suggests replacing `tests.conftest._reset_database` from the plugin instead. It says "e.g.", and the fixture stack covers the same case plus `_libsql_endpoint`'s probe. Direct calls to `_reset_database` from `test_conftest_fixtures.py` keep counting as that test's own calls, which is correct.

**F-6. Autouse fixtures in `tests/conftest.py`:** `_libsql_endpoint` (`:169`, session, connects), `_never_the_configured_database` (`:192`, resets), `_default_pattern_policy` (`:223`, settings and `pattern_config._policy` only) and `_default_pii_policy` (`:249`, `pii_policy._policies` only). Autouse fixtures in test modules are found in Task 5 by `grep -n "autouse=True" tests/test_*.py`.

**F-7. Subprocess candidates, pre-sorted by grep** (on the PRD-013 tip, so re-run on the base in Task 6). These files spawn a subprocess and **mention no storage fixture at all**, so every subprocess test in them must be read: `test_chat_components_import.py`, `test_chat_shell.py`, `test_ground.py`, `test_measure_pii_latency.py`, `test_measure_usage_latency.py`, `test_register.py`, `test_reports_e2e.py`, `test_reports_pages.py`, `test_session_rail.py`, `test_summary.py`, `test_untouched_app.py`. These mix storage fixtures and subprocesses, so only their non-storage subprocess tests need reading: `test_admin_shell.py`, `test_chat_ui_startup_guard.py`, `test_pii_redaction_integration.py`, `test_query_session_id.py`, `test_render_invariants.py`, `test_spike_pii_placeholders.py`, `test_two_instance_smoke.py`, `test_usage_view.py`. Grep found no subprocess call in `test_conftest_fixtures.py`, `test_context_limit_bubble.py`, `test_history_off_integration.py` or `test_usage_bubble.py`. Confirm each in Task 6 and record "no subprocess". `test_measure_usage_latency.py` drives `scripts/measure_usage_latency.py`, which writes usage rows, so expect it on the undeclared list unless its child is pointed elsewhere.

**F-8. The six PRD-006 suites** are `tests/test_untouched_app.py:70-77` `_UNMODIFIED_SUITES`: `test_admin_auth.py`, `test_audit_router.py`, `test_stats_router.py`, `test_db.py`, `test_route_reservations.py`, `test_chat_state.py`.

**F-9. Environment** (harness-ai test-env memory). Python is only in the venv `C:\Users\tobip\.venvs\harness-ai\Scripts\python.exe`. Docker Desktop is often stopped, so start it, then `docker start harness-libsql-dev`. The spaCy models `en_core_web_lg` and `en_core_web_sm` must both be present. Another session on this machine may share the container, so before the two full runs, check that no other harness session is running tests against it.

---

## Patterns to Follow

### Report layout

```
// SOURCE: .agents/reports/PRD-013-audit-and-usage-limits/STORY-001-audit-characterization.report.md (section headings)
## Summary / ## Tasks Completed / ## Validation Results / ## Environment / ## Files Changed /
## Deviations from Plan / ## For later stories / ## Observations (recorded, not fixed) / ## Acceptance Criteria
```

This report adds data sections between *Environment* and *Files Changed*: *Baseline run (AC 1)*, *Driver calls and census (AC 2)*, *Undeclared storage (AC 3)*, *Autouse audit (AC 4)*, *Subprocess audit (AC 5)*, and an *Appendix: scratch instrument*.

### Driver-error recognition (reused for the flake column)

```python
# SOURCE: tests/conftest.py:147-156
except ValueError as exc:
    messages = (str(exc), str(exc.__context__ or ""))
    if not any(database._is_dead_stream(message) for message in messages):
        raise
```

The plugin does not change behaviour. It records the method name and whether the error text matches `stream_expired|stream has expired|invalid baton|tcp connect error|os error 10060`, then re-raises **the same exception object** (PRD 6.6, "Exceptions pass through unchanged").

### Commit sequence

```
// SOURCE: git log main..c3f0ed5 (PRD-013's first four commits)
docs(PRD-013): PRD, stories and index; pre-PRD promoted
docs(PRD-013): STORY-001 plan
test(PRD-013): STORY-001 characterize ...
chore(PRD-013): update STORY-001 status + index; record commit SHA
```

This story's own commit is `docs(PRD-014): STORY-001 storage characterization report`, because no test changes.

---

## Design

### D-1. Two runs, not one

Run A is the plain suite, so the baseline is not run under an instrument that could change it. Run B adds the plugin. Run B's counts must match Run A's, apart from confirmed flakes. A mismatch means the proxy changed behaviour: stop and fix the plugin, never the suite.

### D-2. The scratch plugin, `storage_census.py`

Location: `$TEMP/prd014-story001/` (in PowerShell, `$env:TEMP\prd014-story001\`). That is short enough for MAX_PATH and outside the repo. Load it with `PYTHONPATH="<that dir>;."` and `-p storage_census`.

| Hook | Does |
|---|---|
| `pytest_configure` | Saves the real `libsql.connect` and replaces it with `counting_connect`, which counts `connect` and returns `_Counted(real_client)`. `_Counted.__getattr__` forwards non-callables and wraps callables. A `cursor()` result is wrapped as `_Counted` too. Each call records `(nodeid, phase, bucket, method, seconds, error_class)`. |
| `pytest_collection_modifyitems` (`trylast=True`) | For each item: `nodeid`, module path, `sorted(set(item.fixturenames) & STORAGE)`, where `STORAGE = {"temp_db", "database_url", "uninitialized_db", "database_url_factory", "db_connect"}`. |
| `pytest_runtest_protocol` (hookwrapper) | Sets the module-level `CURRENT = item.nodeid` and clears it after. A module global, not a thread-local, so `asyncio.to_thread` workers are charged to the running test. |
| `pytest_runtest_setup` / `_call` / `_teardown` (hookwrappers) | Set `PHASE`. |
| `pytest_fixture_setup` (hookwrapper) | Pushes `fixturedef.argname` onto `BUCKET` and pops it after. A call's bucket is the **outermost** autouse storage-policy fixture on the stack (`_never_the_configured_database` or `_libsql_endpoint`) if either is present, and otherwise `"test"`. Calls inside a module's own fixture count as the test's. |
| `pytest_runtest_logreport` | Records each phase's outcome. |
| `pytest_sessionfinish` | Writes `census.json` (items, outcomes, per-call aggregates per `(nodeid, bucket, method)`, calls outside any test under `"<no test>"`) to the plugin's directory. Raw per-call rows are aggregated in memory, so the file stays small. |

What counts as a **driver call**: every `libsql.connect` plus every method invoked on a driver connection or cursor. The report breaks the total down by method, so the brief's ~40,000 (definition unknown) can be compared honestly, and so can STORY-007's rerun. Local cursor reads (`fetchone`, `fetchall`, `description`) are listed in their own column and left out of the "round trips" headline.

Known blind spots, to be stated in the report: tests that replace `libsql.connect` with their own fake (`tests/test_db.py:4084` onward) record nothing for the fake, which is correct. Child processes are invisible (AC 5 covers them). A background thread still running after its test ends is charged to the next test.

### D-3. Where the instrument's source lives

AC 6 says the plugin is not committed. The `.py` files stay in `$TEMP/prd014-story001/`. Their source is pasted into the report's appendix as a fenced block, because PRD 11 requires STORY-007 to remeasure "with the same scratch plugin", and a temp file will not survive until then. A fenced block in a report cannot be loaded by `-p`, so it is not a committed plugin. If the reviewer reads AC 6 more strictly, the appendix can move to the uncommitted scratch notes without changing any number.

### D-4. The analysis script, `analyze.py` (scratch)

It reads `census.json` and the Run A JUnit XML and prints Markdown tables:

1. Totals: driver calls per run, split by bucket (`reset`, `endpoint`, `test`, `<no test>`) and by method.
2. Census: storage tests and non-storage tests, overall and per module. Modules with storage tests, modules with none, **mixed** modules. Expected about 1,090 / 2,363, 47 of 91 modules, 27 mixed (brief, 2026-10-14). Record whatever is measured.
3. **Undeclared**: tests with no storage fixture and ≥ 1 `test`-bucket call, grouped by module, with the call count, the first method, and a `PRD-006` flag when the module is in `_UNMODIFIED_SUITES`.
4. The reverse check, for information only: storage-fixture tests with zero `test`-bucket calls. These are not a defect, but STORY-002 may want them.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `.agents/reports/PRD-014-test-suite-db-isolation/STORY-001-storage-characterization.report.md` | CREATE | The only deliverable: baseline, census, undeclared list, both audits, instrument appendix |
| `.agents/stories/PRD-014-test-suite-db-isolation/STORY-001-storage-characterization.md` | UPDATE | `/implement` bookkeeping (`status`, `report`, `commit`) |
| `.agents/PRDs/PRD-014-test-suite-db-isolation/index.md` | UPDATE | Status and commit columns |
| `$TEMP/prd014-story001/storage_census.py`, `analyze.py`, `*.xml`, `*.json`, `*.log` | CREATE (scratch, never committed) | The instrument and the raw outputs |

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 0: Preflight and epic branch

- **Action**: Check the base, create the branch, commit the planning documents.
- **Implement**:
  1. `git fetch origin && git merge-base --is-ancestor c3f0ed5 origin/main`. **If PRD-013 is not in `main`, stop and ask the user** whether to (a) wait for the PRD-013 merge (recommended: the baseline must include the tests PRD-014 will land on), or (b) cut the epic from `epic/PRD-013-audit-and-usage-limits` and rebase later. Record the answer and the base SHA in the report.
  2. `git checkout main && git pull`, then `git checkout -b epic/PRD-014-test-suite-db-isolation`. The untracked PRD-014 files and the `pre-prds/README.md` edit carry over.
  3. Commit `docs(PRD-014): PRD, stories and index; pre-PRD promoted` (the PRD, the eight stories, `index.md`, `pre-prds/PRE-PRD-017-…md`, `pre-prds/README.md`), then `docs(PRD-014): STORY-001 plan`.
  4. Environment: start Docker Desktop if needed, `docker start harness-libsql-dev`, and check that both spaCy models import in the venv. Record the Python, pytest and libsql versions and `docker inspect harness-libsql-dev --format '{{.Config.Image}}'`.
- **Validate**: `git status` is clean apart from scratch. `PY -c "import libsql, pytest; print(pytest.__version__)"` works. (`PY` is the venv Python from F-9.)

### Task 1: Baseline run A (AC 1)

- **Implement**: From the repo root, run the plain suite and time it:
  ```bash
  PY=/c/Users/tobip/.venvs/harness-ai/Scripts/python.exe
  S=$TEMP/prd014-story001; mkdir -p $S
  /usr/bin/time -p $PY -m pytest tests/ -q -rfEs --junitxml=$S/runA.xml 2>&1 | tee $S/runA.log
  ```
  If `/usr/bin/time` is missing in Git Bash, use the `time` keyword or PowerShell `Measure-Command`, and record pytest's own `in N.NNs` line too. Rerun each failure or error alone (`$PY -m pytest "<nodeid>" -q`). A failure that passes alone and has the `STREAM_EXPIRED` / `os error 10060` signature is a **flake**: list it with its nodeid and error line. A failure that reproduces alone is a real failure on `main`: list it and tell the user, because every "counts unchanged" criterion depends on it.
- **Validate**: The report has collected, passed, failed, errored and skipped counts, wall time, and every failure with nodeid, error and rerun result.

### Task 2: Write the scratch plugin (AC 2, AC 3)

- **File**: `$TEMP/prd014-story001/storage_census.py`
- **Action**: CREATE (scratch)
- **Implement**: As in D-2. The proxy must forward every attribute and re-raise the original exception object. Keep it under ~150 lines and use the stdlib only.
- **Validate**: A smoke run on two modules shows non-zero calls attributed per test and split by bucket:
  `PYTHONPATH="$S;." $PY -m pytest tests/test_conftest_fixtures.py tests/test_admin_auth.py -q -p storage_census`.
  Then check it against one known case. `test_conftest_fixtures.py`'s direct `_reset_database()` tests show `test`-bucket calls, and every test shows `reset`-bucket calls from the autouse fixture.

### Task 3: Instrumented run B (AC 2)

- **Implement**: `PYTHONPATH="$S;." $PY -m pytest tests/ -q -rfEs -p storage_census --junitxml=$S/runB.xml 2>&1 | tee $S/runB.log`. Rerun flakes as in Task 1. Compare against Run A (D-1).
- **Validate**: `census.json` exists, and its item count equals Run B's collected count, which equals Run A's.

### Task 4: Analysis (AC 2, AC 3)

- **File**: `$TEMP/prd014-story001/analyze.py`
- **Action**: CREATE (scratch)
- **Implement**: As in D-4. Paste its output into the report. For each undeclared test, read the test enough to name **how** it reaches storage in one phrase (for example "app lifespan via `TestClient(app)`", "`get_connection()` in a module fixture not named `temp_db`", "`request.getfixturevalue`"). STORY-003 chooses between `_DB_NODEIDS` and a fixture based on that phrase.
- **Validate**: The undeclared-list counts add up: total undeclared = sum over modules. Every `PRD-006` flag matches `_UNMODIFIED_SUITES`. `tests/test_admin_auth.py` appears (PRD story 5 expects it). If it does not, explain why in the report.

### Task 5: Autouse audit (AC 4)

- **Implement**: `grep -n "autouse=True" tests/conftest.py tests/test_*.py`. For each fixture, record file:line, scope, what it touches, and **touches storage: yes/no** with the evidence (read the body, and cross-check Run B: a module autouse fixture that reaches storage shows up as `test`-bucket calls on every test in its module). Expected: only `_never_the_configured_database` and `_libsql_endpoint` touch storage.
- **Validate**: Every `autouse=True` hit appears in the table.

### Task 6: Subprocess audit (AC 5)

- **Implement**: Re-run the F-7 grep on the base (`subprocess.`, `Popen`, `sys.executable`, `pytester`). For every subprocess-spawning test with no storage fixture (cross-check with the census), read the `env=` it passes and the child's code path, and record **reaches storage: yes/no** with one line of evidence. For example: "child imports `chat_ui` only and never calls `get_connection`", or "runs `scripts/measure_usage_latency.py`, which calls `init_db()` against the inherited `DATABASE_URL`". Add any "yes" to the undeclared list, marked `(child)`. Per PRD 9.1, such a child can only reach `_ENDPOINT`, so record the URL it would use too.
- **Validate**: Every file in F-7 is accounted for, either as tests read or as "no subprocess" / "all subprocess tests request a storage fixture".

### Task 7: Report and diff check (AC 6)

- **File**: `.agents/reports/PRD-014-test-suite-db-isolation/STORY-001-storage-characterization.report.md`
- **Action**: CREATE
- **Implement**: Use the sections in *Patterns to Follow*. *For later stories* must say: STORY-002 seeds `_DB_NODEIDS` from the undeclared list, with module paths for the PRD-006 suites. STORY-003 and STORY-007 compare against Run A's counts. STORY-007 reruns the appendix instrument and compares driver calls. Put the brief's expected figures beside the measured ones, and treat any gap as an observation, not a failure.
- **Validate**:
  ```bash
  git status --porcelain                         # only .agents/ paths
  git diff --stat HEAD -- tests app chat_ui      # empty
  git ls-files --others --exclude-standard | grep -v '^\.agents/'   # empty: no stray scratch in the repo
  ```

---

## End-to-End Tests

This story's end-to-end check is the two full runs.

- [ ] Run A completes, and its counts and wall time are in the report
- [ ] Run B completes with the same collected and passing counts as Run A, apart from confirmed flakes
- [ ] The smoke run in Task 2 shows per-test attribution across a cached client: a test that runs after another `db` test, on the same `_shared_client`, shows its own calls, not zero

---

## Validation

```bash
PY=/c/Users/tobip/.venvs/harness-ai/Scripts/python.exe
$PY -m pytest tests/ -q                      # Run A (baseline)
PYTHONPATH="$TEMP/prd014-story001;." $PY -m pytest tests/ -q -p storage_census   # Run B
git diff --stat HEAD -- tests app chat_ui     # empty
```

---

## Risks + Mitigations

| # | Risk | Mitigation |
|---|---|---|
| R-1 | `main` lacks PRD-013 (F-1), so a baseline on it would be stale the moment PRD-013 merges | Task 0 stops and asks. The report records the base SHA, and later stories compare against the same SHA's lineage |
| R-2 | Flakes (`STREAM_EXPIRED`, `os error 10060`) make the two runs' counts differ | Rerun each failure alone. Record flakes separately. Counts are compared after excluding confirmed flakes. If the suite slows sharply, `docker restart harness-libsql-dev` (memory) and note it |
| R-3 | The proxy changes driver behaviour | It forwards attributes and re-raises the original exception object. Run B must match Run A (D-1) |
| R-4 | Another session resets the shared container mid-run | Check before starting. If a run shows a burst of unrelated failures, rerun it rather than recording them |
| R-5 | Calls from a lingering worker thread are charged to the next test, which would put a false entry on the undeclared list | For each undeclared test, Task 4 reads the test, so a test with no storage path is spotted and flagged "spillover from <previous nodeid>" instead of listed |
| R-6 | Scratch files leak into the commit | Everything is under `$TEMP`. Task 7's `git ls-files --others` check |

---

## Acceptance Criteria

(Copied from story `STORY-001`)

- [ ] Given untouched `main`, when the full suite runs once, then the report records the collected total, passed, failed, errored and skipped counts, plus the wall time. Any failure is listed with its nodeid and error. That run is the baseline every later story compares against.
- [ ] Given an uncommitted scratch plugin loaded with `-p` that wraps `libsql.connect` and counts calls per test, when the full suite runs under it, then the report records the total driver calls per run and the storage-fixture census: tests and modules requesting any of `temp_db`, `database_url`, `uninitialized_db`, `database_url_factory`, `db_connect` (transitively, via `item.fixturenames`), tests requesting none, and modules mixing both.
- [ ] Given the same run, when tests with at least one driver call are cross-referenced with the census, then the report lists **every test that issues driver calls without a storage fixture**, grouped by module. Each test is flagged if its file is one of the six PRD-006 suites in `tests/test_untouched_app.py::_UNMODIFIED_SUITES`. Driver calls from the autouse `_never_the_configured_database` reset are excluded from this classification.
- [ ] Given every autouse fixture in `tests/conftest.py` and in test modules, when each is read, then the report has a table saying whether it touches storage (expected: only `_never_the_configured_database` and the session `_libsql_endpoint`).
- [ ] Given every test that spawns a subprocess and requests no storage fixture, when its child's environment and code path are read, then the report states whether the child reaches storage. Any that do are added to the undeclared list.
- [ ] Given the story's diff, when reviewed, then it contains only the report (and optionally a note in `.agents/`). No file under `tests/`, `app/` or `chat_ui/` changes, and the scratch plugin is not committed.
- [ ] All tasks completed
- [ ] Follows existing patterns (report layout, commit sequence)
