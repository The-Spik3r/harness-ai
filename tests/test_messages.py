"""PRD-010 STORY-001: `Message`, `Role` and the OpenAI content normalizer.

Every row of PRD-010 Section 6.2's table is one named parametrize case below.
The normalizer has no production caller in this PRD -- PRD-014 is its first
ingress -- so these tests are the whole contract until then. Errors name a
location and a rule and never the content (canary tests), and `Message` keys
exactly like the pipeline's turn does today, with no import between this module
and `duplicate_checker` in either direction.

PRD-017 STORY-003 adds the tool fields (`tool_calls`, `tool_call_id`, Section 6.2).
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import ast
import dataclasses
import inspect
from dataclasses import dataclass
from pathlib import Path
from typing import get_args

import pytest

import app.models.messages as messages_module
from app.models.messages import (
    Message,
    conversation_shape_violation,
    MessageNormalizationError,
    Role,
    ToolCallSpec,
    normalize_message,
    normalize_messages,
)
from app.services.duplicate_checker import dedup_key

_ROOT = Path(__file__).resolve().parents[1]
_JUAN = "juan@empresa.com"
_CANARY = "jane@corp.com SECRET-CANARY"


@dataclass(frozen=True)
class _Turn:
    role: str
    content: str


def _text(text):
    return {"type": "text", "text": text}


def _call(call_id, name="ls", arguments="{}"):
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": arguments}}


def test_exports_the_specified_names_and_signatures():
    assert get_args(Role) == ("system", "user", "assistant", "tool")
    assert list(inspect.signature(normalize_message).parameters) == ["raw"]
    assert list(inspect.signature(normalize_messages).parameters) == ["raw"]
    # PRD-017 D5 (STORY-003): two trailing defaulted tool fields.
    assert [f.name for f in dataclasses.fields(Message)] == ["role", "content", "tool_calls", "tool_call_id"]
    assert Message.__dataclass_params__.frozen
    assert issubclass(MessageNormalizationError, Exception)


def test_message_is_frozen():
    message = Message("user", "x")

    with pytest.raises(dataclasses.FrozenInstanceError):
        message.content = "y"


# --- PRD-010 Section 6.2, one case per table row -----------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ({"role": "user", "content": "text"}, Message("user", "text")),
        (
            {"role": "user", "content": [_text("a"), _text("b")]},
            Message("user", "a\nb"),
        ),
        ({"role": "assistant", "content": None}, Message("assistant", "")),
        # Technical Notes: `tool` is a valid Role; the pipeline refuses it, not this.
        # PRD-017 D5 (STORY-003): a tool turn now carries its `tool_call_id`.
        (
            {"role": "tool", "tool_call_id": "c1", "content": "ls output"},
            Message("tool", "ls output", tool_call_id="c1"),
        ),
        ({"role": "system", "content": "be brief"}, Message("system", "be brief")),
    ],
    ids=[
        "string-content",
        "two-text-parts-joined-with-newline",
        "null-on-assistant-becomes-empty",
        "tool-role-with-string-content",
        "system-role-with-string-content",
    ],
)
def test_normalizes_table_row(raw, expected):
    assert normalize_message(raw) == expected


@pytest.mark.parametrize(
    "raw, rule",
    [
        (
            {
                "role": "user",
                "content": [_text("a"), {"type": "image_url", "image_url": {"url": "https://x/y.png"}}],
            },
            r"content\[1\] is not a text part",
        ),
        ({"role": "user", "content": None}, "null content"),
        ({"role": "system", "content": None}, "null content"),
        # PRD-017 D5 (STORY-003): the tool turn needs its id, so this still
        # tests the null-content rule rather than the missing id. The
        # `tool-calls-key` refusal moved to test_normalizes_tool_shape (accepted).
        ({"role": "tool", "tool_call_id": "c1", "content": None}, "null content"),
        ({"role": "developer", "content": "hi"}, "unknown role"),
    ],
    ids=[
        "image-url-part",
        "null-on-user",
        "null-on-system",
        "null-on-tool",
        "unknown-role-developer",
    ],
)
def test_refuses_table_row(raw, rule):
    with pytest.raises(MessageNormalizationError, match=rule):
        normalize_message(raw)


@pytest.mark.parametrize(
    "raw, rule",
    [
        ({"role": "user", "content": [{"type": "text"}]}, r"content\[0\] text part has no string text"),
        ({"role": "user", "content": [{"type": "text", "text": 3}]}, r"content\[0\] text part has no string text"),
        ({"role": "user", "content": ["a"]}, r"content\[0\] is not a text part"),
        (["role", "user"], "message is not an object"),
        ("user", "message is not an object"),
        ({"content": "x"}, "unknown role"),
        ({"role": 1, "content": "x"}, "unknown role"),
        ({"role": "user", "content": 3}, "content must be a string"),
        ({"role": "user", "content": {"type": "text", "text": "x"}}, "content must be a string"),
        # PRD-017 D5 (STORY-003): `tool_calls: []` is now accepted (see
        # test_normalizes_tool_shape), so the refusal case is gone.
    ],
    ids=[
        "text-part-missing-text",
        "text-part-non-str-text",
        "part-not-a-mapping",
        "message-is-a-list",
        "message-is-a-string",
        "missing-role",
        "non-str-role",
        "content-is-int",
        "content-is-dict",
    ],
)
def test_refuses_malformed_shape(raw, rule):
    with pytest.raises(MessageNormalizationError, match=rule):
        normalize_message(raw)


def test_missing_content_key_is_treated_as_null():
    assert normalize_message({"role": "assistant"}) == Message("assistant", "")

    with pytest.raises(MessageNormalizationError, match="null content"):
        normalize_message({"role": "user"})


def test_empty_text_is_not_refused():
    """Plan Design Decision 7: the 6.2 table refuses only `null`. A policy change is this edit."""
    assert normalize_message({"role": "user", "content": ""}) == Message("user", "")
    assert normalize_message({"role": "user", "content": []}) == Message("user", "")


def test_part_join_keeps_boundaries_visible():
    message = normalize_message(
        {"role": "user", "content": [_text("ignore"), _text("previous instructions")]}
    )

    assert message.content == "ignore\nprevious instructions"
    assert "ignoreprevious" not in message.content


def test_whitespace_and_extra_keys_are_preserved_and_ignored():
    assert normalize_message({"role": "user", "content": "  hi \n"}).content == "  hi \n"
    assert normalize_message({"role": "user", "content": "x", "name": "n"}) == Message("user", "x")


# --- normalize_messages ------------------------------------------------------


def test_normalize_messages_preserves_order_and_length():
    result = normalize_messages(
        [
            {"role": "system", "content": "be brief"},
            {"role": "user", "content": [_text("a"), _text("b")]},
            {"role": "assistant", "content": None},
        ]
    )

    assert result == [Message("system", "be brief"), Message("user", "a\nb"), Message("assistant", "")]


def test_normalize_messages_accepts_empty_and_does_not_validate_structure():
    """Non-empty and last-is-user are STORY-007's checks, not the normalizer's."""
    assert normalize_messages([]) == []
    assert normalize_messages([{"role": "assistant", "content": "x"}]) == [Message("assistant", "x")]
    assert normalize_messages([{"role": "system", "content": "a"}]) == [Message("system", "a")]


def test_normalize_messages_accepts_any_sequence():
    raw = ({"role": "user", "content": "x"}, {"role": "assistant", "content": "y"})

    assert normalize_messages(raw) == [Message("user", "x"), Message("assistant", "y")]


def test_invalid_element_names_its_index_and_rule():
    raw = [
        {"role": "user", "content": "a"},
        {"role": "assistant", "content": "b"},
        {"role": "user", "content": "c"},
        {"role": "user", "content": None},
    ]

    with pytest.raises(MessageNormalizationError) as caught:
        normalize_messages(raw)

    assert str(caught.value).startswith("messages[3]: ")
    assert "null content" in str(caught.value)


@pytest.mark.parametrize(
    "bad",
    [
        {"role": "user", "content": [_text(_CANARY), {"type": "image_url", "image_url": {"url": _CANARY}}]},
        {"role": "developer", "content": _CANARY},
        {"role": "assistant", "content": _CANARY, "tool_calls": [{"id": _CANARY}]},
        {"role": "developer-CANARY", "content": "x"},
        {"role": "user", "content": [{"type": "CANARY_type", "text": _CANARY}]},
        {"role": "user", "content": [{"type": "text", "text": {"nested": _CANARY}}]},
        {"role": "user", "content": {"text": _CANARY}},
        # PRD-017 D5 (STORY-003): tool-shape errors withhold values too.
        {"role": "assistant", "content": None, "tool_calls": [_call(_CANARY), _call(_CANARY)]},
        {"role": "assistant", "content": None, "tool_calls": [_call("c1", arguments={"x": _CANARY})]},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [{"id": "c1", "type": _CANARY, "function": {"name": _CANARY, "arguments": "{}"}}],
        },
        {"role": "user", "content": "x", "tool_call_id": _CANARY},
        {"role": "tool", "content": _CANARY},
        {"role": "assistant", "content": None, "tool_calls": _CANARY},
    ],
    ids=[
        "image-part-beside-canary-text",
        "unknown-role-with-canary-content",
        "tool-calls-with-canary-content",
        "canary-role-value",
        "canary-part-type",
        "non-str-text-holding-canary",
        "dict-content-holding-canary",
        "tool-duplicate-id-canary",
        "tool-non-str-arguments-canary",
        "tool-wrong-type-canary-name",
        "tool-call-id-on-user-canary",
        "tool-turn-canary-content-no-id",
        "tool-calls-string-canary",
    ],
)
def test_error_never_echoes_content(bad):
    with pytest.raises(MessageNormalizationError) as single:
        normalize_message(bad)
    with pytest.raises(MessageNormalizationError) as listed:
        normalize_messages([{"role": "user", "content": "ok"}, bad])

    assert str(listed.value).startswith("messages[1]: ")
    for exc in (single.value, listed.value):
        assert "CANARY" not in str(exc)
        assert "CANARY" not in repr(exc.__cause__)


# --- PRD-017 D5 (STORY-003): tool_calls / tool_call_id -----------------------


def test_tool_call_spec_is_frozen_with_the_specified_fields():
    assert [f.name for f in dataclasses.fields(ToolCallSpec)] == ["id", "name", "arguments"]
    assert ToolCallSpec.__dataclass_params__.frozen
    # AC1: legacy two-argument construction is unchanged.
    legacy = Message("user", "x")
    assert legacy.tool_calls == ()
    assert legacy.tool_call_id is None


def test_tool_call_spec_fields_match_action_adapters_tool_call():
    from app.services.action_adapters import ToolCall

    assert tuple(f.name for f in dataclasses.fields(ToolCallSpec)) == tuple(
        f.name for f in dataclasses.fields(ToolCall)
    )


_ONE_CALL = [_call("c1", "bash", '{"command":"ls"}')]
_TWO_CALLS = [_call("c1", "ls", "{}"), _call("c2", "cat", '{"p":"a"}')]
_TWO_SPECS = (ToolCallSpec("c1", "ls", "{}"), ToolCallSpec("c2", "cat", '{"p":"a"}'))


@pytest.mark.parametrize(
    "raw, expected",
    [
        (
            {"role": "assistant", "content": None, "tool_calls": _ONE_CALL},
            Message("assistant", "", (ToolCallSpec("c1", "bash", '{"command":"ls"}'),)),
        ),
        ({"role": "assistant", "content": "x", "tool_calls": []}, Message("assistant", "x")),
        (
            {"role": "assistant", "content": "running", "tool_calls": _ONE_CALL},
            Message("assistant", "running", (ToolCallSpec("c1", "bash", '{"command":"ls"}'),)),
        ),
        ({"role": "assistant", "content": None, "tool_calls": _TWO_CALLS}, Message("assistant", "", _TWO_SPECS)),
        (
            {"role": "tool", "tool_call_id": "c1", "content": "ok"},
            Message("tool", "ok", tool_call_id="c1"),
        ),
        (
            {"role": "tool", "tool_call_id": "c1", "content": [_text("ok")]},
            Message("tool", "ok", tool_call_id="c1"),
        ),
        (
            {
                "role": "assistant",
                "content": None,
                "tool_calls": _ONE_CALL,
                "reasoning_details": [{"type": "reasoning.text", "text": "t"}],
                "cache_control": {"type": "ephemeral"},
            },
            Message("assistant", "", (ToolCallSpec("c1", "bash", '{"command":"ls"}'),)),
        ),
        (
            {"role": "tool", "tool_call_id": "c1", "content": "ok", "cache_control": {"type": "ephemeral"}},
            Message("tool", "ok", tool_call_id="c1"),
        ),
        (
            {"role": "assistant", "content": None, "tool_calls": _ONE_CALL, "reasoning_content": "t"},
            Message("assistant", "", (ToolCallSpec("c1", "bash", '{"command":"ls"}'),)),
        ),
        (
            {"role": "tool", "tool_call_id": "c1", "content": '{"files":["a"]}'},
            Message("tool", '{"files":["a"]}', tool_call_id="c1"),
        ),
        (
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"id": "c1", "type": "function", "index": 0, "function": {"name": "ls", "arguments": "{}", "x": 1}}
                ],
            },
            Message("assistant", "", (ToolCallSpec("c1", "ls", "{}"),)),
        ),
        # Orchestrator decision STORY-003 (PRD-017 D5): null counts as absent,
        # because SDK `model_dump()` echoes of text assistant turns carry it.
        ({"role": "assistant", "content": "x", "tool_calls": None}, Message("assistant", "x")),
        ({"role": "user", "content": "x", "tool_calls": None}, Message("user", "x")),
        ({"role": "system", "content": "x", "tool_calls": None}, Message("system", "x")),
        ({"role": "tool", "tool_call_id": "c1", "content": "x", "tool_calls": None}, Message("tool", "x", tool_call_id="c1")),
        ({"role": "user", "content": "x", "tool_call_id": None}, Message("user", "x")),
        ({"role": "assistant", "content": "x", "tool_call_id": None}, Message("assistant", "x")),
        ({"role": "system", "content": "x", "tool_call_id": None}, Message("system", "x")),
    ],
    ids=[
        "assistant-null-content-one-call",
        "empty-tool-calls-becomes-empty-tuple",
        "assistant-text-and-calls",
        "two-calls-in-order",
        "tool-turn-string",
        "tool-turn-text-parts",
        "opencode-assistant",
        "opencode-tool-turn",
        "cline-assistant",
        "cline-tool-turn-json-string-content",
        "extra-keys-on-call-and-function-ignored",
        "null-tool-calls-on-assistant",
        "null-tool-calls-on-user",
        "null-tool-calls-on-system",
        "null-tool-calls-on-tool",
        "null-tool-call-id-on-user",
        "null-tool-call-id-on-assistant",
        "null-tool-call-id-on-system",
    ],
)
def test_normalizes_tool_shape(raw, expected):
    assert normalize_message(raw) == expected


@pytest.mark.parametrize(
    "arguments",
    ["", "{", ' { "a" : 1 } \n', '{"q":"acentuación 🙂"}', '{"a":"{\\"b\\":1}"}'],
    ids=["empty", "invalid-json", "whitespace", "non-ascii", "nested-json-string"],
)
def test_arguments_are_carried_byte_for_byte(arguments):
    # PRD-017 D13: never parsed, stripped or re-serialized.
    message = normalize_message(
        {"role": "assistant", "content": None, "tool_calls": [_call("c1", "t", arguments)]}
    )

    assert message.tool_calls[0].arguments == arguments
    assert type(message.tool_calls[0].arguments) is str


def _assistant(*calls):
    return {"role": "assistant", "content": None, "tool_calls": list(calls)}


def _call_without(key):
    call = _call("c1")
    del call[key]
    return call


def _function_without(key):
    call = _call("c1")
    del call["function"][key]
    return call


@pytest.mark.parametrize(
    "raw, rule",
    [
        ({"role": "user", "content": "x", "tool_calls": _ONE_CALL}, "tool_calls are only allowed on assistant"),
        ({"role": "system", "content": "x", "tool_calls": _ONE_CALL}, "tool_calls are only allowed on assistant"),
        (
            {"role": "tool", "tool_call_id": "c1", "content": "x", "tool_calls": _ONE_CALL},
            "tool_calls are only allowed on assistant",
        ),
        # Non-null empty list on a non-assistant role is still refused; only null is absent.
        ({"role": "user", "content": "x", "tool_calls": []}, "tool_calls are only allowed on assistant"),
        ({"role": "assistant", "content": None, "tool_calls": {}}, "tool_calls must be a list"),
        ({"role": "assistant", "content": None, "tool_calls": "c1"}, "tool_calls must be a list"),
        (_assistant("c1"), r"tool_calls\[0\] is not an object"),
        (_assistant(_call_without("id")), r"tool_calls\[0\]\.id must be a non-empty string"),
        (_assistant(_call("")), r"tool_calls\[0\]\.id must be a non-empty string"),
        (_assistant(_call(3)), r"tool_calls\[0\]\.id must be a non-empty string"),
        (_assistant(_call_without("type")), r'tool_calls\[0\]\.type must be "function"'),
        (_assistant({**_call("c1"), "type": "custom"}), r'tool_calls\[0\]\.type must be "function"'),
        (_assistant(_call_without("function")), r"tool_calls\[0\]\.function is not an object"),
        (_assistant({**_call("c1"), "function": "ls"}), r"tool_calls\[0\]\.function is not an object"),
        (_assistant(_function_without("name")), r"tool_calls\[0\]\.function\.name"),
        (_assistant(_call("c1", "")), r"tool_calls\[0\]\.function\.name"),
        (
            _assistant(_call("c0"), _function_without("arguments") | {"id": "c1"}),
            r"tool_calls\[1\]\.function\.arguments must be a string",
        ),
        (
            _assistant(_call("c0"), _call("c1", arguments={"a": 1})),
            r"tool_calls\[1\]\.function\.arguments must be a string",
        ),
        (
            _assistant(_call("c0"), _call("c1", arguments=None)),
            r"tool_calls\[1\]\.function\.arguments must be a string",
        ),
        (_assistant(_call("c1"), _call("c1")), r"tool_calls\[1\]\.id repeats an earlier id"),
        ({"role": "tool", "content": "x"}, "tool_call_id is required on tool messages"),
        ({"role": "tool", "tool_call_id": "", "content": "x"}, "tool_call_id is required on tool messages"),
        ({"role": "tool", "tool_call_id": None, "content": "x"}, "tool_call_id is required on tool messages"),
        ({"role": "tool", "tool_call_id": 7, "content": "x"}, "tool_call_id is required on tool messages"),
        ({"role": "user", "content": "x", "tool_call_id": "c1"}, "tool_call_id is only allowed on tool messages"),
        ({"role": "assistant", "content": "x", "tool_call_id": "c1"}, "tool_call_id is only allowed on tool messages"),
        ({"role": "system", "content": "x", "tool_call_id": "c1"}, "tool_call_id is only allowed on tool messages"),
    ],
    ids=[
        "tool-calls-on-user",
        "tool-calls-on-system",
        "tool-calls-on-tool",
        "empty-tool-calls-on-user",
        "tool-calls-dict",
        "tool-calls-string",
        "item-not-an-object",
        "id-missing",
        "id-empty",
        "id-not-a-string",
        "type-missing",
        "type-custom",
        "function-missing",
        "function-a-string",
        "name-missing",
        "name-empty",
        "arguments-missing-second-call",
        "arguments-dict-second-call",
        "arguments-null-second-call",
        "duplicate-ids",
        "tool-id-missing",
        "tool-id-empty",
        "tool-id-null",
        "tool-id-int",
        "tool-call-id-on-user",
        "tool-call-id-on-assistant",
        "tool-call-id-on-system",
    ],
)
def test_refuses_tool_shape(raw, rule):
    with pytest.raises(MessageNormalizationError, match=rule):
        normalize_message(raw)


def test_tool_shape_error_names_message_index():
    bad = _assistant(_call("c0"), _call("c1", arguments=None))

    with pytest.raises(MessageNormalizationError) as caught:
        normalize_messages([{"role": "user", "content": "x"}, bad])

    assert str(caught.value).startswith("messages[1]: tool_calls[1].function.arguments")


def test_normalize_messages_accepts_a_client_tool_loop():
    # The normalizer checks per-message shape only; the D6 cross-message rules
    # (every call answered, order) are STORY-005's.
    result = normalize_messages(
        [
            {"role": "system", "content": "be brief"},
            {"role": "user", "content": "list files"},
            {"role": "assistant", "content": None, "tool_calls": _TWO_CALLS},
            {"role": "tool", "tool_call_id": "c1", "content": "a"},
            {"role": "tool", "tool_call_id": "c2", "content": "b"},
        ]
    )

    assert result == [
        Message("system", "be brief"),
        Message("user", "list files"),
        Message("assistant", "", _TWO_SPECS),
        Message("tool", "a", tool_call_id="c1"),
        Message("tool", "b", tool_call_id="c2"),
    ]


@pytest.mark.parametrize(
    "raw",
    ["hello", b"hi", None, {"role": "user"}],
    ids=["str", "bytes", "none", "mapping"],
)
def test_normalize_messages_refuses_a_string_or_non_sequence(raw):
    with pytest.raises(MessageNormalizationError, match="messages must be a list"):
        normalize_messages(raw)


# --- structural compatibility with PRD-009's dedup_key -----------------------


@pytest.mark.parametrize(
    "prompt",
    ["summarise this week's incidents", "acentuación y emoji 🙂", ""],
    ids=["ascii", "non-ascii", "empty"],
)
def test_message_list_keys_like_a_structural_user_turn(prompt):
    # PRD-010 STORY-007 deletes query_pipeline._UserTurn: this now compares
    # against the file's own local `_Turn` stand-in (same pattern already used
    # by test_multi_turn_message_list_matches_structural_turns below), instead
    # of a private pipeline class. The assertion itself is unchanged.
    assert dedup_key(_JUAN, [Message("user", prompt)]) == dedup_key(
        _JUAN, [_Turn("user", prompt)]
    )


def test_message_list_matches_pinned_single_turn_digest():
    """The digest pinned in tests/test_dedup_key.py:74, reached through `Message`."""
    key = dedup_key(_JUAN, [Message("user", "summarise this week's incidents")])

    assert key == "0b206c744aa7f9f63562d512657e199713e403130a76a0eda9f75c0743484652"


def test_multi_turn_message_list_matches_structural_turns():
    as_messages = [Message("user", "list files"), Message("assistant", "README.md app tests"), Message("user", "yes")]
    as_turns = [_Turn("user", "list files"), _Turn("assistant", "README.md app tests"), _Turn("user", "yes")]

    assert dedup_key(_JUAN, as_messages) == dedup_key(_JUAN, as_turns)
    # Pinned in tests/test_dedup_key.py:83.
    assert dedup_key(_JUAN, as_messages) == "c63baa9722eff55aed5b2e29db3316b4972843bb43dfb7f7f38cc7068ada4705"


def test_normalized_output_feeds_dedup_key():
    normalized = normalize_messages(
        [
            {"role": "user", "content": [_text("hi")]},
            {"role": "assistant", "content": "hello"},
            {"role": "user", "content": "yes"},
        ]
    )

    assert dedup_key(_JUAN, normalized) == dedup_key(
        _JUAN, [Message("user", "hi"), Message("assistant", "hello"), Message("user", "yes")]
    )


def _imported_modules(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            modules.add(node.module or "")
    return tree, modules


def test_no_import_in_either_direction():
    _, from_messages = _imported_modules(_ROOT / "app" / "models" / "messages.py")
    _, from_checker = _imported_modules(_ROOT / "app" / "services" / "duplicate_checker.py")

    assert from_messages <= {"dataclasses", "typing"}
    assert not any("messages" in module for module in from_checker)


def test_is_pure():
    # Checked on the syntax tree, not the source text: the module docstring
    # says "no settings, no pydantic", which a substring test would trip on.
    tree, _ = _imported_modules(Path(inspect.getsourcefile(messages_module)))
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    names |= {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}

    assert not names & {"settings", "open", "httpx", "pydantic", "log_query", "redact"}


# --- PRD-017 STORY-005: conversation shape (D6, Section 6.3) -------------------

_FOLLOWS = "a tool turn must follow an assistant turn with tool_calls, with only tool turns between"
_ID_RULE = "tool_call_id is not an id of the preceding assistant turn's tool_calls"
_ANSWERED = "tool_call_id answers a call that was already answered"
_LAST = "the last message must be a user or tool turn"
_NEEDS_USER = "the conversation must contain a user turn"


def _u(text="hi"):
    return Message("user", text)


def _a(text, *ids):
    return Message("assistant", text, tuple(ToolCallSpec(i, "ls", "{}") for i in ids))


def _t(call_id, text="out"):
    return Message("tool", text, tool_call_id=call_id)


@pytest.mark.parametrize(
    "messages",
    [
        pytest.param([_u()], id="user-only"),
        pytest.param(
            [Message("system", "s"), _u(), Message("assistant", "a"), _u()], id="text-history"
        ),
        pytest.param([_u(), _a("", "c1", "c2"), _t("c1"), _t("c2")], id="two-calls-answered"),
        pytest.param([_u(), _a("", "c1", "c2"), _t("c2")], id="partial-answer"),
        pytest.param([_u(), _a("", "c1"), _t("c1"), _a("", "c2"), _t("c2")], id="two-rounds"),
        pytest.param([_u(), _a("", "c1"), _t("c1"), _a("", "c1"), _t("c1")], id="id-reused-across-rounds"),
        pytest.param([_u(), _a("", "c1"), _t("c1"), _a("done"), _u()], id="loop-then-user"),
        # Non-empty is the caller's check (location `messages`, not `messages[i]`).
        pytest.param([], id="empty-is-the-callers"),
    ],
)
def test_shape_accepts(messages):
    assert conversation_shape_violation(messages) is None


_SHAPE_REFUSALS = [
    pytest.param([_u(), Message("assistant", "a")], (1, _LAST), id="last-assistant"),
    pytest.param([_u(), Message("system", "s")], (1, _LAST), id="last-system"),
    pytest.param([_a("", "c1"), _t("c1"), Message("assistant", "a")], (2, _LAST), id="last-assistant-after-tools"),
    pytest.param([_t("c1"), _u()], (0, _FOLLOWS), id="tool-first"),
    pytest.param([_u(), _a("", "c1"), _t("c9")], (2, _ID_RULE), id="unknown-id"),
    pytest.param([_u(), _a("", "c1"), _u(), _t("c1")], (3, _FOLLOWS), id="separated-by-user"),
    pytest.param(
        [_u(), _a("", "c1"), Message("assistant", "x"), _t("c1")], (3, _FOLLOWS),
        id="separated-by-callless-assistant",
    ),
    pytest.param([_u(), _a("", "c1"), _t("c1"), _t("c1")], (3, _ANSWERED), id="answered-twice"),
    pytest.param(
        [_u(), _a("", "c1"), Message("tool", "o", tool_call_id=None)], (2, _ID_RULE), id="tool-call-id-none"
    ),
    # R1 (PRD-017 Section 6.3): no user turn anywhere.
    pytest.param([_a("", "c1"), _t("c1")], (1, _NEEDS_USER), id="no-user-turn"),
    pytest.param([_t("c1"), _u(), Message("assistant", "x")], (0, _FOLLOWS), id="first-violation-wins"),
]


@pytest.mark.parametrize("messages, expected", _SHAPE_REFUSALS)
def test_shape_refuses(messages, expected):
    assert conversation_shape_violation(messages) == expected


@pytest.mark.parametrize("messages, expected", _SHAPE_REFUSALS)
def test_shape_rule_never_echoes_values(messages, expected):
    canary = "SECRET-7f3a"
    # Same structure, canary-bearing content and ids: the verdict is unchanged.
    swapped = [
        Message(
            m.role,
            canary,
            tuple(ToolCallSpec(canary + c.id, c.name, canary) for c in m.tool_calls),
            canary + m.tool_call_id if m.tool_call_id is not None else None,
        )
        for m in messages
    ]
    violation = conversation_shape_violation(swapped)
    assert violation is not None
    assert violation[0] == expected[0]
    assert canary not in violation[1]


def test_shape_helper_signature():
    assert list(inspect.signature(conversation_shape_violation).parameters) == ["messages"]
