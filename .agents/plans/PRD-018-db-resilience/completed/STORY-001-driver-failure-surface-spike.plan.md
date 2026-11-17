---
story: STORY-001
prd: PRD-018
slug: driver-failure-surface-spike
title: Driver failure-surface spike — verbatim errors, failing call, and the three open questions
type: SPIKE
complexity: LOW
epic_branch: epic/PRD-018-db-resilience        # all stories commit here, no per-story branch
created: 2026-11-17
---

# Plan: Driver failure-surface spike (PRD-018 F1)

## Summary

This story changes no application code. It writes one throwaway capture script, `.agents/spikes/PRD-018-driver-failure-surface.py`, and one report, `.agents/spikes/PRD-018-driver-failure-surface.md`. The script runs in two roles. A **host orchestrator**, run with `.venv/Scripts/python` on Windows, drives Docker: it creates `harness-test-net` if it is missing, injects each fault into `harness-libsql-dev` (`docker pause`, `docker restart -t 0`), and synchronises with probes over stdin/stdout. **Probes** run in throwaway `docker run -i --rm --network harness-test-net` containers of the `harness-ai` image, which already has `libsql==0.1.11`. Each probe is a fresh process with a fresh client, so the "did it land?" read-back never uses the client that wrote (PRD-007 STORY-001 §2.2 rule). Every driver call is timed and labelled with the call that raised it (`connect` / `execute` / `fetchone` / `commit` / `rollback`). Every message goes through `app.db.database._redacted()` and an SQL guard before it is written. The faults are the five from PRD Section 4: refused, connect timeout, pause mid-statement, restart mid-transaction, idle expiry. The probes also answer the three open questions: does DML autocommit, does `commit()` with no transaction go to the network, and does an abandoned transaction block a fresh writer. The report closes with a ready-to-paste `(message, phase, expected FailureClass)` fixture table for STORY-002 and explicit verdicts on `DEAD_STREAM`@`commit` → `NOT_SENT` and on `TRANSACTION_TIMEOUT` → `NOT_SENT`. Every probe writes only to the scratch table `prd018_spike_rows`, which is dropped at the end. The orchestrator's `finally` and a standalone `host restore` command always leave the dev server running, unpaused, answering `SELECT 1`, and back on its starting networks.

**How a spike is "tested".** No unit tests. The checks are (a) **reproducibility**: each variant runs at least 3 times, and the report gives the repeat count and any variance in text, call or landed result; (b) the **AC checklist** below, item by item; (c) the **restore checks** (Task 7); (d) a **diff check**: nothing under `app/` or `tests/` changed.

## User Story

As a platform operator
I want the driver's real failure text and the call that raised it captured live
So that every retry rule in PRD-018 rests on measured facts and not on guesses about `libsql==0.1.11`

## Story Reference

- Story file: `.agents/stories/PRD-018-db-resilience/STORY-001-driver-failure-surface-spike.md`
- PRD: `.agents/PRDs/PRD-018-db-resilience/PRD.md`: Sections 4 (Characterization), 6.2 (taxonomy), 7/F1, 12 Phase 1, 14 Risk 3, 15 Assumptions

## Metadata

| Field | Value |
|-------|-------|
| Type | SPIKE |
| Complexity | LOW (code); the care is in the fault procedure and the restore |
| Systems Affected | `.agents/spikes/` only. Docker state of `harness-libsql-dev` changes temporarily and is restored |
| Story | STORY-001 |
| PRD | PRD-018 |
| Epic Branch | `epic/PRD-018-db-resilience` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| (none) | `.agents/skills/` holds only `frontend-design` (UI aesthetics). Not relevant to a storage spike. Story `skills: []` | — |

---

## Pre-flight findings (verified by the planner on 2026-11-17, so the implementer does not discover them late)

