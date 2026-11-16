"""PRD-017 STORY-016: OpenCode completes a scripted multi-file task through a live harness.

The real OpenCode CLI (the global npm install, `@opencode/cli`, 2.0.10) runs
non-interactively (`run --standalone --auto --format json`) in a throwaway git
repository. The harness runs as a subprocess with `V1_TOOLS_ENABLED=true` and an
`ACTION_POLICY_FILE` that makes the repository the workspace root and allows
`python -m unittest`, on the STORY-014 stub upstream, behind PRD-015's recording
proxy (`_live.Recorder`, with tool names kept) so the module knows what OpenCode
sent as well as what the harness recorded.

    AC 1  the scripted read, edit, write and test run are executed by OpenCode,
          and both files end with the scripted content
    AC 2  the audit: every row v1 / code, `has_tool_calls`, one conversation_key,
          no duplicate block, and one `action_decisions` row per scripted call,
          joined to its request by `audit_id`
    AC 3  a scripted `shell` `sqlite3 app.db "DROP TABLE users"` is denied
          (`sql.ddl`): OpenCode executes nothing, prints the harness note and exits
    AC 4  opencode-run.json: the version, the command lines, the provider config,
          the request shapes (keys, roles, tool names, streamed) and the exit codes

What it took to run OpenCode non-interactively (STORY-001 found no request at all):

- **`stdin` must be closed** (`subprocess.DEVNULL`). `opencode run` reads a
  non-TTY stdin as part of the message and waits for EOF: an open pipe means no
  request, ever. No TTY is needed.
- The npm shim (`opencode`) is not spawnable from Python: `HARNESS_E2E_OPENCODE`
  names the real `opencode.exe`. Never whatever `opencode` is on PATH.
- Only `run --standalone` and `--version` are ever run. Other commands start
  OpenCode's background service.
- OpenCode asks for a session title first, a request without `tools`.
  `agent.title.disable` turns it off, so each run starts with the agent's request.
- `OPENCODE_DISABLE_MODELS_FETCH=1` and `OPENCODE_DISABLE_AUTOUPDATE=1` keep the
  run offline and on the pinned version.

**Isolation.** `HOME`, `USERPROFILE`, `APPDATA`, `LOCALAPPDATA`, `XDG_*`, `TEMP`
and `TMP` point into a temporary directory, and OpenCode's config is passed only
as `OPENCODE_CONFIG_CONTENT`: nothing is written to the user's home, the
repository holds no token, and no `OPENAI_*`, `OPENROUTER_*`, `ANTHROPIC_*`,
`OPENCODE_*` or `AIDER_*` variable is inherited. Storage is reached only by
children, against `HARNESS_E2E_LIBSQL_URL`. The token is never printed. Every
process the module starts is stopped as a tree, in a `finally`.

Run (skipped without `--run-e2e`):

    docker run -d --name harness-libsql-e2e017-016 -p 8088:8080 -e SQLD_NODE=primary ghcr.io/tursodatabase/libsql-server:latest
    HARNESS_E2E_LIBSQL_URL=http://127.0.0.1:8088 \\
    HARNESS_E2E_OPENCODE=C:/Users/<you>/AppData/Roaming/npm/node_modules/@opencode/cli/bin/opencode.exe \\
        PYTHONUTF8=1 python -m pytest tests/e2e/test_opencode.py -m e2e --run-e2e -v
    docker rm -f harness-libsql-e2e017-016
"""

import json
import os
import secrets
import sqlite3
from pathlib import Path

import pytest

from tests.e2e import _live
from tests.e2e._opencode import (
    ALLOWLIST,
    CALC_EDITED,
    CALC_ORIGINAL,
    DENIAL_NOTE_TEMPLATE,
    DONE_RULE,
    DROP_RULE,
    EDIT_RULE,
    HARNESS_MODEL,
    OPENCODE_MODEL,
    OPENCODE_VERSION,
    START_RULE,
    TEST_ORIGINAL,
    TEST_RULE,
    TEST_WRITTEN,
    WRITE_RULE,
    opencode_config,
    policy_yaml,
    render_script,
    repo_root_text,
)

pytestmark = pytest.mark.e2e

