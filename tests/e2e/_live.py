"""Subprocess plumbing shared by the client E2E modules (PRD-015 STORY-015 to STORY-017).

Nothing here is a test or a fixture. Each module keeps its own thin
module-scoped fixtures, with its own stub script, allowlist and settings, and
builds them from these helpers: the stub upstream and `uvicorn app.main:app` as
subprocesses on ephemeral ports, a child env pinned to the E2E libSQL, and the
user bootstrap and audit reads as children.

Nothing here reaches storage in-process. Every storage access is a child with
`DATABASE_URL` pinned to `HARNESS_E2E_LIBSQL_URL`, which must be loopback, so an
E2E run never touches the unit suite's database or a real one.
"""

import contextlib
import json
import os
import re
import secrets
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit

import httpx
import pytest

from tests.conftest import child_db_env

REPO_ROOT = Path(__file__).resolve().parents[2]
LOOPBACK = {"127.0.0.1", "localhost", "::1"}

# Prints one user's rows as JSON. A single-quoted constant on purpose: it runs
# as `python -c` in a child with DATABASE_URL pinned to the E2E endpoint.
DUMP = (
    "import dataclasses, json, sys\n"
    "from app.db.database import list_audit_logs\n"
    "rows = list_audit_logs(limit=1000, user_id=sys.argv[1])\n"
    "print(json.dumps([dataclasses.asdict(row) for row in rows]))\n"
)


def read_line_within(stream, timeout):
    box = []
    reader = threading.Thread(target=lambda: box.append(stream.readline()), daemon=True)
    reader.start()
    reader.join(timeout)
    assert box and box[0], f"no line from the child within {timeout}s"
    return box[0]


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def port_closed_within(port: int, timeout: float) -> bool:
    """Whether nothing accepts on `port` within `timeout`.

    A wait, not one probe: a venv's `Scripts\\python.exe` on Windows is a
    launcher whose interpreter is a child process. `terminate()` ends the
    launcher, and the child (which holds the socket) follows it a moment later,
    when the launcher's job object closes. A real orphan never closes.
    """
    deadline = time.monotonic() + timeout
    while True:
        with socket.socket() as sock:
            sock.settimeout(1)
            if sock.connect_ex(("127.0.0.1", port)) != 0:
                return True
        if time.monotonic() > deadline:
            return False
        time.sleep(0.2)


def stop(proc: subprocess.Popen, timeout: float) -> None:
    if proc.poll() is None:
        proc.terminate()
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def resolve_e2e_db_url(recipe: str) -> str:
    """`HARNESS_E2E_LIBSQL_URL`, or fail with `recipe`. Never another database."""
    url = os.environ.get("HARNESS_E2E_LIBSQL_URL", "").strip()
    if not url:
        pytest.fail(f"HARNESS_E2E_LIBSQL_URL is not set. Start a throwaway libSQL: {recipe}")
    if urlsplit(url).hostname not in LOOPBACK:
        pytest.fail(f"HARNESS_E2E_LIBSQL_URL must be a loopback endpoint, got host {urlsplit(url).hostname!r}")
    return url


def child_env(db_url: str, **extra) -> dict:
    return {
        **os.environ,
        **child_db_env(db_url),
        "TURSO_AUTH_TOKEN": "",
        "PYTHONPATH": str(REPO_ROOT),
        **extra,
    }


def run_child(cwd: Path, env: dict, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, *args],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def create_user(run, user_id: str, role: str = "user") -> str:
    """The new user's token. `run(*args)` runs a child, as `run_child` does."""
    proc = run(str(REPO_ROOT / "scripts" / "manage_users.py"), "create-user", "--user-id", user_id, "--role", role)
    # The token is on stdout: report only the exit code and stderr.
    assert proc.returncode == 0, f"create-user {user_id} exited {proc.returncode}: {proc.stderr}"
    match = re.search(r"Token \(save this now[^)]*\): (\S+)", proc.stdout)
    assert match, f"create-user {user_id} printed no token line"
    return match.group(1)


def dump_rows(run, user_id: str) -> list:
    """That user's audit rows, oldest first."""
    proc = run("-c", DUMP, user_id)
    assert proc.returncode == 0, f"audit dump exited {proc.returncode}: {proc.stderr}"
    return sorted(json.loads(proc.stdout), key=lambda row: row["id"])


