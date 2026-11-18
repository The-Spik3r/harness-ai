---
story: STORY-009
prd: PRD-019
slug: rolling-restart-script
title: scripts/rolling_restart.sh — drain, wait, recreate, wait ready, one instance at a time
type: NEW_CAPABILITY
complexity: medium
epic_branch: epic/PRD-019-multi-instance-deployment
created: 2026-11-17
---

# Plan: Rolling restart script

## Summary

Add `scripts/rolling_restart.sh` (bash, LF, executable) that restarts `harness-a` then `harness-b` of `docker-compose.lb.yml`: refuse unless every instance's in-container `/ready` is 200, then per instance re-check the others, touch the drain file, wait for its own `/ready` 503, sleep `health_interval*2 + DRAIN_SECONDS`, recreate, wait for `/ready` 200. A static test plus a fake-`docker` shim test (no Docker) pins the contract and the control flow. The live run is STORY-010.

- Story: `.agents/stories/PRD-019-multi-instance-deployment/STORY-009-rolling-restart-script.md`
- PRD sections used: §5 story 4, §7 F6, D4
- Systems affected: `scripts/`, `tests/`. No `app/` change (`/ready` + drain already at `app/main.py:55-75`).

## Design Decisions

(Orchestrator requirements, binding.)

- **Never drains the last healthy instance.** One function `ready_status <svc>` echoes the HTTP code (`000` when `exec` fails or the container is down). Start of run: all services must be 200, else `exit 2` naming the first bad one. Before EACH drain: every OTHER service re-checked; any non-200 → stderr `refusing to drain <svc>: <other> is not ready (<code>)`, `exit 2`, no `touch`. Residual race (an instance dies between check and touch) is accepted; the balancer's passive health covers it. Say so in a script comment.
- **`health_interval` is parsed, not restated.** The script reads it from `deploy/lb/Caddyfile` (path resolved from the script dir, not cwd) with one `sed -n` matching `^[[:space:]]*health_interval[[:space:]]+([0-9]+)s[[:space:]]*$`; zero or >1 matches, or a non-integer → `exit 1` with message naming the file. The test proves the link with `tests/_balancer_stack.py:41-51` (`caddyfile_seconds` / `HEALTH_INTERVAL_S`): the shimmed `sleep` value must equal `2*HEALTH_INTERVAL_S + DRAIN_SECONDS`. The script must contain no numeric literal after `health_interval`.
- **Service list hardcoded**, one line: `SERVICES=(harness-a harness-b)`. Test: `yaml.safe_load(docker-compose.lb.yml)["services"]` entries that have a `build` key (the `*harness-instance` anchor; `lb` has `image`) equal the array, in order. No `docker compose config` at runtime (it prints `.env` secrets); the script never prints compose output beyond service names.
- **`DRAIN_SECONDS`** = env `DRAIN_SECONDS`, else `OPENROUTER_TIMEOUT_SECONDS + 10`, where `OPENROUTER_TIMEOUT_SECONDS` = env, else the literal default `120` on one line `: "${OPENROUTER_TIMEOUT_SECONDS:=120}"`. Test asserts that literal equals `Settings.model_fields["OPENROUTER_TIMEOUT_SECONDS"].default` (120.0). Accept `^[0-9]+(\.[0-9]+)?$` only; a fraction rounds up (`${v%%.*}` + 1) so bash integer math works; otherwise `exit 1`. Header comment notes: a value set only in `.env` is not in the operator's shell; export it to match the instances.
- **DRAIN_FILE** is touched with the container's own value: `exec -T <svc> sh -c 'touch "${DRAIN_FILE:-/tmp/harness-drain}"'` (single-quoted so the container expands). The default literal is asserted equal to `Settings.DRAIN_FILE` (`app/config.py:442`).
- **Readiness probe** (instances publish no port; no curl, `Dockerfile:49,86-87`): `exec -T <svc> python -c '<code>'` using `urllib.request` + `urllib.error.HTTPError` to turn a 503 into its code; URL from `os.environ['PORT']` (same trick as the image HEALTHCHECK `Dockerfile:87`), `timeout=3` (the Caddyfile `health_timeout`). Strip `\r` from the output (Windows).
- **Every wait is a deadline loop** (`$SECONDS`-based, poll `POLL_SECONDS` default 2): drain wait `DRAIN_WAIT_SECONDS` default 30; ready wait `READY_TIMEOUT_SECONDS` default 180 (boot loads spaCy, HEALTHCHECK start-period is 60 s, `Dockerfile:86`). Each timeout prints `timed out after Ns waiting for <svc> /ready to be <code>` (last code seen) and exits non-zero. The one plain `sleep` is the bounded drain window. All four are env-overridable so the shim test is fast.
- **Failure semantics.** Drain-wait timeout: best-effort `rm -f` of the drain file in that container (undo), `exit 3`. Replacement never ready: `exit 4`, naming it; the other instance was never touched and is still serving. Exit 2 = refusal, 1 = usage/config. No journal handling (PRD-018 D11).
- `-f FILE` (default `docker-compose.lb.yml` under the repo root); compose array `COMPOSE=(docker compose -f "$FILE")`. The script does not build: `up --force-recreate` reuses the existing image, so the operator runs `docker compose -f … build` first (STORY-011 documents it). `export MSYS_NO_PATHCONV=1` like `scripts/test-db-in-network.sh:40`. Unknown flag → usage, exit 1.

