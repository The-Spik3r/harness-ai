---
story: STORY-015
prd: PRD-021
slug: cline-realtime-e2e
title: Cline end-to-end on a real-time stream
type: NEW_CAPABILITY
complexity: small
epic_branch: epic/PRD-021-realtime-streaming
created: 2026-11-19
---

# Plan: Cline end-to-end on a real-time stream

## Summary

Mirror STORY-014 (5eebd78) for Cline 3.0.74: a new opt-in `@pytest.mark.e2e` module `tests/e2e/test_cline_realtime.py`, a pure-helper module, a new stub script and a fast non-e2e pin test. The harness runs with `STREAMING_ENABLED=true`, a file-mode registry (`streaming`/`reasoning`) and a roles file granting `stream:realtime` (+ `reasoning:view`). Real time is proven from the harness side (`_live.Recorder(keep_sse=True)`, audit rows). No `app/` change; `test_cline.py`, `_cline.py` and `_opencode_realtime.py` stay unchanged.

- Story: `.agents/stories/PRD-021-realtime-streaming/STORY-015-cline-realtime-e2e.md`
- PRD sections used: 6.6 (stream shape, D6/D9/D17), F10 (stub `stream` shape), Risk 4 (client mishandles `reasoning_content`), D8
- Systems affected: tests only (`tests/e2e/`, `tests/`)

## Design Decisions

- **Import, do not move** the client-neutral helpers. `tests/e2e/_opencode_realtime.py` (`COMPLETION_ID_PREFIX`, `REASONING_FIELD`, `registry_yaml`, `roles_json`, `parse_sse`, `argument_fragments`; lines 20-105) is imported by the new helper module. Its registry uses `HARNESS_MODEL = "openai/gpt-4o"` (`_opencode.py:18`), which is also Cline's model id (`_cline.py:31`), so nothing needs to change. Moving them would touch STORY-014's module for no gain.
- **Copy, not share, the module fixtures** (`child_cwd`, `users`, `harness`, `recorder`, `rows`, `actions`, `seen_*`, `_say`, `_cline_env`, `run_cline`): this is how `test_opencode_realtime.py` and `test_cline.py` already relate. `_assert_real_time` is copied (about 20 lines, `test_opencode_realtime.py:363-383`).
- **Scenario selection by working directory.** Cline's last user turn is its own nudge, so the stub picks the scenario from the system prompt, which names the `-c` directory (`test_cline.py:22-30`). Three repositories: `e2e021-015-cline-text`, `-drop`, `-reason` (constants in the helper module).
- **Every scripted reply path ends with a `submit_and_exit` call.** Cline's loop ends only on it (`scripts/README.md`; `cline.json` rules 0 and default; `-t` does not bound the run). Text and reasoning rules therefore carry `content` + `stream` + one `submit_and_exit` call (`summary` of at least 10 chars; allowed by `opaque_tools`, released whole). They give exactly one request, so `len(run.posts) == 1`. The drop rule carries `run_commands` (denied); the follow-up rule (`role: assistant`, `contains: "[harness] tool call"`, `advertises: submit_and_exit`, as `cline.json` rule 0) answers with `submit_and_exit`. Every rule has `stream: {chunk_chars: 6-8, delay_ms: 60}`; the `default` is a `submit_and_exit` so a missed match still ends the run.
- **Users and roles as STORY-014**: `manage_users.py --role` takes admin|auditor|user only, so `roles_json()` redefines `user` (query, audit own, `stream:realtime`) and `auditor` (+ `reasoning:view`). `_ROLES = {"text": "user", "drop": "user", "reason": "auditor"}`.
- **Policy**: reuse `_cline.policy_yaml()` / `tests/e2e/cline/action_policy.yaml` unchanged (maps `run_commands`; `submit_and_exit` is `opaque_tools: allow`).
- **How an unscriptable case is recorded** (story AC1 and Technical Notes): the harness-side proof is always a hard assertion. Cline-side outcomes (exit code, `finish_reason`, texts, `reasoning_displayed`, output tail) are written to `cline-realtime-run.json` before asserting. If the Task 5 probe proves Cline cannot be driven for a case (e.g. it errors on a streamed `submit_and_exit`, or never completes), that test calls `pytest.skip("Cline 3.0.74 cannot ...: <evidence>")` at its top: a skip with a reason, never a pass. The report quotes it. A missing Cline executable is `pytest.fail` with `_cline.INSTALL_RECIPE` (as `test_cline.py:111-119`); no global install.
- **Reasoning "displayed" is an observation**: scan Cline's `agent_event` stream for `contentType == "reasoning"` (the string exists in `@cline/*` dist; confirm the text field name on the first live run) and for the sentinel; print and record it, never assert. Hard: sentinel in a `reasoning_content` delta (grant works), never in any content delta, Cline's `texts`, any file in the three workspaces (`.git` included) or any audit row (D8). Cline's own data dir is not scanned (it may store what it displays); the report says so.

