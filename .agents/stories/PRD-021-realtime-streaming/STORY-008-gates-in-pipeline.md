---
id: STORY-008
prd: PRD-021
slug: gates-in-pipeline
title: Gates in the pipeline, final pass, divergence and reasoning result
type: feature
priority: high
complexity: medium
phase: "2 - Pipeline"
status: todo
labels: [backend, pipeline, pii, streaming]
epic_branch: epic/PRD-021-realtime-streaming
plan: null
report: null
commit: null
depends_on: [STORY-006, STORY-007]
blocks: [STORY-009]
skills: []
created: 2026-11-18
updated: 2026-11-18
---

# STORY-008: Gates in the pipeline, final pass, divergence and reasoning result

## Description

As a security admin, I want every streamed character to pass the same redaction the buffered answer gets, with any difference between the live and final redaction detected and logged, so that real time is measurable and never silently weaker.

## Acceptance Criteria

- [ ] Given a real-time request whose policy redacts output, when `TextDelta`s arrive, then `sink.content` receives only what `OutputGate.feed` releases and, at the end, `finish()`'s remainder; under `code` with output off, deltas go straight to the sink and no final pass runs (as step 8 today)
- [ ] Given a real-time request, when step 8 runs, then its output redaction is replaced by the gate's final pass; the returned response (and so the chat bubble and audit entities) is the final pass's text; a buffered request runs today's step 8 unchanged
- [ ] Given the gate's released text differs from the final pass, when the request ends, then a `WARNING` names the user and `completion_id` (never content) and the divergence flag is carried to the row writer (persisted by STORY-009)
- [ ] Given `visibility.reasoning`, when reasoning arrives, then real time sends `redact_reasoning` output per segment to `sink.reasoning` (same segmenting as the content gate), and buffered delivery returns the whole redacted reasoning on the pipeline's result (a new optional field, absent/None without the grant); reasoning is never written to `chat_messages` or the audit row (D8)
- [ ] Given a `chat` and a `code` profile, when a scripted 2 000-character response is gated, then p95 per segment and per response are measured against step 8's single call and the numbers are written to the story report (STORY-016 copies them to `docs/features.md`); if p95 per segment exceeds 150 ms, segments batch to two sentences (Risk 2)

## Technical Notes

- Depends on STORY-006's streamed step 7 and STORY-007's `OutputGate`/`redact_reasoning`.
- The sink receives reasoning only when `visibility.reasoning ∧ visibility.realtime`; for `reasoning` without `realtime` the reasoning is collected and returned whole.
- The chat ingress without grants streams upstream (phases) but its response path is the buffered one: the gate must not run there (nothing is released), and step 8 is today's.
- Orchestrator decision (STORY-006 impl, 0eb1fc1): the two gate seams are marked `# STORY-008: output gate` and `# STORY-007/008: reasoning gate` in step 7 of `run_conversation`; `released` flips only when text is actually forwarded, so a gate that holds text back must set it on release, not on receipt. `received_text`/`received_calls` feed the T6 mid-stream estimate and count everything received (orchestrator decision at 006 3.2).
- Orchestrator decision (STORY-007 impl, d1e6fb0): the gate contract is `OutputGate(policy, holdback_max, *, final_redact=)` with `feed(text) -> str` and `finish() -> GateResult(released, final_text, final_entities, diverged, remainder)`; `remainder` is what `finish()` itself releases and must be sent as the last content delta. Pass `query_pipeline._redact` as the content gate's `final_redact` and `stream_redaction.redact_reasoning` for the reasoning gate (`OutputGate(reasoning_policy(policy), ...)`). `gate_applies(policy, settings.PII_REDACTION_ENABLED)` False means forward raw (code, output off). A `PiiRedactorError` in `feed` poisons the gate (nothing raw is released; `released_so_far` gives what left, for the T6 estimate); one from `final_redact` in `finish` propagates. With the master PII switch off, reasoning is not redacted either (PRD-012). A span crossing from the tail into a segment is clipped and masked (orchestrator decision at 007 3.2), so `diverged` is True there.

## Dependencies

- **Blocked by**: STORY-006, STORY-007
- **Blocks**: STORY-009

## PRD Reference

Source: [`PRD-021/PRD.md`](../../PRDs/PRD-021-realtime-streaming/PRD.md) — Sections 6.1, 6.5, D7, D8, T3, T12, Risk 1-2, Quality indicators
