"""PRD-023 STORY-020: OpenCode and the Cline CLI use the gateway's skill tools through `/mcp`.

The real OpenCode (2.3.2) and Cline (3.0.74) CLIs run non-interactively against a live
`uvicorn app.main:app` (`MCP_ENABLED=true`) and the real MCP stub (`scripts/stub_mcp_server.py`).
The model is the repository's scripted fake provider (`scripts/stub_openrouter.py`), reached
**directly** by the client (no `/v1` hop through the harness): the harness is only an MCP
server here, with the harness token in the clients' static `Authorization` header. A recording
proxy (`_live.Recorder`, tool names kept) sits in front of the fake provider, so the module
knows which tools each client offered its model.

Two corpus cases are replayed per client (`tests/corpora/mcp/calls`, role `dev`): an allowed
SELECT (`outcome-select-ok`) and a denied DROP TABLE (`brief-drop-table`). The decision, the
rule and the outcome the rows must carry are read from the YAML. The corpus roles exist only in
`mcp_corpus.configure()`, so the harness gets the same matrix through `RBAC_ROLES_FILE` and
the corpus role `dev` runs as the harness role `user` (test-only mapping, `_mcp.ROLE_MAP`).

    AC 1  OpenCode lists the skill's tools, makes one allowed and one denied call, and the
          `action_decisions` rows match (surface mcp, server stub, decision, rule, outcome)
    AC 2  the same for the Cline CLI
    AC 3  skipped without `--run-e2e` (the module's `pytestmark`)

Both clients are given the harness as a streamable-HTTP MCP server with a static
`Authorization` header (STORY-002). If a client cannot do that it is documented as unsupported
(PRD risk R2); nothing here weakens authentication, origin checks or `/mcp`.

**Database.** With `HARNESS_E2E_LIBSQL_URL` set (a throwaway libSQL, the recipe of
`test_opencode.py`) every child uses it. Without it the module needs no Docker: an embedded
libSQL file in a temporary directory, reached by every child through `tests/e2e/_embedded_db.py`.

**Isolation.** As `test_opencode.py` / `test_cline.py`: every home redirected, no provider
variable inherited, closed stdin, every process stopped as a tree in a `finally`. The token is
never printed or stored: it is redacted from every recorded command and output.

Run (skipped without `--run-e2e`):

    HARNESS_E2E_OPENCODE=C:/Users/<you>/AppData/Roaming/npm/node_modules/@opencode/cli/bin/opencode.exe \\
        PYTHONUTF8=1 python -m pytest tests/e2e/test_mcp_clients.py -m e2e --run-e2e -v -s

`-k opencode` / `-k cline` runs one client. `HARNESS_E2E_CLINE=<path to cline.exe>` overrides the
local install (`npm install --prefix tests/e2e/.clients/cline --save-exact cline@3.0.74`).
"""

import json
import os
import secrets
import time
from pathlib import Path

import pytest

from tests.e2e import _cline, _live, _mcp
from tests.mcp_stub import start_stub as start_mcp_stub

pytestmark = pytest.mark.e2e

NONCE = secrets.token_hex(4)
_RECIPE = (
    "docker run -d --name harness-libsql-e2e023-020 -p 8088:8080 -e SQLD_NODE=primary "
    "ghcr.io/tursodatabase/libsql-server:latest, then HARNESS_E2E_LIBSQL_URL=http://127.0.0.1:8088 "
    "(or leave it unset to use the embedded file)"
)
_OPENCODE_RECIPE = (
    "npm's global @opencode/cli, 2.3.2, then "
    "HARNESS_E2E_OPENCODE=C:/Users/<you>/AppData/Roaming/npm/node_modules/@opencode/cli/bin/opencode.exe"
)
#: Never connected to: `Settings` only needs a valid URL, the launcher assigns the file.
_PLACEHOLDER_URL = "http://127.0.0.1:8080"
_LAUNCHER = Path(__file__).with_name("_embedded_db.py")

_LABELS = ("opencode-allow", "opencode-drop", "cline-allow", "cline-drop")
#: Row fields copied into mcp-e2e-run.json. Never an argument, a preview or a result.
_ACTION_FIELDS = (
    "id", "tool_call_id", "tool_name", "surface", "mcp_server", "operation_kind", "decision", "rule",
    "granted_by", "outcome", "duration_ms", "result_bytes", "skills",
)
_TOKEN = "<harness token>"


