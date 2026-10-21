---
prd: PRD-014
story: STORY-006
decision: D5
conclusion: confirmed
date: 2026-10-21
---

# Spike: do the libSQL stalls come from Docker Desktop's port forwarding? (D5)

**Conclusion: confirmed, on thin evidence.** Over three interleaved runs per arm, with about 143,500 driver calls each, the in-network arm recorded **0 stall events** and the host arm **2**: a 21.05 s `tcp connect error` (`os error 10060`) that errored a test's setup, and a `STREAM_EXPIRED` in the next test that `_reset_database()`'s retry absorbed. That meets the story's rule for *confirmed* (zero in-network, at least one on the host). The sample is small. If both arms really stalled at the host's rate, the in-network arm would still see zero events about 13.5% of the time (Poisson, expected 2.0 events, e^-2). So this settles the direction of STORY-008, not the size of the effect.

## Question and hypothesis

The brief and PRD-014 Section 1 record TCP connections to `harness-libsql-dev` stalling for 7–21 s. A stall past the server's ~10 s stream window ends in `STREAM_EXPIRED`. One during the TCP handshake ends in `tcp connect error ... (os error 10060)` after 21 s. Hypothesis D5: the stalls come from Docker Desktop's Windows port forwarding (host `127.0.0.1:8080` → WSL2 VM → container), not from the libSQL server or the driver. The test: run `-m db` from a container that reaches the server by name on a user network, with no forwarding, against a host-side control arm in the same session (PRD Section 12, Phase 3).

## Setup

