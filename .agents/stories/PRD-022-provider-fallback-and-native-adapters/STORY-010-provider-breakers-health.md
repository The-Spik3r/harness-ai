---
id: STORY-010
prd: PRD-022
slug: provider-breakers-health
title: health.py — one CircuitBreaker per provider, fault recording rules, providers_status()
type: feature
priority: high
complexity: medium
phase: "3 - Chains and breaker"
status: todo
labels: [backend, resilience, concurrency]
epic_branch: epic/PRD-022-provider-fallback-and-native-adapters
plan: null
report: null
commit: null
depends_on: [STORY-002]
blocks: [STORY-011, STORY-015]
skills: []
created: 2026-11-20
updated: 2026-11-20
---

# STORY-010: Provider breakers and providers_status()

## Description

As an operator, I want each provider to have its own circuit breaker with PRD-018's state machine, so that a provider that keeps failing is skipped without a network call and I can see why.

## Acceptance Criteria

- [ ] Given `health.breaker(name)`, when called, then it returns that provider's process-local `CircuitBreaker(name, threshold=5, open_seconds=10.0, probe=None, clock=...)` (module constants `_BREAKER_FAILURE_THRESHOLD`, `_BREAKER_OPEN_SECONDS`, `_PROVIDER_MISCONFIGURED_OPEN_SECONDS = 300`), created lazily and thread-safely; a provider absent from the current registry snapshot has its breaker dropped
- [ ] Given `health.record(name, outcome)`, when the outcome is success, then the breaker records success; a `fallback_eligible` fault other than `misconfigured` records a failure classed by `kind`; `misconfigured` force-opens for 300 s; a 429 that opens the breaker opens it for `max(retry_after_seconds, 10)`; non-eligible faults (`status` 4xx, `shape`, `incompatible`, `refusal`) record nothing
- [ ] Given `health.admit(name)`, when the breaker is closed, it admits; open → `("open", retry_after_seconds)`; half-open with the single live trial already claimed → `("half_open_busy", ...)`; the first caller after the open window is admitted as the trial (PRD-018's `probe=None` semantics) — tested with an injected clock and two threads
- [ ] Given `providers_status()`, when called, then it returns `instance` (PRD-018's format) and, per provider, a PRD-018-shaped `breaker` object (`state`, `since`, `consecutive_failures`, `last_failure_class`, `retry_after_seconds`) plus process-local counters (`attempts_failed` by `provider:kind`, `fallback_answers`, `skipped` by `provider:reason`, `breaker_opens`) with increment helpers; it makes no network or database call
- [ ] Given a breaker transition, when it happens, then exactly one WARNING line names the provider, from/to states and the fault kind, never message text (reuse the breaker's own transition log; check its level)

## Technical Notes

- `app/services/circuit_breaker.py` (`CircuitBreaker` `:93`, `before` `:183`, `record_success` `:246`, `record_failure` `:259`, `force_open` `:281`, `status` `:294`, `BreakerOpen` `:78`); storage's use in `app/db/database.py:154-155, 321-322`; PRD-018 counters in `app/db/storage_counters.py`; `storage_status()` `database.py:1341` for the `instance` and shape.
- The 429 open-time rule may need a small optional argument on `CircuitBreaker` (e.g. `record_failure(cls, open_seconds=None)`); if so, storage's behaviour and PRD-018's tests stay unchanged.
- New file `app/services/upstream/health.py`; pure of settings; injected clock for tests. No wiring into the pipeline here (STORY-011/012).

## Dependencies

- **Blocked by**: STORY-002
- **Blocks**: STORY-011, STORY-015

## PRD Reference

Source: [`PRD-022/PRD.md`](../../PRDs/PRD-022-provider-fallback-and-native-adapters/PRD.md) — Sections 6.10, F6, F9, D12, User story 6