NONCE = secrets.token_hex(4)
_RECIPE = (
    "docker run -d --name harness-libsql-e2e017-016 -p 8088:8080 -e SQLD_NODE=primary "
    "ghcr.io/tursodatabase/libsql-server:latest, then "
    "HARNESS_E2E_LIBSQL_URL=http://127.0.0.1:8088"
)
_OPENCODE_RECIPE = (
    "npm's global @opencode/cli, 2.0.10, then "
    "HARNESS_E2E_OPENCODE=C:/Users/<you>/AppData/Roaming/npm/node_modules/@opencode/cli/bin/opencode.exe"
)

#: Row fields copied into rows.json. Never the token, the prompt or the answer.
_REPORT_FIELDS = (
    "id", "success", "streamed", "ingress", "profile", "model_used", "tokens_used", "conversation_key",
    "ignored_params", "suspicious_pattern", "denied_permission", "error_message",
    "has_tool_calls", "was_duplicate_blocked",
)
_ACTION_FIELDS = ("id", "audit_id", "tool_call_id", "tool_name", "operation_kind", "decision", "rule", "reason")


# --------------------------------------------------------------------------
# Fixtures: database, users, repository, stub, harness, recorder
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
def e2e_db_url():
    return _live.resolve_e2e_db_url(_RECIPE)


@pytest.fixture(scope="module")
def child_cwd(tmp_path_factory):
    """A directory with no `.env`, so no child reads the developer's settings."""
    return tmp_path_factory.mktemp("e2e017-016")


@pytest.fixture(scope="module")
def child_env(e2e_db_url):
    def build(**extra) -> dict:
        return _live.child_env(e2e_db_url, **extra)

    return build


@pytest.fixture(scope="module")
def run_child(child_cwd, child_env):
    def run(*args: str):
        return _live.run_child(child_cwd, child_env(), *args)

    return run


@pytest.fixture(scope="module")
def users(run_child):
    """{label: (user_id, token)}, one user per scenario so row deltas never mix."""
    created = {}
    for label in ("task", "drop"):
        user_id = f"e2e017-016-{label}-{NONCE}"
        created[label] = (user_id, _live.create_user(run_child, user_id))
    return created


@pytest.fixture(scope="module")
def workspace(tmp_path_factory):
    """A throwaway git repository: two files OpenCode changes, `app.db` it must not drop.

    Created before the stub, whose script carries this path.
    """
    path = tmp_path_factory.mktemp("e2e017-016-repo")
    _live.git(path, "init", "-q")
    for key, value in (("user.name", "e2e017-016"), ("user.email", "e2e017-016@example.invalid"),
                       ("core.autocrlf", "false"), ("commit.gpgsign", "false")):
        _live.git(path, "config", key, value)
    _live.write_lf(path / "src" / "__init__.py", "")
    _live.write_lf(path / "src" / "calc.py", CALC_ORIGINAL)
    _live.write_lf(path / "tests" / "__init__.py", "")
    _live.write_lf(path / "tests" / "test_calc.py", TEST_ORIGINAL)
    with sqlite3.connect(path / "app.db") as conn:
        conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
        conn.execute("INSERT INTO users (name) VALUES ('e2e')")
    conn.close()
    _live.git(path, "add", "-A")
    _live.git(path, "commit", "-qm", "init")
    return path


@pytest.fixture(scope="module")
def stub(child_cwd, workspace):
    script = child_cwd / "opencode.json"
    script.write_text(render_script(repo_root_text(workspace)), encoding="utf-8")
    with _live.start_stub(script, child_cwd) as running:
        yield running


@pytest.fixture(scope="module")
def harness(users, stub, child_cwd, child_env, workspace):
    """`uvicorn app.main:app` on a free port. After `users`: startup refuses an empty users table."""
    policy = child_cwd / "action_policy.yaml"
    policy.write_text(policy_yaml(repo_root_text(workspace)), encoding="utf-8")
    env = child_env(
        OPENROUTER_BASE_URL=stub.base,
        OPENROUTER_API_KEY="e2e-unused-key",
        RBAC_ENABLED="true",
        V1_ENABLED="true",
        V1_TOOLS_ENABLED="true",
        V1_TOOL_MODELS=HARNESS_MODEL,
        ACTION_POLICY_FILE=str(policy),
        MODEL_ALLOWLIST=ALLOWLIST,
        USAGE_REQUESTS_PER_MINUTE="*=unlimited",
    )
    with _live.start_harness(child_cwd, env) as running:
        yield running


