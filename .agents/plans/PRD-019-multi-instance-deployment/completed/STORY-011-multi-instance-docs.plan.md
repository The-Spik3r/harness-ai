---
story: STORY-011
prd: PRD-019
slug: multi-instance-docs
title: Docs — multi-instance deployment, settings, roadmap tick; PRD close-out
type: ENHANCEMENT
complexity: small
epic_branch: epic/PRD-019-multi-instance-deployment
created: 2026-11-17
---

# Plan: Multi-instance docs

## Summary

Docs only, no app code. Rewrite `docs/deployment.md` "Multiple instances" (lines 33-44) from what shipped (not PRD draft values), add settings to `docs/configuration.md` and `.env.example`, tick the roadmap affinity item, link the section from README, point `docs/testing.md` at the opt-in Docker E2E, then close the PRD (`status: done`, board 100%).

- Story: `.agents/stories/PRD-019-multi-instance-deployment/STORY-011-multi-instance-docs.md`
- PRD sections used: §4 Documentation, §6.1 (D7), §6.2 (D1), §6.3, F6, F7, §9.3, §15 Verified/Not verified
- Systems affected: docs, `.env.example`, PRD frontmatter, board. No design points (not critical).

## Design Decisions

none beyond the tasks. Facts the docs must state (all read from shipped files):

