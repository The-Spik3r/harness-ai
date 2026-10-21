---
story: STORY-007
prd: PRD-014-test-suite-db-isolation
slug: docs-and-regression-sweep
title: "README and conftest docstring for the db split, plus a three-run regression sweep"
type: ENHANCEMENT
complexity: LOW
epic_branch: epic/PRD-014-test-suite-db-isolation
created: 2026-10-21
---

# Plan: README and conftest docstring for the `db` split, plus a three-run regression sweep

## Summary

Two documentation edits and a measurement pass, with no behaviour change.

1. **README *Running Tests*** gains the three run modes (`pytest tests/`, `-m "not db"`, `-m db`, plus `--collect-only -m db`). It also explains the guard's "reached storage ... without declaring it" failure and its three fixes, shows an example `libsql diagnostics` section with a table of what each verdict means and what to do, and adds a short "if `db` tests flake on Docker Desktop" paragraph, because STORY-006 concluded **confirmed**. The in-container block and its three bullet warnings stay byte-for-byte as they are.
2. **`tests/conftest.py`'s module docstring**: the "Where isolation comes from now" paragraph is rewritten in place so it covers the marker, the `db`-only reset, the guard, the lazy endpoint and the diagnostics. The "Running these tests needs ..." paragraph is narrowed to `db` tests.
3. **Regression sweep**: three consecutive full runs, each count compared with STORY-001's baseline plus the epic's 56 harness tests (3,854 + 56 = 3,910 collected, 3,883 passing, 27 skipped). After that, one more run under STORY-001's scratch `storage_census` plugin, rebuilt from that report's appendix with two documented deltas. It shows non-`db` driver calls are 0 and records the per-run total beside STORY-001's 52,980. A Docker-free `-m "not db"` run against a dead endpoint re-proves the first MVP criterion on the final tree.
4. **The report** ticks every PRD Section 11 box with a pointer to its evidence, and confirms that `git diff main` over the six PRD-006 suites and over `app/` and `chat_ui/` is empty.

## User Story

As a harness developer reading the README
I want to know how to run the suite with and without Docker and how to read a diagnostics section
So that I use the split and trust a red run

## Story Reference

- Story file: `.agents/stories/PRD-014-test-suite-db-isolation/STORY-007-docs-and-regression-sweep.md`
- PRD: `.agents/PRDs/PRD-014-test-suite-db-isolation/PRD.md` (sections 4 *Documentation*, 7 F7, 10, 11, 12 Phase 4, Appendix *D5 result*)
- Upstream evidence:
  - STORY-001 report: baseline, the *Appendix: scratch instrument* (`storage_census.py`, `analyze.py`), *For later stories → STORY-007*
  - STORY-003 report: docstrings were corrected but not rewritten
  - STORY-004/005 reports: Docker-free runs, latest full-run counts (3,910 / 3,883 / 27)
  - STORY-006 report and `.agents/spikes/PRD-014-docker-network-stalls.md`: D5 **confirmed**, and the in-network command

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT (docs plus verification; no `app/` change, no behaviour change in `tests/`) |
| Complexity | LOW |
| Systems Affected | `README.md`, `tests/conftest.py` (docstring only) |
| Story | STORY-007 |
| PRD | PRD-014-test-suite-db-isolation |
| Epic Branch | `epic/PRD-014-test-suite-db-isolation` (commit directly on this branch) |
| Depends on | STORY-003 ✅ `241fae0`, STORY-004 ✅ `96de11b`, STORY-005 ✅ `16402fa`, STORY-006 ✅ `f905425` |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | The story says "Skills: none applicable". `.agents/skills/` holds only `frontend-design`, which does not apply to README or test-harness work | — |

---

## Decisions taken in this plan

