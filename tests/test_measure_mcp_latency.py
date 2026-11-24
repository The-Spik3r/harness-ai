"""PRD-023 STORY-019: the parts of scripts/measure_mcp_latency.py the numbers depend on.

The script is a spike that records numbers and asserts none, so nothing here
asserts a latency. What is tested: importing it has no side effect (no stub, no
client, the placeholder database), p95 is nearest-rank, a miss against the
target is printed as MISSED, the report is ASCII, and a short run in a
subprocess (the suite's `conftest` refuses storage in a non-`db` test, and the
script runs on its own embedded libSQL file, so it needs no Docker) reports both
arms with the deterministic database round trips: three units for the allowed
call, at most three for the denied one. The stub's port is closed afterwards.
"""

import os
import re
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
import scripts.measure_mcp_latency as bench  # noqa: E402

if _saved_database_url is None:
    os.environ.pop("DATABASE_URL", None)
else:
    os.environ["DATABASE_URL"] = _saved_database_url

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _samples(label: str, *values: float) -> "bench.Samples":
    samples = bench.Samples(label)
    for value in values:
        samples.add(value)
    return samples


def _counted(opens: int, units=()):
    counted = bench.Counted()
    counted.opens = opens
    counted.units = list(units)
    counted.statements = ["INSERT INTO t VALUES (?)"] * opens
    return counted


def _report(denied_ms: float, allowed_ms: float, *, opens=(2, 3), target=25.0) -> str:
    samples = {
        ("denied", "M0-M9"): _samples("d", denied_ms),
        ("denied", "M3-M9"): _samples("d", denied_ms),
        ("allowed", "M0-M9"): _samples("a", allowed_ms),
        ("allowed", "M3-M9"): _samples("a", allowed_ms),
    }
    counted = {"denied": _counted(opens[0]), "allowed": _counted(opens[1])}
    return bench._report(samples, counted, 1, target, 4242)


def test_importing_the_script_has_no_side_effect():
    """A fresh interpreter: no stub started, no client opened, the placeholder URL untouched."""
    code = (
        "import scripts.measure_mcp_latency as b\n"
        "from app.config import settings\n"
        "from app.db import database\n"
        "print(database._client is None, settings.DATABASE_URL)\n"
    )
    env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
    completed = subprocess.run(
        [sys.executable, "-c", code], cwd=str(_REPO_ROOT), env={**env, "PYTHONUTF8": "1"},
        capture_output=True, text=True, timeout=120,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.split() == ["True", "http://127.0.0.1:8080"], completed.stdout


def test_p95_is_nearest_rank():
    samples = _samples("x", *[float(n) for n in range(1, 21)])
    low, p50, p95 = samples.summary()
    assert (low, p50, p95) == (1.0, 10.5, 19.0)  # sorted[ceil(0.95 * 20) - 1]
    assert _samples("one", 7.0).summary() == (7.0, 7.0, 7.0)


@pytest.mark.parametrize("allowed_ms, verdict", [(24.99, "MET"), (25.0, "MET"), (25.01, "MISSED"), (250.0, "MISSED")])
def test_a_miss_against_the_target_is_printed_as_a_miss(allowed_ms, verdict):
    line = next(line for line in _report(3.0, allowed_ms).splitlines() if "PRD-023 target" in line)
    assert line.endswith(f"-> {verdict}"), line


def test_the_worst_arm_decides_the_verdict():
    line = next(line for line in _report(60.0, 3.0).splitlines() if "PRD-023 target" in line)
    assert line.endswith("-> MISSED"), line


@pytest.mark.parametrize("opens, word", [((2, 3), "MET"), ((2, 4), "EXCEEDED")])
def test_the_round_trip_line_says_met_or_exceeded(opens, word):
    line = next(line for line in _report(3.0, 3.0, opens=opens).splitlines() if line.strip().startswith("units per call"))
    assert line.endswith(f"-> {word}"), line


def test_the_report_is_ascii():
    """Piped output on Windows is cp1252 (README, Running Tests)."""
    _report(3.0, 4.0).encode("ascii")


def test_zero_runs_is_refused(capsys):
    assert bench.main(["--runs", "0"]) == 1
    assert "--runs must be at least 1" in capsys.readouterr().err


def _port_closed(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(1)
        return probe.connect_ex(("127.0.0.1", port)) != 0


def test_a_short_run_reports_both_arms_and_at_most_three_units():
    completed = subprocess.run(
        [sys.executable, str(_REPO_ROOT / "scripts" / "measure_mcp_latency.py"), "--runs", "3"],
        cwd=str(_REPO_ROOT), env={**os.environ, "PYTHONUTF8": "1"},
        capture_output=True, text=True, timeout=300,
    )
    assert completed.returncode == 0, completed.stderr
    out = completed.stdout
    out.encode("ascii")
    for arm in bench.ARMS:
        for figure in bench.FIGURES:
            assert any(line.split()[:3] == [arm, figure, "3"] for line in out.splitlines()), out
    units = next(line for line in out.splitlines() if line.strip().startswith("units per call"))
    assert re.search(r"denied (\d) \(", units) and int(re.search(r"denied (\d) \(", units).group(1)) <= 3, units
    assert "allowed 3 (admit_usage+insert_mcp_decision_linked+update_action_outcome)" in units, units
    assert units.endswith("-> MET"), units
    assert "p95 ms (M0-M9, upstream excluded)" in out and "p95 ms (M3-M9, upstream excluded)" in out
    assert "PRD-023 target (Section 11): p95 <= 25 ms" in out
    port = int(re.search(r"stub MCP server on 127\.0\.0\.1:(\d+)", out).group(1))
    assert _port_closed(port), f"the stub still holds port {port}"
