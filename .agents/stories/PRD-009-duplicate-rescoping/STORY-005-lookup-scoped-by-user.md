---
id: STORY-005
prd: PRD-009
slug: lookup-scoped-by-user
title: "Duplicate lookup scoped by the authenticated user_id"
type: bug
priority: high
complexity: small
phase: "2 - Rescope the lookup"
status: todo
labels: [backend, database, security]
epic_branch: epic/PRD-009-duplicate-rescoping
plan: null
report: null
commit: null
depends_on: [STORY-004]
blocks: [STORY-007]
skills: []
created: 2026-09-16
updated: 2026-09-16
---

# STORY-005: Duplicate lookup scoped by the authenticated user_id

## Description

As an end user, I want my prompt not to be blocked by someone else's identical prompt, so that a common question works for everyone who asks it, and nobody can poison a colleague's window by sending their prompt first.

## Acceptance Criteria

- [ ] Given `find_duplicate_timestamp(user_id: str, prompt_hash: str, since: str)` and `check_duplicate(user_id: str, prompt: str)`, when they are read, then the lookup adds `user_id = ?` and `run_query` passes `identity.user_id`, the credential-resolved id and never the request body's.
- [ ] Given María's successful send of a prompt, when Juan sends the identical prompt within 24h, then Juan's request reaches the model. Given Juan then sends it again, then Juan is `BLOCKED` with `first_query_at` equal to **his own** success's timestamp, not María's.
- [ ] Given `test_check_duplicate_public_contract_is_stable`, when this story lands, then it pins `["user_id", "prompt"]` (both `str`, no defaults) with a comment citing PRD-009 Section 6.5 and noting that STORY-007 changes the second parameter to `key`. The spies wrapping `check_duplicate` in [tests/test_pii_dedup_isolation.py](../../../tests/test_pii_dedup_isolation.py), [tests/test_query_router.py](../../../tests/test_query_router.py) and [tests/test_query_pipeline_authorization.py](../../../tests/test_query_pipeline_authorization.py) change their wrapper signature only, and every assertion in those tests is unchanged.
- [ ] Given the STORY-001 cross-user characterization test, when this story lands, then it is flipped in place with a comment citing PRD-009 T1/T2 and this story.
- [ ] Given the full suite, then `tests/test_query_outcomes_regression.py` and [tests/test_integration.py](../../../tests/test_integration.py) pass unmodified.

## Technical Notes

- The interim signature `(user_id, prompt)` is deliberate. `user_id` is placed first so STORY-007 only swaps the second parameter, which keeps the spy churn in each touched test to one line.
- [tests/test_duplicate_checker.py](../../../tests/test_duplicate_checker.py) `_seed` hard-codes `user_id="juan@empresa.com"`. Callers now pass the same id, and add a "different user seeded → not duplicate" store-level test.
- Existing single-user tests that relied on the global scope with *different* users (search for seeds whose `user_id` differs from the identity that then sends) must be found and reasoned about individually. Don't bulk-edit them.
- The `idx_audit_logs_dedup` index isn't used yet (still `prompt_hash`), which is acceptable for the interim (PRD Section 12).
- Skills: none applicable.

## Dependencies

- **Blocked by**: STORY-004
- **Blocks**: STORY-007

## PRD Reference

Source: [`PRD-009-duplicate-rescoping/PRD.md`](../../PRDs/PRD-009-duplicate-rescoping/PRD.md) — sections 4 (Lookup), 5 (story 2), 6.5, 7 (F5), 9.1, 9.2 (T1, T2), 12 (Phase 2)
