---
story: STORY-003
prd: PRD-019
slug: image-healthcheck
title: Liveness HEALTHCHECK in the image (python urllib against /health)
type: NEW_CAPABILITY
complexity: small
epic_branch: epic/PRD-019-multi-instance-deployment
created: 2026-11-17
---

# Plan: Image `HEALTHCHECK`

## Summary

Add one exec-form `HEALTHCHECK` to the final stage of `Dockerfile`, probing `/health` (liveness) with `urllib.request`, plus a static, Docker-free test that parses the Dockerfile text. Nothing else changes: `docker-compose.yml`, `Caddyfile`, `CMD`, ports and services stay as they are.

- Story: `.agents/stories/PRD-019-multi-instance-deployment/STORY-003-image-healthcheck.md`
- PRD sections used: Section 7 F5, D3 (Section 15)
- Systems affected: `Dockerfile` (final stage), one new test module

## Design Decisions

- Exec form, no shell, so no quoting layer: `HEALTHCHECK --interval=10s --timeout=3s --start-period=60s CMD ["python", "-c", "<code>"]`. Exec form does not expand `$PORT`; that is fine because the Python code reads `os.environ['PORT']` itself. The story's AC1 wording `$PORT` is satisfied this way (note it in the report).
- The code string must contain no double quotes (it sits inside a JSON array). Use single quotes only, e.g.
  `import os,urllib.request as u;u.urlopen('http://127.0.0.1:%s/health'%os.environ['PORT'],timeout=2)`
  (avoids the f-string with escaped double quotes in PRD F5). A non-2xx or a connection error raises, so the exit code is 1 (unhealthy); a 200 exits 0.
- Verified in the Dockerfile: the runtime stage is `FROM python:3.11-slim` (`Dockerfile:42`), where `python` is on PATH (the file already runs `python -m spacy download` at `Dockerfile:63`). `PORT` is set by `ENV PORT=${PORT}` (`Dockerfile:70-71`), and Docker passes image ENV to the healthcheck process. Caddy listens on `{$PORT}` and proxies `/health` to the backend (`Caddyfile:1,5`), so the probe needs both processes up; that is why `--start-period=60s` matters.
- The probe never targets `/ready` (D3): a DB outage must not mark the container unhealthy.
- Placement: after `EXPOSE ${PORT}` (`Dockerfile:80`) and before the `CMD` comment block (`Dockerfile:82`), with a why-comment citing PRD-019 F5/D3 like `Dockerfile:76-77`. The test asserts on the instruction, not on comments, but keep the comment free of an extra line starting with `HEALTHCHECK`.
- No curl: it is purged at `Dockerfile:49`.

## Skills In Use

None (`skills: []`; `.agents/skills/` holds only `frontend-design`, not relevant).

## Patterns to Follow

| Category | Source | What to mirror |
|----------|--------|----------------|
| Dockerfile comments | `Dockerfile:76-80`, `Dockerfile:82-84` | Why-comment above the instruction, cites PRD ids |
| Static file test | `tests/test_caddyfile_routes.py:1-30` | Module docstring citing PRD/story, `pathlib.Path(__file__).resolve().parents[1] / "<file>"`, no Docker, runs under `-m "not db"` |
| Parse helper + assert messages | `tests/test_caddyfile_routes.py:68-79` | Private helper asserting structure, message names the file and the rule |

No existing test parses the Dockerfile (grep: only `tests/test_config.py:121,263` mention it in comments; `test_docker_smoke_probe.py` has no Dockerfile reference), so a new module is right, as the story allows.

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `Dockerfile` | UPDATE | Add the `HEALTHCHECK` in the final stage |
| `tests/test_dockerfile_healthcheck.py` | CREATE | Static assertions on the Dockerfile text |

## Tasks

### Task 1: Add the HEALTHCHECK

