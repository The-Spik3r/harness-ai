"""PRD-023 STORY-007: the MCP config loader (`app/services/mcp_config.py`).

No database. Every test restores the module state it touches (`mcp_config._config`,
`action_config._policy`, `authz.ROLE_PERMISSIONS`) through `monkeypatch`.
"""

import json
import logging
from pathlib import Path
from types import MappingProxyType

import pytest
import yaml

from app.config import settings
from app.services import action_config, authz, mcp_config
from app.services.identity import Identity
from app.services.mcp_config import MCPConfigError

_EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
_SECRET = "s3ntinel-secret-value"

#: A matrix that grants both example skills; `run-migration` also holds its `requires`.
_GRANTING = {
    "dev": {"skill:open-pull-request", "mcp:connect"},
    "dba": {"skill:run-migration", "action:sql:ddl", "mcp:connect"},
    "admin": {"mcp:connect"},
}


def _example_doc() -> dict:
    return yaml.safe_load((_EXAMPLES / "mcp.yaml").read_text(encoding="utf-8"))


@pytest.fixture
def env(monkeypatch, tmp_path):
    """Restore module state, set the credentials the example reads, and give the
    example action policy and a granting matrix."""
    monkeypatch.setattr(mcp_config, "_config", mcp_config._config)
    monkeypatch.setattr(action_config, "_policy", action_config._policy)
    monkeypatch.setattr(authz, "ROLE_PERMISSIONS", {k: set(v) for k, v in _GRANTING.items()})
    monkeypatch.setenv("MCP_GITHUB_TOKEN", _SECRET)
    monkeypatch.setenv("MCP_PG_STAGING_KEY", _SECRET + "-pg")
    monkeypatch.setattr(settings, "MCP_ENABLED", True)
    monkeypatch.setattr(settings, "ACTION_POLICY_FILE", str(_EXAMPLES / "mcp_action_policy.yaml"))
    action_config.load()
    return tmp_path


def _write(tmp_path, doc, name="mcp.yaml") -> str:
    path = tmp_path / name
    path.write_text(doc if isinstance(doc, str) else yaml.safe_dump(doc), encoding="utf-8")
    return str(path)


def _load(monkeypatch, tmp_path, doc) -> mcp_config.McpConfig:
    monkeypatch.setattr(settings, "MCP_CONFIG_FILE", _write(tmp_path, doc))
    mcp_config.load()
    return mcp_config.get_config()


def _identity(role: str) -> Identity:
    return Identity("u-" + role, role)


# --- The example loads ------------------------------------------------------


def test_examples_load(env, monkeypatch):
    """PRD-023 Section 11: the shipped examples load, together, with a granting matrix."""
    monkeypatch.setattr(settings, "MCP_CONFIG_FILE", str(_EXAMPLES / "mcp.yaml"))
    mcp_config.load()
    cfg = mcp_config.get_config()
    assert list(cfg.servers) == ["github", "postgres-staging"]
    assert [s.id for s in cfg.skills] == ["open-pull-request", "run-migration"]
    assert cfg.v1_prefixes == ("harness_", "harness__")
    assert cfg.servers["github"].timeout_seconds == 60
    assert cfg.servers["postgres-staging"].allow_insecure is True
    assert cfg.servers["postgres-staging"].timeout_seconds == settings.MCP_CALL_TIMEOUT_SECONDS
    assert cfg.skills[0].version == "1.2.0"
    assert cfg.skills[1].requires == ("action:sql:ddl",)


def test_absent_v1_aliases_means_no_aliases(env, monkeypatch):
    doc = _example_doc()
    del doc["v1_aliases"]
    assert _load(monkeypatch, env, doc).v1_prefixes == ()


def test_declared_v1_aliases_are_kept(env, monkeypatch):
    doc = _example_doc()
    doc["v1_aliases"] = {"prefixes": ["harness_"]}
    assert _load(monkeypatch, env, doc).v1_prefixes == ("harness_",)


# --- The rules --------------------------------------------------------------


def _mut(fn):
    def apply(doc):
        fn(doc)
        return doc

    return apply


def _set(path, value):
    def fn(doc):
        node = doc
        for key in path[:-1]:
            node = node[key]
        node[path[-1]] = value

    return _mut(fn)


def _del(path):
    def fn(doc):
        node = doc
        for key in path[:-1]:
            node = node[key]
        del node[path[-1]]

    return _mut(fn)


