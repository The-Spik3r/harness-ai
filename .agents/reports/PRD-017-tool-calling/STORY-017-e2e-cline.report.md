---
story: STORY-017
prd: PRD-017
plan: .agents/plans/PRD-017-tool-calling/completed/STORY-017-e2e-cline.plan.md
epic_branch: epic/PRD-017-tool-calling
commit: 70d0fc5
status: COMPLETE
completed: 2026-11-16
---

# Implementation Report — STORY-017: E2E: Cline completes the same task through the harness

**Plan**: `.agents/plans/PRD-017-tool-calling/completed/STORY-017-e2e-cline.plan.md`
**Epic Branch**: `epic/PRD-017-tool-calling`
**Commit**: `70d0fc5`

## Summary

A new opt-in module, `tests/e2e/test_cline.py`, runs the real, pinned Cline CLI 3.0.74 headless against a live harness (`V1_TOOLS_ENABLED=true`, a Cline action policy), the STORY-014 stub (`tests/e2e/scripts/cline.json`) and PRD-015's recording proxy. It reuses STORY-016's task and audit assertions. Live result: 4 passed (56 s). `tests/e2e/test_opencode.py` still passes live (4 passed, 43 s) after its process helpers moved into `_live.py`. No `app/` file changed, and no fallback was needed.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Cline action policy (template with `@REPO@`) | `tests/e2e/cline/action_policy.yaml` | done |
| 2 | `git`, `write_lf`, `kill_tree`, `run_tree` moved into `_live.py`; `test_opencode.py` imports only | `tests/e2e/_live.py`, `tests/e2e/test_opencode.py` | done |
| 3 | Stub script | `tests/e2e/scripts/cline.json` | done |
| 4 | Constants and pure helpers | `tests/e2e/_cline.py` | done |
| 5 | Everyday pins | `tests/test_e2e_cline_script.py` | done |
| 6-7 | Fixtures, runner and the AC 1-4 tests | `tests/e2e/test_cline.py` | done |
| 8 | Pinned manifest, README paragraph, `run_tree` test, live runs | `tests/e2e/cline/package.json`, `tests/e2e/scripts/README.md`, `tests/test_e2e_live.py` | done |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| Frontend lint | n/a (no frontend) |
| Targeted set (one pytest call): `test_e2e_cline_script`, `test_e2e_opencode_script`, `test_e2e_live`, `test_untouched_app`, `test_stub_openrouter`, and both e2e modules without `--run-e2e` | 123 passed, 8 skipped (the two e2e modules) |
| Live `tests/e2e/test_cline.py --run-e2e` | 4 passed |
| Live `tests/e2e/test_opencode.py --run-e2e` (after the helper move) | 4 passed |
| Full suite | deferred to orchestrator (user decision) |

In-process check required by the orchestrator: `run_commands` `{"commands":["sqlite3 app.db \"DROP TABLE users\""]}` (format `command`) decides `deny` / `sql.ddl`. It does, so there is no carried-over defect.

## The Cline record (AC 4)

- **Version and install**: `cline --version` printed `3.0.74`. Installed locally, pinned, never global, into the git-ignored `tests/e2e/.clients/cline`: `npm install --prefix tests/e2e/.clients/cline --save-exact --no-audit --no-fund cline@3.0.74` (manifest `tests/e2e/cline/package.json`). The lock holds `cline-3.0.74.tgz` with integrity `sha512-pCaRaJ6Jx50Urej+BYjpGkpZnFbPDCPsibKEbIjEuVxETXbZ/A1SMij8Thy8FobercevXX6hV7joAzU7OG5lzA==`. The native `node_modules/@cline/cli-windows-x64/bin/cline.exe` is run, never the shim.
- **Command lines** (`--data-dir` is an absolute temporary directory, one per scenario; the token is replaced by `<harness token>` in the record):
  - `cline.exe auth --data-dir <tmp>/data-<label> --provider openai-compatible --apikey <harness token> --modelid openai/gpt-4o --baseurl http://127.0.0.1:<proxy port>/v1`
  - `cline.exe --data-dir <tmp>/data-<label> --yolo --json -c <repo> -P openai-compatible -m openai/gpt-4o -t 60 "<prompt>"`
