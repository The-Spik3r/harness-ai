---
story: STORY-008
prd: PRD-021
plan: .agents/plans/PRD-021-realtime-streaming/completed/STORY-008-gates-in-pipeline.plan.md
epic_branch: epic/PRD-021-realtime-streaming
commit: pending
status: COMPLETE
completed: 2026-11-18
---

# Implementation Report — STORY-008: Gates in the pipeline, final pass, divergence and reasoning result

## Summary

`OutputGate` is wired at both step 7 seams of `run_conversation`. A gated realtime request takes its step 8 redaction from the gate's final pass (no second `_redact`). `released` flips only on non-empty text sent to the sink. Remainders go last (reasoning, then content). A gate `PiiRedactorError` is handled by the existing T6 arm. Divergence logs a WARNING (user, completion_id, no content). `QuerySuccessResponse.reasoning` is a private attribute, set only for reasoning grant without realtime.

## Validation

| Check | Result |
|-------|--------|
| Backend import | OK |
| Targeted tests (gates, streaming, run_conversation, delivery, pii_profiles, stream_redaction, untouched_app) | 239 passed |
| Full suite | GitHub CI on push (user decision) |

## AC5: latency (`scripts/measure_stream_gate_latency.py`, 2000 chars, 12-char deltas, 50 runs)

| Arm | segment p50 / p95 / max | response p95 | final pass p95 |
|-----|-------------------------|--------------|----------------|
| chat | 13.1 / 16.7 / 20.1 ms | 530.9 ms | 87.5 ms |
| code (output on) | 2.1 / 3.3 / 3.8 ms | 27.2 ms | 8.8 ms |

p95 per segment is far below 150 ms: the Risk 2 batching fallback was not needed.

## Deviations

- The divergence flag is a local (`stream_redaction_divergence`); `log_query` has no parameter for it until STORY-009. Tests assert the WARNING.
- Existing streaming tests changed under the gate (commented, no renames): content order, fault-after-release (now `profile="code"`), held-calls fault (`"think. "`), no-tool-fragment (`["before after"]`).
