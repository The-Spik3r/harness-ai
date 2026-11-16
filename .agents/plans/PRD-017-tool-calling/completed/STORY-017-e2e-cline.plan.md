---
story: STORY-017
prd: PRD-017
slug: e2e-cline
title: "E2E: Cline completes the same task through the harness"
type: NEW_CAPABILITY
complexity: HIGH
epic_branch: epic/PRD-017-tool-calling
created: 2026-11-16
---

# Plan: E2E: Cline completes the same task through the harness

## Summary

A new opt-in E2E module, `tests/e2e/test_cline.py`, runs the git-ignored, pinned Cline CLI 3.0.74 headless (`cline --data-dir <tmp> --yolo --json -c <repo> -P openai-compatible -m openai/gpt-4o -t 60 "<prompt>"`, after `cline auth --data-dir <tmp> ...`) against the same live stack as STORY-016: a harness subprocess (`V1_TOOLS_ENABLED=true`, a **Cline-specific `ACTION_POLICY_FILE`**), the STORY-014 stub with a new script `tests/e2e/scripts/cline.json`, and PRD-015's recording proxy with tool names kept. It reuses STORY-016's task (fix `add()` in `src/calc.py`, write `tests/test_calc.py`, run `python -m unittest -q`), its file contents and its audit assertions. The Cline script uses Cline 4.x tool shapes (`read_files` `files[].path`, `editor` `path`/`old_text`/`new_text`, `run_commands` `commands[]`) and ends every path with `submit_and_exit`, which the policy lists in `opaque_tools` (otherwise it is `tool.unknown` and denied, and Cline loops). The denied-`DROP TABLE` scenario runs in a second throwaway repository that the stub recognises by Cline's system prompt (it carries the working directory). Pure helpers and constants go in `tests/e2e/_cline.py`; an everyday test pins the rendered script's rule sequence against Cline's real request sequence and every scripted call's decision under the policy. **A full headless run was proved during planning against a throwaway responder (Section "Live probe"); no fallback is needed.**

## User Story

As an integrating developer using Cline
I want it to run the same agent task through the harness
So that both target agents are proven, not just one.

## Story Reference

- Story file: `.agents/stories/PRD-017-tool-calling/STORY-017-e2e-cline.md`
- PRD: `.agents/PRDs/PRD-017-tool-calling/PRD.md` (Sections 5 story 1, 7 F11, 11, 14 Risks 1, 4, 7)
- Spike: `.agents/spikes/PRD-017-tool-calling/client-survey.md` ("Driving Cline headlessly (STORY-017)", "Cline CLI 3.0.74: ...")
- Sibling: `.agents/reports/PRD-017-tool-calling/STORY-016-e2e-opencode.report.md`, `tests/e2e/test_opencode.py`, `tests/e2e/_opencode.py`

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY (tests only; no app code) |
| Complexity | HIGH |
| Systems Affected | `tests/e2e/` (new module, helpers, stub script, Cline policy, pinned manifest), `tests/e2e/_live.py` (process helpers moved in), `tests/e2e/test_opencode.py` (imports only), new everyday test, `tests/test_e2e_live.py`, `tests/e2e/scripts/README.md` |
| Story | STORY-017 |
| PRD | PRD-017 |
| Epic Branch | `epic/PRD-017-tool-calling` (commit directly on this branch) |

Dependencies: STORY-001, STORY-014, STORY-016 are all `done` (index).

---

## Live probe (planning phase, 2026-11-16, about 20 min, scratchpad only)

A throwaway SSE responder (`.../scratchpad/cline_probe/responder.py`, never committed) on `127.0.0.1:<free port>` scripted the planned sequence. A driver ran the installed `tests/e2e/.clients/cline/node_modules/@cline/cli-windows-x64/bin/cline.exe` with HOME/USERPROFILE/APPDATA/LOCALAPPDATA/XDG_*/TEMP/TMP set to a scratch directory, `PWD` set to the repository, `OLDPWD`/`INIT_CWD` dropped, no `OPENAI_*`/`OPENROUTER_*`/`ANTHROPIC_*`/`OPENCODE_*`/`AIDER_*`/`CLINE_*` inherited, stdin `DEVNULL`, and every process killed with `taskkill /F /T`. Afterwards there was no `cline.exe` or responder in the process table (`Get-Process`, `Get-CimInstance Win32_Process`; the only `node` there predates the session). `~/.cline` did not exist before or after, and the redirected home stayed empty.

**Verified:**

