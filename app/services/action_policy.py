"""The decision engine: one tool call and one identity in, allow / flag / deny out (PRD-016 Sections 4, 6.2, 6.4, 6.7).

The pipeline, for each call:

1. **Map.** `action_adapters.map_tool_call` reads the call (STORY-004).
   `Unknown`, `Malformed` and `Opaque` become one `tool.unknown`,
   `tool.malformed` or `tool.opaque` classification. `Operations` go on.
2. **Classify.** Each `Operation` goes to the classifier for its kind, in
   argument order: `sql` (STORY-008), `shell` (STORY-009/010, with STORY-013's
   embedded SQL, URLs, secret reads and redirects), `fs_write` / `fs_read`
   (STORY-011/013) and `http` (STORY-012). A classifier that returns one
   `Classification` is wrapped in a tuple. The Section 6.4 order ("embedded
   before the head's own rule") comes from the classifiers themselves; this
   module keeps it and never re-sorts.
3. **Decide.** Each classification is `allow` when the identity holds the
   rule's grant (`authz.holds`, which has no `RBAC_ENABLED` bypass: D7, T4),
   otherwise the rule's `default`. `tool.opaque` has no rule default and takes
   the `opaque_tools` entry's decision (`Opaque.decision`, STORY-006 plan
   decision 3).
4. **Fold.** The most severe outcome wins, `deny > flag > allow` (D9). The
   reported rule is the first classification at that severity, in order. One
   refinement, among `allow`s only: a classification that a grant lifted
   outranks a plain `allow`, so `SELECT 1; DELETE FROM t WHERE id = 3` for a
   role holding `action:sql:write` reports `sql.write` and the grant rather
   than hiding it behind `sql.read` (F11; STORY-014 plan D-3, accepted by the
   orchestrator). For `flag` and `deny` this is D9 exactly, since a grant only
   ever yields `allow`. `flag` is allowed and recorded (D10); what to do with
   it is PRD-017's.

The `reason` (T11) is a fixed subject per rule, a fixed verdict per decision,
and the reported classification's `detail` -- the matched fragment of the
*call*, never a configured host, root or allowlist entry. A verdict is part of
the template because one rule can end in any of the three decisions
(`sql.write` is `deny` for `user`, `allow` for a granted role, `flag` under
`{default: flag}`).

Fail closed (F7, T9): any exception between mapping and the fold is caught at
the `evaluate` boundary, logged at `ERROR` with the tool name and the rule --
never the arguments, the exception text or a traceback, any of which could
quote the target -- and returned as a hard `deny` under `tool.malformed`,
whatever `tool.malformed`'s configured default is. A classifier crash is a
bug, not a policy choice.

Purity (Section 6.12): this module names no `settings`, opens no file and
touches no database. What it reads is in-memory state: the policy through
`action_config.get_policy()`, the SQL dialect and the argument cap through
`action_config`'s two call-time getters, and the role matrix through
`authz.holds()`. The honest limit: unlike `action_adapters` and the
classifiers, importing this module loads `app.config` transitively, because
`action_config` and `authz` import `settings`. That follows from the PRD
itself (`policy=None` defaults to the loaded policy, grants go through
`holds()`), so the test asserts what is true rather than a subprocess "no
settings loaded" check.

The MCP gateway (PRD-023 D4, D7, Section 6.4): `evaluate(..., surface=McpSurface)`
decides a `tools/call` through this same engine. With a surface, visibility is
checked first, inside the boundary: a name outside `surface.visible` is one
`tool.not_in_skill` classification (deny, not grantable) and `map_tool_call` is
never called. A visible name is mapped through the server's own
`mcp_tools` / `mcp_opaque_tools` tables, never the `/v1` ones. Decide, fold, the
reason template and the fail-closed boundary are unchanged. `surface` is the
caller's (computed from the caller's skills), so this module still reads no
settings and does no I/O.

Not this module's work: what PRD-017 does with `flag` and `deny` (D4: since
STORY-010, `query_pipeline` step 7c calls `evaluate_all`, and `tool_release`
releases `allow`/`flag` and turns a `deny` into a note), and recording
decisions (STORY-015, `action_audit.record`). `ActionDecision`
carries `operations`, the reported `operation` and the raw `arguments` beyond
Section 6.2's eight fields so that `record()` keeps its Section 10 signature.
"""

import logging
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Final, Mapping, Optional, Sequence

from app.services import action_adapters, action_config, authz
from app.services.action_classifiers import DECISIONS, Classification, Decision, Operation, RuleId
from app.services.action_classifiers import network, paths, shell, sql

