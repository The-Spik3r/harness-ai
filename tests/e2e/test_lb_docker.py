"""PRD-019 STORY-010: the balanced stack in Docker, end to end.

The real image runs twice behind the shipped docker-compose.lb.yml, laid over by
tests/e2e/docker/compose.lb-e2e.yml under its own project (`harness-lb-e2e`):
throwaway libSQL, a stub upstream inside each instance container, the balancer
published on a free loopback port. The tests share one stack and run in file
order; each leaves the stack with both instances up.

    AC 1  test_stack_comes_up_healthy: both instances `service_healthy`, the
          balancer answers /health and /ready from the host
    AC 2  test_websocket_upgrade_is_sticky_across_reconnects: 101 on /_event
          and the same instance serves every reconnect carrying the cookie
    AC 3  test_failover_to_the_other_instance_and_cookie_reset: SIGKILL the
          pinned instance; the upgrade lands on the other with a new cookie
    AC 4  test_rolling_restart_script_under_query_loop: scripts/rolling_restart.sh
          (rc 0) while /query is posted through the balancer: every call 200
    AC 5  the `stack` fixture: `down -v` always, then a leftovers check

Which instance holds a websocket is read from the kernel, not from logs (Reflex
logs no upgrade and the in-container Caddyfile has no access log): the Caddy to
backend leg of a proxied websocket is one ESTABLISHED socket whose local port is
BACKEND_INTERNAL_PORT (8001), counted from /proc/net/tcp inside each container.
Caddy's keep-alive pool and the balancer's health checks add noise, so a count is
a (min, max) over a short window: the baseline is taken just before connecting,
the held count while the socket is open, and the instance is the one whose held
minimum exceeds its baseline maximum, on exactly one side.

Run (skipped without `--run-e2e`, and without HARNESS_E2E_DOCKER=1, because it
builds the image and needs Docker; about 8 minutes, most of it image build and
boot):

    HARNESS_E2E_DOCKER=1 python -m pytest tests/e2e/test_lb_docker.py -m e2e --run-e2e -v -s

The image is tagged `harness-lb-e2e:local` and stays after the run (like the
smoke's); containers, volumes and the network are removed with `down -v`.
"""

import contextlib
import os
import secrets
import subprocess
import threading
import time
import uuid

import httpx
import pytest
from websockets.exceptions import InvalidStatus
from websockets.sync.client import connect

from tests.e2e import _live
from tests.test_rolling_restart_script import _find_bash

# websockets 17 deprecates holding `connect()` without `with`; the tests keep the
# socket open across polling windows and close it in a `finally`.
pytestmark = [
    pytest.mark.e2e,
    pytest.mark.filterwarnings(r"ignore:connect\(\) must be used as a context manager:DeprecationWarning"),
]

REPO_ROOT = _live.REPO_ROOT
_PROJECT = "harness-lb-e2e"
_FILES = ["docker-compose.lb.yml", "tests/e2e/docker/compose.lb-e2e.yml"]
_COMPOSE = ["docker", "compose", "-p", _PROJECT, *[a for f in _FILES for a in ("-f", f)]]
_INSTANCES = ("harness-a", "harness-b")
_IMAGE = "harness-lb-e2e:local"
_MODEL = "openai/gpt-4o"  # compose.lb-e2e.yml MODEL_ALLOWLIST
_COOKIE = "harness_lb"
NONCE = secrets.token_hex(4)

# Run inside an instance: (min, max) of ESTABLISHED sockets whose local port is
# BACKEND_INTERNAL_PORT over a window. State 01 is ESTABLISHED; ports are hex.
_COUNT_SCRIPT = """
import os, time
port = "%04X" % int(os.environ["BACKEND_INTERNAL_PORT"])
def count():
    n = 0
    for path in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            lines = open(path).read().splitlines()[1:]
        except OSError:
            continue
        for line in lines:
            f = line.split()
            if f[1].rsplit(":", 1)[1] == port and f[3] == "01":
                n += 1
    return n
seen = []
end = time.monotonic() + float(os.environ["WINDOW"])
while True:
    seen.append(count())
    if time.monotonic() >= end:
        break
    time.sleep(0.4)
print(min(seen), max(seen))
"""

_READY_SCRIPT = """
import os, urllib.request as r, urllib.error as e
try:
    print(r.urlopen("http://127.0.0.1:%s/ready" % os.environ["PORT"], timeout=3).status)
except e.HTTPError as x:
    print(x.code)
except Exception:
    print(0)
"""


