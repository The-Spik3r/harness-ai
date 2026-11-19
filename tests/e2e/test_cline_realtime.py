"""PRD-021 STORY-015: Cline end to end on a real-time stream.

The real Cline CLI (the pinned local install under the git-ignored `tests/e2e/.clients/cline`,
3.0.74; `HARNESS_E2E_CLINE` overrides it) runs headless (`--yolo --json`) against a harness with
`STREAMING_ENABLED=true`, a file-mode registry whose model has `streaming: true` and
`reasoning: true` (legacy mode never streams, OD1) and an `RBAC_ROLES_FILE` that grants
`stream:realtime` (and `reasoning:view` to `auditor`). The STORY-004 stub answers with its `stream`
shape. `_live.Recorder(keep_sse=True)` records what the harness streamed back, with arrival
times: the harness-side proof, as in STORY-014.

    AC 1  the answer text streams in pieces and arrives before the end of the stream; every
          audit row has `streamed_realtime` and a `chatcmpl-harness-rt-` id equal to the SSE
          chunk id (a silent buffered fallback fails); Cline completes
    AC 2  a denied `DROP TABLE` call never leaves in pieces: no `tool_calls` delta, no argument
          fragment in the stream; one deny `action_decisions` row; the harness note reaches Cline
    AC 3  reasoning is streamed live (granted role) and never written down: the sentinel is in no
          content delta, no Cline text, no workspace file and no audit row. Whether Cline
          displays it is observed and recorded in `cline-realtime-run.json`, never asserted
    AC 4  skipped without `--run-e2e` (module marker)

Cline's last user turn is its own nudge, so the stub picks the scenario from the system prompt,
which names the `-c` directory (see test_cline.py). Cline's loop ends only on a `submit_and_exit`
call, so every scripted path ends in one (allowed by `opaque_tools`, released whole). Cline's own
data dir is not scanned for the sentinel (it may store what it displays); the server side and the
workspaces are. `manage_users.py --role` only takes `admin|auditor|user`, so `user` and `auditor`
are redefined in the roles file.

Run (skipped without `--run-e2e`):

    docker run -d --name harness-libsql-e2e021-015 -p 8090:8080 -e SQLD_NODE=primary ghcr.io/tursodatabase/libsql-server:latest
    HARNESS_E2E_LIBSQL_URL=http://127.0.0.1:8090 \\
        PYTHONUTF8=1 python -m pytest tests/e2e/test_cline_realtime.py -m e2e --run-e2e -v
    docker rm -f harness-libsql-e2e021-015
"""

import json
import os
import secrets
import sqlite3
from pathlib import Path

import pytest

from tests.e2e import _live
from tests.e2e._cline_realtime import (
    CLIENT_DIR,
    COMPLETION_ID_PREFIX,
    DENIAL_NOTE_TEMPLATE,
    DROP_DIR,
    DROP_RULE,
    FOLLOWUP_RULE,
    INSTALL_RECIPE,
    PROCESS_TIMEOUT_SECONDS,
    REASON_DIR,
    REASONING_FIELD,
    TEXT_DIR,
    TEXT_RULE,
    argument_fragments,
    auth_command,
    cline_executable,
    parse_sse,
    policy_yaml,
    registry_yaml,
    render_script,
    repo_root_text,
    roles_json,
    run_command,
)

pytestmark = pytest.mark.e2e

NONCE = secrets.token_hex(4)
SENTINEL = f"RSN-{NONCE}"
_RECIPE = (
    "docker run -d --name harness-libsql-e2e021-015 -p 8090:8080 -e SQLD_NODE=primary "
    "ghcr.io/tursodatabase/libsql-server:latest, then "
    "HARNESS_E2E_LIBSQL_URL=http://127.0.0.1:8090"
)

_REPORT_FIELDS = (
    "id", "success", "streamed", "ingress", "profile", "model_used", "tokens_used", "conversation_key",
    "ignored_params", "suspicious_pattern", "denied_permission", "error_message",
    "has_tool_calls", "was_duplicate_blocked", "streamed_realtime", "completion_id", "reasoning_shown",
)
_ACTION_FIELDS = ("id", "audit_id", "tool_call_id", "tool_name", "operation_kind", "decision", "rule", "reason")
_ROLES = {"text": "user", "drop": "user", "reason": "auditor"}
_DIRS = {"text": TEXT_DIR, "drop": DROP_DIR, "reason": REASON_DIR}


