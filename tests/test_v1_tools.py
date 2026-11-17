"""PRD-017 STORY-008: `/v1` request translation under `V1_TOOLS_ENABLED`.

Covers PRD-017 Sections 4, 6.3, 6.7 and 10 and D6, D10, D11, D16: with the flag on the
translator admits `tools`, `tool_choice`, `parallel_tool_calls` and tool turns, validates
their shape (location and rule, never a value, T6), checks D6 with the shared
`conversation_shape_violation`, and refuses a `tools` request for a model outside a non-empty
`V1_TOOL_MODELS`. The router reads the flag and the list per request, passes `tools=` to
`run_conversation`, which hands it to step 7 only when set. With the flag off the answer is
PRD-015's, byte for byte (D10).

Two layers: the pure translator (no DB), then the router and pipeline through `TestClient`.
Since STORY-010 the pipeline decides and records every call (step 7c). STORY-011 releases the
allowed calls on the non-streamed body, and STORY-012 streams them as one delta per call
(Section 6.6), checked against the `openai` SDK's stream accumulator. The STORY-010 section
at the end covers the decision and its audit.
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import json
import random
import re

import httpx
import pytest
from fastapi.testclient import TestClient

import app.services.query_pipeline as query_pipeline
from app.config import settings
from app.db.database import get_audit_log, get_connection, insert_user
from app.db.errors import StorageError
from app.db.models import User
from app.main import app
from app.models.messages import ToolCallSpec, conversation_shape_violation, normalize_messages
from app.models.schemas import QuerySuccessResponse
from app.models.v1_schemas import (
    AssistantMessage,
    ChatCompletion,
    ChatCompletionRequest,
    Choice,
    CompletionToolCall,
    HarnessAction,
    HarnessCompletionInfo,
    ToolCallFunction,
    Usage,
)
from app.services import action_audit, action_policy, tool_release, v1_sse
from app.services.action_adapters import ToolCall
from app.services.identity import Identity, hash_token
from app.services.openrouter_client import OpenRouterResult, ToolParams
from app.services.openrouter_client import call_openrouter as _real_call_openrouter
from app.services.query_pipeline import ActionAuditError, _validate_conversation
from app.services.v1_translate import (
    FORWARDED,
    REJECTED_UNLESS_DEFAULT,
    TOOL_PARAMS,
    TOOLS_NOT_SUPPORTED,
    V1RequestError,
    _STRUCTURAL,
    translate_request,
)

# PRD-018 D14: `audit_ref` is required on every success (the row's write_id).
_AUDIT_REF = "0" * 32

_MODEL = "openai/gpt-4o"
_PROMPT = "list the files"
_USER = {"role": "user", "content": _PROMPT}
_CANARY = "CANARY-9f3a"
# Whitespace-odd on purpose (Cline re-stringifies compact JSON): kept byte for byte (D13).
_ARGS = '{"path": "a.py" ,"n":1}'
_TOOL = {
    "type": "function",
    "function": {
        "name": "bash",
        "description": "run a command",
        "parameters": {"type": "object", "properties": {"command": {"type": "string"}}},
        "strict": False,
    },
    "x-unknown": {"kept": True},
}
_TOOL_TURNS = [
    _USER,
    {
        "role": "assistant",
        "content": None,
        "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "bash", "arguments": _ARGS}}],
    },
    {"role": "tool", "tool_call_id": "call_1", "content": "README.md\nsrc"},
]


def _body(**extra):
    return ChatCompletionRequest.model_validate({"model": _MODEL, "messages": [_USER], **extra})


def _on(models=(), **extra):
    return translate_request(_body(**extra), tools_enabled=True, tool_models=models)


def _on_refusal(models=(), **extra):
    with pytest.raises(V1RequestError) as caught:
        _on(models, **extra)
    return caught.value


def _off_refusal(**extra):
    with pytest.raises(V1RequestError) as caught:
        translate_request(_body(**extra))
    return caught.value


# --- AC2: values as sent ---------------------------------------------------------------


@pytest.mark.parametrize("choice", ["none", "auto", "required", {"type": "function", "function": {"name": "bash"}}])
@pytest.mark.parametrize("parallel", [True, False])
def test_tool_request_is_forwarded_as_sent(choice, parallel):
    tools = [_TOOL]
    body = _body(tools=tools, tool_choice=choice, parallel_tool_calls=parallel)

    call = translate_request(body, tools_enabled=True)

    assert call.tools == ToolParams(tools=tools, tool_choice=choice, parallel_tool_calls=parallel)
    # F3: the list as received, never a copy, a filter or a re-serialization.
    assert call.tools.tools is body.tools
    assert call.tools.tools[0]["x-unknown"] == {"kept": True}
    # D11: no longer ignored once forwarded.
    assert call.ignored_params is None


def test_null_tool_choice_and_parallel_are_absent_with_tools():
    call = _on(tools=[_TOOL], tool_choice=None, parallel_tool_calls=None)

    assert call.tools == ToolParams(tools=[_TOOL], tool_choice=None, parallel_tool_calls=None)
    assert call.ignored_params is None


@pytest.mark.parametrize("extra", [{}, {"tools": None}, {"tools": []}], ids=["absent", "null", "empty"])
@pytest.mark.parametrize("choice", [{}, {"tool_choice": None}, {"tool_choice": "none"}])
def test_no_tools_means_no_tool_params(extra, choice):
    call = _on(**extra, **choice)

    assert call.tools is None
    assert call.ignored_params is None


def test_tool_choice_without_tools_is_refused():
    for tools in ({}, {"tools": []}):
        exc = _on_refusal(tool_choice="auto", **tools)
        assert (exc.code, exc.param, exc.message) == (
            "invalid_parameter", "tool_choice", "tool_choice: requires a non-empty tools list",
        )


def test_parallel_tool_calls_without_tools_is_recorded_as_ignored():
    # Q2: nothing was forwarded, so it is recorded as with the flag off (D11).
    for value in (True, None):
        assert _on(tools=[], parallel_tool_calls=value).ignored_params == "parallel_tool_calls"
    assert _on(parallel_tool_calls=False).tools is None


# --- Survey fixtures (STORY-001) ---------------------------------------------------------


def test_opencode_shape_is_accepted():
    call = _on(
        tools=[], stream=True, stream_options={"include_usage": True}, max_tokens=64, temperature=0.1,
        messages=[
            _USER,
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "call_1", "type": "function", "function": {"name": "bash", "arguments": _ARGS}}]},
            {"role": "tool", "tool_call_id": "call_1", "content": "ok", "cache_control": {"type": "ephemeral"}},
        ],
    )

    assert call.tools is None
    assert call.messages[1].tool_calls == (ToolCallSpec("call_1", "bash", _ARGS),)
    assert call.messages[2].tool_call_id == "call_1"


def test_cline_shape_is_accepted_and_arguments_are_kept_exactly():
    tools = [
        {"type": "function", "function": {"name": name, "parameters": {"type": "object"}}}
        for name in ("read_file", "write_file", "execute_command", "attempt_completion")
    ]
    call = _on(
        tools=tools, tool_choice="auto",
        messages=[
            _USER,
            {"role": "assistant", "content": "", "reasoning_content": "thinking", "tool_calls": [
                {"id": "c1", "type": "function", "function": {"name": "read_file", "arguments": _ARGS}}]},
            {"role": "tool", "tool_call_id": "c1", "content": "text"},
        ],
    )

    assert call.tools.tools is not None and len(call.tools.tools) == 4
    assert call.messages[1].tool_calls[0].arguments == _ARGS


def test_survey_extra_top_level_keys_are_ignored_not_refused():
    call = _on(store=False, prompt_cache_key="k", reasoning_effort="low", tool_stream=True, seed=1)

    assert call.ignored_params == "prompt_cache_key,reasoning_effort,seed,store,tool_stream"


# --- D10: functions / function_call ---------------------------------------------------


@pytest.mark.parametrize("key,value", [("functions", [{"name": "f"}]), ("function_call", "auto")])
def test_deprecated_api_stays_refused_with_the_flag_on(key, value):
    exc = _on_refusal(**{key: value})

    assert (exc.code, exc.param) == (TOOLS_NOT_SUPPORTED, key)
    assert exc.message == f"{key}: the deprecated function-calling API is not supported; use tools"


def test_message_level_function_call_is_refused_and_null_is_absent():
    raw = [_USER, {"role": "assistant", "content": "x", "function_call": {"name": "f", "arguments": "{}"}}, _USER]
    exc = _on_refusal(messages=raw)
    assert (exc.code, exc.param) == (TOOLS_NOT_SUPPORTED, "messages[1]")
    assert exc.message == "messages[1]: function_call is the deprecated function-calling API; use tool_calls"

    # Q3: SDK model_dump() echoes carry these nulls on every assistant message.
    echo = {"role": "assistant", "content": "x", "function_call": None, "tool_calls": None}
    call = _on(messages=[_USER, echo, _USER])
    assert [m.role for m in call.messages] == ["user", "assistant", "user"]
    assert _on(messages=[{**_USER, "tool_call_id": None}]).messages[0].tool_call_id is None


# --- Malformed tools / tool_choice / parallel_tool_calls ---------------------------------


def _fn(**changes):
    function = {"name": "ok", **changes}
    return {"type": "function", "function": function}


@pytest.mark.parametrize(
    "tools,param,rule",
    [
        ("x", "tools", "must be a list of tool objects"),
        ({"a": 1}, "tools", "must be a list of tool objects"),
        ([_fn(), 3], "tools[1]", "must be an object"),
        ([{"type": "custom", "function": {"name": "a"}}], "tools[0].type", 'must be "function"'),
        ([{"function": {"name": "a"}}], "tools[0].type", 'must be "function"'),
        ([{"type": "function"}], "tools[0].function", "must be an object"),
        ([{"type": "function", "function": "f"}], "tools[0].function", "must be an object"),
        ([_fn(), _fn(name="")], "tools[1].function.name", "must be a non-empty string"),
        ([_fn(name=3)], "tools[0].function.name", "must be a non-empty string"),
        ([{"type": "function", "function": {}}], "tools[0].function.name", "must be a non-empty string"),
        ([_fn(description=3)], "tools[0].function.description", "must be a string"),
        ([_fn(parameters="x")], "tools[0].function.parameters", "must be an object"),
        ([_fn(strict="yes")], "tools[0].function.strict", "must be a boolean"),
    ],
)
def test_malformed_tools_are_invalid_parameter(tools, param, rule):
    exc = _on_refusal(tools=tools)

    assert (exc.code, exc.param, exc.message) == ("invalid_parameter", param, f"{param}: {rule}")


def test_optional_tool_fields_may_be_absent_or_null():
    tools = [_fn(description=None, parameters=None, strict=None), _fn(name="two")]

    assert _on(tools=tools).tools.tools is not None


@pytest.mark.parametrize(
    "choice",
    ["any", 3, True, ["auto"], {"type": "function"}, {"type": "function", "function": {"name": ""}},
     {"type": "function", "function": {"name": 3}}, {"type": "allowed_tools"}],
)
def test_malformed_tool_choice_is_invalid_parameter(choice):
    exc = _on_refusal(tools=[_TOOL], tool_choice=choice)

    assert (exc.code, exc.param) == ("invalid_parameter", "tool_choice")
    assert exc.message.startswith("tool_choice: must be ")


def test_named_function_must_be_in_tools():
    exc = _on_refusal(tools=[_TOOL], tool_choice={"type": "function", "function": {"name": "missing"}})

    assert (exc.code, exc.param, exc.message) == (
        "invalid_parameter", "tool_choice", "tool_choice: must name a function in tools",
    )


@pytest.mark.parametrize("value", ["true", 1, 0, [], {}])
@pytest.mark.parametrize("tools", [{}, {"tools": [_TOOL]}], ids=["no-tools", "tools"])
def test_non_bool_parallel_tool_calls_is_invalid_parameter(value, tools):
    exc = _on_refusal(parallel_tool_calls=value, **tools)

    assert (exc.code, exc.param, exc.message) == (
        "invalid_parameter", "parallel_tool_calls", "parallel_tool_calls: must be a boolean",
    )


# --- D6 at the edge ---------------------------------------------------------------------


def _a(*ids, content=None):
    return {"role": "assistant", "content": content, "tool_calls": [
        {"id": i, "type": "function", "function": {"name": "f", "arguments": "{}"}} for i in ids]}


def _t(call_id):
    return {"role": "tool", "tool_call_id": call_id, "content": "out"}


_D6_CASES = {
    "tool-first": [_t("c1"), _USER],
    "unknown-id": [_USER, _a("c1"), _t("zzz")],
    "separated-by-user": [_USER, _a("c1"), _USER, _t("c1")],
    "answered-twice": [_USER, _a("c1"), _t("c1"), _t("c1")],
    "last-assistant": [_USER, {"role": "assistant", "content": "hi"}],
    "no-user": [{"role": "system", "content": "s"}, _a("c1"), _t("c1")],
}


@pytest.mark.parametrize("raw", list(_D6_CASES.values()), ids=list(_D6_CASES))
def test_d6_violations_are_invalid_messages_with_the_helper_rule(raw):
    index, rule = conversation_shape_violation(normalize_messages(raw))

    exc = _on_refusal(messages=raw)

    assert (exc.code, exc.param, exc.message) == (
        "invalid_messages", f"messages[{index}]", f"messages[{index}]: {rule}",
    )


def test_last_turn_may_be_a_tool_turn():
    call = _on(messages=[_USER, _a("c1", "c2"), _t("c1"), _t("c2")])

    assert call.messages[-1].role == "tool"


def test_tool_calls_on_a_user_turn_and_a_tool_turn_without_id_are_invalid_messages():
    bad_user = {**_USER, "tool_calls": [{"id": "c", "type": "function", "function": {"name": "f", "arguments": "{}"}}]}
    exc = _on_refusal(messages=[bad_user])
    assert (exc.code, exc.param) == ("invalid_messages", "messages[0]")
    assert "assistant" in exc.message

    exc = _on_refusal(messages=[_USER, _a("c1"), {"role": "tool", "content": "x"}])
    assert (exc.code, exc.param) == ("invalid_messages", "messages[2]")
    assert "tool_call_id" in exc.message


def test_empty_messages_message_is_unchanged_with_the_flag_on():
    exc = _on_refusal(messages=[])

    assert (exc.code, exc.param, exc.message) == ("invalid_messages", "messages", "messages must not be empty")


# --- D16: V1_TOOL_MODELS ------------------------------------------------------------------


def test_model_outside_a_non_empty_list_is_refused():
    exc = _on_refusal(models=["anthropic/claude-3.5-sonnet"], tools=[_TOOL])

    assert (exc.code, exc.param, exc.message) == (
        TOOLS_NOT_SUPPORTED, "tools", "model is not enabled for tool calling (V1_TOOL_MODELS)",
    )


def test_listed_model_and_empty_list_pass():
    assert _on(models=[_MODEL, "other"], tools=[_TOOL]).tools is not None
    assert _on(models=[], tools=[_TOOL]).tools is not None


def test_tool_history_without_tools_is_not_a_tools_request():
    # Q1: OpenCode sends `tools: []` plus history; nothing tool-related is forwarded.
    for extra in ({}, {"tools": []}):
        call = _on(models=["anthropic/claude-3.5-sonnet"], messages=_TOOL_TURNS, **extra)
        assert call.tools is None


def test_model_check_follows_the_tool_shape_check():
    exc = _on_refusal(models=["anthropic/claude-3.5-sonnet"], tools=[{"type": "custom"}])

    assert exc.code == "invalid_parameter"


# --- Check order --------------------------------------------------------------------------


def test_check_order():
    exc = _on_refusal(n=2, tools=[_TOOL])
    assert (exc.code, exc.param) == ("unsupported_parameter", "n")

    exc = _on_refusal(tools=[{"type": "custom"}], temperature="hot")
    assert exc.param == "tools[0].type"

    exc = _on_refusal(tools=[_TOOL], tool_choice="any", messages=[_t("c1")])
    assert exc.param == "tool_choice"

    exc = _on_refusal(models=["anthropic/claude-3.5-sonnet"], tools=[_TOOL], temperature="hot")
    assert exc.param == "tools"


# --- T6 ----------------------------------------------------------------------------------


def test_no_refusal_echoes_client_text():
    canary_tool = {"type": "function", "function": {"name": _CANARY, "description": _CANARY, "parameters": {"k": _CANARY}}}
    cases = [
        {"tools": [canary_tool], "tool_choice": {"type": "function", "function": {"name": _CANARY + "x"}}},
        {"tools": [{**canary_tool, "type": _CANARY}]},
        {"tools": [{"type": "function", "function": {"name": _CANARY, "description": 3}}]},
        {"tools": [canary_tool], "tool_choice": _CANARY},
        {"tools": [canary_tool], "parallel_tool_calls": _CANARY},
        {"tools": [canary_tool]},
        {"messages": [_USER, _a("c1", content=_CANARY), _t(_CANARY)]},
        {"messages": [_USER, {**_a("c1"), "tool_calls": [
            {"id": "c1", "type": "function", "function": {"name": "f", "arguments": _CANARY}},
            {"id": "c1", "type": "function", "function": {"name": "f", "arguments": _CANARY}}]}]},
    ]
    for extra in cases:
        models = ["anthropic/claude-3.5-sonnet"] if extra.get("tools") == [canary_tool] and len(extra) == 1 else ()
        exc = _on_refusal(models, **extra)
        assert _CANARY not in exc.message and _CANARY not in (exc.param or "")
        assert exc.__cause__ is None or _CANARY not in repr(exc.__cause__)


# --- Groups ---------------------------------------------------------------------------------


def test_groups_are_one_per_flag_state():
    assert TOOL_PARAMS == {"tools", "tool_choice", "parallel_tool_calls"}
    on = [FORWARDED, REJECTED_UNLESS_DEFAULT.keys() - TOOL_PARAMS, TOOL_PARAMS, _STRUCTURAL]
    flat = [key for group in on for key in group]
    assert len(flat) == len(set(flat))
    assert TOOL_PARAMS - {"parallel_tool_calls"} <= REJECTED_UNLESS_DEFAULT.keys()
    assert "parallel_tool_calls" not in ChatCompletionRequest.model_fields
    # D10
    assert {"functions", "function_call"} <= REJECTED_UNLESS_DEFAULT.keys()
    assert not {"functions", "function_call"} & TOOL_PARAMS


# --- Defaults are the flag off ---------------------------------------------------------------


def test_defaults_are_the_flag_off_behaviour():
    body = _body(tools=[_TOOL])
    with pytest.raises(V1RequestError) as default:
        translate_request(body)
    with pytest.raises(V1RequestError) as explicit:
        translate_request(body, tools_enabled=False, tool_models=[_MODEL])

    assert (default.value.code, default.value.param, default.value.message) == (
        explicit.value.code, explicit.value.param, explicit.value.message,
    ) == (TOOLS_NOT_SUPPORTED, "tools", "tools: tool calling is not supported (PRD-017)")
    ok = _body(parallel_tool_calls=True)
    assert translate_request(ok) == translate_request(ok, tools_enabled=False, tool_models=[_MODEL])


# --- Flag on accepts everything flag off accepts, with an equal V1Call ---------------------


_SEEDS = range(300)
_FLAG_OFF_ACCEPTED = [
    {"tools": [], "tool_choice": "none"},
    {"tools": None, "tool_choice": None, "functions": [], "function_call": None},
    {"parallel_tool_calls": True},
    {"parallel_tool_calls": None},
    {"user": "u", "metadata": {"a": 1}, "profile": "permissive"},
    {"stream": True, "stream_options": {"include_usage": True, "other": 1}},
    {"temperature": 0.5, "max_completion_tokens": 8, "stop": ["x"]},
]


def _random_request(rng):
    extra = {}
    for key, options in [
        ("tools", [None, [], [_TOOL]]),
        ("tool_choice", [None, "none", "auto"]),
        ("parallel_tool_calls", [None, True, False]),
        ("n", [None, 1, 2]),
        ("user", ["u"]),
        ("temperature", [0.2, "hot"]),
    ]:
        if rng.random() < 0.4:
            extra[key] = rng.choice(options)
    return extra


@pytest.mark.parametrize("extra", _FLAG_OFF_ACCEPTED)
def test_flag_on_returns_an_equal_call_for_every_flag_off_accepted_body(extra):
    body = _body(**extra)

    assert translate_request(body, tools_enabled=True) == translate_request(body)


@pytest.mark.parametrize("seed", _SEEDS)
def test_flag_on_is_a_superset_of_flag_off(seed):
    body = _body(**_random_request(random.Random(seed)))
    try:
        off = translate_request(body)
    except V1RequestError:
        return

    assert translate_request(body, tools_enabled=True) == off


# --- The flag-on property guard ------------------------------------------------------------


def _flag_on_messages(seed):
    """A well-formed tool conversation, then (half the time) one random mutation."""
    rng = random.Random(seed)
    raw = [{"role": "user", "content": "go"}]
    for round_no in range(rng.randrange(0, 3)):
        ids = [f"c{round_no}-{i}" for i in range(rng.randrange(1, 3))]
        raw.append(_a(*ids))
        raw.extend(_t(call_id) for call_id in ids)
        if rng.random() < 0.5:
            raw.append({"role": "assistant", "content": "ok", "tool_calls": None, "function_call": None})
            raw.append({"role": "user", "content": "again"})
    if rng.random() < 0.5:
        return raw
    mutation = rng.randrange(7)
    index = rng.randrange(len(raw))
    if mutation == 0:
        del raw[index]
    elif mutation == 1:
        raw.insert(index, _t("nope"))
    elif mutation == 2:
        raw.insert(index, {"role": "tool", "content": "no id"})
    elif mutation == 3:
        raw.append({"role": "assistant", "content": "last"})
    elif mutation == 4:
        raw[index] = {**raw[index], "tool_calls": [{"id": "x"}]}
    elif mutation == 5:
        raw.insert(index, {"role": "system", "content": "s"})
    else:
        raw.append(dict(raw[-1]))
    return raw


def _translate_flag_on(seed):
    raw = _flag_on_messages(seed)
    try:
        return translate_request(
            ChatCompletionRequest.model_validate({"model": _MODEL, "messages": raw}), tools_enabled=True
        ).messages
    except V1RequestError:
        return None


@pytest.mark.parametrize("seed", _SEEDS)
def test_flag_on_accepted_input_never_trips_the_pipeline_guard(seed):
    messages = _translate_flag_on(seed)
    if messages is None:
        return

    # No pytest.raises: an InvalidConversationError fails this seed's id.
    _validate_conversation(messages)


def test_flag_on_property_generator_is_not_degenerate():
    accepted = sum(_translate_flag_on(seed) is not None for seed in _SEEDS)

    assert accepted >= len(_SEEDS) * 0.25
    assert len(_SEEDS) - accepted >= len(_SEEDS) * 0.25


# ===========================================================================================
# Router and pipeline (TestClient + DB)
# ===========================================================================================

_AUTH_USER_ID = "juan@empresa.com"
_AUTH_TOKEN = "test-user-token"
_ADMIN_TOKEN = "test-admin-token"
_AUTH_HEADERS = {"Authorization": f"Bearer {_AUTH_TOKEN}"}
_PATH = "/v1/chat/completions"
_OTHER_MODEL = "anthropic/claude-3.5-sonnet"
_ANSWER = "Hello from the model."

client = TestClient(app, headers=_AUTH_HEADERS)


@pytest.fixture
def temp_db(temp_db):
    """conftest's initialized database, plus a `user` and an `admin` token."""
    insert_user(User(user_id=_AUTH_USER_ID, role="user", token_hash=hash_token(_AUTH_TOKEN)))
    insert_user(User(user_id="boss@empresa.com", role="admin", token_hash=hash_token(_ADMIN_TOKEN)))
    return temp_db


