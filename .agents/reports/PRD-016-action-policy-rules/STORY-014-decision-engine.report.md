---
story: STORY-014
prd: PRD-016
plan: .agents/plans/PRD-016-action-policy-rules/completed/STORY-014-decision-engine.plan.md
epic_branch: epic/PRD-016-action-policy-rules
commit: pending
status: COMPLETE
completed: 2026-11-15
---

# Implementation Report — STORY-014: Decision engine: evaluate(), grants via holds(), most-severe-wins, safe reasons, fail closed

**Plan**: `.agents/plans/PRD-016-action-policy-rules/completed/STORY-014-decision-engine.plan.md`
**Epic Branch**: `epic/PRD-016-action-policy-rules`
**Commit**: `pending`

## Summary

New `app/services/action_policy.py`: `ActionDecision`, `evaluate(call, identity, policy=None)` and `evaluate_all(calls, identity, policy=None)`. The pipeline:

1. Map the call with `action_adapters.map_tool_call`.
2. Turn `Unknown` / `Malformed` / `Opaque` into one `tool.*` classification each. Classify each `Operation` through the classifier module for its kind. The shell call is the STORY-013 orchestrator's call, verbatim.
3. Decide each classification: `allow` when `authz.holds(identity, rule.grant)`, otherwise `rule.default`. `tool.opaque` takes `Opaque.decision`.
4. Fold with `deny > flag > allow`. The first classification at the maximum `(severity, lifted)` is reported.
5. Build `reason` from a fixed subject per rule, a fixed verdict per decision and the call's `detail`.
6. Stamp `policy_digest` on every decision.

Any exception between mapping and the fold becomes a hard `deny` / `tool.malformed`. It is logged once at `ERROR` with the tool name (`%r`) and the exception type only: no arguments, no exception text, no traceback.

`action_config` gains `get_sql_dialect()` and `get_max_argument_characters()`, two getters read at call time, so the engine never names `settings`.

## Orchestrator decisions applied

1. AC 2 is read the T4 way. RBAC off grants nothing under the built-in matrix. Under a test matrix, `dba` keeps its explicit grant.
   - The orchestrator corrected the story's AC 2 wording (line 32). That edit is included in this commit.
2. An opaque tool records one `Classification("tool.opaque", None, name)`.
3. A raise is a hard `deny` / `tool.malformed`, whatever the configured default. A test pins that `{tool.malformed: {default: allow}}` still denies on a raise.
4. `reason` is stored by STORY-015. The orchestrator's note in `STORY-015-*.md` is included in this commit.
5. The reason for oversized arguments names the cap: "arguments exceed N characters".
6. **Refinement of D9.** Among `allow`s, a classification that a grant lifted outranks a plain `allow`.
   - Example: `SELECT 1; DELETE FROM t WHERE id = 3` for a role holding `action:sql:write` reports `sql.write` with `granted_by="action:sql:write"`, not `sql.read` with `granted_by=None`.
   - For `flag` and `deny` the rule is exactly D9 ("first at the most severe level"), because a grant only ever yields `allow`.
7. The getters, the `evaluate`/`evaluate_all` signatures and the purity test without the subprocess settings census are as the plan describes.

The orchestrator's edit to `STORY-018-*.md` (the PowerShell `Env:` note) is staged in this commit too.

## Reason templates (for review)

`reason = f"{subject} {verdict}"`, followed by `f": {detail}"` when the detail is non-empty.

The verdicts:

| Decision | Verdict |
|---|---|
| `allow` | is permitted |
| `flag` | is permitted and flagged for review |
| `deny` | is not permitted |

The subjects:

| Rule | Subject | Rule | Subject |
|---|---|---|---|
| `sql.read` | read-only SQL | `fs.read` | reading a file |
| `sql.write` | SQL that changes data | `fs.write_in_workspace` | writing inside the workspace |
| `sql.unscoped_write` | SQL that changes every row | `fs.write_outside_workspace` | writing outside the workspace |
| `sql.ddl` | destructive SQL | `fs.write_protected` | writing a protected path |
| `sql.dcl` | SQL that changes permissions | `net.allowlisted` | a request to an allowlisted host |
| `sql.unparsed` | SQL that cannot be parsed | `net.unlisted` | a request to a host that is not allowlisted |
| `shell.allowlisted` | an allowlisted command | `net.unparsed` | a URL that cannot be parsed |
| `shell.unlisted` | a command that is not allowlisted | `secret.read` | reading a secret |
| `shell.destructive` | a destructive command | `tool.unknown` | an unknown tool |
| `shell.pipe_to_interpreter` | piping into an interpreter | `tool.opaque` | an opaque tool |
| `shell.inline_interpreter` | inline interpreter code | `tool.malformed` | a tool call that cannot be read |
| `shell.package_install` | installing packages | | |
| `shell.service_control` | controlling services | | |
| `shell.unclassifiable` | a command that cannot be classified | | |

The details:

