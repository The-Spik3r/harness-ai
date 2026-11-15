"""The action policy: where it comes from, and what stops the boot (PRD-016 Sections 4, 6.12).

This module owns **all** of the configuration I/O behind action policy rules.
`action_adapters`, `action_classifiers/*` and `action_policy` stay pure -- they
read no setting and open no file -- and everything that needs a setting, a
file or the policy in force lives here (PRD-016 Section 6.12).

Three entry points (PRD-016 Section 10):

- `load()` reads `ACTION_POLICY_FILE`. An empty setting reads no file at all
  and the built-in policy stands.
- `get_policy()` returns whatever is in force, and returns the built-in policy
  when `load()` has never run -- `pattern_config.get_policy()`'s contract,
  exactly.
- `policy_digest()` is the SHA-256 of the effective policy, stamped on every
  `ActionDecision` and audit row so a decision can be traced to the policy
  that made it (PRD-016 Sections 4, 6.2).

Called once at startup in **both** lifespans (`app/main.py` and
`chat_ui/chat_ui/chat_ui.py`): the Reflex `api_transformer` mount bypasses the
former entirely, which is why `authz.load()` and `pattern_config.load()` are
already registered twice (PRD-016 Section 6.12). Never per request: every glob
is compiled here, once.

The built-in policy is built through the same `_validate` a policy file will
go through, so the floor cannot drift into a shape a file would be refused
for (PRD-016 F8).

STORY-006 covers the built-in policy, the digest, and `load()` with the
setting empty. What is deliberately **not** here yet: reading and parsing the
file, the per-id `rules:` merge, the wholesale sections and the rest of
Section 9.3's file validation (STORY-007), and the `ACTION_SQL_DIALECT`
cross-check (STORY-008).
"""

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from types import MappingProxyType
from typing import Any, Mapping, Optional

from app.config import settings
from app.services.action_adapters import BUILT_IN_TOOLS, ToolMapping
from app.services.action_classifiers import (
    DECISIONS,
    NON_GRANTABLE_RULES,
    RULE_IDS,
    Decision,
    RuleId,
)
from app.services.authz import (
    ACTION_PERMISSIONS,
    PERMISSION_ACTION_FS_WRITE,
    PERMISSION_ACTION_NET_EGRESS,
    PERMISSION_ACTION_SECRET_READ,
    PERMISSION_ACTION_SHELL_EXEC,
    PERMISSION_ACTION_SQL_DDL,
    PERMISSION_ACTION_SQL_WRITE,
)


class ActionConfigError(Exception):
    """Raised for every way the action policy can be wrong (PRD-016 Section 9.3).

    Checked by `_validate` from STORY-006 on, for the built-in policy and for a
    file alike: a rule missing or unknown, a `default` outside allow/flag/deny,
    a `grant` that is not an action permission, a `grant` on one of the ten
    non-grantable rules (T5), a `default` on `tool.opaque`, an empty `tools:`
    (T7), a tool mapping that is not a `ToolMapping`, an `opaque_tools` entry
    with a bad decision or a name also in `tools`, and a glob that cannot be
    translated.

    Added by STORY-007: `ACTION_POLICY_FILE` unreadable or unparseable, a
    mapping key written twice (D13), an unknown key at any level, a
    `workspace.roots` entry that is not absolute, a malformed `network.allow`
    entry, a `shell.allow` entry with an operator. STORY-008 adds an
    `ACTION_SQL_DIALECT` outside the supported set.

    Startup fails. There is never a silent fallback to the built-in policy --
    a deployment that thinks it is running its own policy and is not is the
    failure this exception exists to prevent (PRD-016 Sections 4, 6.12).

    It is also the outer half of a two-exception seam. `ToolMapping(...)`
    raises `action_adapters.ToolMappingError`, which cannot name a file or a
    tool because `action_adapters` is pure; STORY-007 catches it and re-raises
    this with the file and the `tools.<name>` node attached -- the error an
    operator actually reads at startup.
    """


# --- The model -------------------------------------------------------------


@dataclass(frozen=True)
class Rule:
    """One rule's default decision and the permission that lifts it (PRD-016 Section 6.3).

    `grant` names one of `authz.ACTION_PERMISSIONS`. A role holding it gets
    `allow` for this rule instead of `default`. A rule with no grant cannot be
    lifted by any role: the ten `NON_GRANTABLE_RULES` never take one (T5), and
    the allow-by-default rules have nothing to lift.

    `default` is `None` on `tool.opaque` and only there. Section 6.3 gives it
    the default "(per entry)": its decision is the `opaque_tools` entry's
    (`action_adapters.Opaque.decision`), and no `rules:` value applies to it.
    `_validate` enforces that shape, so every other rule's `default` is a
    `Decision` (STORY-006 plan, decision 3).
    """

    default: Optional[Decision]
    grant: Optional[str]