| Fact | Evidence | Consequence |
|---|---|---|
| **The image has the driver.** `harness-ai-harness-ai:latest` (`6765d09650f3`, built 2 days ago) has `libsql 0.1.11` on Python 3.11.18 | `docker run --rm harness-ai-harness-ai:latest python -c "import importlib.metadata as m; print(m.version('libsql'))"` → `0.1.11` | No rebuild needed for the driver |
| `libsql.connect` signature: `(database, timeout=5.0, isolation_level=..., ..., auth_token="", ...)`. `Connection` exposes `in_transaction`, `isolation_level`, `commit`, `rollback`, `close`, `sync`. The module exports `LEGACY_TRANSACTION_CONTROL` | `print(libsql.connect.__text_signature__)` in the image; same as PRD-007 STORY-006 report:81 | Record `in_transaction` before and after every step. It is direct evidence for Q1 and Q2. The `timeout=5.0` is the suspected `TRANSACTION_TIMEOUT` fuse (PRD-007 STORY-006 report:242). Q3 measures whether it governs the remote wait |
| **The image's `app/db/database.py` differs from the tree** (sha1 `95e7b1be…` in the image vs `c06b8c7a…` on disk; line endings or content) | `sha1sum` both sides | **Bind-mount the tree's `app/` read-only** so `_redacted()` is the current one. Verified: `--mount type=bind,source=G:\coding\harness-ai\app,target=/work/app,readonly` + `-e PYTHONPATH=/work` imports `/work/app/db/database.py` |
| **Do not mount the repo root.** It holds a real `.env`, and `app/config.py:171-172` reads `env_file=".env"` from the cwd | `ls -a` → `.env` | Mount only `app/` → `/work/app` and `.agents/spikes/` → `/work/spike`. Run with `-w /tmp`. Verified: `/work/.env` does not exist in the container. Host-side probes run with `cwd` set to the scratch out dir, with `TURSO_AUTH_TOKEN=` set explicitly |
| **`harness-test-net` does NOT exist.** `harness-libsql-dev` is on `bridge` only | `docker network ls` → `bridge, harness-ai_default, host, none`. `docker inspect … Networks` → `bridge` | The orchestrator creates the network and connects the server with the `scripts/test-db-in-network.sh:59-68` recipe. It records that it did so, and removes both at restore (the PRD-014 STORY-006 precedent: back to `bridge` only) |
| Docker server 29.7.2. **`docker restart -t 0` on a *paused* container works** and leaves it `running paused=false` | Tried on a throwaway `python:3.11-slim` container, not on the dev server | The "pause, then restart while a request is queued" variant (F3c/F3d) is feasible as written |
| `harness-ai-harness-ai-1` is running on :8000 with `DATABASE_URL=libsql://…turso.io` (remote), **not** the dev server | `docker inspect … Config.Env` | Pausing or restarting the dev server does not affect it. Leave it alone: never stop or restart it |
| Host venv: Python 3.12.10 with `libsql 0.1.11` | `.venv/Scripts/python -c "import importlib.metadata as m; print(m.version('libsql'))"` | Host comparison runs need no extra install |
| The Bash tool blocks a foreground `sleep` | Harness rule | Every wait (health, hold, idle) lives inside the Python orchestrator (`time.sleep`), never in a shell one-liner. Run each fault group as its own call (< 10 min), or with `run_in_background` |
| Story line refs: `database.py:405-418` is accurate (the expiry text is at :405-407, the baton text at :411, `_DEAD_STREAM` at :418). `:514-515` is accurate (`Connection refused` at :515) | Opened | Cite as is |

