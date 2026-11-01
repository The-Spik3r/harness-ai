"""PRD-015 STORY-018: the Docker deployment serves /v1 through Caddy.

The real image runs under its own compose project (`harness-smoke`), laid over
the unchanged docker-compose.yml by tests/e2e/docker/compose.smoke.yml: a
throwaway libSQL service, and the stub upstream inside the harness container's
network namespace, so `OPENROUTER_BASE_URL=http://127.0.0.1:9100/v1` stays a
loopback URL. tests/e2e/docker_smoke_probe.py runs inside the container and
prints JSON; the tests below assert on it. Timing is taken in-network because
Docker Desktop's port forwarding is known to stall (PRD-014 STORY-006). One
test also goes through the published port from the host.

    AC 1  tests/test_caddyfile_routes.py (no Docker)
    AC 2  test_v1_through_caddy_matches_the_backend: non-streaming and
          streaming through Caddy equal the same through the backend port
    AC 3  test_keepalives_arrive_through_caddy_with_gzip_on: 30 s stub delay,
          V1_SSE_KEEPALIVE_SECONDS=10, Accept-Encoding: gzip; each keep-alive
          within 2 s of its interval
    AC 4  test_reflex_routes_and_query_still_answer,
          test_v1_models_returns_the_allowlist
          test_published_port_answers_from_the_host: the front door from outside
          test_executor_concurrency_measurement: PRD Risk 6 (2 x workers
          streamed requests split into two waves)

The probe's JSON is written to `smoke.json` in the module's temp directory
(path printed with `-s`) for the story report. Tokens are never printed.

Run (skipped without `--run-e2e`, and without HARNESS_E2E_DOCKER=1, because it
builds the image and needs Docker; port 8095 must be free):

    HARNESS_E2E_DOCKER=1 python -m pytest tests/e2e/test_docker_smoke.py -m e2e --run-e2e -v -s

`HARNESS_SMOKE_WORKERS` (default 4) sets the stack's PIPELINE_MAX_WORKERS for
the concurrency measurement. The stack is removed with `down -v` afterwards.
"""

import json
import os
import secrets
import subprocess
import time

import httpx
import pytest

from tests.e2e import _live
from tests.e2e.docker_smoke_probe import keepalive_problems, split_waves

pytestmark = pytest.mark.e2e

REPO_ROOT = _live.REPO_ROOT
_PROJECT = "harness-smoke"
_PORT = "8095"
_BACKEND_PORT = "8001"  # Dockerfile: ENV BACKEND_INTERNAL_PORT=8001
_WORKERS = int(os.environ.get("HARNESS_SMOKE_WORKERS", "4"))
_ALLOWLIST = ["openai/gpt-4o", "anthropic/claude-3.5-sonnet"]  # compose.smoke.yml MODEL_ALLOWLIST
_KEEPALIVE_SECONDS = 10.0  # compose.smoke.yml V1_SSE_KEEPALIVE_SECONDS
_TOLERANCE = 2.0
_WAVE_DELAY = 5.0  # docker_smoke.json, the SMOKE-WAVE rule
_COMPOSE = [
    "docker", "compose", "-p", _PROJECT,
    "-f", "docker-compose.yml", "-f", "tests/e2e/docker/compose.smoke.yml",
]
# docker_smoke.json's answers, restated.
_DEFAULT_ANSWER = "harness smoke answer: the front door is open"
_QUERY_ANSWER = "harness smoke query answer: query still works"
_SLOW_ANSWER = "harness smoke slow answer: keep-alives came through"

NONCE = secrets.token_hex(4)


def _compose(env: dict, *args: str, timeout: float = 600, check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        [*_COMPOSE, *args], cwd=str(REPO_ROOT), env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=timeout,
    )
    if check and proc.returncode != 0:
        pytest.fail(f"docker compose {' '.join(args[:3])} exited {proc.returncode}:\n{proc.stderr[-3000:]}")
    return proc


def _in_container_status(env: dict, url: str) -> int:
    script = f"import httpx\ntry:\n    print(httpx.get({url!r}, timeout=3).status_code)\nexcept Exception:\n    print(0)\n"
    proc = _compose(env, "exec", "-T", "harness-ai", "python", "-c", script, timeout=60, check=False)
    lines = proc.stdout.strip().splitlines()
    return int(lines[-1]) if proc.returncode == 0 and lines and lines[-1].isdigit() else 0