- For classifier rules, the classifier's own detail is used unchanged.
- For `tool.unknown` and `tool.opaque`, the detail is the tool name, cut to 64 characters.
- For a `Malformed` result, the detail is `Malformed.detail`.
- For the boundary's `tool.malformed`, the detail is the fixed `classification failed`.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | `get_sql_dialect()`, `get_max_argument_characters()`, docstrings | `app/services/action_config.py` | done |
| 2 | The engine | `app/services/action_policy.py` | done |
| 3 | Getter tests | `tests/test_action_config.py` | done |
| 4 | Engine suite G1-G8 | `tests/test_action_policy.py` | done |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | OK |
| Frontend lint | n/a (no frontend) |
| Targeted tests: `test_action_policy.py`, `test_action_config.py`, `test_action_vocabulary.py`, `test_action_adapters.py`, `test_untouched_app.py` | 826 passed, 0 failed, 0 skipped (3.28s) |
| E2E probe (plan Task 2 Validate) | `deny` / `sql.ddl` / `destructive SQL is not permitted: DROP` |
| Full suite | deferred to orchestrator (user decision) |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/services/action_policy.py` | CREATE | +360 |
| `tests/test_action_policy.py` | CREATE | +~715 |
| `app/services/action_config.py` | UPDATE | +31/-2 |
| `tests/test_action_config.py` | UPDATE | +36 |
| `.agents/plans/PRD-016-action-policy-rules/completed/STORY-014-decision-engine.plan.md` | CREATE (archived plan) | |
| `.agents/stories/PRD-016-action-policy-rules/STORY-014-decision-engine.md` | UPDATE (AC 2 wording by the orchestrator; status/plan/report/commit) | |
| `.agents/stories/PRD-016-action-policy-rules/STORY-015-action-decisions-table-and-record.md` | UPDATE (orchestrator note) | +1 |
| `.agents/stories/PRD-016-action-policy-rules/STORY-018-evasion-corpus.md` | UPDATE (orchestrator note) | +1 |
| `.agents/PRDs/PRD-016-action-policy-rules/index.md` | REGENERATE | |

## Deviations from Plan

1. **The secret grant test (G7) uses the `read` tool rather than `bash cat ~/.aws/credentials`.** `cat` of a secret classifies as `[secret.read, shell.unlisted]`, so granting only `action:secret:read` still leaves `shell.unlisted`'s deny. The plan expected `allow` there, which would have been wrong.
   - `test_a_grant_on_one_rule_does_not_lift_another` pins the `bash` behaviour (deny with one grant).
   - With both `action:secret:read` and `action:shell:exec` the call is `allow`, reported as `secret.read`: both classifications are lifted, so the first one wins.
2. **The cross-operation test (G7) passes `shell_allow=("ls",)`.** Under the built-in policy, `ls` is itself `shell.unlisted` (deny), and the first deny is reported. A second test pins that D9 case as well.
3. **Small additions beyond the plan:**
   - `evaluate(None, ...)` fails closed.
   - `evaluate_all` resolves the policy once.
   - A classifier that returns `tool.opaque` fails closed.
   - The mapped operations are kept on a boundary failure.
   - The tool-name detail is capped.
4. **The engine imports `Classification` and `Decision` from `action_classifiers`, but not `RULE_IDS`,** which it does not need. The purity test pins the literal import lines.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_action_policy.py` | 63 tests in G1-G8: built-in user decisions, grants via `holds()`, RBAC-off over every grantable rule, the lifted-allow refinement, the shell keyword wiring (behavioural and spy), the AC 3 shell, flag and opaque cases, the fail-closed boundary over 7 raisers with log-record assertions, reason/digest/order sweep covering all 25 rule ids, shape/`repr`, malformed input, dialect wiring, purity, no I/O |
| `tests/test_action_config.py` | `test_get_sql_dialect_reads_the_setting_at_call_time`, `test_get_max_argument_characters_reads_the_setting_at_call_time`, `test_the_sql_dialect_is_not_in_the_digest` |

## Acceptance Criteria

- [x] **AC 1.**
  - DROP gives `deny` / `sql.ddl` with the exact reason and `granted_by=None`.
  - A SELECT gives `allow` / `sql.read`.
  - An unknown tool gives `deny` / `tool.unknown`.
  - Tests: `test_drop_table_is_denied_as_ddl_with_the_prd_reason`, `test_a_scoped_select_is_allowed_as_read`, `test_an_unknown_tool_is_denied`.
- [x] **AC 2.**
  - `DELETE FROM t WHERE id = 3` is `deny` for `user` and `allow` with the grant for `dba`.
  - `DELETE FROM t` is `deny` for both.
  - With RBAC off, no grant comes from the bypass.
  - Tests: `test_scoped_delete_is_denied_for_user_and_granted_for_dba`, `test_unscoped_delete_is_denied_for_both`, `test_rbac_off_grants_nothing_under_the_built_in_matrix` (9 rules × 3 roles), `test_rbac_off_keeps_an_explicit_grant`.
- [x] **AC 3.**
  - `npm test && rm -rf build` gives `shell.destructive`, and both classifications are kept.
  - A `flag` default gives `flag`.
  - An opaque tool is decided without reading its arguments.
  - Tests: `test_an_allowlisted_head_does_not_hide_a_destructive_segment`, `test_a_flag_default_flags`, `test_an_opaque_tool_takes_its_entry_decision_without_reading_arguments`.
- [x] **AC 4.**
  - A raise gives `deny` / `tool.malformed`.
  - One `ERROR` record carries the tool name and the rule, with no arguments, no marker and no `exc_info`.
  - Tests: `test_a_raise_is_denied_as_malformed_and_logged_without_arguments` (7 raisers).
- [x] **AC 5.**
  - Every reason is the template plus the call's fragment, with no sentinel config value in it.
  - The digest is the policy in force.
  - Input order is preserved.
  - Tests: `test_every_reason_is_the_fixed_template_plus_the_calls_fragment`, `test_the_digest_is_the_policy_in_force`, `test_evaluate_all_preserves_input_order`.
- [x] **Binding.**
  - `cat .env` gives `secret.read`, `ls > .git/config` gives `fs.write_protected`, and `curl evil.com` gives `net.unlisted`, all through `evaluate()`.
  - Tests: `test_embedded_shell_checks_are_wired_through_evaluate`, `test_classify_shell_gets_the_policy_values`.
- [x] **Purity.**
  - Tests: `test_action_policy_stays_pure`, `test_evaluate_does_no_io`.