@pytest.fixture(autouse=True)
def _flag_state(monkeypatch):
    monkeypatch.setattr(settings, "V1_TOOLS_ENABLED", False)
    monkeypatch.setattr(settings, "V1_TOOL_MODELS", "")


class _ThreeArgUpstream:
    """The (messages, model, api_key) stub: raises TypeError on an unexpected keyword."""

    def __init__(self):
        self.calls = []

    def __call__(self, messages, model="gpt-4", api_key=None):
        self.calls.append({"messages": list(messages), "model": model})
        return OpenRouterResult(response=_ANSWER, model_used=model, tokens_used=10)


class _ToolUpstream:
    """Accepts `tools=`; returns whatever `result` says (text by default)."""

    def __init__(self, **result):
        self.calls = []
        self.result = {"response": _ANSWER, "tokens_used": 10, **result}

    def __call__(self, messages, model="gpt-4", api_key=None, *, params=None, tools=None):
        self.calls.append({"messages": list(messages), "model": model, "tools": tools})
        return OpenRouterResult(model_used=model, **self.result)


def _use(monkeypatch, stub):
    monkeypatch.setattr("app.routers.v1.call_openrouter", stub)
    return stub


def _mask_nothing(text, *args):
    return text, []


def _router_body(**extra):
    return {"model": _MODEL, "messages": [_USER], **extra}


