---
story: STORY-006
prd: PRD-014
slug: docker-network-spike
title: "Spike: run the db tests from inside the Docker network vs the host to test the port-forwarding hypothesis (D5)"
type: SPIKE
complexity: LOW
epic_branch: epic/PRD-014-test-suite-db-isolation        # all stories commit here, no per-story branch
created: 2026-10-20
---

# Plan: Spike: stalls inside the Docker network (D5)

## Summary

This story measures and changes no code. It runs `pytest tests/ -m db` six times in one session, interleaved: three times from a container on a user network `harness-test-net` that reaches `harness-libsql-dev` by container name (no Docker Desktop port forwarding), and three times from the Windows host against `http://127.0.0.1:8080` (through the forwarding). Both arms load the same uncommitted scratch plugin, `spike_dump`. It reads the records STORY-005's recorder already keeps in `item.stash[_RECORDS]` and writes every stall event to JSONL: every call ≥ 10 s and every driver error, **including the ones `_reset_database()`'s retry absorbed in a test that then passed**. A scratch summarizer turns the six dumps into one table. The conclusion (confirmed / refuted / inconclusive, by the story's rule) goes into `.agents/spikes/PRD-014-docker-network-stalls.md` and PRD Appendix "D5 result", with a one-paragraph recommendation for STORY-008. Afterwards the network is removed and `harness-libsql-dev` is back on `bridge` only.

## User Story

As the owner of the local environment
I want to know whether Docker Desktop's Windows port forwarding causes the 7–21 s connection stalls
So that the follow-up (move the server, add a scoped retry, or accept it) rests on a measurement

## Story Reference

- Story file: `.agents/stories/PRD-014-test-suite-db-isolation/STORY-006-docker-network-spike.md`
- PRD: `.agents/PRDs/PRD-014-test-suite-db-isolation/PRD.md` (Sections 4 *Spike*, 7/F6, 11 *Quality indicators*, 12 Phase 3, 13, Appendix *D5 result*)

## Metadata

| Field | Value |
|-------|-------|
| Type | SPIKE (measurement only) |
| Complexity | LOW |
| Systems Affected | None in code. New `.agents/spikes/` report, PRD Appendix, `.agents/` bookkeeping. Docker state is temporary (network, one image) |
| Story | STORY-006 |
| PRD | PRD-014 |
| Epic Branch | `epic/PRD-014-test-suite-db-isolation` (commit directly on this branch; it is checked out, worktree clean at `554101b`) |

---

## Skills In Use

None. `.agents/skills/` holds only `frontend-design` (UI). The story says the same (`skills: []`).

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | — | — |

---

## Findings from Exploration

These change the PRD's Phase 3 recipe. Each one is a deviation the report must state.

1. **`docker compose run` has no `--network` option.** The recipe's `docker compose run --rm --network harness-test-net ...` will not parse. Use plain `docker run --rm --network harness-test-net <image> ...` on the image `docker compose build` produces. It also keeps `env_file: .env` (real secrets) out of the container. The conftest's `setdefault`s supply `OPENROUTER_API_KEY` / `ADMIN_TOKEN` (`tests/conftest.py:61-63`).
2. **No `harness-ai` image exists yet** (`docker images` lists only the libsql-server image). It has to be built, and the build is heavy: the builder stage runs `reflex init` + `reflex export` (downloads bun/node packages), and the final stage pip-installs `requirements.txt` and downloads `en_core_web_lg` (~425 MB). See Risk R1 for the fallback.
3. **The image bakes the tests in at build time** (`COPY . .`, `Dockerfile`). The in-network arm runs the code that was in the worktree when the image was built, so build from the clean epic HEAD and record that commit. The image has no `.git` (`.dockerignore`).
4. **The recorder's records are already reachable.** `_storage_policy` puts every driver call of a `db` test (including `_reset_database()` and its retry, since `_begin(item)` runs before the reset) into `item.stash[_RECORDS]` as `_Call(op, seconds, client, idle, error)` (`tests/conftest.py:283-318`, `:584-592`). The stash outlives `_end(item)`, so a `pytest_runtest_protocol` wrapper can read it after teardown. No change to `conftest.py` is needed. The session probe in `_libsql_endpoint` is *not* recorded (`:522-546`). A stall there exits the run, and the log shows it.
5. **`os error 10060` is Windows-only.** In the Linux container a connect timeout is `os error 110` (ETIMEDOUT). The recorder's labels hide the difference anyway: `_infra_error()` returns the *first* marker in `_INFRA_MARKERS` order (`:274-279`, `:321-333`), and `"tcp connect error"` comes before `"os error 10060"`. So a 10060 failure is labelled `tcp connect error`, and the Linux one is too. Count the **connect-timeout family** as label `tcp connect error` **or** `os error 10060`, and say so in the report, so the two arms are counted the same way.
6. **The dead-stream family is wider than `STREAM_EXPIRED`.** The labels come from `database._DEAD_STREAM` (`stream_expired`, `stream has expired`, `invalid baton`, ...). Count them as one family and list the raw labels seen.
7. **Run size.** `-m db` is 1,271 tests (STORY-005 report). The host takes about 360.9 − 77.6 ≈ 4.5–5 min per run. Six runs plus a build is roughly 45–75 min, so start each run in the background and wait for it.
8. **`tests/__init__.py` exists**, so the conftest is imported as `tests.conftest`. The plugin finds it by attribute (`_RECORDS` and `_STALL_SECONDS`) among registered plugins rather than by module name.
9. **The image has only `en_core_web_lg`**, and the memory notes the PII tests also want `en_core_web_sm` (presidio otherwise tries `uv pip install` at test time). If some `db` tests reach that path in-network, they may fail for a non-stall reason. Their verdict line (`no infrastructure signal`) separates them, so they count as environment differences, not stalls (R4).
10. **Shared container.** Another local session may use `harness-libsql-dev` and reset it mid-run (test-env memory). Concurrent load would contaminate both arms. Check before each run (Task 3).

---

## Patterns to Follow

### Scratch instrument outside the repo, quoted in the report's appendix

```
// SOURCE: .agents/reports/PRD-014-test-suite-db-isolation/STORY-001-storage-characterization.report.md:369,400-413
No file under `tests/`, `app/`, `chat_ui/` or `scripts/` changed. The scratch instrument lives in `%TEMP%\prd014-story001\`, outside the repo.
...
PYTHONPATH="<dir>;." python -m pytest tests/ -q -rfEs -p no:cacheprovider -p storage_census --junitxml=<dir>/run.xml
```

Use `%TEMP%\prd014-story006\` (`C:\Users\tobip\AppData\Local\Temp\prd014-story006`), a fixed short path that works from any session, and `-p no:cacheprovider` on every run.

### The records to read

```python
# SOURCE: tests/conftest.py:283-298
@dataclass(frozen=True)
class _Call:
    op: str
    seconds: float
    client: Optional[int]  # None for a `connect` that failed
    idle: Optional[float]  # seconds the client sat unused before it; None for `connect`
    error: Optional[str]  # the matched `_INFRA_MARKERS` label, if the call raised one

_RECORDS = pytest.StashKey[list[_Call]]()
```

### Hook style (pluggy new-style wrapper, as the conftest uses)

```python
# SOURCE: tests/conftest.py:166-167, 186
@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item, call):
    ...
    report = yield
