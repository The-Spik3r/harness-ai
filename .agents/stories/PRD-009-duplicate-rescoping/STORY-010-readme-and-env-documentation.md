---
id: STORY-010
prd: PRD-009
slug: readme-and-env-documentation
title: "README documents the rescoped control, its trade-offs and the resolved multi-turn blocker; .env.example confirmed unchanged"
type: technical
priority: medium
complexity: small
phase: "4 - Regress and document"
status: todo
labels: [docs, security]
epic_branch: epic/PRD-009-duplicate-rescoping
plan: null
report: null
commit: null
depends_on: [STORY-007, STORY-009]
blocks: []
skills: []
created: 2026-09-16
updated: 2026-09-16
---

# STORY-010: README documents the rescoped control, its trade-offs and the resolved multi-turn blocker; .env.example confirmed unchanged

## Description

As a security admin, I want the weakened and strengthened cases written down where operators read, with their mitigations, so that the rescoping is a decision I can review and not a regression I discover.

## Acceptance Criteria

- [ ] Given [README.md](../../../README.md), when it is read, then the Features table's *Duplicate blocking* row says per-user, exact-match, rolling 24h, and a short "Duplicate detection scope" note (under Features or Security) states:
  - what counts as a prior query: successes and suspicious-pattern blocks
  - what does not: failures, policy denials, duplicate blocks, other users' rows, pre-upgrade rows
  - trade-off T1 (one repeat per account) and its owner, PRD-013
  - the one-off post-upgrade gap T8
- [ ] Given the *Multi-turn context* section, when it is read, then it no longer names duplicate detection as the blocker. It states that the key is defined over a conversation and that multi-turn is now blocked only on the pipeline (PRD-010). The *OpenAI-compatible endpoint* bullet asking "what gets hashed" is answered: the last user turn plus a hash of the preceding turns, per user.
- [ ] Given the sentence in *The database is a hard dependency of every request* claiming that a duplicate-check storage failure "lets the query through", when this story lands, then it is corrected to the tested behaviour (500, fail-closed), citing `test_duplicate_check_storage_failure_returns_500`, per PRD Appendix *Observed discrepancy*.
- [ ] Given [.env.example](../../../.env.example) and [app/config.py](../../../app/config.py), when they are checked, then no setting was added by this epic and none is needed. The story report records this explicitly, and `.env.example` is untouched.
- [ ] Given every anchor and relative link added or changed, when they are followed, then each resolves (for example `#multi-turn-context`). [pre-prds/PRE-PRD-009-duplicate-rescoping.md](../../../pre-prds/PRE-PRD-009-duplicate-rescoping.md) reads `status: promoted` with its `prd:` path set, and the full suite is green (README-reading tests such as [tests/test_reports_service.py](../../../tests/test_reports_service.py) unaffected).

## Technical Notes

- Keep the README voice: concrete, states the reason, no marketing. The threat table lives in PRD Section 9.2. The README gets the condensed operator-facing version and a link to the PRD, not a copy.
- Do not edit the roadmap checkbox for *Multi-turn context*; it is still unshipped.
- Skills: none applicable. `frontend-design` does not cover documentation.

## Dependencies

- **Blocked by**: STORY-007, STORY-009
- **Blocks**: None

## PRD Reference

Source: [`PRD-009-duplicate-rescoping/PRD.md`](../../PRDs/PRD-009-duplicate-rescoping/PRD.md) — sections 4 (Documentation), 5 (story 8), 7 (F7), 9.2, 9.3, 15 (Observed discrepancy)