def _count_audit_rows() -> int:
    with get_connection() as conn:
        return conn.execute("SELECT COUNT(*) AS n FROM audit_logs").fetchone()["n"]


def _only_row():
    with get_connection() as conn:
        rows = conn.execute("SELECT id FROM audit_logs").fetchall()
    assert len(rows) == 1
    return get_audit_log(rows[0]["id"])


def _error(message, param, code):
    return {"error": {"message": message, "type": "invalid_request_error", "param": param, "code": code, "harness": None}}


_TOOLS_OFF = "tool calling is not supported (PRD-017)"
_FLAG_OFF_REFUSALS = {
    "tools": (_router_body(tools=[_TOOL]), 400, f"tools: {_TOOLS_OFF}", "tools", "tools_not_supported"),
    "tool_choice": (_router_body(tool_choice="auto"), 400, f"tool_choice: {_TOOLS_OFF}", "tool_choice", "tools_not_supported"),
    "functions": (_router_body(functions=[{"name": "f"}]), 400, f"functions: {_TOOLS_OFF}", "functions", "tools_not_supported"),
    "function_call": (_router_body(function_call="auto"), 400, f"function_call: {_TOOLS_OFF}", "function_call", "tools_not_supported"),
    "tool-turn": (_router_body(messages=[_USER, _t("c1"), _USER]), 400, f"messages[1]: tool turns are not supported (PRD-017)", "messages[1]", "tools_not_supported"),
    "tool_calls": (_router_body(messages=[_USER, _a("c1"), _USER]), 400, "messages[1]: tool calls are not supported (PRD-017)", "messages[1]", "tools_not_supported"),
    "tool_calls-null": (_router_body(messages=[_USER, {"role": "assistant", "content": "x", "tool_calls": None}, _USER]), 400, "messages[1]: tool calls are not supported (PRD-017)", "messages[1]", "tools_not_supported"),
    "last-assistant": (_router_body(messages=[_USER, {"role": "assistant", "content": "x"}]), 400, "messages[1]: the last message must be a user turn", "messages[1]", "invalid_messages"),
    "tools-and-tool-turn": (_router_body(tools=[_TOOL], messages=[_USER, _t("c1"), _USER]), 400, f"tools: {_TOOLS_OFF}", "tools", "tools_not_supported"),
}


