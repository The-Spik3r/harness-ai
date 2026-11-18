"""The two-instance balancer stack as processes (PRD-019 STORY-007, D8; STORY-008 reuses it).

One `Balancer` is: the scripted OpenRouter stub, two uvicorn instances of the
real app (through `tests/_lb_instance.py`, which adds request counters and
breaker hooks and is never imported by `app/`), and one Caddy running
`deploy/lb/Caddyfile` with only its upstream line replaced. Ports are picked
at runtime, every wait is a deadline loop that names the child and shows the
tail of its log, and `stop()` kills every child (also after a failed `start()`).

Killing needs more than `Popen.kill()`: a venv `python.exe` on Windows is a
launcher whose real interpreter is a child (`tests/e2e/_live.py:75-80`), so
`kill()` would leave uvicorn holding its port and a database client. The kill
is `tests.e2e._live.kill_tree` (`taskkill /F /T`, or the process group on POSIX,
which is why each Popen starts a new session), then a check that the port
closed.
"""

import json
import os
import pathlib
import subprocess
import sys
import time
from typing import Callable, Optional

import httpx

from tests._caddy import caddy_binary, caddy_env, free_port
from tests.conftest import child_db_env
from tests.e2e._live import kill_tree, port_closed_within

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
CADDYFILE = REPO_ROOT / "deploy" / "lb" / "Caddyfile"
LB_INSTANCE = REPO_ROOT / "tests" / "_lb_instance.py"
STUB = REPO_ROOT / "scripts" / "stub_openrouter.py"

# PRD-019 F3: the one upstream line, restated (not derived) from
# tests/test_lb_caddyfile.py. The Caddyfile promises it stays one literal line.
UPSTREAM_LINE = "reverse_proxy harness-a:{$PORT} harness-b:{$PORT} {"

# Instance boot: Presidio is off here, but the first import of the app is slow
# on a cold disk (tests/e2e/_live.py:276-290 waits 180 s for the same reason).
BOOT_DEADLINE_S = 180

ADMIN_TOKEN = "balancer-test-admin-token"
OPENROUTER_API_KEY = "balancer-test-key"

DEFAULT_SCRIPT = {"default": {"content": "ok", "finish_reason": "stop"}}


def log_tail(path: pathlib.Path, lines: int = 40) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return f"(no log: {exc})"
    return "\n".join(text.splitlines()[-lines:])


class Child:
    """One process with its log file, its port and a tree kill."""

    def __init__(self, name: str, command: list, env: dict, log: pathlib.Path, port: int):
        self.name = name
        self.port = port
        self.log = log
        self._handle = open(log, "w", encoding="utf-8")
        # start_new_session: kill_tree's POSIX branch kills the process group.
        self.proc = subprocess.Popen(
            command,
            cwd=str(REPO_ROOT),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=self._handle,
            stderr=subprocess.STDOUT,
            start_new_session=(os.name != "nt"),
        )

    def alive(self) -> bool:
        return self.proc.poll() is None

    def kill(self) -> None:
        """Kill the tree and wait for the port to close. Returns whether it closed."""
        # Also when the launcher already exited: a real interpreter child may
        # still hold the port (taskkill /T on a dead PID is harmless).
        kill_tree(self.proc)
        try:
            self._handle.close()
        except OSError:
            pass
        return port_closed_within(self.port, 10)


def wait_until(
    condition: Callable[[], bool],
    deadline_s: float,
    what: str,
    child: Optional[Child] = None,
    interval: float = 0.25,
) -> None:
    """Poll `condition` until true or the deadline; name the child and its log on failure."""
    deadline = time.monotonic() + deadline_s
    while True:
        if child is not None and not child.alive():
            raise AssertionError(
                f"{child.name} exited {child.proc.returncode} before {what}; log tail:\n"
                f"{log_tail(child.log)}"
            )
        try:
            if condition():
                return
        except httpx.HTTPError:
            pass
        if time.monotonic() > deadline:
            tail = f"; log tail:\n{log_tail(child.log)}" if child is not None else ""
            raise AssertionError(f"{what} did not happen within {deadline_s}s{tail}")
        time.sleep(interval)


def _status(url: str) -> int:
    with httpx.Client(trust_env=False, timeout=5) as client:
        return client.get(url).status_code


class Instance:
    """One uvicorn child of the app, with the `/__test__/*` helpers."""

    def __init__(self, index: int, child: Child, drain_file: pathlib.Path):
        self.index = index
        self.child = child
        self.port = child.port
        self.base = f"http://127.0.0.1:{child.port}"
        self.drain_file = drain_file

    def _call(self, method: str, path: str) -> dict:
        with httpx.Client(trust_env=False, timeout=30) as client:
            response = client.request(method, f"{self.base}/__test__/{path}")
        response.raise_for_status()
        return response.json()

    def counters(self) -> dict:
        return self._call("GET", "counters")

    def reset_counters(self) -> None:
        self._call("POST", "reset-counters")

    def init_db(self) -> None:
        self._call("POST", "init-db")

    def force_breaker_open(self) -> None:
        self._call("POST", "breaker/open")

    def reset_breaker(self) -> None:
        self._call("POST", "breaker/reset")


