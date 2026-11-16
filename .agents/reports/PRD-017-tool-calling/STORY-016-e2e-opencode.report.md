---
story: STORY-016
prd: PRD-017
plan: .agents/plans/PRD-017-tool-calling/completed/STORY-016-e2e-opencode.plan.md
epic_branch: epic/PRD-017-tool-calling
commit: d11067c
status: COMPLETE
completed: 2026-11-16
---

# Implementation Report — STORY-016: E2E: OpenCode completes a scripted multi-file task; a scripted DROP TABLE is denied and reported

**Plan**: `.agents/plans/PRD-017-tool-calling/completed/STORY-016-e2e-opencode.plan.md`
**Epic Branch**: `epic/PRD-017-tool-calling`
**Commit**: `d11067c`

## Summary

Tests only, no app code. A new opt-in E2E module (`tests/e2e/test_opencode.py`) runs the real OpenCode 2.0.10 (`run --standalone --auto --format json`) in a throwaway git repository against a live harness (`V1_TOOLS_ENABLED=true`, an action policy with the repository as `workspace.roots` and `shell.allow: [python -m unittest]`) on the STORY-014 stub, behind PRD-015's recording proxy. The scripted task (`read`, `edit`, `write`, `shell python -m unittest -q`, text) completes and both files end with the scripted content. The scripted `shell sqlite3 app.db "DROP TABLE users"` is denied (`sql.ddl`), OpenCode executes nothing, prints the harness note and exits 0 after one request. Pure helpers and constants live in `tests/e2e/_opencode.py` (orchestrator decision Q3); an everyday test pins the rendered script and policy.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Stub script (8 rules, `@REPO@` placeholder) | `tests/e2e/scripts/opencode.json` | done |
| 2 | `DUMP_ACTIONS` / `dump_action_decisions`, opt-in `Recorder(keep_tool_names=True)` | `tests/e2e/_live.py` | done |
| 3 | Constants and pure helpers (`repo_root_text`, `render_script`, `policy_yaml`, `opencode_config`) | `tests/e2e/_opencode.py` | done |
| 4 | Fixtures and runner (`_run_tree` closes stdin and kills the process tree) | `tests/e2e/test_opencode.py` | done |
| 5 | AC 1-4 tests | `tests/e2e/test_opencode.py` | done |
| 6 | Everyday pins | `tests/test_e2e_opencode_script.py`, `tests/test_e2e_live.py` | done |
| 7 | README paragraph and the live run | `tests/e2e/scripts/README.md` | done |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| Targeted tests (one pytest call: `test_e2e_opencode_script.py`, `test_e2e_live.py`, `test_stub_openrouter.py`, `test_untouched_app.py`, `e2e/test_opencode.py`) | 117 passed, 4 skipped (the 4 are the e2e module, without `--run-e2e`) |
| Live E2E (`--run-e2e`, third run) | 4 passed in 32 s |
| Full suite | Deferred to orchestrator (user decision) |

## Live run (AC 4 evidence)

Command: `HARNESS_E2E_LIBSQL_URL=http://127.0.0.1:8088 HARNESS_E2E_OPENCODE=C:/Users/nahue/AppData/Roaming/npm/node_modules/@opencode/cli/bin/opencode.exe PYTHONUTF8=1 python -m pytest tests/e2e/test_opencode.py -m e2e --run-e2e -v` against a throwaway `harness-libsql-e2e017-016` container (removed afterwards).

- **Version**: `opencode v2.0.10`.
- **Command line**: `opencode.exe run --standalone --auto --format json -m harness/openai/gpt-4o "<prompt>"`, cwd the throwaway repository, stdin `DEVNULL`.
- **Provider config** (`OPENCODE_CONFIG_CONTENT`): provider `harness`, `@ai-sdk/openai-compatible`, `baseURL = <recorder>/v1`, `apiKey = <harness token>`, model `openai/gpt-4o`, `agent.title.disable = true`.
- **Env**: HOME, USERPROFILE, APPDATA, LOCALAPPDATA, XDG_*, TEMP, TMP into a temporary directory; `OPENCODE_DISABLE_AUTOUPDATE=1`, `OPENCODE_DISABLE_MODELS_FETCH=1`, `NO_COLOR=1`; `PWD` set to the repository (see findings); no `OPENAI_*`/`OPENROUTER_*`/`ANTHROPIC_*`/`OPENCODE_*`/`AIDER_*` inherited.
- **Request keys** (every agent request): `messages, model, store, stream, stream_options, tools`; `stream: true`, `stream_options: {include_usage}`; no `tool_choice`, `parallel_tool_calls`, `functions`. Message keys `content, role, tool_call_id, tool_calls`; roles `system, user, assistant, tool`. Tools advertised: `edit, execute, glob, grep, question, read, shell, skill, subagent, webfetch, websearch, write`.
- **Streamed**: yes, every request (both runs), and OpenCode accepted the harness SSE order (role chunk, tool-call fragment, finish, usage-only chunk, `[DONE]`) on all 6 requests (exit 0, follow-up requests sent). No keep-alives were seen.
- **`ignored_params`**: `store` on every row.
- **Task run**: exit 0, stub rules `1,2,3,4,5`, OpenCode `tool_use` events `read, edit, write, shell` all `completed`, final text `E2E-OPENCODE-DONE`.
- **Drop run**: exit 0, stub rule `0`, one request, no tool executed, `users` table intact, no tracked file changed, note present in a text event.
- **Audit** (`rows.json`): 6 rows, all `v1`/`code`/`success`/`streamed`, `has_tool_calls` true, `was_duplicate_blocked` false; the 5 task rows share one `conversation_key` (Q1 held, no carried-over defect). The drop run has its own key.
- **Decisions** (`actions.json`), joined by `audit_id` to the request whose response carried the call: `read allow fs.read`, `edit allow fs.write_in_workspace`, `write allow fs.write_in_workspace`, `shell allow shell.allowlisted` (audit ids 13, 14, 15, 16 = the first four rows), and `shell deny sql.ddl` (`call_drop`, audit id 18 = the drop row).
- No token appears in `opencode-run.json`, `rows.json` or `actions.json` (`apiKey` is `<harness token>`). Copies of the three files: `C:\Users\nahue\AppData\Local\Temp\claude\3538ad6943244944\07c1d677-d9dc-4535-8925-6e718a3d991a\scratchpad\{opencode-run,rows,actions}.json`.