# --- AC1: flag off is PRD-015, byte for byte ----------------------------------------------


@pytest.mark.parametrize("case", list(_FLAG_OFF_REFUSALS))
def test_flag_off_refusals_are_prd_015_exactly(temp_db, monkeypatch, case):
    body, status, message, param, code = _FLAG_OFF_REFUSALS[case]
    stub = _use(monkeypatch, _ToolUpstream())

    response = client.post(_PATH, json=body)

    assert response.status_code == status
    assert response.json() == _error(message, param, code)
    assert response.headers["x-should-retry"] == "false"
    assert _count_audit_rows() == 0
    assert stub.calls == []


def test_flag_off_ignores_the_model_list_and_ignores_parallel_tool_calls(temp_db, monkeypatch):
    monkeypatch.setattr(settings, "V1_TOOL_MODELS", _OTHER_MODEL)
    stub = _use(monkeypatch, _ThreeArgUpstream())
    body, _, message, param, code = _FLAG_OFF_REFUSALS["tools"]
    assert client.post(_PATH, json=body).json() == _error(message, param, code)

    response = client.post(_PATH, json=_router_body(parallel_tool_calls=True))

    assert response.status_code == 200
    assert "parallel_tool_calls" in _only_row().ignored_params.split(",")
    assert len(stub.calls) == 1


# --- AC5: the full flag-on request, through the real client -----------------------------------


def _capturing_transport(seen):
    def _handler(request):
        seen.append(request)
        return httpx.Response(200, json={
            "choices": [{"message": {"content": _ANSWER}, "finish_reason": "stop"}],
            "model": _MODEL, "usage": {"total_tokens": 12},
        })
    return httpx.MockTransport(_handler)


def _upstream_over(transport):
    """The real call_openrouter over `transport`, accepting both optional keywords."""
    def _call(messages, model="gpt-4", api_key=None, params=None, *, tools=None):
        with httpx.Client(transport=transport) as http_client:
            return _real_call_openrouter(
                messages, model=model, api_key=api_key, params=params, client=http_client, tools=tools
            )
    return _call


def test_full_flag_on_request_reaches_the_wire_byte_for_byte(temp_db, monkeypatch):
    monkeypatch.setattr(settings, "V1_TOOLS_ENABLED", True)
    monkeypatch.setattr(query_pipeline, "redact", _mask_nothing)
    seen: list = []
    monkeypatch.setattr("app.routers.v1.call_openrouter", _upstream_over(_capturing_transport(seen)))
    tools = [_TOOL]

    response = client.post(_PATH, json=_router_body(tools=tools, tool_choice="auto", messages=_TOOL_TURNS))

    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "chat.completion"
    assert body["choices"][0]["message"]["content"] == _ANSWER
    assert len(seen) == 1
    payload = json.loads(seen[0].content)
    assert payload["tools"] == tools
    assert payload["tool_choice"] == "auto"
    assert "parallel_tool_calls" not in payload
    assert payload["messages"] == _TOOL_TURNS
    # D13: the string, byte for byte (the whole body, not a re-serialization of it).
    assert json.dumps(_ARGS) in seen[0].content.decode("utf-8")
    assert payload["messages"][1]["tool_calls"][0]["function"]["arguments"] == _ARGS
    row = _only_row()
    assert row.ingress == "v1" and row.ignored_params is None


