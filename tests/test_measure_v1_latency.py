"""PRD-015 STORY-019: the parts of scripts/measure_v1_latency.py the numbers depend on.

The script is a spike that records numbers and asserts none, so nothing here
asserts a latency. What is tested: importing it touches no database and starts
no stub, p95 is nearest-rank, the local-only guard refuses a remote host, a
miss against the 10 ms target is printed as a miss, a short run against the
suite's dev server reports all three arms through both ingresses and
deactivates its bench user, and a request that is not answered ends the run
with exit 1 instead of a report.
"""

import os
import socket
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import pytest

# The script's bootstrap writes DATABASE_URL into os.environ at import, as it
# must when run as a program. In the suite that would leak into every later
# subprocess's inherited environment, so the previous value is put back.
_saved_database_url = os.environ.get("DATABASE_URL")
import scripts.measure_v1_latency as bench  # noqa: E402

if _saved_database_url is None:
    os.environ.pop("DATABASE_URL", None)
else:
    os.environ["DATABASE_URL"] = _saved_database_url

from app.db.database import get_connection, get_user, list_audit_logs  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _bench_user_ids() -> list[str]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT user_id FROM users WHERE user_id LIKE 'story019-bench%'"
        ).fetchall()
    return [row["user_id"] for row in rows]


def _samples(label: str, *values: float) -> "bench.Samples":
    samples = bench.Samples(label)
    for value in values:
        samples.add(value)
    return samples


def _report(query: float, v1: float, translate: float) -> str:
    arms = {
        "query": _samples("query", query),
        "v1": _samples("v1", v1),
        "translate": _samples("translate", translate),
    }
    return bench._report(arms, 1, "http://127.0.0.1:8080", "http://127.0.0.1:1/v1", "gpt-4", "off")


def test_importing_the_script_opens_no_connection_and_starts_no_stub():
    """In a fresh interpreter: in this one, other tests have built the client."""
    probe = (
        "import threading\n"
        "import scripts.measure_v1_latency\n"
        "from app.db import database\n"
        "from app.services import pii_redactor\n"
        "assert database._client is None, database._client\n"
        "assert pii_redactor._analyzer is None, pii_redactor._analyzer\n"
        "assert threading.active_count() == 1, threading.enumerate()\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert completed.returncode == 0, completed.stderr


@pytest.mark.parametrize("n, expected_p95", [(20, 19), (50, 48), (1, 1)])
def test_p95_is_nearest_rank(n, expected_p95):
    samples = bench.Samples("v1")
    for value in range(n, 0, -1):  # unsorted on purpose
        samples.add(float(value))

    low, _, p95 = samples.summary()

    assert (low, p95) == (1.0, float(expected_p95))


@pytest.mark.parametrize("url", ["http://127.0.0.1:8080", "http://localhost:8080/"])
def test_the_guard_passes_a_local_endpoint(url):
    bench._guard_local(url, allow_remote=False)


def test_the_guard_refuses_a_remote_endpoint_unless_allowed():
    with pytest.raises(SystemExit, match="non-local"):
        bench._guard_local("libsql://prod.turso.io", allow_remote=False)

    bench._guard_local("libsql://prod.turso.io", allow_remote=True)


def test_run_as_a_program_a_remote_endpoint_is_refused_before_settings_load():
    """No token in the environment: Settings() would raise its own traceback
    first if the guard ran only after the `app.` imports."""
    env = {**os.environ, "TURSO_AUTH_TOKEN": "", "PYTHONPATH": str(_REPO_ROOT)}
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/measure_v1_latency.py",
            "--database-url",
            "https://example.turso.io",
        ],
        cwd=_REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert completed.returncode == 1, completed
    assert "Refusing to write to a non-local database" in completed.stderr
    assert "Traceback" not in completed.stderr, completed.stderr


def test_zero_runs_is_refused(capsys):
    assert bench.main(["--runs", "0"]) == 1
    assert "--runs must be at least 1" in capsys.readouterr().err


@pytest.mark.parametrize("translate_ms, verdict", [(9.99, "MET"), (10.0, "MISSED"), (250.0, "MISSED")])
def test_a_miss_against_the_target_is_printed_as_a_miss(translate_ms, verdict):
    out = _report(query=40.0, v1=41.0, translate=translate_ms)

    line = next(line for line in out.splitlines() if "PRD-015 target" in line)
    assert line.endswith(f"-> {verdict}"), line


@pytest.mark.parametrize("v1_ms, word", [(49.99, "within"), (50.0, "over")])
def test_the_end_to_end_line_says_within_or_over(v1_ms, word):
    out = _report(query=40.0, v1=v1_ms, translate=0.1)

    line = next(line for line in out.splitlines() if "end-to-end added p95 vs" in line)
    assert line.endswith(f"-> {word}"), line


def test_a_negative_difference_keeps_its_sign():
    out = _report(query=40.0, v1=37.5, translate=0.1)

    assert "added p95, end to end (v1 p95 - query p95) : -2.50 ms" in out, out


def test_the_report_is_ascii():
    """Piped output on Windows is cp1252 (README, Running Tests)."""
    _report(query=40.0, v1=41.0, translate=0.1).encode("ascii")


def test_a_short_run_reports_every_arm_and_deactivates_the_bench_user(capsys):
    assert bench.main(["--runs", "3"]) == 0

    out = capsys.readouterr().out
    for arm in bench.ARMS:
        assert any(line.split()[:2] == [arm, "3"] for line in out.splitlines()), out
    assert "PRD-015 target (Section 11)" in out, out
    assert "end-to-end added p95 vs 10 ms" in out, out

    (user_id,) = _bench_user_ids()
    assert f"deactivated bench user {user_id};" in out, out
    assert get_user(user_id).active is False
    rows = list_audit_logs(limit=100, user_id=user_id)
    # One warm-up and three timed requests on each ingress, every one answered.
    assert sorted((row.ingress, row.profile) for row in rows) == (
        [("query", "chat")] * 4 + [("v1", "code")] * 4
    )
    assert all(row.success and not row.streamed for row in rows)
    assert "it wrote 8 audit row(s)" in out, out


def test_a_blocked_request_ends_the_run_without_a_report(monkeypatch, capsys):
    """The same text every time: the second request is a duplicate."""
    monkeypatch.setattr(bench, "_prompt", lambda nonce, run, arm: f"the same text {nonce}")
    servers = []
    real_start = bench._start_stub

    def _recording_start():
        server, thread = real_start()
        servers.append(server)
        return server, thread

    monkeypatch.setattr(bench, "_start_stub", _recording_start)

    assert bench.main(["--runs", "3"]) == 1

    captured = capsys.readouterr()
    # /query's warm-up answers; /v1's warm-up, the same text, is the duplicate.
    assert "/v1/chat/completions was not answered: 400 duplicate_request" in captured.err, captured.err
    assert "p95 ms" not in captured.out
    # The stub was shut down on the way out.
    (server,) = servers
    with socket.socket() as sock:
        sock.settimeout(1)
        assert sock.connect_ex(("127.0.0.1", server.server_address[1])) != 0
