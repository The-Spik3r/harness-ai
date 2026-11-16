---
story: STORY-007
prd: PRD-016
plan: .agents/plans/PRD-016-action-policy-rules/completed/STORY-007-action-policy-file-load-and-validation.plan.md
epic_branch: epic/PRD-016-action-policy-rules
commit: 7e765b7
status: COMPLETE
completed: 2026-11-15
---

# Implementation Report — STORY-007: action_config, part 2: ACTION_POLICY_FILE load, per-id rule merge, wholesale sections, validation, sample file

**Plan**: `.agents/plans/PRD-016-action-policy-rules/completed/STORY-007-action-policy-file-load-and-validation.plan.md`
**Epic Branch**: `epic/PRD-016-action-policy-rules`
**Commit**: `7e765b7`

## Summary

`action_config.load()` now reads `ACTION_POLICY_FILE` for real, replacing STORY-006's interim fail-closed branch. It reads the file as UTF-8 and catches `OSError` and `UnicodeDecodeError`. It parses with `strict_yaml.safe_load` (D13). A new `_parse_document` checks the document shape and the keys at every level. It merges `rules:` per rule id over `_BUILT_IN_RULES` (D12): a present rule overrides only the fields it states, and `grant: null` removes a grant. It builds each `tools:` entry through `ToolMapping(...)` and wraps any `ToolMappingError` as `ActionConfigError` with the `tools: '<name>'` node. A present section replaces the built-in section wholesale, and an absent one keeps it. The result goes through `_validate`, which now also checks three things on every policy, the built-in one included (F8): `workspace.roots` must be absolute (a lexical check that gives the same answer on every OS), `network.allow` entries (an IP literal, an exact host, or a `*.` wildcard over at least two labels), and `shell.allow` entries (not empty, and none of `; & | $` backtick `< > ( )` or a line break). `_policy` is rebound only as the last statement, so a failed load leaves the previous policy and its digest in force. Every error starts with `ACTION_POLICY_FILE '<path>': `, followed by the node and the rule.

New `examples/action_policy.yaml` reproduces PRD 6.6, adds `OPENROUTER_*` to `secrets.env`, and carries header comments on the two replacement rules (Risk 7).

Built-in digest before and after the change: `sha256:52b50e196e79706cbffd5dd2771ed4aa90beac22984d284ae5b872d53c229e23` both times. Sample-file digest: `sha256:60a357181c351eedd61dfce64ec25ee0a80d13d7cd71976dd3ea692e5e7c6e69`.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | `_validate` content checks (roots, network entries, shell operators) | `app/services/action_config.py` | ✅ |
| 2 | File parser: `_check_keys`, `_mapping`, `_parse_rules`, `_parse_tools`, `_parse_section`, `_parse_document` | `app/services/action_config.py` | ✅ |
| 3 | Real `load()`; module, `ActionConfigError`, `_validate` and `load` docstrings | `app/services/action_config.py` | ✅ |
| 4 | Sample file | `examples/action_policy.yaml` | ✅ |
| 5 | Tests | `tests/test_action_config.py` | ✅ |
| 6 | Targeted regression | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ OK |
| Frontend lint | N/A (no frontend) |
| `tests/test_action_config.py` alone | ✅ 202 passed |
| Targeted set (`test_action_config`, `test_main`, `test_chat_ui_startup_guard`, `test_strict_yaml`, `test_untouched_app`) | ✅ 271 passed, 0 failed, 0 skipped (127s) |
| Full suite | Deferred to orchestrator (user decision) |
| E2E | ✅ 4/4: backend import OK; built-in digest unchanged; the sample loads with `Rule(default='flag', grant='action:shell:exec')` and digest `sha256:60a3…6e69`; a sample copy with a second `rules:` raises `ActionConfigError: ACTION_POLICY_FILE '…/dup.yaml': file: is not valid YAML: … found duplicate key 'rules' (first defined on line 53)` |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/services/action_config.py` | UPDATE | +374/-35 |
| `examples/action_policy.yaml` | CREATE | +77 |
| `tests/test_action_config.py` | UPDATE | +634/-16 |
| `.agents/PRDs/PRD-016-action-policy-rules/PRD.md` | UPDATE (orchestrator edit, lines 318 and 322) | +2/-2 |

The orchestrator's PRD 6.6 edit is committed with this story: line 318 adds `OPENROUTER_*` to the sample, and line 322 states the per-field rule merge.

## Deviations from Plan

- The orchestrator's decisions are applied: per-field merge (plan decision 5, now matching PRD 6.6); `OPENROUTER_*` in the sample; the wider shell-operator set; **single-label `*.` wildcards refused** (the plan had accepted them). `*.com` and `*.localhost` fail with "a '*.' wildcard must name at least two labels after '*.' … a top-level-domain wildcard opens egress to the whole domain".
- Extra tests beyond the plan's list: `test_file_refuses_a_null_default`, `test_file_refuses_a_list_value_that_is_not_a_list` (a bare `allow:`), `test_file_refuses_a_directory_as_the_file`, a bare `grant:` case in `test_grant_null_removes_a_grant`, a UNC root in the accepted roots, and `test_file_refuses_a_single_label_wildcard`.
- `test_load_reads_no_file_when_action_policy_file_unset` also patches `action_config.Path` now. This is an addition, not a changed assertion, and it is commented. The STORY-006 assertions are unchanged.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_action_config.py` | 46 new test functions (merge ×4, wholesale/absent/empty/tool-options/digest-order ×5, one per Section 9.3 rule ×35, keep-previous ×1, sample ×1). The test file now has 202 tests in total |

## Acceptance Criteria

- [x] AC 1, per-id merge: `test_rules_merge_per_id_keeping_every_other_rule`, plus `test_a_rule_grant_alone_keeps_the_built_in_default`, `test_grant_null_removes_a_grant` and `test_the_merge_base_is_the_built_in_table_not_the_previous_file`
- [x] AC 2, wholesale sections, absent ones kept: `test_a_present_section_replaces_the_built_in_one` (tools, shell, network, secrets, workspace) and `test_an_absent_section_keeps_the_built_in_one`
- [x] AC 3, one test per Section 9.3 rule: the `test_file_refuses_*` functions (unknown rule id, bad decision, unknown permission, a grant on each of the 10 non-grantable rules, `tools: {}`, unknown `kind`, relative root, mapped and opaque, bad network entry, `;` in `shell.allow`, duplicate key, and the others)
- [x] AC 4, a failed load keeps the previous policy and digest: `test_a_failed_load_keeps_the_previous_file_policy_and_digest`
- [x] AC 5, the sample loads and its digest differs from the built-in one: `test_examples_action_policy_yaml_loads`
