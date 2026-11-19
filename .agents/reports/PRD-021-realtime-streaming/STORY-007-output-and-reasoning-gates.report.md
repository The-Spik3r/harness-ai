---
story: STORY-007
prd: PRD-021
plan: .agents/plans/PRD-021-realtime-streaming/completed/STORY-007-output-and-reasoning-gates.plan.md
epic_branch: epic/PRD-021-realtime-streaming
commit: pending
status: COMPLETE
completed: 2026-11-18
---

# Implementation Report - STORY-007: Hold-back output gate and reasoning gate

**Plan**: `.agents/plans/PRD-021-realtime-streaming/completed/STORY-007-output-and-reasoning-gates.plan.md`
**Epic Branch**: `epic/PRD-021-realtime-streaming`
**Commit**: `pending`

## Summary

New `app/services/stream_redaction.py`: a Presidio-free `Segmenter` (sentence/line boundaries, forced cut, fence tracking), `OutputGate` (redacts `tail + segment` through the new `pii_redactor.redaction_spans`, keeps spans reaching into the segment, clips a tail-crossing span to the segment), `GateResult`, `gate_applies`, `reasoning_policy`, `redact_reasoning`. `pii_redactor.py` gains `redaction_spans`, `apply_spans` and the private `_code_spans` (extracted from `redact_for_policy`, output unchanged). The pipeline is not touched (STORY-008).

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | span entry point, `_code_spans` extraction | `app/services/pii_redactor.py` | done |
| 2-3 | Segmenter, gate, helpers | `app/services/stream_redaction.py` | done |
| 4 | gate corpus | `tests/fixtures/prd021_gate_corpus.py` | done |
| 5 | tests | `tests/test_stream_segments.py`, `tests/test_stream_redaction.py` | done |

## Validation Results

| Check | Result |
|---|---|
| Backend import | OK |
| Targeted tests (10 files) | 393 passed, 1 skipped |
| E2E | none through FastAPI (gate not wired until STORY-008); driven directly with the real analyzer |
| Full suite | GitHub CI on push (user decision) |

## Deviations from Plan

- `redaction_spans` for `chat` also applies `_merge_entities_with_spaces_between`: `AnonymizerEngine.anonymize()` defaults `merge_entities_with_spaces=True` (the plan assumed False). Without it the equivalence test fails on adjacent same-type entities.
- `GateResult` has a fifth field, `remainder` (default ""): the text `finish()` itself released, which the caller must send as the last delta. `released` is still the whole release.
- Forced cut depends only on the first `holdback_max` characters of the buffer and also applies when a boundary lies beyond `holdback_max`, so no segment exceeds `holdback_max` and cuts do not depend on delta splits. Determinism-across-splits is tested for boundary and forced cuts.
- `OutputGate` and `Segmenter` take `kind` from `policy.structure_safe`; `final_redact` errors in `finish()` propagate (gate is finished, not poisoned).

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_stream_segments.py` (35) | boundaries, ellipsis, mid-word terminators, every 2- and 3-way split, forced cut, code newlines, fence opener at every offset, closer rules, differential vs `strip_fenced_blocks` over 30k generated texts, purity AST |
| `tests/test_stream_redaction.py` (64 incl. params) | span equivalence (REDACT_CASES, code corpus), off switch, tail 200, ignored/clipped spans, no divergence per entity (chat, code), T2 per entity and offset, forced cut inside multi-word IBAN (clipped, diverged), Risk 1 pin, fences, `gate_applies`, poisoning, reasoning policy/gate, no logging import |

## Acceptance Criteria

- [x] AC1 whole segments, tail context, segment spans only: stub-span gate test, boundary tests
- [x] AC2 forced cut, `finish()`, `GateResult`, `diverged`: forced-cut and divergence tests
- [x] AC3 T2 every entity, every offset: `test_t2_*`
- [x] AC4 fences unredacted; `code` output off has no gate: fence tests, `gate_applies`
- [x] AC5 `redact_reasoning` under any policy; pure segmenting: reasoning tests, AST purity