if TYPE_CHECKING:
    from app.services.identity import Identity

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ActionDecision:
    """The outcome for one tool call (PRD-016 Section 6.2), plus what STORY-015 records.

    The first eight fields are Section 6.2's, in its order. The last three
    exist because `record(decisions, identity, audit_id, session_id)` gets no
    `ToolCall` (Section 10), so the decision carries what the
    `action_decisions` row needs (Section 6.10).

    Invariant: `rule` is the `rule` of exactly one reported classification,
    and `operation` is that classification's `operation`.
    """

    #: `call.id`; `""` when it is not a string.
    tool_call_id: str
    #: `call.name`; `""` when it is not a string.
    tool_name: str
    decision: Decision
    #: The rule that produced `decision`.
    rule: RuleId
    #: Fixed subject + fixed verdict + the call's matched fragment; safe for the agent (T11).
    reason: str
    #: The action permission that turned deny/flag into allow; None otherwise.
    granted_by: Optional[str]
    #: Every classification, in order, for the audit. Never empty.
    classifications: tuple[Classification, ...]
    #: `action_config.policy_digest()` of the policy that decided.
    policy_digest: str
    #: What the call does; `()` for an unknown, malformed or opaque tool (Section 4).
    operations: tuple[Operation, ...]
    #: The target the reported rule judged; None for the `tool.*` rules.
    operation: Optional[Operation]
    #: The raw arguments as emitted (`""` when not a string), for the audit's
    #: hash and preview. Kept out of `repr`: it may hold a secret (T10).
    arguments: str = field(repr=False)


#: D9: `deny > flag > allow`.
_SEVERITY: Mapping[str, int] = MappingProxyType({"allow": 0, "flag": 1, "deny": 2})

#: One verdict per decision (T11). Names no permission and no role:
#: `granted_by` carries the permission as its own field.
_VERDICTS: Mapping[str, str] = MappingProxyType(
    {
        "allow": "is permitted",
        "flag": "is permitted and flagged for review",
        "deny": "is not permitted",
    }
)

#: One fixed subject per rule, in `RULE_IDS` order (T11). `sql.ddl` is fixed
#: by the PRD's own example: "destructive SQL is not permitted: DROP" (5.1).
_SUBJECTS: Mapping[str, str] = MappingProxyType(
    {
        "sql.read": "read-only SQL",
        "sql.write": "SQL that changes data",
        "sql.unscoped_write": "SQL that changes every row",
        "sql.ddl": "destructive SQL",
        "sql.dcl": "SQL that changes permissions",
        "sql.unparsed": "SQL that cannot be parsed",
        "shell.allowlisted": "an allowlisted command",
        "shell.unlisted": "a command that is not allowlisted",
        "shell.destructive": "a destructive command",
        "shell.pipe_to_interpreter": "piping into an interpreter",
        "shell.inline_interpreter": "inline interpreter code",
        "shell.package_install": "installing packages",
        "shell.service_control": "controlling services",
        "shell.unclassifiable": "a command that cannot be classified",
        "fs.read": "reading a file",
        "fs.write_in_workspace": "writing inside the workspace",
        "fs.write_outside_workspace": "writing outside the workspace",
        "fs.write_protected": "writing a protected path",
        "net.allowlisted": "a request to an allowlisted host",
        "net.unlisted": "a request to a host that is not allowlisted",
        "net.unparsed": "a URL that cannot be parsed",
        "secret.read": "reading a secret",
        "tool.unknown": "an unknown tool",
        "tool.opaque": "an opaque tool",
        "tool.malformed": "a tool call that cannot be read",
        "tool.not_in_skill": "a tool outside the caller's skills",
    }
)

#: The tool name is model-chosen; as a `tool.unknown` / `tool.opaque` detail
#: it is cut to this length.
_NAME_DETAIL_CAP = 64

#: The detail of the boundary's `tool.malformed`: fixed, so nothing of the
#: call or the exception reaches the reason.
_FAILED_DETAIL = "classification failed"


@dataclass(frozen=True)
class McpSurface:
    """Where a call comes from when it is an MCP `tools/call` (PRD-023 D4, D7, Section 6.4).

    The caller computes `visible` (the bare upstream tool names the caller's
    skills expose on `server`); the engine only checks membership.
    """

    #: The upstream server id; selects `mcp_tools[server]` / `mcp_opaque_tools[server]`.
    server: str
    #: Bare upstream tool names the caller may see. Anything else is `tool.not_in_skill`.
    visible: frozenset[str]


#: The `/v1` surface (step 7c): `evaluate(..., surface=V1)` is `evaluate(...)`.
V1: Final = None

