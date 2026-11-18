---
id: STORY-014
prd: PRD-020
slug: local-model-e2e
title: Opt-in end-to-end run against a real local OpenAI-compatible server
type: technical
priority: medium
complexity: medium
phase: "4 - Streaming interface, E2E, docs"
status: in-progress
labels: [testing, e2e]
epic_branch: epic/PRD-020-provider-registry
plan: .agents/plans/PRD-020-provider-registry/STORY-014-local-model-e2e.plan.md
report: null
commit: null
depends_on: [STORY-008, STORY-009, STORY-011, STORY-013]
blocks: [STORY-015]
skills: []
created: 2026-11-18
updated: 2026-11-18
---

# STORY-014: Opt-in end-to-end run against a real local OpenAI-compatible server

## Description

As a maintainer, I want an opt-in E2E run against a real local model server, so that the registry, adapter, relaxation, estimate and tool path are proven against a real server's shapes and not only the stub.

## Acceptance Criteria

- [ ] Given `--run-e2e` and a reachable server (base URL from `HARNESS_E2E_LOCAL_BASE_URL`, default LM Studio `http://localhost:1235/v1`) with the pinned model (from `HARNESS_E2E_LOCAL_MODEL`, default `google/gemma-4-e4b`), when a `/query` request is sent, then it is answered and the audit row has `provider='local'` (the registry's name for it; amended 2026-11-18 from `ollama`, user decision in Technical Notes).
- [ ] Given the same server, when a `/v1` request is made through the OpenAI SDK (buffered to the client), then it is answered with the model's text and the row says the provider.
- [ ] Given the same server, when a `/v1` tool-call request is made and the model returns one tool call, then it is released through the action policy (the existing `tests/e2e` policy style) and recorded.
- [ ] Given no server, no model, or no `--run-e2e`, when the suite runs, then the tests are skipped (never failed) with a reason naming what is missing.
- [ ] Given a completed run, when the report is written, then it records what the server exposes (Ollama: `/api/version` and the `/api/tags` digest; LM Studio: `/api/v0/models` arch, quantization, state; else "not exposed") and whether `usage` was reported (estimated or real).

## Technical Notes

- Opt-in marker pattern: `tests/conftest.py:163-216` (`--run-e2e`, the `e2e` marker `:186`, skip logic `:193-216`); live helpers `tests/e2e/_live.py`, OpenAI SDK precedent `tests/e2e/test_openai_sdk.py`, tool-loop precedent `tests/e2e/test_opencode.py` and `tests/e2e/scripts/tool_loop.json`.
- Server config by env vars with defaults: base URL default `http://127.0.0.1:11434/v1` (Ollama), model env var. The pinned model is NOT decided yet: the orchestrator will settle it with the user before this story is planned, so the plan must not pick one.
- The test writes a registry through `tests/_providers.py` (OD2) with a keyless `ollama` provider (`trust: internal`, `usage_missing: estimate`) and starts the harness the way the other E2E tests do. Server version via `GET /api/version`, digest via `GET /api/tags` for Ollama; other servers record what they expose.
- Section 8 states the E2E needs Ollama on `127.0.0.1:11434` with the pinned model pulled and is skipped when absent; the report location follows the `.agents/reports/` convention of the other stories.
- Orchestrator decision (user, 2026-11-18): the E2E target is the local LM Studio-style server at `http://localhost:1235/v1`, model id `google/gemma-4-e4b` (listed by its `GET /v1/models`, keyless). It stays opt-in (skipped when the server is unreachable); the URL and model id come from env vars with these values as the documented example, never hard-coded as the only option.

## Dependencies

- **Blocked by**: STORY-008, STORY-009, STORY-011, STORY-013
- **Blocks**: STORY-015

## PRD Reference

Source: [`PRD-020/PRD.md`](../../PRDs/PRD-020-provider-registry/PRD.md) — Sections 8, 11 (E2E), 15 (not verified in code); decisions D16
