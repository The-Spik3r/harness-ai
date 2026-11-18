---
id: STORY-005
prd: PRD-019
slug: balancer-caddyfile-and-compose
title: Balancer Caddyfile, docker-compose.lb.yml and the static balancer test
type: feature
priority: high
complexity: medium
phase: "2 - Balancer"
status: in-progress
labels: [caddy, docker, infra]
epic_branch: epic/PRD-019-multi-instance-deployment
plan: .agents/plans/PRD-019-multi-instance-deployment/STORY-005-balancer-caddyfile-and-compose.plan.md
report: null
commit: null
depends_on: [STORY-002, STORY-003, STORY-004]
blocks: [STORY-006, STORY-007, STORY-009]
skills: []
created: 2026-11-17
updated: 2026-11-17
---

# STORY-005: Balancer Caddyfile and compose stack

## Description

As a platform operator, I want one compose file that starts two instances behind a sticky, health-checked Caddy balancer, so that multi-instance is something the repo ships rather than something I work out.

## Acceptance Criteria

- [ ] Given `deploy/lb/Caddyfile`, when validated by the pinned Caddy, then it listens on `:{$PORT}`, proxies **every** path to `harness-a:{$PORT} harness-b:{$PORT}` with `lb_policy cookie harness_lb {$LB_COOKIE_SECRET}`, `lb_try_duration 5s`, active health on `/ready` (5 s interval, 3 s timeout, status 200), passive health with **no** `unhealthy_status`, `dial_timeout 3s`, `response_header_timeout` = `OPENROUTER_TIMEOUT_SECONDS` default + 30 s, `stream_close_delay`, no `encode`, no access log, and no `retry_match`.
- [ ] Given no healthy upstream, when a request arrives, then `handle_errors` answers 503 with `Retry-After: 10` and the fixed bodies: the OpenAI error object with code `service_unavailable` on `/v1/*`, `{"detail":"Service unavailable"}` elsewhere (exact bytes as in PRD F3, adjusted by STORY-004 findings).
- [ ] Given `docker-compose.lb.yml` (standalone), when `docker compose -f docker-compose.lb.yml config` runs with `LB_COOKIE_SECRET` set, then it is valid: `harness-a`/`harness-b` share one YAML anchor (same build, `env_file: .env`, `PORT`, no `ports`, the shared named volume at `AUDIT_BUFFER_DIR` as in `docker-compose.yml`); `lb` runs the digest-pinned `caddy` image, mounts `deploy/lb/Caddyfile`, publishes `${PORT}:${PORT}`, requires `${LB_COOKIE_SECRET:?}`, and `depends_on` both instances with `condition: service_healthy`. Without `LB_COOKIE_SECRET`, `config` fails.
- [ ] Given `tests/test_lb_caddyfile.py` (no Docker, no storage), when run, then it asserts with restated lists: the policy and cookie name, the health directives, `response_header_timeout` equals `Settings().OPENROUTER_TIMEOUT_SECONDS` default + 30 s, the upstream hostnames equal the compose instance service names, only `lb` publishes ports, the volume is shared, and the balancer has no `encode`/`log`/`unhealthy_status`/`retry_match`.
- [ ] Given `docker-compose.yml` and the in-container `Caddyfile`'s routing, when unchanged, then single-instance behaviour is unchanged.

## Technical Notes

- Read STORY-004's report first: version/digest, the verified error status, and the verified way to override upstreams for STORY-007's test (the shipped file must be runnable by the test with only the upstream addresses substituted).
- Parsing in the test: plain text/regex over the Caddyfile and `yaml.safe_load` (check that PyYAML is already installed; no new dependency) over the compose file.
- D7: two named services, no `--scale`; the balancer publishes the build-time `$PORT` (Section 6.1).
- **Orchestrator decision (from STORY-004 findings, to confirm)**: pin `caddy:2.11.7@sha256:36c24ad91a7ff7bc4c87fe22bfa8df3c4b18da0773d73fc12ee2c52b98c0bb7e`. The no-upstream status is 503 after about 5 s as the AC says. `handle_errors 502 503` also answers a request an instance broke mid-flight (the `/v1` body then wrongly says it was not sent to the model), and a `response_header_timeout` is an empty 504 that it does not catch. **Decided:** `handle_errors 502 503 504`, every one answered 503 + `Retry-After: 10`; the `/v1` message is exactly `Service unavailable. Retry after the Retry-After interval.` (code `service_unavailable`), the elsewhere body stays `{"detail":"Service unavailable"}` (PRD F3 updated). The shipped file keeps the literal F3 upstream line (no env default; see STORY-007). Do not add `Secure`; Caddy sets none.

## Dependencies

- **Blocked by**: STORY-002, STORY-003, STORY-004
- **Blocks**: STORY-006, STORY-007, STORY-009

## PRD Reference

Source: [`PRD-019/PRD.md`](../../PRDs/PRD-019-multi-instance-deployment/PRD.md) — Sections 4 (Balancer), 6.1, 7 F3–F4, 9.2 T1/T6; decisions D1, D2, D6, D7, D9