```

### ASCII-only output

```
// SOURCE: tests/conftest.py:425-429 (_diagnostics docstring) and the test-env memory
piped or `tee`d output on Windows is cp1252, and a reader decoding it as UTF-8 fails on `—`, `×` or `→`.
```

The plugin's and summarizer's output stays ASCII. Open logs with `errors="replace"`.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `.agents/spikes/PRD-014-docker-network-stalls.md` | CREATE | The spike report: setup, deviations, the six runs' figures, conclusion, recommendation, instrument source in an appendix |
| `.agents/PRDs/PRD-014-test-suite-db-isolation/PRD.md` | UPDATE | Appendix "D5 result": conclusion + one-paragraph STORY-008 recommendation (replaces `_To be filled by STORY-006._`) |
| `.agents/stories/PRD-014-test-suite-db-isolation/STORY-006-docker-network-spike.md` | UPDATE | Bookkeeping (plan, status, report, commit) |
| `.agents/PRDs/PRD-014-test-suite-db-isolation/index.md` | UPDATE | Bookkeeping |
| `%TEMP%\prd014-story006\spike_dump.py`, `summarize.py`, logs, dumps | SCRATCH | Not committed. Sources quoted in the report's appendix |

No file under `tests/`, `app/`, `chat_ui/` or `scripts/` changes (AC 5). The story allows "at most a helper script". This plan commits none: both helpers stay scratch, as in STORY-001.

---

## Tasks

Execute in order. Shell: Git Bash with `export MSYS_NO_PATHCONV=1` for every `docker` call that takes a Windows path (`-v`), or PowerShell. `S=/c/Users/tobip/AppData/Local/Temp/prd014-story006` (Bash) / `C:/Users/tobip/AppData/Local/Temp/prd014-story006` (Docker `-v`). Host Python: `C:\Users\tobip\.venvs\harness-ai\Scripts\python.exe`.

### Task 0: Record the starting state

- **Action**: read only
- **Implement**: Record in scratch `state-before.txt`: `git rev-parse --short HEAD` (expect `554101b` or the plan commit) and `git status --short` (must be empty for `tests/`, `app/`), `docker ps -a --format '{{.Names}} {{.Image}} {{.Status}} {{.Networks}}'`, `docker network ls`, `docker images`, `docker version --format '{{.Server.Version}}'`, the libsql image digest (`docker inspect harness-libsql-dev --format '{{.Config.Image}}'`). Expected now: `harness-libsql-dev` up on `bridge` only, no `harness-test-net`, no `harness-ai` image. Start Docker Desktop / the container if needed (test-env memory).
- **Validate**: file written. `harness-test-net` absent (if present, stop and ask: it is not ours).

### Task 1: Write the scratch plugin `spike_dump.py`

- **File**: `%TEMP%\prd014-story006\spike_dump.py`
- **Action**: CREATE (scratch)
- **Implement**: a `-p` plugin. It only reads, never patches. Sketch:

  ```python
  """PRD-014 STORY-006 scratch instrument. Not committed; loaded with `-p spike_dump`.

  Reads the STORY-005 recorder's per-test records (`item.stash[_RECORDS]`) after
  each test and writes every stall event -- a call >= _STALL_SECONDS or one that
  ended in a driver error -- to $SPIKE_OUT.jsonl, with the test's outcome, so
  stalls absorbed by `_reset_database()`'s retry in a passing test are counted
  too. Totals go to $SPIKE_OUT.summary.json at session end. ASCII only.
  """
  import json, os, time
  import pytest

  _OUT = os.environ["SPIKE_OUT"]
  _ARM = os.environ.get("SPIKE_ARM", "?")
  _conftest = None
  _outcome: dict[str, str] = {}
  _events: list[dict] = []
  _totals = {"db_tests": 0, "calls": 0, "slowest": 0.0, "over_10s": 0, "errors": {}}
  _started = time.monotonic()

  def _recorder(config):
      global _conftest
      if _conftest is None:
          _conftest = next(p for p in config.pluginmanager.get_plugins()
                           if hasattr(p, "_RECORDS") and hasattr(p, "_STALL_SECONDS"))
      return _conftest

  def pytest_runtest_logreport(report):
      if report.failed:
          _outcome[report.nodeid] = "failed" if report.when == "call" else f"error ({report.when})"
      elif report.when == "call":
          _outcome.setdefault(report.nodeid, report.outcome)

  @pytest.hookimpl(wrapper=True)
  def pytest_runtest_protocol(item, nextitem):
      result = yield
      conf = _recorder(item.config)
      records = item.stash.get(conf._RECORDS, [])
      if item.get_closest_marker("db") is not None:
          _totals["db_tests"] += 1
      _totals["calls"] += len(records)
      for call in records:
          _totals["slowest"] = max(_totals["slowest"], call.seconds)
          stalled = call.seconds >= conf._STALL_SECONDS
          _totals["over_10s"] += stalled
          if call.error:
              _totals["errors"][call.error] = _totals["errors"].get(call.error, 0) + 1
          if stalled or call.error:
              _events.append({"nodeid": item.nodeid, "outcome": _outcome.get(item.nodeid, "?"),
                              "op": call.op, "seconds": round(call.seconds, 3),
                              "idle": None if call.idle is None else round(call.idle, 3),
                              "client": call.client, "error": call.error})
      return result

  def pytest_sessionfinish(session, exitstatus):
      with open(_OUT + ".jsonl", "w", encoding="ascii", errors="replace") as fh:
          for event in _events:
              fh.write(json.dumps(event) + "\n")
      with open(_OUT + ".summary.json", "w", encoding="ascii") as fh:
          json.dump({"arm": _ARM, "exitstatus": int(exitstatus),
                     "wall_seconds": round(time.monotonic() - _started, 1), **_totals}, fh, indent=2)
  ```

  Outcome is attached after the test's last report, since the wrapper's post-yield runs after setup/call/teardown are all logged.
- **Validate** (host, ~30 s): `SPIKE_OUT=$S/smoke SPIKE_ARM=host PYTHONPATH="$S;." python -m pytest tests/test_conftest_fixtures.py -m db -q -p no:cacheprovider -p spike_dump`. Expect it to pass as without the plugin, `smoke.summary.json` with `calls > 0` and `db_tests` equal to the passed count, and `smoke.jsonl` present (likely empty). Then delete the smoke files.

### Task 2: Build the image and set up the network

- **Action**: Docker state (temporary)
- **Implement**:
  1. `docker compose build harness-ai` from the repo root, in the background (it may take 10–20 min). Record the image name it produces (`docker images`, expect `harness-ai-harness-ai`) and the commit it was built from (Task 0).
  2. If the build fails (network/TLS in pip, spaCy or `reflex export`), use the fallback in R1 and record the deviation.
  3. `docker network create harness-test-net` and `docker network connect harness-test-net harness-libsql-dev`.
  4. In-network pre-flight, under 1 min: `docker run --rm --network harness-test-net <image> python -c "import libsql; print(libsql.connect('http://harness-libsql-dev:8080').execute('SELECT 1').fetchone())"`. Expect `(1,)`. Also `docker run --rm <image> python -c "import spacy; spacy.load('en_core_web_sm')"` and record whether the small model is there (Finding 9).
  5. Smoke the plugin in-network on one file: `docker run --rm --network harness-test-net -v "C:/Users/tobip/AppData/Local/Temp/prd014-story006:/spike" -e PYTHONPATH=/spike -e SPIKE_OUT=/spike/smoke-net -e SPIKE_ARM=in-net -e HARNESS_TEST_LIBSQL_URL=http://harness-libsql-dev:8080 -e DATABASE_URL=http://harness-libsql-dev:8080 -e TURSO_AUTH_TOKEN= <image> python -m pytest tests/test_conftest_fixtures.py -m db -q -p no:cacheprovider -p spike_dump`. It mounts only the scratch dir, not the OneDrive repo (story note on MAX_PATH/OneDrive), so the code under test is the image's.
