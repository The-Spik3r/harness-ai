---
story: STORY-005
prd: PRD-023
plan: .agents/plans/PRD-023-mcp-and-skills/completed/STORY-005-policy-mcp-sections-and-rule.plan.md
epic_branch: epic/PRD-023-mcp-and-skills
commit: 5ea6493
status: COMPLETE
completed: 2026-11-22
---

# Implementation Report — STORY-005: Action policy `mcp_tools` / `mcp_opaque_tools` sections and the `tool.not_in_skill` rule

**Plan**: `.agents/plans/PRD-023-mcp-and-skills/completed/STORY-005-policy-mcp-sections-and-rule.plan.md`
**Epic Branch**: `epic/PRD-023-mcp-and-skills`
**Commit**: `5ea6493`

## Summary

`ActionPolicy` gained frozen, doubly-`MappingProxyType` `mcp_tools` / `mcp_opaque_tools` tables (empty in the built-in policy). Each server's table goes through the existing `_validate_tools` / `_validate_opaque_tools` with node `mcp_tools.<server>` (new `node` kwargs whose defaults reproduce the old messages). Server ids must fullmatch `[a-z0-9][a-z0-9-]{0,31}`; an empty server table is refused (T7); a tool in both tables of one server is refused. The spec keys are optional (`_OPTIONAL_SPEC_KEYS`), so PRD-016 specs stay valid. The digest has `mcp_*` keys only when non-empty. The new non-grantable deny rule `tool.not_in_skill` brings the vocabulary to 26 rules / 11 non-grantable, with its `_SUBJECTS` entry. `evaluate()` and adapters are untouched.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Rule id + non-grantable set | `app/services/action_classifiers/__init__.py` | done |
| 2 | `_SUBJECTS` entry | `app/services/action_policy.py` | done |
| 3 | Fields, validators, parser, digest, built-in rule | `app/services/action_config.py` | done |
| 4 | Count assertions 25->26, 10->11 | `tests/test_action_vocabulary.py`, `tests/test_action_config.py` | done |
| 5 | New MCP + rule tests (20 test cases incl. parametrised) | `tests/test_action_config.py` | done |
| 6 | Sweep: two further count-style census assertions | `tests/test_action_policy.py`, `tests/test_action_corpus.py` | done |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| Targeted tests (config, vocabulary, policy, audit, corpus, adapters, untouched_app) | 178 passed |
| Targeted tests (network, paths, secrets, shell, sql) | 1252 passed |
| DB-backed files (`test_actions_view`, `test_admin_actions`) | not run: libSQL dev server down, Docker Desktop not running |
| E2E (load YAML with both sections, `MCP_ENABLED` false/true) | covered by `test_mcp_sections_validate_with_mcp_disabled_or_enabled` |
| Full suite | GitHub CI on push (user decision) |

## Digest continuity (one-time change)

Adding `tool.not_in_skill` changes every policy's digest once. Verified before and after: the pre-change digest of the built-in policy (`sha256:394f1f0a...a204`) and of `examples/action_policy.yaml` (`sha256:4b54b163...5b43`) are reproduced exactly by the new canonical dict with the new rule removed and no `mcp_*` keys. Digests now: built-in `sha256:a392e1a7...cb82`.

## Deviations from Plan

- Two PRD-016 census assertions needed a one-line PRD-023 D7 adjustment the plan did not list, because they require every `RULE_IDS` member to be produced by a sweep/corpus that cannot produce the gateway-only rule until STORY-006: `tests/test_action_policy.py::test_every_reason_is_the_fixed_template_plus_the_calls_fragment` (`produced == set(RULE_IDS) - {"tool.not_in_skill"}`) and `tests/test_action_corpus.py::test_every_rule_id_is_reported_by_some_file` (same exclusion). STORY-006 should add a gateway case and may drop the exclusions.
- Test names mentioning "25" / "ten" kept (renaming needs `_DELIBERATELY_SUPERSEDED_TESTS`); each edited assertion carries a PRD-023 comment.
- Docs (`docs/features.md`, `docs/roadmap.md`: 25 / ten) left for STORY-021.

## Tests Written

`tests/test_action_config.py`: load and expose + immutability, each section changes the digest, no `mcp_*` keys when empty (old-shape digest), order insensitivity, copies, accepted shapes, non-mapping sections, bad server ids (4), empty server table (both sections), tool in both tables, invalid mapping node names, non-string tool names, unknown/missing spec keys still refused, `MCP_ENABLED` false/true, rule vocabulary, grant refused / default allowed.

## Acceptance Criteria

- [x] AC1 sections validated, exposed, in digest: `test_mcp_sections_load_and_are_exposed`, `test_each_mcp_section_alone_changes_the_digest`
- [x] AC2 refusals name file and node: the `test_file_refuses_*mcp*` set
- [x] AC3 `tool.not_in_skill`, 26 / 11, subject: `test_action_vocabulary.py` counts, `test_tool_not_in_skill_is_a_non_grantable_deny_rule`
- [x] AC4 validates with `MCP_ENABLED` false: `test_mcp_sections_validate_with_mcp_disabled_or_enabled`
