"""PRD-016 STORY-006: the built-in action policy, get_policy(), the digest and load()'s empty path.

This module covers `app/services/action_config.py` as STORY-006 leaves it: the
policy model, the 25 rules of PRD Section 6.3, the protected-path and secret
globs of Sections 6.3 and 6.6, the glob match contract, `policy_digest()`, and
the checks `_validate` applies to every policy, the built-in one included
(PRD-016 F8).

Expected values are written out as literals here rather than imported from
the module: these tests are about the PRD table, and comparing the module with
itself would prove nothing.

What it deliberately does **not** cover: reading `ACTION_POLICY_FILE`, the
per-id `rules:` merge, the wholesale sections and the file-level versions of
the `_validate` cases below (Section 9.3) -- STORY-007. How a classifier uses a
glob -- STORY-011 (paths) and STORY-013 (secrets).
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import builtins
import dataclasses
import pathlib
import re
import subprocess
import sys
from pathlib import Path
from types import MappingProxyType

import pytest

from app.config import settings
from app.services import action_config
from app.services.action_adapters import BUILT_IN_TOOLS, ToolCall, ToolMapping, Unknown, map_tool_call
from app.services.action_classifiers import NON_GRANTABLE_RULES, RULE_IDS
from app.services.action_config import (
    BUILT_IN_POLICY,
    ActionConfigError,
    Rule,
    _validate,
    get_policy,
    load,
    policy_digest,
)
from app.services.authz import ACTION_PERMISSIONS

REPO_ROOT = Path(__file__).resolve().parents[1]

#: PRD-016 Section 6.3, lines 226-250, written out.
_PRD_6_3_RULES = {
    "sql.read": ("allow", None),
    "sql.write": ("deny", "action:sql:write"),
    "sql.unscoped_write": ("deny", None),
    "sql.ddl": ("deny", "action:sql:ddl"),
    "sql.dcl": ("deny", None),
    "sql.unparsed": ("deny", None),
    "shell.allowlisted": ("allow", None),
    "shell.unlisted": ("deny", "action:shell:exec"),
    "shell.destructive": ("deny", None),
    "shell.pipe_to_interpreter": ("deny", None),
    "shell.inline_interpreter": ("deny", "action:shell:exec"),
    "shell.package_install": ("deny", "action:shell:exec"),
    "shell.service_control": ("deny", "action:shell:exec"),
    "shell.unclassifiable": ("deny", None),
    "fs.read": ("allow", None),
    "fs.write_in_workspace": ("allow", None),
    "fs.write_outside_workspace": ("deny", "action:fs:write"),
    "fs.write_protected": ("deny", None),
    "net.allowlisted": ("allow", None),
    "net.unlisted": ("deny", "action:net:egress"),
    "net.unparsed": ("deny", None),
    "secret.read": ("deny", "action:secret:read"),
    "tool.unknown": ("deny", None),
    "tool.opaque": (None, None),
    "tool.malformed": ("deny", None),
}

_PRD_PROTECTED_PATHS = (
    ".env*",
    "*.pem",
    "*.key",
    "id_*",
    ".aws/**",
    ".ssh/**",
    ".git/**",
    ".github/workflows/**",
    ".gitlab-ci.yml",
    "Jenkinsfile",
    ".circleci/**",
)
_PRD_SECRET_ENV = ("*KEY*", "*SECRET*", "*TOKEN*", "*PASSWORD*", "*CREDENTIAL*", "AWS_*", "OPENROUTER_*")
_PRD_SECRET_FILES = (".env*", "*.pem", "*.key", "id_*", ".aws/**", ".ssh/**", ".npmrc", ".pypirc")


def _spec(**overrides):
    """The built-in policy's spec, with `overrides` replacing keys."""
    spec = {
        "rules": dict(_PRD_6_3_RULES),
        "tools": BUILT_IN_TOOLS,
        "opaque_tools": {},
        "shell_allow": (),
        "network_allow": (),
        "workspace_roots": (),
        "protected_paths": _PRD_PROTECTED_PATHS,
        "secret_env": _PRD_SECRET_ENV,
        "secret_files": _PRD_SECRET_FILES,
    }
    spec.update(overrides)
    return spec


def _matches(globs, value):
    return any(compiled.search(value) for compiled in globs.compiled)


# --- AC 1: load() with the setting empty -----------------------------------


