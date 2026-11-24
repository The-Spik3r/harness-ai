"""The action-policy vocabulary: rule ids, operation kinds, decisions (PRD-016 Sections 6.2, 6.3, 6.11).

Every classifier in this package (STORY-008..013) takes an `Operation` and
returns `Classification`s whose `rule` is a `RuleId`; `action_config`
(STORY-006/007) validates a policy file's rule names and decisions against the
same closed sets; `action_policy.evaluate()` (STORY-014) folds the results into
a `Decision`. This file only *names* that vocabulary. What each rule defaults to
and which permission lifts it belong to `action_config`'s built-in policy
(STORY-006), not here.

`Operation` and `OperationKind` are defined here rather than in
`action_adapters` (STORY-004), which imports and re-exports them. The
classifiers need `Operation`, and the adapters need `OperationKind`; with both
here the import graph is one-way, `action_adapters -> action_classifiers`, and
no classifier ever imports the adapter layer. `ToolCall` stays in
`action_adapters`: no classifier needs it.

Pure on purpose (PRD-016 Section 6.12): no I/O, no settings, no pydantic, no
`app` import, nothing read at import. Configuration reaches a classifier as an
argument from `action_config`, never through `settings`.
"""

from dataclasses import dataclass
from typing import Literal, Optional, get_args

#: What an operation does, after the adapter layer maps a tool call to it
#: (PRD-016 Section 6.2). Exactly five. `tests/corpora/actions/SOURCES.md`
#: uses a sixth table value, `none`: a survey label for "no classified
#: operation", which STORY-004 resolves to `tool.unknown` or an
#: `opaque_tools` entry. It is not a kind and must not be added here.
OperationKind = Literal["shell", "sql", "fs_write", "fs_read", "http"]

#: The outcome for one tool call (PRD-016 Section 6.2). `flag` is allowed and
#: recorded (D10). The severity order `deny > flag > allow` that combines
#: several classifications is `action_policy`'s (STORY-014, D9).
Decision = Literal["allow", "flag", "deny"]

# The rule catalogue's ids (PRD-016 Section 6.3), in the table's order. A
# closed vocabulary (Section 6.2): an id outside it cannot appear in a policy
# file (a startup error, STORY-007) or be produced by a classifier (a type
# error, and each classifier story's test that walks its outputs).
#
# `tool.malformed` has one trigger the 6.3 "Produced when" column does not
# list: it is also what evaluate() returns when a classifier raises (PRD-016
# F7, threat T9), so a classifier bug fails closed rather than open.
RuleId = Literal[
    # SQL
    "sql.read",
    "sql.write",
    "sql.unscoped_write",
    "sql.ddl",
    "sql.dcl",
    "sql.unparsed",
    # Shell
    "shell.allowlisted",
    "shell.unlisted",
    "shell.destructive",
    "shell.pipe_to_interpreter",
    "shell.inline_interpreter",
    "shell.package_install",
    "shell.service_control",
    "shell.unclassifiable",
    # Filesystem
    "fs.read",
    "fs.write_in_workspace",
    "fs.write_outside_workspace",
    "fs.write_protected",
    # Network
    "net.allowlisted",
    "net.unlisted",
    "net.unparsed",
    # Secret
    "secret.read",
    # Tool
    "tool.unknown",
    "tool.opaque",
    "tool.malformed",
    # PRD-023 D7: appended, so every earlier position and the RULE_IDS order hold.
    "tool.not_in_skill",
]

# The tuple forms, for validators that enumerate the closed vocabularies in
# their error messages (PRD-016 Section 6.12; the `pattern_config._ROLES`
# shape). Order matters only for readable messages.
RULE_IDS: tuple[str, ...] = get_args(RuleId)
OPERATION_KINDS: tuple[str, ...] = get_args(OperationKind)
DECISIONS: tuple[str, ...] = get_args(Decision)

#: The eleven deny rules no role can lift (PRD-016 T5, Section 6.3's closing
#: paragraph; the eleventh, `tool.not_in_skill`, is PRD-023 D7): a policy file that adds a `grant` to any of them is refused at
#: startup (STORY-007). Their `default` can still be changed in the file,
#: visibly, where an auditor will see it. In Section 6.3 order.
NON_GRANTABLE_RULES: frozenset[RuleId] = frozenset(
    {
        "sql.unscoped_write",
        "sql.dcl",
        "sql.unparsed",
        "shell.destructive",
        "shell.pipe_to_interpreter",
        "shell.unclassifiable",
        "fs.write_protected",
        "net.unparsed",
        "tool.unknown",
        "tool.malformed",
        "tool.not_in_skill",
    }
)


@dataclass(frozen=True)
class Operation:
    """One thing a tool call does, as the adapter layer maps it (PRD-016 Section 6.2).

    A call can carry several (`commands[]`, `files[].path`); each is classified
    on its own. Re-exported by `action_adapters` (STORY-004).
    """

    kind: OperationKind
    #: The command, statement, path or URL the rule is about.
    target: str
    #: The tool name the operation came from, for the audit.
    source_tool: str


@dataclass(frozen=True)
class Classification:
    """What one classifier found in one operation (PRD-016 Section 6.2)."""

    rule: RuleId
    #: None for `tool.unknown` / `tool.malformed`: there is no operation to name.
    operation: Optional[Operation]
    #: The matched fragment of the *call* (`DROP`, `rm -rf`, `.env`), never a
    #: configured value such as an allowlist entry (PRD-016 T11).
    detail: str