def _rename_server(old, new):
    def fn(doc):
        doc["servers"][new] = doc["servers"].pop(old)

    return _mut(fn)


_GH = ["servers", "github"]
_PG = ["servers", "postgres-staging"]
_PR = ["skills", "open-pull-request"]

# (id, mutation, node fragment, failing text)
_RULES = [
    ("unknown-top-key", _set(["extra"], 1), "file", "unknown key 'extra'"),
    ("unknown-server-key", _set(_GH + ["bogus"], 1), "servers.github", "unknown key 'bogus'"),
    (
        "unknown-auth-key",
        _set(_GH + ["auth", "bogus"], 1),
        "servers.github.auth",
        "unknown key 'bogus'",
    ),
    (
        "unknown-skill-key",
        _set(_PR + ["bogus"], 1),
        "skills.open-pull-request",
        "unknown key 'bogus'",
    ),
    ("unknown-alias-key", _set(["v1_aliases", "bogus"], 1), "v1_aliases", "unknown key 'bogus'"),
    ("server-id-uppercase", _rename_server("github", "GitHub"), "servers.GitHub", "must match"),
    ("server-id-underscore", _rename_server("github", "git_hub"), "servers.git_hub", "must match"),
    ("server-id-33-chars", _rename_server("github", "a" * 33), "servers." + "a" * 33, "must match"),
    ("url-scheme", _set(_GH + ["url"], "ftp://x.example/mcp"), "servers.github.url", "absolute http(s)"),
    ("url-relative", _set(_GH + ["url"], "/mcp"), "servers.github.url", "absolute http(s)"),
    ("url-no-host", _set(_GH + ["url"], "https:///mcp"), "servers.github.url", "absolute http(s)"),
    (
        "url-userinfo",
        _set(_GH + ["url"], "https://user:pw@x.example/mcp"),
        "servers.github.url",
        "must not carry credentials",
    ),
    (
        "http-without-allow-insecure",
        _del(_PG + ["allow_insecure"]),
        "servers.postgres-staging.url",
        "allow_insecure: true",
    ),
    (
        "allow-insecure-not-bool",
        _set(_PG + ["allow_insecure"], "yes please"),
        "servers.postgres-staging.allow_insecure",
        "true or false",
    ),
    (
        "auth-type",
        _set(_GH + ["auth", "type"], "oauth"),
        "servers.github.auth.type",
        "'oauth' is not an auth type",
    ),
    (
        "bearer-without-token-env",
        _set(_GH + ["auth"], {"type": "bearer"}),
        "servers.github.auth",
        "requires key 'token_env'",
    ),
    (
        "none-with-token-env",
        _set(_GH + ["auth"], {"type": "none", "token_env": "X"}),
        "servers.github.auth.token_env",
        "is not used",
    ),
    (
        "token-env-unset",
        _set(_GH + ["auth", "token_env"], "MCP_DEFINITELY_UNSET_TOKEN"),
        "servers.github.auth.token_env",
        "'MCP_DEFINITELY_UNSET_TOKEN' is not set or is empty",
    ),
    (
        "value-env-unset",
        _set(_PG + ["auth", "value_env"], "MCP_DEFINITELY_UNSET_KEY"),
        "servers.postgres-staging.auth.value_env",
        "'MCP_DEFINITELY_UNSET_KEY' is not set or is empty",
    ),
    (
        "header-authorization",
        _set(_PG + ["auth", "name"], "Authorization"),
        "servers.postgres-staging.auth.name",
        "not allowed as an upstream header",
    ),
    (
        "header-authorization-lowercase",
        _set(_PG + ["auth", "name"], "authorization"),
        "servers.postgres-staging.auth.name",
        "not allowed as an upstream header",
    ),
    (
        "header-hop-by-hop",
        _set(_PG + ["auth", "name"], "Connection"),
        "servers.postgres-staging.auth.name",
        "not allowed as an upstream header",
    ),
    (
        "header-mcp-prefix",
        _set(_PG + ["auth", "name"], "Mcp-Session-Id"),
        "servers.postgres-staging.auth.name",
        "not allowed as an upstream header",
    ),
    (
        "header-not-a-token",
        _set(_PG + ["auth", "name"], "X Api Key"),
        "servers.postgres-staging.auth.name",
        "not allowed as an upstream header",
    ),
    (
        "timeout-zero",
        _set(_GH + ["timeout_seconds"], 0),
        "servers.github.timeout_seconds",
        "between 1 and 600",
    ),
    (
        "timeout-601",
        _set(_GH + ["timeout_seconds"], 601),
        "servers.github.timeout_seconds",
        "between 1 and 600",
    ),
    (
        "timeout-bool",
        _set(_GH + ["timeout_seconds"], True),
        "servers.github.timeout_seconds",
        "must be an integer",
    ),
    (
        "max-result-bytes-1023",
        _set(_GH + ["max_result_bytes"], 1023),
        "servers.github.max_result_bytes",
        "at least 1024",
    ),
    ("skill-id-uppercase", _set(["skills", "Bad"], dict()), "skills.Bad", "must match"),
    (
        "skill-version-float",
        _set(_PR + ["version"], 1.2),
        "skills.open-pull-request.version",
        "quote it",
    ),
    (
        "skill-missing-description",
        _del(_PR + ["description"]),
        "skills.open-pull-request",
        "missing key 'description'",
    ),
    ("skill-empty-tools", _set(_PR + ["tools"], []), "skills.open-pull-request.tools", "must not be empty"),
    (
        "tool-without-separator",
        _set(_PR + ["tools"], ["githubcreate"]),
        "skills.open-pull-request.tools[0]",
        "is not of the form <server>__<tool>",
    ),
    (
        "tool-without-name",
        _set(_PR + ["tools"], ["github__"]),
        "skills.open-pull-request.tools[0]",
        "is not of the form <server>__<tool>",
    ),
    (
        "tool-unconfigured-server",
        _set(_PR + ["tools"], ["nope__x"]),
        "skills.open-pull-request.tools[0]",
        "server 'nope' is not configured",
    ),
    (
        "requires-not-an-action-permission",
        _set(_PR + ["requires"], ["query:submit"]),
        "skills.open-pull-request.requires[0]",
        "is not an action permission",
    ),
    (
        "requires-not-a-list",
        _set(_PR + ["requires"], "action:sql:ddl"),
        "skills.open-pull-request.requires",
        "must be a list",
    ),
    (
        "alias-empty-prefix",
        _set(["v1_aliases", "prefixes"], ["harness_", ""]),
        "v1_aliases.prefixes[1]",
        "must be a non-empty string",
    ),
    (
        "alias-bad-characters",
        _set(["v1_aliases", "prefixes"], ["harness."]),
        "v1_aliases.prefixes[0]",
        "[A-Za-z0-9_-]",
    ),
    (
        "alias-duplicate",
        _set(["v1_aliases", "prefixes"], ["harness_", "harness_"]),
        "v1_aliases.prefixes",
        "must not repeat",
    ),
]


