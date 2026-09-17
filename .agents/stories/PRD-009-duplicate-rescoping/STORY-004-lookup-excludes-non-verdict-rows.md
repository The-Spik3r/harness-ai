---
id: STORY-004
prd: PRD-009
slug: lookup-excludes-non-verdict-rows
title: "Duplicate lookup ignores failed, policy-denied and duplicate-blocked rows"
type: bug
priority: high
complexity: medium
phase: "2 - Rescope the lookup"
status: todo
labels: [backend, database, security]
epic_branch: epic/PRD-009-duplicate-rescoping
plan: null
report: null
commit: null
depends_on: [STORY-001]
blocks: [STORY-005]
skills: []
created: 2026-09-16
updated: 2026-09-16
---

# STORY-004: Duplicate lookup ignores failed, policy-denied and duplicate-blocked rows

## Description

As an end user, I want a retry after an upstream error or a policy denial to go through, and a blocked resend not to extend the window, so that a duplicate block only ever means "this already got a real answer (or a content-check verdict) in the last 24 hours".

## Acceptance Criteria

- [ ] Given `find_duplicate_timestamp` in [app/db/database.py](../../../app/db/database.py), when it is read, then its `WHERE` adds `success = 1 AND was_duplicate_blocked = 0 AND denied_permission IS NULL` to the existing `prompt_hash` and `timestamp` predicates. `ORDER BY timestamp ASC LIMIT 1` is kept, and the signature is unchanged.
- [ ] Given an `OpenRouterError` send followed by the same prompt, and separately an input `PiiRedactorError` send followed by the same prompt, when the retry is posted to `/query`, then it reaches the model (`200 SUCCESS`).
- [ ] Given a model-allowlist denial, a BYOK denial and a missing-`query:submit` denial (each a `success=1` row with `denied_permission`), when the same prompt is sent by an identity that passes authorization, then it reaches the model. Given a suspicious-pattern block row, when the same prompt is sent again, then it is still `BLOCKED` as a duplicate (D1: content checks count).
- [ ] Given a success at −25h and a duplicate-blocked row at −2h, when the same prompt is sent, then it reaches the model. Given a success at −10h and a blocked row at −2h, then `first_query_at` is the success's timestamp.
- [ ] Given the STORY-001 characterization tests for failures, denials and chaining, when this story lands, then each assertion is **flipped in place** (not deleted, not moved) with a comment citing PRD-009 D1 or D3 and this story. The cross-user characterization is untouched, and `tests/test_query_outcomes_regression.py` passes unmodified.

## Technical Notes

- This is the defect fix the pre-PRD opened with. It deliberately still matches on `prompt_hash` (PRD Section 12, Phase 2), so it can ship and be reviewed alone.
- The flag predicates hit the existing `NOT NULL DEFAULT` columns. `denied_permission` is nullable, so the predicate must be `IS NULL`, not `= ''`.
- Add store-level tests to [tests/test_duplicate_checker.py](../../../tests/test_duplicate_checker.py) seeding each row kind: `success=False`, `denied_permission="query:submit"`, `was_duplicate_blocked=True`, `suspicious_pattern="ignore previous instructions"`. The existing window/boundary/whitespace/earliest tests there must still pass unmodified.
- The output-redaction failure arm (`success=False` after the model answered) is also excluded. That is accepted per PRD T6/Risk 4; add one test so it's pinned, not incidental.
- Skills: none applicable.

## Dependencies

- **Blocked by**: STORY-001
- **Blocks**: STORY-005

## PRD Reference

Source: [`PRD-009-duplicate-rescoping/PRD.md`](../../PRDs/PRD-009-duplicate-rescoping/PRD.md) — sections 4 (Lookup), 5 (stories 1, 4), 6.3, 6.4, 7 (F4), 9.2 (T3–T6), 11, 12 (Phase 2)