- **Validate**: `(1,)` printed. `smoke-net.summary.json` written on the host with `calls > 0`. The host still reaches `127.0.0.1:8080` (`python -c` probe or the next host run).

### Task 3: Run the six measured runs, interleaved

- **Action**: run only
- **Implement**: in order: in-net-1, host-1, in-net-2, host-2, in-net-3, host-3. Each in the background, waiting for it to finish before the next starts (never two at once: they share one database).
  - **Before each run:** check no other pytest is using the container (`tasklist | grep -i python` / `docker stats --no-stream harness-libsql-dev` near-idle CPU). Record the start time.
  - **In-net run `i`:**
    ```bash
    docker run --rm --network harness-test-net \
      -v "C:/Users/tobip/AppData/Local/Temp/prd014-story006:/spike" -e PYTHONPATH=/spike \
      -e SPIKE_OUT=/spike/in-net-$i -e SPIKE_ARM=in-net \
      -e HARNESS_TEST_LIBSQL_URL=http://harness-libsql-dev:8080 \
      -e DATABASE_URL=http://harness-libsql-dev:8080 -e TURSO_AUTH_TOKEN= \
      <image> python -m pytest tests/ -m db -q -rA -p no:cacheprovider -p spike_dump \
      > "$S/in-net-$i.log" 2>&1
    ```
    No `--add-host` (story note).
  - **Host run `i`** (repo root, `HARNESS_TEST_LIBSQL_URL` unset, so default `127.0.0.1:8080`):
    ```bash
    SPIKE_OUT="$S/host-$i" SPIKE_ARM=host PYTHONPATH="$S;." \
      /c/Users/tobip/.venvs/harness-ai/Scripts/python.exe -m pytest tests/ -m db -q -rA \
      -p no:cacheprovider -p spike_dump > "$S/host-$i.log" 2>&1
    ```
  - **After each run:** record exit status, the final summary line, `grep -c "libsql verdict: likely infrastructure"` and `grep "libsql verdict"` lines, and that `<run>.summary.json` exists. If a run exits early (endpoint probe failed), record that and repeat that run once.
