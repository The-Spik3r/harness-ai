---
story: STORY-008
prd: PRD-014
slug: d5-follow-up
title: "(Conditional on D5) Act on the spike: in-network test recipe, or a rerun policy scoped to infrastructure failures"
type: ENHANCEMENT
complexity: LOW
epic_branch: epic/PRD-014-test-suite-db-isolation
created: 2026-10-21
---

# Plan: Act on the D5 result (in-network `db` test recipe)

## Summary

PRD Appendix "D5 result" reads **confirmed, on thin evidence**: 0 stall events in 143,461 in-network driver calls, against 2 in 143,604 host calls (spike: `.agents/spikes/PRD-014-docker-network-stalls.md`). So this story takes the **confirmed arm only**. It adds `scripts/test-db-in-network.sh`, which (re)builds the `harness-ai` image, creates `harness-test-net` and connects `harness-libsql-dev` to it idempotently, then runs `python -m pytest tests/ -m db` in a throwaway container that reaches the server by name, with no Docker Desktop port forwarding. The three `tests/test_measure_usage_latency.py` tests that refuse a non-local host name by design are deselected in the script. README *Running Tests* replaces its "A documented recipe is to follow" paragraph with the script. The **rerun arm is not implemented**: the spike says a scoped rerun policy is not needed now, and D4's "no retry" stands. The **inconclusive arm does not apply**. Nothing under `app/` or `chat_ui/` changes, and no test is added or edited.

## User Story

As a harness developer on Windows + Docker Desktop
I want a one-command way to run the `db` tests from inside the Docker network
So that storage tests stop stalling behind Docker Desktop's port forwarding

## Story Reference

- Story file: `.agents/stories/PRD-014-test-suite-db-isolation/STORY-008-d5-follow-up.md`
- PRD: `.agents/PRDs/PRD-014-test-suite-db-isolation/PRD.md` (Sections 7 F8, 13; Appendix D4, D5 result)
- Spike: `.agents/spikes/PRD-014-docker-network-stalls.md` (Setup, Deviations 1/5/8, Recommendation, Appendix A)

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT |
| Complexity | LOW |
| Systems Affected | `scripts/` (new shell script), `.gitattributes` (new), `README.md` |
| Story | STORY-008 |
| PRD | PRD-014 |
| Epic Branch | `epic/PRD-014-test-suite-db-isolation` (commit directly on this branch) |

## Arm decision (Phase 1 gate)

| D5 outcome | Story AC | This plan |
|---|---|---|
| Confirmed | AC 1: committed script + README + one green run recorded | **Implemented** |
| Refuted / stalls unavoidable | AC 2: `pytest-rerunfailures` scoped to `db` | Not applicable. Spike: "A scoped rerun policy is not needed for now." |
| Inconclusive | AC 3: close or block | Not applicable |
| Any arm | AC 4: full-suite counts equal baseline, no `app/` / `chat_ui/` change | **Verified** (Task 6) |

The spike's caveat carries over: the sample is small (about a 13.5% chance of zero in-network events by luck), so validation runs the script **three times**. **Any in-network stall (a `likely infrastructure` verdict, or a call of 10 s or more visible in a failure) reopens D5.** The report records it and the story does not close as confirmed.

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | Story frontmatter `skills: []`. `.agents/skills/` holds only `frontend-design`, which doesn't apply (no UI) | — |

---

## Patterns to Follow

### The validated in-network command (the script automates exactly this)
```bash
# SOURCE: .agents/spikes/PRD-014-docker-network-stalls.md Appendix A
docker compose build harness-ai
docker network create harness-test-net
docker network connect harness-test-net harness-libsql-dev
docker run --rm --network harness-test-net \
  -e HARNESS_TEST_LIBSQL_URL=http://harness-libsql-dev:8080 \
  -e DATABASE_URL=http://harness-libsql-dev:8080 -e TURSO_AUTH_TOKEN= \
  harness-ai-harness-ai python -m pytest tests/ -m db -q -rA -p no:cacheprovider
```
`docker run`, not `docker compose run`: compose has no `--network` (Deviation 1), and `docker run` also keeps `env_file: .env`'s real secrets out of the container. All three `-e` overrides are needed for the reasons README *Running Tests* already gives for the in-container run (README.md:912-918).

### Endpoint override the suite already honours
```python
# SOURCE: tests/conftest.py:64,77
_ENDPOINT = os.environ.get("HARNESS_TEST_LIBSQL_URL", "http://127.0.0.1:8080")
os.environ.setdefault("DATABASE_URL", _ENDPOINT)
```