@pytest.fixture(scope="module")
def compose_env():
    if os.environ.get("HARNESS_E2E_DOCKER", "").strip() != "1":
        pytest.skip("Docker smoke: set HARNESS_E2E_DOCKER=1 (it builds the image and needs Docker)")
    if subprocess.run(["docker", "info"], capture_output=True).returncode != 0:
        pytest.fail("HARNESS_E2E_DOCKER=1 but `docker info` fails: start Docker Desktop first")
    return {
        **os.environ,
        "MSYS_NO_PATHCONV": "1",
        "PORT": _PORT,
        "HARNESS_SMOKE_ADMIN_TOKEN": secrets.token_urlsafe(16),
        "HARNESS_SMOKE_WORKERS": str(_WORKERS),
    }


@pytest.fixture(scope="module")
def stack(compose_env, tmp_path_factory):
    """The running stack's user token. Torn down with `down -v` whatever happens."""
    workdir = tmp_path_factory.mktemp("docker_smoke")
    env = compose_env
    _compose(env, "down", "-v", "--remove-orphans", timeout=180, check=False)  # a previous run's leftovers
    try:
        _compose(env, "build", "harness-ai", timeout=1800)
        _compose(env, "up", "-d", "libsql", timeout=180)

        def run(*args: str) -> subprocess.CompletedProcess:
            # _live.create_user passes the host path of manage_users.py; the
            # container sees the repository at /app, its working directory.
            args = tuple(os.path.relpath(a, REPO_ROOT).replace("\\", "/") if a.startswith(str(REPO_ROOT)) else a
                         for a in args)
            return _compose(env, "run", "--rm", "--no-deps", "-T", "harness-ai", "python", *args,
                            timeout=300, check=False)

        # The users table must have a row before the harness starts (RBAC
        # bootstrap), and libSQL may still be starting: retry for 30 s.
        deadline = time.monotonic() + 30
        while True:
            try:
                token = _live.create_user(run, f"smoke-{NONCE}")
                break
            except AssertionError:
                if time.monotonic() > deadline:
                    raise
                time.sleep(2)

        _compose(env, "up", "-d", "harness-ai", "stub", timeout=300)
        deadline = time.monotonic() + 240  # Presidio and spaCy load at startup
        while _in_container_status(env, f"http://127.0.0.1:{_PORT}/health") != 200:
            if time.monotonic() > deadline:
                pytest.fail("the stack did not answer /health through Caddy within 240 s")
            time.sleep(3)
        while _in_container_status(env, "http://127.0.0.1:9100/health") != 200:
            if time.monotonic() > deadline:
                pytest.fail("the stub did not answer /health within 240 s")
            time.sleep(1)
        yield token
    finally:
        logs = _compose(env, "logs", "--no-color", "--tail", "300", timeout=120, check=False)
        log_path = workdir / "compose.log"
        log_path.write_text(logs.stdout + logs.stderr, encoding="utf-8")
        print(f"\ncompose logs: {log_path}")
        _compose(env, "down", "-v", "--remove-orphans", timeout=300, check=False)


@pytest.fixture(scope="module")
def probe(stack, compose_env, tmp_path_factory):
    env = {**compose_env, "SMOKE_TOKEN": stack}
    proc = _compose(
        env, "exec", "-T", "-e", "SMOKE_TOKEN", "harness-ai",
        "python", "-m", "tests.e2e.docker_smoke_probe",
        "--direct", f"http://127.0.0.1:{_BACKEND_PORT}", "--caddy", f"http://127.0.0.1:{_PORT}",
        "--nonce", NONCE, "--workers", str(_WORKERS), "--identity",
        timeout=300, check=False,
    )
    assert proc.returncode == 0, f"probe exited {proc.returncode}:\n{proc.stderr[-3000:]}"
    result = json.loads(proc.stdout.strip().splitlines()[-1])
    path = tmp_path_factory.mktemp("docker_smoke_probe") / "smoke.json"
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"\nprobe result: {path}")
    return result


def _section(probe: dict, name: str) -> dict:
    section = probe[name]
    assert "error" not in section, section.get("error")
    return section