@pytest.fixture(scope="module")
def recorder(harness):
    proxy = _live.Recorder(harness.base, keep_tool_names=True)
    try:
        yield proxy
    finally:
        proxy.close()


def _say(request, line: str) -> None:
    reporter = request.config.pluginmanager.get_plugin("terminalreporter")
    if reporter is not None:
        reporter.write_line(line)


@pytest.fixture(scope="module")
def seen_rows(request, child_cwd):
    """Every row a test read, keyed by id; written to rows.json for the report."""
    seen: dict = {}
    yield seen
    out = child_cwd / "rows.json"
    out.write_text(json.dumps([seen[key] for key in sorted(seen)], indent=2), encoding="ascii")
    _say(request, f"e2e017-016: {len(seen)} audit rows written to {out}")


@pytest.fixture(scope="module")
def seen_actions(request, child_cwd):
    """Every action decision a test read, keyed by id; written to actions.json for the report."""
    seen: dict = {}
    yield seen
    out = child_cwd / "actions.json"
    out.write_text(json.dumps([seen[key] for key in sorted(seen)], indent=2), encoding="ascii")
    _say(request, f"e2e017-016: {len(seen)} action decisions written to {out}")


@pytest.fixture(scope="module")
def rows(run_child, users, seen_rows):
    """rows(label) -> that user's rows, oldest first."""
    def read(label: str) -> list:
        found = _live.dump_rows(run_child, users[label][0])
        for row in found:
            seen_rows[row["id"]] = {"user": label, **{key: row[key] for key in _REPORT_FIELDS}}
        return found

    return read


@pytest.fixture(scope="module")
def actions(run_child, users, seen_actions):
    """actions(label) -> that user's action decisions, oldest first."""
    def read(label: str) -> list:
        found = _live.dump_action_decisions(run_child, users[label][0])
        for row in found:
            seen_actions[row["id"]] = {"user": label, **{key: row[key] for key in _ACTION_FIELDS}}
        return found

    return read


# --------------------------------------------------------------------------
# Fixtures: OpenCode's home, the runner
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def oc_home(tmp_path_factory):
    return tmp_path_factory.mktemp("e2e017-016-oc-home")


def _oc_env(oc_home: Path, **extra) -> dict:
    """OpenCode's environment: nothing inherited that configures a provider, every home redirected."""
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(("OPENAI_", "OPENROUTER_", "ANTHROPIC_", "OPENCODE_", "AIDER_"))}
    home = str(oc_home)
    env.update(
        HOME=home,
        USERPROFILE=home,
        APPDATA=str(oc_home / "AppData" / "Roaming"),
        LOCALAPPDATA=str(oc_home / "AppData" / "Local"),
        XDG_CONFIG_HOME=str(oc_home / ".config"),
        XDG_DATA_HOME=str(oc_home / ".local" / "share"),
        XDG_CACHE_HOME=str(oc_home / ".cache"),
        XDG_STATE_HOME=str(oc_home / ".local" / "state"),
        TEMP=str(oc_home / "tmp"),
        TMP=str(oc_home / "tmp"),
        OPENCODE_DISABLE_AUTOUPDATE="1",
        OPENCODE_DISABLE_MODELS_FETCH="1",
        NO_COLOR="1",
        **extra,
    )
    # OpenCode takes its working directory from `PWD` when it is set, not from the process's own
    # cwd: a `PWD` inherited from the developer's shell made its `shell` tool run in the harness
    # checkout. Callers that run in a directory pass it as PWD; no other shell variable is kept.
    env.pop("OLDPWD", None)
    env.pop("INIT_CWD", None)
    (oc_home / "tmp").mkdir(exist_ok=True)
    return env


