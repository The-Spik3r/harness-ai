---
story: STORY-016
prd: PRD-017
slug: e2e-opencode
title: "E2E: OpenCode completes a scripted multi-file task; a scripted DROP TABLE is denied and reported"
type: NEW_CAPABILITY
complexity: HIGH
epic_branch: epic/PRD-017-tool-calling
created: 2026-11-16
---

# Plan: E2E: OpenCode completes a scripted multi-file task; a scripted DROP TABLE is denied and reported

## Summary

A new opt-in E2E module, `tests/e2e/test_opencode.py`, runs the installed OpenCode 2.0.10 (`opencode run --standalone --auto --format json`) in a throwaway git repository against the live harness: `uvicorn app.main:app` with `V1_TOOLS_ENABLED=true` and an `ACTION_POLICY_FILE` that sets the repository as `workspace.roots` and `shell.allow: [python -m unittest]`, on the STORY-014 stub upstream, behind PRD-015's recording proxy. A new stub script, `tests/e2e/scripts/opencode.json`, drives `read` → `edit` → `write` → `shell python -m unittest -q` → final text over two source files, and a second scenario answers with `shell` `sqlite3 app.db "DROP TABLE users"`, which the harness denies (`sql.ddl`) and OpenCode prints and exits on. The module asserts the files, the audit rows, the `action_decisions` joined by `audit_id`, and writes `opencode-run.json` (version, command line, provider config, request shapes) for the report. **The blocking problem from STORY-001 was diagnosed in this planning phase and a working invocation is named below (Section "Live diagnosis").** An everyday (non-e2e) test pins the rendered script's rule sequence and the rendered policy's decisions in-process, so a policy or stub change fails in the normal suite, not only under `--run-e2e`.

## User Story

As an integrating developer using OpenCode
I want it to run a real agent task through the harness and to report a denied action instead of crashing
So that I can adopt the harness in agent mode.

## Story Reference

- Story file: `.agents/stories/PRD-017-tool-calling/STORY-016-e2e-opencode.md`
- PRD: `.agents/PRDs/PRD-017-tool-calling/PRD.md` (Sections 5 stories 1-2, 7 F11, 11, 14 Risks 1/2/4, 15 D15)
- Spike: `.agents/spikes/PRD-017-tool-calling/client-survey.md`

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY (tests only; no app code) |
| Complexity | HIGH |
| Systems Affected | `tests/e2e/` (new module, new stub script, `_live.py` helpers), `tests/test_e2e_live.py`, new everyday test |
| Story | STORY-016 |
| PRD | PRD-017 |
| Epic Branch | `epic/PRD-017-tool-calling` (commit directly on this branch) |

Dependencies: STORY-001, STORY-014, STORY-015 are all `done` (index).

---

## Live diagnosis (planning phase, 2026-11-16, ≈30 min, scratchpad only)

Done against a throwaway SSE responder on `127.0.0.1:9311` under the session scratchpad (`.../scratchpad/oc/`), with HOME/USERPROFILE/APPDATA/LOCALAPPDATA/XDG_* redirected there. Every process started was killed and checked (`Get-CimInstance Win32_Process`: no `opencode.exe`, no responder left).

**Root cause of STORY-001's "no request in 100 s": stdin.** `opencode run` reads a non-TTY stdin as (part of) the message and waits for EOF. A Python `Popen(..., stdin=subprocess.PIPE)` that never closes the pipe ran 30 s and sent **zero** requests (reproduced). The same command with `stdin` at `/dev/null` (`subprocess.DEVNULL`) sent its request in about 1 s and exited 0. No TTY is needed. The config shape, the provider and the models catalogue were not the problem: `OPENCODE_CONFIG_CONTENT` **and** a project `opencode.json` both worked once stdin was closed.

**Working invocation (verified, exit 0, the tool executed, follow-up request sent):**

```
env (inherited env minus OPENAI_*/OPENROUTER_*/ANTHROPIC_*/OPENCODE_*, plus):
  HOME=USERPROFILE=<oc-home>  APPDATA=<oc-home>\AppData\Roaming  LOCALAPPDATA=<oc-home>\AppData\Local
  XDG_CONFIG_HOME=<oc-home>\.config  XDG_DATA_HOME=<oc-home>\.local\share
  XDG_CACHE_HOME=<oc-home>\.cache    XDG_STATE_HOME=<oc-home>\.local\state
  OPENCODE_DISABLE_AUTOUPDATE=1  OPENCODE_DISABLE_MODELS_FETCH=1
  OPENCODE_CONFIG_CONTENT=<the JSON below>
cwd = <throwaway repo>, stdin = DEVNULL
<...>\npm\node_modules\@opencode\cli\bin\opencode.exe run --standalone --auto --format json -m harness/openai/gpt-4o "<prompt>"
```

```json
{
  "$schema": "https://opencode.ai/config.json",
  "model": "harness/openai/gpt-4o",
  "agent": {"title": {"disable": true}},
  "provider": {
    "harness": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "Harness",
      "options": {"baseURL": "http://127.0.0.1:<port>/v1", "apiKey": "<token>"},
      "models": {"openai/gpt-4o": {"name": "gpt-4o"}}
    }
  }
}
```

Findings, each observed live unless marked:

1. `opencode debug paths` under the redirect puts data, config, cache, state, log and the db under `<oc-home>`. `tmp` stays the system `%TEMP%\opencode`: set `TEMP`/`TMP` to `<oc-home>\tmp` too (untested, harmless).
2. **The npm shim is not spawnable from Python** (`FileNotFoundError` for `opencode`): `opencode` on PATH is a bash/`.cmd` shim. Use the real `opencode.exe` path (as the Aider module uses `HARNESS_E2E_AIDER`): `HARNESS_E2E_OPENCODE=C:/Users/<you>/AppData/Roaming/npm/node_modules/@opencode/cli/bin/opencode.exe`.
3. **Commands without `--standalone` start a background service.** `opencode models` spawned `opencode.exe serve --service` (its `service.json` went to the redirected state dir; it was killed). The module must only call `run --standalone` and `--version`. Never `models`, `debug config`, `service`.
4. **A title request comes first by default.** Without `agent.title.disable`, each run starts with a no-`tools` request (`keys = messages, model, store, stream, stream_options`, roles `system, user`) before the agent request. With `"agent": {"title": {"disable": true}}` only the agent request was sent (verified with a project `opencode.json`. The implementer confirms it under `OPENCODE_CONFIG_CONTENT`, and if it does not hold, the script answers it through `advertises` (below) and the test treats that row like Aider's commit row).
5. **Request keys of the agent request:** `messages, model, store, stream, stream_options, tools`. `stream: true`, `stream_options: {include_usage: true}`, `store: false`. No `tool_choice`, no `parallel_tool_calls`, no `max_tokens`/`temperature`. `store` will be the row's `ignored_params`. No `GET /v1/models` was made.
6. **Tools advertised for model `openai/gpt-4o`** (12): `edit {path, oldString, newString, replaceAll}`, `glob`, `grep`, `question`, `read {path, offset, limit}`, `shell {command, workdir, timeout, background}`, `skill`, `subagent`, `webfetch`, `websearch`, `write {path, content}`, `execute {code}`. `patch` is **not** advertised (the gpt- rule spares `gpt-4*`), so `edit`/`write` are the edit tools.
7. **CodeMode does not intercept direct tools:** scripted `read`, `edit` (`oldString`/`newString`, no prior read needed), `shell` and an absolute forward-slash `read` (`C:/.../a.txt`) were each executed directly (`--format json` prints a `tool_use` event with `"status":"completed"`), and the follow-up request carried roles `system, user, assistant, tool`. No config to disable `execute` is needed: it is advertised but never called unless the model calls it, and it stays `tool.unknown` (deny).
8. **Stream order accepted:** the responder sent role chunk, one complete tool-call fragment, finish chunk, a usage-only chunk (`choices: []`), `[DONE]`, the PRD-015 order STORY-012 keeps. OpenCode accepted it in every run. The live harness run must confirm it (DD-4 note).
9. A text reply (finish `stop`) ends `opencode run` with exit 0. The text is printed on stdout (default format), or as a `{"type":"text", ... "text": ...}` event (`--format json`).
10. Shell on Windows: `shell {"command": "python -c \"print('pass'+'ing')\""}` ran and returned `passing` (exit 0) as the tool content.
11. **Home side effects:** OpenCode watches the real `C:\Users\<you>\.claude\skills` (Claude-compat skills, read only) even with HOME/USERPROFILE redirected. Nothing is written there. The only write to the real home was `~/.local/share/opencode/log/opencode.log`, from the un-redirected `opencode --version` / `--help` at the start of the diagnosis, which the story accepts. `~/.config/opencode` was not touched (its only file dates from 2026-09-19).
12. `OPENCODE_DISABLE_MODELS_FETCH=1` was set in every run. Whether OpenCode blocks offline without it was **not** tested. Keep it set and record it.

Policy decisions for the planned calls, probed in-process (`action_policy.evaluate_all` under a policy file with `workspace.roots: [C:/.../repo]`, `shell.allow: [python -m unittest]`, built-in `tools`): `read` → allow `fs.read`; `edit` / `write` inside the root → allow `fs.write_in_workspace`; `shell python -m unittest -q` → allow `shell.allowlisted`; `shell sqlite3 app.db "DROP TABLE users"` → **deny `sql.ddl`**; `execute` → deny `tool.unknown`; `write` outside the root → deny `fs.write_outside_workspace`.

**Consequence:** no fallback is needed. Every AC can be proved live. Should the live run regress on this machine (e.g. an OpenCode auto-update), the module fails with the captured output; it does not silently downgrade.

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| none | `.agents/skills/` holds only `frontend-design` (UI). This story has no UI; story `skills: []` | none |

---

## Patterns to Follow

### Module shape, opt-in, fixtures (mirror exactly)
```
# SOURCE: tests/e2e/test_aider.py:56-58, 142-170, 190-208
from tests.e2e import _live
pytestmark = pytest.mark.e2e
...
@pytest.fixture(scope="module")
def aider_exe():
    """`HARNESS_E2E_AIDER`, the pinned Aider. Never whatever `aider` is on PATH."""
    path = os.environ.get("HARNESS_E2E_AIDER", "").strip()
    if not path:
        pytest.fail(f"HARNESS_E2E_AIDER is not set. ...")
...
def e2e_db_url():
    return _live.resolve_e2e_db_url(_RECIPE)      # the DB guard: loopback HARNESS_E2E_LIBSQL_URL only
...
def harness(users, stub, child_cwd, child_env):
    env = child_env(OPENROUTER_BASE_URL=stub.base, OPENROUTER_API_KEY="e2e-unused-key", RBAC_ENABLED="true",
                    V1_ENABLED="true", MODEL_ALLOWLIST=_ALLOWLIST, USAGE_REQUESTS_PER_MINUTE="*=unlimited")
    with _live.start_harness(child_cwd, env) as running:
```

### Running the client, recording, redacting the token
```
# SOURCE: tests/e2e/test_aider.py:307-352
env = {key: value for key, value in os.environ.items()
       if not key.startswith(("OPENAI_", "OPENROUTER_", "ANTHROPIC_", "AIDER_"))}
...
posts_before, upstream_before = len(recorder.posts()), len(stub.settle())
proc = subprocess.run(command, cwd=repo, env=env, stdin=subprocess.DEVNULL, capture_output=True,
                      text=True, encoding="utf-8", errors="replace", timeout=300)
output = (proc.stdout + proc.stderr).replace(token, "<harness token>")
```
`stdin=subprocess.DEVNULL` is **required** for OpenCode (Live diagnosis, root cause).

### Audit reads only through children (DB guard)
```
# SOURCE: tests/e2e/_live.py:37-44, 132-136
DUMP = (
    "import dataclasses, json, sys\n"
    "from app.db.database import list_audit_logs\n"
    "rows = list_audit_logs(limit=1000, user_id=sys.argv[1])\n"
    "print(json.dumps([dataclasses.asdict(row) for row in rows]))\n"
)
def dump_rows(run, user_id: str) -> list:
    proc = run("-c", DUMP, user_id)
    ...
    return sorted(json.loads(proc.stdout), key=lambda row: row["id"])
```
`list_action_decisions(limit, user_id, decision, audit_id)`: `app/db/database.py:2329-2369`. `ActionDecisionRow` fields: `app/db/models.py:578-603`. `was_duplicate_blocked`: `app/db/models.py:16,422`. `has_tool_calls`: `app/db/models.py:35,464`.

### Recorder keeps names, never content (pinned)
```
# SOURCE: tests/e2e/_live.py:270-282, tests/test_e2e_live.py:75-96
def request_shape(body: dict) -> dict:
    """What `Recorder` keeps of one request: names, roles and the model. Never content."""
...
assert "SECRET" not in json.dumps(shape)      # including a tool name "SECRET-TOOL"
```
The default shape must stay exactly as pinned. Tool names get an **opt-in** recorder flag (Task 2).

### Policy file in a test, restored afterwards
```
# SOURCE: tests/test_tool_calling_criteria.py:377-378 ; tests/conftest.py:715-726
monkeypatch.setattr(settings, "ACTION_POLICY_FILE", str(_EXAMPLE_POLICY_FILE))
action_config.load()  # conftest's _default_action_policy restores the policy afterwards
```
```
# SOURCE: tests/test_tool_calling_criteria.py:120-126
decisions = action_policy.evaluate_all(
    tuple(ToolCall(c.id, c.name, c.arguments) for c in calls), Identity(_AUTH_USER_ID, "user"))
assert [d.decision for d in decisions] == ["allow"] * len(calls), [(d.rule, d.reason) for d in decisions]
```

### Stub script sequencing
```
# SOURCE: scripts/stub_openrouter.py:184-239 (Rule.matches, Script.select_request), :128-143 (Request.from_body)
# SOURCE: tests/e2e/scripts/tool_loop.json (after_call chain), tests/e2e/scripts/README.md "Scripting an agent loop"
```
The rule label is the rule's index (`select_request`), which `_live.Stub.requests()` reads from the stub's stderr (`tests/e2e/_live.py:150-152`).

### The note OpenCode must print
```
# SOURCE: app/services/tool_release.py:41
DENIAL_NOTE_TEMPLATE = "[harness] tool call {name} ({id}) was denied: {reason}"
```

### Error / message convention
Messages name the location and the rule, never a value (PRD-015 T6/T9). Assertion messages pass OpenCode's output through an ASCII `_show()` with the token replaced (`tests/e2e/test_aider.py:355-357`).

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `tests/e2e/scripts/opencode.json` | CREATE | Stub script: task loop (read → edit → write → shell unittest → text) and the DROP TABLE reply, with an `@REPO@` placeholder for the repository's absolute path |
| `tests/e2e/test_opencode.py` | CREATE | The opt-in E2E module (marker `e2e`), AC 1-4. Also holds the pure render helpers `render_script(repo)` and `policy_yaml(repo)` |
| `tests/test_e2e_opencode_script.py` | CREATE | Everyday (not e2e) pins: the rendered script answers the planned OpenCode request sequence with the planned rules, and the rendered policy decides each scripted call as planned |
| `tests/e2e/_live.py` | UPDATE | `DUMP_ACTIONS` + `dump_action_decisions(run, user_id)`, and an opt-in `Recorder(upstream, keep_tool_names=False)` that adds `tool_names` (function names only) to POST entries |
| `tests/test_e2e_live.py` | UPDATE | Pins: default shape unchanged (existing test untouched); with `keep_tool_names=True` the entry carries the sorted names and still no content; `DUMP_ACTIONS` compiles and names `list_action_decisions` |
| `tests/e2e/scripts/README.md` | UPDATE | One paragraph for `opencode.json` (what each rule answers, the `@REPO@` render, the title rule) |

No app file changes. No `.gitignore` change (OpenCode is the global install; nothing installed).

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: Stub script `tests/e2e/scripts/opencode.json`

- **File**: `tests/e2e/scripts/opencode.json`
- **Action**: CREATE
- **Implement**: Markers are `E2E-OPENCODE-TASK` and `E2E-OPENCODE-DROP` (uppercase, no PII, so the harness's PII step leaves them intact. Tool content reaches the stub after the pattern and PII steps, D13). Rules, in this order (the first match wins):
  0. DROP: `{"regex": "E2E-OPENCODE-DROP", "last_role": "user", "advertises": "shell", "tool_calls": [{"id": "call_drop", "name": "shell", "arguments": "{\"command\":\"sqlite3 app.db \\\"DROP TABLE users\\\"\"}"}]}`. The arguments decode to `{"command": "sqlite3 app.db \"DROP TABLE users\""}` (OpenCode 2.0's `shell`, orchestrator note).
  1. TASK start: `{"regex": "E2E-OPENCODE-TASK", "last_role": "user", "advertises": "shell", "tool_calls": [{"id": "call_read_calc", "name": "read", "arguments": "{\"path\":\"@REPO@/src/calc.py\"}"}]}`
  2. `{"role": "tool", "last_role": "tool", "after_call": "read", "contains": "def add", "tool_calls": [{"id": "call_edit_calc", "name": "edit", "arguments": "{\"path\":\"@REPO@/src/calc.py\",\"oldString\":\"return a - b\",\"newString\":\"return a + b\"}"}]}`
  3. `{"role": "tool", "last_role": "tool", "after_call": "edit", "regex": "", "tool_calls": [{"id": "call_write_test", "name": "write", "arguments": "{\"path\":\"@REPO@/tests/test_calc.py\",\"content\":\"<the scripted test file, JSON-escaped>\"}"}]}`. The second source file is rewritten wholesale (its "scripted content").
  4. `{"role": "tool", "last_role": "tool", "after_call": "write", "regex": "", "tool_calls": [{"id": "call_unittest", "name": "shell", "arguments": "{\"command\":\"python -m unittest -q\"}"}]}`
  5. `{"role": "tool", "last_role": "tool", "after_call": "shell", "regex": "(?m)^OK", "content": "E2E-OPENCODE-DONE: add() fixed and the tests pass."}`
  6. `{"role": "tool", "last_role": "tool", "after_call": "shell", "regex": "", "content": "E2E-OPENCODE-FAILED: the tests did not pass."}`
  7. Title fallback (only matters if finding 4 does not hold): `{"regex": "", "last_role": "user", "content": "E2E OpenCode run"}`. A request without `tools` matches no rule above (each has `advertises`), so it lands here.
  - `default`: `{"content": "stub_openrouter: opencode.json matched no rule, stopping."}`.
  - Scripted ids must not look like `call_<digits>` (stub rule, README). The ones above don't.
  - The `@REPO@` placeholder appears only inside `arguments` strings. `render_script` (Task 3) substitutes a forward-slash path that contains no `"` or `\` (assert it), so the JSON stays valid and `arguments` stays a byte string the stub sends as given (D13).
  - Repository content (Task 3 constants): `src/calc.py` = `def add(a, b):\n    return a - b\n` (scripted end: `return a + b`). `tests/test_calc.py` starts as a placeholder (`# placeholder\n`) and ends as a `unittest` that imports `src.calc` and asserts `add(2, 3) == 5`. Add `src/__init__.py` and `tests/__init__.py` (empty) so `python -m unittest` discovers it from the repository root. Note: the AC says "two source files". The two that change are `src/calc.py` and `tests/test_calc.py`, and the empty `__init__.py` files never change.
- **Mirror**: `tests/e2e/scripts/tool_loop.json` (after_call chain), `tests/e2e/scripts/aider.json` (rule ordering comment in README).
- **Validate**: `.venv/Scripts/python -c "from scripts.stub_openrouter import parse_script; import json,pathlib; parse_script(json.loads(pathlib.Path('tests/e2e/scripts/opencode.json').read_text().replace('@REPO@','C:/x/repo'))); print('OK')"`

### Task 2: `_live.py` helpers (action decisions dump, opt-in tool names)

- **File**: `tests/e2e/_live.py`
- **Action**: UPDATE
- **Implement**:
  - `DUMP_ACTIONS`: the same single-quoted constant style as `DUMP` (`_live.py:39-44`), calling `list_action_decisions(limit=1000, user_id=sys.argv[1])`, then `dataclasses.asdict`, then JSON. `dump_action_decisions(run, user_id) -> list` sorted by `id` (oldest first), shaped like `dump_rows` (`_live.py:132-136`). Docstring: PRD-017 STORY-016, and why it is a child (module docstring: storage only through children against `HARNESS_E2E_LIBSQL_URL`).
  - `Recorder.__init__(self, upstream, keep_tool_names=False)`. When true, `_RecordingHandler.do_POST` adds `"tool_names": sorted(function names in body["tools"])` to the entry (only `tools[].function.name` strings, nothing else). Default False keeps every existing entry byte-identical, so `test_the_shape_keeps_names_roles_and_model_but_no_content` stays unedited. Docstring: tool names are client-defined names, not content. OpenCode's are public (spike). Opt-in because the default contract says no tool names.
  - `request_shape` itself is **not** changed.
- **Mirror**: `tests/e2e/_live.py:37-44`, `:132-136`, `:327-333`, `:339-359`.
- **Validate**: Task 6's test run.

### Task 3: Render helpers and constants in the E2E module

- **File**: `tests/e2e/test_opencode.py`
- **Action**: CREATE (first part)
- **Implement**:
  - Module docstring in the `test_aider.py:1-46` shape: what runs, the AC map (`AC 1` .. `AC 4`), the **Live diagnosis** essentials (stdin must be DEVNULL, `opencode.exe` not the shim, `--standalone` only, title agent disabled, `OPENCODE_DISABLE_MODELS_FETCH`), isolation (redirected HOME/XDG/APPDATA/TEMP; config only through `OPENCODE_CONFIG_CONTENT`, never in the user's home, never in the repository, so the token is never on disk in the repo), and the exact run recipe:
    ```
    docker run -d --name harness-libsql-e2e017-016 -p 8088:8080 -e SQLD_NODE=primary ghcr.io/tursodatabase/libsql-server:latest
    HARNESS_E2E_LIBSQL_URL=http://127.0.0.1:8088 \
    HARNESS_E2E_OPENCODE=C:/Users/<you>/AppData/Roaming/npm/node_modules/@opencode/cli/bin/opencode.exe \
        PYTHONUTF8=1 python -m pytest tests/e2e/test_opencode.py -m e2e --run-e2e -v
    docker rm -f harness-libsql-e2e017-016
    ```
    (A separate throwaway libSQL, as PRD-015's E2E. Never the unit suite's `harness-libsql-dev`.)
  - Constants: `_SCRIPT = .../scripts/opencode.json`, `_ALLOWLIST = _HARNESS_MODEL = "openai/gpt-4o"`, `_OPENCODE_MODEL = "harness/openai/gpt-4o"`, `_OPENCODE_VERSION = "v2.0.10"`, `_TEST_COMMAND = "python -m unittest"`, the rule labels (`_DROP_RULE, _START_RULE, _EDIT_RULE, _WRITE_RULE, _TEST_RULE, _DONE_RULE = "0", "1", "2", "3", "4", "5"`, `_TITLE_RULE = "7"`), `NONCE = secrets.token_hex(4)`, file contents (original and scripted end for `src/calc.py` and `tests/test_calc.py`).
  - Pure helpers (importable by Task 5, no I/O beyond what the caller passes):
    - `repo_root_text(path: Path) -> str`: `path.resolve().as_posix()`. Assert it contains no `"`, `\` or `@REPO@`.
    - `render_script(repo_text: str) -> str`: the committed script text with `@REPO@` replaced. Round-trips through `json.loads`.
    - `policy_yaml(repo_text: str) -> str`: exactly
      ```yaml
      # PRD-017 STORY-016: the E2E action policy (F11). Sections left out keep the built-in ones,
      # including the built-in tool mapping (OpenCode 2.0: shell, read, write, edit with filePath|path).
      # `execute` (CodeMode) is not mapped, so it stays tool.unknown.
      workspace:
        roots:
          - "<repo_text>"
      shell:
        allow:
          - python -m unittest
      ```
    - `opencode_config(base_url: str, token: str) -> dict`: the JSON shown in Live diagnosis (provider id `harness`, `@ai-sdk/openai-compatible`, `options.baseURL = f"{base_url}/v1"`, `apiKey = token`, `models: {"openai/gpt-4o": {"name": "gpt-4o"}}`, `agent.title.disable = true`, `model = _OPENCODE_MODEL`).
- **Mirror**: `tests/e2e/test_aider.py:56-126`.
- **Validate**: `.venv/Scripts/python -c "import tests.e2e.test_opencode as m; print('OK')"` (import only).

### Task 4: Fixtures and runner in the E2E module

- **File**: `tests/e2e/test_opencode.py`
- **Action**: CREATE (second part)
- **Implement**, all module-scoped unless noted, after the `test_aider.py:142-239` pattern:
  - `opencode_exe`: `HARNESS_E2E_OPENCODE`, `pytest.fail` with a recipe if unset or not a file (finding 2). Never `shutil.which("opencode")`.
  - `e2e_db_url` (`_live.resolve_e2e_db_url(_RECIPE)`), `child_cwd` (`tmp_path_factory.mktemp("e2e017-016")`), `child_env`, `run_child`: as Aider.
  - `users`: one user per scenario, `("task", "drop")`, ids `e2e017-016-<label>-<NONCE>`, role `user`.
  - `workspace` (module-scoped, created **before** the stub, because the stub's script carries its path): `tmp_path_factory.mktemp("e2e017-016-repo")`, `git init -q`, `user.name/email`, `core.autocrlf false`, `commit.gpgsign false`, writes `src/__init__.py`, `src/calc.py`, `tests/__init__.py`, `tests/test_calc.py` (LF, `newline="\n"`), and `app.db` created with Python's `sqlite3` holding table `users` (one row), commits all. Returns the path.
  - `stub(child_cwd, workspace)`: writes `render_script(repo_root_text(workspace))` to `child_cwd / "opencode.json"`, then `_live.start_stub(that, child_cwd)`.
  - `harness(users, stub, child_cwd, child_env, workspace)`: writes `policy_yaml(...)` to `child_cwd / "action_policy.yaml"`. Env = Aider's (`test_aider.py:199-206`) plus `V1_TOOLS_ENABLED="true"`, `V1_TOOL_MODELS=_HARNESS_MODEL`, `ACTION_POLICY_FILE=str(policy path)`.
  - `recorder(harness)`: `_live.Recorder(harness.base, keep_tool_names=True)`.
  - `seen_rows` / `rows` (as Aider, `_REPORT_FIELDS` plus `has_tool_calls`, `was_duplicate_blocked`), and `actions(label)` that returns `_live.dump_action_decisions(run_child, user_id)` and copies `id, audit_id, tool_call_id, tool_name, operation_kind, decision, rule, reason` into `seen_actions`, which is written to `actions.json` at teardown.
  - `oc_home` (module-scoped `mktemp("e2e017-016-oc-home")`) and `opencode_runs` (writes `opencode-run.json` at teardown): `{"opencode_version": <stdout of opencode.exe --version run with the redirected env and stdin DEVNULL>, "provider_config": opencode_config(<recorder base>, "<harness token>"), "env_set": {...names only, values for the non-secret flags...}, "runs": []}`. Run `--version` **with the redirected env**, so even its log goes under `oc_home`.
  - `run_opencode(label, prompt)` (function-scoped): env = inherited minus `OPENAI_*`, `OPENROUTER_*`, `ANTHROPIC_*`, `OPENCODE_*`, `AIDER_*`, plus HOME/USERPROFILE/APPDATA/LOCALAPPDATA/XDG_*/TEMP/TMP under `oc_home`, `OPENCODE_DISABLE_AUTOUPDATE=1`, `OPENCODE_DISABLE_MODELS_FETCH=1`, `OPENCODE_CONFIG_CONTENT=json.dumps(opencode_config(recorder.base, token))`, `NO_COLOR=1`. Command `[opencode_exe, "run", "--standalone", "--auto", "--format", "json", "-m", _OPENCODE_MODEL, prompt]`, `cwd=workspace`, **`stdin=subprocess.DEVNULL`**, `capture_output`, `encoding="utf-8", errors="replace"`, `timeout=300`. Replace the token in the output. Parse stdout as NDJSON (skip lines that are not JSON) into `events`. `tool_uses = [(e["part"]["tool"], e["part"]["state"]["status"]) for e in events if e.get("type") == "tool_use"]` and `texts = [e["part"]["text"] for e in events if e.get("type") == "text"]`. Append to `opencode_runs["runs"]`: test name, the command (prompt included, it holds no secret), exit code, `requests` (recorder posts since before), `upstream_rules` (stub labels since before), `tool_uses`, `streamed` (all posts `stream is True`). After the run, assert no `opencode.exe` child is left listening: `subprocess.run` waits for the process itself, and `--standalone`'s private server is in-process. If the implementer sees a leftover, kill it in a `finally` and record it.
  - `_show(run)`: last 3000 chars, ASCII.
- **Mirror**: `tests/e2e/test_aider.py:142-357`.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/e2e/test_opencode.py -q` → all **skipped** (no `--run-e2e`).

### Task 5: Tests (AC 1-4) in the E2E module

- **File**: `tests/e2e/test_opencode.py`
- **Action**: CREATE (third part)
- **Implement**:
  - `test_opencode_runs_the_scripted_task_through_the_harness(workspace, run_opencode, rows, actions)`, **AC 1, AC 2, AC 4**:
    - `run = run_opencode("task", f"E2E-OPENCODE-TASK [{NONCE}] fix add() in src/calc.py, write its test, run the tests")`
    - `run.returncode == 0`. `src/calc.py` and `tests/test_calc.py` equal their scripted end contents (read bytes, LF).
    - `run.tool_uses == [("read","completed"), ("edit","completed"), ("write","completed"), ("shell","completed")]`, so OpenCode executed every call itself and none went through `execute`. The final text event contains `E2E-OPENCODE-DONE`, which also proves the unittest output reached the stub with `OK`.
    - `run.upstream == [_START_RULE, _EDIT_RULE, _WRITE_RULE, _TEST_RULE, _DONE_RULE]` (if finding 4 does not hold under `OPENCODE_CONFIG_CONTENT`, `_TITLE_RULE` leads, and the test then excludes the title row by `post["tools"] == "absent"`. Document whichever holds).
    - Request shape: every agent post has `stream is True`, `stream_options_keys == ["include_usage"]`, `model == _HARNESS_MODEL`, `tools == "non-empty"`, `tool_choice == "absent"`, `"parallel_tool_calls" not in keys`, `"execute" in tool_names`. Roles of posts 2.. end with `"tool"`. Record the observed `keys`, `message_keys` and `tool_names` in `opencode-run.json` (AC 4 is that file, not an assertion on exact keys beyond the above, so a harmless OpenCode key addition fails no test).
    - Audit (AC 2): `written = rows("task")` new since before. `len(written) == len(agent posts)`. For each row: `success`, `(ingress, profile, model_used) == ("v1", "code", _HARNESS_MODEL)`, `streamed`, `has_tool_calls is True` (posts 1-4 carry calls in the response, post 5 carries them in history: PRD Section 11 "request or response"), `was_duplicate_blocked is False`, `ignored_params == _live.expected_ignored_params(post)` (expected `"store"`). `len({row["conversation_key"] for row in written}) == 1`.
      - **Check during implementation:** the D4 dedup key differs per request, but `conversation_key` is the session key (PRD-015), and Aider's session was one key. If the live run shows the key differs per tool turn, stop and report to the orchestrator; do not weaken the assertion silently.
    - Decisions (AC 2): `decided = actions("task")` new since before. Exactly 4. `[(a["tool_name"], a["decision"], a["rule"]) for a in decided] == [("read","allow","fs.read"), ("edit","allow","fs.write_in_workspace"), ("write","allow","fs.write_in_workspace"), ("shell","allow","shell.allowlisted")]`. Each `a["audit_id"]` is the id of the row for the request whose response carried that call (rows 1-4 in order), and `tool_call_id`s equal the scripted ids (`call_read_calc`, ...). The fifth row has no decision.
  - `test_a_scripted_drop_table_is_denied_and_opencode_reports_it(workspace, run_opencode, rows, actions)`, **AC 3**:
    - `run = run_opencode("drop", f"E2E-OPENCODE-DROP [{NONCE}] clean up the database")`
    - `run.returncode == 0`. `run.tool_uses == []` (OpenCode executed nothing). `sqlite3.connect(workspace/"app.db")` still has table `users` with its row (read only). `git status --porcelain` shows no change to tracked files.
    - `run.upstream == [_DROP_RULE]` and `len(run.posts) == 1`: no retry storm, one request.
    - The note: `"[harness] tool call shell (call_drop) was denied: "` in a text event, followed by the row's `reason` (assert the full `DENIAL_NOTE_TEMPLATE.format(name="shell", id="call_drop", reason=decision["reason"])` is a substring of the joined texts. Use the template literal mirrored in the module, with a comment citing `app/services/tool_release.py:41`, not an import: importing `app.services` builds `Settings()` in-process, the reason `_live.py:233-236` gives).
    - `[row] = new rows("drop")`: `ingress v1`, `profile code`, `has_tool_calls True`, `success True`, `was_duplicate_blocked False`. `[decision] = new actions("drop")`: `(decision, rule, tool_name, tool_call_id, audit_id) == ("deny", "sql.ddl", "shell", "call_drop", row["id"])`.
  - `test_zz_every_row_this_module_wrote_is_v1_and_code(opencode_exe, rows)`: as `test_aider.py:484-492`.
- **Mirror**: `tests/e2e/test_aider.py:365-492`. `tests/test_tool_calling_criteria.py:150-193` for the decision row assertions.
- **Validate**: skipped without `--run-e2e`. Live run in Task 7.

### Task 6: Everyday pins (`tests/test_e2e_opencode_script.py`, `tests/test_e2e_live.py`)

- **File**: `tests/test_e2e_opencode_script.py`
- **Action**: CREATE
- **Implement** (no DB, no subprocess. Sets `OPENROUTER_API_KEY` / `ADMIN_TOKEN` defaults like `tests/test_e2e_live.py:11-12` before importing app):
  - `test_the_rendered_script_answers_opencode_s_sequence_with_the_planned_rules`: `script = parse_script(json.loads(render_script("C:/e2e/repo")))`. Build OpenCode-shaped bodies (system + user with the TASK marker and `tools` naming the 12 tools of finding 6), then append assistant `{content: None, tool_calls: [...]}` and `tool` turns with realistic outputs (`"<path>...\n1: def add(a, b):"`, `"Edited ..."`, `"Wrote file successfully."`, `"...\n\nOK"`). Assert `select_request(Request.from_body(body))[0]` walks `"1","2","3","4","5"`, a failing test output (`"FAILED (failures=1)"`) gives `"6"`, the DROP marker gives `"0"`, and a body without `tools` gives `"7"`. Also assert each scripted `arguments` is valid JSON naming `path` under `C:/e2e/repo` (read/edit/write) or the planned `command`.
  - `test_the_rendered_policy_decides_each_scripted_call_as_planned(tmp_path, monkeypatch)`: write `policy_yaml("C:/e2e/repo")` to `tmp_path`, `monkeypatch.setattr(settings, "ACTION_POLICY_FILE", ...)`, `action_config.load()` (conftest's `_default_action_policy` restores it). `evaluate_all` over the script's calls (taken from the parsed script, so the pin follows the file) with `Identity("e2e", "user")` → read `allow/fs.read`, edit and write `allow/fs.write_in_workspace`, shell unittest `allow/shell.allowlisted`, shell DROP `deny/sql.ddl`. Plus `execute` → `deny/tool.unknown` and a `write` outside the root → `deny/fs.write_outside_workspace` (Risk 4: the root is what keeps the absolute paths allowed). This is exactly the planning probe, made permanent.
  - `test_the_script_has_no_generated_style_ids_and_no_backslash_paths`: guards Task 1's constraints.
  - Import the helpers from `tests.e2e.test_opencode`. Its `pytestmark` marks only tests collected from that module, and the import has no side effects (Task 3 keeps the helpers pure, and module import must not read env or start anything).
- **File**: `tests/test_e2e_live.py`
- **Action**: UPDATE (additions only, no existing assertion edited)
- **Implement**: `test_the_recorder_keeps_tool_names_only_when_asked`: two Recorders over the existing fake upstream fixture. Default: entry has no `tool_names` key. `keep_tool_names=True`: `tool_names == ["a", "b"]` for `tools` `[{"function":{"name":"b"}}, {"function":{"name":"a","description":"SECRET"}}]`, and `"SECRET" not in json.dumps(log)`. `test_the_action_dump_reads_list_action_decisions`: `compile(_live.DUMP_ACTIONS, "<dump>", "exec")` and `"list_action_decisions" in _live.DUMP_ACTIONS`.
- **Mirror**: `tests/test_e2e_live.py:160-182`, `tests/test_tool_calling_criteria.py:120-126,377-378`, `tests/test_stub_openrouter.py:482-520`.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_e2e_opencode_script.py tests/test_e2e_live.py tests/e2e/test_opencode.py tests/test_stub_openrouter.py -q` → the two everyday files pass, the e2e module is all skipped, the stub tests pass. Record the counts.

### Task 7: README entry and the live run

- **File**: `tests/e2e/scripts/README.md`
- **Action**: UPDATE. Add an `opencode.json` paragraph after `tool_loop.json`'s: the two markers, the chain `read → edit → write → shell python -m unittest -q → text` on `after_call`, the DROP reply (`shell`, `sqlite3 app.db "DROP TABLE users"`, denied `sql.ddl` by the harness, so OpenCode only sees text), the title fallback rule (requests without `tools`), and the `@REPO@` render (the test writes the rendered copy into its temp dir. The committed file is never loaded as is). Also fix the stale sentence "The client E2E stories (STORY-015 to STORY-018) add their own scripts here: ... `aider.json` (STORY-016)" only if it is touched; it is PRD-015 numbering, so leave it and name the new script as "PRD-017 STORY-016".
- **Live run (required by the story, "run it at least once here")**:
  1. `docker run -d --name harness-libsql-e2e017-016 -p 8088:8080 -e SQLD_NODE=primary ghcr.io/tursodatabase/libsql-server:latest` (a throwaway; if :8088 is taken, pick another port and record it).
  2. `HARNESS_E2E_LIBSQL_URL=http://127.0.0.1:8088 HARNESS_E2E_OPENCODE=C:/Users/nahue/AppData/Roaming/npm/node_modules/@opencode/cli/bin/opencode.exe PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/e2e/test_opencode.py -m e2e --run-e2e -v`
  3. Copy `opencode-run.json`, `rows.json` and `actions.json` (paths printed by the module) into the report. Check none holds the token (grep the token before copying).
  4. `docker rm -f harness-libsql-e2e017-016`. Check no `opencode.exe` and no stub/uvicorn process is left (`Get-CimInstance Win32_Process`).
  5. Confirm `~/.config/opencode` is unchanged (only `service.json` from 2026-09-19) and record it.
- **Validate**: the live run passes 3 tests. If one fails, record the failure and the captured output in the report. Do not change app code to make it pass; tell the orchestrator.

---

## End-to-End Tests

- [ ] Without `--run-e2e`: `tests/e2e/test_opencode.py` is collected and every test skipped (everyday suite unaffected).
- [ ] With `--run-e2e` (Task 7 recipe): AC 1/2/4 test passes. Both files end with the scripted content. OpenCode's JSON events show `read`, `edit`, `write`, `shell` completed. 5 rows, one `conversation_key`, 4 decisions joined by `audit_id`.
- [ ] With `--run-e2e`: AC 3 test passes. No tool executed, the `users` table intact, one request, the harness note in OpenCode's output, `deny`/`sql.ddl` with the row's `audit_id`.
- [ ] Live confirmation of the stream order (DD-4): OpenCode accepted the harness SSE (role, tool-call fragment(s), finish, usage-only chunk, `[DONE]`) in every request. Exit 0 and the follow-up requests are the evidence. Record it.
- [ ] `opencode-run.json` holds the version (`v2.0.10`), the full command line, the provider config with `<harness token>`, the env flags, the per-request keys/roles/message keys/tool names, `streamed`, and the exit codes.

---

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_e2e_opencode_script.py tests/test_e2e_live.py tests/e2e/test_opencode.py tests/test_stub_openrouter.py -q
# live (Task 7):
HARNESS_E2E_LIBSQL_URL=http://127.0.0.1:8088 HARNESS_E2E_OPENCODE=.../opencode.exe PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/e2e/test_opencode.py -m e2e --run-e2e -v
```
Full suite: deferred to the orchestrator (user decision). No app file is touched, so `test_untouched_app.py` is not needed. No test is renamed or removed, so `test_pii_redaction_integration.py` is not needed.

---

## Risks and mitigations

| Risk | Mitigation |
|------|-----------|
| `agent.title.disable` not honoured via `OPENCODE_CONFIG_CONTENT` (verified only via project `opencode.json`) | Rule 7 answers a tool-less request. The test then excludes that row by its shape and documents it. Alternatively write the config to `<oc-home>/.config/opencode/opencode.json` (the redirected global dir, never the real home), which needs a token on disk under the temp home: acceptable, record it |
| `conversation_key` differs per tool turn (would fail AC 2's "one key") | Stop and report. Not weakened silently |
| OpenCode's shell on Windows resolves a different `python` (or none) | `python` is on PATH on this machine (finding 10 ran `python -c`). If unittest fails, rule 6 answers and the test fails with OpenCode's output showing why. Do not switch to `node` without updating `shell.allow` and the policy pin |
| PII step rewrites tool content or the system prompt (paths hold the Windows user name) | Rules match markers and `OK`, never paths. `code` profile entities exclude PERSON/LOCATION (`app/config.py:311`) |
| Pattern step flags OpenCode's long system prompt | Would show as `suspicious_pattern` on the row. Record it. It is a finding for STORY-018's docs, not a code change here |
| OpenCode auto-update / version drift | `OPENCODE_DISABLE_AUTOUPDATE=1`. The test asserts `--version == v2.0.10` and fails with the actual version otherwise. Never upgrade |
| Leftover processes (`--standalone` server, stub, uvicorn) | `subprocess.run` with timeout. `_live.start_*` stop and check ports. Task 7 step 4 checks the process table |
| Real-home side effects | All OpenCode calls (including `--version`) run with the redirected env. Never `models`/`service`/`debug` (finding 3). The `.claude/skills` watch is read-only and recorded |

## Open questions for the orchestrator

1. `tests/test_e2e_opencode_script.py` imports helpers from an e2e module. Acceptable (precedent: criteria suite imports other test modules)? If not, move the three pure helpers into `tests/e2e/_opencode.py`.
2. The test file is `tests/test_calc.py` inside the throwaway repo and counts as the second "source file". The AC's "two source files" are read as the two files that change. Say if a second non-test module is wanted instead (`src/util.py` via `write`, plus the unittest file unchanged).

---

## Acceptance Criteria

(Copied from story STORY-016)

- [ ] Given a throwaway git repository with two source files, the harness on the stub upstream (STORY-014) with `V1_TOOLS_ENABLED=true` and an action policy file setting the repository as `workspace.roots` and a `shell.allow` with the test command, and OpenCode 2.0.10 configured with the harness as an OpenAI-compatible provider, when OpenCode is run non-interactively on the task, then the scripted reads, edits and test run are executed by OpenCode and both files end with the scripted content. **Covered by** `test_opencode_runs_the_scripted_task_through_the_harness` (files, `tool_uses`, rule sequence).
- [ ] Given that run, when the audit is read, then every row has `ingress='v1'`, `profile='code'`, `has_tool_calls=1` where calls flowed, one `conversation_key`, and an `action_decisions` row per scripted call joined by `audit_id`; no row is a duplicate block. **Covered by** the same test's audit and decision assertions (`was_duplicate_blocked` false).
- [ ] Given a script whose next reply is `bash` with `sqlite3 app.db "DROP TABLE users"` (OpenCode 2.0's name: `shell`), when OpenCode receives the response, then it executes nothing, prints (or records in its output) the harness note with the reason, and exits or continues without a crash or retry storm; the decision row is `deny` / `sql.ddl`. **Covered by** `test_a_scripted_drop_table_is_denied_and_opencode_reports_it`.
- [ ] Given the run, when the report is written, then it records the OpenCode version, the full command line, the provider config used, the request keys OpenCode sent (via the recording proxy), whether it streamed, and anything it needed that the harness had to accept. **Covered by** `opencode-run.json` (fixture `opencode_runs`) plus the Live diagnosis findings, copied into the report.
- [ ] All tasks completed
- [ ] Backend imports without error (no app change)
- [ ] Targeted tests pass; full suite deferred to the orchestrator
- [ ] Follows existing patterns (PRD-015 E2E structure, `_live.py` DB guard, marker `e2e`, `--run-e2e`)