| Item | Value |
|---|---|
| Date | 2026-10-20 21:59 to 2026-10-21 00:38 (-03:00) |
| Code | epic `epic/PRD-014-test-suite-db-isolation` @ `554101b`, worktree clean outside `.agents/` |
| In-network image | `harness-ai-harness-ai:latest` (`55fe13ea01f1`, 1.86 GB), from `docker compose build harness-ai` at `554101b`. Python 3.11.17, pytest 9.1.1 |
| Host | Windows 11, venv `C:\Users\tobip\.venvs\harness-ai` (CPython 3.11), pytest 9.1.1 |
| Docker Desktop | server 29.9.1, WSL2 (the PRD's Section 8 lists 29.8.2, now upgraded) |
| libSQL server | `harness-libsql-dev`, `ghcr.io/tursodatabase/libsql-server@sha256:6dd3eb27…` (unchanged), published on `0.0.0.0:8080` |
| In-network path | container on user network `harness-test-net` → `http://harness-libsql-dev:8080` (Docker DNS, no port forwarding) |
| Host path | `http://127.0.0.1:8080` (Docker Desktop port forwarding), `HARNESS_TEST_LIBSQL_URL` unset |
| In-network env | `HARNESS_TEST_LIBSQL_URL` and `DATABASE_URL` = `http://harness-libsql-dev:8080`, `TURSO_AUTH_TOKEN=` (empty). Secrets from the conftest's `setdefault`s, no `.env` |
| Command (both arms) | `python -m pytest tests/ -m db -q -rA -p no:cacheprovider -p spike_dump` |
| Selection | 1,271 `db` tests (2,639 deselected) |
| Instrument | scratch plugin `spike_dump` (Appendix A) reading STORY-005's recorder, unchanged. Smoke-checked first on `tests/test_conftest_fixtures.py -m db`: 16 passed with and without it, 369 calls recorded on the host and in-network alike |

**Run order (interleaved, never concurrent).** Before each run: no other pytest process on the machine, and `harness-libsql-dev` CPU at or below 0.13%.

| # | Run | Start | End | Note |
|---|---|---|---|---|
| 1 | in-net-1 | 21:59:48 | 22:03:06 | |
| 2 | host-1 | 22:03:42 | 22:07:35 | |
| 3 | in-net-2 | 22:08:07 | 22:11:17 | |
| 4 | host-2 | 22:11:25 | 22:15:25 | |
| 5 | in-net-3 | 22:15:34 | 22:18:38 | |
| – | host-3 | 22:18:47 | 00:32:51 | **Discarded:** the machine slept mid-run (below) |
| 6 | host-3r | 00:33:54 | 00:38:06 | Replacement, run with sleep blocked |

## Deviations from the PRD recipe

1. **`docker run`, not `docker compose run`.** `docker compose run` has no `--network` option, so the recipe as written doesn't parse. The image is the one `docker compose build harness-ai` produced. This also kept `env_file: .env` (real secrets) out of the container.
2. **Only the scratch directory was mounted** (`%TEMP%\prd014-story006` → `/spike`), for the plugin and its output. The code under test is the image's copy of `554101b`, so the OneDrive repo was never bind-mounted.
3. **`-p no:cacheprovider`** on every run, as in STORY-001, to keep `.pytest_cache` out of the tree.
4. **Connect timeouts are counted as one family.** `os error 10060` exists only on Windows (Linux reports `os error 110`). The recorder labels both `tcp connect error` anyway, because `_INFRA_MARKERS` checks that marker first. The STORY-008 rerun pattern needs to know this (see Recommendation).
5. **Two tests' errors are expected, not stalls.** `test_db.py::test_init_db_fails_fast_against_an_unreachable_endpoint` and `test_main.py::test_lifespan_fails_when_the_database_is_unreachable` point the driver at a dead endpoint on purpose (`_UNREACHABLE_URL`, `http://127.0.0.1:1`) and pass because the connect fails. Each run records their two `tcp connect error`s. The summarizer lists them separately and doesn't count them. A refused connect takes 2.03–2.05 s on Windows and 0.000–0.001 s on Linux. That's Windows' SYN retry, not a stall.
6. **host-3 discarded and rerun.** Windows entered S3 sleep at 22:21:56 and woke at 00:31:46 (System log: Kernel-Power 42 / 107, Kernel-General 1 "system time has changed ... from 01:21:58Z to 03:31:46Z"). One recorded `execute` "took" 7,791 s because `time.monotonic()` on Windows counts through sleep. The next DB test, `test_query_router.py::test_duplicate_prompt_blocked_before_openrouter_call`, failed less than a minute after waking with `libsql verdict: likely infrastructure -- execute took 15.05 s and ended in STREAM_EXPIRED`. That's the classic signature, but it can't be told apart from resume effects (the VM's clock jump, port forwarding re-established), so neither event is counted. The rerun, host-3r, was wrapped in a scratch helper that holds `SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)` for the length of the run. No power setting was changed. No sleep or wake event was logged during host-3r.
7. **The interleaving is broken for host-3r.** It started 1 h 45 min after in-net-3, instead of right after it.
8. **`en_core_web_sm` is not in the image** (`OSError: [E050]`). No `db` test failed because of it.

## Results

### Per run

| run | arm | passed | failed | errors | skipped | wall s | driver calls | slowest s | calls >= 10 s | dead-stream | connect-timeout | stall events | absorbed (test passed) | verdict: likely infra | verdict: no signal |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| in-net-1 | in-net | 1267 | 3 | 0 | 1 | 193.4 | 47813 | 0.159 | 0 | 0 | 0 | 0 | 0 | 0 | 3 |
| host-1 | host | 1270 | 0 | 0 | 1 | 229.3 | 47861 | 2.047 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| in-net-2 | in-net | 1267 | 3 | 0 | 1 | 184.7 | 47824 | 0.141 | 0 | 0 | 0 | 0 | 0 | 0 | 3 |
| host-2 | host | 1270 | 0 | 0 | 1 | 237.0 | 47888 | 2.031 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| in-net-3 | in-net | 1267 | 3 | 0 | 1 | 181.1 | 47824 | 0.150 | 0 | 0 | 0 | 0 | 0 | 0 | 3 |
| host-3r | host | 1269 | 0 | 1 | 1 | 249.3 | 47855 | 21.047 | 1 | 1 | 1 | 2 | 1 | 1 | 0 |
| *host-3 (discarded)* | *host* | *1269* | *1* | *0* | *1* | *8039.8* | *47860* | *7791.079* | *2* | *1* | *0* | *(2)* | *(1)* | *(1)* | *0* |

The host's "slowest" of about 2.04 s in host-1 and host-2 is the expected dead-endpoint connect (Deviation 5). Every other call stayed under 0.16 s in-network and under 2.1 s on the host.

### Per arm (valid runs only)

| arm | runs | driver calls | stall events | calls >= 10 s | dead-stream | connect-timeout | stall events per 1,000 calls |
|---|---|---|---|---|---|---|---|
| host | 3 | 143,604 | 2 | 1 | 1 | 1 | 0.0139 |
| in-net | 3 | 143,461 | 0 | 0 | 0 | 0 | 0.0000 |

A **stall event** is one recorded call that took 10 s or more, or that carried an infrastructure label (`STREAM_EXPIRED` family, `tcp connect error`, `os error 10060`). A call that is both counts once. Driver calls per run match within 0.2% across arms, so both arms ran the same work.

### Every stall event

- **host-3r**: `tests/test_audit_stats_prd013.py::test_prd013_pre_prd_row_reports_null_fields_and_false_flags`, `execute` **21.047 s**, client idle 0.00 s before, `tcp connect error`. The raw text in the log is `os error 10060`. Test result: **ERROR at setup**.
- **host-3r**: `tests/test_audit_stats_prd013.py::test_prd013_a_pipeline_row_reads_back_what_story_005_wrote`, the next test. `execute` 0.000 s, client idle 0.297 s, `STREAM_EXPIRED`. Test result: **passed**: `_reset_database()`'s one dead-stream retry absorbed it. Only the recorder catches a stall like this, since it never shows up as a failure.

The pair matches the brief's pattern: a 21 s connect stall on one client, then a dead stream on the reused client right after. The 21.05 s is the Windows TCP connect timeout, not the 15 s figure PRD Section 4 puts out of scope.

### Every verdict line

| run | verdict lines |
|---|---|
| in-net-1, in-net-2, in-net-3 | 3 each, all `no infrastructure signal` (11 / 2 / 2 calls, slowest 0.00–0.01 s) |
| host-1, host-2 | none (nothing failed) |
| host-3r | `libsql verdict: likely infrastructure -- execute took 21.05 s and ended in tcp connect error` |
| *host-3 (discarded)* | *`libsql verdict: likely infrastructure -- execute took 15.05 s and ended in STREAM_EXPIRED`* |

### Failures without an infrastructure signal (in-network only)

These three tests failed in every in-network run and passed in every host run:

- `tests/test_measure_usage_latency.py::test_a_short_run_reports_both_calls_and_cleans_up`
- `tests/test_measure_usage_latency.py::test_a_refused_admit_ends_the_run_without_a_report`
- `tests/test_measure_usage_latency.py::test_a_changed_statement_count_ends_the_run_without_a_report`

Cause: `SystemExit: Refusing to write to a non-local database: http://harness-libsql-dev:8080`. `scripts/measure_usage_latency.py` treats any hostname other than localhost as remote (its own local-only write guard). This comes from addressing the server by container name, not from a stall or a defect, and the verdict line says so (`no infrastructure signal`). An in-network recipe in STORY-008 has to handle it, for example by deselecting these three tests or passing `--allow-remote-database` in that context.

### Other observations (not traced)

- The in-network runs were faster: 181–193 s against 229–249 s on the host, about 20% less with the same number of calls. Port forwarding adds per-call latency even when it doesn't stall.
- No in-network call came near 10 s. The slowest of 143,461 took 0.159 s.

## Recommendation for STORY-008

Stalls appeared only behind Docker Desktop's port forwarding (2 events in 143,604 host calls, 0 in 143,461 in-network calls). So STORY-008 should take the **"confirmed" branch** from PRD Section 13: document an in-network `-m db` recipe, and possibly add `scripts/test-db-in-network.sh`, as the reliable local way to run storage tests. That means: create `harness-test-net`, connect `harness-libsql-dev`, `docker compose build harness-ai`, then `docker run --rm --network harness-test-net -e HARNESS_TEST_LIBSQL_URL=http://harness-libsql-dev:8080 -e DATABASE_URL=http://harness-libsql-dev:8080 -e TURSO_AUTH_TOKEN= harness-ai-harness-ai python -m pytest tests/ -m db`, with `docker compose run`'s missing `--network` and the three `test_measure_usage_latency.py` tests handled. The host-side `-m db` run stays supported, with the verdict line making its rare stalls a ten-second classification. Because the sample is small (about a 13.5% chance of zero in-network events by luck), STORY-008 should repeat a few in-network runs while validating the recipe and treat any in-network stall as reopening D5. A scoped rerun policy is not needed for now. If one is added later, its `--only-rerun` pattern must match `tcp connect error` and `STREAM_EXPIRED` (the labels the recorder prints on both platforms), not only `os error 10060`.

## State left behind

- `harness-test-net`: **removed** (`docker network disconnect` + `docker network rm`).
- `harness-libsql-dev`: still running, on `bridge` only, `0.0.0.0:8080->8080/tcp`, as at the start. Its data was reset by the `db` runs, as any `db` run does.
- No spike container remains (`--rm` on every run).
- **Left on purpose:** image `harness-ai-harness-ai:latest` (`55fe13ea01f1`, 1.86 GB), for STORY-008's recipe. Remove it with `docker image rm harness-ai-harness-ai:latest`.
- Scratch files (not committed): `%TEMP%\prd014-story006\` holds `spike_dump.py`, `summarize.py`, `run.sh`, `keepawake.ps1`, `pytest_procs.ps1`, `smoke_low.py`, `build.log`, `state-before.txt`, `summary.md`, the six runs' `.log` / `.jsonl` / `.summary.json` / `.pre.txt`, and `discarded/host-3.*`.

## Appendix A: commands

```bash
# setup
docker compose build harness-ai
docker network create harness-test-net
docker network connect harness-test-net harness-libsql-dev

# in-network run i (Git Bash, MSYS_NO_PATHCONV=1)
docker run --rm --network harness-test-net \
  -v "C:/Users/tobip/AppData/Local/Temp/prd014-story006:/spike" -e PYTHONPATH=/spike \
  -e SPIKE_OUT=/spike/in-net-$i -e SPIKE_ARM=in-net \
  -e HARNESS_TEST_LIBSQL_URL=http://harness-libsql-dev:8080 \
  -e DATABASE_URL=http://harness-libsql-dev:8080 -e TURSO_AUTH_TOKEN= \
  harness-ai-harness-ai python -m pytest tests/ -m db -q -rA -p no:cacheprovider -p spike_dump

# host run i (repo root)
env -u HARNESS_TEST_LIBSQL_URL SPIKE_OUT="C:\...\prd014-story006/host-$i" SPIKE_ARM=host \
  PYTHONPATH="C:\...\prd014-story006;." \
  C:/Users/tobip/.venvs/harness-ai/Scripts/python.exe -m pytest tests/ -m db -q -rA \
  -p no:cacheprovider -p spike_dump

# host-3r only: the same host command, wrapped in keepawake.ps1 (ES_CONTINUOUS | ES_SYSTEM_REQUIRED for the run)

# summary
python -I summarize.py > summary.md

# teardown
docker network disconnect harness-test-net harness-libsql-dev
docker network rm harness-test-net
```

## Appendix B: instrument sources (scratch, not committed)

### `spike_dump.py`

```python
"""PRD-014 STORY-006 scratch instrument. Not committed; loaded with `-p spike_dump`.

Reads the STORY-005 recorder's per-test records (`item.stash[_RECORDS]`) after
each test and writes every stall event -- a call >= _STALL_SECONDS or one that
ended in a driver error -- to $SPIKE_OUT.jsonl, with the test's outcome, so
stalls absorbed by `_reset_database()`'s retry in a passing test are counted
too. Totals go to $SPIKE_OUT.summary.json at session end. ASCII only.
"""
import json
import os
import time

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
        _conftest = next(
            p
            for p in config.pluginmanager.get_plugins()
            if hasattr(p, "_RECORDS") and hasattr(p, "_STALL_SECONDS")
        )
    return _conftest


def pytest_runtest_logreport(report):
    if report.failed:
        _outcome[report.nodeid] = "failed" if report.when == "call" else f"error ({report.when})"
    elif report.when == "call":
        _outcome.setdefault(report.nodeid, report.outcome)
    elif report.when == "setup" and report.skipped:
        _outcome.setdefault(report.nodeid, "skipped")


@pytest.hookimpl(wrapper=True)
def pytest_runtest_protocol(item, nextitem):
    result = yield
    conf = _recorder(item.config)
    records = item.stash.get(conf._RECORDS, [])
    if item.get_closest_marker("db") is not None:
        _totals["db_tests"] += 1
    _totals["calls"] += len(records)
    for call in records:
        _totals["slowest"] = max(_totals["slowest"], round(call.seconds, 3))
        stalled = call.seconds >= conf._STALL_SECONDS
        _totals["over_10s"] += stalled
        if call.error:
            _totals["errors"][call.error] = _totals["errors"].get(call.error, 0) + 1
        if stalled or call.error:
            _events.append(
                {
                    "nodeid": item.nodeid,
                    "outcome": _outcome.get(item.nodeid, "?"),
                    "op": call.op,
                    "seconds": round(call.seconds, 3),
                    "idle": None if call.idle is None else round(call.idle, 3),
                    "client": call.client,
                    "error": call.error,
                }
            )
    return result


def pytest_sessionfinish(session, exitstatus):
    with open(_OUT + ".jsonl", "w", encoding="ascii", errors="replace") as fh:
        for event in _events:
            fh.write(json.dumps(event) + "\n")
    with open(_OUT + ".summary.json", "w", encoding="ascii") as fh:
        json.dump(
            {
                "arm": _ARM,
                "exitstatus": int(exitstatus),
                "wall_seconds": round(time.monotonic() - _started, 1),
                **_totals,
            },
            fh,
            indent=2,
        )
```

### `summarize.py`

```python
"""PRD-014 STORY-006 scratch analysis. Reads <run>.summary.json / .jsonl / .log, prints Markdown.

A stall event is one recorded call that took >= 10 s or carried an
infrastructure label (a call that is both counts once). Connect timeouts are
counted as one family: the recorder labels Windows' `os error 10060` as
`tcp connect error` (first marker wins), and Linux' `os error 110` the same way.
ASCII only.
"""
import glob
import json
import os
import re
import sys

DIR = os.path.dirname(os.path.abspath(__file__))
_STALL = 10.0
DEAD = ("stream_expired", "stream has expired", "invalid baton", "stream not found", "baton")
CONNECT = ("tcp connect error", "os error 10060", "os error 110")
#: Tests that point the driver at a deliberately dead endpoint and pass because the
#: connect fails instantly (`_UNREACHABLE_URL`, `http://127.0.0.1:1`). Their labelled
#: calls are listed as expected, never counted as stall events (found in in-net-1).
EXPECTED = {
    "tests/test_db.py::test_init_db_fails_fast_against_an_unreachable_endpoint",
    "tests/test_main.py::test_lifespan_fails_when_the_database_is_unreachable",
}


def family(label):
    if label is None:
        return None
    low = label.lower()
    if any(m in low for m in CONNECT):
        return "connect-timeout"
    if any(m in low for m in DEAD):
        return "dead-stream"
    return "other:" + label


def counts(line):
    out = {}
    for n, word in re.findall(r"(\d+) (passed|failed|errors?|skipped|deselected|xfailed|xpassed)", line):
        out["errors" if word.startswith("error") else word] = int(n)
    return out


def load(run):
    summary = json.load(open(os.path.join(DIR, run + ".summary.json")))
    events = [json.loads(l) for l in open(os.path.join(DIR, run + ".jsonl")) if l.strip()]
    log = open(os.path.join(DIR, run + ".log"), encoding="utf-8", errors="replace").read()
    finals = [l for l in log.splitlines() if re.search(r"\d+ (passed|failed)", l) and " in " in l]
    verdicts = [l.strip() for l in log.splitlines() if "libsql verdict:" in l]
    return summary, events, finals[-1].strip("= ") if finals else "(no summary line)", verdicts


def main():
    runs = sorted(
        (os.path.basename(p)[: -len(".summary.json")] for p in glob.glob(os.path.join(DIR, "*.summary.json"))
         if not os.path.basename(p).startswith("smoke")),
        key=lambda r: (r.split("-")[-1].zfill(3), r),
    )
    arms = {}
    rows, all_events, all_verdicts, labels, expected = [], [], [], {}, []
    for run in runs:
        s, events, final, verdicts = load(run)
        expected += [dict(e, run=run) for e in events if e["nodeid"] in EXPECTED and e["seconds"] < _STALL]
        events = [e for e in events if not (e["nodeid"] in EXPECTED and e["seconds"] < _STALL)]
        c = counts(final)
        fams = [family(e["error"]) for e in events]
        stall_events = len(events)  # each jsonl line is one call: >= 10 s or labelled
        dead = sum(f == "dead-stream" for f in fams)
        conn = sum(f == "connect-timeout" for f in fams)
        absorbed = sum(e["outcome"] == "passed" for e in events)
        likely = sum("likely infrastructure" in v for v in verdicts)
        nosig = sum("no infrastructure signal" in v for v in verdicts)
        for label, n in s["errors"].items():
            labels[label] = labels.get(label, 0) + n
        rows.append(
            f"| {run} | {s['arm']} | {c.get('passed', 0)} | {c.get('failed', 0)} | {c.get('errors', 0)} | "
            f"{c.get('skipped', 0)} | {s['wall_seconds']} | {s['calls']} | {s['slowest']:.3f} | {s['over_10s']} | "
            f"{dead} | {conn} | {stall_events} | {absorbed} | {likely} | {nosig} |"
        )
        a = arms.setdefault(s["arm"], {"runs": 0, "calls": 0, "events": 0, "over_10s": 0, "dead": 0, "conn": 0})
        a["runs"] += 1
        a["calls"] += s["calls"]
        a["events"] += stall_events
        a["over_10s"] += s["over_10s"]
        a["dead"] += dead
        a["conn"] += conn
        all_events += [dict(e, run=run) for e in events]
        all_verdicts += [(run, v) for v in verdicts]

    print("## Runs\n")
    print("| run | arm | passed | failed | errors | skipped | wall s | driver calls | slowest s | calls >= 10 s "
          "| dead-stream | connect-timeout | stall events | absorbed (test passed) | verdict: likely infra "
          "| verdict: no signal |")
    print("|" + "---|" * 16)
    print("\n".join(rows))
    print("\n## Per arm\n")
    print("| arm | runs | driver calls | stall events | calls >= 10 s | dead-stream | connect-timeout "
          "| stall events per 1,000 calls |")
    print("|---|---|---|---|---|---|---|---|")
    for arm, a in sorted(arms.items()):
        rate = 1000 * a["events"] / a["calls"] if a["calls"] else 0
        print(f"| {arm} | {a['runs']} | {a['calls']} | {a['events']} | {a['over_10s']} | {a['dead']} | "
              f"{a['conn']} | {rate:.4f} |")
    print("\n## Stall events\n")
    if not all_events:
        print("None.")
    for e in all_events:
        print(f"- {e['run']}: `{e['nodeid']}` {e['op']} {e['seconds']} s (idle {e['idle']}), "
              f"error={e['error']}, test {e['outcome']}")
    print("\n## Expected errors (deliberately dead endpoint; not stall events)\n")
    if not expected:
        print("None.")
    for e in expected:
        print(f"- {e['run']}: `{e['nodeid']}` {e['op']} {e['seconds']} s, error={e['error']}, test {e['outcome']}")
    print("\n## Raw error labels (all recorded calls, expected ones included)\n")
    print(", ".join(f"{k}: {v}" for k, v in labels.items()) or "None.")
    print("\n## Verdict lines\n")
    if not all_verdicts:
        print("None.")
    for run, v in all_verdicts:
        print(f"- {run}: `{v}`")


if __name__ == "__main__":
    sys.exit(main())
```

### `keepawake.ps1` (host-3r only)

```powershell
# PRD-014 STORY-006 scratch: hold ES_SYSTEM_REQUIRED while a command runs; no power setting changes.
param([string]$Cmd)
Add-Type -Namespace W -Name P -MemberDefinition '[DllImport("kernel32.dll")] public static extern uint SetThreadExecutionState(uint f);'
[void][W.P]::SetThreadExecutionState([uint32]"0x80000001")   # ES_CONTINUOUS | ES_SYSTEM_REQUIRED
try { & 'C:\Program Files\Git\bin\bash.exe' -c $Cmd; $code = $LASTEXITCODE }
finally { [void][W.P]::SetThreadExecutionState([uint32]"0x80000000") }
exit $code
```