@pytest.fixture(scope="module")
def opencode_runs(request, opencode_exe, oc_home, recorder, child_cwd):
    """The report's record of every OpenCode run (AC 4), written to opencode-run.json."""
    code, out, err = _live.run_tree([opencode_exe, "--version"], oc_home, _oc_env(oc_home), 120)
    version = out.strip()
    record = {
        "opencode_version": version,
        "provider_config": opencode_config(recorder.base, "<harness token>"),
        "env_set": {
            "HOME/USERPROFILE/APPDATA/LOCALAPPDATA/XDG_*/TEMP/TMP": "<temporary directory>",
            "OPENCODE_DISABLE_AUTOUPDATE": "1",
            "OPENCODE_DISABLE_MODELS_FETCH": "1",
            "OPENCODE_CONFIG_CONTENT": "<provider_config, with the real token>",
            "NO_COLOR": "1",
            "stdin": "DEVNULL",
        },
        "runs": [],
    }
    yield record
    out_file = child_cwd / "opencode-run.json"
    out_file.write_text(json.dumps(record, indent=2), encoding="ascii")
    _say(request, f"e2e017-016: OpenCode runs written to {out_file}")


class _OpenCodeRun:
    def __init__(self, returncode: int, output: str, events: list, posts: list, upstream: list) -> None:
        self.returncode = returncode
        self.output = output
        self.events = events
        self.posts = posts
        self.upstream = upstream
        self.tool_uses = [(event["part"]["tool"], event["part"]["state"]["status"])
                          for event in events if event.get("type") == "tool_use"]
        self.texts = [event["part"]["text"] for event in events if event.get("type") == "text"]


@pytest.fixture
def run_opencode(opencode_exe, oc_home, opencode_runs, recorder, stub, users, workspace, request):
    """run_opencode(label, prompt) -> _OpenCodeRun."""
    def run(label: str, prompt: str) -> _OpenCodeRun:
        token = users[label][1]
        env = _oc_env(oc_home, PWD=str(workspace),
                      OPENCODE_CONFIG_CONTENT=json.dumps(opencode_config(recorder.base, token)))
        command = [opencode_exe, "run", "--standalone", "--auto", "--format", "json", "-m", OPENCODE_MODEL, prompt]
        posts_before, upstream_before = len(recorder.posts()), len(stub.settle())
        returncode, out, err = _live.run_tree(command, workspace, env, 300)
        output = (out + err).replace(token, "<harness token>")
        events = []
        for line in output.splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue  # OpenCode's own log lines are not events
            if isinstance(event, dict):
                events.append(event)
        result = _OpenCodeRun(returncode, output, events, recorder.posts()[posts_before:],
                              stub.settle()[upstream_before:])
        opencode_runs["runs"].append({
            "test": request.node.name,
            "command": command,
            "exit_code": returncode,
            "requests": result.posts,
            "upstream_rules": result.upstream,
            "tool_uses": result.tool_uses,
            "streamed": all(post["stream"] is True for post in result.posts),
        })
        return result

    return run


def _show(run: _OpenCodeRun) -> str:
    """OpenCode's output for an assertion message, ASCII only (cp1252 console)."""
    return run.output[-3000:].encode("ascii", "replace").decode("ascii")


def test_the_pinned_opencode_is_the_one_that_runs(opencode_runs):
    """The version in the record is the one this module was written against."""
    assert OPENCODE_VERSION.lstrip("v") in opencode_runs["opencode_version"], opencode_runs["opencode_version"]


# --------------------------------------------------------------------------
# AC 1, AC 2, AC 4: the scripted task
# --------------------------------------------------------------------------