# --------------------------------------------------------------------------
# Fixtures: clients, database, users, stubs, harness, recorder
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def opencode_exe():
    """`HARNESS_E2E_OPENCODE`, the real `opencode.exe`. Never the shim on PATH."""
    path = os.environ.get("HARNESS_E2E_OPENCODE", "").strip()
    if not path:
        pytest.fail(f"HARNESS_E2E_OPENCODE is not set. Install OpenCode and name its executable: {_OPENCODE_RECIPE}")
    if not Path(path).is_file():
        pytest.fail(f"HARNESS_E2E_OPENCODE does not name a file: {path!r}. {_OPENCODE_RECIPE}")
    return path


@pytest.fixture(scope="module")
def cline_exe():
    """`HARNESS_E2E_CLINE`, or the pinned local install's `cline.exe`. Never whatever `cline` is on PATH."""
    override = os.environ.get("HARNESS_E2E_CLINE", "").strip()
    path = Path(override) if override else _cline.cline_executable(_cline.CLIENT_DIR)
    if not path.is_file():
        pytest.fail(f"Cline is not installed ({'HARNESS_E2E_CLINE' if override else 'tests/e2e/.clients/cline'}). "
                    f"Install it locally, never with -g: {_cline.INSTALL_RECIPE}")
    return path


@pytest.fixture(scope="module")
def work(tmp_path_factory):
    """A directory with no `.env`, so no child reads the developer's settings."""
    return tmp_path_factory.mktemp("e2e023-020")


@pytest.fixture(scope="module")
def database(work):
    """`(env entries, argv prefix)` for every child: the E2E server if set, else an embedded file."""
    if os.environ.get("HARNESS_E2E_LIBSQL_URL", "").strip():
        return _live.child_env(_live.resolve_e2e_db_url(_RECIPE)), (), None
    file = work / "mcp-e2e.db"
    return _live.child_env(_PLACEHOLDER_URL, HARNESS_E2E_DB_FILE=str(file)), (str(_LAUNCHER),), _LAUNCHER


@pytest.fixture(scope="module")
def child_env(database):
    def build(**extra) -> dict:
        return {**database[0], **extra}

    return build


@pytest.fixture(scope="module")
def run_child(work, child_env, database):
    def run(*args: str):
        return _live.run_child(work, child_env(), *database[1], *args)

    return run


@pytest.fixture(scope="module")
def users(run_child):
    """{label: (user_id, token)}: one `user`-role user per client and case, so rows never mix."""
    created = {}
    for label in _LABELS:
        user_id = f"e2e023-020-{label}-{NONCE}"
        created[label] = (user_id, _live.create_user(run_child, user_id, _mcp.ROLE_MAP[_mcp.CORPUS_ROLE]))
    return created


@pytest.fixture(scope="module")
def mcp_stub(work):
    handle = start_mcp_stub(work)
    try:
        yield handle
    finally:
        handle.stop()


@pytest.fixture(scope="module")
def model_stub(work):
    """The scripted fake provider for both clients: the two scripts side by side, told apart by rule label.

    Two stubs, one per client: each script's labels are its own rule indices.
    """
    scripts = {}
    for name, path in (("opencode", _mcp.OPENCODE_SCRIPT), ("cline", _mcp.CLINE_SCRIPT)):
        target = work / f"{name}_mcp.json"
        target.write_text(_mcp.render_script(path), encoding="utf-8")
        scripts[name] = target
    with _live.start_stub(scripts["opencode"], work) as opencode, _live.start_stub(scripts["cline"], work) as cline:
        yield {"opencode": opencode, "cline": cline}


@pytest.fixture(scope="module")
def recorders(model_stub):
    proxies = {name: _live.Recorder(stub.base, keep_tool_names=True) for name, stub in model_stub.items()}
    try:
        yield proxies
    finally:
        for proxy in proxies.values():
            proxy.close()