- Topology: `lb` (caddy `2.11.7`, pinned by digest, `docker-compose.lb.yml`) -> `harness-a`/`harness-b` (in-container Caddy -> backend :8001) -> shared Turso. Start: `LB_COOKIE_SECRET=$(openssl rand -hex 32) docker compose -f docker-compose.lb.yml up -d`. Compose project `harness-ai-lb` with its own `harness-audit-buffer` volume (so `down -v` of one stack cannot destroy the other's journal; check `journal.entries == 0` first).
- Affinity: cookie `harness_lb`, `Path=/; HttpOnly; SameSite=Lax`, **no `Secure`, a session cookie** (PRD §15 Verified, STORY-004 report), value 64 hex signed with `LB_COOKIE_SECRET`. Failover: another instance answers (0.25 s for a dead one, one health interval for an unready one) and the cookie is re-set. The user sees the sign-in gate once (per-instance disk state, `_token` lost), transcripts reload from the DB, the in-flight answer is lost.
- Probes: `/health` liveness (Docker HEALTHCHECK `Dockerfile:86`, interval 10 s, ignores the drain flag); `/ready` readiness (`app/main.py:55-75`: drain file -> 503 `draining`; else `check_ready()`; 200 `{"status":"ready","breaker":"closed"}`; 503 `breaker_open` with `Retry-After`; never moves PRD-018's breaker); `/storage/status` (`stats:read`, not for the balancer). Balancer: `health_uri /ready`, interval 5s, timeout 3s, `fail_duration 30s` (`deploy/lb/Caddyfile`).
- Timeout invariant: every hop > `OPENROUTER_TIMEOUT_SECONDS` + 30 s. Numbers: 120 + 30 = 150 s = `response_header_timeout 150s`; `dial_timeout 3s`, `lb_try_duration 5s`. For a third-party balancer: 150 s read/idle timeout, no response buffering (SSE, websocket), health timeout above `READY_DB_TIMEOUT_SECONDS` (default 2.0).
- Errors: no healthy upstream -> `503` after ~5 s with `Retry-After: 10` (`/v1/*` gets an OpenAI-shaped body, else `{"detail":"Service unavailable"}`); an instance's own 503 passes through untouched. A request that reached an instance is never replayed (no `retry_match`); dial failures retry. No `encode`, no access log.
- Port constraint D7: image built with `PORT`; over plain HTTP the lb must publish that same `$PORT` (compose does); behind TLS on 443 it disappears. Cookie lacks `Secure`: say so, terminate TLS in front.
- Rolling restart: `docker compose -f docker-compose.lb.yml build` FIRST (script never builds; `--force-recreate` reuses the image), then `scripts/rolling_restart.sh [-f FILE]... [-p PROJECT]`. Window = `2 * health_interval` (parsed from `deploy/lb/Caddyfile`, so 10 s) + `DRAIN_SECONDS` (default `OPENROUTER_TIMEOUT_SECONDS`+10; the timeout is read from shell env, else the first instance container (`.env` reaches containers via `env_file`, not your shell), else 120). Tunables: `POLL_SECONDS` 2, `DRAIN_WAIT_SECONDS` 30, `READY_TIMEOUT_SECONDS` 180. Exit codes: 0 done, 1 config, 2 refused (an instance not ready, also before each drain), 3 drain never took effect (undone), 4 replacement never ready (the other still serves). A non-empty journal does not block (adopted, PRD-018 D11).
- Unsupported: `REFLEX_REDIS_URL` set (silently switches Reflex to Redis, untested), `--scale` (Caddyfile names `harness-a`/`harness-b`), IP-hash or round-robin affinity (only the cookie is tested). `docker-compose.yml` single stack unchanged.
- Security: `docker compose config` prints `.env` secrets (do not paste it); `LB_COOKIE_SECRET` is read only by the lb, never by `app/`.
- Not verified (PRD §15, say so): websocket pass-through and `stream_close_delay` across a config reload in isolation; STORY-010's Docker E2E covers stickiness, kill and rolling restart.
- Proof pointers: `tests/test_two_instance_balancer.py` (real Caddy); opt-in `tests/e2e/test_lb_docker.py`. The smoke-test docstring pointer: `tests/test_two_instance_smoke.py` has none (grep found no "balancer"), so omit it.

## Skills In Use

None (`.agents/skills/` holds only `frontend-design`, not applicable).

## Patterns to Follow

| Category | Source | What to mirror |
|---|---|---|
| Prose/tables | `docs/deployment.md:46-60` | bold lead-in, class tables, honest "not covered" text |
| Settings rows | `docs/configuration.md:36` (`AUDIT_BUFFER_MAX_BYTES`) | `\| name \| Required \| default \| description incl. "startup error" \|` |
| .env.example | tail of file (`AUDIT_BUFFER_*`) | a comment line directly above `VAR=value` (`tests/test_config.py:64` regexes `^#.+\nVAR=`) |
| Validation text | `app/config.py:612-633` | `DRAIN_FILE` non-empty absolute path; `READY_DB_TIMEOUT_SECONDS` > 0 and <= 10, under the balancer `health_timeout` (3 s) |

## Files to Change

| File | Action | Purpose |
|---|---|---|
| `docs/deployment.md` | UPDATE | replace lines 33-44; keep the smoke-test paragraph; sub-headings Topology, Affinity and failover, Probes, Timeouts, Rolling restart, TLS and port, Unsupported |
| `docs/configuration.md` | UPDATE | rows after line 36: `DRAIN_FILE`, `READY_DB_TIMEOUT_SECONDS`, `LB_COOKIE_SECRET` (compose-only, `:?`), `REFLEX_REDIS_URL` ("leave unset") |
| `.env.example` | UPDATE | four commented entries appended; `REFLEX_REDIS_URL=` and `LB_COOKIE_SECRET=` empty with a comment (empty makes compose refuse, intended) |
| `docs/roadmap.md` | UPDATE | tick the affinity item (grep `Websocket session affinity`), link `deployment.md#multiple-instances`; fix the intro sentence above it ("cannot yet run behind a balancer") |
| `README.md` | UPDATE | line 360 table row, 368 Shipped (add multi-instance deployment), 370 Next up (drop affinity); link `docs/deployment.md#multiple-instances` |
| `docs/testing.md` | UPDATE | after line 35: the opt-in Docker E2E command |
| `.agents/PRDs/PRD-019-multi-instance-deployment/PRD.md` | UPDATE | frontmatter `status: done`, `updated: 2026-11-17` |

## Tasks

1. **deployment.md**: rewrite per Design Decisions with an ASCII topology diagram (PRD §6.1 with real service names), probe table, timeout table (hop / value / rule), rolling restart steps, exit-code table. Validate: `grep -n unblocked docs/deployment.md` empty; anchor `#multiple-instances` still exists.
2. **configuration.md + .env.example**: rows and entries above. Validate: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_config.py`.
3. **roadmap.md, README.md, testing.md**. E2E text: `HARNESS_E2E_DOCKER=1 python -m pytest tests/e2e/test_lb_docker.py -m e2e --run-e2e -v -s` (`tests/e2e/test_lb_docker.py:32`); needs Docker, builds the image, about 6 min cached / 13 min cold (350 s / 762 s measured), project `harness-lb-e2e` via `tests/e2e/docker/compose.lb-e2e.yml`, not in CI.
4. **AC4 check.** No docs-consistency test exists (grep of `tests/` for `configuration.md` / `deployment.md` finds none), so run in Git Bash and paste the output in the report:
   `for v in DRAIN_FILE READY_DB_TIMEOUT_SECONDS OPENROUTER_TIMEOUT_SECONDS DRAIN_SECONDS POLL_SECONDS DRAIN_WAIT_SECONDS READY_TIMEOUT_SECONDS LB_COOKIE_SECRET PORT; do printf '%s: ' $v; grep -lw "$v" app/config.py docker-compose.lb.yml scripts/rolling_restart.sh | tr '\n' ' '; echo; done`
   Every setting named in the new docs must hit a file, except `REFLEX_REDIS_URL` (Reflex's own variable, documented as "leave unset", cite PRD §6.2). Also confirm each file path and relative link named in the docs exists.
5. **PRD close-out**: set PRD frontmatter `status: done`; set the story `status: done` per implement's report step; run `PYTHONIOENCODING=utf-8 .venv/Scripts/python .agents/scripts/gen_index.py PRD-019` (`errors: none`). The board reads `11/11 stories done — 100%` and `Status: done` (the generator derives them from the stories, `gen_index.py:70-77`, and does not read PRD frontmatter, so the PRD edit is by hand).

## End-to-End Tests

- [ ] Every relative link added to README and docs resolves to an existing file/anchor.
- [ ] Commands in the docs match the shipped compose file name, script path and flags.

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_config.py
```
No `app/` file is touched, so `test_untouched_app.py` is not needed. Full suite: GitHub CI on push.

## Acceptance Criteria -> Tasks -> Tests

| AC | Task(s) | Proof |
|---|---|---|
| AC1 deployment.md rewritten | 1 | no "unblocked" grep; reviewer checks each listed element |
| AC2 settings documented | 2 | `tests/test_config.py` green + task 4 grep |
| AC3 roadmap ticked, README link | 3 | `grep -n "\[x\].*Websocket session affinity" docs/roadmap.md`; README grep `#multiple-instances` |
| AC4 settings exist in code | 4 | grep loop output in report |
| AC5 PRD done, 100% | 5 | `gen_index.py` `errors: none`, board 100% |
