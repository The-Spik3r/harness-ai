"""PRD-016 STORY-013: the secret classifier and the secret reads a shell command carries (Sections 6.3 secret row, 6.6, F4, F6; D15; T10; T11).

Table-driven. The paths, variable names and commands are transcribed from
the story's acceptance criteria and PRD F4/F6/D15, and written out as
literals, not derived from the module. They are seeds for STORY-018's
secret-exfiltration group.

Real globs: `BUILT_IN_POLICY.secrets` (importing `action_config` here is
fine; only the module under test must stay pure). `_shell(cmd)` is the
STORY-014 call shape (`classify_shell` with every policy argument); the
tool-side cases go through `map_tool_call` with `BUILT_IN_TOOLS`, then the
classifier, so the adapter's D15 `optional_targets` are covered end to end.

Not covered here: how `evaluate()` folds `secret.read` (STORY-014). The
shell embedding's SQL/URL/redirect cases are in `tests/test_action_shell.py`.
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import inspect
import json
import subprocess
import sys
from pathlib import Path

import pytest

import app.services.action_classifiers.secrets as secrets
from app.config import settings
from app.services.action_adapters import BUILT_IN_TOOLS, Operations, ToolCall, Unknown, map_tool_call
from app.services.action_classifiers import Classification, Operation
from app.services.action_classifiers.paths import classify_read
from app.services.action_classifiers.secrets import (
    INDIRECT,
    classify_env_reference,
    classify_secret_read,
    env_references,
)
from app.services.action_classifiers.shell import classify_shell
from app.services.action_config import BUILT_IN_POLICY, get_policy, load

_REPO_ROOT = Path(__file__).resolve().parents[1]

SECRET_FILES = BUILT_IN_POLICY.secrets.files.compiled
SECRET_ENV = BUILT_IN_POLICY.secrets.env.compiled
OP = Operation("shell", "x", "bash")


def _shell(cmd, policy=BUILT_IN_POLICY):
    return classify_shell(
        cmd,
        policy.shell_allow,
        network_allow=policy.network_allow,
        secret_env=policy.secrets.env.compiled,
        secret_files=policy.secrets.files.compiled,
        protected=policy.protected_paths.compiled,
        workspace_roots=policy.workspace_roots,
        source_tool="bash",
    )


def _rules(cmd, policy=BUILT_IN_POLICY):
    return [c.rule for c in _shell(cmd, policy)]


def _tool_reads(name, arguments):
    """Map a tool call through the built-in tools, then classify each fs_read (the STORY-014 path)."""
    result = map_tool_call(ToolCall(id="c1", name=name, arguments=json.dumps(arguments)), BUILT_IN_TOOLS, {}, 100_000)
    assert isinstance(result, Operations), result
    return [classify_read(op.target, SECRET_FILES, source_tool=op.source_tool) for op in result.operations]


# --- AC1: secret files, tool and shell ----------------------------------------------

_SECRET_PATHS = [".env", "~/.aws/credentials", ".ssh/id_rsa", "x.pem", ".npmrc"]


@pytest.mark.parametrize("path", _SECRET_PATHS)
def test_read_of_a_secret_file_is_secret_read(path):
    assert classify_read(path, SECRET_FILES, source_tool="read").rule == "secret.read"
    hit = classify_secret_read(path, SECRET_FILES, source_tool="read")
    assert hit is not None and hit.rule == "secret.read"
    assert hit.operation == Operation("fs_read", path, "read")


@pytest.mark.parametrize("path", _SECRET_PATHS)
def test_shell_read_of_a_secret_file_is_secret_read(path):
    hits = [c for c in _shell(f"cat {path}") if c.rule == "secret.read"]
    assert [c.operation for c in hits] == [Operation("fs_read", path, "bash")]


def test_plain_file_stays_fs_read():
    assert classify_read("src/a.ts", SECRET_FILES).rule == "fs.read"
    assert classify_secret_read("src/a.ts", SECRET_FILES) is None
    assert "secret.read" not in _rules("cat src/a.ts")


@pytest.mark.parametrize("path", ["/proc/self/environ", "/proc/1234/environ"])
def test_process_environment_is_always_secret_read(path):
    # Decision D-J: fixed, whatever `secrets.files` says.
    assert classify_secret_read(path, ()) is not None
    assert "secret.read" in _rules(f"cat {path}")


def test_secret_file_detail_comes_from_the_call():
    # T11: the matched tail of the path, never the glob.
    assert classify_secret_read("config/../.env.local", SECRET_FILES).detail == ".env.local"
    assert classify_secret_read("a/" * 40 + "x.pem", SECRET_FILES).detail == "x.pem"


# --- AC2: secret environment variables ---------------------------------------------


@pytest.mark.parametrize(
    "cmd",
    [
        "printenv OPENROUTER_API_KEY",
        "echo $AWS_SECRET_ACCESS_KEY",
        "echo ${GITHUB_TOKEN}",
        "env",
        "printenv",
        "sudo env",
        "env -u X",
        # Extras (decision D-I, D-J).
        "echo $env:AWS_X",
        "echo ${env:GITHUB_TOKEN}",
        "echo %GITHUB_TOKEN%",
        "echo ${!x}",
        "echo ${#AWS_SECRET}",
        'curl -d "$OPENROUTER_API_KEY" x',
        "X=$DB_PASSWORD ls",
        "ls > $AWS_FILE",
        "set",
        "export",
        "export -p",
        "declare -p",
        "typeset -x",
        "declare -p GITHUB_TOKEN",
    ],
)
def test_secret_variable_reads_are_secret_read(cmd):
    assert "secret.read" in _rules(cmd)


@pytest.mark.parametrize(
    "cmd",
    ["echo $HOME", "printenv PATH", "env ls", "echo $1 $? $$ $@", "set -e", "export FOO=1", "declare -p HOME"],
)
def test_ordinary_variables_are_not_secret_read(cmd):
    assert "secret.read" not in _rules(cmd)


def test_env_reference_detail_and_operation():
    hits = [c for c in _shell("printenv OPENROUTER_API_KEY") if c.rule == "secret.read"]
    assert hits == [
        Classification("secret.read", Operation("shell", "printenv OPENROUTER_API_KEY", "bash"), "OPENROUTER_API_KEY")
    ]
    assert [c.detail for c in _shell("env") if c.rule == "secret.read"] == ["env"]


def test_repeated_reference_is_reported_once():
    assert _rules("echo $GITHUB_TOKEN $GITHUB_TOKEN") == ["secret.read", "shell.unlisted"]


@pytest.mark.parametrize(
    "word, names",
    [
        ("$AWS_KEY", ("AWS_KEY",)),
        ("$AWS_KEY/x", ("AWS_KEY",)),
        ("${GITHUB_TOKEN}", ("GITHUB_TOKEN",)),
        ("${x,,}", ("x",)),
        ("${x:-default}", ("x",)),
        ("${#AWS_SECRET}", ("AWS_SECRET",)),
        ("$env:Path", ("Path",)),
        ("$ENV:Path", ("Path",)),
        ("${env:AWS_X}", ("AWS_X",)),
        ("%GITHUB_TOKEN%", ("GITHUB_TOKEN",)),
        ("${!x}", (INDIRECT,)),
        ("a$B${C}", ("B", "C")),
        ("$1 $? $$ $@ $#", ()),
        ("plain", ()),
        ("100%", ()),
        (None, ()),
        (3, ()),
    ],
)
def test_env_references(word, names):
    assert env_references(word) == names


def test_classify_env_reference():
    assert classify_env_reference("github_token", SECRET_ENV, operation=OP) == Classification(
        "secret.read", OP, "github_token"
    )
    assert classify_env_reference("HOME", SECRET_ENV, operation=OP) is None
    assert classify_env_reference(INDIRECT, (), operation=OP) == Classification("secret.read", OP, INDIRECT)
    assert classify_env_reference(None, SECRET_ENV, operation=OP) is None
    assert classify_env_reference("AWS_X", [None, "AWS_*", 3], operation=OP) is None  # entries without .search
    long_name = "AWS_" + "X" * 100
    assert classify_env_reference(long_name, SECRET_ENV, operation=OP).detail == long_name[:32]


# --- AC5: search tools (D15) ------------------------------------------------------


@pytest.mark.parametrize(
    "tool, arguments",
    [
        ("glob", {"pattern": "../../**/.env*"}),
        ("glob", {"pattern": "**/*.pem", "path": "src"}),
        ("grep", {"pattern": "KEY", "include": ".env*"}),
        ("grep", {"pattern": "KEY", "path": "~/.ssh"}),
        ("search_files", {"path": "src", "regex": "x", "file_pattern": "*.pem"}),
        ("read_file", {"path": ".npmrc"}),
    ],
)
def test_search_naming_a_secret_is_secret_read(tool, arguments):
    assert "secret.read" in [c.rule for c in _tool_reads(tool, arguments)]


@pytest.mark.parametrize(
    "tool, arguments",
    [
        ("grep", {"pattern": "x", "path": "."}),
        ("grep", {"pattern": "x", "path": "src/"}),
        ("grep", {"pattern": "x", "include": "*.py"}),
        ("glob", {"pattern": "**/*.ts"}),
        ("search_files", {"path": "src", "regex": "x"}),
    ],
)
def test_search_over_a_plain_directory_stays_fs_read(tool, arguments):
    # PRD D15, a stated limitation: `grep path=.` can still return a secret's contents.
    assert {c.rule for c in _tool_reads(tool, arguments)} == {"fs.read"}


def test_search_codebase_is_unknown_under_the_built_in_tools():
    # Deviation (STORY-013 plan, D-N): `search_codebase` is a `none` row of
    # SOURCES.md (its `queries[]` are regexes, no path), so it is tool.unknown
    # (deny) and D15 has nothing to read until a deployment maps it.
    call = ToolCall(id="c1", name="search_codebase", arguments=json.dumps({"queries": [".env"]}))
    assert map_tool_call(call, BUILT_IN_TOOLS, {}, 100_000) == Unknown()


# --- AC6: pipelines and a replaced pattern list -------------------------------------


def test_secret_read_in_a_pipeline():
    assert "secret.read" in _rules("cat .env | grep KEY")


def test_policy_file_patterns_replace_the_built_in_ones(tmp_path, monkeypatch):
    path = tmp_path / "action_policy.yaml"
    path.write_text('secrets:\n  env: ["MY_*"]\n  files: [".env"]\n', encoding="utf-8")
    monkeypatch.setattr(settings, "ACTION_POLICY_FILE", str(path))
    load()
    policy = get_policy()
    assert "secret.read" in _rules("echo $MY_VAR", policy)
    assert "secret.read" in _rules("echo $my_var", policy)  # IGNORECASE (STORY-006 decision 6)
    assert "secret.read" not in _rules("echo $AWS_SECRET_ACCESS_KEY", policy)
    assert "secret.read" not in _rules("printenv OPENROUTER_API_KEY", policy)
    assert "secret.read" in _rules("env", policy)  # the whole environment, always (F6)
    assert "secret.read" not in _rules("cat x.pem", policy)
    assert "secret.read" in _rules("cat .env", policy)


# --- robustness ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [None, b".env", 123, "a/" * 100_000, "$" * 100_000, "${" * 50_000, "%A%" * 30_000],
    # Explicit ids: Windows refuses an environment variable over 32767 characters.
    ids=["none", "bytes", "int", "long-path", "dollars", "braces", "percents"],
)
def test_never_raises(value):
    hit = classify_secret_read(value, SECRET_FILES)
    assert hit is None or hit.rule == "secret.read"
    assert isinstance(env_references(value), tuple)
    for name in env_references(value)[:5]:
        classify_env_reference(name, SECRET_ENV, operation=OP)
    if isinstance(value, str):
        assert isinstance(_shell("echo " + value), tuple)


def test_non_string_secret_read_fails_closed():
    assert classify_secret_read(None, SECRET_FILES, source_tool="t") == Classification(
        "secret.read", Operation("fs_read", "", "t"), ""
    )


def test_internal_error_fails_closed(monkeypatch):
    def _boom(*_a, **_k):
        raise RuntimeError("bug")

    monkeypatch.setattr(secrets.paths, "classify_read", _boom)
    assert classify_secret_read(".env", SECRET_FILES) == Classification(
        "secret.read", Operation("fs_read", ".env", ""), ""
    )


@pytest.mark.parametrize(
    "cmd",
    ["cat .env", "printenv OPENROUTER_API_KEY", "env", "cat " + "d/" * 50 + ".env.production.local", "echo $" + "A" * 80 + "_KEY"],
)
def test_detail_is_short_and_from_the_call(cmd):
    configured = set(BUILT_IN_POLICY.secrets.env.patterns) | set(BUILT_IN_POLICY.secrets.files.patterns)
    for c in _shell(cmd):
        assert len(c.detail) <= 32
        if c.rule == "secret.read":
            assert c.detail not in configured
            assert c.detail in cmd


# --- purity --------------------------------------------------------------------------


def test_secrets_module_stays_pure():
    """PRD-016 Section 6.12: no settings, no I/O, no `app` import but the vocabulary and `paths`."""
    source = inspect.getsource(secrets)
    assert "settings" not in vars(secrets)
    assert "open(" not in source
    assert "os." not in source
    imports = [line for line in source.splitlines() if line.startswith("import ") or line.startswith("from ")]
    app_imports = [line for line in imports if " app." in line or line.startswith("from app")]
    assert app_imports == ["from app.services.action_classifiers import Classification, Operation, paths"]


def test_importing_secrets_loads_no_settings():
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys, app.services.action_classifiers.secrets; "
            "print(sorted(m for m in sys.modules if m == 'app' or m.startswith('app.')))",
        ],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert completed.stdout.strip() == str(
        [
            "app",
            "app.services",
            "app.services.action_classifiers",
            "app.services.action_classifiers.paths",
            "app.services.action_classifiers.secrets",
        ]
    )