@pytest.mark.parametrize(
    "mutate,node,text", [pytest.param(m, n, t, id=i) for i, m, n, t in _RULES]
)
def test_rule(env, monkeypatch, caplog, mutate, node, text):
    """One case per PRD-023 Section 9.3 rule: file path, node, failing text; and
    no secret value anywhere in the message."""
    path = _write(env, mutate(_example_doc()))
    monkeypatch.setattr(settings, "MCP_CONFIG_FILE", path)
    before = mcp_config.get_config()
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(MCPConfigError) as exc_info:
            mcp_config.load()
    message = str(exc_info.value)
    assert message.startswith(f"MCP_CONFIG_FILE '{path}': ")
    assert f": {node}: " in message
    assert text in message
    assert _SECRET not in message and _SECRET not in caplog.text
    assert mcp_config.get_config() is before


def test_duplicate_yaml_key_is_refused(env, monkeypatch):
    path = _write(env, "servers: {}\nservers: {}\n")
    monkeypatch.setattr(settings, "MCP_CONFIG_FILE", path)
    with pytest.raises(MCPConfigError, match="is not valid YAML") as exc_info:
        mcp_config.load()
    assert path in str(exc_info.value)


def test_unreadable_file_is_refused(env, monkeypatch):
    path = str(env / "missing.yaml")
    monkeypatch.setattr(settings, "MCP_CONFIG_FILE", path)
    with pytest.raises(MCPConfigError, match="cannot be read") as exc_info:
        mcp_config.load()
    assert path in str(exc_info.value)


def test_document_must_be_a_mapping(env, monkeypatch):
    monkeypatch.setattr(settings, "MCP_CONFIG_FILE", _write(env, "- a\n- b\n"))
    with pytest.raises(MCPConfigError, match="file: must be a mapping"):
        mcp_config.load()


# --- Cross-validation -------------------------------------------------------


