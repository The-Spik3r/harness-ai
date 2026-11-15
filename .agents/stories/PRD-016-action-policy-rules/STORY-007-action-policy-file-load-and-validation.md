---
id: STORY-007
prd: PRD-016
slug: action-policy-file-load-and-validation
title: "action_config, part 2: ACTION_POLICY_FILE load, per-id rule merge, wholesale sections, validation, sample file"
type: feature
priority: high
complexity: medium
phase: "2 - Configuration"
status: done
labels: [backend, config, security]
epic_branch: epic/PRD-016-action-policy-rules
plan: .agents/plans/PRD-016-action-policy-rules/completed/STORY-007-action-policy-file-load-and-validation.plan.md
report: .agents/reports/PRD-016-action-policy-rules/STORY-007-action-policy-file-load-and-validation.report.md
commit: 7e765b7
depends_on: [STORY-005, STORY-006]
blocks: [STORY-008]
skills: []
created: 2026-11-15
updated: 2026-11-15
---

# STORY-007: action_config, part 2: ACTION_POLICY_FILE load, per-id rule merge, wholesale sections, validation, sample file

## Description

As a platform operator, I want to set my workspace, allowlists and rollout modes in a file that is validated at startup, so that I can configure the policy without a code change and a typo stops the boot instead of reopening anything.

## Acceptance Criteria

- [ ] Given a file whose `rules:` sets only `shell.unlisted: {default: flag}`, when loaded, then that rule is `flag` and every other rule keeps its built-in default and grant (per-id merge, D12).
- [ ] Given a file with a `tools:` section, when loaded, then the built-in tool mappings are replaced wholesale; the same holds for `shell.allow`, `network.allow`, `secrets` and `workspace.roots`; a section absent from the file keeps the built-in one.
- [ ] Given a file breaking any one validation rule in PRD Section 9.3, when loaded, then `ActionConfigError` names the file, the node and the rule, with one test per rule, including: an unknown rule id, a bad decision, an unknown permission, a grant on each of the ten non-grantable rules, `tools: {}`, an unknown `kind`, a relative workspace root, a name in both `tools` and `opaque_tools`, a bad network entry, a `shell.allow` entry containing `;`, and a duplicate YAML key.
- [ ] Given a file that fails validation after a valid one was loaded, when `load()` runs, then the previously loaded policy and its digest are still in force.
- [ ] Given `examples/action_policy.yaml` (PRD Section 6.6), when a test loads it, then it loads, and its digest differs from the built-in digest.

## Technical Notes

- Orchestrator decision (STORY-006 plan): `tool.opaque` is `Rule(default=None, grant=None)` (PRD 6.3 "(per entry)"); refuse a `rules: tool.opaque` entry in the file. `protected_paths` is built-in only (no file section). Extend STORY-006's `_validate(source, spec)`; its design decision 8 lists the checks left to this story.
- Extend `app/services/action_config.py`: read with `strict_yaml.safe_load` (STORY-005); `_fail(path, *parts)` and `_allowed()` message helpers copied in shape from `pattern_config`; `_policy` rebound as the last statement of `load()`.
- Required versus optional keys: every section is optional; inside a rule both `default` and `grant` are optional (an absent one keeps the built-in value); inside a tool mapping both `kind` and `target` are required.
- Orchestrator decision (STORY-004 plan): a tool mapping also accepts the optional keys `default`, `format` (`text` | `command` | `patch`) and `extra_targets` defined by `action_adapters.ToolMapping`; the `target` key-path syntax (`[]` arrays, `|` alternative spellings) is STORY-004's. Build each mapping through `ToolMapping(...)` and wrap its `ToolMappingError` in `ActionConfigError` naming the file and the node (same seam as `PatternCompileError`). `examples/action_policy.yaml` writes `apply_patch` with `format: patch`.
- Network entries: exact host, `*.`-wildcard host or IP literal via `ipaddress`; anything else is an error. `shell.allow` entries may be multi-token; refuse an empty one or one containing `;`, `&`, `|`, `$` or a backtick.
- The `ACTION_SQL_DIALECT` cross-check is added by STORY-008, where `sqlglot` arrives.
- New `examples/action_policy.yaml`, with comments explaining the `rules:` merge exception (PRD Risk 7).
- Tests: extend `tests/test_action_config.py`, one function per validation rule.
- Skills: none applicable. No UI.

## Dependencies

- **Blocked by**: STORY-005, STORY-006
- **Blocks**: STORY-008

## PRD Reference

Source: [`PRD-016-action-policy-rules/PRD.md`](../../PRDs/PRD-016-action-policy-rules/PRD.md) — sections 6.6, 9.2 (T5, T7, T13), 9.3, 11 (Configuration criteria), 14 (Risk 7), 15 (D12, D13)