def test_router_hands_tool_params_to_the_pipeline(temp_db, monkeypatch):
    monkeypatch.setattr(settings, "V1_TOOLS_ENABLED", True)
    stub = _use(monkeypatch, _ToolUpstream())

    response = client.post(_PATH, json=_router_body(tools=[_TOOL], tool_choice="required", parallel_tool_calls=True))

    assert response.status_code == 200
    assert stub.calls[0]["tools"] == ToolParams(tools=[_TOOL], tool_choice="required", parallel_tool_calls=True)
    assert _only_row().ignored_params is None


@pytest.mark.parametrize("extra", [{}, {"tools": []}], ids=["absent", "empty"])
def test_tools_keyword_is_not_passed_when_there_are_no_tools(temp_db, monkeypatch, extra):
    monkeypatch.setattr(settings, "V1_TOOLS_ENABLED", True)
    stub = _use(monkeypatch, _ThreeArgUpstream())

    response = client.post(_PATH, json=_router_body(messages=_TOOL_TURNS, **extra))

    # A three-argument stub raises TypeError on an unexpected tools= keyword.
    assert response.status_code == 200
    assert len(stub.calls[0]["messages"]) == 3


# --- AC3 / AC4 through the router --------------------------------------------------------------


def test_refusals_through_the_router_write_no_row(temp_db, monkeypatch):
    monkeypatch.setattr(settings, "V1_TOOLS_ENABLED", True)
    stub = _use(monkeypatch, _ToolUpstream())

    response = client.post(_PATH, json=_router_body(messages=[_t("c1"), _USER]))
    assert response.status_code == 400
    assert response.json() == _error(
        "messages[0]: a tool turn must follow an assistant turn with tool_calls, with only tool turns between",
        "messages[0]", "invalid_messages",
    )

    response = client.post(_PATH, json=_router_body(tools=[{"type": "function", "function": {"name": ""}}]))
    assert response.json() == _error(
        "tools[0].function.name: must be a non-empty string", "tools[0].function.name", "invalid_parameter"
    )
    assert _count_audit_rows() == 0
    assert stub.calls == []


@pytest.mark.parametrize("token", [_AUTH_TOKEN, _ADMIN_TOKEN], ids=["user", "admin"])
def test_tool_model_list_holds_for_every_role(temp_db, monkeypatch, token):
    monkeypatch.setattr(settings, "V1_TOOLS_ENABLED", True)
    monkeypatch.setattr(settings, "V1_TOOL_MODELS", _OTHER_MODEL)
    stub = _use(monkeypatch, _ToolUpstream())

    response = client.post(
        _PATH, json=_router_body(tools=[_TOOL]), headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 400
    assert response.json() == _error(
        "model is not enabled for tool calling (V1_TOOL_MODELS)", "tools", "tools_not_supported"
    )
    assert _count_audit_rows() == 0
    assert stub.calls == []


def test_listed_model_passes_through_the_router(temp_db, monkeypatch):
    monkeypatch.setattr(settings, "V1_TOOLS_ENABLED", True)
    monkeypatch.setattr(settings, "V1_TOOL_MODELS", f"{_OTHER_MODEL}, {_MODEL}")
    _use(monkeypatch, _ToolUpstream())

    assert client.post(_PATH, json=_router_body(tools=[_TOOL])).status_code == 200


def test_flag_is_read_per_request(temp_db, monkeypatch):
    stub = _use(monkeypatch, _ToolUpstream())
    body = _router_body(tools=[_TOOL])

    assert client.post(_PATH, json=body).status_code == 400
    monkeypatch.setattr(settings, "V1_TOOLS_ENABLED", True)
    assert client.post(_PATH, json=body).status_code == 200
    monkeypatch.setattr(settings, "V1_TOOLS_ENABLED", False)
    assert client.post(_PATH, json=body).status_code == 400
    assert len(stub.calls) == 1


# --- Streamed (OpenCode shape) ----------------------------------------------------------------


def _data_events(text):
    events = []
    for block in text.split("\n\n"):
        if block.startswith("data: ") and block != "data: [DONE]":
            events.append(json.loads(block[len("data: "):]))
    return events


def test_streamed_opencode_shape_is_accepted(temp_db, monkeypatch):
    monkeypatch.setattr(settings, "V1_TOOLS_ENABLED", True)
    stub = _use(monkeypatch, _ToolUpstream())

    response = client.post(
        _PATH,
        json=_router_body(tools=[], stream=True, stream_options={"include_usage": True}, messages=_TOOL_TURNS),
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    chunks = _data_events(response.text)
    assert any(c["choices"] and c["choices"][0]["delta"].get("content") == _ANSWER for c in chunks)
    assert stub.calls[0]["tools"] is None
    assert [m.role for m in stub.calls[0]["messages"]] == ["user", "assistant", "tool"]


# --- STORY-011: the release on the wire --------------------------------------------------------


def _calling_upstream():
    return _ToolUpstream(
        response="",
        tool_calls=(ToolCallSpec("call_2", "bash", '{"command":"rm -rf /"}'),),
        finish_reason="tool_calls",
    )


def _assert_no_call_released(text):
    # PRD-017 STORY-010 (D2, T1): the denial note legitimately names the tool, the id and the
    # reason ("bash", "call_2", "rm -rf"), so those are no longer leaks. What must not appear is
    # the arguments string (raw and JSON-escaped) or an arguments key. PRD-017 Section 10,
    # STORY-011: `tool_calls: null` is kept on an all-denied JSON body, so that key is no leak.
    for leaked in ('{"command":"rm -rf /"}', '{\\"command\\":\\"rm -rf /\\"}', '"arguments"'):
        assert leaked not in text


def _denial_note(name, call_id, arguments):
    """The note the real engine's verdict for this call yields (PRD-017 Section 6.6)."""
    decision = action_policy.evaluate(ToolCall(call_id, name, arguments), Identity(_AUTH_USER_ID, "user"))
    assert decision.decision == "deny"
    return tool_release.DENIAL_NOTE_TEMPLATE.format(name=name, id=call_id, reason=decision.reason)


def test_denied_call_is_the_note_with_tool_calls_null_and_stop(temp_db, monkeypatch):
    """AC2, AC3: every call denied: the note as content, `tool_calls: null` (key kept), finish
    `stop`, one `deny` action carrying the recorded rule and reason."""
    monkeypatch.setattr(settings, "V1_TOOLS_ENABLED", True)
    stub = _use(monkeypatch, _calling_upstream())

    response = client.post(_PATH, json=_router_body(tools=[_TOOL]))

    assert response.status_code == 200
    body = response.json()
    choice = body["choices"][0]
    with get_connection() as conn:
        row = dict(conn.execute("SELECT * FROM action_decisions").fetchone())
    assert choice["message"] == {
        "role": "assistant",
        "content": _denial_note("bash", "call_2", '{"command":"rm -rf /"}'),
        "tool_calls": None,
    }
    assert choice["finish_reason"] == "stop"
    assert body["harness"]["actions"] == [
        {"tool_call_id": "call_2", "tool_name": "bash", "decision": "deny", "rule": row["rule"], "reason": row["reason"]}
    ]
    _assert_no_call_released(response.text)
    assert len(stub.calls) == 1
    assert row["decision"] == "deny"


def test_streamed_denied_call_is_the_note_and_stop(temp_db, monkeypatch):
    """The streamed twin: the note as content, finish `stop`, no tool-call key, no harness object
    (PRD-017 Section 6.6: the stream carries neither)."""
    monkeypatch.setattr(settings, "V1_TOOLS_ENABLED", True)
    _use(monkeypatch, _calling_upstream())

    response = client.post(_PATH, json=_router_body(tools=[_TOOL], stream=True))

    assert response.status_code == 200
    _assert_no_call_released(response.text)
    assert '"tool_calls"' not in response.text
    chunks = _data_events(response.text)
    streamed = "".join(c["choices"][0]["delta"].get("content") or "" for c in chunks if c["choices"])
    assert streamed == _denial_note("bash", "call_2", '{"command":"rm -rf /"}')
    assert [c["choices"][0]["finish_reason"] for c in chunks if c["choices"]][-1] == "stop"
    assert all("harness" not in c for c in chunks)


def test_allowed_call_is_released_with_content_null_and_finish_tool_calls(temp_db, monkeypatch):
    """AC1, AC3: the allowed call leaves byte for byte, content null, finish `tool_calls`, one
    `allow` action, and the decision row is recorded against the audit row."""
    monkeypatch.setattr(settings, "V1_TOOLS_ENABLED", True)
    _use(monkeypatch, _ToolUpstream(
        response="", tool_calls=(ToolCallSpec("call_r", "read", '{"path":"src/a.py"}'),), finish_reason="tool_calls",
    ))

    response = client.post(_PATH, json=_router_body(tools=[_TOOL]))

    assert response.status_code == 200
    body = response.json()
    choice = body["choices"][0]
    assert choice["message"] == {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {"id": "call_r", "type": "function", "function": {"name": "read", "arguments": '{"path":"src/a.py"}'}}
        ],
    }
    assert choice["finish_reason"] == "tool_calls"
    assert json.dumps('{"path":"src/a.py"}') in response.text
    with get_connection() as conn:
        rows = conn.execute("SELECT decision, audit_id, rule, reason FROM action_decisions").fetchall()
    assert [(r["decision"], r["audit_id"]) for r in rows] == [("allow", _only_row().id)]
    assert body["harness"]["actions"] == [
        {"tool_call_id": "call_r", "tool_name": "read", "decision": "allow", "rule": rows[0]["rule"], "reason": rows[0]["reason"]}
    ]


def test_streamed_allowed_call_is_one_delta_then_finish_tool_calls(temp_db, monkeypatch):
    """STORY-012 AC1 (replaces the STORY-011 interim pin): role chunk with `content: null`, one
    tool-call delta with the whole arguments, finish `tool_calls`, `[DONE]`; the decision is
    recorded and the stream carries no `harness` object (PRD-017 Section 6.6)."""
    monkeypatch.setattr(settings, "V1_TOOLS_ENABLED", True)
    _use(monkeypatch, _ToolUpstream(
        response="", tool_calls=(_READ_CALL,), finish_reason="tool_calls",
    ))

    response = client.post(_PATH, json=_router_body(tools=[_TOOL], stream=True))

    assert response.status_code == 200
    chunks = _data_events(response.text)
    assert [c["choices"] for c in chunks] == [
        [{"index": 0, "delta": {"role": "assistant", "content": None}, "finish_reason": None}],
        [{"index": 0, "delta": {"tool_calls": [
            {"index": 0, "id": "call_r", "type": "function",
             "function": {"name": "read", "arguments": '{"path":"src/a.py"}'}}
        ]}, "finish_reason": None}],
        [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}],
    ]
    assert all("harness" not in c for c in chunks)
    assert json.dumps('{"path":"src/a.py"}') in response.text
    assert response.text.rstrip().endswith("data: [DONE]")
    with get_connection() as conn:
        rows = conn.execute("SELECT decision, audit_id FROM action_decisions").fetchall()
    assert [(r["decision"], r["audit_id"]) for r in rows] == [("allow", _only_row().id)]


