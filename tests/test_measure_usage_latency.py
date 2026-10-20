"""PRD-013 STORY-017: the parts of scripts/measure_usage_latency.py the numbers depend on.

The script is a spike that records numbers and asserts none, so nothing here
asserts a latency. What is tested: importing it touches no database, p95 is
nearest-rank, the local-only guard refuses a remote host, a short run against
the suite's dev server prints both calls' p50/p95 and the variant and leaves no
counter row behind, and the two ways a run can be wrong (a refused admit, a
changed statement count) end it with exit 1 instead of a report.
"""

import os
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
import scripts.measure_usage_latency as bench  # noqa: E402

if _saved_database_url is None:
    os.environ.pop("DATABASE_URL", None)
else:
    os.environ["DATABASE_URL"] = _saved_database_url

from app.db.database import get_connection  # noqa: E402
from app.services.usage_limits import Admission, UsageRefusal  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _bench_rows() -> int:
    with get_connection() as conn:
        return conn.execute(
            "SELECT COUNT(*) AS n FROM usage_daily WHERE user_id LIKE 'story017-bench%'"
        ).fetchone()["n"]


def test_importing_the_script_opens_no_connection():
    """In a fresh interpreter: in this one, other tests have built the client."""
    probe = (
        "import scripts.measure_usage_latency\n"
        "from app.db import database\n"
        "from app.services import pii_redactor\n"
        "assert database._client is None, database._client\n"
        "assert pii_redactor._analyzer is None, pii_redactor._analyzer\n"
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
    samples = bench.Samples("admit")
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
            "scripts/measure_usage_latency.py",
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


def test_a_short_run_reports_both_calls_and_cleans_up(capsys):
    assert bench.main(["--runs", "3"]) == 0

    out = capsys.readouterr().out
    assert "Path A" in out, out
    assert "admit SQL    : 1 statement (INSERT INTO usage_daily)" in out, out
    assert "charge SQL   : 1 statement (UPDATE usage_daily SET)" in out, out
    assert "p50 ms" in out and "p95 ms" in out, out
    for call in ("admit", "charge"):
        assert any(line.split()[:2] == [call, "3"] for line in out.splitlines()), out
    assert _bench_rows() == 0


def test_a_refused_admit_ends_the_run_without_a_report(monkeypatch, capsys):
    refusal = Admission(
        day="2026-10-20",
        refusal=UsageRefusal(
            limit="requests", maximum=1, actual=2, resets_at="2026-10-20T00:01:00Z"
        ),
    )
    monkeypatch.setattr(bench.usage_limits, "admit", lambda *_a, **_k: refusal)

    assert bench.main(["--runs", "3"]) == 1

    captured = capsys.readouterr()
    assert "refused the bench identity" in captured.err
    assert "p50 ms" not in captured.out


def test_a_changed_statement_count_ends_the_run_without_a_report(monkeypatch, capsys):
    monkeypatch.setattr(
        bench,
        "_statement_check",
        lambda identity: (["INSERT ...", "SELECT ..."], ["UPDATE ..."]),
    )

    assert bench.main(["--runs", "3"]) == 1

    captured = capsys.readouterr()
    assert "Expected one statement per call" in captured.err
    assert "p50 ms" not in captured.out
    assert _bench_rows() == 0


def test_zero_runs_is_refused(capsys):
    assert bench.main(["--runs", "0"]) == 1
    assert "--runs must be at least 1" in capsys.readouterr().err
