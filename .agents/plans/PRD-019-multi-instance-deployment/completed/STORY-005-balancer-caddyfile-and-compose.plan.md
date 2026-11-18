---
story: STORY-005
prd: PRD-019
slug: balancer-caddyfile-and-compose
title: Balancer Caddyfile, docker-compose.lb.yml and the static balancer test
type: NEW_CAPABILITY
complexity: medium
epic_branch: epic/PRD-019-multi-instance-deployment
created: 2026-11-17
---

# Plan: Balancer Caddyfile, docker-compose.lb.yml and the static balancer test

## Summary

Add three new files and touch nothing else: `deploy/lb/Caddyfile` (PRD F3 verbatim, with `handle_errors 502 503 504`), `docker-compose.lb.yml` (standalone, PRD F4) and `tests/test_lb_caddyfile.py` (text/regex over the Caddyfile, `yaml.safe_load` over the compose file, restated lists, no Docker, no storage). An optional `caddy validate` runs when a binary is found. `docker-compose.yml`, the in-container `Caddyfile` and `app/` stay untouched.

- Story: `.agents/stories/PRD-019-multi-instance-deployment/STORY-005-balancer-caddyfile-and-compose.md`
- PRD sections used: 6.1, F3, F4, Section 8 (Caddy row), 9.2 T1/T6, 9.3, D6, D7, D9, "Verified (STORY-004)"; STORY-004 report Findings (a)-(e)
- Systems affected: deploy config only (new `deploy/lb/`), one new test

## Design Decisions

- **Caddyfile = F3's directive set, nothing else.** `:{$PORT}`, then the literal line `reverse_proxy harness-a:{$PORT} harness-b:{$PORT} {` (no env default; STORY-007 substitutes it textually), `lb_policy cookie harness_lb {$LB_COOKIE_SECRET}`, `lb_try_duration 5s`, `health_uri /ready`, `health_interval 5s`, `health_timeout 3s`, `health_status 200`, `fail_duration 30s`, `transport http { dial_timeout 3s; response_header_timeout 150s }`, `stream_close_delay 5m`, then `handle_errors 502 503 504 { header Retry-After 10; @v1 path /v1/*; respond @v1 `...` 503; respond `{"detail":"Service unavailable"}` 503 }`. The `/v1` body: `{"error":{"message":"Service unavailable. Retry after the Retry-After interval.","type":"api_error","param":null,"code":"service_unavailable"}}`. Forbidden: `encode`, `log`, `unhealthy_status`, `retry_match`, any global options block (STORY-007 adds its own `admin`).
- **No explicit `Content-Type` header.** Verified: the STORY-004 spike used the same `respond` backtick bodies with no `header Content-Type`, and the 503s came back `Content-Type: application/json` (report Findings (b), lines 66-73; spike file `Caddyfile.56987` has no Content-Type). Adding it would deviate from the F3 directive set for nothing. The test pins the absence of a surprise by asserting the exact bodies only; STORY-007's live check asserts the header.
- **Comments**: short `#` lines citing D9, D6, D7, D2, T1, T6 (what each directive guards); the test strips comments before absence checks.
- **Compose project name (decided): `name: harness-ai-lb`** at the top of `docker-compose.lb.yml`. `docker-compose.yml` has no `name:`, so its project defaults to the directory name (`harness-ai`). Without a distinct name the two files would share one project: `up` of the lb file warns about orphan `harness-ai`, and both stacks would mount the same volume `harness-ai_harness-audit-buffer`, so a single-instance stack's journal would be adopted by the balancer stack and `down -v` of one would destroy the other's undrained rows. With `name:` the logical volume key is still `harness-audit-buffer` at the same path `/var/lib/harness/audit-buffer` (as the story requires), the real volume is `harness-ai-lb_harness-audit-buffer`, separate from the single-instance one. The test must not assert the project-prefixed volume name. Note `-p` on the CLI overrides `name:`; mention in a file comment.
- **Instances** (anchor `x-harness-instance`): `build: {context: ., args: {PORT: ${PORT:-8000}}}`, `env_file: [.env]`, `environment: [AUDIT_BUFFER_DIR=/var/lib/harness/audit-buffer, PORT=${PORT:-8000}]` (a stray `PORT` in `.env` cannot diverge from the build arg, mirrors the `environment` wins comment at `docker-compose.yml:15-17`), `volumes: [harness-audit-buffer:/var/lib/harness/audit-buffer]`, no `ports`, no `image` key (each service builds; the second build is a layer-cache hit). Services: `harness-a: {<<: *harness-instance}`, `harness-b: {<<: *harness-instance}`. No `healthcheck` in compose: the image's `HEALTHCHECK` (`Dockerfile:86`, STORY-003) is what `service_healthy` reads.
- **lb**: `image: caddy:2.11.7@sha256:36c24ad91a7ff7bc4c87fe22bfa8df3c4b18da0773d73fc12ee2c52b98c0bb7e`, `volumes: ["./deploy/lb/Caddyfile:/etc/caddy/Caddyfile:ro"]`, `environment: [PORT=${PORT:-8000}, "LB_COOKIE_SECRET=${LB_COOKIE_SECRET:?set LB_COOKIE_SECRET ...}"]`, `ports: ["${PORT:-8000}:${PORT:-8000}"]`, `depends_on: {harness-a: {condition: service_healthy}, harness-b: {condition: service_healthy}}`. Caddy stays with the image default `caddy run --config /etc/caddy/Caddyfile --adapter caddyfile`. The `:?` message names the variable and how to generate one (`openssl rand -hex 32`). Also add the `/data` and `/config` persistence? No: out of scope, Caddy needs neither with `:{$PORT}` HTTP-only.
- **Test restating**: lists are restated in the test, never derived from the file (pattern of `tests/test_caddyfile_routes.py:1-14, 27-45`). Settings defaults come from the model, not env: `Settings.model_fields["OPENROUTER_TIMEOUT_SECONDS"].default` (pattern `tests/test_config.py:624`; field `app/config.py:245` = 120.0, `READY_DB_TIMEOUT_SECONDS` at `app/config.py:443` = 2.0).
- **No storage trigger**: the `db` marker comes only from requesting a storage fixture or a nodeid in `_DB_NODEIDS` (`tests/conftest.py:117-123, 192-196`). The test uses no fixtures except builtin `tmp_path`/`monkeypatch` if needed, so it runs under `-m "not db"` like `tests/test_caddyfile_routes.py`. Importing `app.config` needs `os.environ.setdefault("OPENROUTER_API_KEY", ...)` / `ADMIN_TOKEN` first (same two lines as `tests/test_caddyfile_routes.py:19-20`).
- **PyYAML**: `requirements.txt:15` lists `PyYAML` (direct, unpinned); installed 6.0.3 (also required by presidio_analyzer, python-frontmatter). No dependency change.