- **File**: `Dockerfile`
- **Action**: UPDATE (insert between `EXPOSE ${PORT}` at line 80 and the `CMD` comment at line 82)
- **Implement**: a comment (liveness not readiness, D3; `python` because curl is purged at line 49; start period covers spaCy load and `init_db()`), then the exec-form instruction from Design Decisions with flags exactly `--interval=10s --timeout=3s --start-period=60s`. Do not touch `CMD`, `ENV`, `EXPOSE`, `STOPSIGNAL`.
- **Mirror**: `Dockerfile:76-80`
- **Validate**: `git diff --stat Dockerfile` shows insertions only. Optional: `docker build -t harness-hc .` then `docker inspect --format "{{json .Config.Healthcheck}}" harness-hc` (slow, spaCy is ~425 MB; skip and report if it takes too long).

### Task 2: Static test

- **File**: `tests/test_dockerfile_healthcheck.py`
- **Action**: CREATE
- **Implement**: read `Dockerfile` as UTF-8; join backslash-continued lines; drop `#` comment lines; collect logical lines whose first token is `HEALTHCHECK`. Tests:
  1. exactly one `HEALTHCHECK` instruction, located after the last `FROM` (the `python:3.11-slim` stage);
  2. flags `--interval=10s`, `--timeout=3s`, `--start-period=60s` all present and no other `--` flag;
  3. exec form: take the text after `CMD`, `json.loads` it, assert `argv[:2] == ["python", "-c"]` and `len(argv) == 3`;
  4. the code string (argv[2]) contains `urllib.request`, `127.0.0.1`, `timeout=2`, `PORT`, and `/health` followed by a non-word character or end (so `/healthz` fails); it does not contain `/ready` or `curl`;
  5. the whole HEALTHCHECK instruction contains neither `curl` nor `/ready`;
  6. `compile(argv[2], "<healthcheck>", "exec")` succeeds (catches a quoting slip without Docker).
  Optional, cheap and strong: run the code string with `subprocess.run([sys.executable, "-c", code], env={..., "PORT": str(port)}, timeout=10)` against a `http.server` thread on a free port picked at runtime (bind port 0), asserting exit 0 on a 200 `/health` and non-zero when nothing listens; shut the server down in `finally`. Works on Windows and Linux. Drop it if flaky; tests 1-6 cover the AC.
  Module docstring cites PRD-019 STORY-003, F5, D3 and says "No Docker: runs under `-m "not db"`".
- **Mirror**: `tests/test_caddyfile_routes.py:1-30`
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_dockerfile_healthcheck.py`

## End-to-End Tests

- [ ] The optional subprocess test runs the exact probe code against a local stub (200 gives exit 0, no listener gives non-zero).
- [ ] Optional manual: `docker build` + `docker inspect` shows Healthcheck Test `["CMD","python","-c",...]` with 10s/3s/60s.
- [ ] Single instance unchanged: `git diff --stat` touches only `Dockerfile` and the new test (no `docker-compose.yml`, no `Caddyfile`).

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_dockerfile_healthcheck.py tests/test_caddyfile_routes.py
```

No `app/` file is touched, so `test_untouched_app.py` is not required; no test is renamed or removed, so the PII guard is not needed. Full suite: GitHub CI on push.

## Acceptance Criteria -> Tasks -> Tests

| AC | Task(s) | Test that proves it |
|----|---------|---------------------|
| AC1 HEALTHCHECK flags + urllib to 127.0.0.1:PORT/health, 2 s, no curl | 1, 2 | `test_dockerfile_healthcheck.py` flags, exec-form and code-content tests |
| AC2 probes `/health`, never `/ready` | 1, 2 | the no-`/ready` and `/health`-path tests |
| AC3 static test: one HEALTHCHECK, values, path, no curl/`/ready` | 2 | the single-instruction, flags and absence tests |
| AC4 compose/start command unchanged | 1 | diff review: only the `Dockerfile` insertion + new test (`git diff --stat`) |

Plus: all tasks completed, validation passes, follows existing patterns.
