---
id: STORY-004
prd: PRD-019
slug: caddy-balancer-spike
title: Spike — verify Caddy cookie policy, health, error and retry behaviour against a pinned Caddy
type: spike
priority: high
complexity: small
phase: "2 - Balancer"
status: done
labels: [caddy, spike, infra]
epic_branch: epic/PRD-019-multi-instance-deployment
plan: .agents/plans/PRD-019-multi-instance-deployment/completed/STORY-004-caddy-balancer-spike.plan.md
report: .agents/reports/PRD-019-multi-instance-deployment/STORY-004-caddy-balancer-spike.report.md
commit: 2e0ac34
depends_on: []
blocks: [STORY-005]
skills: []
created: 2026-11-17
updated: 2026-11-17
---

# STORY-004: Caddy balancer spike

## Description

As the implementer of the balancer, I want every Caddy behaviour this PRD assumes checked against the exact Caddy version we will pin, so that the Caddyfile and tests rest on measured facts (PRD Risk 6, "Not verified in code").

## Acceptance Criteria

- [ ] Given the spike, when it picks a Caddy 2.x version, then it records the version, the official image digest (`caddy:2.<minor>`), and the release binary URL + SHA-256 for Linux amd64 (CI) — and, if available locally, the Windows binary — in a findings section of the report.
- [ ] Given a throwaway setup (real `caddy` process + two tiny local HTTP backends, scripts in the scratchpad or `scripts/spikes/`), when exercised, then the report records verbatim: the `lb_policy cookie` cookie name/attributes (HttpOnly, SameSite, Secure, Path, Max-Age) and its value shape with a secret; whether Caddy re-selects and re-sets the cookie when the pinned upstream is unhealthy.
- [ ] Given no healthy upstream, when a request arrives, then the report records the status Caddy generates (502 vs 503), that `handle_errors` catches it, and that a proxied upstream 503 (with `Retry-After`) passes through untouched and is **not** caught by `handle_errors`.
- [ ] Given a POST that reached an upstream which then dropped the connection, when `lb_try_duration` is set without `retry_match`, then the report records whether Caddy replays it on the other upstream (expected: no for a sent non-GET), and whether a dial failure is retried (expected: yes).
- [ ] Given the pinned version, when parsed, then the report confirms the directive names in PRD F3 (`lb_try_duration`, `health_uri`, `health_interval`, `health_timeout`, `health_status`, `fail_duration`, `transport http { dial_timeout response_header_timeout }`, `stream_close_delay`) are accepted (`caddy validate` / `caddy adapt`), and how the upstream list can be overridden for tests (env placeholder with default, e.g. `{$LB_UPSTREAMS:…}`) — verified, not assumed. The PRD (F3, Section 15 "Not verified") is amended where reality differs, and later stories get `Orchestrator decision` notes.

## Technical Notes

- No application code. Deliverables: the report's findings section, PRD amendments, and optionally a small reusable helper idea for STORY-007 (how to start/stop a caddy process on Windows and Linux).
- Caddy may not be installed on the Windows dev machine; downloading the official release zip into the scratchpad is fine (do not commit binaries).
- The third "Not verified" item (`_token` in the disk-state pickle) is optional; record it if cheap.

## Dependencies

- **Blocked by**: None
- **Blocks**: STORY-005

## PRD Reference

Source: [`PRD-019/PRD.md`](../../PRDs/PRD-019-multi-instance-deployment/PRD.md) — Sections 7 F3, 14 Risk 6, 15 "Not verified in code"; decisions D1, D6, D9
