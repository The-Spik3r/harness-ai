---
id: STORY-017
prd: PRD-017
slug: e2e-cline
title: "E2E: Cline completes the same task through the harness"
type: technical
priority: medium
complexity: large
phase: "4 - Real clients and docs"
status: done
labels: [tests, e2e, clients]
epic_branch: epic/PRD-017-tool-calling
plan: .agents/plans/PRD-017-tool-calling/completed/STORY-017-e2e-cline.plan.md
report: .agents/reports/PRD-017-tool-calling/STORY-017-e2e-cline.report.md
commit: pending
depends_on: [STORY-001, STORY-014, STORY-016]
blocks: [STORY-018]
skills: []
created: 2026-11-15
updated: 2026-11-16
---

# STORY-017: E2E: Cline completes the same task through the harness

## Description

As an integrating developer using Cline, I want it to run the same agent task through the harness, so that both target agents are proven, not just one.

## Acceptance Criteria

- [ ] Given the STORY-016 repository and task, a Cline-specific action policy file (`tools:` mapping Cline's tools per STORY-001, `workspace.roots`, `shell.allow`), and Cline driven headlessly as STORY-001 decided, when Cline runs the task, then both files end with the scripted content.
- [ ] Given that run, when the audit is read, then the same assertions as STORY-016 hold (ingress, profile, `has_tool_calls`, one `conversation_key`, decisions joined by `audit_id`, no duplicate block).
- [ ] Given the scripted `DROP TABLE` reply, when Cline receives it, then it executes nothing and surfaces the harness note; the decision row is `deny` / `sql.ddl`.
- [ ] Given the report, when written, then it records the Cline version and how it was installed (local, pinned, never global), the command line, the config, its request keys, and — if STORY-001 found a full headless run impossible — what the fallback proves and what it does not.

## Technical Notes

- Orchestrator note (STORY-016): reuse `tests/e2e/_live.py` (`dump_action_decisions`, `Recorder(keep_tool_names=True)`) and the `tests/e2e/_opencode.py` / `test_opencode.py` structure (throwaway libSQL on its own port, HOME/APPDATA/XDG redirected, processes killed as a tree in `finally`, stdin=DEVNULL). OpenCode took its working directory from the inherited `PWD` env var, not the process cwd, and ran its shell tool in the harness checkout on the first run; set `PWD` (and drop `OLDPWD`, `INIT_CWD`) to the throwaway repo for Cline too, and check its `-c <dir>` is honoured. One conversation_key across the loop held for OpenCode.
- Orchestrator note (STORY-001): Cline CLI 3.0.74 headless is verified: `cline auth --data-dir <d> --provider openai-compatible --apikey .. --modelid .. --baseurl http://127.0.0.1:<port>/v1`, then `cline --data-dir <d> --yolo --json -c <dir> -P openai-compatible -m .. -t N "<prompt>"`. Its agent loop never stops on its own (2,000+ requests in two minutes in the survey): the script must end with `submit_and_exit` and the run must pass `-t`. `--yolo` advertises only `read_files`, `run_commands`, `editor`, `submit_and_exit`. Installed at `tests/e2e/.clients/cline` (git-ignored).
- Install Cline into a git-ignored directory (STORY-001's choice), pinned; never `npm -g`, never into the user's VS Code.
- PRD-016's note: `examples/action_policy.yaml` maps OpenCode and SQL tools only; a Cline deployment writes its own `tools:` and `shell.allow` (with the built-in policy no Cline shell call is allowed). Put the Cline policy under `tests/e2e/` and reference it from the docs (STORY-018).
- Reuse STORY-016's fixtures and stub script.
- Skills: none applicable. No UI.

## Dependencies

- **Blocked by**: STORY-001, STORY-014, STORY-016
- **Blocks**: STORY-018

## PRD Reference

Source: [`PRD-017-tool-calling/PRD.md`](../../PRDs/PRD-017-tool-calling/PRD.md) — sections 5 (story 1), 7 (F11), 11 (MVP), 14 (Risks 1, 4, 7)