## Skills In Use

None apply (`.agents/skills/` holds only `frontend-design`; story `skills: []`).

## Patterns to Follow

| Category | Source | What to mirror |
|----------|--------|----------------|
| Module layout, fixtures, recipe | `tests/e2e/test_opencode_realtime.py:36-383` | harness env with registry/roles/`STREAMING_ENABLED`, `Recorder(keep_sse=True)`, `_assert_real_time` |
| Cline runner, env isolation, events | `tests/e2e/test_cline.py:285-416` | `_cline_env`, `auth` then run, per-label `--data-dir`, `_ClineRun` |
| Workspaces named for the stub | `tests/e2e/test_cline.py:159-199` | `_make_repo`, dir-name keyed scenarios |
| Helper module | `tests/e2e/_opencode_realtime.py:33-105`, `tests/e2e/_cline.py:56-103` | `render_script`, `auth_command`, `run_command` |
| Stub rules | `tests/e2e/scripts/cline.json` (rules 0-1), `opencode_realtime.json` | `role`/`contains`/`advertises` qualifiers; `stream` shape with `reasoning` |
| Fast pins | `tests/test_e2e_opencode_realtime_script.py:38-130`, `tests/test_e2e_cline_script.py:38-75,142-170` | `_label` over a Cline-shaped body, policy/registry/roles checks |
| Denial note | `tests/e2e/_cline.py:18-25` (`DENIAL_NOTE_TEMPLATE`) | tied to `tool_release` by the opencode pin at `test_e2e_opencode_realtime_script.py:129` |

Excerpt (`test_cline.py:379`): `auth_command(cline_exe, data_dir, recorder.base + "/v1", token)` with an absolute `--data-dir`.

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `tests/e2e/scripts/cline_realtime.json` | CREATE | Stub script: follow-up, drop, text, reason, default |
| `tests/e2e/_cline_realtime.py` | CREATE | Pure constants/helpers: `SCRIPT`, dir names, rule labels, `render_script(repo, sentinel)`; re-exports from `_cline` and `_opencode_realtime` |
| `tests/e2e/test_cline_realtime.py` | CREATE | The opt-in e2e module |
| `tests/test_e2e_cline_realtime_script.py` | CREATE | Fast pins (default suite) |
| `tests/e2e/scripts/README.md` | UPDATE | One paragraph for `cline_realtime.json` (it lists each script) |
| `tests/e2e/_live.py`, `_cline.py`, `_opencode_realtime.py`, `test_cline.py` | none | Unchanged |

## Tasks

### Task 1: Stub script `tests/e2e/scripts/cline_realtime.json`
- Rules in order (label = index): 0 follow-up (`role: assistant`, `contains: "[harness] tool call"`, `last_role: user`, `advertises: submit_and_exit`; `submit_and_exit` id `call_rt_submit_drop`; short streamed content); 1 drop (`role: system`, `contains: e2e021-015-cline-drop`, `last_role: user`, `advertises: run_commands`; content "Cleaning up the database now."; `chunk_chars: 6`; `run_commands` id `call_rt_drop`, arguments `{"commands":["sqlite3 app.db \"DROP TABLE users\""]}`, the shape `cline.json` rule 1 uses); 2 text (`-text` dir; content with `E2E-RT-ANSWER` exactly once; `chunk_chars: 7`; `submit_and_exit` `call_rt_submit_text`); 3 reason (`-reason` dir; content with `E2E-RT-REASONED`; `stream.reasoning` "Thinking about @SENTINEL@ before answering. It stays private."; `chunk_chars: 8`; `submit_and_exit`). `default`: `submit_and_exit` as in `cline.json`. Paths in arguments use `@REPO@` only if a call needs one (none expected).
- Mirror: `cline.json` (qualifier syntax), `opencode_realtime.json` (stream shape).