class Stub:
    def __init__(self, proc: subprocess.Popen, base: str) -> None:
        self.proc = proc
        self.base = base
        self.lines: list = []
        threading.Thread(target=self._drain, daemon=True).start()

    def _drain(self) -> None:
        for line in self.proc.stderr:
            self.lines.append(line.rstrip("\n"))

    def requests(self) -> list:
        """The rule label of every chat request the stub has answered so far."""
        return [line.split(" rule=", 1)[1].split()[0] for line in list(self.lines) if " rule=" in line]

    def settle(self) -> list:
        """`requests()` once the log has been quiet for 0.3 s (the drain is a thread)."""
        seen = len(self.lines)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            time.sleep(0.3)
            if len(self.lines) == seen:
                break
            seen = len(self.lines)
        return self.requests()


@contextlib.contextmanager
def start_stub(script: Path, cwd: Path):
    proc = subprocess.Popen(
        [sys.executable, str(REPO_ROOT / "scripts" / "stub_openrouter.py"), "--port", "0", "--script", str(script)],
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        line = read_line_within(proc.stdout, 10)
        assert line.startswith("stub_openrouter: listening on http://127.0.0.1:"), line
        yield Stub(proc, line.split("listening on ", 1)[1].strip())
    finally:
        stop(proc, 10)


class Harness:
    def __init__(self, base: str, port: int, admin_token: str) -> None:
        self.base = base
        self.port = port
        self.admin_token = admin_token


@contextlib.contextmanager
def start_harness(cwd: Path, env: dict):
    """`uvicorn app.main:app` on a free port, with `env` plus a fresh ADMIN_TOKEN.

    Start it after the users exist: startup refuses an empty users table.
    """
    port = free_port()
    admin_token = secrets.token_urlsafe(16)
    log_path = cwd / "uvicorn.log"
    with open(log_path, "w", encoding="utf-8") as log:
        proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--app-dir", str(REPO_ROOT),
             "--host", "127.0.0.1", "--port", str(port)],
            cwd=str(cwd),
            env={**env, "ADMIN_TOKEN": admin_token},
            stdout=log,
            stderr=subprocess.STDOUT,
        )
    base = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 180  # Presidio and spaCy load at startup
        while True:
            if proc.poll() is not None:
                pytest.fail(f"uvicorn exited {proc.returncode} before /health answered:\n"
                            + log_path.read_text(encoding="utf-8", errors="replace"))
            try:
                if httpx.get(f"{base}/health", timeout=2).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            if time.monotonic() > deadline:
                pytest.fail("uvicorn did not answer /health within 180 s")
            time.sleep(0.5)
        yield Harness(base, port, admin_token)
    finally:
        stop(proc, 15)
        assert port_closed_within(port, 10), f"something still listens on :{port} 10 s after stop"


# --------------------------------------------------------------------------
# What a client sends: a recording proxy, and the ignored_params it implies
# --------------------------------------------------------------------------

# Mirrors of app/services/v1_translate.py:98-117 (FORWARDED,
# REJECTED_UNLESS_DEFAULT's keys, _STRUCTURAL). Literals, not an import:
# importing app.services builds app.config's Settings() in this process, which
# reads the developer's .env. tests/test_e2e_live.py keeps them equal.
FORWARDED = frozenset({"temperature", "top_p", "max_tokens", "stop", "max_completion_tokens"})
REJECTED_UNLESS_DEFAULT = frozenset({
    "tools", "functions", "tool_choice", "function_call", "n", "logprobs", "top_logprobs",
    "response_format", "modalities", "audio",
})
STRUCTURAL = frozenset({"model", "messages", "stream", "stream_options"})
IGNORED_MESSAGE_NAME = "messages[].name"


def expected_ignored_params(entry: dict) -> Optional[str]:
    """The `ignored_params` a request with `entry`'s shape must leave on its row.

    `entry` is a `Recorder.log` item. The rule is PRD-015 Section 7.3's: every
    top-level key neither forwarded, nor rejected-unless-default, nor read by
    the translator, plus `stream_options.<key>` other than `include_usage`,
    plus `messages[].name` (v1_translate.IGNORED_MESSAGE_NAME) when a message
    carried a `name`. Sorted, comma-joined, None if empty.
    """
    ignored = set(entry["keys"]) - FORWARDED - REJECTED_UNLESS_DEFAULT - STRUCTURAL
    ignored |= {f"stream_options.{key}" for key in entry["stream_options_keys"] if key != "include_usage"}
    if "name" in entry["message_keys"]:
        ignored.add(IGNORED_MESSAGE_NAME)
    return ",".join(sorted(ignored)) or None