def _compose(env: dict, *args: str, timeout: float = 600, check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        [*_COMPOSE, *args], cwd=str(REPO_ROOT), env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=timeout,
    )
    if check and proc.returncode != 0:
        pytest.fail(f"docker compose {' '.join(args[:3])} exited {proc.returncode}:\n{proc.stderr[-3000:]}")
    return proc


def _instance_ready(env: dict, svc: str) -> int:
    proc = _compose(env, "exec", "-T", svc, "python", "-c", _READY_SCRIPT, timeout=60, check=False)
    lines = proc.stdout.strip().splitlines()
    return int(lines[-1]) if proc.returncode == 0 and lines and lines[-1].isdigit() else 0


def _wait(what: str, predicate, timeout: float, poll: float = 1.0):
    deadline = time.monotonic() + timeout
    while True:
        value = predicate()
        if value:
            return value
        if time.monotonic() > deadline:
            pytest.fail(f"{what}: not within {timeout:.0f} s")
        time.sleep(poll)


def _wait_ready(env: dict, svc: str, timeout: float = 240) -> None:
    _wait(f"{svc} /ready 200", lambda: _instance_ready(env, svc) == 200, timeout, poll=3)


@pytest.fixture(scope="module")
def stack(tmp_path_factory):
    """(env, base URL, user token). Torn down with `down -v` whatever happens."""
    if os.environ.get("HARNESS_E2E_DOCKER", "").strip() != "1":
        pytest.skip("balanced Docker E2E: set HARNESS_E2E_DOCKER=1 (it builds the image and needs Docker)")
    if subprocess.run(["docker", "info"], capture_output=True).returncode != 0:
        pytest.fail("HARNESS_E2E_DOCKER=1 but `docker info` fails: start Docker Desktop first")
    port = _live.free_port()
    env = {
        **os.environ,
        "MSYS_NO_PATHCONV": "1",
        # D7: the image is built with the default port and a developer's shell PORT must not leak.
        "PORT": "8000",
        "HARNESS_LB_E2E_PORT": str(port),
        "LB_COOKIE_SECRET": secrets.token_hex(16),
        "HARNESS_LB_E2E_ADMIN_TOKEN": secrets.token_urlsafe(16),
    }
    base = f"http://127.0.0.1:{port}"
    workdir = tmp_path_factory.mktemp("lb_docker")
    _compose(env, "down", "-v", "--remove-orphans", timeout=180, check=False)  # a previous run's leftovers
    try:
        build = subprocess.run(
            ["docker", "build", "-t", _IMAGE, "."], cwd=str(REPO_ROOT), env=env,
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1800,
        )
        assert build.returncode == 0, f"docker build exited {build.returncode}:\n{build.stderr[-3000:]}"
        _compose(env, "up", "-d", "libsql", timeout=180)

        def run(*args: str) -> subprocess.CompletedProcess:
            args = tuple(os.path.relpath(a, REPO_ROOT).replace("\\", "/") if a.startswith(str(REPO_ROOT)) else a
                         for a in args)
            return _compose(env, "run", "--rm", "--no-deps", "-T", _INSTANCES[0], "python", *args,
                            timeout=300, check=False)

        # The users table must have a row before an instance starts (RBAC
        # bootstrap), and libSQL may still be starting: retry for 30 s.
        deadline = time.monotonic() + 30
        while True:
            try:
                token = _live.create_user(run, f"lb-{NONCE}")
                break
            except AssertionError:
                if time.monotonic() > deadline:
                    raise
                time.sleep(2)

        _compose(env, "up", "-d", "--wait", "--wait-timeout", "300", timeout=420)
        # The balancer's first active health check can take up to its interval.
        _wait("the balancer's /ready 200", lambda: _status(f"{base}/ready") == 200, 240, poll=3)
        yield env, base, token
    finally:
        logs = _compose(env, "logs", "--no-color", "--tail", "300", timeout=120, check=False)
        log_path = workdir / "compose.log"
        log_path.write_text(logs.stdout + logs.stderr, encoding="utf-8")
        print(f"\ncompose logs: {log_path}")
        _compose(env, "down", "-v", "--remove-orphans", timeout=300, check=False)
        left = subprocess.run(
            ["docker", "ps", "-aq", "--filter", f"label=com.docker.compose.project={_PROJECT}"],
            capture_output=True, text=True, timeout=60,
        ).stdout.split()
        volumes = subprocess.run(
            ["docker", "volume", "ls", "-q", "--filter", f"label=com.docker.compose.project={_PROJECT}"],
            capture_output=True, text=True, timeout=60,
        ).stdout.split()
        if left or volumes:
            print(f"\nWARNING: {_PROJECT} left containers {left} volumes {volumes}")