def test_load_reads_no_file_when_action_policy_file_unset(monkeypatch):
    """AC 1. Patches `open` and `pathlib` rather than `action_config.Path`:
    the module has no `Path` yet (STORY-007 adds it), so any read would have
    to go through one of these."""
    monkeypatch.setattr(settings, "ACTION_POLICY_FILE", "")

    def _no_read(*args, **kwargs):
        raise AssertionError("action_config read a file while ACTION_POLICY_FILE is unset")

    monkeypatch.setattr(builtins, "open", _no_read)
    monkeypatch.setattr(pathlib.Path, "open", _no_read)
    monkeypatch.setattr(pathlib.Path, "read_text", _no_read)
    monkeypatch.setattr(pathlib.Path, "read_bytes", _no_read)

    assert load() is None
    assert get_policy() is BUILT_IN_POLICY


def test_load_with_a_policy_file_set_fails_closed(tmp_path, monkeypatch):
    """No silent fallback (STORY-006 plan, decision 2): a configured file this
    build cannot read stops the boot. The assertion is the type and the path,
    which STORY-007's "unreadable file" error for a missing file also holds."""
    path = str(tmp_path / "missing.yaml")
    monkeypatch.setattr(settings, "ACTION_POLICY_FILE", path)

    with pytest.raises(ActionConfigError) as excinfo:
        load()

    assert path in str(excinfo.value)
    assert "ACTION_POLICY_FILE" in str(excinfo.value)
    assert get_policy() is BUILT_IN_POLICY


# --- AC 2: the built-in policy is PRD Sections 6.3 and 6.6 -----------------


def test_built_in_rules_are_prd_section_6_3():
    assert len(BUILT_IN_POLICY.rules) == 25
    assert tuple(BUILT_IN_POLICY.rules) == RULE_IDS
    assert {
        rule_id: (rule.default, rule.grant) for rule_id, rule in BUILT_IN_POLICY.rules.items()
    } == _PRD_6_3_RULES


def test_the_non_grantable_set_has_ten_rules():
    assert len(NON_GRANTABLE_RULES) == 10


@pytest.mark.parametrize("rule_id", sorted(NON_GRANTABLE_RULES))
def test_the_ten_non_grantable_rules_have_no_grant(rule_id):
    assert BUILT_IN_POLICY.rules[rule_id].grant is None
    assert BUILT_IN_POLICY.rules[rule_id].default == "deny"


def test_every_grant_is_an_action_permission():
    grants = {rule.grant for rule in BUILT_IN_POLICY.rules.values() if rule.grant is not None}
    assert grants <= ACTION_PERMISSIONS
    assert sum(rule.grant is not None for rule in BUILT_IN_POLICY.rules.values()) == 9


def test_tool_opaque_has_no_default_of_its_own():
    """Section 6.3 gives `tool.opaque` the default "(per entry)": the
    opaque_tools entry decides (STORY-006 plan, decision 3)."""
    assert BUILT_IN_POLICY.rules["tool.opaque"] == Rule(None, None)
    assert all(
        rule.default is not None
        for rule_id, rule in BUILT_IN_POLICY.rules.items()
        if rule_id != "tool.opaque"
    )


def test_built_in_tools_are_story_004s_built_in_tools():
    assert BUILT_IN_POLICY.tools is BUILT_IN_TOOLS


@pytest.mark.parametrize("name", ["todowrite", "task", "question", "search_codebase", "ask_question"])
def test_built_in_opaque_tools_is_empty(name):
    """Orchestrator decision (STORY-004 plan): the built-in `opaque_tools` is
    empty. The `none` tools of `tests/corpora/actions/SOURCES.md` (OpenCode
    `todowrite`, `task`, `question`, ...; Cline `search_codebase`,
    `ask_question`, ...) are `tool.unknown` (deny) until a deployment names
    them -- the D1 floor."""
    policy = BUILT_IN_POLICY
    assert dict(policy.opaque_tools) == {}
    result = map_tool_call(
        ToolCall("c1", name, "{}"),
        policy.tools,
        policy.opaque_tools,
        settings.ACTION_MAX_ARGUMENT_CHARACTERS,
    )
    assert result == Unknown()


def test_built_in_protected_path_globs_are_prd_section_6_3():
    assert BUILT_IN_POLICY.protected_paths.patterns == _PRD_PROTECTED_PATHS


def test_built_in_secret_globs_are_prd_sections_6_3_and_6_6():
    """`secrets.env` is Section 6.3's seven (the 6.6 sample is a deployment
    example and omits `OPENROUTER_*`); `secrets.files` is Section 6.6's eight,
    because 6.3 gives no file list (STORY-006 plan, decision 5)."""
    assert BUILT_IN_POLICY.secrets.env.patterns == _PRD_SECRET_ENV
    assert BUILT_IN_POLICY.secrets.files.patterns == _PRD_SECRET_FILES


def test_built_in_workspace_network_and_shell_lists_are_empty():
    """PRD-016 Section 6.5: nothing allowlisted, nothing reachable, no workspace."""
    assert BUILT_IN_POLICY.workspace_roots == ()
    assert BUILT_IN_POLICY.network_allow == ()
    assert BUILT_IN_POLICY.shell_allow == ()


