"""PRD-021 STORY-014: OpenCode end to end on a real-time stream.

The real OpenCode CLI (`run --standalone --auto --format json --thinking`, the global npm
install; its version is recorded in `opencode-run.json`, 2.3.2 when written) talks to a harness
with `STREAMING_ENABLED=true`, a file-mode registry whose model has `streaming: true` and
`reasoning: true` (legacy mode never streams, OD1), and an `RBAC_ROLES_FILE` that grants
`stream:realtime` (and `reasoning:view` to `auditor`). The STORY-004 stub answers with its `stream`
shape, so text and the `DROP TABLE` arguments arrive in fragments. `_live.Recorder(keep_sse=True)`
records what the harness streamed back, with arrival times: the harness-side proof.

    AC 1  the answer text streams in pieces, arrives before the end of the stream, and OpenCode
          completes; every audit row has `streamed_realtime` and a `chatcmpl-harness-rt-` id
          equal to the SSE chunk id (a silent buffered fallback fails the test)
    AC 2  a denied `DROP TABLE` call never leaves in pieces: no `tool_calls` delta, no argument
          fragment in the stream; one deny `action_decisions` row
    AC 3  reasoning is streamed live (granted role) and never written down: the sentinel is in
          no content delta, no OpenCode text, no workspace file and no audit row. Whether OpenCode
          displays it is observed and printed, never asserted
    AC 4  skipped without `--run-e2e` (module marker)

The roles file replaces the matrix wholesale (authz.load) and `manage_users.py --role` only takes
`admin|auditor|user`, so `user` is redefined as query + audit own + real time, and `auditor` as the
same plus `reasoning:view`; users are created with those roles. Reasoning arrives as the
`reasoning_content` delta key (O5) and OpenCode is told so through the model's
`compatibility.reasoningField` (documented at opencode.ai/docs/models).

Run (skipped without `--run-e2e`):

    docker run -d --name harness-libsql-e2e021-014 -p 8089:8080 -e SQLD_NODE=primary ghcr.io/tursodatabase/libsql-server:latest
    HARNESS_E2E_LIBSQL_URL=http://127.0.0.1:8089 \\
    HARNESS_E2E_OPENCODE=C:/Users/<you>/AppData/Roaming/npm/node_modules/@opencode/cli/bin/opencode.exe \\
        PYTHONUTF8=1 python -m pytest tests/e2e/test_opencode_realtime.py -m e2e --run-e2e -v
    docker rm -f harness-libsql-e2e021-014
"""

import json
import os
import secrets
import sqlite3
from pathlib import Path

import pytest

from tests.e2e import _live
from tests.e2e._opencode import CALC_ORIGINAL, DENIAL_NOTE_TEMPLATE, OPENCODE_MODEL, policy_yaml
from tests.e2e._opencode_realtime import (
    COMPLETION_ID_PREFIX,
    DROP_RULE,
    REASONING_FIELD,
    TEXT_RULE,
    argument_fragments,
    opencode_config,
    parse_sse,
    registry_yaml,
    render_script,
    repo_root_text,
    roles_json,
)

pytestmark = pytest.mark.e2e

NONCE = secrets.token_hex(4)
SENTINEL = f"RSN-{NONCE}"
_RECIPE = (
    "docker run -d --name harness-libsql-e2e021-014 -p 8089:8080 -e SQLD_NODE=primary "
    "ghcr.io/tursodatabase/libsql-server:latest, then "
    "HARNESS_E2E_LIBSQL_URL=http://127.0.0.1:8089"
)
_OPENCODE_RECIPE = (
    "npm's global @opencode/cli, then "
    "HARNESS_E2E_OPENCODE=C:/Users/<you>/AppData/Roaming/npm/node_modules/@opencode/cli/bin/opencode.exe"
)
#: Where OpenCode reads reasoning from (the harness emits `reasoning_content` only, O5).
_REASONING_KEY = {"compatibility": {"reasoningField": REASONING_FIELD}}

