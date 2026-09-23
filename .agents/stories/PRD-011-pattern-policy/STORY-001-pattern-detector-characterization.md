---
id: STORY-001
prd: PRD-011
slug: pattern-detector-characterization
title: "Characterize today's substring detector before anything moves"
type: technical
priority: high
complexity: small
phase: "1 - Pin and match"
status: done
labels: [backend, tests, security]
epic_branch: epic/PRD-011-pattern-policy
plan: .agents/plans/PRD-011-pattern-policy/completed/STORY-001-pattern-detector-characterization.plan.md
report: .agents/reports/PRD-011-pattern-policy/STORY-001-pattern-detector-characterization.report.md
commit: 29743aa
depends_on: []
blocks: [STORY-002, STORY-008]
skills: []
created: 2026-09-22
updated: 2026-09-22
---

# STORY-001: Characterize today's substring detector before anything moves

## Description

As the implementer of this epic, I want today's detector verdicts pinned by a test on untouched code, so that the rewrite has to declare every behaviour change instead of absorbing one by accident.

## Acceptance Criteria

- [ ] Given untouched `app/services/pattern_detector.py`, when `tests/test_pattern_characterization.py` runs, then it is green with no production file modified in this commit.
- [ ] Given the characterization corpus, when each case runs through `detect_suspicious_pattern`, then every one of the seven `SUSPICIOUS_PATTERNS` is covered, plus: `overridden`, `overrides`, `overriding`, `@Override`, `public override void`, `override fun`, mixed case, a match spanning a newline (asserted **not** matched today, since the substring test has no whitespace tolerance), and a clean prompt.
- [ ] Given a case whose today-verdict this PRD intends to change, when it is written, then it carries a `# PRD-011: flips to <verdict> in STORY-008` comment naming the new verdict, and those cases are collected in one module-level list so STORY-008 can assert the flipped set is exactly this set and no larger.
- [ ] Given `test_first_matching_pattern_returned_when_multiple_present` in [tests/test_pattern_detector.py](../../../tests/test_pattern_detector.py), when the list-order precedence rule is characterized, then it is restated here as its own case, because `tests/test_pattern_detector.py` is rewritten in STORY-008 and that rule must survive the rewrite.
- [ ] Given `/query`, when a prompt from the corpus that is blocked today is sent, then the six-outcome regression in [tests/test_query_outcomes_regression.py](../../../tests/test_query_outcomes_regression.py) is untouched and still green.

## Technical Notes

- New file only: `tests/test_pattern_characterization.py`. No production code changes in this commit — that is the point of a characterization story (PRD Section 6.9; the precedent is PRD-009 STORY-001 and PRD-010 STORY-003).
- Cases as a module-level list of `(text, expected_pattern_or_None)` tuples, parametrized. Keep them inline here, not in `tests/corpora/` — the corpora added in STORY-011/012 are about the *new* policy, and mixing them would make the flip set unreadable.
- Do not assert on `SUSPICIOUS_PATTERNS`' contents beyond iterating it; STORY-005 moves that list into the built-in policy and the characterization must survive the move by describing behaviour, not structure.
- The flip set is the whole evidentiary value of this story: PRD Section 11, *Refinement of the brief's criterion*, says the default policy must reproduce today's verdicts **except** the enumerated substring-only matches.
- Skills: none applicable.

## Dependencies

- **Blocked by**: None
- **Blocks**: STORY-002, STORY-008

## PRD Reference

Source: [`PRD-011-pattern-policy/PRD.md`](../../PRDs/PRD-011-pattern-policy/PRD.md) — sections 6.9, 11 (*Refinement of the brief's criterion*), 12 (Phase 1), 15 (Evidence)