def test_every_built_in_glob_is_compiled_once():
    for globs in (
        BUILT_IN_POLICY.protected_paths,
        BUILT_IN_POLICY.secrets.env,
        BUILT_IN_POLICY.secrets.files,
    ):
        assert len(globs.compiled) == len(globs.patterns)
        assert all(isinstance(compiled, re.Pattern) for compiled in globs.compiled)
        assert all(compiled.flags & re.IGNORECASE for compiled in globs.compiled)


def test_built_in_policy_is_immutable():
    with pytest.raises(TypeError):
        BUILT_IN_POLICY.rules["sql.read"] = Rule("deny", None)
    with pytest.raises(dataclasses.FrozenInstanceError):
        BUILT_IN_POLICY.shell_allow = ("x",)


# --- The glob contract (STORY-006 plan, decision 6) -------------------------


@pytest.mark.parametrize(
    "path",
    [
        ".env",
        "./.env",
        ".ENV.local",
        "/home/dev/projects/app/.env.local",
        ".github/workflows/ci.yml",
        ".git/config",
        "a/.git/HEAD",
        "id_rsa",
        "x.pem",
        "C:/Users/u/.ssh/id_ed25519",
        "Jenkinsfile",
    ],
)
def test_protected_path_globs_match(path):
    assert _matches(BUILT_IN_POLICY.protected_paths, path)


@pytest.mark.parametrize(
    "path", ["src/env.ts", ".gitignore", "x.pem.txt", "docs/github/workflows.md", ".git"]
)
def test_protected_path_globs_do_not_match(path):
    assert not _matches(BUILT_IN_POLICY.protected_paths, path)


@pytest.mark.parametrize(
    "name", ["AWS_SECRET_ACCESS_KEY", "openrouter_api_key", "GITHUB_TOKEN", "DB_PASSWORD"]
)
def test_secret_env_globs_match(name):
    assert _matches(BUILT_IN_POLICY.secrets.env, name)


@pytest.mark.parametrize("name", ["PATH", "HOME"])
def test_secret_env_globs_do_not_match(name):
    assert not _matches(BUILT_IN_POLICY.secrets.env, name)


@pytest.mark.parametrize("path", [".npmrc", "a/.pypirc", "home/u/.aws/credentials"])
def test_secret_file_globs_match(path):
    assert _matches(BUILT_IN_POLICY.secrets.files, path)


@pytest.mark.parametrize(
    "glob, matching, not_matching",
    [
        ("a/**/b", ["a/b", "a/x/b", "a/x/y/b"], ["ab", "a/xb"]),
        ("a/**", ["a/x", "a/x/y"], ["a"]),
        ("?.txt", ["x.txt"], ["xy.txt", "/.txt"]),
    ],
)
def test_double_star_and_question_mark(glob, matching, not_matching):
    policy = _validate("test", _spec(protected_paths=(glob,)))
    for value in matching:
        assert _matches(policy.protected_paths, value), value
    for value in not_matching:
        assert not _matches(policy.protected_paths, value), value


# --- AC 3: get_policy() before load() --------------------------------------


def test_get_policy_before_load_returns_the_built_in_policy():
    """AC 3. A fresh interpreter is the only place where `load()` has provably
    never run."""
    env = {**os.environ, "ACTION_POLICY_FILE": ""}
    env.setdefault("OPENROUTER_API_KEY", "test-key")
    env.setdefault("ADMIN_TOKEN", "test-token")
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "from app.services import action_config as c; "
            "print(c.get_policy() is c.BUILT_IN_POLICY)",
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "True"


def test_get_policy_in_process_without_load_returns_the_built_in_policy():
    assert action_config._policy is BUILT_IN_POLICY
    assert get_policy() is BUILT_IN_POLICY


# --- AC 4: the digest ------------------------------------------------------


def test_policy_digest_is_stable():
    first = policy_digest()
    assert first == policy_digest()
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", first)
    assert first == policy_digest(BUILT_IN_POLICY)


def _with_rules(**changed):
    return dataclasses.replace(
        BUILT_IN_POLICY, rules=MappingProxyType({**BUILT_IN_POLICY.rules, **changed})
    )


@pytest.mark.parametrize(
    "changed",
    [
        pytest.param(lambda: _with_rules(**{"shell.unlisted": Rule("flag", "action:shell:exec")}), id="default"),
        pytest.param(lambda: _with_rules(**{"shell.unlisted": Rule("deny", None)}), id="grant"),
        pytest.param(
            lambda: dataclasses.replace(BUILT_IN_POLICY, network_allow=("example.com",)),
            id="network_allow",
        ),
    ],
)
def test_policy_digest_changes_with_one_change(changed):
    assert policy_digest(changed()) != policy_digest(BUILT_IN_POLICY)


