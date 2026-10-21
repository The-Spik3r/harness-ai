---
id: STORY-018
prd: PRD-015
slug: caddy-route-and-docker-smoke
title: "Caddy routes /v1/*; Docker smoke with keep-alive through Caddy"
type: technical
priority: high
complexity: medium
phase: "4 - Real clients, deployment, documentation"
status: todo
labels: [deployment, docker, caddy, e2e]
epic_branch: epic/PRD-015-openai-compatible-endpoint
plan: null
report: null
commit: null
depends_on: [STORY-013, STORY-014]
blocks: [STORY-019]
skills: []
created: 2026-10-21
updated: 2026-10-21
---

# STORY-018: Caddy routes /v1/*; Docker smoke with keep-alive through Caddy

## Description

As a platform operator, I want `/v1` served through the same Caddy front door as `/query`, with streamed responses flushed rather than buffered, so that the endpoint works in the Docker deployment exactly as it does locally.

## Acceptance Criteria

- [ ] Given the `Caddyfile`, when it is read, then `@backend_routes` includes `/v1/*` and nothing else changed; a test asserts every harness route prefix (including `/v1`) is in the matcher.
- [ ] Given `docker compose up` with `OPENROUTER_BASE_URL` pointed at the stub, when `POST /v1/chat/completions` is sent to Caddy's port, non-streaming and streaming, then both answer as they do against `uvicorn` directly.
- [ ] Given a stub delay of 30 s and `V1_SSE_KEEPALIVE_SECONDS=10`, when a streamed request goes through Caddy with `encode gzip` in force, then the client receives each keep-alive within 2 s of its interval (Caddy does not buffer `text/event-stream`).
- [ ] Given the smoke, when it runs, then the Reflex routes and `/query` still answer through Caddy, and `/v1/models` returns the allowlist.

## Technical Notes

- `Caddyfile`: add `/v1/*` to the `@backend_routes` path list. If Caddy's encoder buffers SSE in the pinned image, exclude `text/event-stream` from `encode` (or set `flush_interval -1` on the proxy) and say why in a comment.
- The stub must be reachable from the container: run it on the host and use `host.docker.internal`, or as a compose override service; `OPENROUTER_BASE_URL` allows `http` only on loopback, so the override service needs `https` or the stub must sit in the same network namespace. Resolve this in the plan (compose override with `network_mode: service:...` is one option) and record it.
- Docker Desktop port-forwarding stalls are known (PRD-014 STORY-006 spike); run the smoke in-network if it flakes, using the in-network recipe from `scripts/test-db-in-network.sh`.
- The executor-concurrency measurement from PRD Risk 6 (N concurrent streamed requests vs `PIPELINE_MAX_WORKERS`) is taken here and recorded in the report.
- Skills: none applicable.

## Dependencies

- **Blocked by**: STORY-013, STORY-014
- **Blocks**: STORY-019

## PRD Reference

Source: [`PRD-015-openai-compatible-endpoint/PRD.md`](../../PRDs/PRD-015-openai-compatible-endpoint/PRD.md) — sections 6.1, 7.6 (Caddy), 11, 14 (Risks 1, 6)