### The three tests to deselect in-network (already `db` via `_DB_NODEIDS`)
```python
# SOURCE: tests/conftest.py:119-121
"tests/test_measure_usage_latency.py::test_a_short_run_reports_both_calls_and_cleans_up",
"tests/test_measure_usage_latency.py::test_a_refused_admit_ends_the_run_without_a_report",
"tests/test_measure_usage_latency.py::test_a_changed_statement_count_ends_the_run_without_a_report",
```
They call `bench.main(["--runs", "3"])`, and `scripts/measure_usage_latency.py:102-115` `_guard_local` raises `SystemExit: Refusing to write to a non-local database` for any host outside `_LOCAL_HOSTS`. That is the script's own safety guard working. **Deselect them, don't weaken the guard or edit the tests.** The host-side `-m db` and full runs still cover them.

### README tone and structure
```markdown
<!-- SOURCE: README.md:910 (the paragraph this story replaces) -->
**If `db` tests flake on Docker Desktop.** The stalls behind most infrastructure verdicts were measured only behind Docker Desktop's port forwarding: ... A documented recipe is to follow.
```
Bold lead-in sentence, then plain prose and one fenced `bash` block, as in the surrounding *Running Tests* paragraphs (README.md:860-941).

### Shell conventions
There is no shell script in the repo yet (`scripts/` holds Python only). Follow the Python scripts' header style instead: a top comment that says what the script does, why (PRD/story reference), and a usage example (`scripts/measure_usage_latency.py:1-50`). Use `set -euo pipefail`, quote every expansion, and put the tunables in `${VAR:-default}` variables at the top.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `scripts/test-db-in-network.sh` | CREATE | One-command in-network `-m db` run: idempotent network setup, image build, `docker run` with the three overrides, three deselects, pass-through args |
| `.gitattributes` | CREATE | `*.sh text eol=lf`. `core.autocrlf=true` here and no `.gitattributes` exists, so without it the script would be checked out with CRLF and bash fails on `$'\r'` |
| `README.md` | UPDATE | *Running Tests*: replace the "If `db` tests flake on Docker Desktop" paragraph (line 910) with the script and its caveats |

Not changed: anything under `app/`, `chat_ui/`, `tests/`, `requirements.txt`, `Dockerfile`, `docker-compose.yml`.

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: `.gitattributes` for shell scripts

- **File**: `.gitattributes`
- **Action**: CREATE
- **Implement**: one comment line plus `*.sh text eol=lf`. Add no other rules: a repo-wide `* text=auto` would renormalize every file.
- **Validate**: after Task 2, `git add --dry-run scripts/test-db-in-network.sh` shows no CRLF warning, and `git check-attr eol scripts/test-db-in-network.sh` prints `eol: lf`.

### Task 2: `scripts/test-db-in-network.sh`