### Task 2: Helpers `tests/e2e/_cline_realtime.py`
- `SCRIPT`, `TEXT_DIR/DROP_DIR/REASON_DIR`, `FOLLOWUP_RULE, DROP_RULE, TEXT_RULE, REASON_RULE`, `render_script(repo_text, sentinel)` (replace `@REPO@`/`@SENTINEL@`, `json.loads` check). Re-export from `_opencode_realtime`: `COMPLETION_ID_PREFIX, REASONING_FIELD, registry_yaml, roles_json, parse_sse, argument_fragments`; from `_cline`: `policy_yaml, repo_root_text, auth_command, run_command, cline_executable, CLIENT_DIR, DENIAL_NOTE_TEMPLATE, YOLO_TOOLS, PROCESS_TIMEOUT_SECONDS, INSTALL_RECIPE`. No env, process or `app` import (reason as `_cline.py:3-8`).

### Task 3: Fast pins `tests/test_e2e_cline_realtime_script.py`
- `_label` over a Cline-shaped body (system prompt naming the dir, prompt + nudge user turns, `tools` from `YOLO_TOOLS`, `stream: true`; as `test_e2e_cline_script.py:38-50`): each dir selects its rule; a body whose last assistant turn holds `[harness] tool call` selects rule 0; every stream shape has 1 <= chunk_chars <= 8 and delay > 0; the drop arguments cut into >= 4 fragments and parse to the DROP command; the sentinel is only inside `reasoning` and substituted; text/reason rules end in one `submit_and_exit` whose `summary` >= 10 chars; the policy (`action_policy`, as `test_e2e_cline_script.py:142`) denies the drop `run_commands` (`sql.ddl`) and allows `submit_and_exit`; the registry (`tests/_providers.py`) has `streaming`/`reasoning` true; roles file: `user` holds `stream:realtime` and not `reasoning:view`, `auditor` both (as `test_e2e_opencode_realtime_script.py:89`).
- Validate: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_e2e_cline_realtime_script.py`

### Task 4: Live module `tests/e2e/test_cline_realtime.py`
- Docstring in STORY-014's style (AC map, run recipe, container `harness-libsql-e2e021-015`, port 8090). `pytestmark = pytest.mark.e2e`; `NONCE`; `SENTINEL = f"RSN-{NONCE}"`; `_REPORT_FIELDS` adds `streamed_realtime, completion_id, reasoning_shown`.
- Fixtures: `cline_exe` (`test_cline.py:111`), `e2e_db_url`, `child_cwd`, `child_env`, `run_child`, `users`, three workspaces (`_make_repo` copy), `stub` (renders with SENTINEL), `harness` (env as `test_opencode_realtime.py:164-182` with the Cline policy), `recorder` (`keep_tool_names=True, keep_sse=True`), `rows`/`actions`, `cline_runs` (writes `cline-realtime-run.json`), `run_cline(label, repo, prompt)`.
- Tests:
  1. `test_real_time_is_on_for_the_harness_child` (env, roles file, registry text).
  2. **AC1** `test_the_answer_text_streams_in_pieces`: returncode 0, `finish_reason == "completed"`, marker in `run.texts`, `run.upstream == [TEXT_RULE]`, `len(run.posts) == 1`; `_assert_real_time`; >= 3 content deltas; `chunks[-1]["t"] - deltas[0]["t"] >= 0.2`; every `tool_calls` delta carries whole `json.loads`-able arguments (D6).
  3. **AC2** `test_a_denied_drop_table_never_leaves_in_pieces`: as `test_opencode_realtime.py:428-467` with `run_commands`/`call_rt_drop`. Two requests (`[DROP_RULE, FOLLOWUP_RULE]`), both rows real time. Request 1: no `tool_calls` delta, no `"arguments"`/`"function"` in raw, nothing after the finish chunk; the note (template) present and no `DROP TABLE`/`sqlite3`/`app.db`/argument piece outside it. Exactly one deny `action_decisions` row (`sql.ddl`, `run_commands`, `call_rt_drop`) joined to row 1 by `audit_id`, plus the allowed `submit_and_exit`. `app.db` intact, `git status` unchanged, the note reached Cline (`run.texts`).
  4. **AC3** `test_reasoning_is_shown_live_and_never_written_down` (auditor): sentinel in `reasoning` deltas (hard), `reasoning_shown` true on rows, never in content deltas, Cline `texts`, any file in the three workspaces, any row; "displayed" observed, printed, recorded.
  5. `test_zz_every_row_is_v1_code_and_real_time`.
- AC4 is the module marker (`tests/conftest.py:186-228`).

### Task 5: Live probe, then README
- First live run: read `cline-realtime-run.json` and confirm the reasoning event field name, that a streamed `submit_and_exit` completes the run, and what Cline does after the denial note. Adjust Cline-side assertions to what is observed; for any case Cline cannot be driven in, apply the skip rule above and say so in the report. Add the `cline_realtime.json` paragraph to `tests/e2e/scripts/README.md`.

## End-to-End Tests

- [ ] Live, opt-in (pick a free port; `:8089` was STORY-014's):
  `docker run -d --name harness-libsql-e2e021-015 -p 8090:8080 -e SQLD_NODE=primary ghcr.io/tursodatabase/libsql-server:latest`, then
  `HARNESS_E2E_LIBSQL_URL=http://127.0.0.1:8090 PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/e2e/test_cline_realtime.py -m e2e --run-e2e -v`; afterwards `docker rm -f harness-libsql-e2e021-015` and confirm no harness, stub or Cline process remains. CI does not run e2e.
