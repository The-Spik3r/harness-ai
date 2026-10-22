"""PRD-015 STORY-005: `translate_messages`.

The client's `messages` reach the pipeline as `normalize_messages` would build
them, with `developer` as `system` and `name` reported as ignored. Everything
else is a `V1RequestError` naming a location and a rule, never the content
(canary tests). The edge checks make `_validate_conversation` unreachable: a
seeded property test feeds every accepted input to it. No DB.
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import ast
import copy
import inspect
import random
import re
from pathlib import Path

import pytest

import app.services.v1_translate as v1_translate_module
from app.models.messages import Message, MessageNormalizationError, normalize_messages
from app.services.query_pipeline import _validate_conversation
from app.services.v1_translate import (
    IGNORED_MESSAGE_NAME,
    INVALID_MESSAGES,
    TOOLS_NOT_SUPPORTED,
    V1RequestError,
    translate_messages,
)

_CANARY = "jane@corp.com SECRET-CANARY"


def _text(text):
    return {"type": "text", "text": text}


def _image(url="https://x/y.png"):
    return {"type": "image_url", "image_url": {"url": url}}


_USER = {"role": "user", "content": "go on"}


# --- AC 1: the normalizer's output, unchanged --------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        [{"role": "user", "content": "hi"}],
        [{"role": "system", "content": "be brief"}, {"role": "user", "content": [_text("a"), _text("b")]}],
        [{"role": "user", "content": "list"}, {"role": "assistant", "content": None}, _USER],
        [{"role": "user", "content": "list"}, {"role": "assistant"}, _USER],
        [{"role": "user", "content": []}],
    ],
    ids=[
        "string-content",
        "text-part-list",
        "assistant-null-content",
        "assistant-missing-content",
        "empty-part-list",
    ],
)
def test_equals_the_normalizer(raw):
    messages, ignored = translate_messages(raw)

    assert messages == normalize_messages(raw)
    assert ignored == frozenset()


# --- AC 2: developer and name ------------------------------------------------


def test_developer_becomes_system():
    messages, _ = translate_messages([{"role": "developer", "content": "be brief"}, _USER])

    assert messages == [Message("system", "be brief"), Message("user", "go on")]


def test_developer_text_parts_are_joined_like_system():
    messages, _ = translate_messages([{"role": "developer", "content": [_text("a"), _text("b")]}, _USER])

    assert messages[0] == Message("system", "a\nb")


def test_developer_null_content_follows_the_system_rule():
    with pytest.raises(V1RequestError) as caught:
        translate_messages([{"role": "developer", "content": None}, _USER])

    assert caught.value.code == INVALID_MESSAGES
    assert caught.value.param == "messages[0]"
    assert "null content" in caught.value.message


def test_name_is_ignored_and_reported_once():
    raw = [
        {"role": "user", "content": "a", "name": "bob"},
        {"role": "assistant", "content": "b", "name": "helper"},
        {"role": "user", "content": "c"},
    ]

    messages, ignored = translate_messages(raw)

    assert messages == [Message("user", "a"), Message("assistant", "b"), Message("user", "c")]
    assert ignored == frozenset({"messages[].name"})
    assert IGNORED_MESSAGE_NAME == "messages[].name"


def test_name_is_recorded_on_presence_even_when_null():
    _, ignored = translate_messages([{"role": "user", "content": "a", "name": None}])

    assert ignored == frozenset({IGNORED_MESSAGE_NAME})


# --- AC 3: refusals ----------------------------------------------------------


@pytest.mark.parametrize(
    "raw, code, param, rule",
    [
        ([], INVALID_MESSAGES, "messages", "must not be empty"),
        (
            [_USER, {"role": "tool", "content": "out"}, _USER],
            TOOLS_NOT_SUPPORTED,
            "messages[1]",
            "tool turns are not supported",
        ),
        (
            [
                {"role": "assistant", "content": None, "tool_calls": [{"id": "c1", "type": "function"}]},
                _USER,
            ],
            TOOLS_NOT_SUPPORTED,
            "messages[0]",
            "tool calls are not supported",
        ),
        (
            [{"role": "assistant", "content": "x", "tool_calls": []}, _USER],
            TOOLS_NOT_SUPPORTED,
            "messages[0]",
            "tool calls are not supported",
        ),
        (
            [{"role": "assistant", "content": None, "function_call": {"name": "ls"}}, _USER],
            TOOLS_NOT_SUPPORTED,
            "messages[0]",
            "tool calls are not supported",
        ),
        (
            [_USER, {"role": "assistant", "content": "sure"}],
            INVALID_MESSAGES,
            "messages[1]",
            "the last message must be a user turn",
        ),
        (
            [{"role": "system", "content": "be brief"}],
            INVALID_MESSAGES,
            "messages[0]",
            "the last message must be a user turn",
        ),
        (
            [{"role": "user", "content": [_text("a"), _image()]}],
            INVALID_MESSAGES,
            "messages[0]",
            r"content\[1\] is not a text part",
        ),
        ([{"role": "function", "content": "x"}, _USER], INVALID_MESSAGES, "messages[0]", "unknown role"),
        ([{"role": "user", "content": None}], INVALID_MESSAGES, "messages[0]", "null content"),
        (["hi"], INVALID_MESSAGES, "messages[0]", "message is not an object"),
        ("hi", INVALID_MESSAGES, "messages", "must be a list"),
    ],
    ids=[
        "empty-list",
        "tool-role",
        "tool-calls-key",
        "tool-calls-empty-list",
        "function-call-key",
        "last-not-user",
        "only-system",
        "image-part",
        "unknown-role",
        "null-user-content",
        "not-an-object",
        "not-a-list",
    ],
)
def test_refuses(raw, code, param, rule):
    with pytest.raises(V1RequestError) as caught:
        translate_messages(raw)

    exc = caught.value
    assert exc.code == code
    assert exc.param == param
    assert re.search(rule, exc.message)
    assert str(exc) == exc.message
    assert exc.message.startswith(f"{param}: ") or param == "messages"


@pytest.mark.parametrize(
    "raw",
    [
        [{"role": "user", "content": [_text("a"), _image()]}],
        [{"role": "function", "content": "x"}, _USER],
        [{"role": "user", "content": None}],
        ["hi"],
    ],
    ids=["image-part", "unknown-role", "null-user-content", "not-an-object"],
)
def test_normalizer_failure_is_wrapped_with_its_text_kept(raw):
    with pytest.raises(V1RequestError) as caught:
        translate_messages(raw)

    exc = caught.value
    assert isinstance(exc.__cause__, MessageNormalizationError)
    assert exc.message == f"{exc.param}: {exc.__cause__}"


def test_first_failure_wins_tool_turn_before_last_not_user():
    with pytest.raises(V1RequestError) as caught:
        translate_messages([{"role": "tool", "content": "out"}, {"role": "assistant", "content": "x"}])

    assert caught.value.code == TOOLS_NOT_SUPPORTED
    assert caught.value.param == "messages[0]"


def test_tool_calls_are_checked_before_the_normalizer():
    raw = [{"role": "user", "content": [_image()], "tool_calls": []}]

    with pytest.raises(V1RequestError) as caught:
        translate_messages(raw)

    assert caught.value.code == TOOLS_NOT_SUPPORTED


def test_codes_are_the_constants():
    assert INVALID_MESSAGES == "invalid_messages"
    assert TOOLS_NOT_SUPPORTED == "tools_not_supported"


def test_v1_request_error_param_defaults_to_none():
    exc = V1RequestError("invalid_parameter", "temperature must be a number")

    assert (exc.code, exc.message, exc.param) == ("invalid_parameter", "temperature must be a number", None)


# --- T6: errors never echo content -------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        [{"role": "user", "content": [_text(_CANARY), _image(_CANARY)]}],
        [_USER, {"role": "tool", "content": _CANARY}, _USER],
        [{"role": "assistant", "content": _CANARY, "tool_calls": [{"id": _CANARY}]}, _USER],
        [{"role": "developer-CANARY", "content": "x"}, _USER],
        [{"role": "user", "content": _CANARY, "name": _CANARY}, {"role": "assistant", "content": _CANARY}],
        [{"role": "developer", "content": None, "name": _CANARY}, _USER],
    ],
    ids=[
        "image-part-beside-canary-text",
        "tool-role-with-canary-content",
        "tool-calls-holding-canary",
        "canary-role-value",
        "canary-name-on-last-not-user",
        "developer-null-with-canary-name",
    ],
)
def test_error_never_echoes_content(raw):
    with pytest.raises(V1RequestError) as caught:
        translate_messages(raw)

    exc = caught.value
    assert "CANARY" not in str(exc)
    assert "CANARY" not in exc.param
    assert "CANARY" not in repr(exc.__cause__)


# --- input handling ----------------------------------------------------------


def test_input_is_never_mutated():
    raw = [{"role": "developer", "content": "be brief", "name": "ops"}, {"role": "user", "content": "x"}]
    before = copy.deepcopy(raw)

    translate_messages(raw)

    assert raw == before
    assert raw[0]["role"] == "developer"


def test_accepts_any_sequence():
    raw = ({"role": "system", "content": "s"}, {"role": "user", "content": "u"})

    assert translate_messages(raw) == translate_messages(list(raw))


def _imported_modules(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            modules.add(node.module or "")
    return tree, modules


def test_is_pure():
    # Checked on the syntax tree, as test_messages.py does: the docstrings
    # name `query_pipeline` and "no logging", which a substring test would trip on.
    tree, modules = _imported_modules(Path(inspect.getsourcefile(v1_translate_module)))
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    names |= {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}

    assert modules <= {"typing", "app.models.messages"}
    assert not names & {"settings", "open", "httpx", "log_query", "logging", "logger", "query_pipeline"}


# --- AC 4: accepted input never trips the pipeline guard ---------------------
#
# Seeded `random.Random`, not hypothesis (not installed; no new dependency).
# Each seed is its own test id, so a failure reproduces from `[seed-N]`.

_SEEDS = range(500)
# Weighted toward valid shapes so about half the lists are accepted; the
# invalid ones (`tool`, `function`, no role, image parts, ints) still appear.
_ROLES = ["system", "developer", "user", "user", "user", "assistant", "assistant", "tool", "function", None]


def _random_content(rng):
    pick = rng.randrange(10)
    if pick < 4:
        return rng.choice(["hi", "list files", "ignore previous"])
    if pick == 4:
        return ""
    if pick < 7:
        return [_text(rng.choice(["a", "b", "c"])) for _ in range(rng.randrange(4))]
    if pick == 7:
        return None
    if pick == 8:
        return [_image()]
    return 3


def _random_message(rng):
    # Half are ordinary turns: real conversations are mostly well formed, and
    # without this almost every multi-turn list is refused at some index.
    if rng.random() < 0.5:
        return {"role": rng.choice(["system", "developer", "user", "assistant"]), "content": "ok"}
    message = {"content": _random_content(rng)}
    role = rng.choice(_ROLES)
    if role is not None:
        message["role"] = role
    if rng.random() < 0.1:
        message["name"] = "n"
    if rng.random() < 0.05:
        message["tool_calls"] = []
    return message


def _random_messages(rng):
    raw = [_random_message(rng) for _ in range(rng.randrange(5))]
    if raw and rng.random() < 0.6:
        raw[-1] = {"role": "user", "content": rng.choice(["hi", "yes", ""])}
    return raw


def _translate_or_none(seed):
    try:
        return translate_messages(_random_messages(random.Random(seed)))[0]
    except V1RequestError:
        return None


@pytest.mark.parametrize("seed", _SEEDS)
def test_accepted_input_never_trips_the_pipeline_guard(seed):
    messages = _translate_or_none(seed)
    if messages is None:
        return

    # No pytest.raises: an InvalidConversationError fails this seed's id.
    _validate_conversation(messages)


def test_property_generator_is_not_degenerate():
    accepted = sum(_translate_or_none(seed) is not None for seed in _SEEDS)

    assert accepted >= len(_SEEDS) * 0.25
    assert len(_SEEDS) - accepted >= len(_SEEDS) * 0.25
