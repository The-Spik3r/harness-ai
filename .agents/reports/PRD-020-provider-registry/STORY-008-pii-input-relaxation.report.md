---
story: STORY-008
prd: PRD-020
plan: .agents/plans/PRD-020-provider-registry/completed/STORY-008-pii-input-relaxation.plan.md
epic_branch: epic/PRD-020-provider-registry
commit: 8ab795e
status: COMPLETE
completed: 2026-11-18
---

# Implementation Report - STORY-008: PII input relaxation for an internal, relaxed provider

**Plan**: `.agents/plans/PRD-020-provider-registry/completed/STORY-008-pii-input-relaxation.plan.md`
**Epic Branch**: `epic/PRD-020-provider-registry`
**Commit**: `8ab795e`

## Summary

Step 6 of `run_conversation` evaluates `relaxed = route.relaxes_input()` once, from the Route alone. When true it skips the code size limit and the per-message input redaction; the original `Message` objects go to the seam and `input_entities` stays empty (`pii_detected_input=0`, meaning not analyzed). The five `log_query` calls after the decision pass `pii_input_relaxed=relaxed`. Patterns (step 5) and output redaction (step 8) are unchanged; the standard path is textually unchanged.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Step 6 gate: `relaxed`, limit skipped, loop bypassed | `app/services/query_pipeline.py` | done |
| 2 | `pii_input_relaxed=relaxed` on the 5 post-decision rows | `app/services/query_pipeline.py` | done |
| 3 | New tests (18) | `tests/test_query_pipeline_pii_relaxation.py` | done |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| Targeted tests (one call, 7 files) | 231 passed, 0 failed, 0 skipped |
| Full suite | GitHub CI on push (user decision) |

## Deviations from Plan

- The stub server logs counts only, never content, so "what reached the upstream" is read from an injected `call_openrouter` capture (real registry and route in front of it; `/query` and `/v1` cases patch the router's `call_openrouter`), not from the stub log.
- Shape: the loop is bypassed with `enumerate([] if relaxed else messages)` and `redacted_messages = list(messages) if relaxed else []`, keeping the standard path's text unchanged and the diff to a few lines.

## Tests Written

`tests/test_query_pipeline_pii_relaxation.py`: 2x2 matrix (chat/code x relaxed/standard/absent), chat output still masked, code size limit skipped when relaxed and enforced when standard or external, switch off, legacy mode, pattern block before step 6, output-redaction error row flag, original message objects with tool turns, `/query` and `/v1/chat/completions` (code profile) end to end, source guard (five flags after the single decision).

## Acceptance Criteria

- [x] AC1 code relaxed (also over `/v1`)
- [x] AC2 chat relaxed: input unmasked, output masked
- [x] AC3 standard/absent: masked, limit enforced, flag 0
- [x] AC4 switch off -> false, flag 0
- [x] AC5 patterns unchanged, before step 6