# --------------------------------------------------------------------------
# Fixtures: Cline, database, users, repositories, stub, harness, recorder
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def cline_exe():
    """`HARNESS_E2E_CLINE`, or the pinned local install's `cline.exe`. Never whatever `cline` is on PATH."""
    override = os.environ.get("HARNESS_E2E_CLINE", "").strip()
    path = Path(override) if override else cline_executable(CLIENT_DIR)
    if not path.is_file():
        pytest.fail(f"Cline is not installed ({'HARNESS_E2E_CLINE' if override else 'tests/e2e/.clients/cline'}). "
                    f"Install it locally, never with -g: {INSTALL_RECIPE}")
    return path


@pytest.fixture(scope="module")
def e2e_db_url():
    return _live.resolve_e2e_db_url(_RECIPE)


@pytest.fixture(scope="module")
def child_cwd(tmp_path_factory):
    """A directory with no `.env`, so no child reads the developer's settings."""
    return tmp_path_factory.mktemp("e2e021-015")


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
        user_id = f"e2e021-015-{label}-{NONCE}"
        created[label] = (user_id, _live.create_user(run_child, user_id, role))
    return created


def _make_repo(path: Path) -> Path:
    """A throwaway git repository holding `app.db`, which the denied call must not drop."""
    _live.git(path, "init", "-q")
    for key, value in (("user.name", "e2e021-015"), ("user.email", "e2e021-015@example.invalid"),
                       ("core.autocrlf", "false"), ("commit.gpgsign", "false")):
        _live.git(path, "config", key, value)
    _live.write_lf(path / "README.txt", "e2e\n")
    with sqlite3.connect(path / "app.db") as conn:
        conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
        conn.execute("INSERT INTO users (name) VALUES ('e2e')")
    conn.close()
    _live.git(path, "add", "-A")
    _live.git(path, "commit", "-qm", "init")
    return path


@pytest.fixture(scope="module")
def workspaces(tmp_path_factory):
    """{label: repository}. The directory names are what the stub recognises the scenario by."""
    return {label: _make_repo(tmp_path_factory.mktemp(name)) for label, name in _DIRS.items()}


@pytest.fixture(scope="module")
def stub(child_cwd, workspaces):
    script = child_cwd / "cline_realtime.json"
    script.write_text(render_script(repo_root_text(workspaces["drop"]), SENTINEL), encoding="utf-8")
    with _live.start_stub(script, child_cwd) as running:
        yield running


@pytest.fixture(scope="module")
def harness_env(users, stub, child_cwd, child_env, workspaces):
    """The harness child's environment; the files it names are written first."""
    registry = child_cwd / "providers.yaml"
    registry.write_text(registry_yaml(stub.base), encoding="utf-8")
    roles = child_cwd / "roles.json"
    roles.write_text(roles_json(), encoding="utf-8")
    policy = child_cwd / "action_policy.yaml"
    policy.write_text(policy_yaml(repo_root_text(workspaces["drop"])), encoding="utf-8")
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
    _say(request, f"e2e021-015: {len(seen)} audit rows written to {out}")


@pytest.fixture(scope="module")
def seen_actions(request, child_cwd):
    seen: dict = {}
    yield seen
    out = child_cwd / "actions.json"
    out.write_text(json.dumps([seen[key] for key in sorted(seen)], indent=2), encoding="ascii")
    _say(request, f"e2e021-015: {len(seen)} action decisions written to {out}")


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
# Fixtures: Cline's home, the runner
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def cline_home(tmp_path_factory):
    path = tmp_path_factory.mktemp("e2e021-015-cline-home")
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
    # Cline takes its working directory from `PWD` when it is set: callers pass the repository as PWD.
    env.pop("OLDPWD", None)
    env.pop("INIT_CWD", None)
    (home_dir / "tmp").mkdir(exist_ok=True)
    return env


@pytest.fixture(scope="module")
def cline_runs(request, cline_exe, cline_home, recorder, child_cwd):
    """The record of every Cline run, written to cline-realtime-run.json (Cline-side outcomes, AC 1 and AC 3)."""
    code, out, err = _live.run_tree([str(cline_exe), "--version"], cline_home, _cline_env(cline_home), 120)
    record = {"cline_version": out.strip(), "reasoning_displayed": None, "runs": []}
    yield record
    out_file = child_cwd / "cline-realtime-run.json"
    out_file.write_text(json.dumps(record, indent=2), encoding="ascii")
    _say(request, f"e2e021-015: Cline runs written to {out_file}")


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
        # Observation only: Cline's reasoning events (the text field name is read off the first live run).
        self.reasoning_events = [event for event in inner if event.get("contentType") == "reasoning"]


