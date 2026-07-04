---
story: STORY-005
prd: PRD-001
plan: .agents/plans/PRD-001-harness-ia/completed/STORY-005-pattern-detection-service.plan.md
epic_branch: epic/PRD-001-harness-ia
commit: 42724a4
status: COMPLETE
completed: 2026-07-04
---

# Implementation Report — STORY-005: Suspicious pattern detection service

**Plan**: `.agents/plans/PRD-001-harness-ia/completed/STORY-005-pattern-detection-service.plan.md`
**Epic Branch**: `epic/PRD-001-harness-ia`
**Commit**: `42724a4`

## Summary

Implemented `app/services/pattern_detector.py`, a pure function `detect_suspicious_pattern(prompt)` that scans a prompt for any of the seven PRD Section 9 suspicious substrings (case-insensitive, plain substring match). Returns a `PatternDetectionResult(is_suspicious, pattern)` dataclass carrying the specific matched pattern text. The pattern list is a single module-level constant (`SUSPICIOUS_PATTERNS`), satisfying the Strategy-pattern requirement (PRD Section 6) — extending the list requires no branching-logic changes.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Create pattern detector service | `app/services/pattern_detector.py` | ✅ |
| 2 | Create unit tests | `tests/test_pattern_detector.py` | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`app.services.pattern_detector`) | ✅ |
| Backend import (`app.main`) | ✅ |
| Tests (`test_pattern_detector.py`) | ✅ (10 passed) |
| Full suite (`pytest tests/ -v`) | ✅ (31 passed) |
| E2E | ✅ (5/5 checklist items) |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/services/pattern_detector.py` | CREATE | +25 |
| `tests/test_pattern_detector.py` | CREATE | +43 |

## Deviations from Plan

None. Implementation matches the plan exactly, including the module structure, dataclass shape, and test coverage (7 parametrized pattern cases + clean prompt + mixed-case + first-match-wins).

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_pattern_detector.py` | `test_each_pattern_is_flagged_individually` (parametrized ×7 — one per PRD Section 9 pattern), `test_clean_prompt_reports_not_suspicious`, `test_mixed_case_pattern_still_flagged`, `test_first_matching_pattern_returned_when_multiple_present` |

## Acceptance Criteria

- [x] Given a prompt containing any of the seven patterns from PRD Section 9, when scanned, then the detector flags it as suspicious and reports which pattern matched.
- [x] Given a prompt with a pattern in different casing (e.g. "IGNORE PREVIOUS INSTRUCTIONS"), when scanned, then it is still flagged (case-insensitive match).
- [x] Given a prompt containing none of the listed patterns, when scanned, then the detector reports "clean" (`is_suspicious=False`) and no pattern name (`pattern=None`).
- [x] Given the pattern list, when a new pattern needs to be added, then it can be done by editing a single data structure (`SUSPICIOUS_PATTERNS` list), not branching logic.