class Balancer:
    """stub + two instances + Caddy. `start()` then `stop()`; a fixture owns both."""

    def __init__(
        self,
        database_url: str,
        tmp: pathlib.Path,
        script: Optional[dict] = None,
        instance_env: Optional[dict] = None,
    ):
        self.database_url = database_url
        self.tmp = pathlib.Path(tmp)
        self.script = script if script is not None else DEFAULT_SCRIPT
        self.instance_env = dict(instance_env or {})
        self.instances: list = []
        self.stub: Optional[Child] = None
        self.caddy: Optional[Child] = None
        self.lb_port: Optional[int] = None
        self.lb_base: Optional[str] = None

    # -- start -----------------------------------------------------------

    def start(self) -> "Balancer":
        try:
            self._start()
        except BaseException:
            self.stop()
            raise
        return self

    def _upstream_port(self, index: int) -> int:
        """Where the balancer sends instance `index`. STORY-008 overrides this to
        point at a per-instance front Caddy."""
        return self.instances[index].port

    def _start(self) -> None:
        self.tmp.mkdir(parents=True, exist_ok=True)
        script_path = self.tmp / "stub-script.json"
        script_path.write_text(json.dumps(self.script), encoding="utf-8")

        stub_port = free_port()
        self.stub = Child(
            "stub",
            [sys.executable, str(STUB), "--port", str(stub_port), "--script", str(script_path)],
            dict(os.environ),
            self.tmp / "stub.log",
            stub_port,
        )
        wait_until(
            lambda: _status(f"http://127.0.0.1:{stub_port}/health") == 200,
            30, "the stub answering /health", self.stub,
        )

        children = []
        for index in range(2):
            port = free_port()
            drain = self.tmp / f"drain-{index}"
            env = {
                **os.environ,
                **child_db_env(self.database_url),
                "TURSO_AUTH_TOKEN": "",
                "PYTHONPATH": str(REPO_ROOT),
                "DRAIN_FILE": str(drain),
                "OPENROUTER_BASE_URL": f"http://127.0.0.1:{stub_port}/v1",
                "OPENROUTER_API_KEY": OPENROUTER_API_KEY,
                "ADMIN_TOKEN": ADMIN_TOKEN,
                "AUDIT_BUFFER_DIR": str(self.tmp / f"audit-{index}"),
                # Not under test here. Off skips the Presidio boot.
                "PII_REDACTION_ENABLED": "false",
                # The children start before the first per-test schema reset, and
                # the lifespan's authz bootstrap refuses an empty users table
                # when RBAC is on (app/services/authz.py:137-152). Authentication
                # (401) is unaffected: RBAC only gates authorization.
                "RBAC_ENABLED": "false",
                **self.instance_env,
            }
            child = Child(
                f"instance-{'ab'[index]}",
                [sys.executable, str(LB_INSTANCE), "--port", str(port)],
                env,
                self.tmp / f"instance-{index}.log",
                port,
            )
            self.instances.append(Instance(index, child, drain))
            children.append(child)

        # Both are already starting; wait for each in turn (the boots overlap).
        for inst in self.instances:
            wait_until(
                lambda inst=inst: _status(f"{inst.base}/health") == 200,
                BOOT_DEADLINE_S, f"{inst.child.name} answering /health", inst.child,
            )
        for inst in self.instances:
            wait_until(
                lambda inst=inst: _status(f"{inst.base}/ready") == 200,
                30, f"{inst.child.name} answering /ready 200", inst.child,
            )

        original = CADDYFILE.read_text(encoding="utf-8")
        assert original.count(UPSTREAM_LINE) == 1, (
            f"{CADDYFILE} must hold the upstream line exactly once: {UPSTREAM_LINE!r}"
        )
        substituted = original.replace(
            UPSTREAM_LINE,
            f"reverse_proxy 127.0.0.1:{self._upstream_port(0)} "
            f"127.0.0.1:{self._upstream_port(1)} {{",
        )
        assert substituted != original
        caddyfile = self.tmp / "Caddyfile"
        with open(caddyfile, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(substituted)

        self.lb_port = free_port()
        self.lb_base = f"http://127.0.0.1:{self.lb_port}"
        self.caddy = Child(
            "caddy",
            [caddy_binary(), "run", "--config", str(caddyfile), "--adapter", "caddyfile"],
            caddy_env(self.lb_port, free_port()),
            self.tmp / "caddy.log",
            self.lb_port,
        )
        wait_until(
            lambda: _status(f"{self.lb_base}/ready") == 200,
            30, "the balancer answering /ready 200", self.caddy,
        )

    # -- operations ------------------------------------------------------

    def drain(self, index: int) -> None:
        self.instances[index].drain_file.write_text("", encoding="utf-8")

    def undrain(self, index: int) -> None:
        self.instances[index].drain_file.unlink(missing_ok=True)

    def kill_instance(self, index: int) -> None:
        """SIGKILL-equivalent for one instance (STORY-008)."""
        child = self.instances[index].child
        assert child.kill(), f"{child.name}: port {child.port} still open 10 s after the kill"

    # -- stop ------------------------------------------------------------

    def stop(self) -> None:
        """Idempotent. Caddy, then instances, then the stub; every kill is attempted
        before any failure is raised."""
        failures = []
        children = [self.caddy] + [i.child for i in self.instances] + [self.stub]
        for child in children:
            if child is None:
                continue
            try:
                if not child.kill():
                    failures.append(f"{child.name}: port {child.port} still open 10 s after the kill")
            except Exception as exc:  # noqa: BLE001 - keep killing the rest
                failures.append(f"{child.name}: {exc!r}")
        self.caddy = None
        self.instances = []
        self.stub = None
        if failures:
            raise AssertionError("; ".join(failures))