@dataclass(frozen=True)
class Globs:
    """A list of globs and their compiled forms, positional parallels (`PatternList`'s shape).

    `compiled[i]` is `patterns[i]`. Both are tuples: declared order is part of
    the policy, and the digest keeps it.

    The match contract (STORY-006 plan, decision 6), which STORY-011 and
    STORY-013 consume:

    - **Path globs** (`protected_paths`, `secrets.files`) are compiled as
      ``(?:^|/)<body>$``. Call `.search()` on a normalized, `/`-separated path.
      A glob therefore matches at any depth: `.env*` matches
      `/home/dev/projects/app/.env.local`, and `.git/**` matches `.git/config`
      and `a/.git/HEAD`, because a `.env` inside `app/` is still a `.env`.
    - **Name globs** (`secrets.env`) are compiled as ``^<body>$`` and contain
      no `/`. `.search()` and `.fullmatch()` agree, since both ends are
      anchored.

    Every glob is case-insensitive. T6 asks it of protected paths (a
    case-insensitive filesystem opens `.ENV` as `.env`); secret files and env
    names follow, because matching more only adds denials, so it fails closed.
    """

    patterns: tuple[str, ...]
    #: Built once, here, never at request time.
    compiled: tuple[re.Pattern, ...]


@dataclass(frozen=True)
class Secrets:
    """The `secrets:` section: env-variable name globs and file globs (PRD-016 Section 6.6)."""

    env: Globs
    files: Globs


@dataclass(frozen=True)
class ActionPolicy:
    """Everything in force at once (PRD-016 Sections 6.3, 6.6).

    `rules`, `tools` and `opaque_tools` are `MappingProxyType`s and the lists
    are tuples, so the built-in policy cannot be edited in place -- `frozen`
    alone stops reassignment, not mutation.

    `shell_allow`, `network_allow` and `workspace_roots` are empty in the
    built-in policy (PRD-016 Section 6.5): no command is allowlisted, no host
    is reachable, and no directory is a workspace until a deployment says so.
    With no workspace, every write is outside it.

    `protected_paths` is built-in only in PRD-016: Sections 6.6 and 9.3 give
    it no file section (STORY-006 plan, decision 4).
    """

    rules: Mapping[RuleId, Rule]
    tools: Mapping[str, ToolMapping]
    opaque_tools: Mapping[str, Decision]
    shell_allow: tuple[str, ...]
    network_allow: tuple[str, ...]
    workspace_roots: tuple[str, ...]
    protected_paths: Globs
    secrets: Secrets


# --- Globs -----------------------------------------------------------------
#
# Python 3.12 has no `glob.translate` (3.13), and `fnmatch` lets `*` cross
# `/`, so the module translates its own small syntax: literal characters, `*`
# (any run within one segment), `?` (one non-`/` character), and `**` as a
# whole segment (zero or more segments when it is not last, one or more when
# it is). Character classes and escapes are refused rather than supported:
# they would be a second syntax to explain, and none of PRD-016's globs needs
# one.


class _GlobError(ValueError):
    """A glob outside the supported syntax. Only `_validate` sees it; it
    re-raises `ActionConfigError` naming the node."""


_GLOB_FORBIDDEN = frozenset("[]\\")


def _translate_segment(segment: str) -> str:
    out = []
    for char in segment:
        if char == "*":
            out.append("[^/]*")
        elif char == "?":
            out.append("[^/]")
        else:
            out.append(re.escape(char))
    return "".join(out)


def _translate_glob(glob: str) -> str:
    """The regex body for one glob, unanchored. Raises `_GlobError`."""
    if not isinstance(glob, str):
        raise _GlobError(f"must be a string, got {type(glob).__name__}")
    if not glob:
        raise _GlobError("empty glob")
    bad = sorted(set(glob) & _GLOB_FORBIDDEN)
    if bad:
        raise _GlobError(
            f"unsupported character(s) {' '.join(bad)} (supported: literal characters, *, ?, **)"
        )
    if glob.startswith("/"):
        raise _GlobError("must not start with '/': globs match at any depth")
    segments = glob.split("/")
    if any(not segment for segment in segments):
        raise _GlobError("empty path segment")
    parts = []
    for index, segment in enumerate(segments):
        last = index == len(segments) - 1
        if segment == "**":
            # Not last: zero or more whole segments, and it swallows its own
            # trailing `/`. Last: one or more, after the preceding `/`.
            parts.append("[^/]+(?:/[^/]+)*" if last else "(?:[^/]+/)*")
            continue
        if "**" in segment:
            raise _GlobError("'**' must be a whole path segment")
        parts.append(_translate_segment(segment) + ("" if last else "/"))
    return "".join(parts)


