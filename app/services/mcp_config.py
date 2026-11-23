"""The MCP gateway's configuration: servers, skills, aliases (PRD-023 Sections 6.6, 6.8, 9.3).

This module owns the I/O behind `MCP_CONFIG_FILE`. `action_policy` and
`authz` stay pure; everything that reads a setting, a file or an environment
variable for the gateway lives here (the split `action_config` makes for the
action policy).

Entry points:

- `load()` reads `MCP_CONFIG_FILE` when `MCP_ENABLED` is true, validates every
  node, resolves each credential's environment value, cross-validates against
  the loaded action policy and the loaded role matrix, and puts the result in
  force. With `MCP_ENABLED=false` it opens nothing (PRD-017 D20, "off means
  off") and leaves the empty config in force.
- `get_config()` returns what is in force; the empty config before `load()`.
- `held_skills(identity)` / `visible_tools(identity)` are the pure visibility
  accessors (PRD-023 D6, Section 6.5). They read `authz.holds`, which has no
  `RBAC_ENABLED` bypass: with RBAC off the built-in matrix holds no
  `skill:*`, so a caller sees nothing.
- `upstream_auth_headers(server_id)` is the one reader of a credential value
  (D10, T2). STORY-010 builds the southbound headers from it.
- `split_tool(name)` splits `<server>__<tool>` at the first `__` (O7).
- `mcp_config_digest()` is the SHA-256 of the effective config, never of a
  secret value.

Called once at startup in **both** lifespans (`app/main.py` and
`chat_ui/chat_ui/chat_ui.py`), after `action_config.load()`: the Reflex
`api_transformer` mount bypasses the former, as for every other loader.

Failure leaves the previous config in force: `_config` is assigned as the
last statement of `load()`.
"""

import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Optional
from urllib.parse import urlsplit

import yaml

from app.config import settings
from app.services import action_config, authz, strict_yaml
from app.services.authz import ACTION_PERMISSIONS
from app.services.identity import Identity

logger = logging.getLogger(__name__)


class MCPConfigError(Exception):
    """Raised for every way `MCP_CONFIG_FILE` can be wrong (PRD-023 Section 9.3).

    Every message reads `"<source>: <node>: <message>"`: the file, the node in
    YAML path form (`skills.open-pull-request.tools[2]`) and the rule. A
    message never carries a credential value or a URL's userinfo. Startup
    fails; there is never a silent fallback (PRD-023 Story 8).
    """


def _fail(source: str, *parts: str) -> MCPConfigError:
    return MCPConfigError(f"{source}: " + ": ".join(parts))


def _allowed(values) -> str:
    return ", ".join(sorted(values))


# --- The model -------------------------------------------------------------

_AUTH_TYPES = ("bearer", "header", "none")

#: PRD-023 Section 6.4: same literal as `action_config._MCP_SERVER_ID`, so the
#: two files agree. No `_`: it would collide with the `__` separator (O7).
_SERVER_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,31}")

#: An HTTP token (RFC 9110 Section 5.6.2): what a header name may be.
_HEADER_TOKEN = re.compile(r"[A-Za-z0-9!#$%&'*+.^_`|~-]+")

#: Headers the gateway owns or that only a proxy may set: refused as the
#: `auth.name` of a `type: header` server (PRD-023 Section 9.3). `Authorization`
#: is the `bearer` type's header; `Mcp-*` belongs to the protocol layer.
_REFUSED_HEADERS = frozenset(
    {
        "authorization",
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "proxy-connection",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
    }
)

_PREFIX = re.compile(r"[A-Za-z0-9_-]+")

#: Cline hashes a tool name longer than 55 characters (PRD-023 Section 6.8,
#: `tests/corpora/mcp/SOURCES.md`), and there is no reverse map: such a tool is
#: reachable through `/mcp` only, so load() warns.
_CLINE_NAME_LIMIT = 55

_SERVER_KEYS = ("url", "allow_insecure", "auth", "timeout_seconds", "max_result_bytes")
_AUTH_KEYS = ("type", "token_env", "name", "value_env")
_SKILL_KEYS = ("version", "description", "instructions", "tools", "requires")
_SKILL_REQUIRED = ("version", "description", "instructions", "tools")
_TOP_KEYS = ("servers", "skills", "v1_aliases")
_ALIAS_KEYS = ("prefixes",)