- **Config**: only what `cline auth` wrote into `--data-dir`. Environment: `HOME`, `USERPROFILE`, `APPDATA`, `LOCALAPPDATA`, `XDG_*`, `TEMP`, `TMP` redirected to a temporary directory; `PWD` is that run's repository; `NO_COLOR=1`; stdin `DEVNULL`; `OPENAI_*`, `OPENROUTER_*`, `ANTHROPIC_*`, `OPENCODE_*`, `AIDER_*`, `CLINE_*`, `OLDPWD`, `INIT_CWD` not inherited. `~/.cline` did not exist before the run, after the run, or at the end of the session (`home_cline_dir_exists` `{before: false, after: false}`).
- **Request keys** (all 7 agent requests): `messages, model, stream, stream_options, tool_choice, tools`; `stream: true`, `stream_options` `["include_usage"]`, `tool_choice` set (`"auto"`), no `parallel_tool_calls`; request 1 roles `system, user, user`; tools advertised `editor, read_files, run_commands, submit_and_exit`.
- **Outbound traffic**: Cline contacts its own service for feature flags at startup (the planning probe saw `data/cache/feature-flags.json`). No request content goes there and no switch was found. Already an orchestrator note in STORY-018's Technical Notes.

## Live results

Task run: exit 0, `finishReason: completed`, 5 requests (stub rules START, EDIT, WRITE, TEST, DONE), both files byte-equal to `CALC_EDITED` / `TEST_WRITTEN`, Cline executed every call itself. Decisions: `read_files allow fs.read`, `editor allow fs.write_in_workspace` (twice), `run_commands allow shell.allowlisted`, `submit_and_exit allow tool.opaque`, each joined to its request by `audit_id`; one `conversation_key`, no duplicate block.

Drop run: exit 0, 2 requests (`run_commands` DROP TABLE, then `submit_and_exit`), decisions `run_commands deny sql.ddl` and `submit_and_exit allow tool.opaque`; `users` still has 1 row, `git status` unchanged, and the harness note was in Cline's text events.

## Files Changed

| File | Action |
|------|--------|
| `tests/e2e/cline/action_policy.yaml` | CREATE |
| `tests/e2e/cline/package.json` | CREATE |
| `tests/e2e/scripts/cline.json` | CREATE |
| `tests/e2e/_cline.py` | CREATE |
| `tests/e2e/test_cline.py` | CREATE |
| `tests/test_e2e_cline_script.py` | CREATE |
| `tests/e2e/_live.py` | UPDATE (+45: `git`, `write_lf`, `kill_tree`, `run_tree`) |
| `tests/e2e/test_opencode.py` | UPDATE (imports and call sites only; private copies removed) |
| `tests/test_e2e_live.py` | UPDATE (+1 test, `run_tree`) |
| `tests/e2e/scripts/README.md` | UPDATE |
| `.agents/` | story, index, plan archive, this report |

## Deviations from Plan

1. **DONE rule regex**: the plan said `\bOK\b`. Cline wraps the unittest output in JSON text, so the stub sees a literal backslash-n then `OK`, and there is no word boundary between `n` and `O` (the everyday test caught it: the FAILED rule answered). The rule is `(\\n|\n)OK\b` (an escaped or a real newline, then `OK`). The README says so.
2. **Policy mapping test**: the plan compared all five mapped tools with `BUILT_IN_TOOLS`. `apply_patch` deliberately reads `input` only (the built-in one is `patchText|input`), so the test compares four and asserts `apply_patch`'s kind, target and format separately.
3. Orchestrator decisions applied: Q1 policy at `tests/e2e/cline/action_policy.yaml` (no `examples/` file), Q2 helpers moved into `_live.py`, Q3 both drop-run requests and decisions asserted.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_e2e_cline_script.py` | rule sequence against Cline's request sequence; scripted call shapes and paths; no generated ids and placeholder count; policy decision for every scripted call plus edges; policy file maps Cline's tools as the built-in mapping does |
| `tests/test_e2e_live.py` | `run_tree` closes stdin and kills the whole tree on timeout |
| `tests/e2e/test_cline.py` (opt-in) | pinned version; task through the harness (AC 1, 2, 4); denied DROP TABLE (AC 3); every row v1/code |

## Process hygiene

Every `--data-dir` was absolute (asserted in `_cline.auth_command` / `run_command`); every process runs through `_live.run_tree` / `start_stub` / `start_harness` and is killed as a tree in a `finally`. After the runs: no `cline.exe`, uvicorn or stub in the process table (the one `node` predates the session), the throwaway container `harness-libsql-e2e017-017` removed, `~/.cline` absent. No `npm -g`.

## Acceptance Criteria

- [x] Both files end with the scripted content under the Cline policy (`test_cline_runs_the_scripted_task_through_the_harness`; policy pinned by `test_the_cline_policy_decides_each_scripted_call_as_planned` and `test_the_policy_file_maps_cline_s_tools_as_the_built_in_mapping_does`)
- [x] The STORY-016 audit assertions hold (same test)
- [x] The scripted DROP TABLE is `deny` / `sql.ddl`, Cline executes nothing and surfaces the note (`test_a_scripted_drop_table_is_denied_and_cline_reports_it`)
- [x] The report records version, install (local, pinned, never global), command lines, config and request keys; no fallback was needed