def test_policy_digest_ignores_key_order_and_identity():
    reversed_rules = dict(reversed(list(_PRD_6_3_RULES.items())))
    reversed_tools = dict(reversed(list(BUILT_IN_TOOLS.items())))
    other = _validate("test", _spec(rules=reversed_rules, tools=reversed_tools))
    assert other is not BUILT_IN_POLICY
    assert policy_digest(other) == policy_digest(BUILT_IN_POLICY)


# --- _validate: the floor every policy is held to (PRD-016 F8) -------------


def _expect(spec, *fragments):
    with pytest.raises(ActionConfigError) as excinfo:
        _validate("built-in action policy", spec)
    message = str(excinfo.value)
    assert message.startswith("built-in action policy: "), message
    for fragment in fragments:
        assert fragment in message, message
    return message


def test_the_built_in_spec_validates():
    assert _validate("test", _spec()) == BUILT_IN_POLICY


def test_validate_refuses_a_missing_rule():
    rules = dict(_PRD_6_3_RULES)
    del rules["sql.dcl"]
    _expect(_spec(rules=rules), "rules", "missing", "sql.dcl")


def test_validate_refuses_an_unknown_rule():
    message = _expect(
        _spec(rules={**_PRD_6_3_RULES, "sql.nuke": ("deny", None)}), "rules", "'sql.nuke'", "unknown rule"
    )
    assert "sql.read" in message  # the allowed ids are listed


def test_validate_refuses_an_unknown_decision():
    _expect(
        _spec(rules={**_PRD_6_3_RULES, "sql.read": ("block", None)}),
        "rules: 'sql.read'",
        "'block'",
        "allow, deny, flag",
    )


def test_validate_refuses_an_unknown_grant():
    _expect(
        _spec(rules={**_PRD_6_3_RULES, "sql.write": ("deny", "action:sql:everything")}),
        "rules: 'sql.write'",
        "'action:sql:everything'",
        "not an action permission",
    )


@pytest.mark.parametrize("rule_id", sorted(NON_GRANTABLE_RULES))
def test_validate_refuses_a_grant_on_a_non_grantable_rule(rule_id):
    """PRD-016 T5."""
    _expect(
        _spec(rules={**_PRD_6_3_RULES, rule_id: ("deny", "action:sql:write")}),
        f"rules: '{rule_id}'",
        "non-grantable",
    )


def test_validate_refuses_a_default_on_tool_opaque():
    _expect(
        _spec(rules={**_PRD_6_3_RULES, "tool.opaque": ("allow", None)}),
        "rules: 'tool.opaque'",
        "opaque_tools",
    )


def test_validate_refuses_empty_tools():
    """PRD-016 T7."""
    _expect(_spec(tools={}), "tools", "must not be empty")


def test_validate_refuses_a_tool_that_is_not_a_tool_mapping():
    _expect(_spec(tools={"bash": {"kind": "shell"}}), "tools: 'bash'", "ToolMapping")


def test_validate_refuses_an_opaque_tool_with_a_bad_decision():
    _expect(_spec(opaque_tools={"x": "maybe"}), "opaque_tools: 'x'", "'maybe'")


def test_validate_refuses_an_opaque_tool_also_in_tools():
    _expect(_spec(opaque_tools={"bash": "allow"}), "opaque_tools: 'bash'", "tools")


def test_validate_accepts_an_opaque_tool():
    policy = _validate("test", _spec(opaque_tools={"todowrite": "allow"}))
    assert dict(policy.opaque_tools) == {"todowrite": "allow"}


@pytest.mark.parametrize("glob", ["a[b]", "a**", "/etc/**", "a//b", "", "a/", "a\\b"])
def test_validate_refuses_a_bad_glob(glob):
    _expect(_spec(protected_paths=(glob,)), "protected_paths", repr(glob))


def test_validate_refuses_a_bad_secret_file_glob():
    _expect(_spec(secret_files=("x[",)), "secrets.files", "'x['")


def test_validate_refuses_an_env_glob_with_a_slash():
    _expect(_spec(secret_env=("A/B",)), "secrets.env", "'A/B'", "/")


def test_validate_refuses_an_unknown_spec_key():
    spec = _spec()
    spec["extra"] = ()
    _expect(spec, "spec", "extra")


def test_validated_tools_are_copied_not_shared():
    tools = {"bash": ToolMapping("shell", "command")}
    policy = _validate("test", _spec(tools=tools))
    tools["write"] = ToolMapping("fs_write", "filePath")
    assert set(policy.tools) == {"bash"}