@dataclass(frozen=True)
class McpAuth:
    """How the harness authenticates to one upstream (PRD-023 D10).

    `env_name` / `header_name` are config; `_secret` is the resolved value,
    kept out of `repr`, equality and every digest. It is read only through
    `upstream_auth_headers`.
    """

    type: str
    env_name: str = ""
    header_name: str = ""
    _secret: str = field(default="", repr=False, compare=False)


@dataclass(frozen=True)
class McpServer:
    id: str
    url: str
    allow_insecure: bool
    auth: McpAuth
    timeout_seconds: int
    max_result_bytes: int


@dataclass(frozen=True)
class Skill:
    """A named set of gateway tools (PRD-023 D5). Carries no policy of its own."""

    id: str
    version: str
    description: str
    instructions: str
    tools: tuple[str, ...]
    requires: tuple[str, ...]


@dataclass(frozen=True)
class McpConfig:
    """The effective gateway config. `v1_prefixes` empty means no `/v1` alias."""

    servers: Mapping[str, McpServer] = field(default_factory=lambda: MappingProxyType({}))
    skills: tuple[Skill, ...] = ()
    v1_prefixes: tuple[str, ...] = ()


EMPTY_CONFIG = McpConfig()

#: The config in force. Private and read through `get_config()`, for the same
#: reason as `action_config._policy`.
_config = EMPTY_CONFIG


def get_config() -> McpConfig:
    """The config in force -- empty until `load()` runs, and while MCP is off."""
    return _config


# --- Accessors -------------------------------------------------------------


def split_tool(name: str, config: Optional[McpConfig] = None) -> tuple[str, str]:
    """`<server>__<tool>` -> `(server, tool)`, split at the FIRST `__` (O7).

    Server ids cannot contain `_`, so the first `__` is unambiguous; a tool
    name may contain `__`. Raises `ValueError` when there is no `__`, either
    side is empty, or the server is not configured (in `config`, default the
    one in force).
    """
    server, sep, tool = name.partition("__")
    if not sep or not server or not tool:
        raise ValueError(f"{name!r} is not of the form <server>__<tool>")
    servers = (config or _config).servers
    if server not in servers:
        raise ValueError(f"{name!r}: server {server!r} is not configured")
    return server, tool


def held_skills(identity: Identity, config: Optional[McpConfig] = None) -> tuple[Skill, ...]:
    """The defined skills the identity's role holds, in config order (PRD-023 D6).

    Reads `authz.holds`, never `authorize`: with RBAC off `authorize` returns
    at once and would show every skill to every caller.
    """
    skills = (config or _config).skills
    return tuple(s for s in skills if authz.holds(identity, f"skill:{s.id}"))


def visible_tools(
    identity: Identity, config: Optional[McpConfig] = None
) -> Mapping[str, frozenset[str]]:
    """Server id -> the bare tool names the identity may see: the union over
    held skills. A server with no visible tool is absent. `mcp:connect` is
    not checked here (STORY-011) and withheld tools are STORY-012's."""
    cfg = config or _config
    grouped: dict[str, set[str]] = {}
    for skill in held_skills(identity, cfg):
        for tool in skill.tools:
            server, bare = split_tool(tool, cfg)
            grouped.setdefault(server, set()).add(bare)
    return MappingProxyType({s: frozenset(t) for s, t in grouped.items()})


def upstream_auth_headers(server_id: str, config: Optional[McpConfig] = None) -> dict[str, str]:
    """The southbound auth headers for one server, built only from config (D10, T2).

    The one sanctioned reader of a credential value. No inbound header is
    ever forwarded; this is the whole of what authenticates the harness.
    """
    auth = (config or _config).servers[server_id].auth
    if auth.type == "bearer":
        return {"Authorization": f"Bearer {auth._secret}"}
    if auth.type == "header":
        return {auth.header_name: auth._secret}
    return {}


# --- The digest ------------------------------------------------------------


def _canonical(config: McpConfig) -> dict:
    """The config as JSON-ready data. Env var NAMES are in, resolved values
    never are. Explicit, never `dataclasses.asdict` (which would copy `_secret`)."""
    return {
        "servers": {
            s.id: {
                "url": s.url,
                "allow_insecure": s.allow_insecure,
                "auth": {
                    "type": s.auth.type,
                    "env_name": s.auth.env_name,
                    "header_name": s.auth.header_name,
                },
                "timeout_seconds": s.timeout_seconds,
                "max_result_bytes": s.max_result_bytes,
            }
            for s in config.servers.values()
        },
        "skills": {
            k.id: {
                "version": k.version,
                "description": k.description,
                "instructions": k.instructions,
                "tools": list(k.tools),
                "requires": list(k.requires),
            }
            for k in config.skills
        },
        "v1_aliases": list(config.v1_prefixes),
    }