def test_opencode_runs_the_scripted_task_through_the_harness(workspace, run_opencode, rows, actions):
    """AC 1, AC 2 and AC 4."""
    before_rows = {row["id"] for row in rows("task")}
    before_actions = {row["id"] for row in actions("task")}

    run = run_opencode("task", f"E2E-OPENCODE-TASK [{NONCE}] fix add() in src/calc.py, write its test, run the tests")

    assert run.returncode == 0, _show(run)
    assert (workspace / "src" / "calc.py").read_bytes().decode("utf-8") == CALC_EDITED, _show(run)
    assert (workspace / "tests" / "test_calc.py").read_bytes().decode("utf-8") == TEST_WRITTEN, _show(run)
    # OpenCode executed every call itself, none through `execute` (CodeMode).
    assert run.tool_uses == [("read", "completed"), ("edit", "completed"),
                             ("write", "completed"), ("shell", "completed")], _show(run)
    assert any("E2E-OPENCODE-DONE" in text for text in run.texts), _show(run)  # the unittest output ended in OK
    assert run.upstream == [START_RULE, EDIT_RULE, WRITE_RULE, TEST_RULE, DONE_RULE], _show(run)

    assert len(run.posts) == 5
    for post in run.posts:
        assert post["stream"] is True
        assert post["stream_options_keys"] == ["include_usage"]
        assert post["model"] == HARNESS_MODEL
        assert post["tools"] == "non-empty" and post["tool_choice"] == "absent"
        assert "parallel_tool_calls" not in post["keys"]
        assert "execute" in post["tool_names"]
    assert all(post["roles"][-1] == "tool" for post in run.posts[1:])

    written = [row for row in rows("task") if row["id"] not in before_rows]
    assert len(written) == len(run.posts)  # one row per request OpenCode sent
    for row, post in zip(written, run.posts):
        assert row["success"] is True, row
        assert (row["ingress"], row["profile"], row["model_used"]) == ("v1", "code", HARNESS_MODEL)
        assert row["streamed"] is True
        # Requests 1-4 carry the call in the response, request 5 carries them in its history (PRD Section 11).
        assert row["has_tool_calls"] is True
        assert row["was_duplicate_blocked"] is False
        assert row["ignored_params"] == _live.expected_ignored_params(post)
    assert len({row["conversation_key"] for row in written}) == 1, [row["conversation_key"] for row in written]

    decided = [row for row in actions("task") if row["id"] not in before_actions]
    assert [(a["tool_name"], a["decision"], a["rule"]) for a in decided] == [
        ("read", "allow", "fs.read"),
        ("edit", "allow", "fs.write_in_workspace"),
        ("write", "allow", "fs.write_in_workspace"),
        ("shell", "allow", "shell.allowlisted"),
    ]
    assert [a["tool_call_id"] for a in decided] == ["call_read_calc", "call_edit_calc", "call_write_test", "call_unittest"]
    # Each decision belongs to the request whose response carried the call: requests 1-4, in order.
    assert [a["audit_id"] for a in decided] == [row["id"] for row in written[:4]]


# --------------------------------------------------------------------------
# AC 3: a denied DROP TABLE
# --------------------------------------------------------------------------


def test_a_scripted_drop_table_is_denied_and_opencode_reports_it(workspace, run_opencode, rows, actions):
    before_rows = {row["id"] for row in rows("drop")}
    before_actions = {row["id"] for row in actions("drop")}
    status_before = _live.git(workspace, "status", "--porcelain")  # the task test left its two edits in the tree

    run = run_opencode("drop", f"E2E-OPENCODE-DROP [{NONCE}] clean up the database")

    assert run.returncode == 0, _show(run)
    assert run.tool_uses == [], _show(run)  # OpenCode executed nothing
    assert run.upstream == [DROP_RULE] and len(run.posts) == 1, _show(run)  # one request, no retry storm
    with sqlite3.connect(workspace / "app.db") as conn:
        assert conn.execute("SELECT COUNT(*) FROM users").fetchone() == (1,)
    conn.close()
    assert _live.git(workspace, "status", "--porcelain") == status_before  # the denied call changed no file

    [row] = [row for row in rows("drop") if row["id"] not in before_rows]
    assert (row["ingress"], row["profile"], row["success"]) == ("v1", "code", True)
    assert row["has_tool_calls"] is True and row["was_duplicate_blocked"] is False
    [decision] = [a for a in actions("drop") if a["id"] not in before_actions]
    assert (decision["decision"], decision["rule"], decision["tool_name"], decision["tool_call_id"]) == (
        "deny", "sql.ddl", "shell", "call_drop")
    assert decision["audit_id"] == row["id"]
    # The harness's note, as app/services/tool_release.py:41 words it (mirrored in _opencode.py).
    note = DENIAL_NOTE_TEMPLATE.format(name="shell", id="call_drop", reason=decision["reason"])
    assert " ".join(note.split()) in " ".join(" ".join(run.texts).split()), _show(run)


# --------------------------------------------------------------------------
# PRD Section 11: every row this ingress writes
# --------------------------------------------------------------------------


def test_zz_every_row_this_module_wrote_is_v1_and_code(opencode_exe, rows):
    """Named to run last in the module (pytest keeps definition order).

    `opencode_exe` first, so without OpenCode this errors at setup like the rest
    of the module instead of starting children to read rows nobody wrote.
    """
    written = rows("task") + rows("drop")
    assert written
    assert {(row["ingress"], row["profile"]) for row in written} == {("v1", "code")}
