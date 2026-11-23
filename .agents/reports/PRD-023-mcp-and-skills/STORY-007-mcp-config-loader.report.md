---
story: STORY-007
prd: PRD-023
plan: .agents/plans/PRD-023-mcp-and-skills/completed/STORY-007-mcp-config-loader.plan.md
epic_branch: epic/PRD-023-mcp-and-skills
commit: pending
status: COMPLETE
completed: 2026-11-22
---

# Implementation Report - STORY-007: mcp_config loader

## Summary

New `app/services/mcp_config.py`: frozen config model, strict YAML load of `MCP_CONFIG_FILE` (only when `MCP_ENABLED`), every PRD 9.3 rule plus three approved extras (userinfo in URL, non-string `version`, duplicate alias prefixes), credential env resolution kept out of repr/digest, cross-validation against the action policy and role matrix, `held_skills` / `visible_tools` over `authz.holds`, `split_tool`, `upstream_auth_headers`, `mcp_config_digest`, the 55-character warning. Loaded in both lifespans after `action_config.load()`.

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| `tests/test_mcp_config.py` | 67 passed |
| `tests/test_authz.py tests/test_untouched_app.py tests/test_action_config.py` (-k "not lifespan") | 363 passed |
| `tests/test_main.py` lifespan, `tests/test_chat_ui_startup_guard.py` | NOT RUN: Docker Desktop down, libSQL unreachable. New tests collect and compile; CI covers them |
| Full suite | GitHub CI on push (user decision) |

## Deviations from Plan

- Absent `v1_aliases` means no aliases (orchestrator correction); the example declares both prefixes.
- `examples/mcp_action_policy.yaml` holds only the two MCP sections (sections left out keep the built-ins); `target: "files[].path"` validates.

## Acceptance Criteria

- [x] AC1 each 9.3 rule and the Story 8 message: `test_rule[*]`, `test_unmapped_tool_message_is_story_8_exact`
- [x] AC2 disabled opens no file; enabled + empty fails: `test_disabled_opens_no_file`, `test_enabled_without_file_fails`
- [x] AC3 accessors; RBAC off sees nothing: `test_held_skills_and_visible_tools`, `test_rbac_off_*`
- [x] AC4 digest and secrecy: `test_digest_*`, `test_secret_value_appears_nowhere`
- [x] AC5 both lifespans, examples load: `test_examples_load`; lifespan tests written, not run locally
