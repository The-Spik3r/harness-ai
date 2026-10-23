"""PRD-015 STORY-005 `translate_messages` and STORY-006 `translate_request`.

The client's `messages` reach the pipeline as `normalize_messages` would build
them, with `developer` as `system` and `name` reported as ignored. Everything
else is a `V1RequestError` naming a location and a rule, never the content
(canary tests). The edge checks make `_validate_conversation` unreachable: a
seeded property test feeds every accepted input to it.

STORY-006: every other key is forwarded, refused unless it is the default, or
ignored with its name recorded. Only the T5 upstream-body test needs the DB.
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import ast
import copy
import inspect
import json
import random
import re
from dataclasses import fields
from pathlib import Path

import pytest

import app.services.query_pipeline as query_pipeline
import app.services.v1_translate as v1_translate_module
from app.db.database import insert_user
from app.db.models import User
from app.models.messages import Message, MessageNormalizationError, normalize_messages
from app.models.schemas import QuerySuccessResponse
from app.models.v1_schemas import ChatCompletionRequest
from app.services.identity import Identity, hash_token
from app.services.openrouter_client import GenerationParams
from app.services.query_pipeline import _validate_conversation
from app.services.v1_translate import (
    FORWARDED,
    IGNORED_MESSAGE_NAME,
    INVALID_MESSAGES,
    INVALID_PARAMETER,
    REJECTED_UNLESS_DEFAULT,
    TOOLS_NOT_SUPPORTED,
    UNSUPPORTED_PARAMETER,
    V1Call,
    V1RequestError,
    _STRUCTURAL,
    translate_messages,
    translate_request,
)
from tests.test_v1_query_isolation import _capturing_transport, _mask_nothing, _upstream_over

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

    assert modules <= {
        "typing",
        "dataclasses",
        "app.models.messages",
        # STORY-009: translate_result reads QuerySuccessResponse (pydantic only).
        "app.models.schemas",
        "app.models.v1_schemas",
        "app.services.openrouter_client",
    }
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


# === STORY-006: translate_request ============================================


def _body(**extra):
    return ChatCompletionRequest.model_validate({"model": "gpt-4", "messages": [_USER], **extra})


def _refusal(**extra):
    with pytest.raises(V1RequestError) as caught:
        translate_request(_body(**extra))
    return caught.value


# --- AC 1: forwarded ---------------------------------------------------------


def test_forwarded_params_become_generation_params():
    call = translate_request(_body(temperature=0.2, top_p=0.9, max_tokens=100, stop=["END"]))

    assert call.params == GenerationParams(temperature=0.2, max_tokens=100, top_p=0.9, stop=["END"])
    assert call.ignored_params is None


def test_nothing_forwarded_is_params_none():
    assert translate_request(_body()).params is None


def test_explicit_null_forwarded_is_absent_and_not_ignored():
    call = translate_request(_body(temperature=None, top_p=None, max_tokens=None, stop=None))

    assert call.params is None
    assert call.ignored_params is None


def test_integer_temperature_is_a_number():
    assert translate_request(_body(temperature=1)).params == GenerationParams(temperature=1)


def test_max_completion_tokens_alone_becomes_max_tokens():
    call = translate_request(_body(max_completion_tokens=50))

    assert call.params == GenerationParams(max_tokens=50)
    assert call.ignored_params is None


def test_max_tokens_and_max_completion_tokens_equal_are_forwarded_once():
    call = translate_request(_body(max_tokens=50, max_completion_tokens=50))

    assert call.params == GenerationParams(max_tokens=50)


def test_max_completion_tokens_with_null_max_tokens():
    call = translate_request(_body(max_tokens=None, max_completion_tokens=7))

    assert call.params == GenerationParams(max_tokens=7)


def test_max_tokens_and_max_completion_tokens_different_are_refused():
    exc = _refusal(max_tokens=50, max_completion_tokens=60)

    assert exc.code == INVALID_PARAMETER
    assert exc.param == "max_completion_tokens"
    assert exc.message == "max_completion_tokens: must equal max_tokens when both are sent"


_INVALID_FORWARDED = [
    ("temperature", 2.5),
    ("temperature", -0.1),
    ("temperature", "hot"),
    ("temperature", True),
    ("temperature", float("nan")),
    ("top_p", 0),
    ("top_p", 1.5),
    ("top_p", "0.5"),
    ("max_tokens", 0),
    ("max_tokens", 1.5),
    ("max_tokens", "5"),
    ("max_tokens", True),
    ("max_completion_tokens", 0),
    ("max_completion_tokens", 2.0),
    ("stop", ["a", "b", "c", "d", "e"]),
    ("stop", [1]),
    ("stop", {}),
]


@pytest.mark.parametrize(
    "key, value", _INVALID_FORWARDED, ids=[f"{key}={value!r}" for key, value in _INVALID_FORWARDED]
)
def test_forwarded_out_of_range_or_wrong_type_is_invalid_parameter(key, value):
    # No TypeError escapes: GenerationParams alone raises one for "hot" and "5".
    exc = _refusal(**{key: value})

    assert exc.code == INVALID_PARAMETER
    assert exc.param == key
    assert exc.message.startswith(f"{key}: ")
    assert exc.__cause__ is None


def test_forwarded_checks_run_in_table_order():
    assert _refusal(temperature=9, stop=[1]).param == "temperature"


# --- AC 2: unsupported -------------------------------------------------------


@pytest.mark.parametrize(
    "key, value",
    [
        ("n", 2),
        ("n", True),
        ("n", 1.0),
        ("logprobs", True),
        ("top_logprobs", 3),
        ("top_logprobs", 0),
        ("response_format", {"type": "json_object"}),
        ("response_format", {"type": "json_schema", "json_schema": {"name": "x"}}),
        ("response_format", "text"),
        ("modalities", ["text", "audio"]),
        ("modalities", "text"),
        ("audio", {"voice": "alloy", "format": "wav"}),
    ],
    ids=[
        "n-2",
        "n-true",
        "n-float",
        "logprobs-true",
        "top-logprobs-3",
        "top-logprobs-0",
        "json-object",
        "json-schema",
        "response-format-bare-string",
        "audio-modality",
        "modalities-bare-string",
        "audio",
    ],
)
def test_non_default_is_unsupported_parameter(key, value):
    exc = _refusal(**{key: value})

    assert exc.code == UNSUPPORTED_PARAMETER
    assert exc.param == key
    assert exc.message == f"{key}: only the default value is supported on this endpoint"


@pytest.mark.parametrize(
    "extra",
    [
        {"n": 1},
        {"n": None},
        {"logprobs": False},
        {"logprobs": None},
        {"top_logprobs": None},
        {"response_format": {"type": "text"}},
        {"modalities": ["text"]},
        {"audio": None},
    ],
    ids=[
        "n-1",
        "n-null",
        "logprobs-false",
        "logprobs-null",
        "top-logprobs-null",
        "text-format",
        "text-modality",
        "audio-null",
    ],
)
def test_default_is_accepted_and_not_ignored(extra):
    call = translate_request(_body(**extra))

    assert call.ignored_params is None
    assert call.params is None


# --- AC 3: tools -------------------------------------------------------------

_TOOL = {"type": "function", "function": {"name": "ls", "parameters": {}}}


@pytest.mark.parametrize(
    "key, value",
    [
        ("tools", [_TOOL]),
        ("functions", [{"name": "ls"}]),
        ("tool_choice", "auto"),
        ("tool_choice", "required"),
        ("tool_choice", {"type": "function", "function": {"name": "ls"}}),
        ("function_call", "auto"),
        ("function_call", "none"),
        ("function_call", {"name": "ls"}),
    ],
    ids=[
        "tools",
        "functions",
        "tool-choice-auto",
        "tool-choice-required",
        "tool-choice-named",
        "function-call-auto",
        "function-call-none",
        "function-call-named",
    ],
)
def test_tool_use_is_tools_not_supported(key, value):
    exc = _refusal(**{key: value})

    assert exc.code == TOOLS_NOT_SUPPORTED
    assert exc.param == key
    assert exc.message == f"{key}: tool calling is not supported (PRD-016)"


@pytest.mark.parametrize(
    "extra",
    [
        {"tools": []},
        {"tools": None},
        {"functions": []},
        {"tool_choice": "none"},
        {"tools": [], "tool_choice": "none"},
        {"function_call": None},
    ],
    ids=[
        "tools-empty",
        "tools-null",
        "functions-empty",
        "tool-choice-none",
        "both-defaults",
        "function-call-null",
    ],
)
def test_tools_defaults_are_accepted(extra):
    assert translate_request(_body(**extra)).ignored_params is None


def test_tools_refusal_comes_before_every_other_check():
    exc = _refusal(n=2, temperature=9, tools=[_TOOL], messages=[{"role": "tool", "content": "x"}])

    assert (exc.code, exc.param) == (TOOLS_NOT_SUPPORTED, "tools")


# --- AC 4: ignored -----------------------------------------------------------

_AC4_IGNORED = {
    "seed": 7,
    "user": "jane",
    "presence_penalty": 0.5,
    "logit_bias": {"50256": -100},
    "metadata": {"k": "v"},
    "profile": "permissive",
    "ingress": "query",
    "openrouter_api_key": "sk-or-x",
    "x_custom": True,
}


def test_ignored_names_sorted_comma_joined():
    call = translate_request(
        _body(stream=True, stream_options={"include_usage": True, "foo": 1}, **_AC4_IGNORED)
    )

    assert call.ignored_params == (
        "ingress,logit_bias,metadata,openrouter_api_key,presence_penalty,"
        "profile,seed,stream_options.foo,user,x_custom"
    )
    assert call.include_usage is True
    assert call.params is None


def test_ignored_values_never_appear():
    body = _body(
        stream=True,
        stream_options={"include_usage": False, "foo": _CANARY},
        **{key: _CANARY for key in _AC4_IGNORED},
    )

    call = translate_request(body)

    assert "CANARY" not in repr(call)
    assert call.include_usage is False


def test_nothing_ignored_is_none():
    call = translate_request(_body(stream=True, stream_options={"include_usage": True}))

    assert call.ignored_params is None


def test_ignored_key_is_recorded_even_when_null():
    assert translate_request(_body(seed=None)).ignored_params == "seed"


def test_message_name_merges_and_is_listed_once():
    messages = [
        {"role": "user", "content": "a", "name": "bob"},
        {"role": "assistant", "content": "b", "name": "helper"},
        _USER,
    ]

    call = translate_request(_body(messages=messages, seed=1))

    assert call.ignored_params == "messages[].name,seed"


def test_include_usage_only_on_streamed_requests():
    call = translate_request(_body(stream_options={"include_usage": True}))

    assert call.include_usage is False
    assert call.stream is False


@pytest.mark.parametrize(
    "stream_options, param",
    [
        ("yes", "stream_options"),
        ([], "stream_options"),
        ({"include_usage": "true"}, "stream_options.include_usage"),
    ],
    ids=["string", "list", "include-usage-string"],
)
def test_malformed_stream_options_is_invalid_parameter(stream_options, param):
    exc = _refusal(stream=True, stream_options=stream_options)

    assert (exc.code, exc.param) == (INVALID_PARAMETER, param)
    assert exc.message.startswith(f"{param}: ")


def test_model_and_stream_pass_through():
    call = translate_request(
        ChatCompletionRequest.model_validate({"model": "x/y", "messages": [_USER], "stream": True})
    )

    assert (call.model, call.stream, call.include_usage) == ("x/y", True, False)


# --- T4: no field chooses the profile or the door ----------------------------


def test_profile_and_ingress_are_ordinary_ignored_keys():
    call = translate_request(_body(profile="permissive", ingress="query"))

    assert call.ignored_params == "ingress,profile"
    assert {field.name for field in fields(V1Call)} == {
        "messages",
        "params",
        "model",
        "stream",
        "include_usage",
        "ignored_params",
    }


# --- AC 5: the table ---------------------------------------------------------


def test_forwarded_is_generation_params_plus_alias():
    assert FORWARDED == {field.name for field in fields(GenerationParams)} | {"max_completion_tokens"}


def test_the_three_groups_are_disjoint():
    rejected = set(REJECTED_UNLESS_DEFAULT)

    assert not FORWARDED & rejected
    assert not FORWARDED & _STRUCTURAL
    assert not rejected & _STRUCTURAL


def test_every_declared_request_field_is_classified():
    # A field added to ChatCompletionRequest must land in the table; `user` is
    # declared only to document D1 and is ignored like any unknown key.
    classified = FORWARDED | set(REJECTED_UNLESS_DEFAULT) | _STRUCTURAL | {"user"}

    assert set(ChatCompletionRequest.model_fields) == classified


# --- T6: refusals never echo values ------------------------------------------


@pytest.mark.parametrize(
    "extra",
    [
        {"stop": [_CANARY] * 5},
        {"stop": [_CANARY, 1]},
        {"temperature": _CANARY},
        {"n": _CANARY},
        {"tools": [_CANARY]},
        {"stream_options": {"include_usage": _CANARY}},
    ],
    ids=["stop-too-many", "stop-non-string", "temperature-string", "n-string", "tools", "include-usage"],
)
def test_parameter_refusal_never_echoes_the_value(extra):
    exc = _refusal(**extra)

    assert "CANARY" not in str(exc)
    assert "CANARY" not in exc.param
    assert exc.__cause__ is None


# --- messages still go through translate_messages ---------------------------


def test_messages_are_translate_messages_output():
    raw = [{"role": "developer", "content": "be brief"}, _USER]

    assert translate_request(_body(messages=raw)).messages == translate_messages(raw)[0]


def test_message_refusal_surfaces_unchanged():
    exc = _refusal(messages=[_USER, {"role": "assistant", "content": "x"}])

    assert (exc.code, exc.param) == (INVALID_MESSAGES, "messages[1]")


# --- AC 5 / T5: the upstream body is still STORY-001's set -------------------

_AUTH_USER_ID = "juan@empresa.com"


@pytest.fixture
def _v1_user(temp_db):
    """conftest's initialized database, plus the user the pipeline authorizes."""
    insert_user(User(user_id=_AUTH_USER_ID, role="user", token_hash=hash_token("v1-translate-token")))
    return temp_db