| # | Decision | Why |
|---|----------|-----|
| P1 | **Baseline for "equal to STORY-001" = 3,854 + 56 = 3,910 collected, 3,883 passing, 27 skipped.** | STORY-001 measured 3,854 / 3,827 / 27 on `main`. The epic added only `tests/test_db_isolation_harness.py`, which has 56 tests (checked with `--collect-only`), and STORY-005's full run already gave 3,910 / 3,883 / 27. A run matches the baseline when its counts equal these once each flake is counted as a pass |
| P2 | **The new README text goes after the "Locally:" block and before "Inside the Docker container:".** The in-container command and its three bullets are not touched | The AC requires the in-container overrides and warnings to be unchanged. The `DATABASE_URL` bullet's wording ("the autouse fixture that redirects each test at an isolated database") is still true for `db` tests, and the `monkeypatch.undo()` sites are all in `db` tests (conftest `_storage_policy` docstring). Rewording it is out of scope |
| P3 | **README uses bold lead-in paragraphs, not new `###` headings.** | That is how *Running Tests* already handles its caveats ("**A known collection error, and when it does *not* apply.**"). The Table of Contents lists only `##` headings, so it needs no change |
| P4 | **The README does not quote test counts.** It says "about two thirds of the suite". | Counts drift with every PRD. The figures go in the report |
| P5 | **The D5 paragraph points at the spike report's command. It does not copy the recipe.** | The story's note limits this to a short paragraph: "Anything more belongs in STORY-008". The command and its two caveats (`docker run`, not `docker compose run`; the three `test_measure_usage_latency.py` tests refuse the non-local host name) are in `.agents/spikes/PRD-014-docker-network-stalls.md` |
| P6 | **The `_never_the_configured_database` mention in `_storage_policy`'s docstring (`tests/conftest.py:561`) stays.** | It is history ("Until PRD-014 STORY-003 this fixture was ..."), not a stale claim. The story's grep exists to catch stale text, so the report records this as the one expected hit and says why. The other phrase, "every test starts on an empty database", already returns nothing |
| P7 | **The scratch plugin is rebuilt from STORY-001's appendix byte-for-byte, with two deltas, and both are recorded in the report:** (a) `POLICY`'s key `_never_the_configured_database` → `_storage_policy`; (b) `ITEMS[...]` also stores `"db": item.get_closest_marker("db") is not None` | (a) Without it every reset call would be bucketed `test`, so the per-bucket figures could not be compared. The total is unaffected either way. (b) The split that matters now is `db` vs not-`db`, which is no longer the same as storage fixture vs none: the 7 `_DB_NODEIDS` tests differ. Conftest's `tryfirst` marking runs before the plugin's `trylast` hook, so the marker is already set |
| P8 | **The plugin run is a fourth run, separate from the three-run sweep.** | The AC treats the sweep and "the scratch plugin rerun once" as separate checks. Keeping the instrument out of the three counted runs means it cannot be blamed for a flake |
| P9 | **The Docker-free check on the final tree uses `HARNESS_TEST_LIBSQL_URL=http://127.0.0.1:9`, and does not stop `harness-libsql-dev`.** | Another Claude session on this machine shares the container (memory: shared-DB flakes). A dead endpoint is a stricter test than a stopped container, because `DATABASE_URL`'s `setdefault` then points children at a dead port too. STORY-004 used the same technique in its `pytester` tests. STORY-004/005 already proved the case with Docker Desktop stopped. This run only shows the final tree still passes |
| P10 | **The Section 11 checklist is ticked in the report. The PRD's own Section 11 boxes are also ticked in the chore commit,** each with a short pointer | The AC asks for the report. Ticking the PRD as well keeps it from showing open boxes when it is promoted to done. The PRD stays `status: draft` until STORY-008, which is out of this story's scope |

---

## Patterns to Follow

### README tone: commands first, then a bold-led "why" paragraph per caveat

```markdown
// SOURCE: README.md:873-897 (Running Tests)
Locally:

```bash
pytest tests/ -v
```
...
All three overrides are required, for three different reasons. ...

- `HARNESS_TEST_LIBSQL_URL` points the test fixtures at a server they can actually reach. ...

**A known collection error, and when it does *not* apply.** Running `tests/test_pii_badge.py` ...
```

### Module-docstring paragraphs: a bold lead sentence, then the mechanism and why

```python
# SOURCE: tests/conftest.py:17-25 (the paragraph this story rewrites)
**Where isolation comes from now.** It used to come from `tmp_path`: a distinct
file per test. One libSQL server serves one database, so isolation is now a
**reset** rather than a fresh name -- `_reset_database()` drops every table and
index before each `db` test, from the autouse `_storage_policy`. Since PRD-014 a
test that is not `db` cannot reach storage at all, so it has nothing to start
empty. The promise the old docstring made is
unchanged; only the mechanism behind it moved. What did not survive is distinct
URLs per test: see `database_url_factory`.
```

