---
id: STORY-013
prd: PRD-022
slug: v1-response-surfaces
title: /v1 surfaces — answering model, harness.provider/attempts, X-Harness-Provider, exhaustion with retry-after
type: feature
priority: high
complexity: medium
phase: "3 - Chains and breaker"
status: todo
labels: [backend, api, v1]
epic_branch: epic/PRD-022-provider-fallback-and-native-adapters
plan: null
report: null
commit: null
depends_on: [STORY-012]
blocks: [STORY-014, STORY-017]
skills: []
created: 2026-11-20
updated: 2026-11-20
---

# STORY-013: /v1 response surfaces

## Description

As a coding agent on `/v1`, I want to know which provider answered and to get a retryable error with a backoff hint on a total outage, so that my SDK behaves well during failover.

## Acceptance Criteria

- [ ] Given a fallback answer on `/v1/chat/completions` (buffered, and the buffered-SSE stream), when returned, then `model` is the answering catalogue id, the body's `harness` object gains `provider` and `attempts`, and the response has `X-Harness-Provider: <provider name>`; without a fallback `model` equals the requested id and only the new `harness` fields/header are added
- [ ] Given `ChainExhausted` with `retry_after_seconds`, when `/v1` maps it, then 502 `upstream_unavailable` with a `retry-after: <s>` header and no `x-should-retry`; without `retry_after_seconds`, no `retry-after` header
- [ ] Given the last attempt failed non-eligibly (4xx, `shape`, `incompatible`), when mapped, then 502 `upstream_error` with `x-should-retry: false` as today; given no candidate eligible at all for capability/route/BYOK reasons (primary included), then 502 `upstream_error`, non-retryable, naming the capability (O5)
- [ ] Given the error and health surfaces, when any error body or header is built, then it carries only `kind` and status, never provider message text or keys (T10, `v1.py` fault rule); existing `/v1` tests pass unmodified apart from asserting the new header/fields

## Technical Notes

- `app/routers/v1.py` `_PIPELINE_FAULTS` (`:111`), `_Upstream` wrapper (`:120-151`: one call per attempt; `called` = commit signal; `result` = answering call), fault mapping (`:198-212`); `app/services/v1_translate.py` fault table (`:713-718`) and response builder.
- How the pipeline tells `/v1` the answering provider/attempts: through the pipeline result or the `_Upstream` wrapper — the plan picks one and states it; `v1_translate.py` must stay import-free of the upstream package `__init__` (PRD-021 rule).
- `/query` mapping of `ChainExhausted` (502 `all providers unavailable`) is STORY-012's; check it is consistent.
- Orchestrator decision (STORY-012): `ChainExhausted` already maps to 502 `upstream_unavailable` in `/v1` (`v1.py:300`, it is a retryable `UpstreamError`) and to 502 `all providers unavailable` in `/query`; this story adds `retry-after`, `harness.provider` and the answering `model`. The pipeline exposes the answering route via `chain_outcome.route` (rebound to `route` after `chain.run`); the audit `model_used` stays the requested id on the chained path (D17). A chained request with no attempt and a primary `redaction_limit` skip returns today's `QueryBlockedContextLimitResponse`, not `ChainExhausted`.

## Dependencies

- **Blocked by**: STORY-012
- **Blocks**: STORY-014, STORY-017

## PRD Reference

Source: [`PRD-022/PRD.md`](../../PRDs/PRD-022-provider-fallback-and-native-adapters/PRD.md) — Sections 10, F7, F10, D12, D17, O5, T10, User story 4