_REPORT_FIELDS = (
    "id", "success", "streamed", "ingress", "profile", "model_used", "tokens_used", "conversation_key",
    "ignored_params", "suspicious_pattern", "denied_permission", "error_message",
    "has_tool_calls", "was_duplicate_blocked", "streamed_realtime", "completion_id", "reasoning_shown",
)
_ACTION_FIELDS = ("id", "audit_id", "tool_call_id", "tool_name", "operation_kind", "decision", "rule", "reason")
_ROLES = {"text": "user", "drop": "user", "reason": "auditor"}


# --------------------------------------------------------------------------
# Fixtures: database, users, repository, stub, harness, recorder
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def opencode_exe():
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
    return tmp_path_factory.mktemp("e2e021-014")


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
    for label, role in _ROLES.items():
        user_id = f"e2e021-014-{label}-{NONCE}"
        created[label] = (user_id, _live.create_user(run_child, user_id, role))
    return created


@pytest.fixture(scope="module")
def workspace(tmp_path_factory):
    """A throwaway git repository holding `app.db`, which the denied call must not drop."""
    path = tmp_path_factory.mktemp("e2e021-014-repo")
    _live.git(path, "init", "-q")
    for key, value in (("user.name", "e2e021-014"), ("user.email", "e2e021-014@example.invalid"),
                       ("core.autocrlf", "false"), ("commit.gpgsign", "false")):
        _live.git(path, "config", key, value)
    _live.write_lf(path / "src" / "calc.py", CALC_ORIGINAL)
    with sqlite3.connect(path / "app.db") as conn:
        conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
        conn.execute("INSERT INTO users (name) VALUES ('e2e')")
    conn.close()
    _live.git(path, "add", "-A")
    _live.git(path, "commit", "-qm", "init")
    return path


@pytest.fixture(scope="module")
def stub(child_cwd, workspace):
    script = child_cwd / "opencode_realtime.json"
    script.write_text(render_script(repo_root_text(workspace), SENTINEL), encoding="utf-8")
    with _live.start_stub(script, child_cwd) as running:
        yield running


@pytest.fixture(scope="module")
def harness_env(users, stub, child_cwd, child_env, workspace):
    """The harness child's environment; the files it names are written first."""
    registry = child_cwd / "providers.yaml"
    registry.write_text(registry_yaml(stub.base), encoding="utf-8")
    roles = child_cwd / "roles.json"
    roles.write_text(roles_json(), encoding="utf-8")
    policy = child_cwd / "action_policy.yaml"
    policy.write_text(policy_yaml(repo_root_text(workspace)), encoding="utf-8")
    return child_env(
        PROVIDERS_FILE=str(registry),
        OPENROUTER_API_KEY="",
        RBAC_ENABLED="true",
        RBAC_ROLES_FILE=str(roles),
        STREAMING_ENABLED="true",
        V1_ENABLED="true",
        V1_TOOLS_ENABLED="true",
        ACTION_POLICY_FILE=str(policy),
        USAGE_REQUESTS_PER_MINUTE="*=unlimited",
    )


@pytest.fixture(scope="module")
def harness(harness_env, child_cwd):
    """`uvicorn app.main:app` on a free port. After `users`: startup refuses an empty users table."""
    with _live.start_harness(child_cwd, harness_env) as running:
        yield running


@pytest.fixture(scope="module")
def recorder(harness):
    proxy = _live.Recorder(harness.base, keep_tool_names=True, keep_sse=True)
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
    seen: dict = {}
    yield seen
    out = child_cwd / "rows.json"
    out.write_text(json.dumps([seen[key] for key in sorted(seen)], indent=2), encoding="ascii")
    _say(request, f"e2e021-014: {len(seen)} audit rows written to {out}")


@pytest.fixture(scope="module")
def seen_actions(request, child_cwd):
    seen: dict = {}
    yield seen
    out = child_cwd / "actions.json"
    out.write_text(json.dumps([seen[key] for key in sorted(seen)], indent=2), encoding="ascii")
    _say(request, f"e2e021-014: {len(seen)} action decisions written to {out}")