def test_translated_request_upstream_body_is_the_t5_set(_v1_user, monkeypatch):
    accepted_defaults = {
        "n": 1,
        "logprobs": False,
        "response_format": {"type": "text"},
        "modalities": ["text"],
        "tools": [],
        "tool_choice": "none",
    }
    body = ChatCompletionRequest.model_validate(
        {
            "model": "gpt-4",
            "messages": [{"role": "user", "content": "hello world"}],
            "temperature": 0.2,
            "top_p": 0.9,
            "max_completion_tokens": 100,
            "stop": ["END"],
            "stream_options": {"include_usage": True, "foo": 1},
            **_AC4_IGNORED,
            **accepted_defaults,
        }
    )
    call = translate_request(body)
    seen: list = []
    monkeypatch.setattr(query_pipeline, "redact", _mask_nothing)

    result = query_pipeline.run_conversation(
        Identity(user_id=_AUTH_USER_ID, role="user"),
        call.messages,
        None,
        call.model,
        None,
        call.params,
        call_openrouter=_upstream_over(_capturing_transport(seen)),
        profile="code",
        ingress="v1",
    )

    assert isinstance(result, QuerySuccessResponse)
    assert len(seen) == 1
    upstream = json.loads(seen[0].content)
    # T5: the keys STORY-001 pinned, in call_openrouter's order, nothing more.
    assert list(upstream) == ["model", "messages", "temperature", "max_tokens", "top_p", "stop"]
    assert upstream["max_tokens"] == 100
    assert not set(upstream) & (set(_AC4_IGNORED) | set(accepted_defaults) | {"stream_options"})