#: A server with no table: every tool of it is `tool.unknown`.
_EMPTY: Mapping = MappingProxyType({})


class _EngineError(Exception):
    """Internal: an engine invariant broke. Raised below, caught only at the `evaluate` boundary."""


def _is_visible(surface: Optional[McpSurface], name: str) -> bool:
    """Whether `name` may be mapped at all: always on `/v1`, membership in `visible` on the gateway.

    Called through the module so a test's monkeypatch reaches it, as `_classify` is.
    """
    return surface is V1 or name in surface.visible


def _select_tables(
    policy: action_config.ActionPolicy, surface: Optional[McpSurface]
) -> tuple[Mapping, Mapping]:
    """`(tools, opaque_tools)` for the surface; the gateway never falls back to the `/v1` tables (D4)."""
    if surface is V1:
        return policy.tools, policy.opaque_tools
    return (
        policy.mcp_tools.get(surface.server, _EMPTY),
        policy.mcp_opaque_tools.get(surface.server, _EMPTY),
    )


def _classify(op: Operation, policy: action_config.ActionPolicy, dialect: Optional[str]) -> tuple[Classification, ...]:
    """The classifier for `op.kind`, called through its module so a test's monkeypatch reaches it.

    `sql` and `shell` return tuples; `paths` and `network` one
    `Classification`, wrapped here (STORY-011 orchestrator note). The shell
    call is the STORY-013 orchestrator's, verbatim: its keyword arguments
    default to `()`, which would silently disable the embedded checks.
    """
    if op.kind == "sql":
        result = sql.classify_sql(op.target, dialect, source_tool=op.source_tool)
    elif op.kind == "shell":
        result = shell.classify_shell(
            op.target,
            policy.shell_allow,
            network_allow=policy.network_allow,
            secret_env=policy.secrets.env.compiled,
            secret_files=policy.secrets.files.compiled,
            protected=policy.protected_paths.compiled,
            workspace_roots=policy.workspace_roots,
            source_tool=op.source_tool,
        )
    elif op.kind == "fs_write":
        result = (
            paths.classify_write(
                op.target,
                policy.protected_paths.compiled,
                policy.workspace_roots,
                source_tool=op.source_tool,
            ),
        )
    elif op.kind == "fs_read":
        result = (paths.classify_read(op.target, policy.secrets.files.compiled, source_tool=op.source_tool),)
    elif op.kind == "http":
        result = (network.classify_url(op.target, policy.network_allow, source_tool=op.source_tool),)
    else:
        raise _EngineError(f"no classifier for operation kind {op.kind!r}")
    result = tuple(result)
    if not result:
        # Zero classifications would fold to nothing, i.e. an unexplained allow.
        raise _EngineError(f"the {op.kind} classifier returned no classification")
    return result


def _decide(
    c: Classification,
    identity: "Identity",
    policy: action_config.ActionPolicy,
    opaque: Optional[action_adapters.Opaque],
) -> tuple[Decision, Optional[str]]:
    """`(decision, grant)` for one classification (D7, Section 6.7).

    `grant` is the permission that lifted it, or None. A rule id the policy
    does not carry raises `KeyError`, and a decided value outside `DECISIONS`
    (a classifier that returned `tool.opaque`, whose default is None) raises
    `_EngineError`; the boundary fails both closed.
    """
    if c.rule == "tool.opaque":
        if opaque is None:
            raise _EngineError("tool.opaque produced by a classifier")
        decision, grant = opaque.decision, None
    else:
        rule = policy.rules[c.rule]
        if rule.grant is not None and authz.holds(identity, rule.grant):
            decision, grant = "allow", rule.grant
        else:
            decision, grant = rule.default, None
    if decision not in DECISIONS:
        raise _EngineError(f"rule {c.rule} decided {decision!r}")
    return decision, grant


def _fold(decided: Sequence[tuple[Decision, Optional[str]]]) -> int:
    """The index of the reported classification: the first at the maximum `(severity, lifted)` (D9, D-3)."""
    best, best_key = 0, None
    for i, (decision, grant) in enumerate(decided):
        key = (_SEVERITY[decision], grant is not None)
        if best_key is None or key > best_key:
            best, best_key = i, key
    return best


def _reason(rule: RuleId, decision: Decision, detail: str) -> str:
    """The rule's fixed subject, the decision's fixed verdict, and the call's fragment (T11)."""
    reason = f"{_SUBJECTS[rule]} {_VERDICTS[decision]}"
    if detail:
        reason += f": {detail}"
    return reason


