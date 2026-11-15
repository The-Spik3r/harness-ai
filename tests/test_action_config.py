"""PRD-016 STORY-006 and STORY-007: the action policy, built in and from ACTION_POLICY_FILE.

STORY-006: the policy model, the 25 rules of PRD Section 6.3, the
protected-path and secret globs of Sections 6.3 and 6.6, the glob match
contract, `policy_digest()`, `load()`'s empty path, and the checks `_validate`
applies to every policy, the built-in one included (PRD-016 F8).

STORY-007: reading `ACTION_POLICY_FILE`, the per-id `rules:` merge (D12), the
wholesale sections, one test per Section 9.3 validation rule, a failed load
keeping the previous policy, and `examples/action_policy.yaml`.

Expected values are written out as literals here rather than imported from
the module: these tests are about the PRD table, and comparing the module with
itself would prove nothing.

STORY-008: the `ACTION_SQL_DIALECT` cross-check `load()` runs first, file or
no file (PRD-016 Sections 6.9, 9.3).

What it deliberately does **not** cover: how a classifier uses a glob, a list
or the dialect -- STORY-008's `tests/test_action_sql.py` and STORY-010 to
STORY-014.
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
import textwrap
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
    """AC 1. Patches `open` and `pathlib.Path`'s readers: `action_config.Path`
    is `pathlib.Path` (PRD-016 STORY-007 imports it for the loader), so the
    class-level patches cover the loader's read too, and `action_config.Path`
    itself is patched as well."""
    monkeypatch.setattr(settings, "ACTION_POLICY_FILE", "")

    def _no_read(*args, **kwargs):
        raise AssertionError("action_config read a file while ACTION_POLICY_FILE is unset")

    monkeypatch.setattr(builtins, "open", _no_read)
    monkeypatch.setattr(pathlib.Path, "open", _no_read)
    monkeypatch.setattr(pathlib.Path, "read_text", _no_read)
    monkeypatch.setattr(pathlib.Path, "read_bytes", _no_read)
    # PRD-016 STORY-007: the module now has a `Path`; constructing one must not happen either.
    monkeypatch.setattr(action_config, "Path", _no_read)

    assert load() is None
    assert get_policy() is BUILT_IN_POLICY


def test_load_with_a_policy_file_set_fails_closed(tmp_path, monkeypatch):
    """No silent fallback (STORY-006 plan, decision 2): a configured file that
    cannot be read stops the boot. A missing file is unreadable (PRD-016
    STORY-007: the real read path), and the type and the path still hold."""
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


# --- STORY-007: ACTION_POLICY_FILE ------------------------------------------

_SAMPLE_FILE = REPO_ROOT / "examples" / "action_policy.yaml"


def _write_policy(tmp_path, text, name="action_policy.yaml"):
    path = tmp_path / name
    path.write_text(textwrap.dedent(text), encoding="utf-8")
    return str(path)


def _load_text(tmp_path, monkeypatch, text, name="action_policy.yaml"):
    """Write `text` as a policy file, point the setting at it, and load it."""
    path = _write_policy(tmp_path, text, name)
    monkeypatch.setattr(settings, "ACTION_POLICY_FILE", path)
    load()
    return path


def _expect_file(tmp_path, monkeypatch, text, *fragments):
    """`load()` refuses `text`: the message names the file first, then every
    fragment (the node and the rule), and the built-in policy is still in
    force."""
    path = _write_policy(tmp_path, text)
    monkeypatch.setattr(settings, "ACTION_POLICY_FILE", path)
    with pytest.raises(ActionConfigError) as excinfo:
        load()
    message = str(excinfo.value)
    assert message.startswith(f"ACTION_POLICY_FILE '{path}': "), message
    for fragment in fragments:
        assert fragment in message, message
    assert get_policy() is BUILT_IN_POLICY
    return message


def _yaml_double_quoted(value):
    """A YAML double-quoted scalar, so a line break survives as one."""
    escaped = (
        value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r")
    )
    return '"' + escaped + '"'


# --- AC 1: rules: merges per id (D12) ---------------------------------------


def test_rules_merge_per_id_keeping_every_other_rule(tmp_path, monkeypatch):
    _load_text(tmp_path, monkeypatch, "rules:\n  shell.unlisted: {default: flag}\n")
    policy = get_policy()
    assert policy is not BUILT_IN_POLICY
    assert tuple(policy.rules) == RULE_IDS
    # A field the entry leaves out keeps its built-in value (orchestrator decision, STORY-007).
    assert policy.rules["shell.unlisted"] == Rule("flag", "action:shell:exec")
    for rule_id in RULE_IDS:
        if rule_id != "shell.unlisted":
            assert policy.rules[rule_id] == BUILT_IN_POLICY.rules[rule_id], rule_id


def test_a_rule_grant_alone_keeps_the_built_in_default(tmp_path, monkeypatch):
    _load_text(tmp_path, monkeypatch, "rules:\n  fs.read: {grant: 'action:fs:write'}\n")
    assert get_policy().rules["fs.read"] == Rule("allow", "action:fs:write")


@pytest.mark.parametrize("body", ["{grant: null}", "{grant: }"], ids=["null", "bare"])
def test_grant_null_removes_a_grant(tmp_path, monkeypatch, body):
    """Orchestrator decision, STORY-007: `grant: null` removes a grant explicitly."""
    _load_text(tmp_path, monkeypatch, f"rules:\n  sql.write: {body}\n")
    assert get_policy().rules["sql.write"] == Rule("deny", None)


def test_the_merge_base_is_the_built_in_table_not_the_previous_file(tmp_path, monkeypatch):
    _load_text(tmp_path, monkeypatch, "rules:\n  shell.unlisted: {default: flag}\n", "a.yaml")
    assert get_policy().rules["shell.unlisted"].default == "flag"
    _load_text(tmp_path, monkeypatch, "rules: {}\n", "b.yaml")
    assert get_policy().rules["shell.unlisted"] == BUILT_IN_POLICY.rules["shell.unlisted"]


# --- AC 2: present sections replace wholesale, absent ones keep -------------


@pytest.mark.parametrize(
    "text, check",
    [
        pytest.param(
            "tools:\n  bash: {kind: shell, target: command}\n",
            lambda p: set(p.tools) == {"bash"},
            id="tools",
        ),
        pytest.param("shell:\n  allow: [ls]\n", lambda p: p.shell_allow == ("ls",), id="shell"),
        pytest.param(
            "network:\n  allow: [pypi.org]\n",
            lambda p: p.network_allow == ("pypi.org",),
            id="network",
        ),
        pytest.param(
            "secrets:\n  env: ['X_*']\n  files: [a.txt]\n",
            lambda p: p.secrets.env.patterns == ("X_*",)
            and p.secrets.files.patterns == ("a.txt",)
            and not _matches(p.secrets.files, ".env"),
            id="secrets",
        ),
        pytest.param(
            "workspace:\n  roots: [/srv/app]\n",
            lambda p: p.workspace_roots == ("/srv/app",),
            id="workspace",
        ),
    ],
)
def test_a_present_section_replaces_the_built_in_one(tmp_path, monkeypatch, text, check):
    _load_text(tmp_path, monkeypatch, text)
    assert check(get_policy())


def test_an_absent_section_keeps_the_built_in_one(tmp_path, monkeypatch):
    _load_text(tmp_path, monkeypatch, "rules: {}\n")
    policy = get_policy()
    assert policy is not BUILT_IN_POLICY
    assert policy == BUILT_IN_POLICY
    assert policy.tools is BUILT_IN_TOOLS
    assert policy_digest() == policy_digest(BUILT_IN_POLICY)


def test_an_empty_list_means_empty(tmp_path, monkeypatch):
    """PRD-016 Section 6.6: "empty means empty, never 'use the default'"."""
    _load_text(tmp_path, monkeypatch, "shell:\n  allow: []\nsecrets:\n  env: []\n  files: []\n")
    policy = get_policy()
    assert policy.shell_allow == ()
    assert policy.secrets.env.patterns == ()
    assert policy.secrets.files.patterns == ()


def test_a_tool_mapping_accepts_default_format_and_extra_targets(tmp_path, monkeypatch):
    _load_text(
        tmp_path,
        monkeypatch,
        """\
        tools:
          glob: {kind: fs_read, target: path, default: ".", extra_targets: [pattern]}
          apply_patch: {kind: fs_write, target: patchText, format: patch}
        """,
    )
    tools = get_policy().tools
    assert tools["glob"] == ToolMapping("fs_read", "path", default=".", extra_targets=("pattern",))
    assert tools["apply_patch"] == ToolMapping("fs_write", "patchText", format="patch")


def test_load_ignores_comments_and_key_order_in_the_digest(tmp_path, monkeypatch):
    """PRD-016 Section 4: the digest is over the policy, not the file bytes."""
    _load_text(
        tmp_path,
        monkeypatch,
        "shell:\n  allow: [ls]\nrules:\n  sql.write: {default: flag, grant: null}\n",
        "a.yaml",
    )
    first = policy_digest()
    _load_text(
        tmp_path,
        monkeypatch,
        "# a comment\nrules:\n  sql.write: {grant: null, default: flag}  # same\n"
        "shell: {allow: [ls]}\n",
        "b.yaml",
    )
    assert policy_digest() == first


# --- AC 3: one test per Section 9.3 rule ------------------------------------


@pytest.mark.parametrize("key", ["rule", "tool", "protected_paths", "workspaces"])
def test_file_refuses_an_unknown_top_level_key(tmp_path, monkeypatch, key):
    """`protected_paths` included: it is built-in only (STORY-006 plan, decision 4)."""
    _expect_file(
        tmp_path, monkeypatch, f"{key}: {{}}\n", "document", "unknown key", repr(key), "workspace"
    )


@pytest.mark.parametrize(
    "text, node, key",
    [
        ("workspace: {root: [/a]}\n", "workspace", "root"),
        ("network: {allowed: []}\n", "network", "allowed"),
        ("shell: {allowlist: []}\n", "shell", "allowlist"),
        ("secrets: {envs: [], files: []}\n", "secrets", "envs"),
    ],
)
def test_file_refuses_an_unknown_section_key(tmp_path, monkeypatch, text, node, key):
    _expect_file(tmp_path, monkeypatch, text, f"{node}: unknown key {key!r}")


def test_file_refuses_a_missing_section_key(tmp_path, monkeypatch):
    """A present `secrets:` states both keys (orchestrator decision, STORY-007)."""
    _expect_file(tmp_path, monkeypatch, "secrets: {env: []}\n", "secrets", "missing key 'files'")


@pytest.mark.parametrize(
    "text, node",
    [("tools: [bash]\n", "tools"), ("rules: null\n", "rules"), ("workspace: /a\n", "workspace")],
)
def test_file_refuses_a_section_of_the_wrong_type(tmp_path, monkeypatch, text, node):
    _expect_file(tmp_path, monkeypatch, text, f"{node}: must be a mapping")


@pytest.mark.parametrize("text", ["", "- a\n", "just text\n"], ids=["empty", "list", "scalar"])
def test_file_refuses_a_document_that_is_not_a_mapping(tmp_path, monkeypatch, text):
    """An empty file is an error, not "use the built-in policy" (orchestrator decision, STORY-007)."""
    _expect_file(tmp_path, monkeypatch, text, "document", "must be a mapping of sections")


def test_file_refuses_a_list_value_that_is_not_a_list(tmp_path, monkeypatch):
    _expect_file(tmp_path, monkeypatch, "shell:\n  allow:\n", "shell.allow", "must be a list")


def test_file_refuses_an_unreadable_file(tmp_path, monkeypatch):
    """Not UTF-8: `UnicodeDecodeError` must surface as `ActionConfigError`."""
    path = tmp_path / "bad.yaml"
    path.write_bytes(b"\xff\xfe\xfa")
    monkeypatch.setattr(settings, "ACTION_POLICY_FILE", str(path))
    with pytest.raises(ActionConfigError) as excinfo:
        load()
    message = str(excinfo.value)
    assert message.startswith(f"ACTION_POLICY_FILE '{path}': file: cannot be read"), message
    assert get_policy() is BUILT_IN_POLICY


def test_file_refuses_a_directory_as_the_file(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "ACTION_POLICY_FILE", str(tmp_path))
    with pytest.raises(ActionConfigError) as excinfo:
        load()
    assert "file: cannot be read" in str(excinfo.value)
    assert get_policy() is BUILT_IN_POLICY


def test_file_refuses_invalid_yaml(tmp_path, monkeypatch):
    _expect_file(tmp_path, monkeypatch, "rules: [\n", "file: is not valid YAML")


def test_file_refuses_an_unknown_rule_id(tmp_path, monkeypatch):
    message = _expect_file(
        tmp_path,
        monkeypatch,
        "rules:\n  sql.nuke: {default: deny}\n",
        "rules: 'sql.nuke'",
        "unknown rule",
    )
    assert "sql.read" in message  # the allowed ids are listed


def test_file_refuses_an_unknown_rule_key(tmp_path, monkeypatch):
    _expect_file(
        tmp_path,
        monkeypatch,
        "rules:\n  sql.read: {defualt: deny}\n",
        "rules: 'sql.read'",
        "unknown key 'defualt'",
    )


def test_file_refuses_a_rule_that_is_not_a_mapping(tmp_path, monkeypatch):
    _expect_file(
        tmp_path,
        monkeypatch,
        "rules:\n  shell.unlisted: flag\n",
        "rules: 'shell.unlisted'",
        "must be a mapping",
    )


def test_file_refuses_an_empty_rule_entry(tmp_path, monkeypatch):
    """Orchestrator decision, STORY-007."""
    _expect_file(
        tmp_path,
        monkeypatch,
        "rules:\n  shell.unlisted: {}\n",
        "rules: 'shell.unlisted'",
        "default and/or grant",
    )


@pytest.mark.parametrize("body", ["{default: allow}", "{grant: null}"])
def test_file_refuses_a_tool_opaque_rule_entry(tmp_path, monkeypatch, body):
    _expect_file(
        tmp_path,
        monkeypatch,
        f"rules:\n  tool.opaque: {body}\n",
        "rules: 'tool.opaque'",
        "opaque_tools",
    )


def test_file_refuses_a_bad_decision(tmp_path, monkeypatch):
    _expect_file(
        tmp_path,
        monkeypatch,
        "rules:\n  sql.read: {default: block}\n",
        "rules: 'sql.read'",
        "'block'",
        "allow, deny, flag",
    )


def test_file_refuses_a_null_default(tmp_path, monkeypatch):
    _expect_file(
        tmp_path,
        monkeypatch,
        "rules:\n  sql.read: {default: null}\n",
        "rules: 'sql.read'",
        "not a decision",
    )


def test_file_refuses_an_unknown_permission(tmp_path, monkeypatch):
    _expect_file(
        tmp_path,
        monkeypatch,
        "rules:\n  sql.write: {grant: 'action:sql:everything'}\n",
        "rules: 'sql.write'",
        "not an action permission",
    )


@pytest.mark.parametrize("rule_id", sorted(NON_GRANTABLE_RULES))
def test_file_refuses_a_grant_on_a_non_grantable_rule(tmp_path, monkeypatch, rule_id):
    """PRD-016 T5, for each of the ten (`test_the_non_grantable_set_has_ten_rules`)."""
    _expect_file(
        tmp_path,
        monkeypatch,
        f"rules:\n  {rule_id}: {{grant: 'action:sql:write'}}\n",
        f"rules: '{rule_id}'",
        "non-grantable",
    )


def test_file_refuses_empty_tools(tmp_path, monkeypatch):
    """PRD-016 T7."""
    _expect_file(tmp_path, monkeypatch, "tools: {}\n", "tools: must not be empty")


def test_file_refuses_an_unknown_kind(tmp_path, monkeypatch):
    _expect_file(
        tmp_path,
        monkeypatch,
        "tools:\n  bash: {kind: shel, target: command}\n",
        "tools: 'bash'",
        "unknown operation kind 'shel'",
    )


@pytest.mark.parametrize(
    "missing, body", [("target", "{kind: shell}"), ("kind", "{target: command}")]
)
def test_file_refuses_a_missing_target(tmp_path, monkeypatch, missing, body):
    _expect_file(
        tmp_path,
        monkeypatch,
        f"tools:\n  bash: {body}\n",
        "tools: 'bash'",
        f"missing key {missing!r}",
    )


def test_file_refuses_an_unknown_tool_key(tmp_path, monkeypatch):
    _expect_file(
        tmp_path,
        monkeypatch,
        "tools:\n  bash: {kind: shell, target: command, targets: [x]}\n",
        "tools: 'bash'",
        "unknown key 'targets'",
    )


@pytest.mark.parametrize(
    "body, fragment",
    [
        ("{kind: fs_write, target: patchText, format: diff}", "unknown target format 'diff'"),
        ("{kind: fs_write, target: 'files['}", "invalid segment"),
        (
            "{kind: fs_write, target: patchText, format: patch, default: '.'}",
            "default is only allowed",
        ),
        ("{kind: fs_read, target: path, extra_targets: pattern}", "extra_targets must be a list"),
    ],
    ids=["format", "target", "default", "extra_targets_string"],
)
def test_file_refuses_a_tool_mapping_the_adapter_rejects(tmp_path, monkeypatch, body, fragment):
    _expect_file(tmp_path, monkeypatch, f"tools:\n  t1: {body}\n", "tools: 't1'", fragment)


def test_file_refuses_a_tool_both_mapped_and_opaque(tmp_path, monkeypatch):
    _expect_file(
        tmp_path,
        monkeypatch,
        "tools:\n  bash: {kind: shell, target: command}\nopaque_tools:\n  bash: allow\n",
        "opaque_tools: 'bash'",
        "also mapped under tools",
    )


def test_file_refuses_an_opaque_tool_value_that_is_not_a_decision(tmp_path, monkeypatch):
    _expect_file(
        tmp_path,
        monkeypatch,
        "opaque_tools:\n  todowrite: maybe\n",
        "opaque_tools: 'todowrite'",
        "'maybe'",
    )


@pytest.mark.parametrize("root", ["projects", "./x", "~/x", "C:x", "C:", ""])
def test_file_refuses_a_relative_workspace_root(tmp_path, monkeypatch, root):
    _expect_file(
        tmp_path,
        monkeypatch,
        f"workspace:\n  roots: [{root!r}]\n",
        f"workspace.roots: {root!r}",
        "must be an absolute path",
    )


def test_file_accepts_absolute_workspace_roots(tmp_path, monkeypatch):
    roots = ["/home/dev/projects", "C:/Repo", "C:\\Repo", "d:/x", "\\\\srv\\share"]
    _load_text(
        tmp_path,
        monkeypatch,
        "workspace:\n  roots: [" + ", ".join(_yaml_double_quoted(r) for r in roots) + "]\n",
    )
    assert get_policy().workspace_roots == tuple(roots)


def test_file_refuses_a_bad_glob(tmp_path, monkeypatch):
    _expect_file(
        tmp_path,
        monkeypatch,
        "secrets:\n  env: []\n  files: ['a[b']\n",
        "secrets.files: 'a[b'",
        "unsupported",
    )


@pytest.mark.parametrize(
    "entry",
    [
        "https://pypi.org",
        "pypi.org:443",
        "pypi.org/simple",
        "u@pypi.org",
        "*",
        "*pypi.org",
        "a.*.com",
        "10.0.0.0/8",
        "[::1]",
        "*.10.0.0.1",
        "999.1.1.1",
        "127.1",
        "",
        " pypi.org",
        "my_host.example.com",
        "pypi.org.",
    ],
)
def test_file_refuses_a_bad_network_entry(tmp_path, monkeypatch, entry):
    _expect_file(
        tmp_path,
        monkeypatch,
        f"network:\n  allow: [{entry!r}]\n",
        f"network.allow: {entry!r}",
        "not a host, a '*.' wildcard host or an IP literal",
    )


@pytest.mark.parametrize("entry", ["*.com", "*.localhost"])
def test_file_refuses_a_single_label_wildcard(tmp_path, monkeypatch, entry):
    """Orchestrator decision, STORY-007: a top-level-domain wildcard opens the network rule."""
    _expect_file(
        tmp_path,
        monkeypatch,
        f"network:\n  allow: [{entry!r}]\n",
        f"network.allow: {entry!r}",
        "at least two labels",
        "top-level-domain wildcard",
    )


def test_file_accepts_each_network_entry_shape(tmp_path, monkeypatch):
    entries = [
        "registry.npmjs.org",
        "*.githubusercontent.com",
        "*.example.com",
        "localhost",
        "Pypi.ORG",
        "169.254.169.254",
        "::1",
    ]
    _load_text(
        tmp_path,
        monkeypatch,
        "network:\n  allow: [" + ", ".join(repr(e) for e in entries) + "]\n",
    )
    assert get_policy().network_allow == tuple(entries)


@pytest.mark.parametrize(
    "entry, operator",
    [
        ("ls; rm", ";"),
        ("a && b", "&"),
        ("a | b", "|"),
        ("echo $HOME", "$"),
        ("echo `id`", "`"),
        ("a > f", ">"),
        ("a < f", "<"),
        ("(ls)", "("),
        ("a\nb", "\n"),
        ("a\rb", "\r"),
    ],
)
def test_file_refuses_a_shell_allow_entry_with_an_operator(tmp_path, monkeypatch, entry, operator):
    _expect_file(
        tmp_path,
        monkeypatch,
        "shell:\n  allow: [" + _yaml_double_quoted(entry) + "]\n",
        f"shell.allow: {entry!r}",
        f"contains the shell operator {operator!r}",
    )


@pytest.mark.parametrize("entry", ["", "  "])
def test_file_refuses_an_empty_shell_allow_entry(tmp_path, monkeypatch, entry):
    _expect_file(
        tmp_path,
        monkeypatch,
        f"shell:\n  allow: [{entry!r}]\n",
        f"shell.allow: {entry!r}",
        "must not be empty",
    )


def test_file_accepts_a_multi_token_shell_allow_entry(tmp_path, monkeypatch):
    _load_text(tmp_path, monkeypatch, "shell:\n  allow: [npm test, git]\n")
    assert get_policy().shell_allow == ("npm test", "git")


@pytest.mark.parametrize(
    "text, key",
    [
        ("rules: {}\nrules: {}\n", "'rules'"),
        ("rules:\n  sql.read: {default: allow}\n  sql.read: {default: deny}\n", "'sql.read'"),
        (
            "tools:\n  bash: {kind: shell, target: command}\n  bash: {kind: shell, target: cmd}\n",
            "'bash'",
        ),
    ],
    ids=["section", "rule_id", "tool_name"],
)
def test_file_refuses_a_duplicate_key(tmp_path, monkeypatch, text, key):
    """PRD-016 D13: `strict_yaml` refuses a key written twice, at any depth."""
    _expect_file(tmp_path, monkeypatch, text, "file: is not valid YAML", f"duplicate key {key}")


# --- AC 4: a failed load keeps the previous policy -------------------------


def test_a_failed_load_keeps_the_previous_file_policy_and_digest(tmp_path, monkeypatch):
    _load_text(tmp_path, monkeypatch, "rules:\n  shell.unlisted: {default: flag}\n", "good.yaml")
    policy = get_policy()
    digest = policy_digest()
    assert policy is not BUILT_IN_POLICY
    assert digest != policy_digest(BUILT_IN_POLICY)

    # Fails late: rules and tools parse, then `_validate` refuses the network entry.
    bad = _write_policy(
        tmp_path,
        """\
        rules:
          shell.unlisted: {default: allow}
        tools:
          bash: {kind: shell, target: command}
        network:
          allow: ["https://x"]
        """,
        "bad.yaml",
    )
    monkeypatch.setattr(settings, "ACTION_POLICY_FILE", bad)
    with pytest.raises(ActionConfigError):
        load()

    assert get_policy() is policy
    assert policy_digest() == digest


# --- AC 5: examples/action_policy.yaml --------------------------------------


def test_examples_action_policy_yaml_loads(monkeypatch):
    """PRD-016 Section 11: "`examples/action_policy.yaml` loads in a test"."""
    monkeypatch.setattr(settings, "ACTION_POLICY_FILE", str(_SAMPLE_FILE))
    load()
    policy = get_policy()
    assert policy is not BUILT_IN_POLICY
    assert policy_digest() != policy_digest(BUILT_IN_POLICY)
    assert policy.rules["shell.unlisted"] == Rule("flag", "action:shell:exec")
    assert policy.rules["sql.write"] == Rule("deny", "action:sql:write")
    assert policy.tools["apply_patch"] == ToolMapping("fs_write", "patchText", format="patch")
    assert len(policy.tools) == 7
    assert dict(policy.opaque_tools) == {"todowrite": "allow"}
    assert policy.workspace_roots == ("/home/dev/projects",)
    assert "npm test" in policy.shell_allow
    assert "*.githubusercontent.com" in policy.network_allow
    # `OPENROUTER_*` is the one addition to the PRD 6.6 sample (orchestrator decision, STORY-007).
    assert policy.secrets.env.patterns == _PRD_SECRET_ENV
    assert policy.secrets.files.patterns == _PRD_SECRET_FILES


# --- STORY-008: the ACTION_SQL_DIALECT cross-check ---------------------------
#
# PRD-016 STORY-008: `load()` refuses a dialect sqlglot does not know before it
# looks at ACTION_POLICY_FILE. The dialect names are literals, not read from
# `SQL_DIALECTS`.


def test_load_accepts_a_known_sql_dialect(monkeypatch):
    """STORY-008 AC 5: `ACTION_SQL_DIALECT=postgres` loads."""
    monkeypatch.setattr(settings, "ACTION_POLICY_FILE", "")
    monkeypatch.setattr(settings, "ACTION_SQL_DIALECT", "postgres")

    assert load() is None
    assert get_policy() is BUILT_IN_POLICY


def test_empty_sql_dialect_is_the_generic_one(monkeypatch):
    monkeypatch.setattr(settings, "ACTION_POLICY_FILE", "")
    monkeypatch.setattr(settings, "ACTION_SQL_DIALECT", "")

    assert load() is None
    assert get_policy() is BUILT_IN_POLICY


def test_load_refuses_an_unknown_sql_dialect(monkeypatch):
    """STORY-008 AC 5: the error names the setting and lists the dialects sqlglot knows."""
    monkeypatch.setattr(settings, "ACTION_POLICY_FILE", "")
    monkeypatch.setattr(settings, "ACTION_SQL_DIALECT", "nosuchdb")

    with pytest.raises(ActionConfigError) as excinfo:
        load()

    message = str(excinfo.value)
    assert "ACTION_SQL_DIALECT" in message
    assert "'nosuchdb'" in message
    for dialect in ("postgres", "mysql", "sqlite", "tsql", "snowflake"):
        assert dialect in message
    assert get_policy() is BUILT_IN_POLICY


@pytest.mark.parametrize(
    "value",
    ["Postgres", " postgres", "postgres ", "mysql, normalization_strategy = lowercase"],
)
def test_sql_dialect_check_is_exact(monkeypatch, value):
    """Exact membership: no case folding, no whitespace, no sqlglot settings suffix."""
    monkeypatch.setattr(settings, "ACTION_POLICY_FILE", "")
    monkeypatch.setattr(settings, "ACTION_SQL_DIALECT", value)

    with pytest.raises(ActionConfigError) as excinfo:
        load()

    assert repr(value) in str(excinfo.value)


def test_sql_dialect_is_checked_before_the_policy_file(tmp_path, monkeypatch):
    """A valid file does not get a bad dialect through, and nothing is rebound."""
    monkeypatch.setattr(settings, "ACTION_POLICY_FILE", str(_SAMPLE_FILE))
    monkeypatch.setattr(settings, "ACTION_SQL_DIALECT", "nosuchdb")

    with pytest.raises(ActionConfigError) as excinfo:
        load()

    assert "ACTION_SQL_DIALECT" in str(excinfo.value)
    assert "ACTION_POLICY_FILE" not in str(excinfo.value)
    assert get_policy() is BUILT_IN_POLICY
