---
id: STORY-007
prd: PRD-023
slug: mcp-config-loader
title: "`mcp_config`: servers, skills, aliases, cross-validation, digest, loaded in both lifespans"
type: feature
priority: high
complexity: large
phase: "2 - Vocabulary and configuration"
status: todo
labels: [mcp, config, security, rbac]
epic_branch: epic/PRD-023-mcp-and-skills
plan: null
report: null
commit: null
depends_on: [STORY-004, STORY-005]
blocks: [STORY-010, STORY-011, STORY-015, STORY-017]
skills: []
created: 2026-11-22
updated: 2026-11-22
---

# STORY-007: `mcp_config`: servers, skills, aliases, cross-validation, digest, loaded in both lifespans

## Description

As a platform operator, I want `MCP_CONFIG_FILE` loaded and cross-validated at startup with errors that name the file and node, so that a typo never exposes a tool to the wrong role.

## Acceptance Criteria

- [ ] Given each Section 9.3 `MCP_CONFIG_FILE` rule (unknown key, server id pattern, url scheme / `allow_insecure`, `auth.type`, unset/empty `token_env`/`value_env`, forbidden header names, `timeout_seconds`/`max_result_bytes` range, skill id pattern, empty `tools`, malformed skill tool, unmapped skill tool, bad `requires`, `skill:<id>` granted for an undefined skill, role holding a skill without its `requires` (O2), bad alias prefix, duplicate keys, and an `mcp_tools` server absent from the MCP config), when a failing file loads, then `MCPConfigError` names the file and node (one test per rule; PRD Story 8's exact message for the unmapped tool)
- [ ] Given `MCP_ENABLED=false`, when `mcp_config.load()` runs, then it opens no file (asserted with a path that fails if opened); given `MCP_ENABLED=true` and an empty `MCP_CONFIG_FILE`, then startup fails
- [ ] Given a valid config, when loaded, then `get_config()`, `held_skills(identity)` (via `authz.holds`, no `RBAC_ENABLED` bypass) and `visible_tools(identity) -> Mapping[server, frozenset[tool]]` return the expected sets; with RBAC off and the built-in matrix, visible is empty
- [ ] Given `mcp_config_digest()`, when a skill version changes the digest changes, and when only a credential's env value changes it does not; credential names are included and values never appear in the digest, logs or errors
- [ ] Given `app/main.py` and the chat UI's mounted lifespan, when both start, then `mcp_config.load()` runs after `authz.load()` and `action_config.load()`; `examples/mcp.yaml` plus example policy sections load in a test

## Technical Notes

- Orchestrator decision (STORY-002): Cline hashes a tool id longer than 55 characters (or one with characters outside `[a-zA-Z0-9_-]`) to `<sanitized[:55]>_<sha1(raw)[:8]>`, so its `/v1` alias does not resolve (the PRD 6.8 limitation stands; there is no reverse map in the MVP). `mcp_config.load()` logs one `WARNING` per skill tool whose `<server>__<tool>` exceeds 55 characters, naming the skill and the tool. It is a warning, not an error. Vectors: `tests/corpora/mcp/SOURCES.md` (Clients).
- New `app/services/mcp_config.py`, YAML via `strict_yaml.safe_load`; frozen dataclasses for the config model; `MCPConfigError` in the `ActionConfigError` shape.
- Both lifespans: `app/main.py` and `chat_ui/chat_ui/chat_ui.py` `register_lifespan_task` (PRD-007). Follow how `action_config.load()` is wired there.
- Credentials: resolve env values at load time and keep them only in memory for `mcp_upstream` (STORY-010); never in `repr`, digest or errors.
- Server ids never contain `_`, so `<server>__<tool>` splits at the first `__` (O7).

## Dependencies

- **Blocked by**: STORY-004, STORY-005
- **Blocks**: STORY-010, STORY-011, STORY-015, STORY-017

## PRD Reference

Source: [`PRD-023/PRD.md`](../../PRDs/PRD-023-mcp-and-skills/PRD.md) — Sections 4 (Skills and configuration), 6.6, 6.11, 9.3, F3, D5, D6, O2, O7, User Story 8