def test_v1_through_caddy_matches_the_backend(probe):
    compare = _section(probe, "compare")
    direct, caddy = compare["direct"], compare["caddy"]

    assert direct["completion"]["status"] == 200, direct["completion"]
    assert direct["completion"]["content"] == _DEFAULT_ANSWER
    assert direct["completion"]["id_ok"]
    assert caddy["completion"] == direct["completion"]

    assert direct["stream"]["status"] == 200, direct["stream"]
    assert direct["stream"]["content_type"].startswith("text/event-stream")
    assert caddy["stream"]["content_type"].startswith("text/event-stream")
    assert caddy["stream"]["events"] == direct["stream"]["events"]
    events = direct["stream"]["events"]
    assert events[-1] == "[DONE]"
    assert events[0]["choices"][0]["delta"]["content"] == _DEFAULT_ANSWER
    assert all(event["id_ok"] for event in events[:-1])
    assert events[-2]["usage"]["total_tokens"] == 15  # include_usage chunk


def test_keepalives_arrive_through_caddy_with_gzip_on(probe):
    timings = _section(probe, "keepalive")
    caddy = timings["caddy_gzip"]
    shown = json.dumps({label: {k: v for k, v in t.items() if k != "error"} for label, t in timings.items()})
    # The interval is 10 s and the stub waits 30 s: keep-alives at 10 and 20
    # s; the one at 30 s races the answer, so two are required.
    problems = keepalive_problems(caddy, _KEEPALIVE_SECONDS, _TOLERANCE, minimum=2)
    assert not problems, f"through Caddy: {problems}; all timings: {shown}"
    assert not keepalive_problems(timings["direct_gzip"], _KEEPALIVE_SECONDS, _TOLERANCE, minimum=2), shown
    assert caddy["content_type"].startswith("text/event-stream"), shown


def test_reflex_routes_and_query_still_answer(probe):
    routes = _section(probe, "routes")
    assert routes["/"]["status"] == 200 and routes["/"]["content_type"].startswith("text/html"), routes["/"]
    # The console page is a directory in the static export: file_server sends
    # the browser to its trailing-slash form, which serves the page.
    console = routes["/admin/audit"]
    assert console["status"] in (200, 308), console
    assert console["final_status"] == 200 and console["content_type"].startswith("text/html"), console
    assert console["final_path"] in ("/admin/audit", "/admin/audit/"), console
    assert routes["/ping"]["status"] == 200, routes["/ping"]
    assert routes["/health"] == {"status": 200, "body": '{"status":"ok"}'}
    assert routes["/query"] == {"status": 200, "response": _QUERY_ANSWER}


def test_v1_models_returns_the_allowlist(probe):
    models = _section(probe, "routes")["/v1/models"]
    assert models == {"status": 200, "ids": _ALLOWLIST}


def test_published_port_answers_from_the_host(stack):
    base = f"http://127.0.0.1:{_PORT}"
    headers = {"Authorization": f"Bearer {stack}"}
    models = httpx.get(f"{base}/v1/models", headers=headers, timeout=30)
    assert models.status_code == 200
    assert [item["id"] for item in models.json()["data"]] == _ALLOWLIST
    body = {
        "model": _ALLOWLIST[0],
        "messages": [{"role": "user", "content": f"host side streamed {NONCE}"}],
        "stream": True,
    }
    streamed = httpx.post(f"{base}/v1/chat/completions", headers=headers, json=body, timeout=60)
    assert streamed.status_code == 200
    assert streamed.headers["content-type"].startswith("text/event-stream")
    assert _DEFAULT_ANSWER in streamed.text and streamed.text.rstrip().endswith("data: [DONE]")


def test_executor_concurrency_measurement(probe):
    run = _section(probe, "concurrency")
    requests = run["requests"]
    failed = [entry for entry in requests if not entry or "error" in entry or entry["status"] != 200 or not entry["done"]]
    assert not failed, failed
    at_once, queued = split_waves(requests, _WAVE_DELAY)
    print(
        f"\nconcurrency: workers={run['workers']} count={run['count']} wall={run['wall']}s "
        f"at_once={at_once} queued={queued} totals={sorted(e['total'] for e in requests)}"
    )
    # PIPELINE_MAX_WORKERS requests commit at once; the rest wait for a worker.
    assert len(at_once) == run["workers"], (at_once, queued)
    assert len(queued) == run["count"] - run["workers"], (at_once, queued)
