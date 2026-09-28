"""Startup-guard coverage for the chat UI entry point.

Four lifespan concerns live here now:

  * PRD-005 STORY-016's RBAC bootstrap guard, registered as a lifespan task.
  * PRD-007 STORY-008's database reachability guard, which fires from init_db()
    at *import* time -- so for this ingress it is not a lifespan task at all,
    and the probe that exercises it must observe a failed import rather than a
    running app.
  * PRD-010 STORY-006's pipeline-executor shutdown, registered as an
    `@asynccontextmanager` lifespan task -- the same registration mechanism as
    the RBAC guard, checked the same way.
  * PRD-011 STORY-007's `pattern_config.load()`, registered as a lifespan task
    beside `authz.load`. A malformed PATTERNS_FILE must stop this ingress too,
    since it is the one production actually runs.

app/main.py's lifespan never runs under Reflex's api_transformer mount (see
chat_ui/chat_ui/chat_ui.py's comments) -- init_db(), pii_redactor.load(),
authz.load(), pattern_config.load(), authz.check_bootstrap(), and the
pipeline executor's shutdown are all duplicated there. This runs in a subprocess with PYTHONPATH
set to chat_ui/, exactly like tests/test_chat_components_import.py, so
importing chat_ui.chat_ui here never puts the inner package on this process's
sys.path.
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
result["pipeline_shutdown_registered"] = (
    chat_ui_module._pipeline_executor_lifespan in tasks
)

# PRD-011 STORY-007. The class name, not `except PatternConfigError`: a wrong
# exception type then fails an assertion instead of crashing the probe.
load = chat_ui_module.pattern_config.load
result["patterns_load_registered"] = load in tasks
result["patterns_load_adjacent"] = (
    load in tasks
    and chat_ui_module.authz.load in tasks
    and tasks.index(load) == tasks.index(chat_ui_module.authz.load) + 1
)
try:
    load()
    result["patterns_raised"] = None
except Exception as exc:
    result["patterns_raised"] = type(exc).__name__
    result["patterns_message"] = str(exc)

# PRD-012 STORY-007. Runs after pattern_config.load because it reads the
# loaded pattern profiles; Reflex runs tasks in registration order.
pii_load = chat_ui_module.pii_policy.load
result["pii_policy_load_registered"] = pii_load in tasks
result["pii_policy_load_after_patterns"] = (
    pii_load in tasks
    and load in tasks
    and tasks.index(pii_load) == tasks.index(load) + 1
)
try:
    pii_load()
    result["pii_policy_raised"] = None
except Exception as exc:
    result["pii_policy_raised"] = type(exc).__name__
# Force the one inconsistent combination load() checks. This child process
# exits right after, so the replaced builder leaks nowhere.
import dataclasses
_pii_policy = chat_ui_module.pii_policy
_real_code = _pii_policy._build_code_policy()
_pii_policy._build_code_policy = lambda: dataclasses.replace(
    _real_code, skip_fenced_blocks=True, structure_safe=False
)
try:
    pii_load()
    result["pii_policy_forced_raised"] = None
except Exception as exc:
    result["pii_policy_forced_raised"] = type(exc).__name__

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
    # PRD-011 STORY-007: the "no patterns file" case, stated rather than
    # inherited -- the child builds its own Settings(), and a developer's shell
    # must not turn it into a file.
    env["PATTERNS_FILE"] = ""
    env["PATTERN_PROFILE_DEFAULT"] = "chat"
    return env


def test_check_bootstrap_registered_as_chat_ui_lifespan_task(_empty_rbac_env):
    result = _run_probe(_empty_rbac_env)
    assert not result["errors"], result["errors"]
    assert result["guard_registered"] is True


def test_check_bootstrap_raises_against_empty_users_table(_empty_rbac_env):
    result = _run_probe(_empty_rbac_env)
    assert not result["errors"], result["errors"]
    assert result["raised"] is True


def test_pipeline_executor_shutdown_registered_as_chat_ui_lifespan_task(_empty_rbac_env):
    result = _run_probe(_empty_rbac_env)
    assert not result["errors"], result["errors"]
    assert result["pipeline_shutdown_registered"] is True


# --------------------------------------------------------------------------
# PRD-011 STORY-007 -- pattern_config.load() as a chat UI lifespan task.
# --------------------------------------------------------------------------

#: PRD-011 User Story 2's typo, `mach` for `match`. Well-formed YAML, so the
#: failure is load()'s validation, not a parse error. Same text as
#: tests/test_main.py's, so both entry points are refused on the same file.
_MALFORMED_PATTERNS = """
lists:
  injection:
    mach: word
    scope: everywhere
    patterns:
      - ignore previous instructions
