"""Startup-guard coverage for the chat UI entry point.

Two guards live here now, both for the same structural reason:

  * PRD-005 STORY-016's RBAC bootstrap guard, registered as a lifespan task.
  * PRD-007 STORY-008's database reachability guard, which fires from init_db()
    at *import* time -- so for this ingress it is not a lifespan task at all,
    and the probe that exercises it must observe a failed import rather than a
    running app.

app/main.py's lifespan never runs under Reflex's api_transformer mount (see
chat_ui/chat_ui/chat_ui.py's comments) -- init_db(), pii_redactor.load(),
authz.load(), and now authz.check_bootstrap() are all duplicated there. This
runs in a subprocess with PYTHONPATH set to chat_ui/, exactly like
tests/test_chat_components_import.py, so importing chat_ui.chat_ui here
never puts the inner package on this process's sys.path.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.conftest import child_db_env  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
_PYTHONPATH = [str(REPO_ROOT / "chat_ui"), str(REPO_ROOT)]

_CHECK_SCRIPT = r"""
import json, sys

result = {"errors": []}
try:
    import chat_ui.chat_ui as chat_ui_module
except Exception as exc:
    print(json.dumps({"errors": ["import: {}: {}".format(type(exc).__name__, exc)]}))
    sys.exit(0)

tasks = chat_ui_module.app.get_lifespan_tasks()
result["guard_registered"] = chat_ui_module.authz.check_bootstrap in tasks

try:
    chat_ui_module.authz.check_bootstrap()
    result["raised"] = False
except chat_ui_module.authz.RbacNotBootstrappedError:
    result["raised"] = True

print(json.dumps(result))
"""


def _run_probe(env):
    proc = subprocess.run(
        [sys.executable, "-c", _CHECK_SCRIPT],
        cwd=str(REPO_ROOT / "chat_ui"),
        env=env,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        pytest.fail(f"chat_ui startup-guard probe crashed:\n{proc.stdout}\n{proc.stderr}")
    return json.loads(proc.stdout.strip().splitlines()[-1])


@pytest.fixture
def _empty_rbac_env(database_url_factory):
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(_PYTHONPATH)}
    # One variable: STORY-005 rejects `sqlite:///` in a child's own Settings(),
    # which briefly split the validating URL from the throwaway one. STORY-006
    # made the fixture hand out a real libSQL endpoint, so they are the same.
    env.update(child_db_env(database_url_factory("chat_ui_guard")))
    env["RBAC_ENABLED"] = "true"
    return env


def test_check_bootstrap_registered_as_chat_ui_lifespan_task(_empty_rbac_env):
    result = _run_probe(_empty_rbac_env)
    assert not result["errors"], result["errors"]
    assert result["guard_registered"] is True


def test_check_bootstrap_raises_against_empty_users_table(_empty_rbac_env):
    result = _run_probe(_empty_rbac_env)
    assert not result["errors"], result["errors"]
    assert result["raised"] is True


# --------------------------------------------------------------------------
# STORY-008 -- the database reachability guard, at the Reflex import boundary.
# --------------------------------------------------------------------------

#: A closed port on loopback: refused immediately, no DNS, no route to wait on.
#: It also passes STORY-005's validator -- `http://` is the local dev server's
#: scheme -- which is what makes this a test of *this* story's guard rather than
#: of the configuration check. The asserted exception name is the proof.
_UNREACHABLE_URL = "http://127.0.0.1:1"

_TOKEN_SENTINEL = "s3cret-turso-token-value"

# No try/except, deliberately: this probe exists to fail. The script above
# swallows an import error into JSON and exits 0, which is right for a guard
# that must be observed *after* a successful import and wrong for one that
# prevents the import from completing at all.
_UNREACHABLE_SCRIPT = r"""
import chat_ui.chat_ui  # noqa: F401 -- the import itself is the assertion
print("import completed, which the guard should have prevented")
"""


def _run_failing_probe(env) -> str:
    """Runs the import probe and returns stderr, insisting it did fail.

    Same subprocess construction as `_run_probe` -- same interpreter, same cwd,
    same PYTHONPATH -- inverted only in what counts as success.
    """
    proc = subprocess.run(
        [sys.executable, "-c", _UNREACHABLE_SCRIPT],
        cwd=str(REPO_ROOT / "chat_ui"),
        env=env,
        capture_output=True,
        text=True,
    )
    if proc.returncode == 0:
        pytest.fail(
            "importing chat_ui.chat_ui succeeded against an unreachable "
            f"database -- the startup guard did not fire:\n{proc.stdout}"
        )
    return proc.stderr


@pytest.fixture
def _unreachable_db_env():
    """The chat UI's environment, pointed at a database that cannot answer."""
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(_PYTHONPATH)}
    env.update(child_db_env(_UNREACHABLE_URL))
    env["TURSO_AUTH_TOKEN"] = _TOKEN_SENTINEL
    return env


def test_chat_ui_import_fails_when_the_database_is_unreachable(_unreachable_db_env):
    """AC1 and AC4 on the Reflex path: the failure is at import, not per-request.

    init_db() runs at chat_ui.chat_ui module scope, so there is no later moment
    at which this ingress could serve a request with a dead database behind it.
    """
    stderr = _run_failing_probe(_unreachable_db_env)

    assert "DatabaseUnreachableError" in stderr, stderr
    assert "DATABASE_URL" in stderr


def test_chat_ui_failure_names_the_endpoint_not_the_credential(_unreachable_db_env):
    """AC3 where it actually matters: an operator reads the whole traceback,
    not just the message, and a traceback prints every frame's exception text."""
    stderr = _run_failing_probe(_unreachable_db_env)

    assert "127.0.0.1:1" in stderr
    assert _TOKEN_SENTINEL not in stderr