The paragraph has a broken wrap ("made is / unchanged") and does not mention the marker's source, the guard's failure, the lazy endpoint or the diagnostics. Keep the bold lead, the `tmp_path` history and the `database_url_factory` pointer. Wrap at ~80 columns like the rest of the docstring. Use ASCII `--` for dashes, as the docstring already does.

### Exact strings the README must quote (copy them, don't paraphrase)

```python
# SOURCE: tests/conftest.py:451-456 (_UNDECLARED)
"{nodeid} reached storage ({where}) without declaring it.\n"
"Request temp_db (or database_url / uninitialized_db / database_url_factory / db_connect),\n"
"add @pytest.mark.db, or -- for a suite that must not be edited -- add its nodeid to\n"
"_DB_NODEIDS in tests/conftest.py."
```

```python
# SOURCE: tests/conftest.py:398-409 (_verdict) -- the four verdict forms
"no driver calls recorded"
f"likely infrastructure -- {op} took {s:.2f} s and ended in {error}"
f"likely infrastructure -- {op} took {s:.2f} s (no driver error)"
f"no infrastructure signal ({n} calls, slowest {s:.2f} s)"
```

```text
# SOURCE: tests/conftest.py:412-447 (_diagnostics) -- line order of the section
calls: <n> on <c> client(s), <k> connect(s)
slowest: <op> <s.sss> s (client idle <s.ss> s before)[ -> <label>]
over 10 s: <op s.sss s, ...> | none
driver errors: <n> x <label>, ... | none
libsql verdict: <verdict>
```

The README example section should be a realistic infrastructure case built from that format, with ASCII `->` and `x`. Use the spike's host-arm event (21.05 s `tcp connect error` at setup) or the PRD 6.6 `STREAM_EXPIRED` example, re-spelled in the real output format: `--` not `—`, `x` not `×`, `->` not `→`.

### The D5 command to point at