def _shape(value) -> str:
    if value is None:
        return "null"
    if value == []:
        return "[]"
    return "non-empty"


def request_shape(body: dict) -> dict:
    """What `Recorder` keeps of one request: names, roles and the model. Never content."""
    messages = body.get("messages") if isinstance(body.get("messages"), list) else []
    stream_options = body.get("stream_options")
    return {
        "keys": sorted(body),
        "model": body.get("model"),
        "stream": body.get("stream"),
        "stream_options_keys": sorted(stream_options) if isinstance(stream_options, dict) else [],
        "roles": [message.get("role") for message in messages if isinstance(message, dict)],
        "message_keys": sorted({key for message in messages if isinstance(message, dict) for key in message}),
        **{key: _shape(body[key]) if key in body else "absent" for key in ("tools", "tool_choice", "functions")},
    }


class _RecordingHandler(BaseHTTPRequestHandler):
    recorder: "Recorder"
    _RELAYED = ("content-type", "x-should-retry", "x-harness-audit-id")
    # X-Harness-Device passes too (PRD-015 Section 7.2): without it the row's
    # `device` would be None because of the proxy, not the client.
    _FORWARDED = ("authorization", "content-type", "accept", "x-harness-device")

    def log_message(self, *args) -> None:
        pass  # no header echo, and ASCII-only output

    def _relay(self, method: str, raw: Optional[bytes], entry: dict) -> None:
        headers = {key: value for key, value in self.headers.items() if key.lower() in self._FORWARDED}
        with httpx.Client(timeout=None) as client, \
                client.stream(method, self.recorder.upstream + self.path, content=raw, headers=headers) as upstream:
            with self.recorder.lock:
                entry["status"] = upstream.status_code
            self.send_response(upstream.status_code)
            for key in self._RELAYED:
                if key in upstream.headers:
                    self.send_header(key, upstream.headers[key])
            # Raw bytes, then close: no chunked re-encoding, and each SSE chunk
            # (keep-alives included) is flushed as it arrives.
            self.send_header("Connection", "close")
            self.end_headers()
            partial = b""
            for chunk in upstream.iter_raw():
                # Count SSE comment lines (": keep-alive") before relaying the
                # chunk, carrying a line split across chunks. Only the count is kept.
                *lines, partial = (partial + chunk).split(b"\n")
                with self.recorder.lock:
                    entry["keepalives"] += sum(1 for line in lines if line.startswith(b":"))
                self.wfile.write(chunk)
                self.wfile.flush()

    def _record(self, method: str, shape: dict) -> dict:
        has_device = "x-harness-device" in {key.lower() for key in self.headers}
        entry = {"method": method, "path": self.path, **shape,
                 "status": None, "keepalives": 0, "device_header": has_device}
        with self.recorder.lock:
            self.recorder.log.append(entry)
        return entry

    def do_POST(self) -> None:
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        try:
            shape = request_shape(json.loads(raw))
        except (ValueError, AttributeError):
            shape = {"keys": None}
        self._relay("POST", raw, self._record("POST", shape))

    def do_GET(self) -> None:
        self._relay("GET", None, self._record("GET", {}))


class Recorder:
    """A proxy in front of the harness that records request shapes (`request_shape`).

    It tells what a client sends: the audit row cannot, because an accepted
    default such as `tools: []` is never recorded as ignored. No content, no
    header value and no token is kept.

    Each `log` entry holds `method` and `path`, the shape for a POST, and
    `status` (the harness's answer), `keepalives` (SSE comment lines relayed
    to the client) and `device_header` (whether `X-Harness-Device` was sent,
    never its value).
    """

    def __init__(self, upstream: str) -> None:
        self.upstream = upstream
        self.log: list = []
        self.lock = threading.Lock()
        handler = type("Handler", (_RecordingHandler,), {"recorder": self})
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def posts(self) -> list:
        with self.lock:
            return [entry for entry in self.log if entry["method"] == "POST"]

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