def _status(url: str) -> int:
    try:
        return httpx.get(url, timeout=5).status_code
    except httpx.HTTPError:
        return 0


def _cookie_from(response: httpx.Response) -> str | None:
    for raw in response.headers.get_list("set-cookie"):
        first = raw.split(";", 1)[0]
        if first.startswith(f"{_COOKIE}="):
            return first.split("=", 1)[1]
    return None


def _first_cookie(base: str) -> str:
    response = httpx.get(f"{base}/", timeout=30)
    assert response.status_code == 200, response.status_code
    cookie = _cookie_from(response)
    assert cookie and len(cookie) == 64, "the balancer set no 64-hex harness_lb cookie"
    return cookie


def _ws_url(base: str) -> str:
    return f"ws://{base.removeprefix('http://')}/_event/?EIO=4&transport=websocket&token={uuid.uuid4()}"


def _ws_headers(cookie: str, base: str, origin: bool) -> dict:
    headers = {"Cookie": f"{_COOKIE}={cookie}"}
    if origin:
        headers["Origin"] = base
    return headers


def _open_ws(base: str, cookie: str, origin: bool = False):
    """A connected websocket (status 101 asserted); keep it referenced to hold it open."""
    ws = connect(_ws_url(base), additional_headers=_ws_headers(cookie, base, origin), open_timeout=15)
    assert ws.response.status_code == 101, ws.response.status_code
    return ws


def _count_window(env: dict, svc: str, seconds: float) -> tuple[int, int]:
    proc = _compose(
        env, "exec", "-T", "-e", f"WINDOW={seconds}", svc, "python", "-c", _COUNT_SCRIPT,
        timeout=120, check=False,
    )
    assert proc.returncode == 0, f"counting sockets in {svc}: {proc.stderr[-500:]}"
    low, high = proc.stdout.split()[-2:]
    return int(low), int(high)


def _baseline(env: dict) -> dict:
    """Per instance: the highest backend socket count seen in a quiet window."""
    return {svc: _count_window(env, svc, 2.0)[1] for svc in _INSTANCES}


def _holders(env: dict, base: dict, extra: int, deadline_s: float = 20.0) -> list[str]:
    """Instances whose count stays at least `extra` above baseline while the sockets are held.

    The held minimum over a window must exceed the baseline maximum by `extra`:
    a keep-alive that comes and goes cannot raise the minimum for the whole window.
    """
    deadline = time.monotonic() + deadline_s
    while True:
        held = [svc for svc in _INSTANCES if _count_window(env, svc, 2.0)[0] >= base[svc] + extra]
        if len(held) == 1 or time.monotonic() > deadline:
            return held
        time.sleep(0.5)


def _serving(env: dict, base_url: str, cookie: str, extra: int = 1, origin: bool = False) -> str:
    """Open `extra` websockets with the cookie, return the instance that holds them, close them."""
    before = _baseline(env)
    sockets = [_open_ws(base_url, cookie, origin) for _ in range(extra)]
    try:
        holders = _holders(env, before, extra)
    finally:
        for ws in sockets:
            with contextlib.suppress(Exception):
                ws.close()
    assert len(holders) == 1, (
        f"{extra} websocket(s) must raise the backend socket count on exactly one instance "
        f"(baseline {before}, holders {holders})"
    )
    return holders[0]


def test_stack_comes_up_healthy(stack):
    env, base, _ = stack
    ps = _compose(env, "ps", "--format", "{{.Service}} {{.Health}}", timeout=60).stdout.split("\n")
    health = {line.split()[0]: line.split()[1] for line in ps if len(line.split()) == 2}
    assert health.get("harness-a") == "healthy" and health.get("harness-b") == "healthy", health
    assert httpx.get(f"{base}/health", timeout=10).status_code == 200
    assert httpx.get(f"{base}/ready", timeout=10).status_code == 200
    for svc in _INSTANCES:
        assert _instance_ready(env, svc) == 200, svc