1. **Everything goes to the loopback base URL.** `cline auth --data-dir <d> --provider openai-compatible --apikey <k> --modelid openai/gpt-4o --baseurl http://127.0.0.1:<port>/v1` (exit 0), then `cline --data-dir <d> --yolo --json -c <repo> -P openai-compatible -m openai/gpt-4o -t <s> "<prompt>"`: every agent request reached `POST /v1/chat/completions` on the responder.
2. **`--data-dir` must be absolute.** A relative `--data-dir` is resolved against the process cwd for `auth` and against the `-c` directory for the run. In the first attempt the run then found no provider config and **called `api.openai.com` with no key** ("You didn't provide an API key"). No key or content left the machine, but the test must pass an absolute `--data-dir` (assert `Path.is_absolute()`).
3. **Request keys** (all 5 task requests): `messages, model, stream, stream_options, tool_choice, tools`; `stream: true`, `stream_options: {include_usage: true}`, `tool_choice: "auto"`, no `parallel_tool_calls`, no `max_tokens`/`temperature`/`store`. Message keys `content, role, tool_call_id, tool_calls`. Tools advertised: **`editor, read_files, run_commands, submit_and_exit`**, also with model id `openai/gpt-4o`. (Cline's `codex-and-gpt-use-apply-patch` routing rule, which swaps `editor` for `apply_patch` when the model id contains `gpt`, applies to act mode only, not to the `--yolo` preset.) Tool `content` is a string (JSON text written by Cline).
4. **Request 1 has two user turns**: the prompt, then Cline's own `[SYSTEM] This run is not complete until you call one of these terminal completion tools: submit_and_exit. ...`. Every text-only answer is followed by another request ending in that same nudge. **The stub's `role: user` matcher (the last user turn) therefore never sees the prompt**, so the prompt cannot pick the scenario. Cline's system prompt (about 4,600 characters, the same length on every request) contains the `-c` working directory, so the scenario is picked by `role: system` + `contains` on the workspace directory name.
5. **The full task ran**: `read_files {"files":[{"path":<abs>/src/calc.py}]}` → `editor {"path":<abs>/src/calc.py,"old_text":"return a - b","new_text":"return a + b"}` → `editor {"path":<abs>/tests/test_calc.py,"old_text":"# placeholder\n","new_text":TEST_WRITTEN}` → `run_commands {"commands":["python -m unittest -q"]}` → `submit_and_exit {"summary":...,"verified":true}`. Exit 0, 5 requests, both files byte-equal to STORY-016's `CALC_EDITED` / `TEST_WRITTEN` (LF kept). `editor` on an **existing** file needs `old_text` (without it Cline errors "already exists"), so the test file is written by replacing the `# placeholder\n` line.
6. **`submit_and_exit.summary` must be at least 10 characters.** `"done"` failed Zod validation, the run did not end, and Cline looped. The run ends on a valid call: NDJSON `{"type":"done","reason":"completed"}` and `{"type":"run_result","finishReason":"completed"}`.
7. **`-t` does not bound the run.** With `-t 10` and a responder that only answers text, Cline sent 984 requests in 60 s and was still running when the driver killed it (the same happened with `-t 90` and a 150 s kill). Pass `-t` as the story asks, but the real bounds are (a) a stub `default` that answers `submit_and_exit`, so no script path ends in text, and (b) `_run_tree`'s own timeout and tree kill.
8. **The drop flow**: a text answer carrying a harness-style note → Cline printed it as an NDJSON `content_start`/`content_end` event with `contentType: "text"` and `text: <note>`, executed nothing, and sent one more request (`..., assistant <note>, user <nudge>`). Answering that with `submit_and_exit` ended the run (exit 0, 2 requests).
9. **Tool results reach the next request** as `role: tool` strings: `read_files` → `[{"query":<path>,"result":"1 | def add(a, b):\n2 |     return a - b","success":true}]`; `editor` → `{"query":"edit:<path>","result":"Edited <path>\n```diff ...`; `run_commands` → `[{"query":"python -m unittest -q","result":"\n[stderr]\n---...\r\nRan 1 test in 0.000s\r\n\r\nOK\r\n","success":true}]`. The unittest output is on stderr and wrapped in JSON with escaped newlines, so STORY-016's `(?m)^OK` does not match; `\bOK\b` does. `run_commands` ran in the `-c` directory (the test was discovered and passed). The session record shows `cwd` and `workspace_root` = the `-c` directory.
10. **NDJSON events** for assertions: `agent_event` with `event.type` `content_start`/`content_end`, `contentType` `tool` (`toolName`, `toolCallId`, `input`; `content_end` carries `output` or `error`) or `text` (`text`); then `done` and `run_result`.

**Not verified during planning (first live run checks them):** the harness's `Authorization` check of Cline's bearer token (the openai-compatible SDK sends `Authorization: Bearer <apikey>`); and Cline's outbound feature-flag fetch: `data/cache/feature-flags.json` appeared (`userId: null`), so Cline contacts its own service at startup. No request content goes there, and no switch to turn it off was found. Record it in the report.

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| none | `.agents/skills/` holds only `frontend-design`; this story has no UI (story Technical Notes: "Skills: none applicable") | none |

---

## Patterns to Follow

### Module shape, opt-in, fixtures (mirror exactly)
```
// SOURCE: tests/e2e/test_opencode.py:84-103, 150-256
pytestmark = pytest.mark.e2e
NONCE = secrets.token_hex(4)
...
@pytest.fixture(scope="module")
def harness(users, stub, child_cwd, child_env, workspace):
    policy = child_cwd / "action_policy.yaml"
    policy.write_text(policy_yaml(repo_root_text(workspace)), encoding="utf-8")
    env = child_env(OPENROUTER_BASE_URL=stub.base, ..., V1_TOOLS_ENABLED="true",
        V1_TOOL_MODELS=HARNESS_MODEL, ACTION_POLICY_FILE=str(policy), MODEL_ALLOWLIST=ALLOWLIST,
        USAGE_REQUESTS_PER_MINUTE="*=unlimited")
```
Users per scenario (`test_opencode.py:188-195`), `seen_rows` / `seen_actions` → `rows.json` / `actions.json` (`:265-306`), `rows(label)` / `actions(label)` via `_live.dump_rows` / `_live.dump_action_decisions` (`:285-306`). Use prefix `e2e017-017` everywhere STORY-016 uses `e2e017-016` (users, temp dirs, container name `harness-libsql-e2e017-017`).

### Running the client: stdin closed, tree killed
```
// SOURCE: tests/e2e/test_opencode.py:116-142
def _run_tree(command: list, cwd: Path, env: dict, timeout: int):
    proc = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.DEVNULL, ...)
    try: out, err = proc.communicate(timeout=timeout)
    except BaseException: _kill_tree(proc); raise
    finally:
        if proc.poll() is None: _kill_tree(proc)
