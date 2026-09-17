---
id: STORY-007
prd: PRD-009
slug: lookup-matches-on-dedup-key
title: "check_duplicate(user_id, key) and the lookup match on dedup_key, with the pinned contract tests updated"
type: feature
priority: high
complexity: medium
phase: "3 - Switch to the key"
status: done
labels: [backend, database, security]
epic_branch: epic/PRD-009-duplicate-rescoping
plan: .agents/plans/PRD-009-duplicate-rescoping/completed/STORY-007-lookup-matches-on-dedup-key.plan.md
report: .agents/reports/PRD-009-duplicate-rescoping/STORY-007-lookup-matches-on-dedup-key.report.md
commit: c734df9
depends_on: [STORY-005, STORY-006]
blocks: [STORY-008, STORY-010]
skills: []
created: 2026-09-16
updated: 2026-09-17
---

# STORY-007: check_duplicate(user_id, key) and the lookup match on dedup_key, with the pinned contract tests updated

## Description

As a PRD-010 implementer, I want the duplicate check to take the key rather than a prompt, so that the conversation-shaped key is what the control actually enforces and multi-turn only has to pass more turns to `dedup_key`.

## Acceptance Criteria

- [ ] Given `find_duplicate_timestamp(user_id: str, dedup_key: str, since: str)`, when it is read, then its SQL is exactly PRD Section 6.3's: `user_id = ? AND dedup_key = ? AND timestamp >= ?` plus the three flag predicates from STORY-004, `ORDER BY timestamp ASC LIMIT 1`. `prompt_hash` no longer appears in it.
- [ ] Given `check_duplicate(user_id: str, key: str) -> DuplicateCheckResult`, when `run_query` calls it, then it passes the key computed in STORY-006. `check_duplicate` itself no longer calls `hash_prompt`, and it still raises `DuplicateCheckError` on `StorageError` (the router's 500 is unchanged).
- [ ] Given `EXPLAIN QUERY PLAN` on the lookup against a `temp_db`, when it is inspected, then it uses `idx_audit_logs_dedup`. The assertion follows `test_find_user_by_token_hash_uses_the_index` in [tests/test_db.py](../../../tests/test_db.py).
- [ ] Given the contract tests in PRD Section 6.5, when this story lands, then each is updated in place with a PRD-009 citation:
  - `test_check_duplicate_public_contract_is_stable` pins `["user_id", "key"]`
  - the `hash_prompt` census returns to `duplicate_checker.py: 1`
  - `test_hash_prompt_only_ever_receives_raw_text` drops the second `duplicate_checker` entry
  - the spies adapt their signature only
  - [tests/test_duplicate_checker.py](../../../tests/test_duplicate_checker.py) is re-seeded with `user_id` + `dedup_key`, keeping every window/boundary/whitespace/earliest case
  - [tests/test_audit_session_id.py](../../../tests/test_audit_session_id.py)'s "global 24h exact-match" docstring is corrected
- [ ] Given a pre-PRD row (`dedup_key` NULL) for the same user and prompt within 24h, when the prompt is sent, then it reaches the model (D6, T8, pinned by a test naming Risk 3). The regression module and every non-contract assertion in `test_query_router.py` / `test_integration.py` pass unmodified.

## Technical Notes

- No outcome assertion may change here (PRD Section 11 quality indicators). If one has to, the change is wrong. Stop and re-check the key wiring.
- A row whose `dedup_key` is NULL never matches (`NULL = ?` is never true), so D6 needs no code, only the pinning test. If the user later chooses Risk 3's alternative, it's a follow-up story, not a change here.
- After this story, `prompt_hash` is written but no longer read by the duplicate control. It remains the evidence column for `/audit`, the admin console and `test_two_instance_smoke.py`. Do not remove or re-mean it (D5).
- Skills: none applicable.

## Dependencies

- **Blocked by**: STORY-005, STORY-006
- **Blocks**: STORY-008, STORY-010

## PRD Reference

Source: [`PRD-009-duplicate-rescoping/PRD.md`](../../PRDs/PRD-009-duplicate-rescoping/PRD.md) — sections 4 (Lookup, Pipeline & logging, Tests), 6.3, 6.5, 10 (internal API), 11, 14 (Risks 3, 5), 15 (D5, D6)
