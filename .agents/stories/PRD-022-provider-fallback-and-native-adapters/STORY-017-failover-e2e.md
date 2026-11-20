---
id: STORY-017
prd: PRD-022
slug: failover-e2e
title: E2E — OpenRouter killed, Anthropic answers a tools request, breaker opens, status reports it
type: technical
priority: high
complexity: medium
phase: "4 - Observability, streaming, docs"
status: todo
labels: [testing, e2e]
epic_branch: epic/PRD-022-provider-fallback-and-native-adapters
plan: null
report: null
commit: null
depends_on: [STORY-008, STORY-013, STORY-014, STORY-015]
blocks: [STORY-018]
skills: []
created: 2026-11-20
updated: 2026-11-20
---

# STORY-017: Failover E2E

## Description

As the PRD's MVP definition, I want an end-to-end test with real processes (harness + stub OpenRouter + stub Anthropic) driven by the OpenAI SDK, so that the Section 1 goal is demonstrated, not inferred.

## Acceptance Criteria

- [ ] Given the User story 1 chain, a stub OpenRouter scripted to fail (503) and a stub in Anthropic mode, when the OpenAI SDK sends a `/v1` tools request, then Anthropic answers, the client's `tool_calls[0].function.arguments` is canonical JSON decided by the action policy, `X-Harness-Provider` names the Anthropic provider, and `/audit?request_id=` shows the two rows of User story 1
- [ ] Given the same setup, when requests continue to fail on OpenRouter, then after PRD-018's threshold the breaker opens and the next request reaches OpenRouter **zero** times (stub hit counter) while still being answered by Anthropic
- [ ] Given both stubs failing, when every breaker is open, then `/v1` returns 502 `upstream_unavailable` with `retry-after` and zero stub hits, and one `success=0` row with `skipped_providers` (User story 4)
- [ ] Given `GET /providers/status`, when read after the run, then both providers' breaker states and counters match what happened
- [ ] Given the e2e marker conventions, when the suite runs without `--run-e2e`, then the test is skipped; with it, it passes locally on Windows and in CI (if CI runs e2e)

## Technical Notes

- Existing e2e harness: `tests/e2e/` (scripts under `tests/e2e/scripts/`, `requirements-e2e.txt` pins `openai==3.40.0`). Follow the PRD-020/021 e2e tests' structure for process start-up and stub ports.
- The breaker threshold is 5 (constants); the PRD's F11 text says "three requests open the breaker" — the threshold wins; script enough failures to reach it.
- Orchestrator decision (STORY-013): `X-Harness-Provider` / `harness.provider` / `harness.attempts` exist on buffered JSON `/v1` responses only; a stream carries only the answering `model`. O5 (no eligible candidate) is 502 `upstream_error`, `x-should-retry: false`, message `no provider can serve this request: <reasons>`.

## Dependencies

- **Blocked by**: STORY-008, STORY-013, STORY-014, STORY-015
- **Blocks**: STORY-018

## PRD Reference

Source: [`PRD-022/PRD.md`](../../PRDs/PRD-022-provider-fallback-and-native-adapters/PRD.md) — Sections 1 (MVP goal), F11, 11 (MVP definition), User stories 1, 3, 4, 6