@pytest.fixture(scope="module")
def rows(run_child, users, seen_rows):
    """rows(label) -> that user's full rows, oldest first (the tests search them for the sentinel)."""
    def read(label: str) -> list:
        found = _live.dump_rows(run_child, users[label][0])
        for row in found:
            seen_rows[row["id"]] = {"user": label, **{key: row[key] for key in _REPORT_FIELDS}}
        return found

    return read


@pytest.fixture(scope="module")
def actions(run_child, users, seen_actions):
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
    return tmp_path_factory.mktemp("e2e021-014-oc-home")


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
    # OpenCode takes its working directory from `PWD` when it is set (see test_opencode.py).
    env.pop("OLDPWD", None)
    env.pop("INIT_CWD", None)
    (oc_home / "tmp").mkdir(exist_ok=True)
    return env


@pytest.fixture(scope="module")
def opencode_runs(request, opencode_exe, oc_home, recorder, child_cwd):
    """The record of every OpenCode run, written to opencode-run.json."""
    code, out, err = _live.run_tree([opencode_exe, "--version"], oc_home, _oc_env(oc_home), 120)
    version = out.strip()
    _say(request, f"e2e021-014: opencode --version: {version}")
    record = {
        "opencode_version": version,
        "provider_config": opencode_config(recorder.base, "<harness token>", _REASONING_KEY),
        "reasoning_displayed": None,
        "runs": [],
    }
    yield record
    out_file = child_cwd / "opencode-run.json"
    out_file.write_text(json.dumps(record, indent=2), encoding="ascii")
    _say(request, f"e2e021-014: OpenCode runs written to {out_file}")


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
        self.reasonings = [event["part"].get("text", "") for event in events if event.get("type") == "reasoning"]
        self.errors = [event for event in events if event.get("type") == "error"]


@pytest.fixture
def run_opencode(opencode_exe, oc_home, opencode_runs, recorder, stub, users, workspace, request):
    """run_opencode(label, prompt) -> _OpenCodeRun."""
    def run(label: str, prompt: str) -> _OpenCodeRun:
        token = users[label][1]
        env = _oc_env(oc_home, PWD=str(workspace),
                      OPENCODE_CONFIG_CONTENT=json.dumps(opencode_config(recorder.base, token, _REASONING_KEY)))
        command = [opencode_exe, "run", "--standalone", "--auto", "--format", "json", "--thinking",
                   "-m", OPENCODE_MODEL, prompt]
        posts_before, upstream_before = len(recorder.posts()), len(stub.settle())
        returncode, out, err = _live.run_tree(command, workspace, env, 300)
        output = (out + err).replace(token, "<harness token>")
        events = []
        for line in output.splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if isinstance(event, dict):
                events.append(event)
        result = _OpenCodeRun(returncode, output, events, recorder.posts()[posts_before:],
                              stub.settle()[upstream_before:])
        opencode_runs["runs"].append({
            "test": request.node.name,
            "command": command[:-1] + ["<prompt>"],
            "exit_code": returncode,
            "requests": [{key: value for key, value in post.items() if key != "sse"} for post in result.posts],
            "upstream_rules": result.upstream,
            "tool_uses": result.tool_uses,
            "sse_chunks": [len(post["sse"]) for post in result.posts],
        })
        return result

    return run


def _show(run: _OpenCodeRun) -> str:
    """OpenCode's output for an assertion message, ASCII only (cp1252 console)."""
    return run.output[-3000:].encode("ascii", "replace").decode("ascii")


def _norm(text: str) -> str:
    return " ".join(text.split())


