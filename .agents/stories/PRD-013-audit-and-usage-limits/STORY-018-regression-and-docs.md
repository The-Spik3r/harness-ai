---
id: STORY-018
prd: PRD-013
slug: regression-and-docs
title: "Regression sweep, README and .env docs"
type: technical
priority: medium
complexity: medium
phase: "4 - See it and prove it"
status: done
labels: [tests, docs]
epic_branch: epic/PRD-013-audit-and-usage-limits
plan: .agents/plans/PRD-013-audit-and-usage-limits/completed/STORY-018-regression-and-docs.plan.md
report: .agents/reports/PRD-013-audit-and-usage-limits/STORY-018-regression-and-docs.report.md
commit: af85840
depends_on: [STORY-013, STORY-014, STORY-015, STORY-016, STORY-017]
blocks: []
skills: []
created: 2026-10-04
updated: 2026-10-20
---

# STORY-018: Regression sweep, README and .env docs

## Description

As a platform operator, I want the documentation to state what is now limited, recorded and refused, and proof that nothing else moved, so that I can upgrade knowing what changes for my users.

## Acceptance Criteria

- [ ] Given the full suite, when it runs, then it is green, and `git diff main` shows no changed assertion in `test_query_outcomes_regression.py` rows 1-7, `test_chat_outcomes_regression.py`, `test_duplicate_scope.py` or `test_pii_characterization.py`; every other modified pre-existing test carries a comment citing PRD-013 and the decision.
- [ ] Given the README, when it is read, then it has a *Usage limits* section covering the two limits, their defaults, role maps and per-user overrides, the fixed window, the possible budget overshoot, the BYOK rule, fail-closed gate and fail-open charge, and the measured round trips from STORY-017.
- [ ] Given the README's API reference, when it is read, then it documents the usage-limit `BLOCKED` body, the eight new `/audit` fields with their meanings (including the three limits of `conversation_key`) and the three new `/stats` fields.
- [ ] Given the README's environment table and `.env.example`, when they are read, then both list `USAGE_LIMITS_ENABLED`, `USAGE_DAILY_TOKEN_BUDGET`, `USAGE_REQUESTS_PER_MINUTE` and `BREAK_GLASS_INGRESSES`, and the `ADMIN_TOKEN` row says it is refused on `/v1`.
- [ ] Given the README's *Duplicate detection scope*, *The database is a hard dependency of every request* and roadmap sections, when they are read, then the PRD-013 note reads as shipped, the per-request round trips are updated, and the roadmap lists this PRD under shipped.

## Technical Notes

- The pre-PRD was already marked `promoted` and linked in `pre-prds/README.md` when the PRD was created; do not redo it.
- State the defaults as starting points, as PRD Section 9.3 does, and say that an upgraded deployment gets limits without opting in.
- README claims about latency must match STORY-017's report figure for figure.
- Document `manage_users.py set-limits` beside the existing user-management commands.
- Mass fixture errors in the suite mean restart the libSQL dev container, not bisect code.
- Skills: none applicable. No UI surface changes in this story.

## Dependencies

- **Blocked by**: STORY-013, STORY-014, STORY-015, STORY-016, STORY-017
- **Blocks**: None

## PRD Reference

Source: [`PRD-013-audit-and-usage-limits/PRD.md`](../../PRDs/PRD-013-audit-and-usage-limits/PRD.md) — sections 7 (F18), 9.3, 10, 11 (Quality indicators), 12 (Phase 4)