def _compile_path_glob(glob: str) -> re.Pattern:
    return re.compile("(?:^|/)" + _translate_glob(glob) + "$", re.IGNORECASE)


def _compile_name_glob(glob: str) -> re.Pattern:
    if isinstance(glob, str) and "/" in glob:
        raise _GlobError("a name glob must not contain '/'")
    return re.compile("^" + _translate_glob(glob) + "$", re.IGNORECASE)


# --- The built-in policy ---------------------------------------------------

#: PRD-016 Section 6.3, in `RULE_IDS` order: (default, grant). Nine granted,
#: ten non-grantable, six with nothing to lift.
_BUILT_IN_RULES: Mapping[str, tuple[Optional[str], Optional[str]]] = MappingProxyType(
    {
        "sql.read": ("allow", None),
        "sql.write": ("deny", PERMISSION_ACTION_SQL_WRITE),
        "sql.unscoped_write": ("deny", None),
        "sql.ddl": ("deny", PERMISSION_ACTION_SQL_DDL),
        "sql.dcl": ("deny", None),
        "sql.unparsed": ("deny", None),
        "shell.allowlisted": ("allow", None),
        "shell.unlisted": ("deny", PERMISSION_ACTION_SHELL_EXEC),
        "shell.destructive": ("deny", None),
        "shell.pipe_to_interpreter": ("deny", None),
        "shell.inline_interpreter": ("deny", PERMISSION_ACTION_SHELL_EXEC),
        "shell.package_install": ("deny", PERMISSION_ACTION_SHELL_EXEC),
        "shell.service_control": ("deny", PERMISSION_ACTION_SHELL_EXEC),
        "shell.unclassifiable": ("deny", None),
        "fs.read": ("allow", None),
        "fs.write_in_workspace": ("allow", None),
        "fs.write_outside_workspace": ("deny", PERMISSION_ACTION_FS_WRITE),
        "fs.write_protected": ("deny", None),
        "net.allowlisted": ("allow", None),
        "net.unlisted": ("deny", PERMISSION_ACTION_NET_EGRESS),
        "net.unparsed": ("deny", None),
        "secret.read": ("deny", PERMISSION_ACTION_SECRET_READ),
        "tool.unknown": ("deny", None),
        # "(per entry)": the opaque_tools entry decides (see `Rule`).
        "tool.opaque": (None, None),
        "tool.malformed": ("deny", None),
    }
)

#: PRD-016 Section 6.3, the `fs.write_protected` row, in table order.
_BUILT_IN_PROTECTED_PATHS = (
    ".env*",
    "*.pem",
    "*.key",
    # Also matches e.g. `src/id_utils.py`: kept as the PRD writes it, because
    # over-matching only denies a write (STORY-006 plan, decision 6).
    "id_*",
    ".aws/**",
    ".ssh/**",
    ".git/**",
    ".github/workflows/**",
    ".gitlab-ci.yml",
    "Jenkinsfile",
    ".circleci/**",
)

#: PRD-016 Section 6.3, the `secret.read` row (seven, in table order). The
#: Section 6.6 sample shows six because it is a deployment example and omits
#: `OPENROUTER_*`; the built-in policy keeps the gateway's own key covered.
_BUILT_IN_SECRET_ENV = (
    "*KEY*",
    "*SECRET*",
    "*TOKEN*",
    "*PASSWORD*",
    "*CREDENTIAL*",
    "AWS_*",
    "OPENROUTER_*",
)

#: PRD-016 Section 6.6's `secrets.files` (Section 6.3 gives no file list).
_BUILT_IN_SECRET_FILES = (
    ".env*",
    "*.pem",
    "*.key",
    "id_*",
    ".aws/**",
    ".ssh/**",
    ".npmrc",
    ".pypirc",
)

_BUILT_IN_SOURCE = "built-in action policy"


