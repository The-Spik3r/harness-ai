"""PRD-015 STORY-015: the `e2e` marker is opt-in, like `benchmark`.

The live-client E2E tests start a harness and a stub as subprocesses, so the
everyday run must never start them. These run in a `pytester` child that loads
a copy of the real `tests/conftest.py`, the same way
`tests/test_db_isolation_harness.py` checks the `db` marker. The child test
bodies reach no storage, so the endpoint is a dead port and Docker is not needed.
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

from pathlib import Path

import pytest

pytest_plugins = ("pytester",)

_REPO_ROOT = Path(__file__).resolve().parents[1]

_CHILD = """
import pytest

@pytest.mark.e2e
def test_live():
    pass

@pytest.mark.benchmark
def test_timed():
    pass

def test_plain():
    pass
"""


def _run(pytester, monkeypatch, *args):
    monkeypatch.setenv("PYTHONPATH", str(_REPO_ROOT))
    monkeypatch.setenv("HARNESS_TEST_LIBSQL_URL", "http://127.0.0.1:9")
    pytester.makeconftest((_REPO_ROOT / "tests" / "conftest.py").read_text(encoding="utf-8"))
    pytester.makepyfile(test_child=_CHILD)
    return pytester.runpytest_subprocess("-p", "no:cacheprovider", "-rs", *args)


def test_e2e_tests_are_skipped_by_default(pytester, monkeypatch):
    result = _run(pytester, monkeypatch)
    result.assert_outcomes(passed=1, skipped=2)
    result.stdout.fnmatch_lines(["*e2e: pass --run-e2e*"])


def test_run_e2e_runs_them_and_leaves_benchmark_skipped(pytester, monkeypatch):
    result = _run(pytester, monkeypatch, "--run-e2e")
    result.assert_outcomes(passed=2, skipped=1)
    result.stdout.fnmatch_lines(["*benchmark: pass --run-benchmark*"])


def test_run_benchmark_does_not_unskip_e2e(pytester, monkeypatch):
    result = _run(pytester, monkeypatch, "--run-benchmark")
    result.assert_outcomes(passed=2, skipped=1)
    result.stdout.fnmatch_lines(["*e2e: pass --run-e2e*"])


def test_the_marker_is_registered(pytester, monkeypatch):
    monkeypatch.setenv("PYTHONPATH", str(_REPO_ROOT))
    monkeypatch.setenv("HARNESS_TEST_LIBSQL_URL", "http://127.0.0.1:9")
    pytester.makeconftest((_REPO_ROOT / "tests" / "conftest.py").read_text(encoding="utf-8"))
    result = pytester.runpytest_subprocess("-p", "no:cacheprovider", "--markers")
    result.stdout.fnmatch_lines(["@pytest.mark.e2e: live client E2E*--run-e2e"])