## Findings (beyond the plan's live diagnosis)

1. **`PWD` decides OpenCode's working directory.** With cwd set by `Popen` but `PWD` inherited from the developer's Git Bash (`G:/coding/harness-ai`), OpenCode's `shell` tool ran in the harness checkout: `python -m unittest -q` there discovered the harness's own 138 tests (all failed to import `pytest` under the system Python), and rule 6 (`E2E-OPENCODE-FAILED`) answered. Setting `PWD` to the repository in the child env fixes it. The edits were unaffected because their paths are absolute. First run therefore wrote nothing in the checkout other than failed imports (git status of the checkout shows only this story's files). Worth stating in STORY-018's docs: a client launched from a shell whose `PWD` differs from the project directory acts in the wrong directory.
2. **`agent.title.disable` works through `OPENCODE_CONFIG_CONTENT`** (Q2): every run sent only agent requests (5 and 1 posts, the test asserts the count). Nothing was written to any config file, and `~/.config/opencode` was not touched (only `service.json` from 2026-09-19 is there). The title rule (7) stayed unused.
3. **Process hygiene.** Only `run --standalone` and `--version` were run. Each OpenCode run is a `Popen` with stdin `DEVNULL` whose whole tree is killed (`taskkill /T /F`) in a `finally`. After the live runs and the container removal, the process table shows no `opencode.exe`, uvicorn or stub process; the throwaway libSQL container is gone; `harness-libsql-dev` and the pre-existing compose container were not touched.

## Files Changed

| File | Action |
|------|--------|
| `tests/e2e/scripts/opencode.json` | CREATE |
| `tests/e2e/_opencode.py` | CREATE |
| `tests/e2e/test_opencode.py` | CREATE |
| `tests/test_e2e_opencode_script.py` | CREATE |
| `tests/e2e/_live.py` | UPDATE (+`DUMP_ACTIONS`, `dump_action_decisions`, `tool_names`, `Recorder(keep_tool_names)`; default shape unchanged) |
| `tests/test_e2e_live.py` | UPDATE (2 tests added, none edited) |
| `tests/e2e/scripts/README.md` | UPDATE (one paragraph) |

## Deviations from Plan

- Helpers and constants are in `tests/e2e/_opencode.py`, not in the E2E module (orchestrator decision Q3). The everyday test imports from there.
- Added `PWD=<repository>` to OpenCode's env (finding 1), and `_oc_env` drops `OLDPWD` and `INIT_CWD`.
- Added `test_the_pinned_opencode_is_the_one_that_runs` (version assertion, 4 e2e tests instead of 3) and `test_the_mirrored_denial_note_equals_the_release_step_s` in the everyday file, which pins the mirrored note literal against `tool_release.DENIAL_NOTE_TEMPLATE`.
- The drop test compares `git status` before and after its run instead of expecting a clean tree, because the module-scoped repository holds the task test's edits.
- `README.md` paragraph says "PRD-017 STORY-016" and leaves the stale PRD-015 numbering sentence alone, as planned.
- The plan's open question 2 (second source file): `tests/test_calc.py` counts as the second changed file (orchestrator Q4).

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/e2e/test_opencode.py` (live, `--run-e2e`) | `test_the_pinned_opencode_is_the_one_that_runs`, `test_opencode_runs_the_scripted_task_through_the_harness`, `test_a_scripted_drop_table_is_denied_and_opencode_reports_it`, `test_zz_every_row_this_module_wrote_is_v1_and_code` |
| `tests/test_e2e_opencode_script.py` | rule sequence, scripted arguments, no generated-style ids / placeholder count, policy decisions, mirrored note |
| `tests/test_e2e_live.py` | `test_the_recorder_keeps_tool_names_only_when_asked`, `test_the_action_dump_reads_list_action_decisions` |

## Acceptance Criteria

- [x] AC 1: OpenCode executed read, edit, write, shell itself; both files end with the scripted content (`test_opencode_runs_the_scripted_task_through_the_harness`, live).
- [x] AC 2: every row v1/code, `has_tool_calls`, one `conversation_key`, one decision per call joined by `audit_id`, no duplicate block (same test, live).
- [x] AC 3: `shell` DROP TABLE denied `sql.ddl`, nothing executed, note printed, one request, exit 0 (`test_a_scripted_drop_table_is_denied_and_opencode_reports_it`, live).
- [x] AC 4: version, command line, provider config, request keys, streamed, exit codes recorded (`opencode-run.json`, summarised above).
- [x] All tasks completed; backend imports; targeted tests pass; full suite deferred to the orchestrator.