def test_mixed_response_releases_the_allowed_call_and_notes_the_denied_one(temp_db, monkeypatch):
    """AC2, AC3: text, a note for the deny, the allowed call, finish `tool_calls`, actions in model order."""
    monkeypatch.setattr(settings, "V1_TOOLS_ENABLED", True)
    _use(monkeypatch, _ToolUpstream(
        response="Reading.", tool_calls=(_READ_CALL, _DROP_TABLE), finish_reason="tool_calls",
    ))

    response = client.post(_PATH, json=_router_body(tools=[_TOOL]))

    assert response.status_code == 200
    body = response.json()
    choice = body["choices"][0]
    rows = _decision_table()
    note = tool_release.DENIAL_NOTE_TEMPLATE.format(name="shell", id="call_1", reason=rows[1]["reason"])
    assert choice["message"]["content"] == "Reading.\n\n" + note
    assert [c["id"] for c in choice["message"]["tool_calls"]] == ["call_r"]
    assert choice["finish_reason"] == "tool_calls"
    assert [(a["tool_call_id"], a["decision"]) for a in body["harness"]["actions"]] == [
        ("call_r", "allow"), ("call_1", "deny"),
    ]


def test_flag_on_text_only_body_is_the_flag_off_body(temp_db, monkeypatch):
    """AC5 (DD-1): a text-only answer has the same body with the flag on as off: no `tool_calls`,
    no `actions`. Only the per-request values differ."""
    bodies = []
    for enabled, prompt in ((False, "first prompt"), (True, "second prompt")):
        monkeypatch.setattr(settings, "V1_TOOLS_ENABLED", enabled)
        _use(monkeypatch, _ToolUpstream())
        response = client.post(_PATH, json=_router_body(messages=[{"role": "user", "content": prompt}]))
        assert response.status_code == 200
        body = response.json()
        for key in ("id", "created"):
            body.pop(key)
        body["harness"].pop("audit_id")
        bodies.append(body)

    assert bodies[0] == bodies[1]
    assert "tool_calls" not in bodies[1]["choices"][0]["message"]
    assert "actions" not in bodies[1]["harness"]


def test_router_sdk_round_trip(temp_db, monkeypatch):
    """AC4: the OpenAI SDK parses the router's released-call body, arguments equal."""
    openai = pytest.importorskip("openai")
    monkeypatch.setattr(settings, "V1_TOOLS_ENABLED", True)
    _use(monkeypatch, _ToolUpstream(response="", tool_calls=(_READ_CALL,), finish_reason="tool_calls"))

    response = client.post(_PATH, json=_router_body(tools=[_TOOL]))

    parsed = openai.types.chat.ChatCompletion.model_validate(response.json())
    assert parsed.choices[0].finish_reason == "tool_calls"
    assert parsed.choices[0].message.tool_calls[0].function.arguments == _READ_CALL.arguments


# --- STORY-012: streamed tool-call deltas ------------------------------------------------------

_A1 = '{"path":"a\\"b.py"}'
_A2 = '{"command": "ls  -la"}'
_STREAM_USAGE = {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}


def _two_call_completion():
    return ChatCompletion(
        id="chatcmpl-harness-42",
        created=1792569600,
        model=_MODEL,
        choices=[Choice(
            message=AssistantMessage(content=None, tool_calls=[
                CompletionToolCall(id="call_1", function=ToolCallFunction(name="read", arguments=_A1)),
                CompletionToolCall(id="call_2", function=ToolCallFunction(name="bash", arguments=_A2)),
            ]),
            finish_reason="tool_calls",
        )],
        usage=Usage(**_STREAM_USAGE),
        harness=HarnessCompletionInfo(audit_id=42, audit_ref=_AUDIT_REF, actions=[
            HarnessAction(tool_call_id="call_1", tool_name="read", decision="allow", rule="r", reason="x"),
            HarnessAction(tool_call_id="call_2", tool_name="bash", decision="allow", rule="r", reason="x"),
        ]),
    )


