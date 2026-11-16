"""PRD-017 STORY-017: Cline completes the same scripted task through a live harness.

The real Cline CLI (the pinned local install, `cline` 3.0.74, under the git-ignored
`tests/e2e/.clients/cline`) runs headless (`--yolo --json`) in a throwaway git
repository. The harness runs as a subprocess with `V1_TOOLS_ENABLED=true` and the
Cline action policy (`tests/e2e/cline/action_policy.yaml`, with the repository as
the workspace root), on the STORY-014 stub upstream, behind PRD-015's recording
proxy (`_live.Recorder`, with tool names kept). The task, the files and the audit
assertions are STORY-016's (`test_opencode.py`); only the tool shapes are Cline's.

    AC 1  Cline executes the scripted read, edit, edit and test run itself, and
          both files end with the scripted content
    AC 2  the audit: every row v1 / code, `has_tool_calls`, one conversation_key,
          no duplicate block, and one `action_decisions` row per scripted call,
          joined to its request by `audit_id`
    AC 3  a scripted `run_commands` `sqlite3 app.db "DROP TABLE users"` is denied
          (`sql.ddl`): Cline executes nothing and prints the harness note
    AC 4  cline-run.json: the version, how it was installed, the command lines,
          the request shapes (keys, roles, tool names, streamed) and the exit codes

What it took to run Cline headless (STORY-001 found it possible, the planning probe proved it):

- **`--data-dir` must be an absolute temporary directory**, for `auth` and for the run.
  A relative one resolves against different directories, the run then finds no
  provider and calls api.openai.com with no key. Each scenario gets a fresh one.
- Cline's last user turn is its own nudge (`[SYSTEM] This run is not complete until you
  call one of these terminal completion tools: submit_and_exit`), so the stub cannot
  pick the scenario from the prompt. It picks it from the system prompt, which carries
  the `-c` working directory (the directory names in `_cline.TASK_DIR` / `DROP_DIR`).
- Cline's loop ends only on a `submit_and_exit` call (summary of at least 10
  characters). `-t` does not bound the run, so every script path ends in that call,
  and `_live.run_tree` kills the tree after `_cline.PROCESS_TIMEOUT_SECONDS`.
- The native `cline.exe` runs, never the npm shim. `PWD` is set to the repository
  (Cline takes its working directory from the environment), `OLDPWD`/`INIT_CWD` dropped.
- `stdin` is closed (`subprocess.DEVNULL`).

**Isolation.** `HOME`, `USERPROFILE`, `APPDATA`, `LOCALAPPDATA`, `XDG_*`, `TEMP` and
`TMP` point into a temporary directory, the config lives only in `--data-dir`, and no
`OPENAI_*`, `OPENROUTER_*`, `ANTHROPIC_*`, `OPENCODE_*`, `AIDER_*` or `CLINE_*` variable
is inherited. Cline contacts its own service for feature flags at startup (no request
content goes there, and no switch was found): recorded in the report. Storage is
reached only by children, against `HARNESS_E2E_LIBSQL_URL`. The token is never printed.
Every process the module starts is stopped as a tree, in a `finally`.

Run (skipped without `--run-e2e`):

    npm install --prefix tests/e2e/.clients/cline --save-exact --no-audit --no-fund cline@3.0.74
    docker run -d --name harness-libsql-e2e017-017 -p 8088:8080 -e SQLD_NODE=primary ghcr.io/tursodatabase/libsql-server:latest
    HARNESS_E2E_LIBSQL_URL=http://127.0.0.1:8088 \\
        PYTHONUTF8=1 python -m pytest tests/e2e/test_cline.py -m e2e --run-e2e -v
    docker rm -f harness-libsql-e2e017-017

`HARNESS_E2E_CLINE=<path to cline.exe>` overrides the local install.
"""

import json
import os
import secrets
import sqlite3
from pathlib import Path

import pytest

