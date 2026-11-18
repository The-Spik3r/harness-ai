"""The image's HEALTHCHECK is a liveness probe of /health (PRD-019 STORY-003, F5, D3).

The probe must keep passing while the database is down (a readiness failure must
never restart-loop a container), so it targets `/health` and never `/ready`.
curl is purged from the image, so the probe is `python -c` with `urllib.request`.

These tests read the Dockerfile text. They also run the exact probe code against
a stub server on a free port, which proves the quoting works without building
the image (the spaCy layer makes a build slow).

No Docker and no storage: this runs under `-m "not db"`.
"""

import http.server
import json
import os
import pathlib
import re
import socket
import subprocess
import sys
import threading

import pytest

_DOCKERFILE = pathlib.Path(__file__).resolve().parents[1] / "Dockerfile"


def _logical_lines() -> list:
    """Dockerfile instructions: continuations joined, comment lines dropped."""
    out, buf = [], ""
    for raw in _DOCKERFILE.read_text(encoding="utf-8").splitlines():
        if not buf and (not raw.strip() or raw.lstrip().startswith("#")):
            continue
        if raw.lstrip().startswith("#"):
            continue  # a comment inside a continued instruction
        if raw.rstrip().endswith("\\"):
            buf += raw.rstrip()[:-1] + " "
            continue
        out.append((buf + raw).strip())
        buf = ""
    return out


def _healthchecks() -> list:
    return [l for l in _logical_lines() if l.split(None, 1)[0].upper() == "HEALTHCHECK"]


def _healthcheck() -> str:
    found = _healthchecks()
    assert len(found) == 1, f"Dockerfile: expected exactly one HEALTHCHECK, found {len(found)}"
    return found[0]


def _argv() -> list:
    text = _healthcheck()
    assert " CMD " in text, "Dockerfile: HEALTHCHECK must have a CMD"
    exec_part = text.split(" CMD ", 1)[1].strip()
    assert exec_part.startswith("["), "Dockerfile: HEALTHCHECK CMD must be exec form (JSON array)"
    return json.loads(exec_part)


def _code() -> str:
    return _argv()[2]


def test_single_healthcheck_in_final_stage():
    lines = _logical_lines()
    froms = [i for i, l in enumerate(lines) if l.split(None, 1)[0].upper() == "FROM"]
    hc = [i for i, l in enumerate(lines) if l.split(None, 1)[0].upper() == "HEALTHCHECK"]
    assert len(hc) == 1, f"Dockerfile: expected exactly one HEALTHCHECK, found {len(hc)}"
    assert hc[0] > froms[-1], "Dockerfile: HEALTHCHECK must be in the final (runtime) stage"


def test_flags_are_exactly_interval_timeout_start_period():
    head = _healthcheck().split(" CMD ", 1)[0]
    flags = re.findall(r"--[\w-]+=\S+", head)
    assert sorted(flags) == ["--interval=10s", "--start-period=60s", "--timeout=3s"], (
        f"Dockerfile: HEALTHCHECK flags must be interval/timeout/start-period only, got {flags}"
    )


def test_exec_form_python_dash_c():
    argv = _argv()
    assert len(argv) == 3 and argv[:2] == ["python", "-c"], (
        f"Dockerfile: HEALTHCHECK must be CMD [\"python\", \"-c\", <code>], got {argv}"
    )


def test_probe_code_targets_health_with_urllib_and_2s_timeout():
    code = _code()
    for needle in ("urllib.request", "127.0.0.1", "timeout=2", "PORT"):
        assert needle in code, f"Dockerfile: HEALTHCHECK code must contain {needle!r}"
    assert re.search(r"/health(?!\w)", code), "Dockerfile: HEALTHCHECK must probe /health exactly"
    assert "/ready" not in code and "curl" not in code


def test_instruction_never_mentions_ready_or_curl():
    text = _healthcheck()
    assert "curl" not in text, "Dockerfile: HEALTHCHECK must not use curl (purged from the image)"
    assert "/ready" not in text, "Dockerfile: HEALTHCHECK is liveness; it must never call /ready (PRD-019 D3)"


def test_probe_code_compiles():
    compile(_code(), "<healthcheck>", "exec")


# --- the exact probe code against a stub, no Docker -------------------------

def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _run_probe(port: int) -> int:
    env = {**os.environ, "PORT": str(port)}
    return subprocess.run(
        [sys.executable, "-c", _code()], env=env, timeout=15,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    ).returncode


@pytest.fixture
def stub_server():
    """Serve GET /health (200) and anything else (503) on a free port."""
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            ok = self.path == "/health"
            self.send_response(200 if ok else 503)
            self.end_headers()
            self.wfile.write(b"ok" if ok else b"no")

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_probe_exits_zero_on_200_health(stub_server):
    assert _run_probe(stub_server) == 0


def test_probe_exits_nonzero_when_nothing_listens():
    assert _run_probe(_free_port()) != 0