@pytest.fixture(scope="module")
def harness(users, mcp_stub, model_stub, work, child_env, database):
    """`uvicorn app.main:app` on a free port with `/mcp` on. After `users`: startup refuses an empty users table."""
    (work / "mcp.yaml").write_text(_mcp.mcp_config_yaml(mcp_stub.url), encoding="utf-8")
    (work / "action_policy.yaml").write_text(_mcp.policy_yaml(), encoding="utf-8")
    (work / "roles.json").write_text(_mcp.roles_json(), encoding="utf-8")
    env = child_env(
        MCP_ENABLED="true",
        MCP_CONFIG_FILE=str(work / "mcp.yaml"),
        ACTION_POLICY_FILE=str(work / "action_policy.yaml"),
        RBAC_ENABLED="true",
        RBAC_ROLES_FILE=str(work / "roles.json"),
        OPENROUTER_BASE_URL=model_stub["opencode"].base,
        OPENROUTER_API_KEY="e2e-unused-key",
        USAGE_REQUESTS_PER_MINUTE="*=unlimited",
    )
    with _live.start_harness(work, env, launcher=database[2]) as running:
        yield running


def _say(request, line: str) -> None:
    reporter = request.config.pluginmanager.get_plugin("terminalreporter")
    if reporter is not None:
        reporter.write_line(line)


@pytest.fixture(scope="module")
def record(request, work, harness):
    """The report's record of every client run and every row read, written to mcp-e2e-run.json."""
    data = {"opencode_version": None, "cline_version": None, "runs": [], "rows": {}}
    yield data
    out = work / "mcp-e2e-run.json"
    out.write_text(json.dumps(data, indent=2), encoding="ascii")
    _say(request, f"e2e023-020: run record written to {out}")


@pytest.fixture(scope="module")
def decisions(run_child, users, record):
    """decisions(label) -> that user's `action_decisions` rows, oldest first."""
    def read(label: str) -> list:
        found = _live.dump_action_decisions(run_child, users[label][0])
        record["rows"][label] = [{key: row[key] for key in _ACTION_FIELDS} for row in found]
        return found

    return read


# --------------------------------------------------------------------------
# The two clients' environments and runners
# --------------------------------------------------------------------------


def _client_env(home_dir: Path, drop_prefixes: tuple, **extra) -> dict:
    """A client's environment: nothing inherited that configures a provider, every home redirected."""
    env = {key: value for key, value in os.environ.items() if not key.startswith(drop_prefixes)}
    home = str(home_dir)
    env.update(
        HOME=home,
        USERPROFILE=home,
        APPDATA=str(home_dir / "AppData" / "Roaming"),
        LOCALAPPDATA=str(home_dir / "AppData" / "Local"),
        XDG_CONFIG_HOME=str(home_dir / ".config"),
        XDG_DATA_HOME=str(home_dir / ".local" / "share"),
        XDG_CACHE_HOME=str(home_dir / ".cache"),
        XDG_STATE_HOME=str(home_dir / ".local" / "state"),
        TEMP=str(home_dir / "tmp"),
        TMP=str(home_dir / "tmp"),
        NO_COLOR="1",
        **extra,
    )
    # The clients take their working directory from `PWD` when it is set: callers that run in a
    # directory pass it as PWD, and no other shell variable is kept.
    env.pop("OLDPWD", None)
    env.pop("INIT_CWD", None)
    (home_dir / "tmp").mkdir(parents=True, exist_ok=True)
    return env


def _redact(text: str, token: str) -> str:
    return text.replace(token, _TOKEN)


def _show(text: str) -> str:
    """A client's output for an assertion message, ASCII only (cp1252 console)."""
    return text[-3000:].encode("ascii", "replace").decode("ascii")


class _Run:
    def __init__(self, label, returncode, output, posts, upstream, stub_calls) -> None:
        self.label = label
        self.returncode = returncode
        self.output = output
        self.posts = posts
        self.upstream = upstream
        self.stub_calls = stub_calls  # {tool: calls this run added on the MCP stub}

    def offered(self) -> set:
        """Every tool name the client offered its model, over all its requests."""
        return {name for post in self.posts for name in post.get("tool_names", [])}


