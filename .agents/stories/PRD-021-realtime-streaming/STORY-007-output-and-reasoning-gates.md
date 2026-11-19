---
id: STORY-007
prd: PRD-021
slug: output-and-reasoning-gates
title: Hold-back output gate and reasoning gate
type: feature
priority: high
complexity: large
phase: "2 - Pipeline"
status: done
labels: [backend, pii, streaming]
epic_branch: epic/PRD-021-realtime-streaming
plan: .agents/plans/PRD-021-realtime-streaming/completed/STORY-007-output-and-reasoning-gates.plan.md
report: .agents/reports/PRD-021-realtime-streaming/STORY-007-output-and-reasoning-gates.report.md
commit: d1e6fb0
depends_on: []
blocks: [STORY-008]
skills: []
created: 2026-11-18
updated: 2026-11-18
---

# STORY-007: Hold-back output gate and reasoning gate

## Description

As a chat user with `stream:realtime`, I want streamed text released only in whole segments redacted with context, so that I never see a half-written email address or name the harness would have masked.

## Acceptance Criteria

- [ ] Given `app/services/stream_redaction.py` (new), when `OutputGate(policy, holdback_max).feed(text)` is called with deltas, then it returns only whole segments (`chat`: sentence end `.?!…` followed by whitespace, or newline; `code`: newline), each redacted with `_redact(context_tail + segment, policy)` where only spans starting inside the new segment are applied and the tail is the last ≤ 200 raw released characters
- [ ] Given a buffer longer than `holdback_max` with no boundary, when fed, then it releases up to its last whitespace through the same path; `finish()` releases the remainder and returns a `GateResult` with the released text, the final whole-text redaction (exactly step 8's call) and a `diverged` flag
- [ ] Given every default PII entity type in a sentence, when the text is split into two deltas at every character offset, then the concatenated released text never contains the raw entity (T2)
- [ ] Given `code` policy with `skip_fenced_blocks`, when a fenced block streams, then it is released line by line unredacted, as step 8 leaves it; given `code` with output redaction off, then the module exposes that no gate applies (the caller forwards raw)
- [ ] Given `redact_reasoning(text, policy)`, when called under any policy (including `code` with output off), then the text is redacted with the `chat` entity list when the policy's list is narrower (D8); the segmenting logic (boundary search, tail, forced cut) is pure and tested without Presidio

## Technical Notes

- Step 8 today: `query_pipeline.py:850-882`; `_redact` at `:225-242`; policies `pii_policy.py:111-116` (`chat`, `output=True`), `:131-138` (`code`, `output=PII_CODE_REDACT_OUTPUT`).
- **CRITICAL story** (PII; the gate's contract is consumed by STORY-008): the orchestrator supplies binding design points.
- The module reads no settings; `holdback_max` and the policy come from the caller.
- Mapping spans from `context_tail + segment` back to the segment: decide how `_redact`'s output is split (e.g. analyze, then anonymize only the segment's spans) and test the boundary cases (a span crossing the tail/segment boundary was already decided with the tail).
- Test corpus per entity goes under `tests/` (it pins Risk 1 per entity, which STORY-008 measures).

## Dependencies

- **Blocked by**: None
- **Blocks**: STORY-008

## PRD Reference

Source: [`PRD-021/PRD.md`](../../PRDs/PRD-021-realtime-streaming/PRD.md) — Sections 6.5, F5, D7, D8, T2, T3, T12
