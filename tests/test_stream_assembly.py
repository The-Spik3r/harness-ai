"""PRD-021 STORY-006: `phase_of`, the pure phase mapping (Sections 6.1, 6.2; D6, T1, T4)."""

import ast
from pathlib import Path

import pytest

from app.services.stream_assembly import phase_of
from app.services.upstream.types import Finish, ReasoningDelta, TextDelta, ToolCallDelta, UsageReport

_SRC = Path(__file__).resolve().parent.parent / "app" / "services" / "stream_assembly.py"


def test_phase_of_reasoning_is_thinking_and_empty_reasoning_is_nothing():
    assert phase_of(ReasoningDelta("hmm"), "waiting") == ("thinking", None)
    assert phase_of(ReasoningDelta(""), "waiting") is None


def test_phase_of_text_is_writing_and_empty_text_is_nothing():
    assert phase_of(TextDelta("Hi"), "waiting") == ("writing", None)
    assert phase_of(TextDelta(""), "waiting") is None
    assert phase_of(TextDelta(""), None) is None


def test_phase_of_nameless_tool_fragment_is_nothing():
    assert phase_of(ToolCallDelta(0, arguments='{"a"'), "writing") is None
    assert phase_of(ToolCallDelta(0, name="", arguments="{"), "writing") is None


def test_phase_of_named_tool_carries_its_kind_and_unmapped_has_none():
    kinds = {"bash": "shell"}
    assert phase_of(ToolCallDelta(0, name="bash"), "writing", kinds) == ("preparing_action", "shell")
    assert phase_of(ToolCallDelta(0, name="mystery"), "writing", kinds) == ("preparing_action", None)
    assert phase_of(ToolCallDelta(0, name="bash"), "writing") == ("preparing_action", None)


def test_phase_of_emits_on_change_only():
    assert phase_of(TextDelta("a"), "writing") is None
    assert phase_of(ReasoningDelta("a"), "thinking") is None
    assert phase_of(ToolCallDelta(1, name="b"), "preparing_action", {"b": "shell"}) is None


@pytest.mark.parametrize("event", [Finish("stop"), UsageReport(1, 2, 3)])
def test_phase_of_ignores_finish_and_usage(event):
    assert phase_of(event, "waiting") is None


def test_phase_of_never_returns_text():
    # T4: a phase carries a kind, never a command or an argument.
    secret = "DROP TABLE users"
    result = phase_of(ToolCallDelta(0, name="sql", arguments=secret), "waiting", {"sql": "sql"})
    assert result == ("preparing_action", "sql")
    assert secret not in repr(result)


def test_stream_assembly_is_pure():
    tree = ast.parse(_SRC.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
    assert imported <= {
        "typing",
        "app.services.action_classifiers",
        "app.services.delivery",
        "app.services.upstream.types",
    }