# --- Validation ------------------------------------------------------------
#
# Every message names the source (the built-in policy, or STORY-007's file),
# the offending node in YAML node-path form, and the rule that failed, and
# enumerates the allowed values where there is a closed set -- the shape
# `pattern_config` uses.


def _fail(source: str, *parts: str) -> ActionConfigError:
    return ActionConfigError(f"{source}: " + ": ".join(parts))


def _allowed(values) -> str:
    return ", ".join(sorted(values))


_SPEC_KEYS = frozenset(
    {
        "rules",
        "tools",
        "opaque_tools",
        "shell_allow",
        "network_allow",
        "workspace_roots",
        "protected_paths",
        "secret_env",
        "secret_files",
    }
)


def _validate_rules(source: str, rules: Any) -> Mapping[RuleId, Rule]:
    if not isinstance(rules, Mapping):
        raise _fail(source, "rules", f"must be a mapping, got {type(rules).__name__}")
    unknown = sorted(set(rules) - set(RULE_IDS), key=str)
    if unknown:
        raise _fail(
            source,
            "rules",
            f"{unknown[0]!r}",
            f"unknown rule (allowed: {_allowed(RULE_IDS)})",
        )
    missing = [rule_id for rule_id in RULE_IDS if rule_id not in rules]
    if missing:
        raise _fail(
            source,
            "rules",
            f"missing rule(s) {', '.join(missing)} (every rule must be present: "
            f"{_allowed(RULE_IDS)})",
        )

    built = {}
    for rule_id in RULE_IDS:
        node = f"{rule_id!r}"
        value = rules[rule_id]
        if not isinstance(value, tuple) or len(value) != 2:
            raise _fail(source, "rules", node, "must be a (default, grant) pair")
        default, grant = value
        if rule_id == "tool.opaque":
            if default is not None:
                raise _fail(
                    source,
                    "rules",
                    node,
                    f"default {default!r} is not allowed: the decision is each "
                    "opaque_tools entry's (PRD-016 Section 6.3)",
                )
            if grant is not None:
                raise _fail(
                    source,
                    "rules",
                    node,
                    f"grant {grant!r} is not allowed: the decision is each "
                    "opaque_tools entry's (PRD-016 Section 6.3)",
                )
            built[rule_id] = Rule(None, None)
            continue
        if default not in DECISIONS:
            raise _fail(
                source,
                "rules",
                node,
                f"default {default!r} is not a decision (allowed: {_allowed(DECISIONS)})",
            )
        if grant is not None:
            if grant not in ACTION_PERMISSIONS:
                raise _fail(
                    source,
                    "rules",
                    node,
                    f"grant {grant!r} is not an action permission "
                    f"(allowed: {_allowed(ACTION_PERMISSIONS)})",
                )
            if rule_id in NON_GRANTABLE_RULES:
                raise _fail(
                    source,
                    "rules",
                    node,
                    f"grant {grant!r} is not allowed on a non-grantable rule "
                    f"(non-grantable: {_allowed(NON_GRANTABLE_RULES)})",
                )
        built[rule_id] = Rule(default, grant)
    return MappingProxyType(built)


def _validate_tools(source: str, tools: Any) -> Mapping[str, ToolMapping]:
    if not isinstance(tools, Mapping):
        raise _fail(source, "tools", f"must be a mapping, got {type(tools).__name__}")
    if not tools:
        # T7: an empty `tools:` would turn every call into tool.unknown -- safe,
        # but a policy nobody meant to write.
        raise _fail(source, "tools", "must not be empty (PRD-016 T7)")
    for name, mapping in tools.items():
        if not isinstance(name, str) or not name:
            raise _fail(source, "tools", f"{name!r}", "a tool name must be a non-empty string")
        if not isinstance(mapping, ToolMapping):
            raise _fail(
                source,
                "tools",
                f"{name!r}",
                f"must be a ToolMapping, got {type(mapping).__name__}",
            )
    # BUILT_IN_TOOLS is placed in the policy as is (its proxy wraps a dict
    # nobody else holds); anything else is copied so the caller's dict cannot
    # edit the policy afterwards.
    if tools is BUILT_IN_TOOLS:
        return BUILT_IN_TOOLS
    return MappingProxyType(dict(tools))