def mcp_config_digest(config: Optional[McpConfig] = None) -> str:
    """`sha256:<hex>` of the effective config (the one in force when None).

    Canonical JSON with sorted keys, so file comments, whitespace and key
    order do not matter. Changing only a credential's value does not change
    it; changing its env var name does."""
    canonical = json.dumps(
        _canonical(_config if config is None else config),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# --- Validation ------------------------------------------------------------


def _check_keys(source: str, where: str, body: Mapping, allowed, required=()) -> None:
    """Unknown keys, then missing keys (`action_config._check_keys`'s shape)."""
    unknown = sorted(set(body) - set(allowed), key=str)
    if unknown:
        raise _fail(
            source, where, f"unknown key {unknown[0]!r} (expected one of: {_allowed(allowed)})"
        )
    missing = sorted(set(required) - set(body))
    if missing:
        raise _fail(source, where, f"missing key {missing[0]!r} (required: {_allowed(required)})")


def _mapping(source: str, node: str, value: Any) -> Mapping:
    if not isinstance(value, Mapping):
        raise _fail(source, node, f"must be a mapping, got {type(value).__name__}")
    return value


def _string(source: str, node: str, value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise _fail(source, node, "must be a non-empty string")
    return value


def _int_in_range(source: str, node: str, value: Any, low: int, high: Optional[int]) -> int:
    # `bool` is an `int` subclass: `timeout_seconds: true` must not become 1.
    if isinstance(value, bool) or not isinstance(value, int):
        raise _fail(source, node, f"must be an integer, got {type(value).__name__}")
    if value < low or (high is not None and value > high):
        bound = f"between {low} and {high}" if high is not None else f"at least {low}"
        raise _fail(source, node, f"must be {bound}, got {value}")
    return value


def _parse_url(source: str, node: str, value: Any, allow_insecure: bool) -> str:
    url = _string(source, node, value)
    try:
        parts = urlsplit(url)
        parts.port  # noqa: B018 -- raises ValueError on a malformed port
    except ValueError as exc:
        raise _fail(source, node, f"is not a valid URL: {exc}") from exc
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise _fail(source, node, "must be an absolute http(s) URL with a host")
    if parts.username is not None or parts.password is not None or "@" in parts.netloc:
        # A credential in a URL would reach the digest, logs and errors.
        raise _fail(source, node, "must not carry credentials; use auth with an env var")
    if parts.scheme == "http" and not allow_insecure:
        raise _fail(source, node, "uses http; set allow_insecure: true to allow it, or use https")
    return url


def _env_value(source: str, node: str, name: Any) -> str:
    """Resolve a credential env var. The error names the variable, never a value."""
    name = _string(source, node, name)
    value = os.environ.get(name)
    if not value:
        raise _fail(source, node, f"environment variable {name!r} is not set or is empty")
    return value


def _parse_auth(source: str, node: str, raw: Any) -> McpAuth:
    body = _mapping(source, node, raw)
    _check_keys(source, node, body, _AUTH_KEYS)
    kind = body.get("type", "none")
    if kind not in _AUTH_TYPES:
        raise _fail(
            source, f"{node}.type", f"{kind!r} is not an auth type (allowed: {_allowed(_AUTH_TYPES)})"
        )
    wanted = {"bearer": ("token_env",), "header": ("name", "value_env"), "none": ()}[kind]
    present = set(body) - {"type"}
    for key in wanted:
        if key not in body:
            raise _fail(source, node, f"type {kind!r} requires key {key!r}")
    extra = sorted(present - set(wanted))
    if extra:
        raise _fail(source, f"{node}.{extra[0]}", f"is not used by auth type {kind!r}")
    if kind == "bearer":
        env = body["token_env"]
        secret = _env_value(source, f"{node}.token_env", env)
        return McpAuth("bearer", env_name=env, _secret=secret)
    if kind == "header":
        name = _string(source, f"{node}.name", body["name"])
        lowered = name.lower()
        if (
            not _HEADER_TOKEN.fullmatch(name)
            or lowered in _REFUSED_HEADERS
            or lowered.startswith("mcp-")
        ):
            raise _fail(
                source,
                f"{node}.name",
                f"{name!r} is not allowed as an upstream header (not a valid header name, "
                "Authorization, a hop-by-hop header or an Mcp-* header)",
            )
        env = body["value_env"]
        secret = _env_value(source, f"{node}.value_env", env)
        return McpAuth("header", env_name=env, header_name=name, _secret=secret)
    return McpAuth("none")


def _parse_server(source: str, server_id: Any, raw: Any) -> McpServer:
    node = f"servers.{server_id}"
    if not isinstance(server_id, str) or not _SERVER_ID.fullmatch(server_id):
        raise _fail(
            source,
            f"servers.{server_id}",
            f"server id {server_id!r} must match [a-z0-9][a-z0-9-]{{0,31}}",
        )
    body = _mapping(source, node, raw)
    _check_keys(source, node, body, _SERVER_KEYS, required=("url",))
    allow_insecure = body.get("allow_insecure", False)
    if not isinstance(allow_insecure, bool):
        raise _fail(source, f"{node}.allow_insecure", "must be true or false")
    url = _parse_url(source, f"{node}.url", body["url"], allow_insecure)
    auth = _parse_auth(source, f"{node}.auth", body.get("auth", {}))
    timeout = body.get("timeout_seconds", settings.MCP_CALL_TIMEOUT_SECONDS)
    timeout = _int_in_range(source, f"{node}.timeout_seconds", timeout, 1, 600)
    max_bytes = body.get("max_result_bytes", settings.MCP_MAX_RESULT_BYTES)
    max_bytes = _int_in_range(source, f"{node}.max_result_bytes", max_bytes, 1024, None)
    return McpServer(server_id, url, allow_insecure, auth, timeout, max_bytes)


def _str_list(source: str, node: str, raw: Any) -> list[str]:
    if not isinstance(raw, list):
        raise _fail(source, node, f"must be a list, got {type(raw).__name__}")
    for i, item in enumerate(raw):
        _string(source, f"{node}[{i}]", item)
    return raw


def _parse_skill(source: str, skill_id: Any, raw: Any, servers: Mapping[str, McpServer]) -> Skill:
    node = f"skills.{skill_id}"
    if not isinstance(skill_id, str) or not authz.is_skill_permission(f"skill:{skill_id}"):
        raise _fail(
            source,
            node,
            f"skill id {skill_id!r} must match [a-z0-9][a-z0-9-]{{0,47}}",
        )
    body = _mapping(source, node, raw)
    _check_keys(source, node, body, _SKILL_KEYS, required=_SKILL_REQUIRED)
    version = body["version"]
    if not isinstance(version, str) or not version:
        raise _fail(
            source,
            f"{node}.version",
            f"must be a non-empty string, got {version!r}; quote it (version: \"1.0\")",
        )
    description = _string(source, f"{node}.description", body["description"])
    instructions = _string(source, f"{node}.instructions", body["instructions"])
    tools = _str_list(source, f"{node}.tools", body["tools"])
    if not tools:
        raise _fail(source, f"{node}.tools", "must not be empty")
    for i, tool in enumerate(tools):
        try:
            split_tool(tool, McpConfig(servers=servers))
        except ValueError as exc:
            raise _fail(
                source,
                f"{node}.tools[{i}]",
                f"{exc} (a configured server id, then '__', then the tool name)",
            ) from exc
    requires = _str_list(source, f"{node}.requires", body.get("requires", []))
    for i, perm in enumerate(requires):
        if perm not in ACTION_PERMISSIONS:
            raise _fail(
                source,
                f"{node}.requires[{i}]",
                f"{perm!r} is not an action permission (allowed: {_allowed(ACTION_PERMISSIONS)})",
            )
    return Skill(skill_id, version, description, instructions, tuple(tools), tuple(requires))


def _parse_aliases(source: str, raw: Any) -> tuple[str, ...]:
    """`v1_aliases.prefixes`. Absent means no aliases: the `/v1` bridge only
    resolves prefixes the operator declared (PRD-023 Section 6.8)."""
    body = _mapping(source, "v1_aliases", raw)
    _check_keys(source, "v1_aliases", body, _ALIAS_KEYS)
    prefixes = _str_list(source, "v1_aliases.prefixes", body.get("prefixes", []))
    for i, prefix in enumerate(prefixes):
        if not _PREFIX.fullmatch(prefix):
            raise _fail(
                source,
                f"v1_aliases.prefixes[{i}]",
                f"{prefix!r} must be non-empty and use only [A-Za-z0-9_-]",
            )
    if len(set(prefixes)) != len(prefixes):
        raise _fail(source, "v1_aliases.prefixes", "must not repeat a prefix")
    return tuple(prefixes)


def _parse_document(source: str, document: Any) -> McpConfig:
    body = _mapping(source, "file", document)
    _check_keys(source, "file", body, _TOP_KEYS)
    raw_servers = _mapping(source, "servers", body.get("servers", {}))
    servers = {sid: _parse_server(source, sid, raw) for sid, raw in raw_servers.items()}
    servers_view = MappingProxyType(servers)
    raw_skills = _mapping(source, "skills", body.get("skills", {}))
    skills = tuple(_parse_skill(source, sid, raw, servers_view) for sid, raw in raw_skills.items())
    prefixes = _parse_aliases(source, body["v1_aliases"]) if "v1_aliases" in body else ()
    return McpConfig(servers_view, skills, prefixes)


def _cross_validate(source: str, config: McpConfig) -> None:
    """Against the loaded action policy, then the loaded role matrix (PRD-023 Section 9.3, O2)."""
    policy = action_config.get_policy()
    for skill in config.skills:
        for i, tool in enumerate(skill.tools):
            server, bare = split_tool(tool, config)
            if bare not in policy.mcp_tools.get(server, {}) and bare not in (
                policy.mcp_opaque_tools.get(server, {})
            ):
                raise _fail(
                    source,
                    f"skills.{skill.id}.tools[{i}]",
                    f"{tool!r} has no mcp_tools or mcp_opaque_tools entry in ACTION_POLICY_FILE",
                )
    for section in (policy.mcp_tools, policy.mcp_opaque_tools):
        for server in section:
            if server not in config.servers:
                raise _fail(
                    source,
                    f"ACTION_POLICY_FILE {'mcp_tools' if section is policy.mcp_tools else 'mcp_opaque_tools'}.{server}",
                    f"server {server!r} is not defined under servers",
                )
    by_id = {s.id: s for s in config.skills}
    for role in sorted(authz.ROLE_PERMISSIONS):
        held = authz.ROLE_PERMISSIONS[role]
        for permission in sorted(p for p in held if p.startswith("skill:")):
            skill = by_id.get(permission[len("skill:") :])
            if skill is None:
                raise _fail(
                    source,
                    f"roles.{role}",
                    f"{permission!r} names a skill that is not defined under skills",
                )
            for needed in skill.requires:
                if needed not in held:
                    raise _fail(
                        source,
                        f"roles.{role}",
                        f"holds {permission!r} but not {needed!r}, which skill "
                        f"{skill.id!r} requires; grant it or remove the skill",
                    )


def load() -> None:
    """Read `MCP_CONFIG_FILE` and put its config in force, or fail startup.

    `MCP_ENABLED=false`: nothing is read, nothing is validated, and the empty
    config is put in force (an assignment, no I/O) so a config loaded earlier
    in the same process cannot leak. Enabled with an empty `MCP_CONFIG_FILE`
    is an error: a deployment that thinks the gateway is configured and is
    not is the failure this exception exists to prevent.

    Otherwise every check passes before `_config` is rebound, which is the
    last statement: a file that fails, at any rule, leaves the previous
    config intact (`action_config.load()`'s shape). Settings are read here,
    at call time, never at import. `strict_yaml.safe_load` only: a key
    written twice is an error, not "the last one wins" (D13).

    Run after `action_config.load()` and `authz.load()`: it cross-validates
    against both.
    """
    global _config

    if not settings.MCP_ENABLED:
        _config = EMPTY_CONFIG
        return

    path = settings.MCP_CONFIG_FILE
    if not path:
        raise _fail(
            "MCP_CONFIG_FILE",
            "setting",
            "MCP_ENABLED is true but MCP_CONFIG_FILE is empty; set a path or MCP_ENABLED=false",
        )

    source = f"MCP_CONFIG_FILE '{path}'"
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise _fail(source, "file", f"cannot be read: {exc}") from exc

    try:
        document = strict_yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise _fail(source, "file", f"is not valid YAML: {exc}") from exc

    config = _parse_document(source, document)
    _cross_validate(source, config)

    for skill in config.skills:
        for tool in skill.tools:
            if len(tool) > _CLINE_NAME_LIMIT:
                logger.warning(
                    "MCP skill %r tool %r is %d characters long (over %d): Cline hashes such a "
                    "name and the /v1 bridge cannot resolve it; it is reachable through /mcp only",
                    skill.id,
                    tool,
                    len(tool),
                    _CLINE_NAME_LIMIT,
                )

    _config = config
