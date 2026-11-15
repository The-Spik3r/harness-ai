---
id: STORY-003
prd: PRD-016
slug: rule-vocabulary-and-action-permissions
title: Rule ids, operation kinds, the six action permissions and authz.holds()
type: feature
priority: high
complexity: small
phase: "1 - Threat model and vocabulary"
status: done
labels: [backend, rbac, security]
epic_branch: epic/PRD-016-action-policy-rules
plan: .agents/plans/PRD-016-action-policy-rules/completed/STORY-003-rule-vocabulary-and-action-permissions.plan.md
report: .agents/reports/PRD-016-action-policy-rules/STORY-003-rule-vocabulary-and-action-permissions.report.md
commit: 598bb29
depends_on: []
blocks: [STORY-004, STORY-006]
skills: []
created: 2026-11-15
updated: 2026-11-15
---

# STORY-003: Rule ids, operation kinds, the six action permissions and authz.holds()

## Description

As a platform operator, I want action permissions to be ordinary RBAC permissions that `RBAC_ROLES_FILE` can grant, and checked without the `RBAC_ENABLED=false` escape hatch, so that one file says which roles may do what and turning RBAC off never opens every action.

## Acceptance Criteria

- [x] Given `app/services/authz.py`, when imported, then it defines the six constants `PERMISSION_ACTION_SQL_WRITE` … `PERMISSION_ACTION_SECRET_READ` with the values in PRD Section 6.7, an `ACTION_PERMISSIONS` frozenset of exactly those six, and `_KNOWN_PERMISSIONS` contains the original five plus the six.
- [x] Given the built-in `ROLE_PERMISSIONS`, when inspected, then no role (`admin`, `auditor`, `user`) holds any action permission.
- [x] Given an `RBAC_ROLES_FILE` granting `dba` the permission `action:sql:write`, when `authz.load()` runs, then it loads; given one granting `action:sql:writ`, then it raises `AuthzConfigError` naming the permission.
- [x] Given `holds(identity, "action:sql:write")` with `RBAC_ENABLED=false` and a role that does not hold it, when called, then it returns `False` (no bypass); with a role that holds it, then `True`; with a role absent from the matrix, then `False`.
- [x] Given `app/services/action_classifiers/__init__.py`, when imported, then `RuleId` is a `Literal` of exactly the 25 rule ids in PRD Section 6.3, `OperationKind` is `Literal["shell", "sql", "fs_write", "fs_read", "http"]`, `Decision` is `Literal["allow", "flag", "deny"]`, `Classification` is the frozen dataclass of Section 6.2, and `NON_GRANTABLE_RULES` is exactly the ten deny rules of T5.

## Technical Notes

- `holds()` sits beside `authorize()` with a docstring citing PRD-016 D7 and explaining why it does not call `authorize()`. `authorize()` is unchanged.
- `action_classifiers/__init__.py` is pure: no `settings` import (PRD Section 6.12). The rule catalogue's *defaults and grants* belong to STORY-006's built-in policy; this story only names the vocabulary. `Classification.operation` is typed against STORY-004's `Operation`; declare it here with a forward reference or move `Operation` here and re-export it from `action_adapters`, whichever keeps the import graph acyclic.
- Tests: extend `tests/test_authz.py`; new `tests/test_action_vocabulary.py` asserting the 25 ids and the non-grantable set against PRD Section 6.3.
- Comment the constants in the style of the existing PRD-005 block.
- Skills: none applicable. No UI.

## Dependencies

- **Blocked by**: None
- **Blocks**: STORY-004, STORY-006

## PRD Reference

Source: [`PRD-016-action-policy-rules/PRD.md`](../../PRDs/PRD-016-action-policy-rules/PRD.md) — sections 4 (RBAC), 6.2, 6.3, 6.7, 9.2 (T4, T5), 15 (D6, D7)