def _assert_real_time(run: _OpenCodeRun, written: list) -> list:
    """Real time, proven from the harness side; returns the parsed chunks of every request, flat.

    A buffered fallback (switch, grant or registry capability missing) leaves `streamed_realtime`
    false and a `chatcmpl-harness-` id without `-rt-`: it fails here, not silently.
    """
    assert len(written) == len(run.posts) >= 1, (len(written), len(run.posts))
    every = []
    for row, post in zip(written, run.posts):
        assert row["success"] is True, row
        assert row["streamed_realtime"] is True, f"buffered fallback: audit row {row['id']} streamed_realtime false"
        assert row["completion_id"] and row["completion_id"].startswith(COMPLETION_ID_PREFIX), row["completion_id"]
        chunks = parse_sse(post["sse"])
        assert chunks and chunks[-1]["done"] is True, "the stream does not end with [DONE]"
        body = chunks[:-1]
        assert body[0]["role"] == "assistant", "the first chunk is not the role chunk"
        assert {chunk["id"] for chunk in body} == {row["completion_id"]}, (
            "SSE chunk ids differ from the audit completion_id (D17)")
        assert all("harness" not in chunk["body"] for chunk in body)
        every.extend(chunks)
    return every


# --------------------------------------------------------------------------
# Real time is on
# --------------------------------------------------------------------------


def test_real_time_is_on_for_the_harness_child(harness_env, child_cwd):
    assert harness_env["STREAMING_ENABLED"] == "true"
    roles = json.loads((child_cwd / "roles.json").read_text(encoding="utf-8"))
    assert "stream:realtime" in roles["user"] and "stream:realtime" in roles["auditor"]
    assert "reasoning:view" in roles["auditor"] and "reasoning:view" not in roles["user"]
    assert "streaming: true" in (child_cwd / "providers.yaml").read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# AC 1: the answer text streams in pieces
# --------------------------------------------------------------------------


def test_the_answer_text_streams_in_pieces(run_opencode, rows):
    before = {row["id"] for row in rows("text")}

    run = run_opencode("text", f"E2E-RT-TEXT [{NONCE}] say the marker word")

    assert run.returncode == 0, _show(run)
    assert not run.errors, _show(run)
    assert any("E2E-RT-ANSWER" in text for text in run.texts), _show(run)
    assert run.upstream == [TEXT_RULE] and len(run.posts) == 1, _show(run)
    written = [row for row in rows("text") if row["id"] not in before]
    chunks = _assert_real_time(run, written)
    deltas = [chunk for chunk in chunks if chunk.get("content")]
    assert len(deltas) >= 3, [chunk["content"] for chunk in deltas]
    # Generous local margin: the stub paces 60 ms per delta over ~18 deltas, so the first text arrives
    # long before the end. A buffered stream sends everything at once at the end.
    assert chunks[-1]["t"] - deltas[0]["t"] >= 0.2, (deltas[0]["t"], chunks[-1]["t"])
    assert "".join(chunk["content"] for chunk in deltas).count("E2E-RT-ANSWER") == 1


# --------------------------------------------------------------------------
# AC 2: a denied DROP TABLE never leaves in pieces
# --------------------------------------------------------------------------


