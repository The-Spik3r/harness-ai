---
id: STORY-016
prd: PRD-021
slug: streaming-docs
title: Document real-time streaming, grants and progress feedback
type: enhancement
priority: medium
complexity: small
phase: "4 - Clients and docs"
status: done
labels: [docs]
epic_branch: epic/PRD-021-realtime-streaming
plan: .agents/plans/PRD-021-realtime-streaming/completed/STORY-016-streaming-docs.plan.md
report: .agents/reports/PRD-021-realtime-streaming/STORY-016-streaming-docs.report.md
commit: 305ce41
depends_on: [STORY-010, STORY-012, STORY-013, STORY-014, STORY-015]
blocks: []
skills: []
created: 2026-11-18
updated: 2026-11-19
---

# STORY-016: Document real-time streaming, grants and progress feedback

## Description

As a platform operator, I want the docs to explain the two delivery modes, how to grant them and what they cost, so that I can turn real time on knowingly.

## Acceptance Criteria

- [ ] Given `docs/features.md`, when read, then the OpenAI-compatible endpoint and Tool calling sections no longer say "`stream: true` is buffered, not streamed" without qualification; they describe buffered vs real-time delivery, the two permissions, the switch, held tool calls, `reasoning_content`, the error-after-commit shape, and the residual risks (released text cannot be recalled, T3's reasoning residual, the divergence column)
- [ ] Given the gate cost numbers from STORY-008 and the latency numbers from STORY-010/011, when documented, then they appear in `docs/features.md` with the conditions they were measured under
- [ ] Given `.env.example` and `README.md`, when read, then `STREAMING_ENABLED`, `STREAM_HOLDBACK_MAX_CHARACTERS`, `STREAM_COALESCE_MS` are listed with defaults, and an `RBAC_ROLES_FILE` example grants `stream:realtime`; the docs state that real time needs a providers-file model with `streaming: true` (legacy mode never streams)
- [ ] Given `docs/roadmap.md`, when read, then PRD-021 is marked delivered and Section 13's future items are listed; the verified-client list follows STORY-014/015's reports

## Technical Notes

- `docs/features.md:241,248,476,489` today (line numbers may have moved; grep "buffered").
- Docs only; no code.
- Orchestrator note (STORY-008): AC5 latency numbers are in `.agents/reports/PRD-021-realtime-streaming/STORY-008-gates-in-pipeline.report.md` (chat segment p95 16.7 ms, response p95 530.9 ms vs final pass 87.5 ms; code segment p95 3.3 ms); measured with `scripts/measure_stream_gate_latency.py`. Batching fallback not needed.

## Dependencies

- **Blocked by**: STORY-010, STORY-012, STORY-013, STORY-014, STORY-015
- **Blocks**: None

## PRD Reference

Source: [`PRD-021/PRD.md`](../../PRDs/PRD-021-realtime-streaming/PRD.md) — Sections 4 (Documentation), 9.3, 12 Phase 4