@pytest.fixture
def run_cline(cline_exe, cline_home, cline_runs, recorder, stub, users, workspaces, request):
    """run_cline(label, prompt) -> _ClineRun, in that label's repository."""
    def run(label: str, prompt: str) -> _ClineRun:
        token = users[label][1]
        repo = workspaces[label]
        data_dir = cline_home / f"data-{label}"
        assert data_dir.is_absolute()  # a relative --data-dir sends the run to api.openai.com
        auth = auth_command(cline_exe, data_dir, recorder.base + "/v1", token)
        returncode, out, err = _live.run_tree(auth, cline_home, _cline_env(cline_home), 120)
        assert returncode == 0, (out + err).replace(token, "<harness token>")[-2000:]

        command = run_command(cline_exe, data_dir, repo, prompt)
        posts_before, upstream_before = len(recorder.posts()), len(stub.settle())
        returncode, out, err = _live.run_tree(command, repo, _cline_env(cline_home, PWD=str(repo)),
                                              PROCESS_TIMEOUT_SECONDS)
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
            "command": command[:-1] + ["<prompt>"],
            "exit_code": returncode,
            "requests": [{key: value for key, value in post.items() if key != "sse"} for post in result.posts],
            "upstream_rules": result.upstream,
            "tool_events": result.tool_events,
            "finish_reason": result.finish_reason,
            "sse_chunks": [len(post["sse"]) for post in result.posts],
            "text_count": len(result.texts),
            "reasoning_event_count": len(result.reasoning_events),
            "reasoning_displayed": any(SENTINEL in json.dumps(e) for e in result.reasoning_events),
            "sentinel_in_output": SENTINEL in output,
            "output_tail": output[-1500:].replace(SENTINEL, "<sentinel>"),
        })
        return result

    return run


def _show(run: _ClineRun) -> str:
    """Cline's output for an assertion message, ASCII only (cp1252 console)."""
    return run.output[-3000:].encode("ascii", "replace").decode("ascii")


def _norm(text: str) -> str:
    return " ".join(text.split())


def _assert_real_time(run: _ClineRun, written: list) -> list:
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


def test_the_answer_text_streams_in_pieces(run_cline, rows):
    before = {row["id"] for row in rows("text")}

    run = run_cline("text", f"E2E-RT-TEXT [{NONCE}] say the marker word")

    assert run.returncode == 0, _show(run)
    assert run.finish_reason == "completed", _show(run)
    assert any("E2E-RT-ANSWER" in text for text in run.texts), _show(run)
    assert run.upstream == [TEXT_RULE] and len(run.posts) == 1, _show(run)
    written = [row for row in rows("text") if row["id"] not in before]
    chunks = _assert_real_time(run, written)
    deltas = [chunk for chunk in chunks if chunk.get("content")]
    assert len(deltas) >= 3, [chunk["content"] for chunk in deltas]
    # Generous local margin: the stub paces 60 ms per delta over ~18 deltas; a buffered stream sends
    # everything at once at the end.
    assert chunks[-1]["t"] - deltas[0]["t"] >= 0.2, (deltas[0]["t"], chunks[-1]["t"])
    assert "".join(chunk["content"] for chunk in deltas).count("E2E-RT-ANSWER") == 1
    # D6: the allowed submit_and_exit leaves whole, never in pieces.
    for chunk in chunks:
        for call in chunk.get("tool_calls") or []:
            json.loads(call["function"]["arguments"])


# --------------------------------------------------------------------------
# AC 2: a denied DROP TABLE never leaves in pieces
# --------------------------------------------------------------------------