from tests.e2e import _cline, _live
from tests.e2e._cline import (
    ALLOWLIST,
    CALC_EDITED,
    CALC_ORIGINAL,
    DENIAL_NOTE_TEMPLATE,
    DONE_RULE,
    DROP_RULE,
    DROP_SUBMIT_RULE,
    EDIT_RULE,
    HARNESS_MODEL,
    START_RULE,
    TEST_ORIGINAL,
    TEST_RULE,
    TEST_WRITTEN,
    WRITE_RULE,
    YOLO_TOOLS,
    auth_command,
    policy_yaml,
    render_script,
    repo_root_text,
    run_command,
)

pytestmark = pytest.mark.e2e

NONCE = secrets.token_hex(4)
_RECIPE = (
    "docker run -d --name harness-libsql-e2e017-017 -p 8088:8080 -e SQLD_NODE=primary "
    "ghcr.io/tursodatabase/libsql-server:latest, then "
    "HARNESS_E2E_LIBSQL_URL=http://127.0.0.1:8088"
)

#: Row fields copied into rows.json. Never the token, the prompt or the answer.
_REPORT_FIELDS = (
    "id", "success", "streamed", "ingress", "profile", "model_used", "tokens_used", "conversation_key",
    "ignored_params", "suspicious_pattern", "denied_permission", "error_message",
    "has_tool_calls", "was_duplicate_blocked",
)
_ACTION_FIELDS = ("id", "audit_id", "tool_call_id", "tool_name", "operation_kind", "decision", "rule", "reason")


# --------------------------------------------------------------------------
# Fixtures: Cline, database, users, repositories, stub, harness, recorder
# --------------------------------------------------------------------------


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
def e2e_db_url():
    return _live.resolve_e2e_db_url(_RECIPE)


@pytest.fixture(scope="module")
def child_cwd(tmp_path_factory):
    """A directory with no `.env`, so no child reads the developer's settings."""
    return tmp_path_factory.mktemp("e2e017-017")


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
        user_id = f"e2e017-017-{label}-{NONCE}"
        created[label] = (user_id, _live.create_user(run_child, user_id))
    return created


def _make_repo(path: Path) -> Path:
    """A throwaway git repository: two files Cline changes, `app.db` it must not drop."""
    _live.git(path, "init", "-q")
    for key, value in (("user.name", "e2e017-017"), ("user.email", "e2e017-017@example.invalid"),
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
def workspace(tmp_path_factory):
    """The task repository. Created before the stub, whose script carries this path.

    The directory name is what the stub recognises the scenario by (`_cline.TASK_DIR`).
    """
    return _make_repo(tmp_path_factory.mktemp(_cline.TASK_DIR))


@pytest.fixture(scope="module")
def drop_workspace(tmp_path_factory):
    """The drop repository (`_cline.DROP_DIR`): a second one, so Cline's system prompt names it."""
    return _make_repo(tmp_path_factory.mktemp(_cline.DROP_DIR))


@pytest.fixture(scope="module")
def stub(child_cwd, workspace, drop_workspace):
    script = child_cwd / "cline.json"
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
    _say(request, f"e2e017-017: {len(seen)} audit rows written to {out}")


@pytest.fixture(scope="module")
def seen_actions(request, child_cwd):
    """Every action decision a test read, keyed by id; written to actions.json for the report."""
    seen: dict = {}
    yield seen
    out = child_cwd / "actions.json"
    out.write_text(json.dumps([seen[key] for key in sorted(seen)], indent=2), encoding="ascii")
    _say(request, f"e2e017-017: {len(seen)} action decisions written to {out}")


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
# Fixtures: Cline's home, the runner
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def cline_home(tmp_path_factory):
    path = tmp_path_factory.mktemp("e2e017-017-cline-home")
    assert path.is_absolute()
    return path


def _cline_env(home_dir: Path, **extra) -> dict:
    """Cline's environment: nothing inherited that configures a provider, every home redirected."""
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(("OPENAI_", "OPENROUTER_", "ANTHROPIC_", "OPENCODE_", "AIDER_", "CLINE_"))}
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
    # Cline takes its working directory from `PWD` when it is set (as OpenCode does): a `PWD`
    # inherited from the developer's shell would point it at the harness checkout. Callers that
    # run in a directory pass it as PWD; no other shell variable is kept.
    env.pop("OLDPWD", None)
    env.pop("INIT_CWD", None)
    (home_dir / "tmp").mkdir(exist_ok=True)
    return env


