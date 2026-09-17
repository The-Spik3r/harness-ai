"""PRD-010 STORY-001: `Message`, `Role` and the OpenAI content normalizer.

Every row of PRD-010 Section 6.2's table is one named parametrize case below.
The normalizer has no production caller in this PRD -- PRD-014 is its first
ingress -- so these tests are the whole contract until then. Errors name a
location and a rule and never the content (canary tests), and `Message` keys
exactly like the pipeline's turn does today, with no import between this module
and `duplicate_checker` in either direction.
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
import app.services.query_pipeline as query_pipeline
from app.models.messages import (
    Message,
    MessageNormalizationError,
    Role,
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


def test_exports_the_specified_names_and_signatures():
    assert get_args(Role) == ("system", "user", "assistant", "tool")
    assert list(inspect.signature(normalize_message).parameters) == ["raw"]
    assert list(inspect.signature(normalize_messages).parameters) == ["raw"]
    assert [f.name for f in dataclasses.fields(Message)] == ["role", "content"]
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
        ({"role": "tool", "content": "ls output"}, Message("tool", "ls output")),
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
        ({"role": "tool", "content": None}, "null content"),
        # The exact OpenAI tool-call shape: content null *and* tool_calls. It
        # must hit the PRD-016 rule, not normalize to "" (check order).
        (
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "ls", "arguments": "{}"}}],
            },
            "PRD-016",
        ),
        ({"role": "developer", "content": "hi"}, "unknown role"),
    ],
    ids=[
        "image-url-part",
        "null-on-user",
        "null-on-system",
        "null-on-tool",
        "tool-calls-key",
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
        ({"role": "assistant", "content": "x", "tool_calls": []}, "PRD-016"),
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
        "tool-calls-empty-list",
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
    ],
    ids=[
        "image-part-beside-canary-text",
        "unknown-role-with-canary-content",
        "tool-calls-with-canary-content",
        "canary-role-value",
        "canary-part-type",
        "non-str-text-holding-canary",
        "dict-content-holding-canary",
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
def test_message_list_keys_like_the_pipeline_user_turn_today(prompt):
    # STORY-007 deletes _UserTurn: replace this reference with the pinned digest
    # from test_dedup_key.py:74, never delete the assertion.
    assert dedup_key(_JUAN, [Message("user", prompt)]) == dedup_key(
        _JUAN, [query_pipeline._UserTurn(prompt)]
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
