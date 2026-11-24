"""PRD-023 STORY-019: the MCP decision corpus, its loader and its fixed setup (F12, Section 11).

`tests/corpora/mcp/calls/*.yaml`, one gateway call per file in the PRD-016 corpus
shape plus `server:` (format: `tests/corpora/mcp/SOURCES.md`, "Decision corpus
format"). Shared by `tests/test_mcp_corpus.py` (the runners) and STORY-020 (the
real clients replay the files that are not marked `e2e: false`).

The loader reuses `CorpusError`, `_one_of`, `_tool_call` and `_CLIENTS` from
`tests/test_action_corpus.py`; it does not reuse `_load_case` or `_ROLES`, which
are tied to `corpora/actions/` and the roles `user/dba/admin`. The corpus roles
here are `user`, `dev` and `dba`, and they exist only in `configure()`'s
monkeypatched matrix: STORY-020 must create equivalent roles.

Loaded where it is imported (`load_corpus()`): a malformed file fails collection
naming the file and the node.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Optional

import yaml

from app.config import settings
from app.services import (
    action_config,
    authz,
    mcp_config,
    mcp_gateway,
    mcp_upstream,
    pattern_config,
    strict_json,
    strict_yaml,
)
from app.services.action_classifiers import DECISIONS, RULE_IDS
from app.services.identity import Identity
from app.services.mcp_config import McpAuth, McpConfig, McpServer, Skill
from tests.test_action_corpus import CorpusError, _CLIENTS, _one_of, _tool_call

CALLS = Path(__file__).resolve().parent / "corpora" / "mcp" / "calls"

SERVER = "stub"
SKILL_ID = "open-pull-request"
#: The bare tools of the stub that the skill lists. `create_branch` is deliberately
#: absent (hidden); `nope` is not on the stub (listed by the skill, absent upstream);
#: `poisoned` is on the stub with an injection in its description (withheld).
SKILL = Skill(
    SKILL_ID, "1.0.0", "d", "i",
    tuple(
        f"{SERVER}__{tool}"
        for tool in (
            "query", "push_files", "create_pull_request", "slow", "huge", "inject", "nope", "poisoned"
        )
    ),
    (),
)
POLICY = """\
mcp_tools:
  stub:
    query: {kind: sql, target: sql}
    push_files: {kind: fs_write, target: "files[].path"}
mcp_opaque_tools:
  stub:
    create_pull_request: flag
    slow: allow
    huge: allow
    inject: allow
"""
#: Server `timeout_seconds` and `max_result_bytes` of the matrix: `slow seconds=20` times out
#: and `huge size=5000` is over the cap.
TIMEOUT_SECONDS = 2
MAX_RESULT_BYTES = 2048
V1_PREFIXES = ("harness_", "harness__")

ROLES = ("user", "dev", "dba")
IDENTITIES: Mapping[str, Identity] = MappingProxyType(
    {role: Identity(user_id=f"u-{role}", role=role) for role in ROLES}
)
#: A second user of the same role: the prior `/v1` row of another caller (correlation).
OTHER_USER = Identity(user_id="u-other", role="dev")
#: The JSON-RPC id of a call by role, so a row's `tool_call_id` is `mcp:<id>` and short enough
#: for the 64-character note fields.
JSONRPC_IDS: Mapping[str, int] = MappingProxyType({"user": 1, "dev": 2, "dba": 3})

CATEGORIES = ("brief", "outcome", "visibility", "alias", "correlation")
OUTCOMES = ("ok", "tool_error", "upstream_error", "timeout", "result_too_large", "result_blocked")
VIA = ("mcp", "v1")
PATTERN_MODES = ("flag", "block")
RBAC_MODES = ("enabled", "disabled")
FAULTS = ("tool_error", "upstream_error", "image_result")
PRIOR_USERS = ("same", "other")

_REQUIRED = frozenset({"tool_call", "server", "category", "expect", "outcome", "rule", "note"})
_OPTIONAL = frozenset(
    {"via", "client", "granted_by", "flags", "patterns", "rbac", "fault", "prior", "window_seconds", "linked", "e2e"}
)
_PRIOR_KEYS = frozenset({"user", "name", "arguments", "age_seconds", "audit"})
_PRIOR_OPTIONAL = frozenset({"decision"})

_BLOCK_PATTERNS = """\
lists:
  injection:
    match: word
    scope: everywhere
    patterns:
      - forget everything
      - ignore previous instructions
