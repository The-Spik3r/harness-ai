---
id: STORY-006
prd: PRD-016
slug: action-config-loader
title: "action_config, part 1: ActionPolicy model, built-in policy, get_policy(), digest, both lifespans"
type: feature
priority: high
complexity: medium
phase: "2 - Configuration"
status: done
labels: [backend, config, security]
epic_branch: epic/PRD-016-action-policy-rules
plan: .agents/plans/PRD-016-action-policy-rules/completed/STORY-006-action-config-loader.plan.md
report: .agents/reports/PRD-016-action-policy-rules/STORY-006-action-config-loader.report.md
commit: pending
depends_on: [STORY-003, STORY-004]
blocks: [STORY-007, STORY-009, STORY-011, STORY-012]
skills: []
created: 2026-11-15
updated: 2026-11-15
---

# STORY-006: action_config, part 1: ActionPolicy model, built-in policy, get_policy(), digest, both lifespans

## Description

As a security admin, I want a built-in action policy that denies every dangerous class out of the box and is in force from the first boot, so that a deployment that configures nothing is protected rather than open.

## Acceptance Criteria

- [x] Given `ACTION_POLICY_FILE=""`, when `action_config.load()` runs, then no file is opened (asserted with a path that would fail if read) and `get_policy()` returns `BUILT_IN_POLICY`.
- [x] Given `BUILT_IN_POLICY`, when inspected, then every one of the 25 rules has the default and grant of PRD Section 6.3, the ten non-grantable rules have no grant, the tool mappings are STORY-004's `BUILT_IN_TOOLS`, the protected-path and secret globs are those of Sections 6.3 and 6.6, and `workspace.roots`, `network.allow` and `shell.allow` are empty.
- [x] Given `get_policy()` called before `load()` has ever run, when called, then it returns `BUILT_IN_POLICY` and does not raise (the `pattern_config.get_policy()` contract).
- [x] Given `policy_digest()`, when called twice on the same policy, then it returns the same `sha256:<hex>`; given two policies that differ in one rule's default, then the digests differ.
- [x] Given `app/main.py` and `chat_ui/chat_ui/chat_ui.py`, when the app boots, then `action_config.load()` runs in both lifespans, after `authz.load()`.

## Technical Notes

- New `app/services/action_config.py`, mirroring `pattern_config.py`: `ActionConfigError`, frozen `Rule(default, grant)`, frozen `ActionPolicy` (rules, tools, opaque_tools, shell_allow, network_allow, workspace_roots, secrets), `BUILT_IN_POLICY`, private `_policy`, `get_policy()`, `policy_digest()`, and a `load()` that in this story only handles the empty setting.
- The built-in policy is built from module data through a `_validate(policy)` function that STORY-007 extends into the full file validator, so the floor cannot drift into a shape a file would be refused for (PRD F8).
- Orchestrator decision (STORY-004 plan): the built-in `opaque_tools` is **empty**. The `none` tools of SOURCES.md (OpenCode `todowrite`, `task`, ...; Cline `search_codebase`, ...) are `tool.unknown` (deny) until a deployment names them, which is the D1 floor. State this in the AC2 test.
- Digest: SHA-256 over a canonical JSON of the effective policy (sorted keys), not over file bytes, so comments and key order do not change it.
- Globs are compiled once here (`**` translated by the module), protected-path globs case-insensitive (T6).
- Tests: new `tests/test_action_config.py` (built-in and digest cases); extend the lifespan tests that already assert `pattern_config.load()` runs in both lifespans.
- Skills: none applicable. No UI.

## Dependencies

- **Blocked by**: STORY-003, STORY-004
- **Blocks**: STORY-007, STORY-009, STORY-011, STORY-012

## PRD Reference

Source: [`PRD-016-action-policy-rules/PRD.md`](../../PRDs/PRD-016-action-policy-rules/PRD.md) — sections 4 (Configuration), 6.3, 6.5, 6.12, 7 (F8), 10 (Internal API)
