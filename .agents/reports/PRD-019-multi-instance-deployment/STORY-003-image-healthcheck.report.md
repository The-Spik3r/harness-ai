---
story: STORY-003
prd: PRD-019
plan: .agents/plans/PRD-019-multi-instance-deployment/completed/STORY-003-image-healthcheck.plan.md
epic_branch: epic/PRD-019-multi-instance-deployment
commit: 95d9393
status: COMPLETE
completed: 2026-11-17
---

# Implementation Report - STORY-003: Liveness HEALTHCHECK in the image

**Commit**: `95d9393`

## Summary

Added one exec-form `HEALTHCHECK` (interval 10s, timeout 3s, start-period 60s) to the final stage of `Dockerfile`. It runs `python -c` with `urllib.request` against `http://127.0.0.1:$PORT/health` with a 2 s timeout. Added a Docker-free test module that parses the Dockerfile and runs the exact probe code against a stub server.

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| Tests | 14 passed (`test_dockerfile_healthcheck.py` 8, `test_caddyfile_routes.py` 6) |
| `docker build` | Skipped (slow spaCy layer); the Docker E2E in STORY-010 builds the image |
| Full suite | GitHub CI on push (user decision) |

## Files Changed

| File | Action |
|------|--------|
| `Dockerfile` | UPDATE (+7, insertions only) |
| `tests/test_dockerfile_healthcheck.py` | CREATE |

## Deviations from Plan

- AC1 says `$PORT`; exec form does not expand it, so the Python code reads `os.environ['PORT']` instead. Same effect, no shell quoting layer.
- `docker build` / `docker inspect` (optional manual step) not run.

## Acceptance Criteria

- [x] HEALTHCHECK flags + urllib to 127.0.0.1:PORT/health, 2 s, no curl (flags, exec-form, code tests)
- [x] Probes `/health`, never `/ready` (no-`/ready` tests; stub test: 200 on /health gives exit 0)
- [x] Static test asserts one HEALTHCHECK, values, path, no curl//ready
- [x] compose / start command unchanged (diff touches only `Dockerfile` and the new test)