```
Task 2 moves `_kill_tree` / `_run_tree` (and `_git`, `_write_lf`) into `_live.py` as `kill_tree` / `run_tree` / `git` / `write_lf`, so both client modules share one copy.

### Environment isolation and `PWD`
```
// SOURCE: tests/e2e/test_opencode.py:319-346
env = {key: value for key, value in os.environ.items()
       if not key.startswith(("OPENAI_", "OPENROUTER_", "ANTHROPIC_", "OPENCODE_", "AIDER_"))}
env.update(HOME=home, USERPROFILE=home, APPDATA=..., XDG_*=..., TEMP=..., TMP=..., NO_COLOR="1", **extra)
env.pop("OLDPWD", None); env.pop("INIT_CWD", None)
```
Cline adds `CLINE_` to the filtered prefixes and is called with `PWD=<that run's repo>`.

### Pure helpers module with an everyday pin
```
// SOURCE: tests/e2e/_opencode.py:1-10, 44-62
"""... Nothing here is a test or a fixture, and nothing reads the environment, starts a
process or imports `app` ..."""
def render_script(repo_text: str) -> str:
    rendered = SCRIPT.read_text(encoding="utf-8").replace(_PLACEHOLDER, repo_text)
    json.loads(rendered)
```
```
// SOURCE: tests/test_e2e_opencode_script.py:90-111
policy.write_text(_opencode.policy_yaml(_REPO), encoding="utf-8")
monkeypatch.setattr(settings, "ACTION_POLICY_FILE", str(policy))
action_config.load()  # conftest's _default_action_policy restores the policy afterwards
...
assert dict(zip([c.id for c in scripted], decide(*scripted))) == {...}
```

### Stub qualifiers (the matcher reads the last message of `role`)
```
// SOURCE: scripts/stub_openrouter.py:194-211
if self.last_role is not None and (not messages or _role(messages[-1]) != self.last_role): return False
if self.advertises is not None and self.advertises not in request.tool_names: return False
if self.after_call is not None: ... last assistant turn called a tool of this name
subject = _last_text(messages, self.role or "user")
```
`default` may carry `tool_calls` (`_parse_reply` is shared, `scripts/stub_openrouter.py:295`, `:380`).

### The Cline mapping and policy-file replacement rules
```
// SOURCE: app/services/action_adapters.py:543-565
"run_commands": ToolMapping("shell", "commands[]|commands|cmd", format="command"),
"read_files": ToolMapping("fs_read", "files[].path|files[].file_path|files[].filePath"
    "|files.path|files.file_path|files.filePath|file_paths[]|file_paths|paths[]|paths"),
"editor": ToolMapping("fs_write", "path"),
```
`tools:` / `opaque_tools:` / `workspace:` / `shell:` each **replace** the built-in section when present (`app/services/action_config.py:980-986`; `examples/action_policy.yaml:9-16`). YAML tool keys: `kind, target, default, format, extra_targets, optional_targets` (`action_config.py:847-848`). `submit_and_exit` is a `none` row in SOURCES.md (`tests/corpora/actions/SOURCES.md:144`), so it is unmapped: it must go in `opaque_tools` as `allow`, and must not also be under `tools` (`action_config.py:501-506`).

### The note Cline must print
```
// SOURCE: app/services/tool_release.py:41
DENIAL_NOTE_TEMPLATE = "[harness] tool call {name} ({id}) was denied: {reason}"
```
Mirrored in `_opencode.DENIAL_NOTE_TEMPLATE` (`tests/e2e/_opencode.py:39-41`) and pinned against the release step by `tests/test_e2e_opencode_script.py:114-115`. Import it from `_opencode`; do not add a third copy.

### Error / message convention
`pytest.fail` messages name the variable and the recipe, never a value from the run (`test_opencode.py:151-158`). The token never leaves the test: replace it in output (`test_opencode.py:395`) and in the recorded commands (`<harness token>`).

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `tests/e2e/scripts/cline.json` | CREATE | Stub script: Cline's task and drop sequences, every path ending in `submit_and_exit` |
| `tests/e2e/cline/action_policy.yaml` | CREATE | The Cline action policy (F11): `workspace.roots` (`@REPO@`), `shell.allow`, Cline 4.x `tools:`, `opaque_tools: {submit_and_exit: allow}`. STORY-018's docs reference it |
| `tests/e2e/cline/package.json` | CREATE | Pinned manifest (`cline: 3.0.74`, exact) with the install recipe, like `tests/e2e/continue/package.json` |
| `tests/e2e/_cline.py` | CREATE | Constants and pure helpers: paths, rule labels, markers, `render_script`, `policy_yaml`, `cline_executable`, `auth_command`, `run_command` |
| `tests/e2e/test_cline.py` | CREATE | The opt-in E2E module (AC 1-4) |
| `tests/test_e2e_cline_script.py` | CREATE | Everyday pins: rule sequence, scripted arguments, every scripted call's decision, policy file shape |
| `tests/e2e/_live.py` | UPDATE | Add `kill_tree`, `run_tree`, `git`, `write_lf` (moved from `test_opencode.py`) |
| `tests/e2e/test_opencode.py` | UPDATE | Import those four from `_live` and delete the private copies; no test changed |
| `tests/test_e2e_live.py` | UPDATE | One test for `run_tree` (stdin closed, tree killed on timeout) |
| `tests/e2e/scripts/README.md` | UPDATE | One paragraph for `cline.json` |

No `app/` file changes. `test_untouched_app.py` is not needed for that reason, but run it once as a guard (it is cheap).

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: The Cline policy file `tests/e2e/cline/action_policy.yaml`

