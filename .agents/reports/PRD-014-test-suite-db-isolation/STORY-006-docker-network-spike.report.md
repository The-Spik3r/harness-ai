---
story: STORY-006
prd: PRD-014
plan: .agents/plans/PRD-014-test-suite-db-isolation/completed/STORY-006-docker-network-spike.plan.md
epic_branch: epic/PRD-014-test-suite-db-isolation
commit: f905425
status: COMPLETE
completed: 2026-10-21
---

# Implementation Report — STORY-006: Spike: stalls inside the Docker network (D5)

**Plan**: `.agents/plans/PRD-014-test-suite-db-isolation/completed/STORY-006-docker-network-spike.plan.md`
**Epic Branch**: `epic/PRD-014-test-suite-db-isolation`
**Commit**: `f905425`

## Summary

The spike ran `pytest tests/ -m db` six valid times, interleaved: three from a container of the `harness-ai` image on `harness-test-net`, reaching `http://harness-libsql-dev:8080` by name, and three from the host through Docker Desktop's port forwarding at `127.0.0.1:8080`. A scratch plugin dumped every stall event the STORY-005 recorder saw, including ones the reset retry absorbed. **Result: confirmed.** 0 stall events in 143,461 in-network calls against 2 in 143,604 host calls: a 21.05 s `tcp connect error` (`os error 10060`) at setup, then an absorbed `STREAM_EXPIRED`. The sample is small: zero events would still happen about 13.5% of the time if both arms really stalled at the host's rate. The report is at `.agents/spikes/PRD-014-docker-network-stalls.md`. The conclusion and the STORY-008 recommendation (in-network recipe) are in PRD Appendix "D5 result". No test or app code changed.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 0 | Record starting state (git, containers, networks, images, Docker version, libsql digest) | scratch `state-before.txt` | ✅ |
| 1 | Scratch plugin `spike_dump`. Smoke: 16 passed with and without it, 369 calls. Event path checked with the threshold lowered to 0.01 s by a throwaway helper (105 events, outcomes attached) | scratch `spike_dump.py` | ✅ |
| 2 | `docker compose build harness-ai` (built first try, 1.86 GB). Network created, container connected. Pre-flight `(1,)` both ways. `en_core_web_sm` absent. In-network smoke: 16 passed, 369 calls | Docker (temporary) | ✅ |
| 3 | Six measured runs, interleaved, pre-checked for concurrent use. host-3 discarded (system sleep) and rerun as host-3r | scratch logs, dumps | ✅ (with deviation) |
| 4 | Summarizer, decision rule applied: **confirmed**. Totals cross-checked against `grep -c "libsql verdict"` per log | scratch `summarize.py`, `summary.md` | ✅ |
| 5 | Network disconnected and removed. Container on `bridge` only, port 8080, running. Image left for STORY-008 | Docker | ✅ |
| 6 | Spike report, instrument sources in its appendix | `.agents/spikes/PRD-014-docker-network-stalls.md` | ✅ |
| 7 | PRD Appendix "D5 result", `updated` bumped | `.agents/PRDs/PRD-014-test-suite-db-isolation/PRD.md` | ✅ |
| 8 | Diff check: only `.agents/` paths | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`python -c "from app.main import app"`) | ✅ OK (no code changed) |
| Frontend lint | N/A: the repo has no `frontend/` (the chat UI is Reflex) |
| Tests | N/A: no code written. The instrument was smoke-tested (Task 1, Task 2.5) |
| `git diff --stat -- tests app chat_ui scripts` | ✅ empty |
| E2E | ✅ 5/5 (below) |

### E2E (from the plan)

- [x] In-network pre-flight returns `(1,)` from `harness-libsql-dev:8080`
- [x] Plugin smoke runs (host and in-network) leave outcomes unchanged (16 passed) and write a summary with `calls > 0` (369)
- [x] Six measured runs completed, interleaved, never concurrent, each with log, jsonl and summary (host-3 replaced by host-3r, below)
- [x] `summarize.py` verdict totals agree with `grep -c` on every log (in-net 3/3/3 `no infrastructure signal`, host-3r 1 `likely infrastructure`, host-1/2 none)
- [x] Docker state after Task 5 equals Task 0's, except for the named image

### Run figures

| run | passed | failed | errors | wall s | calls | slowest s | stall events |
|---|---|---|---|---|---|---|---|
| in-net-1 | 1267 | 3 | 0 | 193.4 | 47,813 | 0.159 | 0 |
| host-1 | 1270 | 0 | 0 | 229.3 | 47,861 | 2.047* | 0 |
| in-net-2 | 1267 | 3 | 0 | 184.7 | 47,824 | 0.141 | 0 |
| host-2 | 1270 | 0 | 0 | 237.0 | 47,888 | 2.031* | 0 |
| in-net-3 | 1267 | 3 | 0 | 181.1 | 47,824 | 0.150 | 0 |
| host-3r | 1269 | 0 | 1 | 249.3 | 47,855 | 21.047 | 2 |