profiles:
  chat:
    lists: [injection]
    roles:
      user: block
"""


@pytest.fixture
def _malformed_patterns_env(_empty_rbac_env, tmp_path):
    """The chat UI's environment, pointed at a malformed patterns file.

    Through the environment, not monkeypatch: the probe is a subprocess that
    constructs its own Settings()."""
    patterns_file = tmp_path / "patterns.yaml"
    patterns_file.write_text(_MALFORMED_PATTERNS, encoding="utf-8")
    return {**_empty_rbac_env, "PATTERNS_FILE": str(patterns_file)}


def test_pattern_config_load_registered_as_chat_ui_lifespan_task(_empty_rbac_env):
    """AC 2: registered on the mount app.main's lifespan never reaches, and
    directly after authz.load -- Reflex runs tasks in registration order, so
    this also places it before check_bootstrap's database read."""
    result = _run_probe(_empty_rbac_env)
    assert not result["errors"], result["errors"]
    assert result["patterns_load_registered"] is True
    assert result["patterns_load_adjacent"] is True


def test_pattern_config_load_is_a_noop_when_patterns_file_unset(_empty_rbac_env):
    """AC 5 on the Reflex path: no PATTERNS_FILE, nothing raised."""
    result = _run_probe(_empty_rbac_env)
    assert not result["errors"], result["errors"]
    assert result["patterns_raised"] is None


def test_pattern_config_load_fails_chat_ui_startup_on_malformed_file(_malformed_patterns_env):
    """AC 4 on the Reflex path. The import succeeds -- the failure is the
    lifespan task, so the process refuses to start rather than to import.

    The probe calls load() by hand, so a raise alone would pass even with the
    registration deleted; asserting registration too is what makes this a
    claim about startup rather than about load()."""
    result = _run_probe(_malformed_patterns_env)
    assert not result["errors"], result["errors"]
    assert result["patterns_load_registered"] is True
    assert result["patterns_raised"] == "PatternConfigError"
    assert "injection" in result["patterns_message"]
    assert "mach" in result["patterns_message"]


# --------------------------------------------------------------------------
# PRD-012 STORY-007 -- pii_policy.load() in the Reflex lifespan.
# --------------------------------------------------------------------------


def test_pii_policy_load_registered_after_pattern_config_load(_empty_rbac_env):
    """AC 5, Reflex path: registered on the mount app.main's lifespan never
    reaches, directly after pattern_config.load, whose profiles it reads."""
    result = _run_probe(_empty_rbac_env)
    assert not result["errors"], result["errors"]
    assert result["pii_policy_load_registered"] is True
    assert result["pii_policy_load_after_patterns"] is True


def test_pii_policy_load_is_a_noop_by_default(_empty_rbac_env):
    """Built-in policies and default settings: nothing raised."""
    result = _run_probe(_empty_rbac_env)
    assert not result["errors"], result["errors"]
    assert result["pii_policy_raised"] is None


def test_pii_policy_config_error_fails_chat_ui_startup(_empty_rbac_env):
    """AC 5, Reflex path: a PiiConfigError stops the boot. The probe calls
    load() by hand, so a raise alone would pass even with the registration
    deleted; asserting registration too is what makes this a claim about
    startup rather than about load()."""
    result = _run_probe(_empty_rbac_env)
    assert not result["errors"], result["errors"]
    assert result["pii_policy_load_registered"] is True
    assert result["pii_policy_forced_raised"] == "PiiConfigError"


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