- **Action**: CREATE.
- **Implement**: A committed, commented YAML (header comment: PRD-017 STORY-017, F11; that `tools:` replaces the built-in mapping wholesale, so only Cline's tools are mapped and every other name is `tool.unknown`; that the file is a template whose `@REPO@` the test replaces with the throwaway repository; that a deployment copies it and writes its own root):
  ```yaml
  workspace:
    roots:
      - "@REPO@"
  shell:
    allow:
      - python -m unittest
  tools:
    # Cline 4.x / CLI 3.0.74 (STORY-001), the same targets as the built-in mapping
    run_commands:      { kind: shell,    target: "commands[]|commands|cmd", format: command }
    read_files:        { kind: fs_read,  target: "files[].path|files[].file_path|files[].filePath|files.path|files.file_path|files.filePath|file_paths[]|file_paths|paths[]|paths" }
    editor:            { kind: fs_write, target: path }
    apply_patch:       { kind: fs_write, target: input, format: patch }
    fetch_web_content: { kind: http,     target: "requests[].url" }
  opaque_tools:
    submit_and_exit: allow   # Cline's loop ends only on this call; denied, Cline asks again forever
  ```
  Comment why `apply_patch` and `fetch_web_content` are there (Cline's act mode advertises them; `--yolo` does not) and that `search_codebase`, `skills`, `ask_question`, `spawn_agent` and `team_*` stay unmapped. Copy the `read_files` alternatives exactly from `action_adapters.py:557-563` (the everyday test compares them).
- **Validate**: Task 5's policy test loads it through `action_config.load()`.

### Task 2: Shared process helpers in `_live.py`

- **Files**: `tests/e2e/_live.py` UPDATE, `tests/e2e/test_opencode.py` UPDATE.
- **Implement**: Move `_git`, `_write_lf`, `_kill_tree`, `_run_tree` (`test_opencode.py:106-142`) into `_live.py` as `git`, `write_lf`, `kill_tree`, `run_tree`, unchanged in behaviour, with docstrings citing PRD-017 STORY-016 (origin) and STORY-017 (shared). In `test_opencode.py` replace the definitions with `_live.` calls (`_live.git(...)`, `_live.run_tree(...)`, `_live.write_lf(...)`). No test function is renamed or removed, so `_DELIBERATELY_SUPERSEDED_TESTS` is untouched.
- **Mirror**: the existing `_live.stop` / `start_stub` docstring style.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/e2e/test_opencode.py tests/test_e2e_live.py -q` (the e2e module skips without `--run-e2e` but must still import).

### Task 3: Stub script `tests/e2e/scripts/cline.json`

- **Action**: CREATE. Rule order matters (first match wins). `@REPO@` appears only inside `arguments` strings, three times (read, edit, write). Ids are scripted and never `call_<digits>`. Every reply that is not a denial ends in a call, so Cline never gets a text answer from the stub.

| # | Label | Qualifiers and matcher | Reply |
|---|-------|------------------------|-------|
| 0 | `DROP_SUBMIT_RULE` | `role: assistant`, `contains: "[harness] tool call"`, `last_role: user`, `advertises: submit_and_exit` | `submit_and_exit` `{"summary":"E2E-CLINE-DROP: the harness denied the call, nothing was run.","verified":true}`, id `call_submit_drop` |
| 1 | `DROP_RULE` | `role: system`, `contains: "e2e017-017-cline-drop"`, `last_role: user`, `advertises: run_commands` | `run_commands` `{"commands":["sqlite3 app.db \"DROP TABLE users\""]}`, id `call_drop` |
| 2 | `START_RULE` | `role: system`, `contains: "e2e017-017-cline-task"`, `last_role: user`, `advertises: read_files` | `read_files` `{"files":[{"path":"@REPO@/src/calc.py"}]}`, id `call_read_calc` |
| 3 | `EDIT_RULE` | `role: tool`, `last_role: tool`, `after_call: read_files`, `contains: "def add"` | `editor` `{"path":"@REPO@/src/calc.py","old_text":"return a - b","new_text":"return a + b"}`, id `call_edit_calc` |
| 4 | `TEST_RULE` | `role: tool`, `last_role: tool`, `after_call: editor`, `contains: "test_calc.py"` | `run_commands` `{"commands":["python -m unittest -q"]}`, id `call_unittest` |
| 5 | `WRITE_RULE` | `role: tool`, `last_role: tool`, `after_call: editor`, `regex: ""` | `editor` `{"path":"@REPO@/tests/test_calc.py","old_text":"# placeholder\n","new_text":<TEST_WRITTEN>}`, id `call_write_test` |
| 6 | `DONE_RULE` | `role: tool`, `last_role: tool`, `after_call: run_commands`, `regex: "\\bOK\\b"`, `advertises: submit_and_exit` | `submit_and_exit` `{"summary":"E2E-CLINE-DONE: add() fixed and the tests pass.","verified":true}`, id `call_submit_done` |
| 7 | `FAILED_RULE` | `role: tool`, `last_role: tool`, `after_call: run_commands`, `regex: ""` | `submit_and_exit` `{"summary":"E2E-CLINE-FAILED: the tests did not pass.","verified":false}`, id `call_submit_failed` |
| default | | | `submit_and_exit` `{"summary":"stub_openrouter: cline.json matched no rule, stopping.","verified":false}`, id `call_submit_default` |

  Notes for the implementer:
  - Rule 4 before rule 5: both follow an `editor` call. The first `editor` result names `src/calc.py`, the second names `tests/test_calc.py` (probe item 9), so the second one goes to the test run.
  - Rule 0 before rule 1: the drop run's second request still has the drop directory in its system prompt and ends on a user turn. Its last assistant turn is the note.
  - The markers in rules 1 and 2 are directory names, created by `tmp_path_factory.mktemp("e2e017-017-cline-task")` / `("e2e017-017-cline-drop")` (pytest appends a digit). They are constants in `_cline.py` (`TASK_DIR`, `DROP_DIR`), and the everyday test checks that the script uses them.
  - `"\\bOK\\b"` in JSON is the regex `\bOK\b`. The unittest output arrives JSON-escaped (probe item 9), so `^OK` would never match.
  - The `new_text` string is `TEST_WRITTEN` JSON-encoded. Generate it with `json.dumps(_opencode.TEST_WRITTEN)` instead of typing it, then check it with Task 5's argument test.
- **Validate**: Task 5's tests.

### Task 4: Constants and helpers `tests/e2e/_cline.py`

- **Action**: CREATE. Same rules as `_opencode.py`: no environment reads, no processes, no `app` import (docstring says so and why, citing `_live.py`).
- **Implement**:
  - `SCRIPT = REPO_ROOT/tests/e2e/scripts/cline.json`, `POLICY = REPO_ROOT/tests/e2e/cline/action_policy.yaml`, `CLIENT_DIR = REPO_ROOT/tests/e2e/.clients/cline`.
  - `CLINE_VERSION = "3.0.74"`, `HARNESS_MODEL = ALLOWLIST = "openai/gpt-4o"`, `TEST_COMMAND = "python -m unittest"`, `RUN_TIMEOUT_SECONDS = 60` (the `-t` value) and `PROCESS_TIMEOUT_SECONDS = 180` (the real bound, probe item 7).
  - `TASK_DIR = "e2e017-017-cline-task"`, `DROP_DIR = "e2e017-017-cline-drop"`.
  - Rule labels `DROP_SUBMIT_RULE, DROP_RULE, START_RULE, EDIT_RULE, TEST_RULE, WRITE_RULE, DONE_RULE, FAILED_RULE = "0".."7"`.
  - `YOLO_TOOLS = ("editor", "read_files", "run_commands", "submit_and_exit")` (probe item 3).
  - Re-export from `_opencode`: `CALC_ORIGINAL, CALC_EDITED, TEST_ORIGINAL, TEST_WRITTEN, DENIAL_NOTE_TEMPLATE, repo_root_text` (the same task, reused, story Technical Notes).
  - `render_script(repo_text)` (the `_opencode.render_script` body over `SCRIPT`; reuse a shared private helper if it reads cleanly, otherwise repeat the 3 lines) and `policy_yaml(repo_text)`: `POLICY.read_text()` with `@REPO@` replaced, and the same check that the path has no quote, backslash or placeholder (`repo_root_text` already does it).
  - `cline_executable(client_dir) -> Path`: the platform binary `node_modules/@cline/cli-<platform>-<arch>/bin/cline(.exe)`, found by globbing `node_modules/@cline/cli-*/bin/cline*` and taking the one file. Run the native binary, not the npm `.cmd` shim (STORY-016 finding: shims are not spawnable from Python). It returns a path and does not check that the file exists; the fixture does.
  - `auth_command(exe, data_dir, base_url, token)` and `run_command(exe, data_dir, repo, prompt)`: the two argv lists from the probe. Each asserts `data_dir.is_absolute()` (probe item 2: a relative one sent the request to `api.openai.com`). `run_command` passes `-t str(RUN_TIMEOUT_SECONDS)`.
  - `INSTALL_RECIPE` string: `npm install --prefix tests/e2e/.clients/cline --save-exact --no-audit --no-fund cline@3.0.74` (equivalently, copy `tests/e2e/cline/package.json` there and `npm install --prefix tests/e2e/.clients/cline`). Never `-g`.
- **Mirror**: `tests/e2e/_opencode.py:12-87`.

### Task 5: Everyday pins `tests/test_e2e_cline_script.py`

- **Action**: CREATE. Mirror `tests/test_e2e_opencode_script.py` (env defaults at the top, `_script()`, `_calls()`, `_body()`, `_assistant()`, `_tool()`, `_label()`).
- **Implement**, with request bodies shaped as the probe recorded them (a `system` turn whose content contains the workspace directory, **two** user turns, prompt then nudge, `tools` = `YOLO_TOOLS`, `tool_choice: "auto"`):
  1. `test_the_rendered_script_answers_cline_s_sequence_with_the_planned_rules`: task request 1 (system names `.../e2e017-017-cline-task0`) → `START_RULE`; plus `read_files` call + tool result with `1 | def add(a, b):` → `EDIT_RULE`; plus `editor` + `{"query":"edit:C:/e2e/.../src/calc.py","result":"Edited ..."}` → `WRITE_RULE`; plus `editor` + result naming `tests/test_calc.py` → `TEST_RULE`; plus `run_commands` + the JSON-escaped unittest output ending `\\r\\nOK\\r\\n` → `DONE_RULE`; the same with `FAILED (failures=1)` → `FAILED_RULE`. Drop request 1 (system names `.../e2e017-017-cline-drop0`) → `DROP_RULE`; drop request 2 (`..., assistant <note>, user <nudge>`) → `DROP_SUBMIT_RULE`. A request whose system prompt names neither directory → `default`, and the default reply is a `submit_and_exit` call.
  2. `test_the_scripted_calls_carry_cline_s_shapes_and_the_planned_paths`: parsed arguments of every scripted call (including the default's) are exactly the Task 3 table; every `submit_and_exit` summary is at least 10 characters (probe item 6); `new_text` equals `_opencode.TEST_WRITTEN`.
  3. `test_the_script_has_no_generated_style_ids_and_only_the_placeholder_for_paths`: as in STORY-016 (`@REPO@` count 3, no `call_\d+` ids, no placeholder after render), and the markers `TASK_DIR` / `DROP_DIR` appear in rules 2 / 1.
  4. `test_the_cline_policy_decides_each_scripted_call_as_planned`: write `_cline.policy_yaml(_REPO)` to `tmp_path`, `monkeypatch.setattr(settings, "ACTION_POLICY_FILE", ...)`, `action_config.load()`, then `action_policy.evaluate_all` over every scripted call (default included):
     `call_drop → ("deny", "sql.ddl")`, `call_read_calc → ("allow", "fs.read")`, `call_edit_calc` and `call_write_test → ("allow", "fs.write_in_workspace")`, `call_unittest → ("allow", "shell.allowlisted")`, every `call_submit_* → ("allow", "tool.opaque")`. Plus the edges: `editor` outside the root → `fs.write_outside_workspace`; `run_commands` `{"commands":["rm -rf /"]}` → whatever the built-in rule gives (assert `deny`); an unmapped Cline name (`ask_question`) → `("deny", "tool.unknown")`. **If any of these differs, the policy or the script is wrong: stop and fix the data, never the expectation.** In particular, confirm that `sqlite3 app.db "DROP TABLE users"` inside `commands[]` (format `command`) still reaches `sql.ddl` as OpenCode's `shell` did.
  5. `test_the_policy_file_maps_cline_s_tools_as_the_built_in_mapping_does`: load the file and assert `policy.tools[name] == BUILT_IN_TOOLS[name]` for the five mapped names, and that `submit_and_exit` is only in `opaque_tools`, so the committed policy cannot drift from STORY-001's mapping.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_e2e_cline_script.py -q`.

### Task 6: Fixtures and runner in `tests/e2e/test_cline.py`

- **Action**: CREATE. Module docstring in the `test_opencode.py:1-50` shape: what runs, the AC map, "what it took to run Cline headless" (probe items 2, 4, 6, 7 and the `-c`/`PWD` handling), isolation, and the run recipe (`docker run -d --name harness-libsql-e2e017-017 -p 8088:8080 ...`, `HARNESS_E2E_LIBSQL_URL=...`, optional `HARNESS_E2E_CLINE=<cline.exe>`, `PYTHONUTF8=1 python -m pytest tests/e2e/test_cline.py -m e2e --run-e2e -v`).
- **Implement** (fixtures module-scoped unless noted):
  - `cline_exe`: `HARNESS_E2E_CLINE` if set, else `_cline.cline_executable(_cline.CLIENT_DIR)`; `pytest.fail` with `INSTALL_RECIPE` when it is not a file. Never whatever `cline` is on PATH.
  - `e2e_db_url`, `child_cwd` (`mktemp("e2e017-017")`), `child_env`, `run_child`, `users` (`task`, `drop`): as in STORY-016.
  - `workspace` (`mktemp(_cline.TASK_DIR)`) and `drop_workspace` (`mktemp(_cline.DROP_DIR)`): one shared builder function `_make_repo(path)` creating STORY-016's layout (`src/__init__.py`, `src/calc.py`, `tests/__init__.py`, `tests/test_calc.py`, `app.db` with one `users` row, git init + config + commit), using `_live.git` / `_live.write_lf`.
  - `stub`: write `render_script(repo_root_text(workspace))` into `child_cwd/cline.json`, `_live.start_stub`.
  - `harness`: `policy_yaml(repo_root_text(workspace))` into `child_cwd/action_policy.yaml`; the same env as STORY-016 (`V1_TOOLS_ENABLED=true`, `V1_TOOL_MODELS`, `MODEL_ALLOWLIST`, `RBAC_ENABLED`, `V1_ENABLED`, `USAGE_REQUESTS_PER_MINUTE="*=unlimited"`).
  - `recorder`: `_live.Recorder(harness.base, keep_tool_names=True)`.
  - `seen_rows`, `seen_actions`, `rows`, `actions`: as in STORY-016, `e2e017-017` in messages.
  - `cline_home` (`mktemp("e2e017-017-cline-home")`) and `_cline_env(home, **extra)`: STORY-016's `_oc_env` without the `OPENCODE_*` settings, plus `CLINE_` among the filtered prefixes, `NO_COLOR=1`, `OLDPWD` / `INIT_CWD` dropped.
  - `cline_runs` (records for AC 4, written to `child_cwd/cline-run.json`): `cline_version` (`[exe, "--version"]`, stdout stripped), `install` (`INSTALL_RECIPE`, `CLIENT_DIR`, `package.json`'s pinned version read from `CLIENT_DIR/package.json`), `env_set` (as STORY-016, plus `PWD`, `--data-dir` = "<temporary directory, absolute>"), `home_cline_dir_exists` `{before, after}` for the **real** home (`Path(os.environ["USERPROFILE" or "HOME"]) / ".cline"` read in the pytest process before the first run and at teardown), and `runs: []`.
  - `run_cline` (function-scoped): `run(label, repo, prompt)`:
    1. `data_dir = cline_home / f"data-{label}"` (absolute; a fresh one per scenario, so no session or provider state carries over).
    2. `auth_command(exe, data_dir, recorder.base + "/v1", token)` via `_live.run_tree(..., cwd=cline_home, env=_cline_env(cline_home), timeout=120)`; assert exit 0 (show redacted output).
    3. `run_command(exe, data_dir, repo, prompt)` via `_live.run_tree(..., cwd=repo, env=_cline_env(cline_home, PWD=str(repo)), timeout=_cline.PROCESS_TIMEOUT_SECONDS)`.
    4. Redact the token from stdout and stderr, parse NDJSON lines into events (skip non-JSON lines), and build `tool_events` (`content_end` with `contentType == "tool"`: `(toolName, toolCallId, "error" in event)`) and `texts` (`content_end` text events, plus `run_result.text`).
    5. Slice `recorder.posts()` and `stub.settle()` as STORY-016 does, and append to `cline_runs["runs"]`: `test`, both commands with the token replaced by `<harness token>`, `exit_code`, `requests` (the shapes), `upstream_rules`, `tool_events`, `streamed`, `finish_reason` (from `run_result`).
  - `_show(run)`: last 3000 characters, ASCII only.
- **Mirror**: `tests/e2e/test_opencode.py:145-422`.

### Task 7: Tests (AC 1-4) in `tests/e2e/test_cline.py`

- `test_the_pinned_cline_is_the_one_that_runs(cline_runs)`: `cline_runs["cline_version"] == "3.0.74"` and the installed `package.json` pins `3.0.74`.
- `test_cline_runs_the_scripted_task_through_the_harness(workspace, run_cline, rows, actions)`: AC 1, AC 2, AC 4.
  - `run = run_cline("task", workspace, f"E2E-CLINE-TASK [{NONCE}] fix add() in src/calc.py, write its test, run the tests")`.
  - `returncode == 0`; `finish_reason == "completed"`; `calc.py` bytes `== CALC_EDITED`, `tests/test_calc.py` bytes `== TEST_WRITTEN`.
  - `tool_events == [("read_files","call_read_calc",False), ("editor","call_edit_calc",False), ("editor","call_write_test",False), ("run_commands","call_unittest",False), ("submit_and_exit","call_submit_done",False)]` (Cline executed every call itself, none failed).
  - `upstream == [START_RULE, EDIT_RULE, WRITE_RULE, TEST_RULE, DONE_RULE]`; `len(posts) == 5`.
  - Every post: `stream is True`, `stream_options_keys == ["include_usage"]`, `model == HARNESS_MODEL`, `tools == "non-empty"`, `tool_choice == "non-empty"` (Cline sends `"auto"`; the shape keeps no value), `"parallel_tool_calls" not in keys`, `tool_names == list(YOLO_TOOLS)` (sorted); `roles[:3] == ["system","user","user"]` on the first; `roles[-1] == "tool"` on posts 2-5.
  - Rows: one per post, `success`, `("v1","code",HARNESS_MODEL)`, `streamed`, `has_tool_calls is True`, `was_duplicate_blocked is False`, `ignored_params == _live.expected_ignored_params(post)`; exactly one `conversation_key`.
  - Decisions: `[("read_files","allow","fs.read"), ("editor","allow","fs.write_in_workspace"), ("editor","allow","fs.write_in_workspace"), ("run_commands","allow","shell.allowlisted"), ("submit_and_exit","allow","tool.opaque")]`; ids in script order; `audit_id`s equal the five rows' ids, in order (each response carried one call).
- `test_a_scripted_drop_table_is_denied_and_cline_reports_it(drop_workspace, run_cline, rows, actions)`: AC 3.
  - `status_before = git status --porcelain`; `run = run_cline("drop", drop_workspace, f"E2E-CLINE-DROP [{NONCE}] clean up the database")`.
  - `returncode == 0`, `finish_reason == "completed"`; `tool_events == [("submit_and_exit","call_submit_drop",False)]` (no file or shell tool ran); `upstream == [DROP_RULE, DROP_SUBMIT_RULE]`, `len(posts) == 2` (no retry storm); `users` still has 1 row; `git status` unchanged.
  - Rows: two, both `v1`/`code`/`success`, `has_tool_calls is True`, not duplicate-blocked.
  - Decisions: `[("run_commands","deny","sql.ddl","call_drop"), ("submit_and_exit","allow","tool.opaque","call_submit_drop")]`, the first joined to row 1, the second to row 2.
  - The note `DENIAL_NOTE_TEMPLATE.format(name="run_commands", id="call_drop", reason=<decision reason>)`, whitespace-normalised, is in the text events (probe item 8).
- `test_zz_every_row_this_module_wrote_is_v1_and_code(cline_exe, rows)`: as in STORY-016.
- `cline_runs` teardown asserts nothing. The report reads `home_cline_dir_exists` from `cline-run.json`.

### Task 8: Pinned manifest, README paragraph, live run

- `tests/e2e/cline/package.json`: `{"name": "harness-e2e-cline", "private": true, "description": "Cline CLI for the PRD-017 STORY-017 E2E (tests/e2e/test_cline.py). Installed into the git-ignored tests/e2e/.clients/cline, never globally: npm install --prefix tests/e2e/.clients/cline --save-exact --no-audit --no-fund cline@3.0.74", "dependencies": {"cline": "3.0.74"}}`. The 157 KB lock stays in the ignored directory. The report records the `cline-3.0.74.tgz` integrity hash from it (`sha512-pCaRaJ6J...`).
- `tests/e2e/scripts/README.md`: one paragraph after `opencode.json`'s: the rules in order, why the scenario is picked from the system prompt (the nudge is the last user turn), why every path ends in `submit_and_exit` and the default is one too (`-t` does not stop Cline), the 10-character summary minimum, `\bOK\b`, and the policy file at `tests/e2e/cline/action_policy.yaml`. Also add `cline.json` to the list in the first paragraph.
- **Live run**: start a throwaway `harness-libsql-e2e017-017` on 8088 (never touch `harness-libsql-dev`), run the module with `--run-e2e -v`, copy `cline-run.json`, `rows.json`, `actions.json` to the scratchpad, remove the container, then check the process table for `cline.exe`, uvicorn and the stub (none left) and that `~/.cline` does not exist.

---

## End-to-End Tests

- [ ] `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_e2e_cline_script.py tests/test_e2e_opencode_script.py tests/test_e2e_live.py tests/test_stub_openrouter.py tests/test_untouched_app.py tests/e2e/test_cline.py tests/e2e/test_opencode.py -q`: everyday tests pass, both e2e modules skip.
- [ ] Live: `HARNESS_E2E_LIBSQL_URL=http://127.0.0.1:8088 PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/e2e/test_cline.py -m e2e --run-e2e -v`: 4 passed.
- [ ] Re-run STORY-016's live module once against the same container (`HARNESS_E2E_OPENCODE=...`), because Task 2 touched its helpers: 4 passed. If OpenCode is unavailable, say so in the report. The everyday import check still covers the refactor.
- [ ] After the runs: no `cline.exe` / uvicorn / stub in `Get-CimInstance Win32_Process`, `~/.cline` absent, container removed, `git status` of the checkout shows only this story's files.

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest <the targeted set above> -q
PYTHONIOENCODING=utf-8 .venv/Scripts/python .agents/scripts/gen_index.py PRD-017   # errors: none
```
Full suite: deferred to orchestrator (user decision).

---

## Risks and mitigations

| Risk | Mitigation |
|------|-----------|
| The harness changes something the stub matches on (system prompt or tool content after the pattern/PII steps, D13), so rules 1/2/3/4/6 miss | Markers are directory names, `def add`, `test_calc.py`, `OK`: no PII, no pattern phrase. The `default` reply is a `submit_and_exit`, so a miss ends the run quickly, and `upstream_rules` in the assertion message shows which rule answered |
| The built-in `code` profile blocks a user turn on an injection phrase in Cline's nudge or system prompt | The `code` profile does not inspect `system`, and the nudge has no listed phrase (`app/services/pattern_config.py:196-246`). If a row shows `suspicious_pattern`, report it, do not change the patterns |
| `run_commands` format `command` classifies `sqlite3 ... "DROP TABLE users"` differently from OpenCode's `shell` | Task 5 checks it in-process before any live run. If it is not `sql.ddl`, stop and report: that is a mapping finding for the orchestrator, not a test to bend |
| `-t` is ignored, so a broken script loops (probe: 984 requests per minute) | Default `submit_and_exit`, `PROCESS_TIMEOUT_SECONDS`, `run_tree` kills the tree, `USAGE_REQUESTS_PER_MINUTE=*=unlimited` keeps the harness from adding 429 retries |
| A relative `--data-dir` sends traffic to `api.openai.com` | `auth_command` / `run_command` assert an absolute path; the fixture builds it from `tmp_path_factory` |
| Cline's startup feature-flag fetch is outbound traffic the test cannot switch off | Recorded in the report; no prompt, token or file content goes there (the agent's requests all reached the loopback URL in the probe). Flag it to the orchestrator for STORY-018's docs |
| Cline's system prompt or the nudge changes in another version | The version is pinned and asserted (`test_the_pinned_cline_is_the_one_that_runs`); the everyday test documents the shapes the script relies on |
| The Task 2 refactor breaks STORY-016's module | Pure move; import check in the everyday run, plus one live re-run if OpenCode is available |
| Windows line endings: `editor` might write CRLF | Probe: LF kept, bytes equal `TEST_WRITTEN`. The assertion compares bytes |

## Fallback (not expected)

The probe proved a full headless run, so no fallback is planned. If the live run against the harness cannot complete (for example, the harness refuses Cline's bearer token or request shape), do not replace the run with a replay. Record in the report which AC is unproved: AC 1 (files changed by Cline) and AC 3's "Cline surfaces the note" need the live client. The everyday test still proves the policy decisions (AC 3's `deny`/`sql.ddl`) and the script sequence. Stop and tell the orchestrator.

## Open questions for the orchestrator

1. **Policy location**: `tests/e2e/cline/action_policy.yaml` (a template with `@REPO@`, beside a pinned `package.json`, mirroring `tests/e2e/continue/`). PRD Section 13 lists `examples/action_policy.cline.yaml` as future work, so it is not created here. OK?
2. **Helper move** (Task 2): moving `_run_tree` & co. from `test_opencode.py` into `_live.py` touches a STORY-016 file (imports only). The alternative is a second copy in `test_cline.py`. The plan picks the move.
3. **Drop decisions**: Cline's drop run makes 2 requests and 2 decisions (`deny sql.ddl`, then `allow tool.opaque` for `submit_and_exit`), where OpenCode made 1. AC 3 only fixes the first. The plan asserts both.

---

## Acceptance Criteria

(Copied from story STORY-017)

- [ ] Given the STORY-016 repository and task, a Cline-specific action policy file (`tools:` mapping Cline's tools per STORY-001, `workspace.roots`, `shell.allow`), and Cline driven headlessly as STORY-001 decided, when Cline runs the task, then both files end with the scripted content. (Task 7 `test_cline_runs_the_scripted_task_through_the_harness`; policy: Task 1, pinned by Task 5)
- [ ] Given that run, when the audit is read, then the same assertions as STORY-016 hold (ingress, profile, `has_tool_calls`, one `conversation_key`, decisions joined by `audit_id`, no duplicate block). (same test)
- [ ] Given the scripted `DROP TABLE` reply, when Cline receives it, then it executes nothing and surfaces the harness note; the decision row is `deny` / `sql.ddl`. (Task 7 `test_a_scripted_drop_table_is_denied_and_cline_reports_it`; in-process: Task 5 test 4)
- [ ] Given the report, when written, then it records the Cline version and how it was installed (local, pinned, never global), the command line, the config, its request keys, and, if STORY-001 found a full headless run impossible, what the fallback proves and what it does not. (`cline-run.json` from Task 6, summarised in the report; no fallback needed, so say so)
- [ ] All tasks completed
- [ ] Backend imports (`from app.main import app`)
- [ ] Follows existing patterns (STORY-016's module, helper and pin structure)