def evaluate(
    call: action_adapters.ToolCall,
    identity: "Identity",
    policy: Optional[action_config.ActionPolicy] = None,
    *,
    surface: Optional[McpSurface] = V1,
) -> ActionDecision:
    """Decide one tool call for one identity (PRD-016 Sections 4, 10). Never raises for model input.

    `policy=None` is the policy in force (`action_config.get_policy()`).
    `surface` is `V1` (None) for the `/v1` path, or an `McpSurface` for the
    gateway (PRD-023 D4, D7); its visibility check and table selection are
    inside the boundary below.
    The policy, its digest, the SQL dialect and the argument cap are resolved
    before the fail-closed boundary: they are configuration, not model input,
    and a failure there is a deployment bug that should surface. Everything
    from `map_tool_call` to the fold is inside it (T9).
    """
    if policy is None:
        policy = action_config.get_policy()
    digest = action_config.policy_digest(policy)
    dialect = action_config.get_sql_dialect()
    cap = action_config.get_max_argument_characters()

    raw_id = getattr(call, "id", None)
    raw_name = getattr(call, "name", None)
    raw_arguments = getattr(call, "arguments", None)
    tool_call_id = raw_id if isinstance(raw_id, str) else ""
    tool_name = raw_name if isinstance(raw_name, str) else ""
    arguments = raw_arguments if isinstance(raw_arguments, str) else ""

    operations: tuple[Operation, ...] = ()
    try:
        opaque = None
        if not _is_visible(surface, tool_name):
            # PRD-023 D7: checked before any mapping, so a hidden tool's mapping is never consulted.
            hidden = True
            result = None
            classifications = (Classification("tool.not_in_skill", None, tool_name[:_NAME_DETAIL_CAP]),)
        else:
            hidden = False
            tools, opaque_tools = _select_tables(policy, surface)
            result = action_adapters.map_tool_call(call, tools, opaque_tools, cap)
        if hidden:
            pass
        elif isinstance(result, action_adapters.Operations):
            operations = result.operations
            classifications = tuple(c for op in operations for c in _classify(op, policy, dialect))
        elif isinstance(result, action_adapters.Opaque):
            # Its arguments are never read (Section 6.4); it is still recorded.
            opaque = result
            classifications = (Classification("tool.opaque", None, tool_name[:_NAME_DETAIL_CAP]),)
        elif isinstance(result, action_adapters.Unknown):
            classifications = (Classification("tool.unknown", None, tool_name[:_NAME_DETAIL_CAP]),)
        elif isinstance(result, action_adapters.Malformed):
            classifications = (Classification("tool.malformed", None, result.detail),)
        else:
            raise _EngineError(f"unexpected mapping result {type(result).__name__}")

        decided = [_decide(c, identity, policy, opaque) for c in classifications]
        index = _fold(decided)
        reported = classifications[index]
        decision, grant = decided[index]
        return ActionDecision(
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            decision=decision,
            rule=reported.rule,
            reason=_reason(reported.rule, decision, reported.detail),
            granted_by=grant,
            classifications=classifications,
            policy_digest=digest,
            operations=operations,
            operation=reported.operation,
            arguments=arguments,
        )
    except Exception as exc:
        # Only the exception's type: its message or traceback could quote the
        # target. `%r` keeps a model-chosen name from forging a log line.
        # `BaseException` (KeyboardInterrupt) is not caught.
        logger.error(
            "action policy: classifying tool %r failed (%s); denied under tool.malformed",
            tool_name,
            type(exc).__name__,
        )
        failed = Classification("tool.malformed", None, _FAILED_DETAIL)
        return ActionDecision(
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            decision="deny",
            rule="tool.malformed",
            reason=_reason("tool.malformed", "deny", _FAILED_DETAIL),
            granted_by=None,
            classifications=(failed,),
            policy_digest=digest,
            operations=operations,
            operation=None,
            arguments=arguments,
        )


def evaluate_all(
    calls: Sequence[action_adapters.ToolCall],
    identity: "Identity",
    policy: Optional[action_config.ActionPolicy] = None,
) -> tuple[ActionDecision, ...]:
    """Decide every call of one response, in input order (PRD-016 Sections 4, 10).

    Each call is decided on its own; mixed outcomes are PRD-017's (D1). The
    policy is resolved once, so every decision of one response carries one
    policy and one digest. `policy` is an additive optional parameter beyond
    Section 10's `evaluate_all(calls, identity)`, which still works unchanged.
    """
    if policy is None:
        policy = action_config.get_policy()
    return tuple(evaluate(call, identity, policy) for call in calls)