def _validate_opaque_tools(
    source: str, opaque_tools: Any, tools: Mapping[str, ToolMapping]
) -> Mapping[str, Decision]:
    if not isinstance(opaque_tools, Mapping):
        raise _fail(
            source, "opaque_tools", f"must be a mapping, got {type(opaque_tools).__name__}"
        )
    for name, decision in opaque_tools.items():
        if not isinstance(name, str) or not name:
            raise _fail(
                source, "opaque_tools", f"{name!r}", "a tool name must be a non-empty string"
            )
        if decision not in DECISIONS:
            raise _fail(
                source,
                "opaque_tools",
                f"{name!r}",
                f"decision {decision!r} is not a decision (allowed: {_allowed(DECISIONS)})",
            )
        if name in tools:
            raise _fail(
                source,
                "opaque_tools",
                f"{name!r}",
                "also mapped under tools; a tool is either mapped or opaque, not both",
            )
    return MappingProxyType(dict(opaque_tools))


def _validate_strings(source: str, node: str, values: Any) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, (list, tuple)):
        raise _fail(source, node, f"must be a list, got {type(values).__name__}")
    for value in values:
        if not isinstance(value, str):
            raise _fail(source, node, f"{value!r}", "must be a string")
    return tuple(values)


def _validate_globs(source: str, node: str, values: Any, compile_one) -> Globs:
    patterns = _validate_strings(source, node, values)
    compiled = []
    for pattern in patterns:
        try:
            compiled.append(compile_one(pattern))
        except _GlobError as exc:
            raise _fail(source, node, f"{pattern!r}", str(exc)) from exc
    return Globs(patterns=patterns, compiled=tuple(compiled))


def _validate(source: str, spec: Mapping[str, Any]) -> ActionPolicy:
    """Build and check one `ActionPolicy`, or raise `ActionConfigError`.

    The one constructor of `ActionPolicy` outside tests. The built-in policy
    goes through it at import, and STORY-007 sends the file through it after
    the merge, so the floor cannot drift into a shape a file would be refused
    for (PRD-016 F8). `source` prefixes every message: `"built-in action
    policy"` here, `"ACTION_POLICY_FILE '<path>'"` in STORY-007.

    `spec` has exactly the keys of `_SPEC_KEYS`. `rules` maps a rule id to a
    `(default, grant)` pair; `tools` holds already-built `ToolMapping`s; the
    rest are a mapping (`opaque_tools`) or lists of strings.

    Checked here, in this order:

    - the spec's keys;
    - rules: every `RULE_IDS` member present and none unknown; then per rule,
      `default` in `DECISIONS`, `grant` absent or in `authz.ACTION_PERMISSIONS`,
      no grant on a `NON_GRANTABLE_RULES` member (T5), and `tool.opaque` with
      neither default nor grant;
    - tools: a non-empty mapping (T7) of non-empty names to `ToolMapping`s;
    - opaque_tools: non-empty names to a `DECISIONS` member, none also in tools;
    - every glob translates (protected paths, then secret env, then secret files).

    Added by STORY-007: reading and parsing the file, document and section key
    checks, the per-id `rules:` merge and the wholesale sections, building
    `ToolMapping`s from YAML and wrapping `ToolMappingError`, absolute
    `workspace.roots`, the syntax of `network.allow` entries, `shell.allow`
    entries with operators, and duplicate keys (`strict_yaml`). The
    `ACTION_SQL_DIALECT` cross-check is STORY-008's. The built-in lists are
    empty, so none of those checks could fail on the built-in policy.
    """
    keys = set(spec)
    if keys != _SPEC_KEYS:
        unknown = sorted(keys - _SPEC_KEYS)
        missing = sorted(_SPEC_KEYS - keys)
        raise _fail(
            source,
            "spec",
            f"unknown keys {unknown}, missing keys {missing} (expected: {_allowed(_SPEC_KEYS)})",
        )

    rules = _validate_rules(source, spec["rules"])
    tools = _validate_tools(source, spec["tools"])
    opaque_tools = _validate_opaque_tools(source, spec["opaque_tools"], tools)
    shell_allow = _validate_strings(source, "shell.allow", spec["shell_allow"])
    network_allow = _validate_strings(source, "network.allow", spec["network_allow"])
    workspace_roots = _validate_strings(source, "workspace.roots", spec["workspace_roots"])
    protected_paths = _validate_globs(
        source, "protected_paths", spec["protected_paths"], _compile_path_glob
    )
    secret_env = _validate_globs(source, "secrets.env", spec["secret_env"], _compile_name_glob)
    secret_files = _validate_globs(
        source, "secrets.files", spec["secret_files"], _compile_path_glob
    )

    return ActionPolicy(
        rules=rules,
        tools=tools,
        opaque_tools=opaque_tools,
        shell_allow=shell_allow,
        network_allow=network_allow,
        workspace_roots=workspace_roots,
        protected_paths=protected_paths,
        secrets=Secrets(env=secret_env, files=secret_files),
    )