---

## Skills In Use

None. `.agents/skills/` holds only `frontend-design` (not applicable); story `skills: []`.

---

## Patterns to Follow

| Category | Source | What to mirror |
|----------|--------|----------------|
| Test docstring + restated list | `tests/test_caddyfile_routes.py:1-45` | module docstring explaining why lists are restated; "No Docker and no storage"; PRD-number comments on each entry |
| Env setdefault before app import | `tests/test_caddyfile_routes.py:19-20` | needed for `from app.config import Settings` |
| Default read from the model | `tests/test_config.py:624` | `Settings.model_fields[name].default` |
| Compose comment style | `docker-compose.yml:8-17` | comments explaining volume and `environment` precedence; same journal path and volume key |
| Caddyfile style | `Caddyfile:1-12` | tab indentation, directive per line |
| Verified directive set | STORY-004 report Findings (e); PRD "Verified (STORY-004)" | the file is accepted by `caddy validate` as written |

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `deploy/lb/Caddyfile` | CREATE | the balancer config (F3) |
| `docker-compose.lb.yml` | CREATE | standalone two-instance stack (F4) |
| `tests/test_lb_caddyfile.py` | CREATE | static contract test |

No other file changes. `.dockerignore` needs nothing (`deploy/` is not ignored and is not copied into any image layer that matters). Board/story frontmatter edited by the planner only.

---

## Tasks

