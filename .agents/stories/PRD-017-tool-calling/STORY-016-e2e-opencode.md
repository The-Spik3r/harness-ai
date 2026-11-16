---
id: STORY-016
prd: PRD-017
slug: e2e-opencode
title: "E2E: OpenCode completes a scripted multi-file task; a scripted DROP TABLE is denied and reported"
type: technical
priority: medium
complexity: large
phase: "4 - Real clients and docs"
status: todo
labels: [tests, e2e, clients]
epic_branch: epic/PRD-017-tool-calling
plan: null
report: null
commit: null
depends_on: [STORY-001, STORY-014, STORY-015]
blocks: [STORY-017, STORY-018]
skills: []
created: 2026-11-15
updated: 2026-11-15
---

# STORY-016: E2E: OpenCode completes a scripted multi-file task; a scripted DROP TABLE is denied and reported

## Description

As an integrating developer using OpenCode, I want it to run a real agent task through the harness and to report a denied action instead of crashing, so that I can adopt the harness in agent mode.

## Acceptance Criteria

- [ ] Given a throwaway git repository with two source files, the harness on the stub upstream (STORY-014) with `V1_TOOLS_ENABLED=true` and an action policy file setting the repository as `workspace.roots` and a `shell.allow` with the test command, and OpenCode 2.0.10 configured with the harness as an OpenAI-compatible provider, when OpenCode is run non-interactively on the task, then the scripted reads, edits and test run are executed by OpenCode and both files end with the scripted content.
- [ ] Given that run, when the audit is read, then every row has `ingress='v1'`, `profile='code'`, `has_tool_calls=1` where calls flowed, one `conversation_key`, and an `action_decisions` row per scripted call joined by `audit_id`; no row is a duplicate block.
- [ ] Given a script whose next reply is `bash` with `sqlite3 app.db "DROP TABLE users"`, when OpenCode receives the response, then it executes nothing, prints (or records in its output) the harness note with the reason, and exits or continues without a crash or retry storm; the decision row is `deny` / `sql.ddl`.
- [ ] Given the run, when the report is written, then it records the OpenCode version, the full command line, the provider config used, the request keys OpenCode sent (via the recording proxy), whether it streamed, and anything it needed that the harness had to accept.

## Technical Notes

- Orchestrator note (STORY-001 plan): OpenCode 2.0.10 renamed tools (`bash`→`shell`, `apply_patch`→`patch`, `task`→`subagent`; `read`/`write`/`edit` take `path`); STORY-001 adds them to `BUILT_IN_TOOLS` and `examples/action_policy.yaml`. Its CodeMode tool `execute {code}` stays `tool.unknown` (deny) and must never go in `opaque_tools`; if OpenCode routes calls through `execute` by default, find the config that disables CodeMode and record it.
- Follow PRD-015's E2E stories for structure: `tests/e2e/test_aider.py`, `tests/e2e/_live.py` (live harness, recording proxy, DB guard), marker `e2e`, opt-in with `--run-e2e`.
- OpenCode is installed globally (v2.0.10); do not upgrade it. Its config can live in the throwaway repository (`opencode.json`) or `OPENCODE_CONFIG`; write it there, never in the user's home config. STORY-001's survey note says how it talks to an OpenAI-compatible base URL and which tool names it uses.
- The model name OpenCode sends must be in `MODEL_ALLOWLIST` (and `V1_TOOL_MODELS` if set).
- Outbound OpenRouter fails from the dev machine (PRD-015 Risk 7): the stub is the upstream (D15). If OpenCode needs network for anything else (model catalogue), find the offline setting and record it.
- Run it at least once here and attach the result to the report; the everyday suite must still skip it without `--run-e2e`.
- Skills: none applicable. No UI.

## Dependencies

- **Blocked by**: STORY-001, STORY-014, STORY-015
- **Blocks**: STORY-017, STORY-018

## PRD Reference

Source: [`PRD-017-tool-calling/PRD.md`](../../PRDs/PRD-017-tool-calling/PRD.md) — sections 5 (stories 1, 2), 7 (F11), 11 (MVP), 14 (Risks 1, 2, 4), 15 (D15)
