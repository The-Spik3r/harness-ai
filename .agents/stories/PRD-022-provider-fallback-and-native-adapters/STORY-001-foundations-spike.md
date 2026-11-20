---
id: STORY-001
prd: PRD-022
slug: foundations-spike
title: Spike — confirm built PRD-018/020/021 seams, pin the anthropic SDK, check redirects and the Messages wire format
type: spike
priority: high
complexity: medium
phase: "1 - Foundations"
status: in-progress
labels: [spike, upstream, anthropic, security]
epic_branch: epic/PRD-022-provider-fallback-and-native-adapters
plan: .agents/plans/PRD-022-provider-fallback-and-native-adapters/STORY-001-foundations-spike.plan.md
report: null
commit: null
depends_on: []
blocks: [STORY-002, STORY-003, STORY-004, STORY-006]
skills: []
created: 2026-11-20
updated: 2026-11-20
---

# STORY-001: Spike — confirm built seams, pin the anthropic SDK, check redirects and the Messages wire format

## Description

As the orchestrator of PRD-022, I want the PRD's "Not verified" list checked against the code as built and against the `anthropic` SDK, so that every later story builds on facts, not on the PRD's draft-time assumptions.

## Acceptance Criteria

- [ ] Given PRD-018's `app/services/circuit_breaker.py`, when the spike reads it, then the report confirms (with `file:line`) that `CircuitBreaker` already has `before()`, `record_success()`, `record_failure(cls)`, `force_open(seconds)`, `status()`, an injected clock and `probe=None` live-trial half-open — i.e. O10 is already done and no extraction is needed — or lists exactly what is missing
- [ ] Given PRD-020/021 as built (`app/services/upstream/`, `provider_registry.py`, `authz.authorize_route`, `query_pipeline.py` steps 6–7, `v1.py` fault mapping, `AUDIT_LOGS_ADDED_COLUMNS`), when compared with PRD-022 Sections 6.1, 6.8 and "Builds on PRD-020", then every divergence (e.g. `ProviderAdapter.stream(..., *, reasoning=)`) is listed in the report with the consequence for later stories
- [ ] Given the `anthropic` SDK, when the spike installs the chosen exact version into the venv, then `requirements.txt` pins it exactly, the report names its HTTP dependency (httpx vs other), and a scratch test against a local HTTP server proves whether a 30x redirect is followed with the `x-api-key` header attached; if it is followed, the report recommends D2's raw-`httpx` fallback (the PRD amendment is the orchestrator's)
- [ ] Given the SDK's types and bundled docs (no live API call), when inspected, then the report records: the Messages SSE event names and `input_json_delta` shape, the `stop_reason` vocabulary (incl. `refusal`, `pause_turn`), usage field names incl. both cache fields, the thinking request shape (`adaptive` / `display: summarized`) or the nearest supported equivalent, the exception classes in 6.5 and how `retry-after` is read from a `RateLimitError`, and the `tool_use.id` format constraints (R5)
- [ ] Given the spike, when finished, then a committed test `tests/test_prd022_spike_anthropic_sdk.py` pins the facts later stories rely on (SDK importable at the pinned version, `max_retries=0` accepted, redirect behaviour, exception class names) without network access beyond localhost

## Technical Notes

- PRD "Not verified (STORY-001 confirms)" list and Section 8; R1, R5, R6.
- O10 is already satisfied: `app/services/circuit_breaker.py:1-37` documents `probe=None` "for PRD-022 providers" and `force_open`. Confirm, do not rewrite.
- `pip index versions anthropic` showed 2.11.0 as latest on 2026-11-20; the PRD's "1.x on httpx2" may be stale — record what is true.
- Items the spike cannot verify without a real Anthropic key (thinking-without-history acceptance, summarized thinking non-empty on every model, OpenRouter 403 semantics, OpenAI SDK honouring `retry-after` on 502) are recorded as "unverifiable offline" with the safe default the PRD proposes.
- Output: the report is the deliverable; findings that change later stories are handed to the orchestrator in the final message.

## Dependencies

- **Blocked by**: None
- **Blocks**: STORY-002, STORY-003, STORY-004, STORY-006

## PRD Reference

Source: [`PRD-022/PRD.md`](../../PRDs/PRD-022-provider-fallback-and-native-adapters/PRD.md) — Sections 6.10, 8, 14 (R1, R5, R6), 15 "Not verified", Phase 1
