---
id: STORY-009
prd: PRD-011
slug: flag-arm-and-audit-columns
title: "Flag arm, and pattern_role / pattern_action audit columns"
type: feature
priority: high
complexity: medium
phase: "3 - The pipeline inspects the conversation"
status: todo
labels: [backend, audit, database, security]
epic_branch: epic/PRD-011-pattern-policy
plan: null
report: null
commit: null
depends_on: [STORY-008]
blocks: [STORY-010, STORY-012]
skills: []
created: 2026-09-22
updated: 2026-09-22
---

# STORY-009: Flag arm, and pattern_role / pattern_action audit columns

## Description

As a security admin, I want a hit in a tool result recorded and the request allowed to continue, so that indirect injection is visible in the audit with the role that carried it instead of being invisible.

## Acceptance Criteria

- [ ] Given [app/db/models.py](../../../app/db/models.py), when it is read, then `pattern_role TEXT` and `pattern_action TEXT` are declared **both** in `CREATE_AUDIT_LOGS_TABLE` and in `AUDIT_LOGS_ADDED_COLUMNS`, and `AuditLog` carries both as `Optional[str] = None`. Given a database created before this story, when `init_db()` runs, then both columns are added and no existing row is backfilled.
- [ ] Given a blocking hit, when the row is written, then `pattern_role` is the role of the matched message and `pattern_action='block'`; the response body is still byte-identical to today's.
- [ ] Given a `tool` flag under the `code` profile, when `run_conversation` runs, then one row is written at step 5 with `suspicious_pattern` set, `pattern_role='tool'`, `pattern_action='flag'`, `success=True`, explicit `session_id` and non-NULL `dedup_key`, **and execution continues**: redaction runs, `call_openrouter` is called, and a second row records the successful exchange.
- [ ] Given a conversation with several flags, when the row is written, then it records the **first** flag in walk order and no more; given a conversation with both a flag and a later block, then one block row is written and the flag is not recorded (PRD Section 6.7).
- [ ] Given `log_query`, when the flag and block arms call it, then `pattern_role` and `pattern_action` are passed explicitly at every call site that has them, alongside the already-required `session_id` and `dedup_key`.

## Technical Notes

- The flag arm is the first place in this pipeline that writes an audit row and then continues. Put it exactly where the block is — step 5, before redaction and before the upstream call — so a flagged request that later fails upstream leaves two rows rather than one row trying to say both things (PRD Section 6.1).
- Column convergence: both the `CREATE` declaration and the added-columns entry, per the comment already in `app/db/models.py` — listing a column in only one of them makes every new deployment ALTER its own brand-new table. Both are nullable `TEXT` with no default, like `session_id` and `dedup_key`.
- `pattern_action IS NULL` means "block" for every row written before this PRD. Nothing is backfilled — the same choice PRD-009 made for `dedup_key`. STORY-010 encodes that in the counters; do not change any counter here.
- Two flags in one conversation cannot both be recorded: `audit_logs` has one `suspicious_pattern` column and this PRD adds no list column. A second table is PRD-013's territory (PRD Section 6.7).
- Extend `tests/test_query_pipeline_patterns.py` (flag arm proceeds, ordering rules) and `tests/test_db.py` (convergence, and the existing rule that a NOT NULL added column needs a default — these two are nullable, so it does not bite).
- Skills: none applicable.

## Dependencies

- **Blocked by**: STORY-008
- **Blocks**: STORY-010, STORY-012

## PRD Reference

Source: [`PRD-011-pattern-policy/PRD.md`](../../PRDs/PRD-011-pattern-policy/PRD.md) — sections 4 (Audit), 6.1, 6.4 (D4), 6.7 (D6), 6.9, 7 (F6, F7), 9.2 (T2), 11
