"""Startup-guard coverage for the chat UI entry point (STORY-016).

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