\* the deliberate dead-endpoint connect in two tests, not a stall. The three in-network failures are `tests/test_measure_usage_latency.py` refusing the non-local hostname (`no infrastructure signal`). They pass on the host. Verdict line from host-3r: `libsql verdict: likely infrastructure -- execute took 21.05 s and ended in tcp connect error`.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `.agents/spikes/PRD-014-docker-network-stalls.md` | CREATE | +393 |
| `.agents/PRDs/PRD-014-test-suite-db-isolation/PRD.md` | UPDATE | +4/-2 |
| `.agents/plans/PRD-014-test-suite-db-isolation/completed/STORY-006-docker-network-spike.plan.md` | CREATE (archived) | +346 |
| `.agents/reports/PRD-014-test-suite-db-isolation/STORY-006-docker-network-spike.report.md` | CREATE | this file |
| `.agents/stories/.../STORY-006-docker-network-spike.md`, `.agents/PRDs/.../index.md` | UPDATE | bookkeeping |

## Deviations from Plan

1. **host-3 discarded, rerun as host-3r.** Windows entered S3 sleep at 22:21:56 and woke at 00:31:46, mid-run (Kernel-Power 42/107). One call "took" 7,791 s, since `time.monotonic()` counts through sleep on Windows. A 15.05 s `STREAM_EXPIRED` failure came within a minute of waking. Neither event is counted, because they can't be told apart from resume effects. host-3r was wrapped in a scratch `keepawake.ps1` (`SetThreadExecutionState`, held only for that run, no power setting changed). This treats the sleep as interference, per the plan's R3. It also breaks the interleaving for that run: host-3r started 1 h 45 min after in-net-3.
2. **Expected errors excluded from stall events.** Two tests point the driver at a dead endpoint on purpose and pass. Their instant (Linux) or 2 s (Windows) `tcp connect error`s show up in every run. The plan's definition ("any infrastructure label") would have counted them, so the summarizer lists them separately by nodeid, below 10 s only. Found after in-net-1, before any conclusion was drawn.
3. **The runner wrote host-1's dumps under the wrong name.** A `\$` escaped the variable, so they landed in `%TEMP%\prd014-story006$name.*`. The files were complete. They were moved to `host-1.*` and the runner was fixed before the next host run.
4. **The plan's pre-check counted Python processes.** That matched four markitdown MCP servers, so the runner counts processes whose command line mentions `pytest` instead. It was 0 before every run.
5. **"Refuted" thresholds unused.** The 25% rate rule never came into play: the in-network rate was 0.

## Tests Written

None. The story allows no test or app code changes (AC 5). The scratch instrument was smoke-tested instead (Tasks 1, 2.5). Its source is in the spike report's Appendix B.

## Acceptance Criteria

- [x] Given `harness-libsql-dev` attached to a user network `harness-test-net`, when `pytest tests/ -m db -q -rA` runs three times from the `harness-ai` image on that network with `HARNESS_TEST_LIBSQL_URL` and `DATABASE_URL` set to `http://harness-libsql-dev:8080` and `TURSO_AUTH_TOKEN=` empty, then each run's counts, failures and verdict lines are recorded. (Report, *Results*. Run with `docker run`, since `docker compose run` has no `--network`)
- [x] Given the same session, when `pytest tests/ -m db -q -rA` runs three times from the host against `http://127.0.0.1:8080` (control arm), then the same figures are recorded. (host-1, host-2, host-3r. host-3 recorded as discarded)
- [x] Given both arms, when the STORY-005 recorder's data is summarized, then the report counts per run calls ≥ 10 s, `STREAM_EXPIRED` and `os error 10060` events (including stalls absorbed by `_reset_database()`'s retry, not only failures). (Per-run table. One absorbed `STREAM_EXPIRED` in host-3r)
- [x] Given those counts, when concluded, then `.agents/spikes/PRD-014-docker-network-stalls.md` states one of **confirmed**, **refuted** or **inconclusive**. The conclusion and a one-paragraph recommendation for STORY-008 are copied into PRD Appendix "D5 result". (**Confirmed**, with the sample-size caveat)
- [x] Given the story's diff, when reviewed, then it contains the spike report, the PRD appendix update and at most a helper script. No test or app code changes. The containers and network are left as they were found, or the report says what was left. (No helper committed. Network removed. Image `harness-ai-harness-ai:latest` left and named in the report)
