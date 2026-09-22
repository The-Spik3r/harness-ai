---
id: STORY-010
prd: PRD-011
slug: narrowed-counters-and-admin-fields
title: "blocked_suspicious counts blocks only; role and action surfaced in /audit and the console"
type: enhancement
priority: high
complexity: medium
phase: "3 - The pipeline inspects the conversation"
status: todo
labels: [backend, api, audit, admin]
epic_branch: epic/PRD-011-pattern-policy
plan: null
report: null
commit: null
depends_on: [STORY-009]
blocks: [STORY-013]
skills: []
created: 2026-09-22
updated: 2026-09-22
---

# STORY-010: blocked_suspicious counts blocks only; role and action surfaced in /audit and the console

## Description

As a compliance admin, I want a flagged request not counted as a blocked one, and the triggering role visible where I read the audit, so that my security figures stay true and I can tell a careless user from a compromised data source.

## Acceptance Criteria

- [ ] Given `count_blocked_suspicious()` and the admin snapshot query in [app/db/database.py](../../../app/db/database.py), when they run, then both predicates are `suspicious_pattern IS NOT NULL AND (pattern_action IS NULL OR pattern_action = 'block')`.
- [ ] Given one block row, one flag row and one legacy row with `pattern_action IS NULL`, when `/stats` and the admin snapshot are read, then `blocked_suspicious` is 2 — the flag is excluded and the legacy row still counts.
- [ ] Given `AuditQueryEntry` in [app/models/schemas.py](../../../app/models/schemas.py) and the mapping in [app/routers/admin.py](../../../app/routers/admin.py), when `GET /audit` is read, then each entry carries nullable `pattern_role` and `pattern_action` alongside the existing `suspicious_pattern_detected`, which keeps its current meaning of "a pattern was matched" and is therefore true for a flag too.
- [ ] Given the admin console's Register view, when a row with a pattern is rendered, then the triggering role and whether it was a block or a flag are visible, and a row from before this PRD (both fields NULL) renders without an error or a misleading label.
- [ ] Given the snapshot JSON built in `app/db/database.py`, when it is read, then both new fields appear in the per-row object, and the existing reports/admin tests pass with only additive changes.

## Technical Notes

- This is the story that keeps a security number honest. `suspicious_pattern IS NOT NULL` is literally today's definition of "blocked as suspicious" in both the counter and the snapshot; landing STORY-009's flag rows without this change silently reclassifies every flag as a block (PRD Section 6.7, 9.2 T8).
- `NULL` counts as a block deliberately, so no historical row moves and no admin's existing figure changes (PRD Risk 4). Write the test that asserts a legacy NULL row still counts — it is the whole reason the predicate is not simply `= 'block'`.
- `suspicious_pattern_detected` on the admin entry keeps its meaning. Do not narrow it to blocks: it answers "was a pattern matched", which is still exactly what it reports. The new `pattern_action` field is what distinguishes the two cases.
- Admin console work is two nullable fields on an existing row — no new view, no layout change. The `frontend-design` skill does not apply (PRD Section 15, *Skills referenced*).
- Extend `tests/test_stats_router.py`, `tests/test_admin_state.py` / `tests/test_admin_formatting.py` as appropriate, and `tests/test_audit_router.py`. Every modified pre-existing test carries a comment citing PRD-011 D6.
- Skills: none applicable.

## Dependencies

- **Blocked by**: STORY-009
- **Blocks**: STORY-013

## PRD Reference

Source: [`PRD-011-pattern-policy/PRD.md`](../../PRDs/PRD-011-pattern-policy/PRD.md) — sections 6.7 (D6), 7 (F7), 9.2 (T8), 10, 11, 14 (Risk 4)