```text
# SOURCE: .agents/spikes/PRD-014-docker-network-stalls.md:134 onward
docker run --rm --network harness-test-net \
  -e HARNESS_TEST_LIBSQL_URL=http://harness-libsql-dev:8080 ...
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `README.md` | UPDATE | *Running Tests*: three run modes, guard failure + three fixes, diagnostics example + verdict table, D5 paragraph. *Requirements* line 389: the libSQL server is needed for the storage tests only |
| `tests/conftest.py` | UPDATE | Module docstring only: rewrite "Where isolation comes from now" and narrow "Running these tests needs ..." No code line changes |
| `.agents/reports/PRD-014-test-suite-db-isolation/STORY-007-docs-and-regression-sweep.report.md` | CREATE (by `/implement`) | Run tables, every verdict line, plugin figures, Section 11 checklist with evidence, diff checks |
| scratch `%TEMP%\prd014-story007\storage_census.py`, `analyze.py` | CREATE (scratch, **not committed**) | STORY-001's instrument with the P7 deltas |

No file under `app/`, `chat_ui/` or `scripts/` changes. No test file other than `tests/conftest.py`'s docstring.

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 0: Pre-flight

- **Implement**:
  - `git branch --show-current` → `epic/PRD-014-test-suite-db-isolation`. Working tree clean apart from `.agents/` bookkeeping.
  - Docker Desktop running, then `docker start harness-libsql-dev`. Check that no other pytest process is running against it (process list), as STORY-001 did.
  - `C:\Users\tobip\.venvs\harness-ai\Scripts\python.exe -m pytest --collect-only -q -p no:cacheprovider tests/` → **3,910** collected. `--collect-only -q -m db` → record the count (expected ~1,297: STORY-005's 1,271 deselected by `not db`).
  - Prepare the keep-awake wrapper (memory: S3 sleep mid-run): a PowerShell helper that calls `SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)` around the run, with no power-setting change.
- **Validate**: counts recorded in the report's *Environment* table (Python, pytest, libsql, server image, Docker engine version).

### Task 1: `tests/conftest.py` module docstring

- **File**: `tests/conftest.py` (lines 17-35 only)
- **Action**: UPDATE
- **Implement**: Replace the "Where isolation comes from now" paragraph. It must say, without claiming every test is reset:
  - Isolation used to come from `tmp_path` (keep that history sentence).
  - **The marker**: a test is `db` when its fixture closure meets `_STORAGE_FIXTURES` or it is listed in `_DB_NODEIDS`. `pytest_collection_modifyitems` applies it, so no test file declares it, though `@pytest.mark.db` also works.
  - **`db`-only reset**: the autouse `_storage_policy` runs `_reset_database()` before each `db` test, so each starts empty.
  - **The guard**: every other test has `database._shared_client` and `libsql.connect` replaced by `_refuse()`. A storage access fails the test with a message naming the fix. A swallowed access fails it at teardown. So a non-`db` test can neither see rows nor leave them, and the promise (no test reaches another test's rows or anyone's real database) is unchanged.
  - **The lazy endpoint**: `_libsql_endpoint` is probed only when a `db` test or a storage fixture asks for it, so `pytest -m "not db"` runs without the server.
  - **Diagnostics**: a failing `db` test's report gains a `libsql diagnostics` section ending in `libsql verdict: ...` (one sentence, pointing at `pytest_runtest_makereport`).
  - Distinct URLs per test did not survive (keep the `database_url_factory` pointer).

  Then reword the next paragraph's opening to "Running the `db` tests needs the local libSQL dev server ...", and add one clause that `-m "not db"` needs none. The `docker run` lines and the `HARNESS_TEST_LIBSQL_URL` sentence stay unchanged.
- **Mirror**: the paragraph style of `tests/conftest.py:1-16`: bold lead, ~80-column wrap, `--` dashes, backticked names.
- **Validate**:
  - `git diff -- tests/conftest.py` shows changes inside the module docstring only (no line after the closing `"""` at line 35).
  - `python -m pytest -q -p no:cacheprovider tests/test_db_isolation_harness.py tests/test_conftest_fixtures.py` passes.
  - The stale grep (Task 3) is clean apart from P6.

### Task 2: README *Running Tests*

- **File**: `README.md`
- **Action**: UPDATE
- **Implement**, in this order, between the "Locally:" block (line 873) and "Inside the Docker container:" (line 879):
  1. Replace the single `pytest tests/ -v` block with four commented commands:
     ```bash
     pytest tests/ -v                  # everything (the default); needs the libSQL server
     pytest tests/ -m "not db" -v      # the tests that never touch storage; no Docker needed
     pytest tests/ -m db -v            # only the storage tests
     pytest tests/ --collect-only -q -m db   # list what counts as a db test
     ```
     Then one "why" paragraph: about two thirds of the suite never touches storage. Those tests are not `db`, are not reset, and cannot reach the server, so `-m "not db"` is a fast loop that needs no Docker. A test is `db` when it requests a storage fixture (`temp_db`, `database_url`, `uninitialized_db`, `database_url_factory`, `db_connect`, directly or through another fixture), carries `@pytest.mark.db`, or is listed in `_DB_NODEIDS` in `tests/conftest.py`. With the server down, a full run stops at the first `db` test with the "libSQL dev server ... is unreachable" message.
  2. **"A test failed with "reached storage ... without declaring it"."** Quote the message (from `_UNDECLARED`, with a sample nodeid and `where`). Say what it means: a non-`db` test tried to open a database connection, and the harness refused before any socket was opened. That is a missing declaration, not a database problem. It cannot be hidden by `except Exception` and is caught at teardown if swallowed. Then the three fixes, in order of preference:
     - (1) request a storage fixture (usually `temp_db`), the usual fix for a new test;
     - (2) add `@pytest.mark.db` when the test reaches storage some other way, e.g. through the app's lifespan;
     - (3) add its nodeid, or its module path, to `_DB_NODEIDS` when the file must not be edited (the six PRD-006 suites that `tests/test_untouched_app.py` pins).
  3. **"Reading a `libsql diagnostics` section."** Every failing `db` test (setup, call or teardown) prints one. A passing test prints none. `grep "libsql verdict"` over a run log classifies every failure without a rerun. Include one example section (format per *Patterns*), then a 3-row table, *Verdict → Means → Do*:
     - `likely infrastructure -- <op> took <s> s and ended in STREAM_EXPIRED / tcp connect error / ...` → a libSQL stall or dropped stream hit this test → rerun that test alone. If it passes, it was not your change. Quote the verdict line in a story report.
     - `likely infrastructure -- <op> took <s> s (no driver error)` → a call stalled ≥ 10 s but the driver did not report an error → the failure is probably a timeout downstream of the stall. Rerun alone, same as above.
     - `no infrastructure signal (<n> calls, slowest <s> s)` → storage behaved normally → **treat it as a real failure** and debug it.
     - `no driver calls recorded` → nothing was recorded (no storage call yet, or `monkeypatch.undo()` removed the recorder) → judge it from the traceback.

     One sentence: the section prints method names, timings and error labels, never SQL or parameters.
  4. **"If `db` tests flake on Docker Desktop."** Two or three sentences. STORY-006 measured stalls only behind Docker Desktop's port forwarding (0 in-network vs 2 on host, a small sample). Running `-m db` from a container on the same Docker network as `harness-libsql-dev` avoided them. Point at the command in `.agents/spikes/PRD-014-docker-network-stalls.md` and note its two caveats (`docker run --network`, not `docker compose run`; the three `tests/test_measure_usage_latency.py` tests refuse the non-local host name by design). Say a documented recipe is to follow (STORY-008).
  5. Also update *Requirements* (line 389): "a local libSQL server for the storage tests (see [Running Tests](#running-tests)); `pytest -m "not db"` needs none -- no Turso account needed". Keep the existing em-dash style of that line.
- **Mirror**: README *Running Tests* (`README.md:860-899`): commands first, bold-led "why" paragraphs, existing in-container block untouched.
- **Validate**:
  - `git diff -U0 -- README.md` shows no removed or changed line in the in-container block (the `docker-compose run` command, "All three overrides are required ...", its three bullets, the Linux `host.docker.internal` line) and none in the "known collection error" paragraph.
  - Every command in the new block is run once: `--collect-only -q -m db` and `-m "not db" --collect-only -q` both collect without error.
  - The quoted guard message and verdict forms are compared character by character with `tests/conftest.py`.

### Task 3: Stale-text grep

- **Implement**: `grep -rn "_never_the_configured_database\|every test starts on an empty database" tests README.md --include=*.py --include=*.md` (excluding `__pycache__`). Also grep `README.md` and the conftest module docstring for "before each test" / "every test" claims that describe the reset.
- **Validate**: the only hit is `tests/conftest.py:561` (history, P6). Record the output in the report.

### Task 4: Three-run regression sweep (AC 3)

- **Implement**: Three consecutive full runs, each in the background, each wrapped in the keep-awake helper, with nothing else using the container:
  ```bash
  W='C:\Users\tobip\AppData\Local\Temp\prd014-story007'   # outside the repo; Windows-form path
  for i in 1 2 3; do
    /c/Users/tobip/.venvs/harness-ai/Scripts/python.exe -m pytest tests/ -q -rfEs -p no:cacheprovider \
      --junitxml="$W/run$i.xml" 2>&1 | tee "$W/run$i.log"
  done
  grep -n "libsql verdict" "$W"/run*.log
  ```
  For each run, record: collected, passed, failed, errors, skipped, pytest wall time, and every failure with its phase, error and **verdict line pasted verbatim**. Rerun each failure alone and record the outcome.
  - A failure whose verdict is `no infrastructure signal` (or a non-`db` guard failure) is a **defect that blocks the story**. Stop, investigate, and report it. Do not rerun it away.
  - A failure in a non-`db` test can have no verdict, because it cannot be an infrastructure flake. Treat it as a defect too.
  - If Windows slept during a run (System log Kernel-Power 42/107, or a call of thousands of seconds), discard that run, say so, and run another (STORY-006 precedent).
- **Validate**: each run equals 3,910 / 3,883 / 27 once flakes are counted as passes (P1). Wall times are compared with STORY-001's 339.6 s (Run A) and 302.4 s (Run B). If the median is worse, say so plainly and attribute the difference to the recorded stalls (≈15-21 s each) only where the logs show them.

### Task 5: Scratch plugin rerun (AC 4)

- **Implement**:
  - Create `%TEMP%\prd014-story007\` and save `storage_census.py` and `analyze.py` from STORY-001's appendix. Apply only the P7 deltas, and keep a `diff` of each file against the appendix text for the report.
  - Run once:
    ```bash
    PYTHONPATH="C:\Users\tobip\AppData\Local\Temp\prd014-story007;." \
      python -m pytest tests/ -q -rfEs -p no:cacheprovider -p storage_census \
      --junitxml="$W/census.xml" 2>&1 | tee "$W/census.log"
    python -I -X utf8 "$W/analyze.py" "$W/census.json"
    ```
  - Add a short scratch query over `census.json` that sums calls by the new `db` flag and lists every non-`db` nodeid with ≥ 1 call (expected: none).
- **Validate**:
  - Run passes with the same counts as Task 4.
  - The non-`db` total is **0**.
  - The per-run total, by bucket (`reset`, `test`, `endpoint`), is recorded beside STORY-001's 52,980 (18,014 / 34,964 / 2). Expected: around STORY-001's storage-fixture share of 47,044, plus the resets the 7 listed tests gain, plus the `db` harness tests' calls.
  - **State the measurement's limit in the report.** In a non-`db` test the guard replaces `libsql.connect` over the plugin's wrapper, so an attempted call would be refused, not counted, and would fail the test. The zero is therefore proved by two things together: the census shows no calls, and the run is green. `pytester` children run out of process, and the plugin does not see them, as in STORY-001.

### Task 6: Docker-free check on the final tree (Section 11, MVP 1)

- **Implement**: `HARNESS_TEST_LIBSQL_URL=http://127.0.0.1:9 python -m pytest tests/ -m "not db" -q -p no:cacheprovider` (P9).
- **Validate**: 0 failed, 0 errors, no "unreachable" exit. Passed, skipped and deselected counts and wall time are recorded beside STORY-005's 2,613 passed / 26 skipped / 1,271 deselected / 77.6 s.

### Task 7: Diff checks and the Section 11 checklist (AC 5)

- **Implement**:
  - `git diff --stat main -- app chat_ui` → empty.
  - `git diff main -- tests/test_admin_auth.py tests/test_audit_router.py tests/test_stats_router.py tests/test_db.py tests/test_route_reservations.py tests/test_chat_state.py` → empty.
  - `python -m pytest -q tests/test_untouched_app.py` → passes. It already ran inside Task 4; cite that run.
  - In the report, copy PRD Section 11 (MVP, Functional, Quality) and tick every box. Each box gets a pointer to a story report section, a command output in this report, or a test name in `tests/test_db_isolation_harness.py`. Map them before writing:

    | Section 11 box | Evidence |
    |---|---|
    | `-m "not db"` with Docker stopped | STORY-004 and STORY-005 reports (Docker stopped), and Task 6 here |
    | zero driver calls, enforced | the guard in `_storage_policy`, its self-tests (STORY-003), Task 5 here |
    | undeclared → message | STORY-003 self-tests (name them) and the `_UNDECLARED` text |
    | diagnostics on every `db` failure | STORY-005 self-tests (pytester, setup/call/teardown), and Task 4 verdict lines if any |
    | counts = baseline, pinned assertions unchanged | Task 4, Task 7 diffs |
    | driver calls drop | Task 5 vs STORY-001 |
    | Functional boxes | the STORY-002/003/005 self-tests by name, plus Task 7 |
    | Quality: `-m "not db"` wall time | STORY-004 (60 s), Task 6 |
    | Quality: full-run wall time | Task 4 vs 339.6 s, stated honestly |
    | Quality: three runs | Task 4 |
    | Quality: spike conclusion | STORY-006 report, PRD Appendix *D5 result* |

    Look up each self-test's name in `tests/test_db_isolation_harness.py` (`grep -n "^def test_\|^async def test_"`). Don't cite from memory.
- **Validate**: no box is left unticked without a stated reason. If one cannot be ticked (for example wall time is worse), mark it `[ ]`, say why, and raise it in the report summary instead of hiding it.

### Task 8: Commit

- **Implement**: one `docs(PRD-014): STORY-007 README and conftest docstring for the db split` commit with `README.md` and `tests/conftest.py`. Then, per the epic's pattern, a `chore(PRD-014): STORY-007 report; update status + index` commit with the report, the story's frontmatter, `index.md`, the PRD's Section 11 ticks (P10) and the plan moved to `completed/`. Both commit messages end with the `Co-Authored-By` line. The scratch directory is not committed.
- **Validate**: `git status` is clean and `git log --oneline -2` shows both commits.

---

## End-to-End Tests

- [ ] The README's four commands each run (collect-only for the two `-m db` forms, a full `-m "not db"` in Task 6, a full run in Task 4)
- [ ] The quoted guard message matches what a deliberately undeclared test prints. Reuse STORY-003's pytester self-test output, or a throwaway test file run once and deleted, so no committed test changes
- [ ] The README's example diagnostics section matches the real line format of `_diagnostics()`. Compare with a STORY-005 pytester self-test's expected output, or with any real failure from Task 4
- [ ] Three full runs: counts = 3,910 / 3,883 / 27 apart from flakes, and every failure's verdict is `likely infrastructure`
- [ ] Plugin run: non-`db` calls = 0, total recorded beside 52,980
- [ ] Dead-endpoint `-m "not db"` run is green

---

## Validation

```bash
PY=/c/Users/tobip/.venvs/harness-ai/Scripts/python.exe
$PY -m pytest --collect-only -q -p no:cacheprovider tests/ | tail -1                 # 3910 tests collected
$PY -m pytest --collect-only -q -p no:cacheprovider -m db tests/ | tail -1
$PY -m pytest -q -p no:cacheprovider tests/test_db_isolation_harness.py tests/test_conftest_fixtures.py tests/test_untouched_app.py
HARNESS_TEST_LIBSQL_URL=http://127.0.0.1:9 $PY -m pytest -q -p no:cacheprovider -m "not db" tests/
git diff --stat main -- app chat_ui                                                    # empty
git diff main -- tests/test_admin_auth.py tests/test_audit_router.py tests/test_stats_router.py \
  tests/test_db.py tests/test_route_reservations.py tests/test_chat_state.py           # empty
grep -rn "_never_the_configured_database\|every test starts on an empty database" tests/*.py tests/conftest.py README.md
```

---

## Risks

| Risk | Mitigation |
|------|------------|
| A run fails with `no infrastructure signal` | That blocks the story by its AC. Stop, investigate as a defect, and report. Do not rerun until it is green |
| Windows sleeps mid-run, so a stall reading is really a sleep | Keep-awake wrapper. Check Kernel-Power events, discard the run and repeat (STORY-006 precedent) |
| Another session resets the shared container mid-run | Check the process list before each run. A mid-run reset shows as a burst of unrelated `db` failures with "no such table". If it happens, note it, wait and rerun the whole run. Don't count it |
| The plugin and the conftest recorder interfere | Each one wraps whatever `libsql.connect` is at the moment it wraps: the plugin at `pytest_configure`, the recorder per `db` test. They layer, and both re-raise the original exception. The plugin run must give the same counts as Task 4, otherwise it is invalid |
| Wall time worse than STORY-001's 339.6 s (STORY-005's single run was 360.9 s) | Report honestly with per-run figures and any stalls. Do not tick the Quality box without evidence (Task 7) |
| README drift: numbers that rot, or prose that contradicts conftest | P4 (no counts). Quoted strings are copied from conftest and checked in Task 2 |
| Docstring edit accidentally touches code | Task 1's diff check: changes only above the closing `"""` |

---

## Acceptance Criteria

(Copied from story `STORY-007`)

- [ ] Given README *Running Tests*, when read, then it documents `pytest tests/` (everything, the default, needs Docker), `pytest tests/ -m "not db"` (no Docker) and `pytest tests/ -m db`. It explains what the guard's failure means and the three ways to resolve it, shows an example `libsql diagnostics` section, and says what each verdict means and what to do about it. The existing in-container overrides and their warnings are unchanged.
- [ ] Given `tests/conftest.py`'s module docstring, when read, then "Where isolation comes from now" describes the marker, the `db`-only reset, the guard and the lazy endpoint, without stating that every test is reset.
- [ ] Given three consecutive full runs, when they complete, then each run's counts are recorded and equal STORY-001's baseline, apart from flakes. Every failure, if any, carries `libsql verdict: likely infrastructure`. A failure with `no infrastructure signal` is a defect that blocks the story.
- [ ] Given STORY-001's scratch plugin rerun once on the final tree, when the driver-call count is compared, then non-`db` tests issue 0 calls and the total per run is recorded beside STORY-001's figure.
- [ ] Given PRD Section 11, when this story's report is written, then every checkbox is ticked with a pointer to the evidence (story report, command output, or test name). `git diff main` over the six PRD-006 suites is empty, and no file under `app/` or `chat_ui/` changed across the epic.
- [ ] All tasks completed
- [ ] Backend import unaffected (no `app/` change); `tests/conftest.py` still imports and the harness self-tests pass
- [ ] Follows existing patterns (README caveat style, conftest docstring style)