def test_websocket_upgrade_is_sticky_across_reconnects(stack):
    env, base, _ = stack
    cookie = _first_cookie(base)
    # Reflex may refuse an upgrade without an Origin header: use one if the first try is refused.
    origin = False
    try:
        _open_ws(base, cookie).close()
    except InvalidStatus as err:
        print(f"\nupgrade without Origin refused ({err.response.status_code}); sending Origin {base}")
        origin = True
        _open_ws(base, cookie, origin=True).close()
    print(f"\nOrigin header needed: {origin}")

    served = [_serving(env, base, cookie, origin=origin) for _ in range(3)]
    assert len(set(served)) == 1, f"three reconnects with one cookie landed on {served}"
    pinned = served[0]
    # Two sockets held at once with the cookie: the same instance carries both.
    assert _serving(env, base, cookie, extra=2, origin=origin) == pinned
    print(f"\nsticky instance: {pinned}")


def test_failover_to_the_other_instance_and_cookie_reset(stack):
    env, base, _ = stack
    cookie = _first_cookie(base)
    pinned = _serving(env, base, cookie)
    other = next(svc for svc in _INSTANCES if svc != pinned)

    _compose(env, "kill", "-s", "SIGKILL", pinned, timeout=120)
    try:
        before = {other: _count_window(env, other, 2.0)[1]}
        deadline = time.monotonic() + 20
        ws = None
        while ws is None:
            try:
                ws = connect(_ws_url(base), additional_headers={"Cookie": f"{_COOKIE}={cookie}"}, open_timeout=15)
            except Exception as err:  # the balancer answers 503 until it knows the instance is down
                if time.monotonic() > deadline:
                    pytest.fail(f"no upgrade through the balancer within 20 s of the kill: {err!r}")
                time.sleep(1)
        try:
            assert ws.response.status_code == 101
            held = _count_window(env, other, 2.0)[0]
            assert held >= before[other] + 1, f"the survivor {other} holds no new websocket ({held} vs {before})"
        finally:
            ws.close()
        # The old cookie names a dead instance: the survivor answers and the
        # balancer re-sets the cookie (STORY-004 findings).
        response = httpx.get(f"{base}/", headers={"Cookie": f"{_COOKIE}={cookie}"}, timeout=30)
        assert response.status_code == 200
        new_cookie = _cookie_from(response)
        assert new_cookie, "no Set-Cookie after the pinned instance died"
        assert new_cookie != cookie
    finally:
        _compose(env, "up", "-d", "--no-deps", pinned, timeout=300)
        _wait_ready(env, pinned)
    # The balancer must see both again before the next test (health check interval).
    def both_routable():
        seen = {_cookie_from(httpx.get(f"{base}/ready", timeout=10)) for _ in range(12)}
        return len(seen - {None}) == 2
    _wait("both instances routable through the balancer", both_routable, 90, poll=2)


def test_rolling_restart_script_under_query_loop(stack):
    env, base, token = stack
    bash = _find_bash()
    if bash is None:
        pytest.skip("no usable bash for scripts/rolling_restart.sh")
    results: list[tuple[float, object]] = []
    stop = threading.Event()
    started = time.monotonic()

    def loop():
        n = 0
        with httpx.Client(timeout=30) as client:
            while not stop.is_set():
                n += 1
                try:
                    r = client.post(
                        f"{base}/query", headers={"Authorization": f"Bearer {token}"},
                        json={"prompt": f"SMOKE-QUERY {NONCE}-{n}", "model": _MODEL},
                    )
                    results.append((time.monotonic() - started, r.status_code))
                except Exception as err:
                    results.append((time.monotonic() - started, repr(err)))
                time.sleep(0.2)

    thread = threading.Thread(target=loop, daemon=True)
    thread.start()
    try:
        proc = subprocess.run(
            [bash, "scripts/rolling_restart.sh", *[a for f in _FILES for a in ("-f", f)], "-p", _PROJECT],
            cwd=str(REPO_ROOT), env={**env, "DRAIN_SECONDS": "3"}, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=900,
        )
    finally:
        stop.set()
        thread.join(timeout=60)
    print(f"\nrolling_restart rc={proc.returncode}\n{proc.stderr[-1500:]}")
    failures = [(round(t, 1), r) for t, r in results if r != 200]
    print(f"query loop: {len(results)} calls, {len(failures)} failures, over {time.monotonic() - started:.0f} s")
    assert proc.returncode == 0, f"rolling_restart exited {proc.returncode}:\n{proc.stderr[-2000:]}"
    assert len(results) >= 30, f"the loop made only {len(results)} calls; it died early"
    assert not failures, f"{len(failures)} of {len(results)} /query calls failed (offset s, outcome): {failures[:10]}"
    for svc in _INSTANCES:
        assert _instance_ready(env, svc) == 200, svc