### Task 1: Create `deploy/lb/Caddyfile`
- **File**: `deploy/lb/Caddyfile`, **Action**: CREATE (tabs, LF, trailing newline)
- **Implement**: the F3 text from Design Decisions with short D-number comments. Keep `reverse_proxy harness-a:{$PORT} harness-b:{$PORT} {` as one literal line.
- **Mirror**: `Caddyfile:1-12`; PRD F3 block
- **Validate** (manual, local Caddy from the brief, `$env:PORT=8000; $env:LB_COOKIE_SECRET=x; $env:CADDY_ADMIN=localhost:0`-style): `caddy validate --config deploy/lb/Caddyfile --adapter caddyfile` returns 0 (DNS-lookup info lines for `harness-a/b` are expected); `caddy adapt` shows the 502/503/504 error routes and `response_header_timeout` 1.5e11.

### Task 2: Create `docker-compose.lb.yml`
- **File**: `docker-compose.lb.yml`, **Action**: CREATE
- **Implement**: per Design Decisions: `name: harness-ai-lb`; `x-harness-instance` anchor; `harness-a`, `harness-b` via `<<: *harness-instance`; `lb`; top-level `volumes: {harness-audit-buffer:}`. Header comment: standalone because an overlay cannot drop `ports` (D7); publishes the build-time `$PORT` (Section 6.1); `docker compose down -v` destroys undrained journal entries (copy the warning from `docker-compose.yml:8-12`); the `name:` rationale; secret generation.
- **Mirror**: `docker-compose.yml:1-25`
- **Validate** (manual, Docker available): `LB_COOKIE_SECRET=x docker compose -f docker-compose.lb.yml config` exits 0 and shows `harness-a`/`harness-b` identical, no `ports` on them, `lb` with the digest image, `ports` `8000:8000`, both `depends_on` `service_healthy`. Then without the secret (`env -u LB_COOKIE_SECRET` or a clean shell): `docker compose -f docker-compose.lb.yml config` exits non-zero with the `:?` message. Also run `docker compose -f docker-compose.yml config` and confirm unchanged. Check `PORT=9000` renders `9000:9000` and `PORT: "9000"` for the build arg. A `.env` file may be needed for `env_file`: `config` fails on a missing `.env`, so run it where `.env` exists (it is gitignored and present locally) or note the failure as an environment issue, not a defect.

### Task 3: Create `tests/test_lb_caddyfile.py`
- **File**: `tests/test_lb_caddyfile.py`, **Action**: CREATE
- **Implement**: helpers `_caddyfile()` (text with comments and blank lines stripped for directive checks; raw text for the bodies) and `_compose()` (`yaml.safe_load`; YAML merge keys resolve). Tests, each with a PRD citation comment:
  1. policy: `lb_policy cookie harness_lb {$LB_COOKIE_SECRET}` exactly (cookie name `harness_lb`, secret placeholder, never a literal secret); `lb_try_duration 5s`; site address `:{$PORT}`.
  2. upstream line is exactly `reverse_proxy harness-a:{$PORT} harness-b:{$PORT} {` (STORY-007 substitutes it textually) and appears once.
  3. active health: `health_uri /ready`, `health_interval 5s`, `health_timeout 3s`, `health_status 200`; `fail_duration 30s`.
  4. `dial_timeout 3s`; `response_header_timeout` parsed as seconds equals `int(Settings.model_fields["OPENROUTER_TIMEOUT_SECONDS"].default) + 30` (150); also `stream_close_delay 5m`.
  5. `Settings.model_fields["READY_DB_TIMEOUT_SECONDS"].default` (2.0) `<` parsed `health_timeout` seconds (3) (PRD 9.3).
  6. forbidden directives absent from the comment-stripped text, by regex on the first token of each line: `encode`, `log`, `unhealthy_status`, `retry_match`; also no `{$...:default}` form in the upstream line, and no global options block.
  7. `handle_errors` codes exactly `502 503 504`; `header Retry-After 10`; the two exact `respond` lines (backtick bodies, status 503) restated in the test as full strings; the `/v1` body also `json.loads`-checked for `code == "service_unavailable"`, `type == "api_error"`, `param is None`, message exactly `Service unavailable. Retry after the Retry-After interval.`; elsewhere body `{"detail":"Service unavailable"}`.
  8. compose: instance names = all services except `lb` = `{harness-a, harness-b}`; upstream hostnames parsed from the `reverse_proxy` line equal that set (as sets, and the count is 2); only `lb` has `ports`, equal to `["${PORT:-8000}:${PORT:-8000}"]`; instances have the same `build` (args `PORT: ${PORT:-8000}`), `env_file == [".env"]`, same `environment`, `AUDIT_BUFFER_DIR=/var/lib/harness/audit-buffer` present, same `volumes == ["harness-audit-buffer:/var/lib/harness/audit-buffer"]` (restated string), the named volume declared top-level; the volume key and path equal those in `docker-compose.yml` (read it with `yaml.safe_load`, assert the same `volumes` entry on `harness-ai`, so the two files cannot drift).
  9. lb: image string equals the pinned `caddy:2.11.7@sha256:36c24...bb7e` (restated, full digest); mounts `./deploy/lb/Caddyfile:/etc/caddy/Caddyfile:ro`; `environment` contains `LB_COOKIE_SECRET=${LB_COOKIE_SECRET:?` prefix (assert `:?` present, and that no default form `:-` is used for the secret) and `PORT`; `depends_on` has both instance names each with `condition: service_healthy`; `name == "harness-ai-lb"` (documents the project decision).
  10. optional `caddy validate`: `shutil.which(os.environ.get("CADDY_BIN") or "caddy")`; `pytest.skip` if none. Run `[caddy, "validate", "--config", <path>, "--adapter", "caddyfile"]` with env `PORT=8000`, `LB_COOKIE_SECRET=test-secret`, `CADDY_ADMIN=localhost:0`, `timeout=30`; assert rc 0. No shared helper (STORY-006 owns that and the require switch); no process left running (`validate` exits).