def _payloads(events):
    """The `data:` payloads of rendered events, `[DONE]` kept as a string."""
    out = []
    for event in events:
        assert event.startswith("data: ") and event.endswith("\n\n")
        body = event[len("data: "):-2]
        out.append(body if body == "[DONE]" else json.loads(body))
    return out


def _accumulate(payloads):
    """Feed a stream's chunks through the `openai` SDK's accumulator (AC3)."""
    openai = pytest.importorskip("openai")
    from openai.lib.streaming.chat import ChatCompletionStreamState

    state = ChatCompletionStreamState()
    for payload in payloads:
        if payload != "[DONE]":
            state.handle_chunk(openai.types.chat.ChatCompletionChunk.model_validate(payload))
    return state.get_final_completion()


def _call_tuples(message):
    return [(c.id, c.type, c.function.name, c.function.arguments) for c in message.tool_calls]


@pytest.mark.parametrize("include_usage", [True, False])
def test_completion_events_stream_two_released_calls(include_usage):
    """AC1: role chunk with `content: null`, one chunk per call with the whole arguments, finish
    `tool_calls`, usage only on request, `[DONE]`; every chunk carries the completion's ids."""
    events = v1_sse.completion_events(_two_call_completion(), include_usage=include_usage)
    payloads = _payloads(events)

    def base(choices, **extra):
        return {
            "id": "chatcmpl-harness-42", "object": "chat.completion.chunk",
            "created": 1792569600, "model": _MODEL, "choices": choices, **extra,
        }

    def call_chunk(index, call_id, name, arguments):
        return base([{"index": 0, "delta": {"tool_calls": [
            {"index": index, "id": call_id, "type": "function",
             "function": {"name": name, "arguments": arguments}}
        ]}, "finish_reason": None}])

    expected = [
        base([{"index": 0, "delta": {"role": "assistant", "content": None}, "finish_reason": None}]),
        call_chunk(0, "call_1", "read", _A1),
        call_chunk(1, "call_2", "bash", _A2),
        base([{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]),
    ]
    if include_usage:
        expected.append(base([], usage=_STREAM_USAGE))
    expected.append("[DONE]")
    assert payloads == expected
    assert not any(isinstance(p, dict) and "harness" in p for p in payloads)
    # D13: the arguments strings go out byte for byte.
    text = "".join(events)
    assert json.dumps(_A1) in text and json.dumps(_A2) in text


def test_completion_events_text_only_has_no_tool_call_delta():
    completion = _two_call_completion()
    completion.choices[0].message = AssistantMessage(content="Hi.")
    completion.choices[0].finish_reason = "stop"
    payloads = _payloads(v1_sse.completion_events(completion, include_usage=False))
    assert [p["choices"][0]["delta"] for p in payloads[:-1]] == [{"role": "assistant", "content": "Hi."}, {}]
    assert "tool_calls" not in "".join(v1_sse.completion_events(completion, include_usage=False))


def test_sdk_accumulator_rebuilds_the_non_streamed_message():
    """AC3 (pure): the SDK's stream accumulator over the rendered chunks equals the parsed body."""
    openai = pytest.importorskip("openai")
    completion = _two_call_completion()

    final = _accumulate(_payloads(v1_sse.completion_events(completion, include_usage=True)))
    plain = openai.types.chat.ChatCompletion.model_validate(json.loads(completion.model_dump_json()))

    assert final.choices[0].message.content is None and plain.choices[0].message.content is None
    assert final.choices[0].finish_reason == plain.choices[0].finish_reason == "tool_calls"
    assert _call_tuples(final.choices[0].message) == _call_tuples(plain.choices[0].message)
    assert [t[3] for t in _call_tuples(final.choices[0].message)] == [_A1, _A2]
    assert final.usage.total_tokens == plain.usage.total_tokens == 10


def test_streamed_and_plain_tool_responses_accumulate_to_the_same_message(temp_db, monkeypatch):
    """AC3 (router): the same two allowed calls, streamed and plain, give one message."""
    openai = pytest.importorskip("openai")
    monkeypatch.setattr(settings, "V1_TOOLS_ENABLED", True)
    _use(monkeypatch, _ToolUpstream(
        response="",
        tool_calls=(_READ_CALL, ToolCallSpec("call_r2", "read", '{"path":"src/b.py"}')),
        finish_reason="tool_calls",
    ))

    def ask(n, **extra):
        messages = [{"role": "user", "content": f"list the files {n}"}]
        return client.post(_PATH, json=_router_body(tools=[_TOOL], messages=messages, **extra))

    streamed = ask(1, stream=True, stream_options={"include_usage": True})
    plain = ask(2)

    assert streamed.status_code == plain.status_code == 200
    final = _accumulate(_data_events(streamed.text))
    parsed = openai.types.chat.ChatCompletion.model_validate(plain.json())
    assert final.choices[0].message.content is None and parsed.choices[0].message.content is None
    assert final.choices[0].finish_reason == parsed.choices[0].finish_reason == "tool_calls"
    assert _call_tuples(final.choices[0].message) == _call_tuples(parsed.choices[0].message)
    assert [t[0] for t in _call_tuples(parsed.choices[0].message)] == ["call_r", "call_r2"]


@pytest.mark.parametrize("include_usage", [True, False])
def test_flag_on_text_only_stream_is_the_flag_off_stream(temp_db, monkeypatch, include_usage):
    """AC2 (DD-1): a text-only stream is the same with the flag on as off, byte for byte once
    the per-request id and `created` are normalized."""
    texts = []
    for enabled, prompt in ((False, "first prompt"), (True, "second prompt")):
        monkeypatch.setattr(settings, "V1_TOOLS_ENABLED", enabled)
        _use(monkeypatch, _ToolUpstream())
        response = client.post(_PATH, json=_router_body(
            messages=[{"role": "user", "content": prompt}], stream=True,
            stream_options={"include_usage": include_usage},
        ))
        assert response.status_code == 200
        texts.append(response.text)

    assert "tool_calls" not in texts[1]
    normalized = [
        re.sub(r'"created":\d+', '"created":0', re.sub(r"chatcmpl-harness-\d+", "chatcmpl-harness-0", t))
        for t in texts
    ]
    assert normalized[0] == normalized[1]


def test_streamed_all_denied_is_the_note_then_stop_and_no_delta(temp_db, monkeypatch):
    """AC4: every call denied: the note in the role chunk, finish `stop`, no tool-call delta."""
    monkeypatch.setattr(settings, "V1_TOOLS_ENABLED", True)
    _use(monkeypatch, _calling_upstream())

    response = client.post(_PATH, json=_router_body(tools=[_TOOL], stream=True))

    assert response.status_code == 200
    chunks = _data_events(response.text)
    assert [c["choices"] for c in chunks] == [
        [{"index": 0, "delta": {"role": "assistant", "content": _denial_note("bash", "call_2", '{"command":"rm -rf /"}')},
          "finish_reason": None}],
        [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    ]
    assert response.text.rstrip().endswith("data: [DONE]")
    assert '"tool_calls"' not in response.text


def test_streamed_mixed_response_is_text_and_note_then_the_allowed_call(temp_db, monkeypatch):
    """A mixed answer streams the text and the note, only the allowed call, finish `tool_calls`."""
    monkeypatch.setattr(settings, "V1_TOOLS_ENABLED", True)
    _use(monkeypatch, _ToolUpstream(
        response="Reading.", tool_calls=(_READ_CALL, _DROP_TABLE), finish_reason="tool_calls",
    ))

    response = client.post(_PATH, json=_router_body(tools=[_TOOL], stream=True))

    assert response.status_code == 200
    chunks = _data_events(response.text)
    rows = _decision_table()
    note = tool_release.DENIAL_NOTE_TEMPLATE.format(name="shell", id="call_1", reason=rows[1]["reason"])
    assert chunks[0]["choices"][0]["delta"] == {"role": "assistant", "content": "Reading.\n\n" + note}
    call_deltas = [c["choices"][0]["delta"]["tool_calls"] for c in chunks if "tool_calls" in c["choices"][0]["delta"]]
    assert [[(t["index"], t["id"]) for t in d] for d in call_deltas] == [[(0, "call_r")]]
    assert chunks[-1]["choices"][0]["finish_reason"] == "tool_calls"
    assert "DROP TABLE" not in response.text.replace(note, "")


# --- STORY-010: decide and record ----------------------------------------------------------

_AUDIT_FAILED = {
    "error": {
        "message": "Action audit failed: decisions could not be recorded",
        "type": "api_error", "param": None, "code": "internal_error", "harness": None,
    }
}
_DROP_TABLE = ToolCallSpec("call_1", "shell", json.dumps({"command": 'sqlite3 app.db "DROP TABLE users"'}))
_READ_CALL = ToolCallSpec("call_r", "read", '{"path":"src/a.py"}')


def _decision_table():
    with get_connection() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM action_decisions ORDER BY id")]


@pytest.mark.parametrize("stream", [False, True], ids=["json", "sse"])
def test_drop_table_via_shell_is_denied_and_recorded_with_the_audit_id(temp_db, monkeypatch, stream):
    """AC4: one deny/sql.ddl row against the request's audit row; no call in the response."""
    monkeypatch.setattr(settings, "V1_TOOLS_ENABLED", True)
    _use(monkeypatch, _ToolUpstream(response="", tool_calls=(_DROP_TABLE,), finish_reason="tool_calls"))

    response = client.post(_PATH, json=_router_body(tools=[_TOOL], stream=stream))

    assert response.status_code == 200
    (row,) = _decision_table()
    audit = _only_row()
    assert (row["decision"], row["rule"], row["tool_name"]) == ("deny", "sql.ddl", "shell")
    assert row["audit_id"] == audit.id
    assert audit.has_tool_calls is True
    assert "arguments" not in response.text
    if stream:
        assert '"tool_calls"' not in response.text
    else:
        # PRD-017 Section 10 (STORY-011): the JSON body keeps tool_calls: null when every call is denied; no call data appears.
        assert response.json()["choices"][0]["message"]["tool_calls"] is None
    note = tool_release.DENIAL_NOTE_TEMPLATE.format(name="shell", id="call_1", reason=row["reason"])
    if stream:
        content = "".join(
            c["choices"][0]["delta"].get("content") or "" for c in _data_events(response.text) if c["choices"]
        )
    else:
        content = response.json()["choices"][0]["message"]["content"]
        assert int(response.headers["X-Harness-Audit-Id"]) == audit.id
    assert content == note


def _fail_record(monkeypatch):
    def failing(*args, **kwargs):
        raise StorageError(f"driver said {_CANARY}")

    monkeypatch.setattr(action_audit, "record", failing)


def test_action_audit_failure_is_500_internal_error_and_releases_nothing(temp_db, monkeypatch):
    """AC3 (JSON): fixed body, retryable, no call id, arguments or driver text; no decision rows."""
    monkeypatch.setattr(settings, "V1_TOOLS_ENABLED", True)
    _use(monkeypatch, _ToolUpstream(response="", tool_calls=(_READ_CALL, _DROP_TABLE), finish_reason="tool_calls"))
    _fail_record(monkeypatch)

    response = client.post(_PATH, json=_router_body(tools=[_TOOL]))

    assert response.status_code == 500
    assert response.json() == _AUDIT_FAILED
    assert "x-should-retry" not in response.headers
    for leaked in ("call_r", "call_1", "src/a.py", "DROP TABLE", _CANARY):
        assert leaked not in response.text
    assert _decision_table() == []


def test_action_audit_failure_after_stream_commit_is_the_error_event(temp_db, monkeypatch):
    """AC3 (SSE): one error data event, no [DONE], nothing of the calls (mirrors test_v1_sse)."""
    monkeypatch.setattr(settings, "V1_TOOLS_ENABLED", True)
    _use(monkeypatch, _ToolUpstream(response="", tool_calls=(_READ_CALL, _DROP_TABLE), finish_reason="tool_calls"))
    _fail_record(monkeypatch)

    response = client.post(_PATH, json=_router_body(tools=[_TOOL], stream=True))

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert _data_events(response.text) == [_AUDIT_FAILED]
    assert "[DONE]" not in response.text
    for leaked in ("call_r", "call_1", "src/a.py", "DROP TABLE", _CANARY):
        assert leaked not in response.text
    assert _decision_table() == []


def test_action_audit_failure_marks_the_row_and_the_same_request_is_answered_again(temp_db, monkeypatch):
    """D8: the retry is not held as a duplicate once the row is marked failed."""
    monkeypatch.setattr(settings, "V1_TOOLS_ENABLED", True)
    stub = _use(monkeypatch, _ToolUpstream(response="", tool_calls=(_READ_CALL,), finish_reason="tool_calls"))
    real_record = action_audit.record
    _fail_record(monkeypatch)

    assert client.post(_PATH, json=_router_body(tools=[_TOOL])).status_code == 500
    monkeypatch.setattr(action_audit, "record", real_record)
    retry = client.post(_PATH, json=_router_body(tools=[_TOOL]))

    assert retry.status_code == 200
    assert len(stub.calls) == 2


def test_fault_code_maps_action_audit_error():
    """AC3: a new test, so the pre-existing `_fault_code` parametrize stays unedited."""
    from app.routers.v1 import _PIPELINE_FAULTS, _fault_code

    exc = ActionAuditError("x")

    assert isinstance(exc, _PIPELINE_FAULTS)
    assert _fault_code(exc) == "internal_error"


def test_router_never_reads_raw_upstream_tool_calls():
    """T1: no `<x>.result.tool_calls` attribute chain in the router; calls come from the pipeline result."""
    import ast
    import pathlib

    tree = ast.parse(pathlib.Path("app/routers/v1.py").read_text(encoding="utf-8"))
    chains = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and node.attr == "tool_calls"
        and isinstance(node.value, ast.Attribute) and node.value.attr == "result"
    ]

    assert chains == []


def test_query_body_and_schema_ignore_the_tool_outcome(temp_db, monkeypatch):
    """D17, DD-1: a private attribute is never serialized and never in the OpenAPI schema."""
    # PRD-018 D14: audit_ref is on every success.
    fields = {"status", "response", "audit_id", "audit_ref", "model_used", "tokens_used", "pii_redacted", "pii_entities_masked"}
    plain = QuerySuccessResponse(response="r", audit_id=1, audit_ref=_AUDIT_REF, model_used="m", tokens_used=2)
    carrying = QuerySuccessResponse(response="r", audit_id=1, audit_ref=_AUDIT_REF, model_used="m", tokens_used=2)
    carrying._tool_outcome = tool_release.ToolOutcome(tool_release.Release((), (), None), ())

    assert carrying.tool_outcome is not None and plain.tool_outcome is None
    assert carrying.model_dump() == plain.model_dump()
    assert carrying.model_dump_json() == plain.model_dump_json()
    assert QuerySuccessResponse.model_json_schema() == plain.model_json_schema()
    assert set(app.openapi()["components"]["schemas"]["QuerySuccessResponse"]["properties"]) == fields

    monkeypatch.setattr("app.routers.query.call_openrouter", _ThreeArgUpstream())
    response = client.post("/query", json={"prompt": "hello"})
    assert response.status_code == 200
    assert set(response.json()) == fields