profiles:
  chat:
    lists: [injection]
    roles:
      user: block
  code:
    lists: [injection]
    roles:
      user: block
      tool: block
"""


@dataclass(frozen=True)
class Prior:
    """The `/v1` alias row a correlation case seeds before the gateway call."""

    user: str
    name: str
    arguments: str
    age_seconds: int
    audit: bool
    decision: Optional[str]


@dataclass(frozen=True)
class Case:
    path: Path
    name: str  # northbound name (`stub__query`), or the raw `/v1` name for `via: v1`
    arguments: str  # JSON-object text, as the file wrote it
    server: Optional[str]
    category: str
    via: str
    client: Optional[str]
    expect: Mapping[str, str]
    outcome: Mapping[str, Optional[str]]
    rule: Mapping[str, str]
    granted_by: Mapping[str, str]
    flags: Optional[tuple]
    patterns: str
    rbac: str
    fault: Optional[str]
    prior: Optional[Prior]
    window_seconds: int
    linked: Optional[bool]
    e2e: bool
    note: str

    @property
    def stem(self) -> str:
        return self.path.stem

    @property
    def roles(self) -> tuple[str, ...]:
        return tuple(self.expect)

    def arguments_object(self) -> dict:
        return json.loads(self.arguments)


def _roles_of(name: str, node: str, value: Any, *, nonempty: bool = True) -> dict:
    if not isinstance(value, dict) or (nonempty and not value):
        raise CorpusError(name, node, "must be a non-empty mapping of role to value")
    for role in value:
        _one_of(name, node, role, ROLES)
    return value


def _arguments_text(name: str, node: str, text: str) -> str:
    """The text must be one JSON object (a strict parse: duplicate keys are refused)."""
    try:
        parsed = strict_json.loads(text)
    except Exception as exc:  # noqa: BLE001 - re-raised as the corpus error naming the node
        raise CorpusError(name, node, f"not valid JSON: {type(exc).__name__}") from exc
    if not isinstance(parsed, dict):
        raise CorpusError(name, node, "must be the text of a JSON object")
    return text


def _flags(name: str, value: Any) -> tuple:
    if not isinstance(value, list):
        raise CorpusError(name, "flags", "must be a list")
    for index, flag in enumerate(value):
        if not isinstance(flag, (dict, str)):
            raise CorpusError(name, f"flags[{index}]", "must be a mapping or a string")
    return tuple(value)


def _prior(name: str, value: Any) -> Prior:
    if not isinstance(value, dict):
        raise CorpusError(name, "prior", "must be a mapping")
    unknown = set(value) - _PRIOR_KEYS - _PRIOR_OPTIONAL
    if unknown:
        raise CorpusError(name, "prior", f"unknown key {sorted(map(str, unknown))[0]}")
    missing = _PRIOR_KEYS - set(value)
    if missing:
        raise CorpusError(name, f"prior.{sorted(missing)[0]}", "required key is missing")
    user = _one_of(name, "prior.user", value["user"], PRIOR_USERS)
    if not isinstance(value["name"], str) or not value["name"]:
        raise CorpusError(name, "prior.name", "must be a non-empty string")
    if not isinstance(value["arguments"], str):
        raise CorpusError(name, "prior.arguments", "must be a string (the text of a JSON object)")
    arguments = _arguments_text(name, "prior.arguments", value["arguments"])
    age = value["age_seconds"]
    if isinstance(age, bool) or not isinstance(age, int) or age < 0:
        raise CorpusError(name, "prior.age_seconds", "must be a non-negative integer")
    if not isinstance(value["audit"], bool):
        raise CorpusError(name, "prior.audit", "must be true or false")
    decision = value.get("decision")
    if decision is not None:
        _one_of(name, "prior.decision", decision, DECISIONS)
    return Prior(user, value["name"], arguments, age, value["audit"], decision)


def load_case(path: Path) -> Case:
    """Parse and check one call file; every violation is a `CorpusError` naming the file and the node."""
    name = path.name
    try:
        document = strict_yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise CorpusError(name, "file", f"not valid YAML: {exc}") from exc
    if not isinstance(document, dict):
        raise CorpusError(name, "file", "must be a mapping")

    keys = set(document)
    unknown = keys - _REQUIRED - _OPTIONAL
    if unknown:
        raise CorpusError(name, str(sorted(map(str, unknown))[0]), "unknown key")
    missing = _REQUIRED - keys
    if missing:
        raise CorpusError(name, sorted(missing)[0], "required key is missing")

    call = _tool_call(name, "tool_call", document["tool_call"])
    arguments = _arguments_text(name, "tool_call.arguments", call.arguments)
    server = document["server"]
    if server is not None and server != SERVER:
        raise CorpusError(name, "server", f"{server!r} is not {SERVER!r} or null")
    category = _one_of(name, "category", document["category"], CATEGORIES)
    via = _one_of(name, "via", document.get("via", "mcp"), VIA)
    client = document.get("client")
    if client is not None:
        _one_of(name, "client", client, _CLIENTS)

    expect = _roles_of(name, "expect", document["expect"])
    for role, decision in expect.items():
        _one_of(name, f"expect.{role}", decision, DECISIONS)
    outcome = _roles_of(name, "outcome", document["outcome"])
    if set(outcome) != set(expect):
        raise CorpusError(name, "outcome", "must name exactly the roles of expect")
    for role, value in outcome.items():
        if value is not None:
            _one_of(name, f"outcome.{role}", value, OUTCOMES)
        if value is not None and expect[role] == "deny":
            raise CorpusError(name, f"outcome.{role}", "a denied call is never forwarded: must be null")

    rule = document["rule"]
    if isinstance(rule, str):
        rule = {role: rule for role in expect}
    rule = _roles_of(name, "rule", rule)
    if set(rule) != set(expect):
        raise CorpusError(name, "rule", "must name exactly the roles of expect")
    for role, rule_id in rule.items():
        _one_of(name, f"rule.{role}", rule_id, RULE_IDS)

    granted_by = document.get("granted_by", {})
    _roles_of(name, "granted_by", granted_by, nonempty=False)
    for role, permission in granted_by.items():
        if expect.get(role) != "allow":
            raise CorpusError(name, f"granted_by.{role}", "must name a role whose expected decision is allow")
        _one_of(name, f"granted_by.{role}", permission, authz.ACTION_PERMISSIONS)

    flags = _flags(name, document["flags"]) if "flags" in document else None
    patterns = _one_of(name, "patterns", document.get("patterns", "flag"), PATTERN_MODES)
    rbac = _one_of(name, "rbac", document.get("rbac", "enabled"), RBAC_MODES)
    fault = document.get("fault")
    if fault is not None:
        _one_of(name, "fault", fault, FAULTS)

    prior = _prior(name, document["prior"]) if "prior" in document else None
    window = document.get("window_seconds", 300)
    if isinstance(window, bool) or not isinstance(window, int) or window < 0:
        raise CorpusError(name, "window_seconds", "must be a non-negative integer")
    linked = document.get("linked")
    if linked is not None and not isinstance(linked, bool):
        raise CorpusError(name, "linked", "must be true or false")
    if category == "correlation":
        if linked is None:
            raise CorpusError(name, "linked", "a correlation call declares linked (prior may be absent)")
        if via != "mcp" or set(expect) != {"dev"}:
            raise CorpusError(name, "expect", "a correlation call is a gateway call by dev")
    elif prior is not None or linked is not None:
        raise CorpusError(name, "prior", "only a correlation call has prior and linked")
    if via == "v1" and any(v is not None for v in outcome.values()):
        raise CorpusError(name, "outcome", "a v1 call is decided at step 7c and never forwarded: must be null")
    e2e = document.get("e2e", True)
    if not isinstance(e2e, bool):
        raise CorpusError(name, "e2e", "must be true or false")

    note = document["note"]
    if not isinstance(note, str) or not note.strip():
        raise CorpusError(name, "note", "must be a non-empty string")

    return Case(
        path=path, name=call.name, arguments=arguments, server=server, category=category, via=via,
        client=client, expect=MappingProxyType(dict(expect)), outcome=MappingProxyType(dict(outcome)),
        rule=MappingProxyType(dict(rule)), granted_by=MappingProxyType(dict(granted_by)), flags=flags,
        patterns=patterns, rbac=rbac, fault=fault, prior=prior, window_seconds=window, linked=linked,
        e2e=e2e, note=note,
    )


def load_corpus(directory: Path = CALLS) -> list[Case]:
    """Every `calls/*.yaml`, sorted. A missing directory raises (a loud failure at collection)."""
    return [load_case(path) for path in sorted(directory.glob("*.yaml"))] if directory.is_dir() else _missing(directory)


def _missing(directory: Path):
    raise FileNotFoundError(f"MCP corpus directory not found: {directory}")


# --- the flags of a result, in both recorded shapes ---------------------------------


def normalise_flags(flags) -> list[tuple]:
    """A comparable, sorted form of `result_flags`, whichever shape wrote it (STORY-014).

    `_inspect_result` hits are `{"list": "injection", "pattern_id": N}`; `_screen_result`
    adds `{"uninspected": N}`; `record_outcome`'s signature also admits plain strings. Works on
    the recorded tuple/list and on `json.loads(row["result_flags"])` (`None` is no flags).
    """
    out = []
    for flag in flags or ():
        if isinstance(flag, str):
            out.append(("flag", flag))
        elif isinstance(flag, dict) and "uninspected" in flag:
            out.append(("uninspected", flag["uninspected"]))
        elif isinstance(flag, dict) and "list" in flag:
            out.append(("list", flag["list"], flag.get("pattern_id")))
        else:
            raise AssertionError(f"unknown result_flags shape: {flag!r}")
    return sorted(out, key=repr)


# --- the fixed setup ---------------------------------------------------------------


def configure(
    monkeypatch, tmp_path, url: str, *, rbac: str = "enabled", patterns: str = "flag",
    prefixes: tuple[str, ...] = (), mcp_enabled: bool = False,
) -> None:
    """The matrix every corpus call runs in: server `stub`, skill `open-pull-request`, the policy
    sections for it and the roles `user`, `dev`, `dba` (`dba` = dev + `action:sql:ddl`).

    Everything goes through `monkeypatch`, so teardown restores it; the caller resets
    `mcp_upstream` state and the tools cache (the `_fresh` fixture of `tests/test_mcp_tools_call.py`).
    """
    monkeypatch.setattr(settings, "RBAC_ENABLED", rbac == "enabled")
    monkeypatch.setattr(settings, "USAGE_LIMITS_ENABLED", True)
    monkeypatch.setattr(settings, "MCP_ALLOWED_ORIGINS", "")
    monkeypatch.setattr(settings, "MCP_ENABLED", mcp_enabled)
    if rbac == "enabled":
        monkeypatch.setattr(
            authz, "ROLE_PERMISSIONS",
            {
                "dev": {f"skill:{SKILL_ID}", "mcp:connect"},
                "dba": {f"skill:{SKILL_ID}", "mcp:connect", authz.PERMISSION_ACTION_SQL_DDL},
                "user": {"mcp:connect"},
            },
        )
    # `rbac: disabled` keeps the built-in matrix (PRD Section 11: "with RBAC_ENABLED=false and the
    # built-in matrix" the catalogue is empty). `held_skills` reads the matrix, not `authorize`, so a
    # matrix that grants the skill would still show it with RBAC off.
    policy_file = tmp_path / "action_policy.yaml"
    policy_file.write_text(POLICY, encoding="utf-8")
    monkeypatch.setattr(action_config, "_policy", action_config._policy)  # restored at teardown
    monkeypatch.setattr(settings, "ACTION_POLICY_FILE", str(policy_file))
    action_config.load()
    server = McpServer(SERVER, url, True, McpAuth(type="none"), TIMEOUT_SECONDS, MAX_RESULT_BYTES)
    monkeypatch.setattr(
        mcp_config, "_config",
        McpConfig(servers={SERVER: server}, skills=(SKILL,), v1_prefixes=tuple(prefixes)),
    )
    if patterns == "block":
        patterns_file = tmp_path / "patterns.yaml"
        patterns_file.write_text(_BLOCK_PATTERNS, encoding="utf-8")
        monkeypatch.setattr(pattern_config, "_policy", pattern_config._policy)  # restored at teardown
        monkeypatch.setattr(settings, "PATTERNS_FILE", str(patterns_file))
        monkeypatch.setattr(settings, "PATTERN_PROFILE_DEFAULT", "chat")
        pattern_config.load()
    monkeypatch.setattr(mcp_upstream, "_state", None)
    mcp_upstream.invalidate_tools_cache()
    mcp_gateway._unlisted_logged.clear()


def reply_kind(case: Case, role: str) -> str:
    """What the agent receives, derived from the declared decision, rule and outcome (never declared).

    `not_callable` is JSON-RPC -32602; `denied` an `isError` result with the denial note; the
    others the harness texts of `mcp_gateway`; `result` the upstream result as it came.
    """
    if case.rule[role] == "tool.not_in_skill":
        return "not_callable"
    if case.expect[role] == "deny":
        return "denied"
    return {
        "timeout": "timeout", "upstream_error": "upstream_error", "result_too_large": "too_large",
        "result_blocked": "blocked",
    }.get(case.outcome[role], "result")