## Skills In Use

None apply (`.agents/skills/` holds only `frontend-design`).

## Patterns to Follow

| Category | Source | What to mirror |
|----------|--------|----------------|
| Script header/style | `scripts/test-db-in-network.sh:1-40` | `#!/usr/bin/env bash`, long header comment citing PRD/story, `set -euo pipefail`, `MSYS_NO_PATHCONV` |
| Exec bit | `git ls-files -s scripts/test-db-in-network.sh` = `100755` | `git add --chmod=+x`; `.gitattributes:2` already forces `*.sh` LF |
| Static test | `tests/test_lb_caddyfile.py:67-100` | `_ROOT`, `_COMPOSE_LB`, `_compose()` yaml loader; module docstring citing decisions |
| Derived timing | `tests/_balancer_stack.py:41-52` | import `HEALTH_INTERVAL_S`; never restate 5 |
| Settings default | `tests/test_lb_caddyfile.py:34-38` | set `OPENROUTER_API_KEY`/`ADMIN_TOKEN` via `os.environ.setdefault` before `from app.config import Settings` |
| Probe | `Dockerfile:87` | `os.environ['PORT']` + `urllib` one-liner |

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `scripts/rolling_restart.sh` | CREATE | The script (mode 100755, LF) |
| `tests/test_rolling_restart_script.py` | CREATE | Static contract + fake-docker control-flow cases |

No other file. Docs (README / deploy notes) belong to STORY-011; do not touch `docker-compose.lb.yml`.

## Tasks

### Task 1: Write the script
- **File**: `scripts/rolling_restart.sh` · **Action**: CREATE
- **Implement**: per Design Decisions. Layout: header comment (PRD-019 F6/D4, usage, tunables, exit codes, "never drains the last healthy instance", residual race, journal note); `set -euo pipefail`; constants (`SERVICES`, defaults); `die`/`log` (stderr); `parse_args`; `read_health_interval`; `compute_drain_seconds`; `ready_status`; `wait_ready_code <svc> <code> <timeout>`; `require_others_ready <svc>`; main loop `for svc in "${SERVICES[@]}"`: require_others_ready → touch → wait 503 (undo on timeout) → `sleep $((HI*2+DRAIN))` → `up -d --force-recreate --no-deps` → wait 200 → log "restarted". Call `sleep` unqualified (the shim intercepts it). `ready_status` must be safe under `set -e`: `code=$("${COMPOSE[@]}" exec -T … 2>/dev/null) || code=000`.
- **Mirror**: `scripts/test-db-in-network.sh:1-40`
- **Validate**: `bash -n scripts/rolling_restart.sh`; then `git add --chmod=+x scripts/rolling_restart.sh` (Windows `core.fileMode` is off, so `chmod` alone is not enough) and `git ls-files -s scripts/rolling_restart.sh` shows `100755`.

### Task 2: Static tests (no Docker; module docstring says so)
- **File**: `tests/test_rolling_restart_script.py` · **Action**: CREATE
- Cases: (a) bytes contain no `\r`; index mode `100755` via `git ls-files -s` (skip if git/index entry missing); (b) `set -euo pipefail` is a line; (c) `bash -n` (skip if `shutil.which("bash")` is None); (d) `SERVICES=` array equals compose services with `build` (and `lb` absent); (e) readiness uses `exec`, `python -c` and `urllib`, and the script text has no `curl`/`wget`; (f) the `:120` literal equals the Settings default and the `/tmp/harness-drain` literal equals `Settings.DRAIN_FILE`; (g) no digit literal follows `health_interval` in the script and it reads `deploy/lb/Caddyfile`; (h) `DRAIN_SECONDS` default formula text is `OPENROUTER_TIMEOUT_SECONDS` + 10.
- **Mirror**: `tests/test_lb_caddyfile.py:34-100`