- **Mirror**: `tests/test_caddyfile_routes.py:1-45` (docstring, restated lists), `tests/test_config.py:624`
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_lb_caddyfile.py -m "not db"` then without `-m`, with `CADDY_BIN` set to the brief's caddy.exe to exercise test 10 (and once without it to see the skip).

---

## End-to-End Tests

- [ ] `caddy validate` on `deploy/lb/Caddyfile` (Task 1 and test 10) with the local caddy.exe.
- [ ] `docker compose -f docker-compose.lb.yml config` with and without `LB_COOKIE_SECRET` (Task 2; the without case must fail with the `:?` text). Manual, not pytest (story AC3, brief point 4).
- [ ] Live traffic, drain, kill and the `Content-Type` header on the 503s are STORY-007/008/010, not here.

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_lb_caddyfile.py tests/test_caddyfile_routes.py
```
`tests/test_caddyfile_routes.py` proves the in-container Caddyfile still routes the same (AC5). No `app/` file changes, so `tests/test_untouched_app.py` is not needed; no test renamed, so no `_DELIBERATELY_SUPERSEDED_TESTS` entry. Do not run the full suite (CI).

## Acceptance Criteria -> Tasks -> Tests

| AC | Task(s) | Test that proves it |
|----|---------|---------------------|
| AC1 Caddyfile directive set, validates | 1, 3 | `tests/test_lb_caddyfile.py` tests 1-6 and 10 (`caddy validate`, skipped without a binary; run locally with `CADDY_BIN`) |
| AC2 handle_errors 503 + Retry-After + bodies | 1, 3 | `tests/test_lb_caddyfile.py` test 7 (static); live behaviour already verified in STORY-004, re-proved by STORY-007 |
| AC3 compose valid, anchor, lb, `:?` | 2, 3 | `tests/test_lb_caddyfile.py` tests 8-9; manual `docker compose config` with and without the secret |
| AC4 static test, restated lists | 3 | `tests/test_lb_caddyfile.py` (whole module; no Docker, no storage) |
| AC5 single-instance unchanged | none (no edit) | `tests/test_caddyfile_routes.py`; `git status` shows `docker-compose.yml`/`Caddyfile` untouched |

## Risks

- `docker compose config` needs `.env` (`env_file`); fails if absent. Mitigation: run where it exists; the test never calls Docker.
- `name: harness-ai-lb` is a deliberate choice that changes the real volume name; if the orchestrator prefers a shared project, drop `name:` and the test-9 assertion (tradeoff stated above).
- `caddy validate` resolves env placeholders: set `PORT` and `LB_COOKIE_SECRET`, else the address is `:` and validate fails. DNS failures for `harness-a/b` are logged only (Findings (e)).
