---
id: STORY-015
prd: PRD-022
slug: providers-status-and-stats
title: GET /providers/status and the /stats fallback figures
type: feature
priority: medium
complexity: medium
phase: "4 - Observability, streaming, docs"
status: done
labels: [backend, api, observability]
epic_branch: epic/PRD-022-provider-fallback-and-native-adapters
plan: .agents/plans/PRD-022-provider-fallback-and-native-adapters/completed/STORY-015-providers-status-and-stats.plan.md
report: .agents/reports/PRD-022-provider-fallback-and-native-adapters/STORY-015-providers-status-and-stats.report.md
commit: null
depends_on: [STORY-010, STORY-012]
blocks: [STORY-016, STORY-017]
skills: []
created: 2026-11-20
updated: 2026-11-20
---

# STORY-015: /providers/status and /stats figures

## Description

As an operator, I want one endpoint that shows each provider's breaker and the fallback counters, and `/stats` figures for fallbacks and failed attempts, so that I can tell a provider outage from a bad key.

## Acceptance Criteria

- [ ] Given `GET /providers/status` with `stats:read`, when called, then it returns PRD Section 10's shape from `providers_status()` (pydantic response models mirroring `StorageStatusResponse`), with no network or database call (test patches the DB/network to raise); without `stats:read` → 403 as `/storage/status`
- [ ] Given a breaker that opened on a 401, when status is read, then `last_failure_class: "misconfigured"` and a `retry_after_seconds` near 300; message text never appears (T10)
- [ ] Given `GET /stats`, when called, then it adds `fallback_answers` (success rows with `attempt > 1`), `failed_attempts` (`attempt IS NOT NULL AND success = 0`) and `answers_by_provider: [{provider, count}]` (top N, N as the existing top lists) inside the existing single-statement snapshot
- [ ] Given a legacy deployment (no `PROVIDERS_FILE`), when status is read, then it lists the legacy provider with a closed breaker

## Technical Notes

- `app/routers/admin.py:203` `/storage/status` and `:186-215` `/stats` snapshot; `app/models/schemas.py:364` `StorageBreakerResponse`, `:401` storage status response; `app/services/authz.py:14` `stats:read`.
- Reuse `StorageBreakerResponse` for the per-provider breaker object if its fields match exactly; otherwise a sibling model with the same field names.
- Orchestrator decision (STORY-010): consume `health.providers_status(names) -> ProvidersStatus(instance, providers: Mapping[name, BreakerStatus], counters: ProviderCounters(attempts_failed: {'provider:kind': n}, fallback_answers, skipped: {'provider:reason': n}, breaker_opens))`; pass the registry's provider names (health cannot read the registry). Counters are process-local and are not pruned with breakers. Every provider breaker transition logs one WARNING (`transition_log_level`).

## Dependencies

- **Blocked by**: STORY-010, STORY-012
- **Blocks**: STORY-016, STORY-017

## PRD Reference

Source: [`PRD-022/PRD.md`](../../PRDs/PRD-022-provider-fallback-and-native-adapters/PRD.md) — Sections 10, F9, D12, T10, User story 6