- **Validate**: six logs, six `.jsonl`, six `.summary.json` in scratch.

### Task 4: Summarize, and repeat if inconclusive

- **File**: `%TEMP%\prd014-story006\summarize.py`
- **Action**: CREATE (scratch)
- **Implement**: reads every `*.summary.json` / `*.jsonl` / `*.log` in the dir and prints an ASCII Markdown table, one row per run: arm, run, collected / passed / failed / errors (from the log's last line), wall time, driver calls, slowest call, **calls ≥ 10 s**, **dead-stream events**, **connect-timeout events** (`tcp connect error` + `os error 10060`, Finding 5), **absorbed** (events in a test whose outcome is `passed`), `likely infrastructure` verdict lines, `no infrastructure signal` verdict lines. Then per-arm totals and rate per 1,000 driver calls. Also a list of every event (nodeid, op, seconds, idle, error, outcome), and the raw error labels seen.
  - **Stall event** = one recorded call that is ≥ 10 s **or** carries an infrastructure label. A call that is both counts once.
  - **Decision rule (story AC 4):**
    - **Confirmed:** zero stall events across the in-net runs, and ≥ 1 across the host runs.
    - **Refuted:** in-net stall events at a comparable rate. Use the rate per 1,000 calls. If the in-net rate is ≥ 25% of the host rate, call it refuted. If in-net > 0 but < 25% of host, the story's three-way rule still says **refuted** (forwarding is not the whole cause). State the ratio and flag in the recommendation that forwarding may aggravate it.
    - **Inconclusive:** zero in both arms. Run up to three more host runs (host-4..6, same command). If one stalls, immediately run one more in-net run so the comparison stays interleaved, then apply the rule above to all runs. If none stalls, the conclusion is **inconclusive: could not be reproduced**.
  - `no infrastructure signal` failures are not stall events. List them separately, with whether the same nodeid failed in the other arm (environment difference vs. real defect).
  - Note, without tracing, anything about stall durations (e.g. a cluster at ~15 s), as the story allows (PRD Section 4).
- **Validate**: `python summarize.py > summary.md` runs. The totals match a manual `grep -c` of verdict lines in the logs.

### Task 5: Restore Docker state

- **Action**: Docker state
- **Implement**: `docker network disconnect harness-test-net harness-libsql-dev`, `docker network rm harness-test-net`. Confirm `harness-libsql-dev` is still up, on `bridge` only, with port 8080 published (`docker ps`, `docker inspect ... .NetworkSettings.Networks`). No `--rm` container remains (`docker ps -a`). **The built image is left in place** for STORY-008 (several GB). Record that in the report with its name and size, and the command to remove it (`docker image rm <image>`). Leave the container running if it was running at Task 0.
- **Validate**: `docker network ls` and `docker ps -a` match `state-before.txt` except for the image, which the report names.

### Task 6: Write the spike report

- **File**: `.agents/spikes/PRD-014-docker-network-stalls.md`
- **Action**: CREATE (`mkdir -p .agents/spikes`)
- **Implement**: sections:
  1. **Conclusion** (first line, bold): `confirmed` / `refuted` / `inconclusive`, with the arm totals in one sentence.
  2. **Question and hypothesis** (D5, PRD Section 12 Phase 3).
  3. **Setup:** date, epic commit, image name + build commit, Docker Desktop version, libsql image digest, network topology (host → `127.0.0.1:8080` forwarded; container → `harness-libsql-dev:8080` on `harness-test-net`), env vars per arm, run order and start times.
  4. **Deviations from the PRD recipe:** `docker run` instead of `docker compose run` (Finding 1), the scratch mount instead of a repo mount, the fallback image if used, `-p no:cacheprovider`, the connect-timeout family counting (Finding 5), the small-model note (Finding 9).
  5. **Results:** the summarizer table, the per-arm totals and rates, every stall event, every verdict line, and failures without infrastructure signal.
  6. **Recommendation for STORY-008** (one paragraph): confirmed → document/script an in-network `-m db` recipe (PRD Section 13, e.g. `scripts/test-db-in-network.sh`). Refuted → `pytest-rerunfailures --only-rerun "STREAM_EXPIRED|os error 10060"` scoped to `-m db` (note that the Linux spelling would need `tcp connect error` too). Inconclusive → no follow-up beyond keeping the verdict line, or the rerun policy only if stalls come back in STORY-007's sweep.
  7. **State left behind:** network removed, container restored, image left (name, size, removal command).
  8. **Appendix:** `spike_dump.py` and `summarize.py` sources, and the exact commands.
  ASCII-safe text is not required in `.md`, but keep quoted log lines verbatim.
- **Validate**: every figure in the report traces to `summary.md` or a log.

### Task 7: PRD Appendix "D5 result"

- **File**: `.agents/PRDs/PRD-014-test-suite-db-isolation/PRD.md`
- **Action**: UPDATE (replace `_To be filled by STORY-006._` under `### D5 result`, line ~455)
- **Implement**: the conclusion sentence with both arms' stall counts and runs, a link to `../../spikes/PRD-014-docker-network-stalls.md`, and the same one-paragraph STORY-008 recommendation. Bump frontmatter `updated:` only if it changes.
- **Validate**: `git diff --stat` shows only `.agents/` paths.

### Task 8: Final diff check

- **Validate**: `git status --short` / `git diff --stat` show only `.agents/spikes/PRD-014-docker-network-stalls.md`, the PRD, and the story/index/plan/report bookkeeping. `git diff --stat -- tests app chat_ui scripts` is empty, and nothing from `%TEMP%\prd014-story006\` is in the tree.

---

## End-to-End Tests

- [ ] In-network pre-flight returns `(1,)` from `harness-libsql-dev:8080` (Task 2.4)
- [ ] The plugin smoke runs (host and in-net) leave the test outcomes unchanged and write a summary with `calls > 0` (Tasks 1, 2.5)
- [ ] Six measured runs completed, interleaved, never concurrent, each with log + jsonl + summary (Task 3)
- [ ] `summarize.py` totals agree with `grep -c "libsql verdict"` on the logs (Task 4)
- [ ] Docker state after Task 5 equals Task 0's except for the named image

---

## Validation

```bash
# instrument does not change outcomes
SPIKE_OUT=$S/smoke SPIKE_ARM=host PYTHONPATH="$S;." python -m pytest tests/test_conftest_fixtures.py -m db -q -p no:cacheprovider -p spike_dump
# nothing outside .agents/ changed
git diff --stat -- tests app chat_ui scripts      # empty
docker network ls | grep harness-test-net          # nothing
docker inspect harness-libsql-dev --format '{{json .NetworkSettings.Networks}}'   # bridge only
```

---

## Risks

| # | Risk | Mitigation |
|---|---|---|
| R1 | `docker compose build` fails or takes too long (`reflex export` downloads bun/node; pip/spaCy over a TLS-intercepting network) | Retry once. Then build a test-only image from a scratch `Dockerfile.spike` with the same test environment: `FROM python:3.11-slim`, `COPY requirements.txt`, `pip install -r`, `python -m spacy download en_core_web_lg`, `COPY . .`, `WORKDIR /app` (the final stage minus Caddy and the frontend), via `docker build -f "$S/Dockerfile.spike" -t harness-spike .`. Record it as a deviation. The networking under test is the same |
| R2 | Bind mount from Windows into the container fails or garbles paths | Only the short scratch dir is mounted, never the OneDrive repo. Use `MSYS_NO_PATHCONV=1` in Git Bash. If the mount still fails, run without `-v`, then `docker cp` the dumps out of a named (not `--rm`) container and remove it afterwards |
| R3 | Another session uses or resets `harness-libsql-dev` mid-run | Check before each run (Task 3). If interference is seen, discard that run, repeat it, and record it. If it keeps happening, stop and ask the user before switching to a throwaway container, since the AC names `harness-libsql-dev` |
| R4 | In-network failures with a non-stall cause (missing `en_core_web_sm`, Linux-vs-Windows behaviour, a test that assumes `127.0.0.1`) | They carry `no infrastructure signal` and are not stall events. Report them separately, compared with the host arm. They do not affect the conclusion |
| R5 | A stall hits the unrecorded session probe and the run exits | Visible in the log as the unreachable-server exit. Record it as a stall event for that arm (by hand, with its message) and repeat the run once |
| R6 | Zero stalls anywhere (stalls are intermittent) | The story's inconclusive path: up to three more host runs, interleaved with an in-net run if one stalls (Task 4) |
| R7 | Time: six to twelve ~5 min runs plus a build | Background runs. If interrupted, the per-run files allow resuming at the next run in the order |

---

## Acceptance Criteria

(Copied from story `STORY-006`)

- [ ] Given `harness-libsql-dev` attached to a user network `harness-test-net`, when `pytest tests/ -m db -q -rA` runs three times from the `harness-ai` image on that network with `HARNESS_TEST_LIBSQL_URL` and `DATABASE_URL` set to `http://harness-libsql-dev:8080` and `TURSO_AUTH_TOKEN=` empty, then each run's counts, failures and verdict lines are recorded.
- [ ] Given the same session, when `pytest tests/ -m db -q -rA` runs three times from the host against `http://127.0.0.1:8080` (control arm), then the same figures are recorded.
- [ ] Given both arms, when the STORY-005 recorder's data is summarized, then the report counts per run calls ≥ 10 s, `STREAM_EXPIRED` and `os error 10060` events (including stalls absorbed by `_reset_database()`'s retry, not only failures).
- [ ] Given those counts, when concluded, then `.agents/spikes/PRD-014-docker-network-stalls.md` states one of **confirmed** (zero stalls in-network and at least one on the host), **refuted** (in-network stalls at a comparable rate) or **inconclusive** (zero in both arms: repeat up to three more host runs, then record that it could not be reproduced). The conclusion and a one-paragraph recommendation for STORY-008 are copied into PRD Appendix "D5 result".
- [ ] Given the story's diff, when reviewed, then it contains the spike report, the PRD appendix update and at most a helper script. No test or app code changes. The containers and network are left as they were found, or the report says what was left.
- [ ] All tasks completed
- [ ] Follows existing patterns (scratch instrument outside the repo, quoted in the report, as in STORY-001)
