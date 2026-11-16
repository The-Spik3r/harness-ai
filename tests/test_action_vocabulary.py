"""The action-policy vocabulary (PRD-016 Sections 6.2, 6.3, 9.2 T5; STORY-003).

The expected values are transcribed from the PRD and hardcoded on purpose: no
test in this repo reads a PRD file, and later stories edit the PRD. Sources:
`_PRD_6_3_RULE_IDS` is the Section 6.3 rule-catalogue table, top to bottom;
`_PRD_T5_NON_GRANTABLE` is threat T5's list in Section 9.2 (the rows of 6.3
whose default is `deny` and whose grant is `—`).
"""

import dataclasses
import inspect
import typing
from typing import Optional, get_args

import pytest

import app.services.action_classifiers as action_classifiers
from app.services.action_classifiers import (
    DECISIONS,
    NON_GRANTABLE_RULES,
    OPERATION_KINDS,
    RULE_IDS,
    Classification,
    Decision,
    Operation,
    OperationKind,
    RuleId,
)

_PRD_6_3_RULE_IDS = (
    "sql.read",
    "sql.write",
    "sql.unscoped_write",
    "sql.ddl",
    "sql.dcl",
    "sql.unparsed",
    "shell.allowlisted",
    "shell.unlisted",
    "shell.destructive",
    "shell.pipe_to_interpreter",
    "shell.inline_interpreter",
    "shell.package_install",
    "shell.service_control",
    "shell.unclassifiable",
    "fs.read",
    "fs.write_in_workspace",
    "fs.write_outside_workspace",
    "fs.write_protected",
    "net.allowlisted",
    "net.unlisted",
    "net.unparsed",
    "secret.read",
    "tool.unknown",
    "tool.opaque",
    "tool.malformed",
)

_PRD_T5_NON_GRANTABLE = (
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
)

# PRD-016 D5: the rules for what a classifier cannot read.
_D5_UNCLASSIFIABLE = {"shell.unclassifiable", "sql.unparsed", "net.unparsed", "tool.malformed"}


def test_rule_id_is_exactly_the_25_ids_of_prd_section_6_3():
    assert get_args(RuleId) == _PRD_6_3_RULE_IDS
    assert len(get_args(RuleId)) == 25
    assert len(set(get_args(RuleId))) == 25
    assert RULE_IDS == get_args(RuleId)


def test_every_rule_id_is_class_dot_name():
    counts: dict[str, int] = {}
    for rule in RULE_IDS:
        prefix, _, name = rule.partition(".")
        assert name, rule
        counts[prefix] = counts.get(prefix, 0) + 1

    assert counts == {"sql": 6, "shell": 8, "fs": 4, "net": 3, "secret": 1, "tool": 3}


def test_operation_kind_is_the_five_of_section_6_2():
    assert get_args(OperationKind) == ("shell", "sql", "fs_write", "fs_read", "http")
    assert OPERATION_KINDS == get_args(OperationKind)


def test_decision_is_allow_flag_deny():
    assert get_args(Decision) == ("allow", "flag", "deny")
    assert DECISIONS == get_args(Decision)


def test_non_grantable_rules_are_exactly_the_ten_of_t5():
    assert isinstance(NON_GRANTABLE_RULES, frozenset)
    assert NON_GRANTABLE_RULES == frozenset(_PRD_T5_NON_GRANTABLE)
    assert len(NON_GRANTABLE_RULES) == 10
    assert NON_GRANTABLE_RULES <= set(RULE_IDS)
    assert _D5_UNCLASSIFIABLE <= NON_GRANTABLE_RULES


def test_classification_is_the_frozen_dataclass_of_section_6_2():
    assert dataclasses.is_dataclass(Classification)
    assert tuple(f.name for f in dataclasses.fields(Classification)) == ("rule", "operation", "detail")

    unknown = Classification("tool.unknown", None, "x")
    with pytest.raises(dataclasses.FrozenInstanceError):
        unknown.rule = "tool.malformed"

    operation = Operation(kind="sql", target="DROP TABLE t", source_tool="query")
    first = Classification(rule="sql.ddl", operation=operation, detail="DROP")
    second = Classification(rule="sql.ddl", operation=operation, detail="DROP")
    assert first == second
    assert hash(first) == hash(second)


def test_operation_is_the_frozen_dataclass_of_section_6_2():
    assert dataclasses.is_dataclass(Operation)
    assert tuple(f.name for f in dataclasses.fields(Operation)) == ("kind", "target", "source_tool")

    operation = Operation(kind="shell", target="ls", source_tool="bash")
    with pytest.raises(dataclasses.FrozenInstanceError):
        operation.target = "rm -rf /"


def test_type_hints_resolve():
    # No dangling forward reference: Operation is defined in the same module.
    hints = typing.get_type_hints(Classification)

    assert hints["operation"] == Optional[Operation]
    assert hints["rule"] == RuleId


def test_action_classifiers_package_stays_pure():
    """PRD-016 Section 6.12: no settings, no file I/O, no `app` import."""
    source = inspect.getsource(action_classifiers)

    assert "settings" not in vars(action_classifiers)
    assert "open(" not in source
    assert "Path(" not in source
    imports = [
        line
        for line in source.splitlines()
        if line.startswith("import ") or line.startswith("from ")
    ]
    assert not [line for line in imports if " app." in line or line.startswith("from app")]
