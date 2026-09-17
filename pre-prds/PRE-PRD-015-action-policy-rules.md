---
target_prd: PRD-015
slug: action-policy-rules
title: Action policy rules
status: draft
prd:
depends_on: [PRD-011]
blocks: [PRD-016]
estimated_stories: 12-15
created: 2026-09-16
---

# Action policy rules

## Problem

Coding agents do not only produce text; they call tools that write files, run commands and query databases. The harness's checks are text-level: a prompt can pass the injection filter and still yield a tool call that drops a table (README, *MCP servers and agent skills*). Enabling tool calling (PRD-016) without an enforcement point for actions would make the harness a pass-through for exactly the operations it exists to control.

The README ([Action policy rules](../README.md#action-policy-rules)) already defines the intent: a deny-by-default rule set evaluated **before** a tool call leaves the harness, in the position the pattern check holds for prompts.

## Goal

Every tool call the model emits is classified and allowed, denied or flagged by per-deployment, per-role rules before the client receives it — with the decision audited as rigorously as an allowed call.

## Proposed scope

**In** (rule classes from the README)

| Class | Denies |
|---|---|
| Destructive SQL | `DROP`, `TRUNCATE`, `ALTER`, `GRANT`, `DELETE`/`UPDATE` without `WHERE` |
| Shell execution | `rm -rf`, `curl … \| sh`, package installs, service restarts |
| Filesystem writes | Outside an allowlisted workspace; `.env`, credentials, CI config |
| Network egress | Hosts outside an allowlist |
| Secret access | Env vars / files matching secret patterns |

- Rule file format and startup validation (reusing PRD-011's loading mechanism).
- Tool-call parser: map a `tool_call` (name + JSON args) to a class and a target. Known tool schemas for OpenCode/Cline/Aider as adapters; unknown tools → default decision.
- Decision engine: allow / deny / flag, per role via the RBAC matrix in [authz.py](../app/services/authz.py).
- Audit columns for action decisions.
- Tested against synthetic `tool_calls` — does not need PRD-014 or PRD-016 to exist.

**Out**
- Executing or sandboxing tools (the harness never runs them).
- Tool-call streaming.
- MCP server hosting (roadmap *MCP servers and agent skills*).

## Open decisions

| # | Question | Proposed default |
|---|---|---|
| D1 | Unknown tool name | Deny by default, per the README's deny-by-default intent; allowlist per deployment. |
| D2 | SQL classification: regex or parser? | Parser (e.g. `sqlglot`) — regex is trivially evaded. |
| D3 | Shell classification | Tokenize and match command heads + dangerous flag combos; anything with pipes to an interpreter denied. |
| D4 | Response on deny | Replace the tool call with an assistant message carrying the reason (PRD-016 decides the wire shape). |
| D5 | Obfuscation (base64, `eval`, chained commands) | Deny when the parser cannot classify with confidence. |

## Evidence

- README: "These rules are per-deployment configuration, which makes *Configurable, per-deployment pattern lists* a prerequisite."
- README: "RBAC … the same `DELETE` can already be denied for one role and allowed for another."

## Success criteria

- A synthetic `DROP TABLE users` tool call is denied and audited; a `SELECT` is allowed.
- `rm -rf /`, `curl x | sh`, a write to `.env` are denied.
- A role with explicit permission is allowed the same `DELETE … WHERE`.
- Evasion corpus (quoting, base64, `;`-chaining, `$(…)`) does not produce an allow.
- Invalid rule file stops startup.

## Risks

| Risk | Mitigation |
|---|---|
| Classifiers are evadable | Deny-on-uncertainty (D5); evasion corpus grows with findings. |
| Every agent names tools differently | Adapter per client; unknown → deny. |
| Over-blocking makes agents unusable | Flag mode per class for rollout; audit data drives promotion to deny. |

## Tentative story breakdown

1. Action threat model
2. Rule file format and validation
3. Tool-call parser and client adapters
4. SQL classifier
5. Shell classifier
6. Filesystem path rules
7. Network egress rules
8. Secret access rules
9. Decision engine with RBAC per role
10. Audit columns for decisions
11. Synthetic tool-call corpus
12. Evasion corpus
13. Admin console: action decisions view
14. README and `.env` docs
