---
id: STORY-014
prd: PRD-016
slug: decision-engine
title: "Decision engine: evaluate(), grants via holds(), most-severe-wins, safe reasons, fail closed"
type: feature
priority: high
complexity: medium
phase: "3 - Classifiers and the engine"
status: todo
labels: [backend, security, rbac]
epic_branch: epic/PRD-016-action-policy-rules
plan: null
report: null
commit: null
depends_on: [STORY-004, STORY-008, STORY-013]
blocks: [STORY-015, STORY-017]
skills: []
created: 2026-11-15
updated: 2026-11-15
---

# STORY-014: Decision engine: evaluate(), grants via holds(), most-severe-wins, safe reasons, fail closed

## Description

As the PRD-017 implementer, I want one pure function that takes a tool call and an identity and returns allow, flag or deny with a reason, so that wiring action policy into the response path is plumbing.

## Acceptance Criteria

- [ ] Given the built-in policy and a `user` identity, when `evaluate` runs on `query` with `DROP TABLE users`, then `decision="deny"`, `rule="sql.ddl"`, `reason="destructive SQL is not permitted: DROP"`, `granted_by=None`; on `SELECT * FROM users WHERE id = 1`, then `allow` / `sql.read`; on an unknown tool, then `deny` / `tool.unknown`.
- [ ] Given a test RBAC matrix with `dba` holding `action:sql:write`, when `DELETE FROM t WHERE id = 3` is evaluated, then `deny` for `user` and `allow` with `granted_by="action:sql:write"` for `dba`; `DELETE FROM t` is `deny` for both; with `RBAC_ENABLED=false`, then `deny` for `dba` too (D7).
- [ ] Given `npm test && rm -rf build` with `npm test` allowlisted, when evaluated, then `deny` reported as `shell.destructive` with both segments' classifications kept; given `shell.unlisted: {default: flag}`, then `make release` is `flag`; given `opaque_tools: {todowrite: allow}`, then `todowrite` is `allow` / `tool.opaque` without classification.
- [ ] Given a classifier monkeypatched to raise, when `evaluate` runs, then it returns `deny` / `tool.malformed` and logs at `ERROR` with the tool name and rule but not the arguments (asserted on the log record).
- [ ] Given every decision the engine can produce, when its `reason` is checked, then it is the rule's fixed template plus the matched fragment of the call and never contains a configured host, root or allowlist entry; every decision carries `policy_digest()` of the policy in force; `evaluate_all` preserves input order.

## Technical Notes

- Orchestrator decision (STORY-013 plan): call `classify_shell(op.target, policy.shell_allow, network_allow=policy.network_allow, secret_env=policy.secrets.env.compiled, secret_files=policy.secrets.files.compiled, protected=policy.protected_paths.compiled, workspace_roots=policy.workspace_roots, source_tool=op.source_tool)`. Its keyword args default to `()`, which silently disables checks, so engine tests MUST assert through `evaluate()` that `cat .env` is `secret.read`, `ls > .git/config` is `fs.write_protected` and `curl evil.com` is `net.unlisted` under the built-in policy.
- Orchestrator note (STORY-011): `classify_sql`/`classify_shell` return tuples; `paths.classify_write`/`classify_read` (and `classify_url`, F5) return a single `Classification`. Normalize in the engine.
- Orchestrator decision (STORY-008 plan): the engine gets the SQL dialect through a getter in `action_config` (validated setting, not an `ActionPolicy` field, so it is not in the digest) and calls `classify_sql(statement, dialect, source_tool=...)`.
- Orchestrator decision (STORY-006 plan): `tool.opaque` carries no rule default; the engine takes its decision from `Opaque.decision` (the per-entry `opaque_tools` value).
- New `app/services/action_policy.py`: `ActionDecision` (PRD Section 6.2), `evaluate(call, identity, policy=None)`, `evaluate_all(calls, identity)`. `policy=None` → `action_config.get_policy()` (a read of in-memory state, not I/O).
- Pipeline: `map_tool_call` (STORY-004) → per operation, the classifier for its kind (`shell` STORY-009/009/012, `sql` STORY-008, `fs_write` / `fs_read` STORY-011/012, `http` STORY-012) → per classification `allow if holds(identity, rule.grant) else rule.default` → severity `deny > flag > allow`, first at that severity in the PRD Section 6.4 order.
- Reason templates: one per rule, in this module, reviewed in the story's report.
- Pure: no `settings` import, no I/O; the import-graph test covers `action_policy`, `action_adapters` and `action_classifiers`.
- Tests: new `tests/test_action_policy.py`.
- Skills: none applicable. No UI.

## Dependencies

- **Blocked by**: STORY-004, STORY-008, STORY-013
- **Blocks**: STORY-015, STORY-017

## PRD Reference

Source: [`PRD-016-action-policy-rules/PRD.md`](../../PRDs/PRD-016-action-policy-rules/PRD.md) — sections 4 (Decision engine), 6.2, 6.4, 6.7, 7 (F7), 9.2 (T4, T9, T11), 10 (Internal API), 11 (Functional requirements), 15 (D9, D10)