- **File**: `scripts/test-db-in-network.sh`
- **Action**: CREATE (then `git update-index --chmod=+x` once added, since Windows has no exec bit)
- **Implement**:
  - Shebang `#!/usr/bin/env bash` and a header comment: what it does; why (D5 confirmed: stalls appear only behind Docker Desktop port forwarding, spike path); the three deselects and why; usage, e.g. `scripts/test-db-in-network.sh`, `scripts/test-db-in-network.sh --no-build -x -k audit`.
  - `set -euo pipefail`. `export MSYS_NO_PATHCONV=1`, so Git Bash doesn't rewrite container-side paths (a no-op on Linux/macOS). `cd "$(dirname "$0")/.."` so it works from any cwd.
  - Tunables: `NETWORK="${HARNESS_TEST_NETWORK:-harness-test-net}"` and `SERVER="${HARNESS_LIBSQL_CONTAINER:-harness-libsql-dev}"`.
  - Optional first arg `--no-build` skips the build. Every remaining arg goes to pytest (`"$@"`).
  - **Server check**: `docker inspect -f '{{.State.Running}}' "$SERVER"` must print `true`. Otherwise print to stderr how to start it (`docker start $SERVER`, or the README's `docker run -d --name harness-libsql-dev ...`) and exit 2. Don't create the server: README owns that command and its pinned digest.
  - **Network, idempotent**: `docker network inspect "$NETWORK" >/dev/null 2>&1 || docker network create "$NETWORK" >/dev/null`.
  - **Connect, idempotent**: list the server's networks with `docker inspect -f '{{range $k, $_ := .NetworkSettings.Networks}}{{println $k}}{{end}}' "$SERVER"`. `grep -qxF "$NETWORK"` that output, and run `docker network connect "$NETWORK" "$SERVER"` only if it's missing. Connecting is additive: the server keeps `bridge` and its `0.0.0.0:8080` publish, so host-side runs are unaffected. **Don't tear the network down at exit**, because a rerun reuses it.
  - **Image**: unless `--no-build`, `docker compose build harness-ai`, which is layer-cached. Resolve the tag with `image="$(docker compose config --images harness-ai)"` (prints `harness-ai-harness-ai` here) rather than hard-coding it, so a clone in another directory still works.
  - **Run**: `exec docker run --rm --network "$NETWORK" -e HARNESS_TEST_LIBSQL_URL="$url" -e DATABASE_URL="$url" -e TURSO_AUTH_TOKEN= "$image" python -m pytest tests/ -m db -q -p no:cacheprovider --deselect <3 nodeids> "$@"`, with `url="http://$SERVER:8080"`. Don't bind-mount the repo (spike Deviation 2): the image's copy is what was validated, and nothing is written into the OneDrive tree. `exec` makes pytest's exit code the script's.
- **Mirror**: spike Appendix A (commands), `scripts/measure_usage_latency.py:1-50` (header style)
- **Validate**: `bash -n scripts/test-db-in-network.sh` passes. Run it with `harness-libsql-dev` stopped: exit 2 and the start hint, with no network created before the check fails.

### Task 3: README *Running Tests*

- **File**: `README.md`
- **Action**: UPDATE (line 910's paragraph only)
- **Implement**: keep the bold lead-in **If `db` tests flake on Docker Desktop.** and the measured numbers sentence. Replace the rest with:
  - run `scripts/test-db-in-network.sh` (from Git Bash on Windows), in a fenced `bash` block showing the plain call and a `--no-build -k ...` example;
  - what it does in one sentence: builds the image, puts `harness-libsql-dev` on `harness-test-net` (idempotent, left in place) and runs `-m db` in a throwaway container that reaches it by name;
  - caveats: it tests the code **baked into the image**, so leave out `--no-build` after a change; the three `tests/test_measure_usage_latency.py` tests are deselected there because their script refuses a non-local host name, and the host run covers them; `docker compose config` needs the `.env` from [Quickstart — Docker](#quickstart--docker);
  - the host-side `pytest tests/ -m db` stays supported, with the verdict line for its rare stalls;
  - keep the spike link as the evidence.
- **Validate**: re-read the section. No "recipe is to follow" text remains, and every anchor link resolves to an existing heading.

### Task 4: Prove the script (three in-network runs)

- **Action**: RUN (no file change)
- **Implement**: Start Docker Desktop and `docker start harness-libsql-dev` (memory: often stopped). Make sure no other pytest process is running, since a `db` run resets the shared DB. Then:
  1. Run 1: `scripts/test-db-in-network.sh 2>&1 | tee <scratch>/in-net-1.log`, which includes the build. Record the build time.
  2. Runs 2 and 3: `scripts/test-db-in-network.sh --no-build 2>&1 | tee <scratch>/in-net-$i.log`.
  3. Idempotency: run 2 finds the network and the connection already there, without errors.
  4. `grep -c "libsql verdict" <scratch>/in-net-*.log`. Expect 0.
  - Wrap long runs in the `SetThreadExecutionState` keep-awake helper (memory: S3 sleep invalidates timings).
- **Expected per run**: exit 0. `1267 passed, 1 skipped, 2642 deselected` (1,271 `db` − 3 deselected = 1,268 selected; the spike's in-net counts were 1,267 passed + 3 failed + 1 skipped). About 180-195 s of pytest time.
- **If a run stalls** (any `likely infrastructure` verdict): it does **not** pass. Record the verdict line in the report and treat D5 as reopened (PRD D5 result, spike Recommendation). Don't add retries.

### Task 5: Docs regression check

- **Action**: RUN
- **Validate**: `git diff --stat` lists only `.gitattributes`, `scripts/test-db-in-network.sh`, `README.md` (plus `.agents/` bookkeeping). `git diff --name-only -- app/ chat_ui/ tests/` is empty.

### Task 6: Full suite against the baseline (AC 4)

- **Action**: RUN (host, background, keep-awake)
- **Implement**: `C:/Users/tobip/.venvs/harness-ai/Scripts/python.exe -m pytest tests/ -q -p no:cacheprovider`, piped to a log via `cmd /c "... > log 2>&1"` (memory: byte-clean logs).
- **Expected**: 3,910 collected, 3,883 passing, 27 skipped (STORY-001's 3,854 / 3,827 / 27 + the epic's 56, as in STORY-007). Any failure must carry a `likely infrastructure` verdict and pass when rerun alone, or it counts as real. Run `tests/test_untouched_app.py` (inside the full run) to confirm the pinned PRD-006 suites are intact.

---

## End-to-End Tests

- [ ] Server stopped → script exits 2 with the `docker start harness-libsql-dev` hint and creates no network
- [ ] First run on a clean state (`harness-test-net` absent) creates the network, connects the server, builds and runs green
- [ ] Second run with the network already present: no "already exists" error, runs green
- [ ] Three runs green at 1,267 passed / 1 skipped / 2,642 deselected, 0 `libsql verdict` lines
- [ ] Pass-through works: `scripts/test-db-in-network.sh --no-build -k test_init_db` selects a subset and exits 0 (document `-k`/`-x`, not path args, which would stack with `tests/`)
- [ ] After the runs, `harness-libsql-dev` still answers on `127.0.0.1:8080` from the host, e.g. a host-side `pytest tests/test_conftest_fixtures.py -m db -q` passes, proving the connect didn't break port publishing
- [ ] Full host suite: 3,910 / 3,883 / 27

---

## Validation

```bash
bash -n scripts/test-db-in-network.sh
git check-attr eol scripts/test-db-in-network.sh          # eol: lf
scripts/test-db-in-network.sh                              # 1267 passed, 1 skipped
scripts/test-db-in-network.sh --no-build                   # x2
grep -c "libsql verdict" <scratch>/in-net-*.log            # 0 each
git diff --name-only -- app/ chat_ui/ tests/               # empty
python -m pytest tests/ -q -p no:cacheprovider             # 3,910 / 3,883 / 27
```

---

## Risks

| # | Risk | Mitigation |
|---|---|---|
| P1 | CRLF checkout breaks the script (`core.autocrlf=true`, no `.gitattributes`) | Task 1, `*.sh text eol=lf`. Verify with `git check-attr` and run it from a fresh checkout of the file (`git rm --cached` + `git checkout`) |
| P2 | A stale image tests old code | Build by default. `--no-build` is opt-in and the README says so. The tree since `554101b` changed only docs, but the default stays safe |
| P3 | The build's `reflex init/export` builder stage reruns on every code change (slow, needs network) | Accepted: layer cache keeps `pip install` and the spaCy model. Record the build time in the report. `--no-build` for repeat runs |
| P4 | `docker compose config` / `build` fails without `.env` (`env_file`) | Documented in README. The script's `set -e` surfaces compose's own "env file not found" message |
| P5 | An in-network stall during validation | Reopens D5 (Task 4). Report it and don't paper over it with retries |
| P6 | A `db` run resets the shared DB under another session (memory: shared container) | Check for other pytest processes before each run, the same precondition as the spike |
| P7 | Hard-coded test nodeids drift if those tests are renamed | pytest ignores an unknown `--deselect`, so a renamed test would run in-network and fail with the self-explaining `Refusing to write to a non-local database`. That's loud, not silent. The script comment points at `tests/conftest.py`'s `_DB_NODEIDS` entries so both get edited together |
| P8 | Machine sleeps mid-run | Keep-awake wrapper (memory) |

---

## Acceptance Criteria

(Copied from story `STORY-008`)

- [ ] Given D5 **confirmed**, when this story lands, then a committed script (e.g. `scripts/test-db-in-network.sh`) runs `-m db` from the `harness-ai` image on `harness-test-net`, creating the network idempotently. README *Running Tests* documents it, and one run of the script is recorded green in the report. *(Implemented; three runs recorded.)*
- [ ] Given D5 **refuted** or stalls unavoidable on Docker Desktop, ... `pytest-rerunfailures` ... *(N/A: D5 confirmed. The report quotes the spike's Recommendation: "A scoped rerun policy is not needed for now.")*
- [ ] Given **inconclusive**, ... *(N/A: D5 confirmed.)*
- [ ] Given whichever arm is implemented, when the full suite runs, then counts equal STORY-001's baseline and no file under `app/` or `chat_ui/` changes. *(Baseline as carried by STORY-007: 3,910 / 3,883 / 27.)*
- [ ] All tasks completed
- [ ] Follows existing patterns
