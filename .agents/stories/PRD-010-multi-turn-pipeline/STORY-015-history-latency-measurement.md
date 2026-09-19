---
id: STORY-015
prd: PRD-010
slug: history-latency-measurement
title: "Measure added per-send latency of history assembly and per-turn redaction at 20 exchanges"
type: spike
priority: medium
complexity: small
phase: "4 - Prove and document"
status: done
labels: [backend, performance, pii]
epic_branch: epic/PRD-010-multi-turn-pipeline
plan: .agents/plans/PRD-010-multi-turn-pipeline/completed/STORY-015-history-latency-measurement.plan.md
report: .agents/reports/PRD-010-multi-turn-pipeline/STORY-015-history-latency-measurement.report.md
commit: 0a95158
depends_on: [STORY-012]
blocks: [STORY-018]
skills: []
created: 2026-09-17
updated: 2026-09-19
---

# STORY-015: Measure added per-send latency of history assembly and per-turn redaction at 20 exchanges

## Description

As a platform operator, I want the cost of sending history measured on real Presidio and a real libSQL read, so that we know whether PRD Risk 3 needs its redaction-cache follow-up before users hit it.

## Acceptance Criteria

- [ ] Given a session with 20 answered exchanges (realistic 300–800 character prompts, some with PII), when 30 sends are timed against the local libSQL dev server with real `redact()` and a stub upstream, then the report records p50/p95 for (a) `assemble`, (b) redaction of all messages, and (c) the whole `run_conversation` excluding upstream, next to the same figures for a single-turn send.
- [ ] Given the measurement, when the added latency is at most one `messages_for` read plus per-turn redaction (PRD Section 11 quality indicator), then the report says so with numbers. If not, it states the gap and opens the redaction-cache follow-up in PRD Section 13 with the data.
- [ ] Given the measurement script, when it is committed, then it lives under `scripts/` (for example `scripts/measure_history_latency.py`), is excluded from the default pytest run, and is runnable with one documented command.
- [ ] Given the full suite, when this story lands, then it is green and no production file is modified.

## Technical Notes

- Spike: the deliverable is the numbers in `.agents/reports/PRD-010-multi-turn-pipeline/STORY-015-*.report.md`, plus the script. Optimizations are out of scope for this commit.
- Reuse the round-trip measurement style from `test_round_trip_cost_is_measured_and_reported` in [tests/test_two_instance_smoke.py](../../../tests/test_two_instance_smoke.py).
- Load the spaCy model once before timing (`pii_redactor.load()`) so model load is not measured.
- Following the libSQL dev-server note, if timings look pathological after repeated runs, restart the container before drawing conclusions.
- Skills: none applicable.

## Dependencies

- **Blocked by**: STORY-012
- **Blocks**: STORY-018

## PRD Reference

Source: [`PRD-010-multi-turn-pipeline/PRD.md`](../../PRDs/PRD-010-multi-turn-pipeline/PRD.md) — sections 11 (Quality indicators), 13, 14 (Risk 3)