**Existing verbatim captures to reuse rather than re-derive** (cite them in the report's "Reused" section and the fixture table):

| Text | Source | Live? |
|---|---|---|
| `Hrana: `api error: `status=400 Bad Request, body={"message":"The stream has expired due to inactivity","code":"STREAM_EXPIRED"}``` | `app/db/database.py:405-407` | live (PRD-007 STORY-009, PRD-008 STORY-014) |
| `Hrana: `api error: `status=400 Bad Request, body=Received an invalid baton``` | `app/db/database.py:410-411` | live (PRD-008 STORY-024) |
| `Hrana: `http error: error sending request for url (http://127.0.0.1:1/v2/pipeline): client error (Connect): tcp connect error: Connection refused (os error 111)`` | `tests/test_db.py:4958-4962` | live (PRD-007 STORY-006) |
| `… tcp connect error: A connection attempt failed (os error 10060)`` | `tests/test_db_isolation_harness.py:224-229` | **partly synthetic**: the token was added for a redaction test. The live event is PRD-014 spike:84 |
| `os error 110` (Linux connect timeout) | PRD-014 spike:51 | **named only, no verbatim text in the repo.** F2 must capture it |
| `UNIQUE constraint failed: users.token_hash` / `no such table: users` / `duplicate column name: pii_detected_input` | `app/db/database.py:372-380` | live (`STATEMENT` rows for the fixture table) |
| `in_transaction= True` after an `INSERT … RETURNING` | PRD-013 STORY-009 report:49-54 | live: an implicit transaction opens on DML (prior evidence for Q1) |
| `no_commit -> LOST`, `close_only -> LOST` (fresh-client read-back) | PRD-007 STORY-001 report:68-91 | live, but against the 2025 server and a different abandonment shape. Q1 re-verifies |

---

## Patterns to Follow

### Timed wrapper that re-raises the original exception
```python
# SOURCE: tests/conftest.py:375-410 (_RecordedClient)
def timed(*args, **kwargs):
    started = time.monotonic()
    ...
    try:
        return attr(*args, **kwargs)
    except Exception as exc:
        error = _infra_error(str(exc))
        raise
    finally:
        self._last_used = time.monotonic()
        _record(_Call(name, self._last_used - started, self._number, idle, error))
```
The probe's `_step(call, fn)` helper follows this: it times the call, records `call` as the phase, captures `type(exc).__name__` and `_redacted(str(exc))`, and **does not wrap** the exception. A probe that has to continue after a failure catches it in the caller and records it.

### Redaction before anything is written
```python
# SOURCE: tests/conftest.py:357-370 (_infra_error) and app/db/database.py:491-505 (_redacted)
text = database._redacted(message)
```
The `_infra_error` docstring is the warning to honour: "a whole driver message can quote SQL (`near "...": syntax error`)". The probe adds an SQL guard on top of `_redacted()` (Task 1).

### In-network container recipe
```bash
# SOURCE: scripts/test-db-in-network.sh:59-68, 76-80
if ! docker network inspect "$NETWORK" >/dev/null 2>&1; then
  docker network create "$NETWORK" >/dev/null
fi
if ! docker inspect -f '{{range $k, $_ := .NetworkSettings.Networks}}{{println $k}}{{end}}' "$SERVER" \
    | grep -qxF "$NETWORK"; then
  docker network connect "$NETWORK" "$SERVER"
fi
...
exec docker run --rm --network "$NETWORK" \
  -e HARNESS_TEST_LIBSQL_URL="$url" -e DATABASE_URL="$url" -e TURSO_AUTH_TOKEN= \
  "$image" ...
```
Deviations from the script, each stated in the report's "Deviations": no `docker compose build` (the driver is already in the image, and the code comes from the bind mount); `-i` for the stdin/stdout handshake; bind mounts of `app/` and `.agents/spikes/` only; `-w /tmp`; the env `OPENROUTER_API_KEY=spike ADMIN_TOKEN=spike PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/work`. The image name comes from `docker compose config --images harness-ai` (`harness-ai-harness-ai`).

### Separate-process read-back
```
# SOURCE: .agents/reports/PRD-007-turso-migration/STORY-001-driver-decision.md:70, 328-356
"Four cases, each written by its own process and its own client, then read back by a
 third process constructing a fresh client. A same-client read-back was never used as evidence"
```

### Spike report shape
```
# SOURCE: .agents/spikes/PRD-014-docker-network-stalls.md:1-60
frontmatter (prd, story, decision, conclusion, date) → bold conclusion paragraph →
"Question and hypothesis" → "Setup" table → "Deviations from the PRD recipe" (numbered) →
"Results" → "Recommendation" → Appendix (the instrument, quoted)
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `.agents/spikes/PRD-018-driver-failure-surface.py` | CREATE | Throwaway capture script: host orchestrator plus in-container probes. Stdlib, `libsql` and `app.db.database._redacted` only |
| `.agents/spikes/PRD-018-driver-failure-surface.md` | CREATE | The report, with the STORY-002 fixture table |
| `app/`, `tests/`, `scripts/`, `docker-compose.yml`, PRD | **NO CHANGE** | Story Technical Notes: "No change under `app/` or `tests/`". Any PRD-018 Section 6.2 or Phase 1 change is an **orchestrator decision** (PRD Section 12 Phase 1), so the report recommends it and does not edit the PRD |

Raw capture output (JSONL) goes to the session scratchpad (`--out <scratchpad>/prd018-spike`). It is never written under the repo. The report quotes the redacted lines it needs in an appendix.

---

## Tasks

Execute in order. **Run nothing else against `harness-libsql-dev` from Task 3 to Task 7**: no pytest, no `scripts/measure_*`, no second spike (brief: two clients against the one server fail each other).

### Task 0: Record the starting state

- **Action**: run and keep the output for the report's Setup table.
  ```bash
  git -C G:/coding/harness-ai rev-parse --short HEAD; git -C G:/coding/harness-ai status --short
  docker version --format '{{.Server.Version}}'
  docker inspect -f '{{.State.Status}} paused={{.State.Paused}} image={{.Image}}' harness-libsql-dev
  docker inspect -f '{{range $k, $_ := .NetworkSettings.Networks}}{{println $k}}{{end}}' harness-libsql-dev
  docker network ls --format '{{.Name}}'
  docker compose config --images harness-ai
  docker images --format '{{.Repository}}:{{.Tag}} {{.ID}} {{.CreatedSince}}' harness-ai-harness-ai
  docker stats --no-stream --format '{{.Name}} {{.CPUPerc}}' harness-libsql-dev
  ```
  Also confirm that no pytest process is running (`tasklist //FI "IMAGENAME eq python.exe" //V` or PowerShell `Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Select CommandLine`). If one is, stop and wait.
- **Validate**: server `running paused=false`, CPU near 0%, networks = `bridge` (expected today).

### Task 1: Write the capture script

- **File**: `.agents/spikes/PRD-018-driver-failure-surface.py`
- **Action**: CREATE
- **Implement**: one file, argparse, two roles. Module docstring: purpose, PRD-018 F1 / STORY-001, "throwaway, not production code", and the exact commands from Task 3-6.

  **Constants** (module level): `SERVER = "harness-libsql-dev"`, `NETWORK = "harness-test-net"`, `IN_NET_URL = "http://harness-libsql-dev:8080"`, `HOST_URL = "http://127.0.0.1:8080"`, `REFUSED_URL = "http://127.0.0.1:1"`, `UNROUTABLE_URLS = ("http://10.255.255.1:8080", "http://192.0.2.1:8080")`, `TABLE = "prd018_spike_rows"`, `IDLE_SECONDS = 15.0` (> the ~10 s window measured at `database.py:66-67`), `IDLE_CONTROL_SECONDS = 8.0`, `PAUSE_HOLD_LONG = 60.0`, `PAUSE_HOLD_SHORT = 15.0`, `REPEATS = 3`, `PROBE_WALL_TIMEOUT = 300.0`.

  **Probe role** (`probe <name> [--url U] [--marker M] [--hold S]`), runs in the container or on the host:
  - Before any `app` import: `os.environ.setdefault` for `OPENROUTER_API_KEY`, `ADMIN_TOKEN`, `DATABASE_URL` (= the probe's URL), and `TURSO_AUTH_TOKEN=""` (mirror `tests/conftest.py:77-79`). Then `from app.db.database import _redacted`.
  - Talks to the **raw** `libsql` client (`libsql.connect(url, auth_token="")`), not `get_connection()`. The question is what the driver does, and `_Connection.__exit__` would add its own commit or rollback. Record that choice in the report's Setup.
  - `_step(call, fn)`: times `fn()`, notes `client.in_transaction` before and after (guarded by `getattr`, since the attribute may raise on a dead client), and emits one record. On exception it emits the record and **re-raises the same object** (the `_RecordedClient` rule). The SQL guard: if the redacted message contains `TABLE`, `INSERT`, `SELECT`, `CREATE` or `DROP` (case-insensitive), cut the SQL span to `<sql elided>` and set `sql_elided: true`. The report states how many records were elided (expected: 0).
  - Record shape, one JSON object per line on stdout, prefixed `REC `: `{"probe", "variant", "repeat", "where": "in-net"|"host", "step", "call", "elapsed_s", "outcome": "ok"|"raised", "exc_type", "message", "sql_elided", "in_tx_before", "in_tx_after", "marker", "t_wall"}`. `call` is one of `connect`, `execute`, `fetchone`, `fetchall`, `commit`, `rollback`, `close`, so the phase vocabulary is STORY-002's (`.agents/stories/PRD-018-db-resilience/STORY-002-classifier-and-phase-tracking.md` Technical Notes).
  - Handshake: the probe prints `READY <step>` and blocks on `sys.stdin.readline()` for `GO`. It prints `SENT <step>` immediately before a call the host must interrupt. It prints `DONE` at exit. Flush after every line.
  - Statements: always split `cur = client.execute(sql, params)` and `cur.fetchone()` / `fetchall()` into two `_step`s, so the report shows whether the request leaves on `execute` or on `fetch*`. The marker is a `uuid4().hex` passed in by the host.
  - Probes (each a function): `setup` (`CREATE TABLE IF NOT EXISTS prd018_spike_rows (id INTEGER PRIMARY KEY AUTOINCREMENT, marker TEXT NOT NULL, note TEXT)` + `commit`), `teardown` (`DROP TABLE IF EXISTS` + `commit`), `landed --marker M` (fresh client, `SELECT COUNT(*) … WHERE marker = ?`, emits `landed: true|false`), `select1` (health), and one function per variant in Tasks 3-5.

  **Host role** (`host preflight|run <group>|restore|all --out DIR`), run with `.venv/Scripts/python` from the repo root:
  - `preflight`: Task 0's checks in code. Writes `DIR/state.json` with `{network_existed, server_was_on_network, server_networks}`. Creates and connects the network per `scripts/test-db-in-network.sh:59-68`. Runs probe `select1` in-network and probe `setup`.
  - `_probe(name, where, **args)`: `subprocess.Popen` with list args (no shell), `stdin=PIPE, stdout=PIPE, text=True`. In-network:
    ```
    docker run -i --rm --network harness-test-net
      --mount type=bind,source=<repo>\app,target=/work/app,readonly
      --mount type=bind,source=<repo>\.agents\spikes,target=/work/spike,readonly
      -w /tmp -e PYTHONPATH=/work -e PYTHONDONTWRITEBYTECODE=1
      -e DATABASE_URL=<url> -e TURSO_AUTH_TOKEN= -e OPENROUTER_API_KEY=spike -e ADMIN_TOKEN=spike
      harness-ai-harness-ai python /work/spike/PRD-018-driver-failure-surface.py probe <name> ...
    ```
    Host: `[sys.executable, __file__, "probe", ...]` with `cwd=DIR` (no `.env`) and the same env. It reads lines, appends `REC` payloads to `DIR/captures.jsonl`, and yields `READY`/`SENT` to the variant driver, which writes `GO\n`. A wall-clock guard (`PROBE_WALL_TIMEOUT`) kills the probe (`docker kill` by a `--name prd018-probe-<uuid8>` given to each run) and records `outcome: "hung"`.
  - `_docker(*args)`: `subprocess.run(["docker", *args], check=True, capture_output=True, text=True)`. Each fault command and its wall time go into `captures.jsonl` as `{"host_action": ...}` records, so the report can quote the exact sequence.
  - `_wait_healthy(timeout=60)`: polls `urllib.request.urlopen(f"{HOST_URL}/health")` until 200, then runs probe `select1` in-network. It records the downtime.
  - `run <group>`: one of `refused`, `connect-timeout`, `pause`, `restart`, `idle`, `q1`, `q2`, `q3`, each looping `REPEATS` times, with a `try/finally: _restore_server()` around every group that touches Docker.
  - `_restore_server()`: `docker unpause harness-libsql-dev` (ignore "not paused"), `docker start harness-libsql-dev` (a no-op if running), `_wait_healthy()`.
  - `restore` (the final restore, and the manual escape hatch): `_restore_server()`, probe `teardown`, an in-network and a host `select1`, then a `sqlite_master` check that no `prd018_spike_%` table remains. Then, **only if `state.json` says the spike created them**, `docker network disconnect harness-test-net harness-libsql-dev` and `docker network rm harness-test-net`. Last, it prints `docker inspect -f '{{.State.Status}} paused={{.State.Paused}}'` and the network list.
- **Mirror**: `tests/conftest.py:375-410` (timed re-raise), `scripts/test-db-in-network.sh:59-80` (network and run), `.agents/spikes/PRD-014-docker-network-stalls.md` Appendix (a scratch instrument quoted in the report).
- **Validate**: `.venv/Scripts/python .agents/spikes/PRD-018-driver-failure-surface.py --help` and `... probe --help`. Then `host preflight --out <scratch>` followed directly by `host restore --out <scratch>`. Both succeed and leave the server `running paused=false`.

### Task 2: Smoke-run the harness with no fault

- **Action**: `host preflight`, then probe `landed` for a fresh marker (expect `false`), then a positive control: a probe that `INSERT`s + `commit()`s marker M, then `landed M` in a new process (expect `true`). Then `host restore`.
- **Validate**: `captures.jsonl` holds records with `call`, `elapsed_s` and `in_tx_*` filled in. This shows the read-back can see a committed row, which every "landed? false" later depends on.

### Task 3: Faults with no Docker interruption: F1 refused, F2 connect timeout

Each variant: in-network ×3, then host ×3 for comparison (the Windows text differs: expect `os error 10061` and about 2 s, per PRD-014 spike:52).

- **F1 `refused`** (`--url http://127.0.0.1:1`, inside the container this is the container's own loopback, so it is refused): steps `connect` → `execute("SELECT 1")` → `fetchone`. This records **which call raises**: `database.py` comments say the client is lazy, so `connect` probably succeeds and `execute` raises, which tells STORY-002 that a connect-phase failure can surface with `phase = execute` and must be recognised by text (`client error (Connect)` / `tcp connect error`). Then, on a **new never-used** client to the same URL, `commit()` alone, and `rollback()` alone (Q2 evidence: a raise means the call went to the network).
- **F2 `connect-timeout`**: the same steps against `UNROUTABLE_URLS[0]`, guarded by `PROBE_WALL_TIMEOUT`. Expect `os error 110` after about 130 s on Linux (default `tcp_syn_retries`), or a fast `No route to host` (113) / `Network is unreachable` (101) if Docker's NAT rejects it. **Record whichever happens.** If it is not a timeout, repeat with `UNROUTABLE_URLS[1]` (TEST-NET-1). If neither times out in-network, say so. The host run (expected `os error 10060` after about 21 s) and PRD-014's live 10060 are then the timeout evidence, labelled host-only. Note in the report that the elapsed time doubles as evidence for the PRD Section 15 assumption "no client-side timeout is configured, and whether the driver offers one is unverified".
- **Validate**: 6 in-network + 6 host records per fault (3 repeats × at least 2 steps), texts identical across repeats apart from elapsed time.

### Task 4: Faults that interrupt the server: F3 pause, F4 restart, F5 idle

Every Docker action goes through `_docker()`. Every group sits in `try/finally: _restore_server()`. Use a new marker per repeat. Run **probe `landed`** for each marker **after** `_wait_healthy()`, in a new container.

- **F3 `pause` mid-statement (read timeout)**. The procedure: the probe opens a client, `execute("SELECT 1")` + `fetchone` (warm) → `READY`. The host runs `docker pause harness-libsql-dev` → `GO`. The probe sends `SENT`, then `execute(INSERT marker)`. The request is now in the frozen server's socket buffer, which is "mid-statement" from the client's view.
  - **F3a** hold `PAUSE_HOLD_LONG` (60 s): does the driver give up by itself? If the call is still blocked at 60 s, record "no client-side read timeout within 60 s". Then `docker unpause`, record what the call returns or raises and its total elapsed time, then `commit()` if `execute` returned. `landed`.
  - **F3b** hold `PAUSE_HOLD_SHORT` (15 s, past the stream window): `docker unpause`. Does the queued request run, raise `STREAM_EXPIRED`, or something else? Then `commit()`. `landed`.
  - **F3c** hold 3 s, then `docker restart -t 0 harness-libsql-dev` **while paused** (verified to work on Docker 29.7.2). The process dies with the request queued, so expect a connection-reset or closed-connection text on `execute`. This is the `OUTCOME_UNKNOWN` example PRD Section 6.2 is missing. `_wait_healthy()`, `landed`.
  - **F3d** as F3c, but the in-flight call is `commit()` after a successful `INSERT` (pause → `GO` → `SENT` → `commit()` → restart). It gives the text of a reset on `commit`. `landed`.
  - If the paused call never returns even after unpause or restart, the wall guard records `hung`. Say so in the report, and do not invent text (story Technical Notes).
- **F4 `restart` mid-transaction (`invalid baton`)**. `docker restart -t 0 harness-libsql-dev` throughout (abrupt, crash-like; say so in Deviations). After each restart run `_wait_healthy()` before `GO`.
  - **F4a** `execute(INSERT m1)` (record `in_tx_after`, expect True) → `READY` → restart + healthy → `GO` → `execute(INSERT m2)`, expecting `invalid baton` on `execute`. Then `commit()` (record), then `rollback()` (record). `landed m1`, `landed m2`. This shows whether the earlier uncommitted work "went with the stream" (PRD 6.2 `DEAD_STREAM` row).
  - **F4b** `execute(INSERT m)` → restart → `commit()` directly. This is the text of `DEAD_STREAM`@`commit` by restart. `landed m`.
  - **F4c** `execute("SELECT 1")` + `fetchone` only (`in_tx_after` expected False) → restart → `commit()`. **Q2**: does a commit with no open transaction touch the dead stream? Then `execute("SELECT 1")` to record the baton text on `execute`.
- **F5 `idle` expiry (`STREAM_EXPIRED`)**, no Docker action (the probe sleeps):
  - **F5a** `SELECT 1` → sleep `IDLE_SECONDS` → `execute("SELECT 1")`: expect the `database.py:405-407` text. Confirm it matches the reused text byte for byte.
  - **F5b** `execute(INSERT m)` → sleep 15 s → `commit()`. **The key evidence for `DEAD_STREAM`@`commit`**: what raises, on which call, and does `landed m` say false?
  - **F5c** `execute(INSERT m)` → sleep 15 s → `execute("SELECT 1")` → `commit()`. `landed m`.
  - **F5d** (**Q2**) `SELECT 1` (`in_tx_after` False) → sleep 15 s → `commit()`. A raise means `commit()` with no transaction goes to the network. No raise means it is local or a no-op. Then `rollback()` the same way.
  - **F5-control** as F5a with `IDLE_CONTROL_SECONDS` (8 s): must succeed. This confirms that the window is still about 10 s on today's server and that the 15 s results are not an artefact.
- **Validate**: after every group the host prints `running paused=false` and `select1` is ok. Every variant has 3 repeats in `captures.jsonl`.

### Task 5: The three open questions

- **Q1: does DML autocommit on a remote endpoint?**
  - **Q1a** abandon by process exit: probe A `execute(INSERT m)` + `fetchone` if any, records `in_tx_after`, then `os._exit(0)` (no `commit`, no `close`). Then `landed m` immediately, and again after 15 s (past stream expiry, in case the server applies or discards on expiry).
  - **Q1b** abandon while alive: probe A `INSERT m`, no commit, `READY`, then blocks (holds the stream). The host runs `landed m` in a second container while A is alive, then lets A `os._exit(0)`, then `landed m` again after 15 s.
  - **Q1c** positive control: `INSERT` + `commit()` → `landed` true (already in Task 2; repeat here ×3).
  - Report: "durable before `commit()`: yes/no", with `in_tx_after` and the PRD-007 §2.2 / PRD-013 STORY-009 prior results side by side.
- **Q2: does `commit()` with no open transaction issue a network request, and what does it raise against a dead stream?** Evidence already gathered: F1 (never-used client against a refused URL), F4c (restart, no tx), F5d (expiry, no tx). Add **Q2-healthy**: on a live client after a `SELECT 1` (`in_tx` False), time 20 `commit()` calls against 20 `execute("SELECT 1")` round trips. This is weak evidence on its own, so it is labelled supporting only. Report: yes/no plus the verbatim text, or "no raise".
- **Q3: does a fresh writer wait, fail with `TRANSACTION_TIMEOUT`, or succeed after a stream was abandoned mid-transaction?** (Risk 3)
  - **Q3a** A alive: probe A `INSERT ma` (tx open), `READY`, holds 30 s. Probe B (new container) `execute(INSERT mb)` → `commit()`, timing each step. Record which call raised, the verbatim text (expect something with `TRANSACTION_TIMEOUT`), and the elapsed time (about 5 s would match `timeout=5.0`; about 10 s would match stream expiry). Then `landed mb`, which is what decides whether a `TRANSACTION_TIMEOUT` was "refused, not applied", and `landed ma` after A exits.
  - **Q3b** A abandoned by `os._exit(0)` right after its `INSERT`, B immediately after. Same records.
  - **Q3c** (optional, labelled extra): B connects with `libsql.connect(url, timeout=1.0)`. Does the wait follow it? This answers the PRD Section 15 timeout assumption.
  - Report min / median / max over the repeats.
- **Validate**: each answer cites record ids from `captures.jsonl` and in-network evidence (host runs are optional comparison).

### Task 6: Write the report

- **File**: `.agents/spikes/PRD-018-driver-failure-surface.md`
- **Action**: CREATE
- **Structure** (PRD-014 spike shape):
  1. Frontmatter: `prd: PRD-018`, `story: STORY-001`, `feature: F1`, `date: 2026-11-17`, `conclusion: <one line>`.
  2. **Conclusion** paragraph: the answers to Q1-Q3 in one sentence each, plus the two verdicts.
  3. **Setup** table: date and times, `HEAD`, image id, libsql and Python versions (container and host), Docker version, server image digest, paths (in-network by name, host through port forwarding), the bind mounts and env, raw client vs `get_connection()`, repeat count.
  4. **Procedure**: per fault and variant, the exact sequence (probe step → host action → probe step), with the Docker commands verbatim, and how the server was restored after each.
  5. **Deviations** (numbered): no image rebuild (bind mount instead); `-i` handshake; `docker restart -t 0`; any fault that could not be produced; anything that differs from the story text.
  6. **Captures** table, one row per (fault, variant, step that raised): `fault | variant | call that raised | verbatim message (via _redacted()) | elapsed s | in_tx before→after | landed? | where | repeats agreeing`. AC 1 requires all five faults. A fault that produced no failure (for example F3b succeeding after unpause) still gets a row saying so.
  7. **Q1 / Q2 / Q3** sections, each: question → evidence (record refs) → answer → what it changes in PRD Section 6.2 / Risk 3.
  8. **Reused captures**: the table from this plan's pre-flight section, each marked "re-observed today: identical / differs / not re-observed".
  9. **Fixture table for STORY-002** (AC 5), ready to paste into `tests/test_db_resilience_classify.py`:
     - A markdown table `| # | message | phase | expected FailureClass | source |`, and
     - the same rows as a Python literal block:
       ```python
       # PRD-018 STORY-001 (.agents/spikes/PRD-018-driver-failure-surface.md): verbatim, via _redacted()
       _FIXTURES = [
           # (message, phase, expected FailureClass)
           ("Hrana: `http error: ... Connection refused (os error 111)`", "execute", "NOT_SENT"),  # F1 in-net
       ]
       ```
     - Rows: every captured string at the phase it was raised (in-network first, host variants as separate rows), plus the reused live strings (STREAM_EXPIRED, invalid baton, refused 111, 10060), plus the three `STATEMENT` strings from `database.py:372-380`, plus one synthetic "unrecognised `Hrana:` text" → `OUTCOME_UNKNOWN`, labelled synthetic. Expected classes follow PRD 6.2 **as written** (dead stream on `execute`/`fetch*` → `DEAD_STREAM`; on `commit` → `OUTCOME_UNKNOWN`; reset or timeout after send → `OUTCOME_UNKNOWN`; connect-phase text → `NOT_SENT` whatever the phase). Rows a verdict below would change are marked "→ `NOT_SENT` if the orchestrator accepts V1/V2".
  10. **Verdicts** (AC 5, explicit yes/no each):
      - **V1: may `DEAD_STREAM`@`commit` move to `NOT_SENT`?** Yes only if, in every repeat of F4b, F5b and F5c, `commit()` raised a dead-stream marker **and** `landed` was false, **and** Q1 showed that DML is not durable before `commit()`. Otherwise no, with the counter-example. The report states that it is the orchestrator's decision to record in the PRD (Section 12 Phase 1).
      - **V2: is `TRANSACTION_TIMEOUT` `NOT_SENT`?** Yes only if, in every Q3 repeat, the writer's marker was not landed after the error. Also name the call it was raised on and the elapsed time against the 2 s budget (PRD D5). If `TRANSACTION_TIMEOUT` was never produced, say so: it then has no fixture row and stays `OUTCOME_UNKNOWN` by default.
  11. **Recommendation for STORY-002/003**: for example, "connect failures surface on `execute`, so classify by text", "no client-side read timeout: a pause blocks for N s", and the `os error 110` text.
  12. **Restore evidence**: the final `docker inspect`, network list, `select1` on both paths, no `prd018_spike_%` table.
  13. **Appendix A**: how to rerun (`host preflight` / `run <group>` / `restore`). **Appendix B**: the redacted JSONL lines the tables cite (no SQL, no token; the SQL-elided count).
- **Rule**: no invented text. A blank stays blank, with "not produced, observed: …".

### Task 7: Restore and verify (always; also after any failure mid-way)

- **Action**: `.venv/Scripts/python .agents/spikes/PRD-018-driver-failure-surface.py host restore --out <scratch>`
- **Validate** (each output pasted into the report's Restore evidence):
  - `docker inspect -f '{{.State.Status}} paused={{.State.Paused}}' harness-libsql-dev` → `running paused=false`
  - `docker inspect -f '{{range $k, $_ := .NetworkSettings.Networks}}{{println $k}}{{end}}' harness-libsql-dev` → the Task 0 networks (`bridge`)
  - `docker network ls` → no `harness-test-net` if the spike created it
  - `SELECT 1` ok from the host (`127.0.0.1:8080`). The in-network check runs before the network is removed
  - `SELECT name FROM sqlite_master WHERE name LIKE 'prd018_spike_%'` → no rows
  - `harness-ai-harness-ai-1` still `Up` (untouched)
  - Optional smoke, **one pytest process only**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_conftest_fixtures.py -m db -q -p no:cacheprovider` passes (shows the dev server serves the suite again)

### Task 8: Final diff check

- **Action**: `git status --short` and `git diff --stat`
- **Validate**: the only new or changed files are `.agents/spikes/PRD-018-driver-failure-surface.{py,md}`, plus the planner's story, index and plan edits and implement's own report and archived plan. Nothing under `app/`, `tests/`, `scripts/` or `docker-compose.yml`. `.venv/Scripts/python -c "from app.main import app; print('OK')"` prints OK.

---

## End-to-End Tests

For a spike, "tests" means the captures can be reproduced and every AC is met. No pytest file is added.

- [ ] `host preflight` → `host restore` round trip leaves the server `running paused=false` on `bridge` (Task 1)
- [ ] Positive control: committed marker `landed: true`; never-written marker `false` (Task 2)
- [ ] Every variant has ≥ 3 repeats; the report lists any variance in text, call or landed result
- [ ] Every Captures row cites in-network evidence (host rows are comparison only)
- [ ] `sql_elided` count stated; no SQL and no token anywhere in the report (`grep -iE "insert|select|create|authtoken=[^*]" .agents/spikes/PRD-018-driver-failure-surface.md` shows only prose and `_FIXTURES` comments, no driver text with SQL)
- [ ] Task 7 restore checks all pass

## Validation

```bash
.venv/Scripts/python .agents/spikes/PRD-018-driver-failure-surface.py --help
.venv/Scripts/python -c "from app.main import app; print('OK')"
docker inspect -f '{{.State.Status}} paused={{.State.Paused}}' harness-libsql-dev   # running paused=false
git status --short   # only .agents/ files
```

---

## Risks

| Risk | Mitigation |
|---|---|
| A fault leaves the shared dev server paused or stopped | `try/finally: _restore_server()` per group, a standalone `host restore`, and Task 7 is mandatory even after a crash |
| Docker's NAT answers the unroutable address fast instead of timing out (no `os error 110`) | Two addresses, then fall back to the host 10060 and PRD-014's live capture. Labelled host-only. Do not invent the Linux text |
| A paused request never returns after unpause | Wall guard (`PROBE_WALL_TIMEOUT`) → `hung`. F3c's restart-while-paused gives the reset text anyway |
| The bind mount's view of `app/` drifts during the run | The branch is clean and nothing edits `app/`. Record `HEAD` in Setup |
| The `.env` secret reaches a probe | Only `app/` and `.agents/spikes/` are mounted; `-w /tmp`; host probes run with `cwd` = the scratch dir and `TURSO_AUTH_TOKEN=` |
| Driver text quotes SQL | `_redacted()` + the SQL guard + the elided count. Messages for infrastructure faults are not expected to carry SQL |
| `docker restart -t 0` differs from the graceful restart STORY-024 used for the baton text | F4a compares today's text with `database.py:411` byte for byte. If it differs, run one extra `docker restart` (default `-t 10`) repeat and report both |
| A long run exceeds the 10-minute tool timeout | One `host run <group>` per call; F2 and F3a are the long ones (about 2 min and about 1 min × 3) |

## Open questions for the orchestrator

- V1/V2 are **recommendations**. Recording `DEAD_STREAM`@`commit` → `NOT_SENT` (and the `TRANSACTION_TIMEOUT` class) in PRD Section 6.2 / Phase 1 is the orchestrator's decision. The implementer does not edit the PRD.
- Should `harness-test-net` stay in place afterwards (as `scripts/test-db-in-network.sh` leaves it) or be removed (the PRD-014 STORY-006 precedent)? Default in this plan: restore to the Task 0 state, which means removing it.

---

## Acceptance Criteria

(Copied from story STORY-001, with how each is covered)

- [ ] Given `harness-libsql-dev` reached from inside `harness-test-net`, when each fault is injected (connection refused, connect timeout, `docker pause` mid-statement, `docker restart` mid-transaction, idle expiry), then the report records for each one the fault, the call that raised, the verbatim message through `database._redacted()`, and whether the effect landed. → Tasks 3-4 (F1-F5), Captures table (Task 6 §6)
- [ ] Given a remote endpoint, when an `INSERT` runs and the client is abandoned without `commit()`, then the report says whether the row is durable (Q1). → Task 5 Q1a/Q1b/Q1c, report §7
- [ ] Given no open transaction, when `commit()` is called, then the report says whether it issues a network request and what it raises against a dead stream (Q2). → F1 never-used client, F4c, F5d, Q2-healthy; report §7
- [ ] Given a stream abandoned mid-transaction, when a fresh client writes to the same table, then the report says whether that write waits, fails with `TRANSACTION_TIMEOUT` (verbatim), or succeeds, and how long it takes (Q3, Risk 3). → Task 5 Q3a/Q3b (Q3c optional), report §7
- [ ] Given the captures, the report contains a ready-to-paste fixture table `(message, phase, expected FailureClass)` for STORY-002 and states explicitly whether `DEAD_STREAM`@`commit` may move to `NOT_SENT` and whether `TRANSACTION_TIMEOUT` is `NOT_SENT`. → report §9 (table + `_FIXTURES` block) and §10 (V1, V2)
- [ ] All tasks completed; dev server left running, unpaused, `SELECT 1` ok (Task 7)
- [ ] No change under `app/` or `tests/` (Task 8); `from app.main import app` OK
- [ ] Follows existing patterns (`_RecordedClient` re-raise, `_redacted()`, in-network recipe, PRD-014 report shape)