- [ ] Without the opt-in the module reports every test skipped (AC4): `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/e2e/test_cline_realtime.py`.
- [ ] `tests/e2e/test_cline.py` is unchanged; no live re-run needed.

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_e2e_cline_realtime_script.py tests/test_e2e_cline_script.py tests/test_e2e_opencode_realtime_script.py tests/test_e2e_marker.py tests/test_e2e_live.py tests/test_untouched_app.py tests/e2e/test_cline_realtime.py
```
No `app/` file is touched (`test_untouched_app.py` is a cheap guard). Do not run the full suite (GitHub CI).

## Acceptance Criteria -> Tasks -> Tests

| AC | Task(s) | Test that proves it |
|----|---------|---------------------|
| AC1 text arrives and run completes, or the report states why not | 1, 2, 4, 5 | `test_cline_realtime.py::test_the_answer_text_streams_in_pieces` (live); script pinned in `test_e2e_cline_realtime_script.py`; skip-with-reason + report if Cline cannot be driven |
| AC2 denied call: note shown, no fragment released | 1, 4 | `test_cline_realtime.py::test_a_denied_drop_table_never_leaves_in_pieces` |
| AC3 both grants: record whether Cline displays `reasoning_content` | 1, 4, 5 | `test_cline_realtime.py::test_reasoning_is_shown_live_and_never_written_down` (observation in `cline-realtime-run.json`) |
| AC4 skipped without the opt-in | 4 | module `pytestmark` + the no-`--run-e2e` run (all skipped) |

Plus: every audit row `streamed_realtime` true with a `chatcmpl-harness-rt-` id equal to the SSE id (a buffered fallback fails); the report states the Risk 4 outcome for Cline.

## Risks

- Cline may loop or error when a streamed reply mixes text and `submit_and_exit`; Task 5 probes it first, and `PROCESS_TIMEOUT_SECONDS` (180, `_cline.py:42`) bounds the run.
- Cline's session store may keep displayed reasoning on disk; out of the D8 assertion (server side and workspaces only), stated in the report.
- Port clashes: pick a free port and remove the container afterwards.