def _real_cline_dir() -> Path:
    return Path(os.environ.get("USERPROFILE") or os.environ.get("HOME") or "~").expanduser() / ".cline"


@pytest.fixture(scope="module")
def cline_runs(request, cline_exe, cline_home, recorder, child_cwd):
    """The report's record of every Cline run (AC 4), written to cline-run.json."""
    code, out, err = _live.run_tree([str(cline_exe), "--version"], cline_home, _cline_env(cline_home), 120)
    try:
        pinned = json.loads((_cline.CLIENT_DIR / "package.json").read_text(encoding="utf-8"))["dependencies"]["cline"]
    except (OSError, ValueError, KeyError):
        pinned = None
    record = {
        "cline_version": out.strip(),
        "install": {"recipe": _cline.INSTALL_RECIPE, "directory": "tests/e2e/.clients/cline (git-ignored)",
                    "pinned_in_package_json": pinned, "global": False},
        "env_set": {
            "HOME/USERPROFILE/APPDATA/LOCALAPPDATA/XDG_*/TEMP/TMP": "<temporary directory>",
            "PWD": "<that run's repository>",
            "--data-dir": "<temporary directory, absolute, one per scenario>",
            "NO_COLOR": "1",
            "stdin": "DEVNULL",
            "dropped": "OPENAI_*, OPENROUTER_*, ANTHROPIC_*, OPENCODE_*, AIDER_*, CLINE_*, OLDPWD, INIT_CWD",
        },
        "home_cline_dir_exists": {"before": _real_cline_dir().exists(), "after": None},
        "runs": [],
    }
    yield record
    record["home_cline_dir_exists"]["after"] = _real_cline_dir().exists()
    out_file = child_cwd / "cline-run.json"
    out_file.write_text(json.dumps(record, indent=2), encoding="ascii")
    _say(request, f"e2e017-017: Cline runs written to {out_file}")


class _ClineRun:
    def __init__(self, returncode: int, output: str, events: list, posts: list, upstream: list) -> None:
        self.returncode = returncode
        self.output = output
        self.events = events
        self.posts = posts
        self.upstream = upstream
        inner = [event["event"] for event in events
                 if event.get("type") == "agent_event" and isinstance(event.get("event"), dict)]
        ends = [event for event in inner if event.get("type") == "content_end"]
        self.tool_events = [(event.get("toolName"), event.get("toolCallId"), bool(event.get("error")))
                            for event in ends if event.get("contentType") == "tool"]
        results = [event for event in events if event.get("type") == "run_result"]
        self.finish_reason = results[-1].get("finishReason") if results else None
        self.texts = [event.get("text") or "" for event in ends if event.get("contentType") == "text"]
        self.texts += [result["text"] for result in results if isinstance(result.get("text"), str)]


