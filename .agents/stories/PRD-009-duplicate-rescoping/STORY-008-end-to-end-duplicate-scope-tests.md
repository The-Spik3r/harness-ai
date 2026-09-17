---
id: STORY-008
prd: PRD-009
slug: end-to-end-duplicate-scope-tests
title: "End-to-end /query tests for every row of the what-counts table: two users, retry after failure, denial, chaining"
type: technical
priority: high
complexity: medium
phase: "3 - Switch to the key"
status: done
labels: [backend, tests, security]
epic_branch: epic/PRD-009-duplicate-rescoping
plan: .agents/plans/PRD-009-duplicate-rescoping/completed/STORY-008-end-to-end-duplicate-scope-tests.plan.md
report: .agents/reports/PRD-009-duplicate-rescoping/STORY-008-end-to-end-duplicate-scope-tests.report.md
commit: 7302bd9
depends_on: [STORY-007]
blocks: [STORY-009]
skills: []
created: 2026-09-16
updated: 2026-09-17
---

# STORY-008: End-to-end /query tests for every row of the what-counts table: two users, retry after failure, denial, chaining

## Description

As a security admin, I want the rescoped control proven through the real HTTP boundary for every kind of prior row, so that "what counts as a prior query" is one readable test module, not an inference spread across unit tests.

## Acceptance Criteria

- [ ] Given a new `tests/test_duplicate_scope.py`, when it runs, then it has one end-to-end test per row of PRD Section 6.3's table, each driving real `POST /query` requests with bearer tokens (no seeded fakes, except for rows that need a backdated timestamp or a pre-PRD NULL key). Each test asserts both the HTTP outcome and the resulting audit rows.
- [ ] Given PRD Section 5 stories 1–4 and their examples, when the module is read, then each example exists as a named test. The names match the Juan/María scenarios closely enough that a reader of the PRD can find them.
- [ ] Given two users sending the same prompt, when both succeed, then their rows carry **different** `dedup_key` values and the **same** `prompt_hash` (D5: evidence unchanged).
- [ ] Given a same-user repeat after a success, when it is blocked, then the blocked row's `dedup_key` equals the success row's, and `was_duplicate_blocked=1`. A third send is still `BLOCKED` with `first_query_at` = the success, not the blocked row (D3).
- [ ] Given the full suite, when it runs, then everything passes. Given the Section 11 functional-requirement checklist, when each item is checked against a test in this module, STORY-003's module or STORY-002's schema tests, then every item maps to a named test, and the mapping is recorded in the story report.

## Technical Notes

- This module overlaps deliberately with the store-level tests from STORY-004/005/007. Those prove the SQL; this proves the wiring through `require_permission`, the router and `run_query`, which is where a forgotten `identity.user_id` or key would actually break.
- Build two identities the way [tests/test_pii_dedup_isolation.py](../../../tests/test_pii_dedup_isolation.py) does (`insert_user` + `hash_token`). The suspicious-pattern row uses a member of `SUSPICIOUS_PATTERNS`.
- For the chaining and pre-PRD rows, seed with `insert_audit_log` and a backdated `timestamp`. For the pre-PRD case, compute the would-be key and assert the seeded row has `dedup_key=None`.
- Skills: none applicable.

## Dependencies

- **Blocked by**: STORY-007
- **Blocks**: STORY-009

## PRD Reference

Source: [`PRD-009-duplicate-rescoping/PRD.md`](../../PRDs/PRD-009-duplicate-rescoping/PRD.md) — sections 4 (Tests), 5 (stories 1–4), 6.3, 11 (functional requirements), 12 (Phase 3)
