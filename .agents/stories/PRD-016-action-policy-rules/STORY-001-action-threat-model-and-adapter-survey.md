---
id: STORY-001
prd: PRD-016
slug: action-threat-model-and-adapter-survey
title: Action threat model and adapter survey (OpenCode, Cline, Aider) with SOURCES.md
type: spike
priority: high
complexity: small
phase: "1 - Threat model and vocabulary"
status: done
labels: [security, research, docs]
epic_branch: epic/PRD-016-action-policy-rules
plan: .agents/plans/PRD-016-action-policy-rules/completed/STORY-001-action-threat-model-and-adapter-survey.plan.md
report: .agents/reports/PRD-016-action-policy-rules/STORY-001-action-threat-model-and-adapter-survey.report.md
commit: 322067d
depends_on: []
blocks: [STORY-004]
skills: []
created: 2026-11-15
updated: 2026-11-15
---

# STORY-001: Action threat model and adapter survey (OpenCode, Cline, Aider) with SOURCES.md

## Description

As the PRD-016 implementer, I want the real tool names and argument keys of OpenCode, Cline and Aider recorded with their source, and the action threat model written down, so that the built-in adapter mappings are facts rather than guesses and every later story tests against the same threats.

## Acceptance Criteria

- [ ] Given OpenCode's current tool definitions, when the survey runs, then `tests/corpora/actions/SOURCES.md` lists each tool PRD Section 4 names (`bash`, `write`, `edit`, `patch`, `read`, `webfetch`, `glob`, `grep`, `list`) with its exact name, the argument key that carries the target, the client version or commit, and the file/URL of the schema; any tool that differs from the PRD is listed under "Corrections to PRD Section 4".
- [ ] Given Cline's current tool definitions, when the survey runs, then the same is recorded for `execute_command`, `write_to_file`, `replace_in_file`, `read_file`, `list_files`, `search_files`, `browser_action`, plus the MCP tools (`use_mcp_tool`, `access_mcp_resource`), which are recorded as `tool.unknown` by design.
- [ ] Given Aider, when the survey runs, then `SOURCES.md` states with a source whether any Aider mode emits OpenAI `tool_calls`; if one does, its mapping is listed for STORY-004; if none does, the PRD assumption "Aider needs no adapter" is confirmed in writing.
- [ ] Given the PRD's threat table (Section 9.2, T1–T13), when the threat model is written, then `.agents/spikes/PRD-016-action-policy-rules/threat-model.md` maps every threat to the rule(s) in Section 6.3 that answer it and to the corpus group (synthetic or evasion) that will prove it, and lists any threat with no rule as an open finding.
- [ ] Given the spike is complete, when the PRD is reread, then any correction found is applied to PRD Sections 4 and 15 (Assumptions) in the same commit, and the PRD's `updated` date is bumped.

## Technical Notes

- Research only: no `app/` code changes. Output files: `tests/corpora/actions/SOURCES.md` (new directory) and `.agents/spikes/PRD-016-action-policy-rules/threat-model.md`.
- Follow the provenance style of `tests/corpora/agent_prompts/SOURCES.md` (PRD-011 STORY-011).
- Record argument key casing exactly (`filePath` vs `path`); STORY-004 maps by exact key.
- Also record whether a tool can name several paths in one call (OpenCode `patch`, Cline `replace_in_file`): PRD F1 yields one `fs_write` per path.
- Record which clients send absolute and which send relative paths; it backs PRD D11 and the README's OpenCode setup step.
- Record the target argument key used by common database tools (`query`, `execute_sql`, `run_sql`) for the generic SQL mapping.
- Skills: none applicable. No UI.

## Dependencies

- **Blocked by**: None
- **Blocks**: STORY-004

## PRD Reference

Source: [`PRD-016-action-policy-rules/PRD.md`](../../PRDs/PRD-016-action-policy-rules/PRD.md) — sections 4 (Operations and adapters), 9.2, 15 (Assumptions to verify in STORY-001)