@pytest.fixture
def run_cline(cline_exe, cline_home, cline_runs, recorder, stub, users, request):
    """run_cline(label, repo, prompt) -> _ClineRun."""
    def run(label: str, repo: Path, prompt: str) -> _ClineRun:
        token = users[label][1]
        data_dir = cline_home / f"data-{label}"
        assert data_dir.is_absolute()  # a relative --data-dir sends the run to api.openai.com
        auth = auth_command(cline_exe, data_dir, recorder.base + "/v1", token)
        returncode, out, err = _live.run_tree(auth, cline_home, _cline_env(cline_home), 120)
        assert returncode == 0, (out + err).replace(token, "<harness token>")[-2000:]

        command = run_command(cline_exe, data_dir, repo, prompt)
        posts_before, upstream_before = len(recorder.posts()), len(stub.settle())
        returncode, out, err = _live.run_tree(command, repo, _cline_env(cline_home, PWD=str(repo)),
                                              _cline.PROCESS_TIMEOUT_SECONDS)
        output = (out + err).replace(token, "<harness token>")
        events = []
        for line in output.splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue  # Cline's own log lines are not events
            if isinstance(event, dict):
                events.append(event)
        result = _ClineRun(returncode, output, events, recorder.posts()[posts_before:],
                           stub.settle()[upstream_before:])
        cline_runs["runs"].append({
            "test": request.node.name,
            "auth_command": [part.replace(token, "<harness token>") for part in auth],
            "command": command,
            "exit_code": returncode,
            "requests": result.posts,
            "upstream_rules": result.upstream,
            "tool_events": result.tool_events,
            "streamed": all(post["stream"] is True for post in result.posts),
            "finish_reason": result.finish_reason,
        })
        return result

    return run


def _show(run: _ClineRun) -> str:
    """Cline's output for an assertion message, ASCII only (cp1252 console)."""
    return run.output[-3000:].encode("ascii", "replace").decode("ascii")


def test_the_pinned_cline_is_the_one_that_runs(cline_runs):
    """The version in the record is the one this module was written against."""
    assert _cline.CLINE_VERSION in cline_runs["cline_version"], cline_runs["cline_version"]
    if "HARNESS_E2E_CLINE" not in os.environ:
        assert cline_runs["install"]["pinned_in_package_json"] == _cline.CLINE_VERSION


# --------------------------------------------------------------------------
# AC 1, AC 2, AC 4: the scripted task
# --------------------------------------------------------------------------


def test_cline_runs_the_scripted_task_through_the_harness(workspace, run_cline, rows, actions):
    """AC 1, AC 2 and AC 4."""
    before_rows = {row["id"] for row in rows("task")}
    before_actions = {row["id"] for row in actions("task")}

    run = run_cline("task", workspace, f"E2E-CLINE-TASK [{NONCE}] fix add() in src/calc.py, write its test, run the tests")

    assert run.returncode == 0, _show(run)
    assert run.finish_reason == "completed", _show(run)
    assert (workspace / "src" / "calc.py").read_bytes().decode("utf-8") == CALC_EDITED, _show(run)
    assert (workspace / "tests" / "test_calc.py").read_bytes().decode("utf-8") == TEST_WRITTEN, _show(run)
    # Cline executed every call itself, and none of them failed.
    assert run.tool_events == [
        ("read_files", "call_read_calc", False), ("editor", "call_edit_calc", False),
        ("editor", "call_write_test", False), ("run_commands", "call_unittest", False),
        ("submit_and_exit", "call_submit_done", False),
    ], _show(run)
    assert run.upstream == [START_RULE, EDIT_RULE, WRITE_RULE, TEST_RULE, DONE_RULE], _show(run)

    assert len(run.posts) == 5
    for post in run.posts:
        assert post["stream"] is True
        assert post["stream_options_keys"] == ["include_usage"]
        assert post["model"] == HARNESS_MODEL
        assert post["tools"] == "non-empty" and post["tool_choice"] == "non-empty"  # Cline sends "auto"
        assert "parallel_tool_calls" not in post["keys"]
        assert post["tool_names"] == sorted(YOLO_TOOLS)
    assert run.posts[0]["roles"][:3] == ["system", "user", "user"]  # the prompt, then Cline's own nudge
    assert all(post["roles"][-1] == "tool" for post in run.posts[1:])

    written = [row for row in rows("task") if row["id"] not in before_rows]
    assert len(written) == len(run.posts)  # one row per request Cline sent
    for row, post in zip(written, run.posts):
        assert row["success"] is True, row
        assert (row["ingress"], row["profile"], row["model_used"]) == ("v1", "code", HARNESS_MODEL)
        assert row["streamed"] is True
        # Requests 1-5 carry the call in the response or in their history (PRD Section 11).
        assert row["has_tool_calls"] is True
        assert row["was_duplicate_blocked"] is False
        assert row["ignored_params"] == _live.expected_ignored_params(post)
    assert len({row["conversation_key"] for row in written}) == 1, [row["conversation_key"] for row in written]

    decided = [row for row in actions("task") if row["id"] not in before_actions]
    assert [(a["tool_name"], a["decision"], a["rule"]) for a in decided] == [
        ("read_files", "allow", "fs.read"),
        ("editor", "allow", "fs.write_in_workspace"),
        ("editor", "allow", "fs.write_in_workspace"),
        ("run_commands", "allow", "shell.allowlisted"),
        ("submit_and_exit", "allow", "tool.opaque"),
    ]
    assert [a["tool_call_id"] for a in decided] == [
        "call_read_calc", "call_edit_calc", "call_write_test", "call_unittest", "call_submit_done"]
    # Each response carried one call, so each decision belongs to the request in the same position.
    assert [a["audit_id"] for a in decided] == [row["id"] for row in written]