@pytest.fixture(scope="module")
def clients(request, work, tmp_path_factory, recorders, model_stub, mcp_stub, users, harness,
            record):
    """clients.run(label) -> _Run, each (client, case) run once and cached."""
    cache: dict = {}
    oc_home = tmp_path_factory.mktemp("e2e023-020-oc-home")
    cl_home = tmp_path_factory.mktemp("e2e023-020-cline-home")
    oc_drop = ("OPENAI_", "OPENROUTER_", "ANTHROPIC_", "OPENCODE_", "AIDER_")
    cl_drop = (*oc_drop, "CLINE_")

    def exe(client: str):
        """The client's executable, resolved on first use so `-k cline` needs no OpenCode (and the reverse)."""
        found = request.getfixturevalue(f"{client}_exe")
        key = f"{client}_version"
        if record[key] is None:
            home, drop = (oc_home, oc_drop) if client == "opencode" else (cl_home, cl_drop)
            record[key] = _live.run_tree([str(found), "--version"], home, _client_env(home, drop), 120)[1].strip()
        return found


    def run_opencode(label: str, prompt: str):
        opencode_exe = exe("opencode")
        token = users[label][1]
        env = _client_env(oc_home, oc_drop, PWD=str(work),
                          OPENCODE_CONFIG_CONTENT=json.dumps(
                              _mcp.opencode_config(recorders["opencode"].base, harness.base, token)))
        command = [opencode_exe, "run", "--standalone", "--auto", "--format", "json", "-m", _mcp.OPENCODE_MODEL, prompt]
        returncode, out, err = _live.run_tree(command, work, env, 300)
        return command, returncode, (out + err)

    def run_cline(label: str, prompt: str):
        cline_exe = exe("cline")
        token = users[label][1]
        data_dir = cl_home / f"data-{label}"
        assert data_dir.is_absolute()
        auth = _mcp.auth_command(cline_exe, data_dir, recorders["cline"].base + "/v1", "e2e-unused-key")
        returncode, out, err = _live.run_tree(auth, cl_home, _client_env(cl_home, cl_drop), 120)
        assert returncode == 0, _redact(out + err, token)[-2000:]
        settings_dir = data_dir / "settings"
        settings_dir.mkdir(parents=True, exist_ok=True)
        (settings_dir / "cline_mcp_settings.json").write_text(
            json.dumps(_mcp.cline_settings(harness.base, token)), encoding="utf-8")
        repo = tmp_path_factory.mktemp(_mcp.CL_DROP_DIR if label.endswith("drop") else _mcp.CL_ALLOW_DIR)
        command = _mcp.run_command(cline_exe, data_dir, repo, prompt)
        returncode, out, err = _live.run_tree(command, repo, _client_env(cl_home, cl_drop, PWD=str(repo)),
                                              _cline.PROCESS_TIMEOUT_SECONDS)
        return command, returncode, (out + err)

    def run(label: str) -> _Run:
        if label in cache:
            return cache[label]
        client, case = label.split("-")
        marker = "E2E-MCP-ALLOW" if case == "allow" else "E2E-MCP-DROP"
        prompt = f"{marker} [{NONCE}] run the scripted stub query"
        recorder, stub = recorders[client], model_stub[client]
        posts_before, upstream_before = len(recorder.posts()), len(stub.settle())
        calls_before = mcp_stub.stats()["calls"]
        command, returncode, output = (run_opencode if client == "opencode" else run_cline)(label, prompt)
        token = users[label][1]
        output = _redact(output, token)
        calls_after = mcp_stub.stats()["calls"]
        stub_calls = {tool: calls_after.get(tool, 0) - calls_before.get(tool, 0) for tool in calls_after}
        result = _Run(label, returncode, output, recorder.posts()[posts_before:], stub.settle()[upstream_before:],
                      {tool: n for tool, n in stub_calls.items() if n})
        record["runs"].append({
            "label": label,
            "command": [_redact(str(part), token) for part in command],
            "exit_code": returncode,
            "request_tool_names": [post.get("tool_names") for post in result.posts],
            "upstream_rules": result.upstream,
            "stub_calls_added": result.stub_calls,
            "output_tail": _show(output),
        })
        cache[label] = result
        return result

    return run


# --------------------------------------------------------------------------
# Assertions shared by both clients
# --------------------------------------------------------------------------