def test_a_denied_drop_table_never_leaves_in_pieces(workspaces, run_cline, rows, actions):
    workspace = workspaces["drop"]
    before_rows = {row["id"] for row in rows("drop")}
    before_actions = {row["id"] for row in actions("drop")}
    status_before = _live.git(workspace, "status", "--porcelain")

    run = run_cline("drop", f"E2E-RT-DROP [{NONCE}] clean up the database")

    assert run.returncode == 0, _show(run)
    assert run.finish_reason == "completed", _show(run)
    assert run.upstream == [DROP_RULE, FOLLOWUP_RULE] and len(run.posts) == 2, _show(run)
    with sqlite3.connect(workspace / "app.db") as conn:
        assert conn.execute("SELECT COUNT(*) FROM users").fetchone() == (1,)
    conn.close()
    assert _live.git(workspace, "status", "--porcelain") == status_before

    written = [row for row in rows("drop") if row["id"] not in before_rows]
    new_actions = [a for a in actions("drop") if a["id"] not in before_actions]
    [decision] = [a for a in new_actions if a["decision"] == "deny"]
    assert (decision["rule"], decision["tool_name"], decision["tool_call_id"]) == (
        "sql.ddl", "run_commands", "call_rt_drop")
    assert decision["audit_id"] == written[0]["id"]
    allowed = [a for a in new_actions if a["decision"] == "allow"]
    assert [(a["tool_name"], a["tool_call_id"]) for a in allowed] == [("submit_and_exit", "call_rt_submit_drop")]

    _assert_real_time(run, written)
    first = [chunk for chunk in parse_sse(run.posts[0]["sse"]) if not chunk["done"]]
    # D6: request 1 carries no tool-call delta at all (the call was denied, and fragments are never forwarded).
    assert not [chunk for chunk in first if chunk["tool_calls"]], "a tool_calls delta left the harness"
    assert all('"arguments"' not in chunk["raw"] and '"function"' not in chunk["raw"] for chunk in first)
    finishes = [index for index, chunk in enumerate(first) if chunk["finish_reason"]]
    assert finishes and all(chunk["content"] is None for chunk in first[finishes[0] + 1:])  # nothing after the finish
    text = _norm("".join(chunk["content"] or "" for chunk in first))
    note = _norm(DENIAL_NOTE_TEMPLATE.format(name="run_commands", id="call_rt_drop", reason=decision["reason"]))
    assert note in text, text
    remainder = text.replace(note, "")
    # The note quotes the policy reason (action_classifiers/sql.py); only a leak outside it counts.
    for banned in ("DROP TABLE", "sqlite3", "app.db"):
        assert banned not in remainder, (banned, remainder)
    arguments = '{"commands":["sqlite3 app.db \\"DROP TABLE users\\""]}'
    for piece in argument_fragments(arguments, 6):
        if len(piece) >= 5:
            assert piece not in remainder, piece
    # The note reached Cline itself: request 2 was selected by it (rule FOLLOWUP_RULE above), and Cline printed it.
    assert note in _norm(" ".join(run.texts)) or "[harness] tool call" in run.output, _show(run)


# --------------------------------------------------------------------------
# AC 3: reasoning is shown live and never written down
# --------------------------------------------------------------------------


def test_reasoning_is_shown_live_and_never_written_down(request, workspaces, run_cline, rows, cline_runs):
    before = {row["id"] for row in rows("reason")}

    run = run_cline("reason", f"E2E-RT-REASON [{NONCE}] think about it")

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
    for workspace in workspaces.values():
        for path in workspace.rglob("*"):
            if path.is_file():  # `.git` included: nothing in the repository may hold the sentinel
                assert SENTINEL.encode() not in path.read_bytes(), f"{path} holds the reasoning sentinel"
    for row in written:
        assert SENTINEL not in json.dumps(row, default=str)
    # Observed only: did Cline show it?
    displayed = any(SENTINEL in json.dumps(event) for event in run.reasoning_events) or SENTINEL in run.output
    cline_runs["reasoning_displayed"] = displayed
    _say(request, f"e2e021-015: Cline displayed the reasoning: {displayed} "
                  f"(reasoning events: {len(run.reasoning_events)}, field {REASONING_FIELD})")


# --------------------------------------------------------------------------
# Every row this module wrote
# --------------------------------------------------------------------------


def test_zz_every_row_is_v1_code_and_real_time(cline_exe, rows):
    """Named to run last; `cline_exe` first so a missing Cline errors before any child starts."""
    written = rows("text") + rows("drop") + rows("reason")
    assert written
    assert {(row["ingress"], row["profile"]) for row in written} == {("v1", "code")}
    assert all(row["streamed_realtime"] is True for row in written)
