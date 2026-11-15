---
id: STORY-015
prd: PRD-016
slug: action-decisions-table-and-record
title: action_decisions table, indexes, record() and read functions
type: feature
priority: high
complexity: medium
phase: "4 - Evidence"
status: todo
labels: [backend, audit, db]
epic_branch: epic/PRD-016-action-policy-rules
plan: null
report: null
commit: null
depends_on: [STORY-014]
blocks: [STORY-016, STORY-017]
skills: []
created: 2026-11-15
updated: 2026-11-15
---

# STORY-015: action_decisions table, indexes, record() and read functions

## Description

As an auditor, I want every action decision, allowed ones included, stored as one row per tool call with the policy digest that made it, so that the audit shows what was attempted and can be read correctly after the policy changes.

## Acceptance Criteria

- [ ] Given a fresh database and one created before this PRD, when `init_db()` runs, then `action_decisions` exists with the columns of PRD Section 6.10 and both indexes; no existing table is altered; a second `init_db()` is a no-op.
- [ ] Given three `ActionDecision`s (allow, flag, deny) and an identity, when `record(decisions, identity, audit_id=7, session_id="s1")` runs, then three rows are written in one transaction with `audit_id=7`, `session_id="s1"`, the identity's `user_id` and `role`, and three ids are returned in order.
- [ ] Given a decision on arguments longer than 500 characters, when recorded, then `arguments_hash` is `hash_prompt()` of the full string, `arguments_preview` and `target_preview` are the first 500 characters, and `classifications` is a JSON array of `{rule, kind, detail}` for every classification.
- [ ] Given `record(...)` with `audit_id` omitted, when it runs, then the rows store `NULL`; given an insert failure midway, then no row of that batch is written.
- [ ] Given rows for two users, when `list_action_decisions(limit, user_id=None, decision=None)` and `count_action_decisions()` run, then they filter by user and decision, return newest first by `id`, and the counts match per decision.

## Technical Notes

- Orchestrator decision (STORY-012 plan): `Operation.target` for `http` is the whole URL including the query string, which may carry tokens. Store the `action_decisions` target with query and fragment values redacted (keep the keys) and state it in the AC tests.
- `app/db/models.py`: `CREATE_ACTION_DECISIONS_TABLE`, the two index statements, a frozen `ActionDecisionRow` dataclass; comment block in the `usage_daily` style explaining no foreign key and no added-columns mapping (PRD Section 6.10).
- `app/db/database.py`: create in `init_db()`; `insert_action_decisions(rows)` in a single transaction; `list_action_decisions`, `count_action_decisions`.
- New `app/services/action_audit.py`: `record()`; reuse `hash_prompt` and the 500-character preview of `audit_logger`.
- Order by `id`, never by the TEXT timestamp (PRD-006 Section 13, as `chat_messages` does).
- Tests: new `tests/test_action_audit.py`; the `db` marker applies (the libSQL dev-server note: mass fixture errors mean restart the container).
- Skills: none applicable. No UI.

## Dependencies

- **Blocked by**: STORY-014
- **Blocks**: STORY-016, STORY-017

## PRD Reference

Source: [`PRD-016-action-policy-rules/PRD.md`](../../PRDs/PRD-016-action-policy-rules/PRD.md) — sections 4 (Audit), 6.10, 7 (F10), 9.2 (T10), 15 (D8)