def test_unmapped_tool_message_is_story_8_exact(env, monkeypatch):
    """PRD-023 User Story 8: the message, with the failing entry as the third tool."""
    doc = _example_doc()
    doc["skills"]["open-pull-request"]["tools"] = [
        "github__create_branch",
        "github__push_files",
        "github__create_pullrequest",
    ]
    path = _write(env, doc)
    monkeypatch.setattr(settings, "MCP_CONFIG_FILE", path)
    with pytest.raises(MCPConfigError) as exc_info:
        mcp_config.load()
    assert str(exc_info.value) == (
        f"MCP_CONFIG_FILE '{path}': skills.open-pull-request.tools[2]: "
        "'github__create_pullrequest' has no mcp_tools or mcp_opaque_tools entry in ACTION_POLICY_FILE"
    )


def test_policy_server_absent_from_servers_is_refused(env, monkeypatch):
    doc = _example_doc()
    doc["skills"].pop("run-migration")
    del doc["servers"]["postgres-staging"]
    path = _write(env, doc)
    monkeypatch.setattr(settings, "MCP_CONFIG_FILE", path)
    with pytest.raises(MCPConfigError) as exc_info:
        mcp_config.load()
    message = str(exc_info.value)
    assert "ACTION_POLICY_FILE mcp_tools.postgres-staging" in message
    assert "'postgres-staging' is not defined under servers" in message


def test_role_granted_an_undefined_skill_is_refused(env, monkeypatch):
    authz.ROLE_PERMISSIONS["dev"].add("skill:ghost")
    monkeypatch.setattr(settings, "MCP_CONFIG_FILE", str(_EXAMPLES / "mcp.yaml"))
    with pytest.raises(MCPConfigError) as exc_info:
        mcp_config.load()
    message = str(exc_info.value)
    assert "roles.dev" in message and "'skill:ghost'" in message and "not defined" in message


def test_role_holding_a_skill_without_its_requires_is_refused(env, monkeypatch):
    """O2: `run-migration` requires `action:sql:ddl`."""
    authz.ROLE_PERMISSIONS["dba"].discard("action:sql:ddl")
    monkeypatch.setattr(settings, "MCP_CONFIG_FILE", str(_EXAMPLES / "mcp.yaml"))
    with pytest.raises(MCPConfigError) as exc_info:
        mcp_config.load()
    message = str(exc_info.value)
    assert "roles.dba" in message
    assert "'skill:run-migration'" in message and "'action:sql:ddl'" in message


# --- Enabled / disabled -----------------------------------------------------


def test_disabled_opens_no_file(env, monkeypatch):
    """Off means PRD-017 (D20): no file is touched, and the empty config is in force."""
    monkeypatch.setattr(settings, "MCP_ENABLED", False)
    monkeypatch.setattr(settings, "MCP_CONFIG_FILE", str(env / "nonexistent.yaml"))

    def _boom(*args, **kwargs):
        raise AssertionError("MCP_ENABLED=false must not open a file")

    monkeypatch.setattr(Path, "read_text", _boom)
    monkeypatch.setattr(Path, "open", _boom)
    monkeypatch.setattr("builtins.open", _boom)
    mcp_config.load()
    assert mcp_config.get_config() is mcp_config.EMPTY_CONFIG
    assert mcp_config.visible_tools(_identity("admin")) == {}
    assert mcp_config.held_skills(_identity("admin")) == ()


def test_disabled_clears_a_previous_config(env, monkeypatch):
    monkeypatch.setattr(settings, "MCP_CONFIG_FILE", str(_EXAMPLES / "mcp.yaml"))
    mcp_config.load()
    assert mcp_config.get_config().skills
    monkeypatch.setattr(settings, "MCP_ENABLED", False)
    mcp_config.load()
    assert mcp_config.get_config() is mcp_config.EMPTY_CONFIG


def test_enabled_without_file_fails(env, monkeypatch):
    monkeypatch.setattr(settings, "MCP_CONFIG_FILE", "")
    with pytest.raises(MCPConfigError, match="MCP_CONFIG_FILE: setting: .*MCP_ENABLED=false"):
        mcp_config.load()


def test_failing_load_keeps_the_previous_config(env, monkeypatch):
    monkeypatch.setattr(settings, "MCP_CONFIG_FILE", str(_EXAMPLES / "mcp.yaml"))
    mcp_config.load()
    good = mcp_config.get_config()
    digest = mcp_config.mcp_config_digest()
    monkeypatch.setattr(settings, "MCP_CONFIG_FILE", _write(env, "servers: 3\n", "bad.yaml"))
    with pytest.raises(MCPConfigError):
        mcp_config.load()
    assert mcp_config.get_config() is good
    assert mcp_config.mcp_config_digest() == digest