def _expected(case_key: str) -> dict:
    """What the corpus says the `dev` role's call must record."""
    case = _mcp.pick_cases()[case_key]
    return {
        # The row keeps the bare tool name and the server in `mcp_server` (observed; the corpus name is `stub__query`).
        "tool_name": case.name.split("__", 1)[1],
        "decision": case.expect[_mcp.CORPUS_ROLE],
        "rule": case.rule[_mcp.CORPUS_ROLE],
        "outcome": case.outcome[_mcp.CORPUS_ROLE],
    }


def _rows_for(decisions, label: str, expect_outcome) -> list:
    """The label's rows once the outcome the corpus declares has been recorded (it is written after the reply)."""
    deadline = time.monotonic() + 15
    while True:
        found = decisions(label)
        if len(found) == 1 and (expect_outcome is None or found[0]["outcome"] == expect_outcome):
            return found
        if time.monotonic() > deadline:
            return found
        time.sleep(0.5)


def _assert_lists_tools(run: _Run, to_name) -> None:
    offered = run.offered()
    assert run.posts, _show(run.output)
    wanted = {to_name(name) for name in _mcp.visible_tools()}
    assert wanted <= offered, (sorted(wanted - offered), sorted(offered), _show(run.output))
    for bare in _mcp.never_offered():
        assert to_name(bare) not in offered, (bare, sorted(offered))


def _assert_allowed(run: _Run, decisions, label: str) -> None:
    expect = _expected("allow")
    assert expect["decision"] == "allow" and expect["outcome"] == "ok"  # the corpus says what this case is
    [row] = _rows_for(decisions, label, expect["outcome"])
    assert (row["surface"], row["mcp_server"]) == ("mcp", "stub"), row
    assert (row["tool_name"], row["decision"], row["rule"], row["outcome"]) == (
        expect["tool_name"], expect["decision"], expect["rule"], expect["outcome"]), row
    assert run.stub_calls.get("query") == 1, (run.stub_calls, _show(run.output))


def _assert_denied(run: _Run, decisions, label: str, after_rule: str) -> None:
    expect = _expected("deny")
    assert expect["decision"] == "deny" and expect["outcome"] is None
    [row] = _rows_for(decisions, label, None)
    assert (row["surface"], row["mcp_server"]) == ("mcp", "stub"), row
    assert (row["tool_name"], row["decision"], row["rule"], row["outcome"]) == (
        expect["tool_name"], expect["decision"], expect["rule"], expect["outcome"]), row
    assert run.stub_calls.get("query", 0) == 0, run.stub_calls  # the denied call never reached the stub
    # The client sent the harness's denial back to its model, which went on to the scripted closing reply.
    assert run.upstream and run.upstream[-1] == after_rule, (run.upstream, _show(run.output))


# --------------------------------------------------------------------------
# AC 1: OpenCode
# --------------------------------------------------------------------------


def test_opencode_lists_the_skills_tools(clients):
    _assert_lists_tools(clients("opencode-allow"), _mcp.opencode_tool_name)


def test_opencode_allowed_call(clients, decisions):
    run = clients("opencode-allow")
    assert run.returncode == 0, _show(run.output)
    _assert_allowed(run, decisions, "opencode-allow")
    assert run.upstream[-1] == _mcp.OC_AFTER_RULE, (run.upstream, _show(run.output))


def test_opencode_denied_call(clients, decisions):
    run = clients("opencode-drop")
    assert run.returncode == 0, _show(run.output)
    _assert_denied(run, decisions, "opencode-drop", _mcp.OC_AFTER_RULE)


# --------------------------------------------------------------------------
# AC 2: Cline
# --------------------------------------------------------------------------


def test_cline_lists_the_skills_tools(clients):
    _assert_lists_tools(clients("cline-allow"), _mcp.cline_tool_name)


def test_cline_allowed_call(clients, decisions):
    run = clients("cline-allow")
    _assert_allowed(run, decisions, "cline-allow")
    assert run.upstream[-1] == _mcp.CL_AFTER_RULE, (run.upstream, _show(run.output))


def test_cline_denied_call(clients, decisions):
    run = clients("cline-drop")
    _assert_denied(run, decisions, "cline-drop", _mcp.CL_AFTER_RULE)