def test_a_denied_drop_table_never_leaves_in_pieces(workspace, run_opencode, rows, actions):
    before_rows = {row["id"] for row in rows("drop")}
    before_actions = {row["id"] for row in actions("drop")}
    status_before = _live.git(workspace, "status", "--porcelain")

    run = run_opencode("drop", f"E2E-RT-DROP [{NONCE}] clean up the database")

    assert run.returncode == 0, _show(run)
    assert run.tool_uses == [], _show(run)
    assert run.upstream == [DROP_RULE] and len(run.posts) == 1, _show(run)
    with sqlite3.connect(workspace / "app.db") as conn:
        assert conn.execute("SELECT COUNT(*) FROM users").fetchone() == (1,)
    conn.close()
    assert _live.git(workspace, "status", "--porcelain") == status_before

    [row] = [row for row in rows("drop") if row["id"] not in before_rows]
    [decision] = [a for a in actions("drop") if a["id"] not in before_actions]
    assert (decision["decision"], decision["rule"], decision["tool_name"], decision["tool_call_id"]) == (
        "deny", "sql.ddl", "shell", "call_rt_drop")
    assert decision["audit_id"] == row["id"]

    chunks = _assert_real_time(run, [row])
    body = [chunk for chunk in chunks if not chunk["done"]]
    # D6: no tool-call delta at all (the call was denied, and fragments are never forwarded).
    assert not [chunk for chunk in body if chunk["tool_calls"]], "a tool_calls delta left the harness"
    assert all('"arguments"' not in chunk["raw"] and '"function"' not in chunk["raw"] for chunk in body)
    finishes = [index for index, chunk in enumerate(body) if chunk["finish_reason"]]
    assert finishes and all(chunk["content"] is None for chunk in body[finishes[0] + 1:])  # nothing after the finish
    text = _norm("".join(chunk["content"] or "" for chunk in body))
    note = _norm(DENIAL_NOTE_TEMPLATE.format(name="shell", id="call_rt_drop", reason=decision["reason"]))
    assert note in text, text
    remainder = text.replace(note, "")
    # The note quotes the policy reason (action_classifiers/sql.py); only a leak outside it counts.
    for banned in ("DROP TABLE", "sqlite3", "app.db"):
        assert banned not in remainder, (banned, remainder)
    arguments = '{"command":"sqlite3 app.db \\"DROP TABLE users\\""}'
    for piece in argument_fragments(arguments, 6):
        if len(piece) >= 5:
            assert piece not in remainder, piece
    assert note in _norm(" ".join(run.texts)), _show(run)  # the note reached OpenCode itself


# --------------------------------------------------------------------------
# AC 3: reasoning is shown live and never written down
# --------------------------------------------------------------------------


def test_reasoning_is_shown_live_and_never_written_down(request, workspace, run_opencode, rows, opencode_runs):
    before = {row["id"] for row in rows("reason")}

    run = run_opencode("reason", f"E2E-RT-REASON [{NONCE}] think about it")

    assert run.returncode == 0, _show(run)
    assert any("E2E-RT-REASONED" in text for text in run.texts), _show(run)
    written = [row for row in rows("reason") if row["id"] not in before]
    chunks = _assert_real_time(run, written)
    body = [chunk for chunk in chunks if not chunk["done"]]
    # Hard: the grant plus real time delivered reasoning on the wire (D9).
    assert SENTINEL in "".join(chunk["reasoning"] or "" for chunk in body), "no reasoning_content reached the client"
    assert [row["reasoning_shown"] for row in written] == [True] * len(written)
    # Hard: never content, never a file, never an audit row (D8).
    assert SENTINEL not in "".join(chunk["content"] or "" for chunk in body)
    assert not any(SENTINEL in text for text in run.texts), _show(run)
    for path in workspace.rglob("*"):
        if path.is_file():  # `.git` included: nothing in the repository may hold the sentinel
            assert SENTINEL.encode() not in path.read_bytes(), f"{path} holds the reasoning sentinel"
    for row in written:
        assert SENTINEL not in json.dumps(row, default=str)
    # Observed only: did OpenCode show it? (`--thinking` asks for thinking blocks.)
    displayed = any(SENTINEL in text for text in run.reasonings)
    opencode_runs["reasoning_displayed"] = displayed
    _say(request, f"e2e021-014: OpenCode displayed the reasoning: {displayed} "
                  f"(reasoning events: {len(run.reasonings)}, reasoningField {REASONING_FIELD})")


# --------------------------------------------------------------------------
# Every row this module wrote
# --------------------------------------------------------------------------


def test_zz_every_row_is_v1_code_and_real_time(opencode_exe, rows):
    """Named to run last; `opencode_exe` first so a missing OpenCode errors before any child starts."""
    written = rows("text") + rows("drop") + rows("reason")
    assert written
    assert {(row["ingress"], row["profile"]) for row in written} == {("v1", "code")}
    assert all(row["streamed_realtime"] is True for row in written)