# --- Visibility -------------------------------------------------------------


def test_held_skills_and_visible_tools(env, monkeypatch):
    monkeypatch.setattr(settings, "MCP_CONFIG_FILE", str(_EXAMPLES / "mcp.yaml"))
    mcp_config.load()

    dev = _identity("dev")
    assert [s.id for s in mcp_config.held_skills(dev)] == ["open-pull-request"]
    tools = mcp_config.visible_tools(dev)
    assert dict(tools) == {"github": {"create_branch", "push_files", "create_pull_request"}}
    assert isinstance(tools["github"], frozenset)

    dba = _identity("dba")
    assert dict(mcp_config.visible_tools(dba)) == {"postgres-staging": {"query"}}

    # No grant, unknown role: nothing, and no server key.
    assert dict(mcp_config.visible_tools(_identity("admin"))) == {}
    assert mcp_config.held_skills(_identity("nobody")) == ()


def test_rbac_off_built_in_matrix_sees_nothing(env, monkeypatch):
    """RBAC off must not hand every skill to every caller (no bypass, D6)."""
    monkeypatch.setattr(authz, "ROLE_PERMISSIONS", {"admin": {"mcp:connect"}, "user": {"mcp:connect"}})
    monkeypatch.setattr(settings, "RBAC_ENABLED", False)
    monkeypatch.setattr(settings, "MCP_CONFIG_FILE", str(_EXAMPLES / "mcp.yaml"))
    mcp_config.load()
    assert dict(mcp_config.visible_tools(_identity("admin"))) == {}
    assert dict(mcp_config.visible_tools(_identity("user"))) == {}


def test_rbac_off_with_a_granting_matrix_is_non_empty(env, monkeypatch):
    """The other half: `holds` follows the matrix, whatever RBAC_ENABLED says."""
    monkeypatch.setattr(settings, "RBAC_ENABLED", False)
    monkeypatch.setattr(settings, "MCP_CONFIG_FILE", str(_EXAMPLES / "mcp.yaml"))
    mcp_config.load()
    assert dict(mcp_config.visible_tools(_identity("dev"))) != {}


def test_two_skills_sharing_a_tool_expose_it_once(env, monkeypatch):
    doc = _example_doc()
    doc["skills"]["second"] = {
        "version": "1",
        "description": "d",
        "instructions": "i",
        "tools": ["github__push_files", "github__create_branch"],
    }
    authz.ROLE_PERMISSIONS["dev"].add("skill:second")
    _load(monkeypatch, env, doc)
    tools = mcp_config.visible_tools(_identity("dev"))
    assert tools["github"] == frozenset({"create_branch", "push_files", "create_pull_request"})
    assert [s.id for s in mcp_config.held_skills(_identity("dev"))] == [
        "open-pull-request",
        "second",
    ]


def test_split_tool_splits_at_the_first_double_underscore(env, monkeypatch):
    monkeypatch.setattr(settings, "MCP_CONFIG_FILE", str(_EXAMPLES / "mcp.yaml"))
    mcp_config.load()
    assert mcp_config.split_tool("github__a__b") == ("github", "a__b")
    for bad in ("github", "github__", "__x", "nope__x"):
        with pytest.raises(ValueError):
            mcp_config.split_tool(bad)


# --- Digest and secrecy -----------------------------------------------------


def _digest_of(monkeypatch, tmp_path, doc) -> str:
    _load(monkeypatch, tmp_path, doc)
    return mcp_config.mcp_config_digest()


def test_digest_tracks_config_not_secrets(env, monkeypatch):
    base = _digest_of(monkeypatch, env, _example_doc())
    assert base.startswith("sha256:") and len(base) == len("sha256:") + 64

    doc = _example_doc()
    doc["skills"]["run-migration"]["version"] = "0.4.0"
    assert _digest_of(monkeypatch, env, doc) != base

    # Only the credential's VALUE changes: same digest.
    monkeypatch.setenv("MCP_GITHUB_TOKEN", "a-different-secret")
    assert _digest_of(monkeypatch, env, _example_doc()) == base

    # The env var NAME changes: different digest.
    monkeypatch.setenv("MCP_GITHUB_TOKEN_2", _SECRET)
    doc = _example_doc()
    doc["servers"]["github"]["auth"]["token_env"] = "MCP_GITHUB_TOKEN_2"
    assert _digest_of(monkeypatch, env, doc) != base

    # allow_insecure is recorded.
    doc = _example_doc()
    doc["servers"]["postgres-staging"]["url"] = "https://pg-mcp.internal:8080/mcp"
    del doc["servers"]["postgres-staging"]["allow_insecure"]
    assert _digest_of(monkeypatch, env, doc) != base


