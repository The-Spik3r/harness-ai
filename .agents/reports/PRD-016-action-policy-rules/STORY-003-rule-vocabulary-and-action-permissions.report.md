---
story: STORY-003
prd: PRD-016
plan: .agents/plans/PRD-016-action-policy-rules/completed/STORY-003-rule-vocabulary-and-action-permissions.plan.md
epic_branch: epic/PRD-016-action-policy-rules
commit: 598bb29
status: COMPLETE
completed: 2026-11-15
---

# Implementation Report — STORY-003: Rule ids, operation kinds, the six action permissions and authz.holds()

**Plan**: `.agents/plans/PRD-016-action-policy-rules/completed/STORY-003-rule-vocabulary-and-action-permissions.plan.md`
**Epic Branch**: `epic/PRD-016-action-policy-rules`
**Commit**: `598bb29`

## Summary

`app/services/authz.py` gains the six `action:*` permission constants (PRD-016 Section 6.7), an `ACTION_PERMISSIONS` frozenset, the six folded into `_KNOWN_PERMISSIONS` so `RBAC_ROLES_FILE` can grant them through the existing unknown-permission check (F9), a D6 comment on `ROLE_PERMISSIONS` (no built-in role holds one, `admin` included; the dict is unchanged), and `holds(identity, permission) -> bool`, a matrix lookup with no `RBAC_ENABLED` bypass (D7). `authorize()`, `authorize_model()` and `load()` are unchanged.

New pure package `app/services/action_classifiers/` whose `__init__.py` holds the closed vocabulary: `OperationKind` (five kinds), `Decision`, `RuleId` (the 25 ids of Section 6.3, in table order), the tuple forms `RULE_IDS` / `OPERATION_KINDS` / `DECISIONS`, `NON_GRANTABLE_RULES` (the ten of T5), and the frozen `Operation` and `Classification` dataclasses of Section 6.2. It imports only `dataclasses` and `typing`.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Action permission constants, `ACTION_PERMISSIONS`, `_KNOWN_PERMISSIONS`, D6 comment | `app/services/authz.py` | ✅ |
| 2 | `holds()` after `authorize()` | `app/services/authz.py` | ✅ |
| 3 | Vocabulary package | `app/services/action_classifiers/__init__.py` | ✅ |
| 4 | AC1-AC4 tests | `tests/test_authz.py` | ✅ |
| 5 | AC5 + purity tests | `tests/test_action_vocabulary.py` | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ `OK` |
| Frontend lint | n/a (no `frontend/` in this repo) |
| Chat UI import | n/a (`chat_ui/` not touched) |
| Story tests (`test_authz.py`, `test_action_vocabulary.py`) | ✅ 79 passed |
| Targeted set (plan's Validation: the two above + `test_rbac.py`, `test_main.py`, `test_query_pipeline_break_glass.py::test_ingress_break_glass_is_not_an_rbac_permission`, `test_untouched_app.py`) | ✅ 124 passed, 0 failed, 0 skipped (91 s) |
| Full suite | Deferred to orchestrator (user decision) |
| E2E | No route/UI/startup change; the "a roles file granting an action permission boots" property is `test_load_accepts_an_action_permission_grant`, through the same `authz.load()` both lifespans call |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/services/authz.py` | UPDATE | +50/-1 |
| `app/services/action_classifiers/__init__.py` | CREATE | +131 |
| `tests/test_authz.py` | UPDATE | +127 |
| `tests/test_action_vocabulary.py` | CREATE | +154 |
| `.agents/stories/PRD-016-action-policy-rules/STORY-004-tool-call-adapter-layer.md` | UPDATE | +1 (orchestrator's note: `Operation`/`OperationKind` live in `action_classifiers`; STORY-004 re-exports them) |

## Deviations from Plan

None in the code. Orchestrator decisions applied as given: `Operation` and `OperationKind` live in `action_classifiers/__init__.py` (STORY-004 note committed with this story); `none` is not an `OperationKind` (stated in its comment); the T9 `tool.malformed` trigger is stated in the comment above `RuleId`; `RULE_IDS`, `OPERATION_KINDS`, `DECISIONS` kept; expected values hardcoded in the tests. One small addition to the plan's test list: the "built-in roles are exactly admin/auditor/user" check is its own test (`test_built_in_roles_are_exactly_the_three_parametrized`) rather than folded into the parametrized AC2 test. No pre-existing test assertion was modified or renamed.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_authz.py` | `test_action_permission_constants_match_prd_016_section_6_7`, `test_known_permissions_are_the_original_five_plus_the_six`, `test_no_built_in_role_holds_an_action_permission[admin/auditor/user]`, `test_built_in_roles_are_exactly_the_three_parametrized`, `test_load_accepts_an_action_permission_grant`, `test_load_refuses_a_misspelled_action_permission`, `test_holds_is_false_for_a_role_without_the_permission` (6 permissions x user/admin x RBAC off/on), `test_holds_is_true_for_a_role_with_the_permission[RBAC off/on]`, `test_holds_is_false_for_a_role_absent_from_the_matrix[RBAC off/on]`, `test_holds_does_not_inherit_authorize_rbac_off_bypass`, `test_holds_reads_the_matrix_load_installed` |
| `tests/test_action_vocabulary.py` | `test_rule_id_is_exactly_the_25_ids_of_prd_section_6_3`, `test_every_rule_id_is_class_dot_name`, `test_operation_kind_is_the_five_of_section_6_2`, `test_decision_is_allow_flag_deny`, `test_non_grantable_rules_are_exactly_the_ten_of_t5`, `test_classification_is_the_frozen_dataclass_of_section_6_2`, `test_operation_is_the_frozen_dataclass_of_section_6_2`, `test_type_hints_resolve`, `test_action_classifiers_package_stays_pure` |

## Acceptance Criteria

- [x] AC1: six constants with the Section 6.7 values, `ACTION_PERMISSIONS` of exactly those six, `_KNOWN_PERMISSIONS` = original five + six (`test_action_permission_constants_match_prd_016_section_6_7`, `test_known_permissions_are_the_original_five_plus_the_six`)
- [x] AC2: no built-in role holds an action permission (`test_no_built_in_role_holds_an_action_permission[*]`)
- [x] AC3: `dba` granted `action:sql:write` loads; `action:sql:writ` raises `AuthzConfigError` naming the permission and the file (`test_load_accepts_an_action_permission_grant`, `test_load_refuses_a_misspelled_action_permission`)
- [x] AC4: `holds()` False without the permission with RBAC off (no bypass), True with it, False for a role absent from the matrix (`test_holds_is_*`, `test_holds_does_not_inherit_authorize_rbac_off_bypass`)
- [x] AC5: `RuleId` = the 25 ids, `OperationKind` = five, `Decision` = three, `Classification` frozen dataclass of 6.2, `NON_GRANTABLE_RULES` = the ten of T5 (`tests/test_action_vocabulary.py`)