# --------------------------------------------------------------------------
# AC 3: a denied DROP TABLE
# --------------------------------------------------------------------------


def test_a_scripted_drop_table_is_denied_and_cline_reports_it(drop_workspace, run_cline, rows, actions):
    before_rows = {row["id"] for row in rows("drop")}
    before_actions = {row["id"] for row in actions("drop")}
    status_before = _live.git(drop_workspace, "status", "--porcelain")

    run = run_cline("drop", drop_workspace, f"E2E-CLINE-DROP [{NONCE}] clean up the database")

    assert run.returncode == 0, _show(run)
    assert run.finish_reason == "completed", _show(run)
    # Cline executed no file or shell tool: only the `submit_and_exit` that ends its run.
    assert run.tool_events == [("submit_and_exit", "call_submit_drop", False)], _show(run)
    assert run.upstream == [DROP_RULE, DROP_SUBMIT_RULE] and len(run.posts) == 2, _show(run)  # no retry storm
    with sqlite3.connect(drop_workspace / "app.db") as conn:
        assert conn.execute("SELECT COUNT(*) FROM users").fetchone() == (1,)
    conn.close()
    assert _live.git(drop_workspace, "status", "--porcelain") == status_before  # the denied call changed no file

    written = [row for row in rows("drop") if row["id"] not in before_rows]
    assert len(written) == 2
    for row in written:
        assert (row["ingress"], row["profile"], row["success"]) == ("v1", "code", True)
        assert row["has_tool_calls"] is True and row["was_duplicate_blocked"] is False
    decided = [a for a in actions("drop") if a["id"] not in before_actions]
    assert [(a["tool_name"], a["decision"], a["rule"], a["tool_call_id"]) for a in decided] == [
        ("run_commands", "deny", "sql.ddl", "call_drop"),
        ("submit_and_exit", "allow", "tool.opaque", "call_submit_drop"),
    ]
    assert [a["audit_id"] for a in decided] == [row["id"] for row in written]
    # The harness's note, as app/services/tool_release.py:41 words it (mirrored in _opencode.py).
    note = DENIAL_NOTE_TEMPLATE.format(name="run_commands", id="call_drop", reason=decided[0]["reason"])
    assert " ".join(note.split()) in " ".join(" ".join(run.texts).split()), _show(run)


# --------------------------------------------------------------------------
# PRD Section 11: every row this ingress writes
# --------------------------------------------------------------------------


def test_zz_every_row_this_module_wrote_is_v1_and_code(cline_exe, rows):
    """Named to run last in the module (pytest keeps definition order).

    `cline_exe` first, so without Cline this errors at setup like the rest of the
    module instead of starting children to read rows nobody wrote.
    """
    written = rows("task") + rows("drop")
    assert written
    assert {(row["ingress"], row["profile"]) for row in written} == {("v1", "code")}