### Task 3: Fake-docker shim cases (same file; skip when bash is absent)
- **Implement**: a fixture builds `tmp_path/bin/` with two bash shims and prepends it to `PATH` (works under Git Bash and Linux; pass `str(path)` through `Path.as_posix()`; run `bash scripts/rolling_restart.sh` with `subprocess.run(..., timeout=60)`):
  - `docker`: appends `"$*"` to `$FAKE/calls.log`; parses `compose [-f x] exec -T <svc> ...`: `python -c` → print the first line of `$FAKE/ready_<svc>` (delete that line when more than one remains, so the last line is sticky; line `down` → exit 1); `sh -c touch` → write `503` to `ready_<svc>`; `up -d --force-recreate --no-deps <svc>` → copy `$FAKE/after_up_<svc>` (default `200`) over `ready_<svc>`, which can hold several lines.
  - `sleep`: log the arg; sleep 0 when the arg ≥ 5 (the drain window), else real `sleep`.
  - Env for speed: `POLL_SECONDS=1 DRAIN_WAIT_SECONDS=3 READY_TIMEOUT_SECONDS=3 DRAIN_SECONDS=7`.
- **Cases**:
  1. *refuse at start* (AC1): `ready_harness-b`=503 → rc≠0, stderr names `harness-b`, calls.log has no `touch` and no `up`.
  2. *happy path* (AC2): calls ordered touch a → poll a → `sleep` → `up … harness-a` → poll a → touch b → … → `up … harness-b`; the logged sleep equals `2*HEALTH_INTERVAL_S + 7` (links the script to the Caddyfile); `--no-deps` and `--force-recreate` present; `-f` passes through.
  3. *never ready* (AC3): `after_up_harness-a`=`down` → rc≠0, stderr names `harness-a`, no call mentions `harness-b` after the `up`, so it was never touched.
  4. *last healthy instance* (orchestrator): `after_up_harness-a`=`200\n503` (ready once, then not) → the pre-drain check for `harness-b` sees `harness-a` 503 → rc=2, stderr names `harness-a`, no `touch … harness-b` in the log.
  5. *drain never takes effect*: shim ignores touch (flag file `ignore_touch`) → rc≠0 and an `rm -f` undo call is logged.
- **Validate**: below.

## End-to-End Tests

- [ ] The shim cases above are the control-flow check. The live run against real containers belongs to STORY-010; do not run Docker here.

## Validation

```bash
bash -n scripts/rolling_restart.sh
git ls-files -s scripts/rolling_restart.sh        # 100755
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_rolling_restart_script.py tests/test_lb_caddyfile.py
```

`tests/test_untouched_app.py` is not needed (no `app/` change). The new test imports `tests/_balancer_stack.py` (pulls `httpx` and `tests.conftest`), so it needs no DB itself.

## Acceptance Criteria → Tasks → Tests

| AC | Task(s) | Test that proves it |
|----|---------|---------------------|
| AC1 refuse when any instance not ready, names it | 1, 3 | `test_refuses_when_an_instance_is_not_ready` (shim case 1) |
| AC2 per-service order, sleep formula, DRAIN_SECONDS default, recreate flags | 1, 3 | `test_happy_path_order_and_drain_window` (case 2) + static (f)(g)(h) |
| AC3 never-ready replacement stops, other untouched | 1, 3 | `test_stops_when_replacement_never_ready` (case 3) |
| AC4 static: `bash -n`, service list, in-container python+urllib, `set -euo pipefail` | 2 | `test_bash_syntax`, `test_service_list_matches_compose`, `test_readiness_runs_in_container_with_python_urllib`, `test_strict_mode` |
| Orchestrator: never drains last healthy | 1, 3 | `test_rechecks_other_instances_before_each_drain` (case 4) |
| Orchestrator: LF + exec bit | 1, 2 | `test_lf_and_executable_bit` |

Plus: all tasks completed, validation passes, follows existing patterns.

## Risks

- `docker compose exec` of a stopped container exits non-zero: handled as `000`, which is "not ready".
- `OPENROUTER_TIMEOUT_SECONDS` resolution (orchestrator correction): operator shell env, else the value inside the first instance (`docker compose exec -T <svc> python -c ...`, because `.env` reaches containers via `env_file`), else 120 (app default, asserted by the static test); fractions round up; `DRAIN_SECONDS` env wins over all. The fake-docker shim answers that exec; `test_drain_window_uses_the_container_timeout` proves it. Implementation note: on Git Bash `/usr/bin` precedes a prepended PATH entry, so the shim `sleep` is injected as a function through `BASH_ENV`.
- Git Bash path conversion of `/tmp/...` in `exec` args: `MSYS_NO_PATHCONV=1`; the path stays inside single quotes passed to `sh -c`.
- Shim tests depend on bash being the Git Bash one on Windows (`shutil.which("bash")` may find WSL's `System32\bash.exe`): prefer `Git\bin\bash.exe` / skip when `bash -c 'echo ok'` fails.