def test_digest_ignores_key_order_and_comments(env, monkeypatch):
    base = _digest_of(monkeypatch, env, _example_doc())
    reordered = dict(reversed(list(_example_doc().items())))
    assert _digest_of(monkeypatch, env, reordered) == base
    text = (_EXAMPLES / "mcp.yaml").read_text(encoding="utf-8") + "\n# trailing comment\n"
    assert _digest_of(monkeypatch, env, text) == base


def test_digest_when_disabled_is_stable_and_differs(env, monkeypatch):
    loaded = _digest_of(monkeypatch, env, _example_doc())
    monkeypatch.setattr(settings, "MCP_ENABLED", False)
    mcp_config.load()
    off = mcp_config.mcp_config_digest()
    assert off == mcp_config.mcp_config_digest(mcp_config.EMPTY_CONFIG)
    assert off != loaded


def test_secret_value_appears_nowhere(env, monkeypatch, caplog):
    with caplog.at_level(logging.DEBUG):
        cfg = _load(monkeypatch, env, _example_doc())
    assert _SECRET not in repr(cfg)
    assert _SECRET not in json.dumps(mcp_config._canonical(cfg))
    assert _SECRET not in mcp_config.mcp_config_digest()
    assert _SECRET not in caplog.text
    # The one sanctioned path.
    assert mcp_config.upstream_auth_headers("github") == {"Authorization": f"Bearer {_SECRET}"}
    assert mcp_config.upstream_auth_headers("postgres-staging") == {"X-Api-Key": _SECRET + "-pg"}


def test_auth_none_has_no_headers(env, monkeypatch):
    doc = _example_doc()
    doc["servers"]["github"]["auth"] = {"type": "none"}
    _load(monkeypatch, env, doc)
    assert mcp_config.upstream_auth_headers("github") == {}
    doc["servers"]["github"].pop("auth")
    _load(monkeypatch, env, doc)
    assert mcp_config.upstream_auth_headers("github") == {}


def test_config_collections_are_immutable(env, monkeypatch):
    cfg = _load(monkeypatch, env, _example_doc())
    assert isinstance(cfg.servers, MappingProxyType)
    assert isinstance(cfg.skills, tuple) and isinstance(cfg.skills[0].tools, tuple)


# --- The 55-character warning ----------------------------------------------


def _long_tool_doc(total_length: int) -> tuple[dict, str]:
    """A config whose one skill tool is `github__<name>` of `total_length` chars."""
    name = "t" * (total_length - len("github__"))
    doc = _example_doc()
    doc["skills"]["open-pull-request"]["tools"] = [f"github__{name}"]
    return doc, name


def _mapped_policy(monkeypatch, tmp_path, name):
    path = tmp_path / "policy.yaml"
    path.write_text(f"mcp_opaque_tools:\n  github:\n    {name}: allow\n", encoding="utf-8")
    monkeypatch.setattr(settings, "ACTION_POLICY_FILE", str(path))
    action_config.load()


def test_tool_name_over_55_characters_warns_once(env, monkeypatch, caplog):
    doc, name = _long_tool_doc(56)
    doc["skills"].pop("run-migration")
    authz.ROLE_PERMISSIONS["dba"] = {"mcp:connect"}
    _mapped_policy(monkeypatch, env, name)
    with caplog.at_level(logging.WARNING, logger=mcp_config.logger.name):
        _load(monkeypatch, env, doc)
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "open-pull-request" in warnings[0].getMessage() and "t" * 20 in warnings[0].getMessage()
    assert mcp_config.get_config().skills


def test_tool_name_of_55_characters_does_not_warn(env, monkeypatch, caplog):
    doc, name = _long_tool_doc(55)
    doc["skills"].pop("run-migration")
    authz.ROLE_PERMISSIONS["dba"] = {"mcp:connect"}
    _mapped_policy(monkeypatch, env, name)
    with caplog.at_level(logging.WARNING, logger=mcp_config.logger.name):
        _load(monkeypatch, env, doc)
    assert not [r for r in caplog.records if r.levelno == logging.WARNING]