#: The policy in force when nothing is configured. Public and never rebound --
#: `load()` rebinds `_policy`, not this -- so a test, and STORY-007's assertion
#: that the example file parses to the same thing, can name it.
#:
#: `opaque_tools` is **empty** (orchestrator decision, STORY-004 plan). The
#: `none` rows of `tests/corpora/actions/SOURCES.md` (OpenCode `todowrite`,
#: `task`, `question`, `websearch`, ...; Cline `search_codebase`,
#: `ask_question`, ...) are `tool.unknown` (deny) until a deployment names
#: them. That is the D1 floor.
BUILT_IN_POLICY = _validate(
    _BUILT_IN_SOURCE,
    {
        "rules": _BUILT_IN_RULES,
        "tools": BUILT_IN_TOOLS,
        "opaque_tools": {},
        "shell_allow": (),
        "network_allow": (),
        "workspace_roots": (),
        "protected_paths": _BUILT_IN_PROTECTED_PATHS,
        "secret_env": _BUILT_IN_SECRET_ENV,
        "secret_files": _BUILT_IN_SECRET_FILES,
    },
)

#: The policy in force. Private, and read through `get_policy()`: a public name
#: would be captured by `from app.services.action_config import POLICY` at
#: import time and never see the loaded file.
_policy = BUILT_IN_POLICY


def get_policy() -> ActionPolicy:
    """The policy in force -- the built-in one until `load()` replaces it.

    Returns rather than raises when `load()` has never run. Every test that
    never boots an app gets the floor (PRD-016 Section 6.12), and STORY-014's
    `evaluate(policy=None)` reads this.
    """
    return _policy


# --- The digest ------------------------------------------------------------


def _canonical(policy: ActionPolicy) -> dict:
    """The policy's source values as JSON-ready data. Never the compiled
    regexes. List order is kept, because declared order is part of the policy;
    mapping key order is not (the digest sorts keys)."""
    return {
        "rules": {
            rule_id: {"default": rule.default, "grant": rule.grant}
            for rule_id, rule in policy.rules.items()
        },
        "tools": {name: asdict(mapping) for name, mapping in policy.tools.items()},
        "opaque_tools": dict(policy.opaque_tools),
        "shell_allow": list(policy.shell_allow),
        "network_allow": list(policy.network_allow),
        "workspace_roots": list(policy.workspace_roots),
        "protected_paths": list(policy.protected_paths.patterns),
        "secrets": {
            "env": list(policy.secrets.env.patterns),
            "files": list(policy.secrets.files.patterns),
        },
    }


def policy_digest(policy: Optional[ActionPolicy] = None) -> str:
    """`sha256:<hex>` of the effective policy -- the one in force when `policy` is None.

    Computed over a canonical JSON of the policy (sorted keys), not over file
    bytes, so comments, whitespace and key order in a file do not change it,
    and two files that mean the same policy share a digest (PRD-016 Section
    4). Stamped on every `ActionDecision` and audit row (Section 6.2).

    Computed on every call: about fifty small entries, microseconds. A cached
    copy would be a second piece of module state that could disagree with
    `_policy`.
    """
    if policy is None:
        policy = _policy
    canonical = json.dumps(
        _canonical(policy), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# --- Loading ---------------------------------------------------------------


def load() -> None:
    """Load `ACTION_POLICY_FILE`, or keep the built-in policy, or fail startup.

    An empty `ACTION_POLICY_FILE` is a no-op: the built-in policy stands and
    **no file is read**. The setting is read here, at call time, never at
    import.

    In STORY-006 a non-empty setting raises `ActionConfigError` naming the
    path: reading the file is STORY-007's, and ignoring a configured file
    would be exactly the silent fallback PRD-016 Sections 4 and 6.12 forbid.
    The message carries the setting and the path, which STORY-007's
    "unreadable file" error will carry too.

    The contract STORY-007 must keep: every check passes before anything is
    rebound -- `_policy` is assigned as the last statement, so a file that
    fails leaves the previous policy intact (`pattern_config.load()`'s shape).
    """
    path = settings.ACTION_POLICY_FILE
    if not path:
        return
    raise ActionConfigError(
        f"ACTION_POLICY_FILE '{path}': loading a policy file is not available in "
        "this build (PRD-016 STORY-007); unset ACTION_POLICY_FILE to run the "
        "built-in policy"
    )
