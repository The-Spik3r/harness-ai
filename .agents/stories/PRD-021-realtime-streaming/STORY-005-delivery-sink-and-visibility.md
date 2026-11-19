---
id: STORY-005
prd: PRD-021
slug: delivery-sink-and-visibility
title: DeliverySink, step 2d visibility and stage events
type: feature
priority: high
complexity: medium
phase: "2 - Pipeline"
status: in-progress
labels: [backend, pipeline, streaming]
epic_branch: epic/PRD-021-realtime-streaming
plan: .agents/plans/PRD-021-realtime-streaming/STORY-005-delivery-sink-and-visibility.plan.md
report: null
commit: null
depends_on: [STORY-002]
blocks: [STORY-006]
skills: []
created: 2026-11-18
updated: 2026-11-18
---

# STORY-005: DeliverySink, step 2d visibility and stage events

## Description

As the pipeline author, I want a delivery sink the pipeline reports to, a visibility decision computed once after admission, and stage events at the steps that run, so that ingresses can show progress and later stories can stream content, while `sink=None` stays today's behaviour.

## Acceptance Criteria

- [ ] Given `app/services/delivery.py` (new, pure: no settings, no I/O), when imported, then it defines the `DeliverySink` protocol (`stage`, `phase`, `content`, `reasoning`, `committed`), closed `StageName`/`PhaseName` vocabularies, frozen `Visibility(realtime, reasoning, upstream_streamed)` with a pure constructor taking the switch, the two `holds()` results, the capabilities and the ingress, and `QueueSink(loop)` that forwards with `loop.call_soon_threadsafe` into an unbounded `asyncio.Queue` and silently drops puts once closed or once the loop is gone
- [ ] Given `run_conversation(..., *, sink=None)`, when any existing caller runs, then no event is computed and every existing test passes unchanged
- [ ] Given a sink, when a request passes step 2c, then step 2d computes `Visibility` per Section 6.1 (`realtime = STREAMING_ENABLED ∧ holds(stream:realtime) ∧ caps.streaming`, `reasoning = STREAMING_ENABLED ∧ holds(reasoning:view) ∧ caps.reasoning`, `upstream_streamed = STREAMING_ENABLED ∧ caps.streaming ∧ (realtime ∨ reasoning ∨ ingress == "chat")`) from the route resolved at step 2; a refused request never computes it
- [ ] Given a sink, when the pipeline runs, then `stage()` is called at the head of steps 2, 2c (only with `USAGE_LIMITS_ENABLED`), 4, 5, 6 (only with `PII_REDACTION_ENABLED`), 7c (only when calls exist) and 8 (`masking_output`, only when output redaction runs) — names only, depending on configuration, never on what a check found (T10)
- [ ] Given a recording sink and a role without `stream:realtime`, when the pipeline runs across the visibility matrix, then `content` and `reasoning` are never called (this story never calls them at all); `/query`/`run_query` never pass a sink (D20)

## Technical Notes

- `query_pipeline.py:373` `run_conversation`; step 2c at `:432-438` area; `_deny` discipline `:245-305`. `sink=` follows the "defaulted keyword, passed only when set" pattern (PRD Section 6.9).
- Visibility is stored for STORY-006 to read; this story does not change step 7.
- `holds()` only, never `authorize()` (T8). The settings are read per request inside the pipeline and passed into the pure constructor.
- Stage name vocabulary (Section 7.1): `checking_permissions`, `checking_usage`, `checking_duplicates`, `inspecting_prompt`, `masking_input`, `evaluating_actions`, `masking_output`. Phase vocabulary: `waiting`, `thinking`, `writing`, `preparing_action`.
- A sink method that raises must not break the pipeline: wrap calls so a sink fault is logged once and ignored (the pipeline never depends on its consumer, Section 6.3).

## Dependencies

- **Blocked by**: STORY-002
- **Blocks**: STORY-006

## PRD Reference

Source: [`PRD-021/PRD.md`](../../PRDs/PRD-021-realtime-streaming/PRD.md) — Sections 6.1, 6.3, 6.4, F3, F4, D3, D11, D18, T10
