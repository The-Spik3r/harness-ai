"""PRD-020 STORY-009 (D8, O7): the pure token estimate.

    AC1  ceil per side, tools, empties; the module imports nothing but math/json
"""

import ast
import copy
import inspect
import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

from pathlib import Path

import pytest

from app.models.messages import Message, ToolCallSpec
from app.services import usage_estimate
from app.services.usage_estimate import estimate_tokens


def _call(arguments):
    return ToolCallSpec(id="c1", name="f", arguments=arguments)


@pytest.mark.parametrize(
    "sent, received, cpt, tools, expected",
    [
        ([], ("", ()), 4, None, 0),
        ([Message("user", "abcd")], ("", ()), 4, None, 1),
        ([Message("user", "abcde")], ("", ()), 4, None, 2),
        # ceil per side, not on the sum: 5 + 5 chars at 4 is 2 + 2, not 3.
        ([Message("user", "a" * 5)], ("b" * 5, ()), 4, None, 4),
        ([Message("user", "a" * 10)], ("", ()), 3, None, 4),
        ([Message("user", "a" * 10)], ("", ()), 2.5, None, 4),
        # multi-byte counts characters, not bytes
        ([Message("user", "ñññññññn")], ("", ()), 4, None, 2),
        ([Message("user", "你好世界")], ("", ()), 4, None, 1),
        # history tool_calls arguments count, a call-only turn has empty content
        ([Message("assistant", "", tool_calls=(_call("x" * 8),))], ("", ()), 4, None, 2),
        # response content and response calls
        ([], ("abcd", (_call("12345678"),)), 4, None, 3),
        # tools: sorted-key JSON length; absent 0, empty list "[]" = 2 chars
        ([], ("", ()), 1, None, 0),
        ([], ("", ()), 1, [], 2),
        ([], ("", ()), 1, [{"b": 1, "a": 2}], len('[{"a": 2, "b": 1}]')),
    ],
)
def test_estimate_table(sent, received, cpt, tools, expected):
    assert estimate_tokens(sent, received, cpt, tools=tools) == expected


def test_tools_key_order_is_irrelevant():
    a = [{"type": "function", "function": {"name": "f", "parameters": {"x": 1, "y": 2}}}]
    b = [{"function": {"parameters": {"y": 2, "x": 1}, "name": "f"}, "type": "function"}]
    assert estimate_tokens([], ("", ()), 4, tools=a) == estimate_tokens([], ("", ()), 4, tools=b)


def test_non_ascii_tools_count_characters():
    tools = [{"name": "ñ"}]
    assert estimate_tokens([], ("", ()), 1, tools=tools) == len('[{"name": "ñ"}]')


def test_none_content_counts_zero():
    msg = Message("user", "x")
    object.__setattr__(msg, "content", None)  # frozen; a None content must still count 0
    assert estimate_tokens([msg], ("", ()), 4) == 0


@pytest.mark.parametrize("cpt", [0, -1, -0.5])
def test_non_positive_cpt_raises(cpt):
    with pytest.raises(ValueError):
        estimate_tokens([Message("user", "a")], ("a", ()), cpt)


def test_inputs_are_not_mutated():
    sent = [Message("user", "hello"), Message("assistant", "", tool_calls=(_call("{}"),))]
    tools = [{"b": 1, "a": [1, 2]}]
    before = copy.deepcopy((sent, tools))
    estimate_tokens(sent, ("ok", (_call("{}"),)), 4, tools=tools)
    assert (sent, tools) == before


def test_is_pure():
    tree = ast.parse(Path(inspect.getsourcefile(usage_estimate)).read_text(encoding="utf-8"))
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            modules.add(node.module)
    # `app.models.messages` is imported only under TYPE_CHECKING, for annotations.
    runtime = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            runtime |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            runtime.add(node.module)
    assert runtime <= {"json", "math", "typing", "__future__"}
    assert modules <= runtime | {"app.models.messages"}
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert not names & {"settings", "open", "httpx", "logger", "logging"}
