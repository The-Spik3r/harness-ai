---
story: STORY-020
prd: PRD-023
slug: e2e-opencode-cline
title: "E2E (opt-in): OpenCode and the Cline CLI through `/mcp` against the stub"
type: NEW_CAPABILITY
complexity: medium
epic_branch: epic/PRD-023-mcp-and-skills
created: 2026-11-24
---

# Plan: E2E OpenCode and Cline through `/mcp`

## Summary

One opt-in module, `tests/e2e/test_mcp_clients.py` (`pytestmark = pytest.mark.e2e`, skipped without `--run-e2e` by `tests/conftest.py:230`), runs the installed OpenCode 2.3.2 and Cline CLI 3.0.74 against a real `uvicorn app.main:app` subprocess (`MCP_ENABLED=true`) and the real MCP stub (`tests/mcp_stub.py:107 start_stub`). The model is `scripts/stub_openrouter.py` driven by a scripted JSON (the repo's fake provider). The clients' **model provider points straight at it** (no `/v1` hop) and it answers with the MCP tool call by name. Per client: assert the advertised tool names (via `_live.Recorder(keep_tool_names=True)` in front of the fake provider), one allowed `stub__query` SELECT and one denied DROP TABLE, then the `action_decisions` rows (`surface='mcp'`, `mcp_server='stub'`, decision, rule, outcome) and the stub's call counter (the denied call never reaches it). Cases come from the corpus (`outcome-select-ok.yaml`, `brief-drop-table.yaml`, role `dev`), so decision/rule/outcome are read from the YAML. DB without Docker: an embedded libSQL file through a test-only launcher (Task 2); `HARNESS_E2E_LIBSQL_URL` still works.

- Story: `.agents/stories/PRD-023-mcp-and-skills/STORY-020-e2e-opencode-cline.md`
- PRD sections used: §4 test-infrastructure bullets, §11 MVP definition, F12, R2; STORY-002 report and `tests/corpora/mcp/SOURCES.md:268-345` (client facts)
- Systems affected: tests only. No `app/` change (`tests/test_untouched_app.py` not needed).

## Design Decisions

- **Roles.** The corpus matrix exists only in `tests/mcp_corpus.py:356 configure()` (monkeypatches `authz.ROLE_PERMISSIONS`). A real process gets the same matrix through `RBAC_ROLES_FILE` (`app/services/authz.py:151 load()`: replaces the matrix wholesale, accepts `skill:<id>`). `scripts/manage_users.py:29,144` only creates `admin|auditor|user`, so corpus roles map `dev -> user`, `dba -> admin`, `user -> auditor`. `_mcp.roles_json()` writes: `user` = built-ins + `skill:open-pull-request` + `mcp:connect`; `admin` = built-ins + skill + `mcp:connect` + `action:sql:ddl` (`authz.PERMISSION_ACTION_SQL_DDL`); `auditor` = built-ins + `mcp:connect`. Only `dev` is replayed (both cases), so only `user` users are created; the file stays complete.
- **Server config.** `mcp_config_yaml(stub_url)`: server `stub` (`allow_insecure: true`, `auth: {type: none}`, shape of `examples/mcp.yaml`), skill `open-pull-request` rendered from `mcp_corpus.SKILL` (same tools, so the visible set equals the corpus's). Action policy is `mcp_corpus.POLICY` verbatim. No `v1_aliases` (`/v1` unused).
- **Database.** `Settings` refuses a file URL (`app/config.py:531`), so the harness cannot take one by env. A launcher `tests/e2e/_embedded_db.py` replaces `python` for every child (harness, `manage_users`, row dump). The child env carries `DATABASE_URL=http://127.0.0.1:8080` (placeholder, never connected) and `HARNESS_E2E_DB_FILE=<tmp>/mcp-e2e.db`. The launcher imports `app.config`, assigns `settings.DATABASE_URL = <file>` before anything connects (the trick of `scripts/measure_mcp_latency.py:62-71,226`; `app/db/database.py:198` keys its client on `settings.DATABASE_URL` at call time), then dispatches `-m` (`runpy.run_module`; uvicorn runs in-process, no reload/workers), `-c` (`exec`) or a script path (`runpy.run_path`). If `HARNESS_E2E_LIBSQL_URL` is set it is used instead and no launcher runs (existing recipe). Auth is never touched.
- **Provider wiring.** OpenCode: `provider.harness.options.baseURL = <recorder>/v1` (as `tests/e2e/_opencode.py:80 opencode_config`) plus `mcp.servers.harness`. Cline: `_cline.auth_command(exe, data_dir, recorder.base + "/v1", dummy_key)` plus `<data-dir>/settings/cline_mcp_settings.json`. The harness token goes only into the MCP `Authorization` header.
- **Client MCP entries (STORY-002, `SOURCES.md:274-275`).** OpenCode: `mcp.servers.harness = {type: "remote", url: <harness>/mcp, headers: {Authorization: "Bearer <token>"}, codemode: false}` (no `enabled`; the key is `disabled`). Cline: `{"mcpServers": {"harness": {"type": "streamableHttp", "url", "headers"}}}` (without `type` it falls back to SSE and lists nothing). Model-facing names for server key `harness` (observed): OpenCode `harness_stub__query`, Cline `harness__stub__query`.
- **R2.** If a client cannot list tools with the static header, do not weaken auth, origin or `/mcp`. Report it as unsupported (evidence: logged request sequence) and mark that client's tests `pytest.skip` with the reason only after the orchestrator agrees. Neither CLI sends `Origin` (observed), and neither starts OAuth on a `401`.

## Skills In Use

None (`.agents/skills/` holds only `frontend-design`; no `chat_ui/` change).

## Patterns to Follow

| Category | Source | What to mirror |
|----------|--------|----------------|
| Module layout | `tests/e2e/test_opencode.py:1-100`, `test_cline.py:1-90` | docstring with run recipe, `pytestmark`, module-scoped fixtures, `NONCE` user ids |
| Isolation env | `test_opencode.py:279-306 _oc_env`, `test_cline.py:292 _cline_env` | redirect HOME/XDG/TEMP, drop `OPENAI_*`..., `PWD`, closed stdin (`_live.run_tree`); copy as both modules do |
| Process helpers | `_live.py:133 run_tree`, `:186 create_user`, `:203 dump_action_decisions`, `:241 start_stub`, `:265 start_harness`, `:437 Recorder` | reuse, do not re-implement |
| MCP stub | `tests/mcp_stub.py:107 start_stub`, `StubHandle.calls()/stats()/reset()/stop()` | import as `start_mcp_stub` (clashes with `_live.start_stub`) |
| Corpus | `tests/mcp_corpus.py:321 load_corpus()`, `Case.expect/rule/outcome/arguments_object()` | pick cases by `case.stem` |
| Scripted model | `tests/e2e/scripts/opencode.json`, `cline.json` (`advertises`, `after_call`, `last_role`; Cline picks the scenario from the system prompt's working directory and ends only on `submit_and_exit`, `scripts/README.md:84`) | new scripts |
| Pure-helper test | `tests/test_e2e_cline_realtime_script.py:27-60` | `parse_script` + `select_request` on synthetic bodies; configs loaded by the real loaders |

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `tests/e2e/_mcp.py` | CREATE | pure helpers: constants, `ROLE_MAP`, `roles_json`, `mcp_config_yaml`, `policy_yaml`, `opencode_config`, `cline_settings`, `render_script`, tool-name functions, `pick_cases()` |
| `tests/e2e/_embedded_db.py` | CREATE | the launcher |
| `tests/e2e/scripts/opencode_mcp.json`, `cline_mcp.json` | CREATE | scripted model |
| `tests/e2e/test_mcp_clients.py` | CREATE | the E2E, both clients |
| `tests/test_e2e_mcp_clients_script.py` | CREATE | everyday (non-E2E) unit test of the helpers |
| `tests/e2e/_live.py` | UPDATE | `start_harness(cwd, env, launcher=None)`: when given, argv is `[python, launcher, "-m", "uvicorn", ...]`; default unchanged |
| `tests/e2e/scripts/README.md` | UPDATE | one paragraph per new script |

## Tasks

### Task 1: Probe the embedded DB first (decides the DB path)
After Task 2: run `.venv/Scripts/python tests/e2e/_embedded_db.py -m uvicorn app.main:app --port <free>` with env `DATABASE_URL=http://127.0.0.1:8080 HARNESS_E2E_DB_FILE=<tmp>/p.db OPENROUTER_API_KEY=x ADMIN_TOKEN=x RBAC_ENABLED=false`. `GET /health` must answer 200 (lifespan, `init_db`, `check_bootstrap`). A second launcher child (`-c` dump of `list_action_decisions`) must read the file while the harness runs. If either fails, stop and report to the orchestrator: the alternative is `HARNESS_E2E_LIBSQL_URL` with Docker (down locally).

### Task 2: `tests/e2e/_embedded_db.py`
`parse(argv) -> (mode, target, rest)` (pure) and `main`. `sys.argv` is rebuilt as `python` would: `-c` gives `["-c", *rest]` (`_live.py:40 DUMP` reads `sys.argv[1]`). Requires `HARNESS_E2E_DB_FILE` (absolute path, else `SystemExit` naming the variable) and refuses to run when `HARNESS_E2E_LIBSQL_URL` is set.

### Task 3: `_live.start_harness(..., launcher=None)`
Insert `str(launcher)` after `sys.executable` (`_live.py:265-275`). Validate: `tests/test_e2e_live.py`.

### Task 4: `tests/e2e/_mcp.py` and the two scripts
- Constants: `OPENCODE_VERSION = "v2.3.2"` (not `_opencode.py`'s v2.0.10, which stays), `CASE_ALLOW = "outcome-select-ok"`, `CASE_DENY = "brief-drop-table"`, `OPENCODE_QUERY`/`CLINE_QUERY` as above. Reuse `_opencode.repo_root_text`, `_cline.cline_executable`, `_cline.auth_command`, `_cline.run_command`.
- `visible_tools()` = `stub__*` of `mcp_corpus.SKILL.tools` minus `nope` and `poisoned` (`mcp_corpus.py:46-56`); the advertised set must also exclude `create_branch` (hidden).
- `opencode_mcp.json`: rule `E2E-MCP-DROP` (`last_role: user`, `advertises: harness_stub__query`) -> call DROP; `E2E-MCP-ALLOW` -> SELECT; `after_call: harness_stub__query` + `last_role: tool` -> text `E2E-MCP-DONE`; a final `regex: ""` text rule (title request); `default` text `E2E-MCP-NOT-ADVERTISED` (a missing tool shows as no row). The arguments are substituted from the corpus (`@ARGS_ALLOW@`/`@ARGS_DENY@`, `json.dumps` of the corpus text) so the stub sends the corpus bytes.
- `cline_mcp.json`: scenario by system-prompt working directory (`e2e023-020-cline-allow|drop`, `role: system`, `advertises: harness__stub__query`); `after_call: harness__stub__query` -> `submit_and_exit` (summary at least 10 chars); `default` -> `submit_and_exit`.

### Task 5: `tests/e2e/test_mcp_clients.py`
- Fixtures (module scope): DB choice; `users` (per client two `user`-role users, allow and drop, `NONCE` ids, via `_live.create_user(run, ...)` with `run` prefixing the launcher when embedded); `mcp_stub` (`start_mcp_stub(tmp)`, stopped in `finally`); `op_stub` (`_live.start_stub(script, cwd)`); `recorder` (`Recorder(op_stub.base, keep_tool_names=True)`); `harness` (started after `users`; env `MCP_ENABLED=true`, `MCP_CONFIG_FILE`, `ACTION_POLICY_FILE`, `RBAC_ENABLED=true`, `RBAC_ROLES_FILE`, `OPENROUTER_BASE_URL=op_stub.base`, `OPENROUTER_API_KEY=e2e-unused-key`, `USAGE_REQUESTS_PER_MINUTE="*=unlimited"`); `opencode_exe` (`HARNESS_E2E_OPENCODE`, `test_opencode.py:111`); `cline_exe` (`HARNESS_E2E_CLINE` or local install, `test_cline.py:112`). No audit rows or `/v1` are used.
- Runners: OpenCode `opencode run --standalone --auto --format json -m harness/openai/gpt-4o <marker>` with `OPENCODE_CONFIG_CONTENT`, 300 s (mirror `test_opencode.py:345-378`); Cline `auth`, then write the settings file, then `run_command` in `<tmp>/e2e023-020-cline-<label>`, 180 s (mirror `test_cline.py:373-410`). Redact the token from stored output.
- Tests per client, `test_<client>_lists_the_skills_tools`, `_allowed_call`, `_denied_call` (each run cached per label): (1) the run's request `tool_names` hold the client-prefixed `visible_tools()` and none of `create_branch`, `poisoned`, `nope`; (2) allow: exactly one row for that user with `surface == "mcp"`, `mcp_server == "stub"`, `tool_name == "stub__query"`, `decision`, `rule` (`sql.read`), `outcome` (`ok`) taken from the corpus `dev` entries, and the stub's `query` counter +1; (3) deny: one row `deny` / `sql.ddl` / `outcome is None`, same surface and server, counter unchanged (take counter before and after each run), and the fake provider's last rule label is the after-call one (the agent saw the denial and went on). Read rows after `op_stub.settle()`.
- Teardown writes `mcp-e2e-run.json` (versions, commands with token redacted, request tool names, rows) for the report, like `opencode-run.json`.

### Task 6: `tests/test_e2e_mcp_clients_script.py` (runs in CI: no client, no DB)
Both scripts parse and select the allow/deny/after-call rules on synthetic bodies, including "tool not advertised -> default"; `mcp_config_yaml` loads with `mcp_config.load()` (monkeypatched settings, restored) and yields the corpus skill; `roles_json` loads with `authz.load()` (monkeypatch `ROLE_PERMISSIONS`) and `authz.holds` agrees with `configure()`'s matrix through `ROLE_MAP`; `policy_yaml == mcp_corpus.POLICY`; `opencode_config` has `type remote`, `codemode False`, an `Authorization` header and no `enabled`; `cline_settings` has `streamableHttp`; `pick_cases()` finds both stems with `e2e` true, `dev` allow/deny and rules `sql.read`/`sql.ddl`; launcher `parse()` for the three modes and the missing-variable error.

## End-to-End Tests (the implementer runs them locally)

Both clients are installed here (OpenCode 2.3.2 at `C:/Users/nahue/AppData/Roaming/npm/node_modules/@opencode/cli/bin/opencode.exe`, Cline 3.0.74 under `tests/e2e/.clients/cline`). No Docker needed:

```bash
HARNESS_E2E_OPENCODE="C:/Users/nahue/AppData/Roaming/npm/node_modules/@opencode/cli/bin/opencode.exe" \
PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/e2e/test_mcp_clients.py -m e2e --run-e2e -v -s -p no:cacheprovider
```
Debug per client with `-k opencode` / `-k cline` (one pytest at a time). With Docker, add `HARNESS_E2E_LIBSQL_URL=http://127.0.0.1:8088`. Afterwards `tasklist` must show no `opencode`, `cline`, `python` uvicorn or stub left. Without the flag: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/e2e/test_mcp_clients.py -q` reports all skipped.

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider -m "not db" tests/test_e2e_mcp_clients_script.py tests/test_e2e_live.py tests/test_e2e_marker.py tests/test_e2e_opencode_script.py tests/test_e2e_cline_script.py tests/test_mcp_corpus.py tests/e2e/test_mcp_clients.py
```
No `app/` file is touched, so `tests/test_untouched_app.py` is not needed. No test is renamed.

## Acceptance Criteria -> Tasks -> Tests

| AC | Task(s) | Test that proves it |
|----|---------|---------------------|
| AC1 OpenCode lists tools, one allow, one deny, matching rows | 2-5 | `tests/e2e/test_mcp_clients.py::test_opencode_lists_the_skills_tools`, `::test_opencode_allowed_call`, `::test_opencode_denied_call` (local `--run-e2e`) |
| AC2 Cline, same | 2-5 | `::test_cline_lists_the_skills_tools`, `::test_cline_allowed_call`, `::test_cline_denied_call` |
| AC3 skipped without `--run-e2e` | 5 | `pytestmark = pytest.mark.e2e` with `tests/conftest.py:230` (mechanism pinned by `tests/test_e2e_marker.py`); helpers covered by `tests/test_e2e_mcp_clients_script.py` |

## Risks / open questions

- **Embedded file with a real uvicorn lifespan and cross-process reads is unproven** (only `TestClient` in one process was measured). Task 1 decides; if it fails the E2E cannot run locally without Docker.
- Cline MCP tool approval under `--yolo` is unverified; if it blocks, add `"autoApprove": ["*"]` to its entry and record it.
- The MCP tool names the model sees are STORY-002's observations; if a client differs, fix the constants, never the server.
- Corpus `dev` runs as harness role `user` (test-only matrix, stated in the module docstring).
