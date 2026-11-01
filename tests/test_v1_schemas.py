"""PRD-015 STORY-004: the /v1 wire shapes against PRD Sections 7.1 and 7.4-7.7.

No DB. Each example below is the PRD's, copied verbatim with concrete values
where the PRD shows an ellipsis. The OpenAI SDK block at the end is skipped
when `openai` is not installed (it is a test-only dependency, STORY-015).
"""

import json

import pytest
from pydantic import ValidationError

from app.models.v1_schemas import (
    CHAT_COMPLETION_ID_PREFIX,
    AssistantMessage,
    ChatCompletion,
    ChatCompletionChunk,
    ChatCompletionRequest,
    Choice,
    ChunkChoice,
    ChunkDelta,
    ErrorDetail,
    ErrorResponse,
    HarnessCompletionInfo,
    ModelEntry,
    ModelList,
    Usage,
    chat_completion_id,
)

_CREATED = 1792569600
_CONTENT = "def add(a, b):\n    return a + b"

# Section 7.4
_COMPLETION_EXAMPLE = {
    "id": "chatcmpl-harness-1842",
    "object": "chat.completion",
    "created": _CREATED,
    "model": "openai/gpt-4o",
    "choices": [
        {
            "index": 0,
            "message": {"role": "assistant", "content": _CONTENT},
            "logprobs": None,
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 812, "completion_tokens": 96, "total_tokens": 908},
    "harness": {"audit_id": 1842, "pii_redacted": False, "pii_entities_masked": []},
}

# Section 7.6: content, finish and usage chunks.
_CHUNK_HEAD = {
    "id": "chatcmpl-harness-1842",
    "object": "chat.completion.chunk",
    "created": _CREATED,
    "model": "openai/gpt-4o",
}
_CONTENT_CHUNK_EXAMPLE = {
    **_CHUNK_HEAD,
    "choices": [
        {"index": 0, "delta": {"role": "assistant", "content": _CONTENT}, "finish_reason": None}
    ],
}
_FINISH_CHUNK_EXAMPLE = {
    **_CHUNK_HEAD,
    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
}
_USAGE_CHUNK_EXAMPLE = {
    **_CHUNK_HEAD,
    "choices": [],
    "usage": {"prompt_tokens": 812, "completion_tokens": 96, "total_tokens": 908},
}

# Section 7.7
_MODELS_EXAMPLE = {
    "object": "list",
    "data": [
        {"id": "openai/gpt-4o", "object": "model", "created": 0, "owned_by": "openai"},
        {"id": "gpt-4", "object": "model", "created": 0, "owned_by": "harness"},
    ],
}

# Section 7.5
_ERROR_EXAMPLE = {
    "error": {
        "message": (
            "Usage limit reached: tokens 1000412 of 1000000; resets at 2026-10-22 00:00:00"
        ),
        "type": "permission_error",
        "param": None,
        "code": "usage_limit_exceeded",
        "harness": {
            "reason": "Usage limit reached",
            "limit": "tokens",
            "maximum": 1000000,
            "actual": 1000412,
            "resets_at": "2026-10-22 00:00:00",
        },
    }
}

_OPTIONAL_REQUEST_FIELDS = (
    "stream_options",
    "temperature",
    "top_p",
    "max_tokens",
    "stop",
    "max_completion_tokens",
    "n",
    "logprobs",
    "top_logprobs",
    "response_format",
    "tools",
    "tool_choice",
    "functions",
    "function_call",
    "modalities",
    "audio",
    "user",
)


def _usage():
    return Usage(prompt_tokens=812, completion_tokens=96, total_tokens=908)


def _completion():
    return ChatCompletion(
        id=chat_completion_id(1842),
        created=_CREATED,
        model="openai/gpt-4o",
        choices=[Choice(message=AssistantMessage(content=_CONTENT), finish_reason="stop")],
        usage=_usage(),
        harness=HarnessCompletionInfo(audit_id=1842),
    )


def _chunk(choices, usage=None):
    return ChatCompletionChunk(
        id=chat_completion_id(1842),
        created=_CREATED,
        model="openai/gpt-4o",
        choices=choices,
        usage=usage,
    )


def _content_chunk():
    return _chunk([ChunkChoice(delta=ChunkDelta(role="assistant", content=_CONTENT))])


def _finish_chunk():
    return _chunk([ChunkChoice(delta=ChunkDelta(), finish_reason="stop")])


def _usage_chunk():
    return _chunk([], usage=_usage())


_CHUNK_CASES = [
    pytest.param(_content_chunk, _CONTENT_CHUNK_EXAMPLE, id="content"),
    pytest.param(_finish_chunk, _FINISH_CHUNK_EXAMPLE, id="finish"),
    pytest.param(_usage_chunk, _USAGE_CHUNK_EXAMPLE, id="usage"),
]


def _all_dumps(model):
    """The python, json-mode and JSON-string serializations, which must agree."""
    return [model.model_dump(), model.model_dump(mode="json"), json.loads(model.model_dump_json())]


# --- Request (Section 7.1) ---------------------------------------------------


def test_request_keeps_unknown_keys_in_model_extra():
    body = {
        "model": "openai/gpt-4o",
        "messages": [{"role": "user", "content": "hi"}],
        "stream": True,
        "seed": 7,
        "profile": "chat",
        "session_id": "x",
    }
    request = ChatCompletionRequest.model_validate(body)

    assert request.model == "openai/gpt-4o"
    assert request.messages == [{"role": "user", "content": "hi"}]
    assert request.stream is True
    assert request.model_extra == {"seed": 7, "profile": "chat", "session_id": "x"}
    dumped = request.model_dump()
    assert {key: dumped[key] for key in body} == body


def test_request_defaults():
    request = ChatCompletionRequest(model="gpt-4", messages=[])

    assert request.stream is False
    assert request.model_extra == {}
    for name in _OPTIONAL_REQUEST_FIELDS:
        assert getattr(request, name) is None
        assert name not in request.model_fields_set


def test_request_tells_absent_from_explicit_null():
    explicit = ChatCompletionRequest.model_validate({"model": "m", "messages": [], "n": None})
    absent = ChatCompletionRequest.model_validate({"model": "m", "messages": []})

    assert "n" in explicit.model_fields_set
    assert "n" not in absent.model_fields_set


def test_request_parameters_are_not_typed_by_pydantic():
    # STORY-006 judges these values and names the `param`; parsing must not.
    request = ChatCompletionRequest.model_validate(
        {"model": "m", "messages": [], "temperature": "hot", "n": 3, "tools": [{"type": "x"}]}
    )

    assert request.temperature == "hot"
    assert request.n == 3
    assert request.tools == [{"type": "x"}]


@pytest.mark.parametrize(
    "body",
    [
        pytest.param({"messages": []}, id="no-model"),
        pytest.param({"model": "m"}, id="no-messages"),
        pytest.param({"model": "m", "messages": "hi"}, id="messages-string"),
        pytest.param({"model": "m", "messages": {"role": "user"}}, id="messages-object"),
        pytest.param({"model": 5, "messages": []}, id="model-not-string"),
    ],
)
def test_request_missing_or_malformed_required_fields_fail(body):
    with pytest.raises(ValidationError):
        ChatCompletionRequest.model_validate(body)


def test_request_messages_items_stay_raw():
    messages = [{"role": "developer", "content": [{"type": "text", "text": "x"}]}, 3, None]
    request = ChatCompletionRequest.model_validate({"model": "m", "messages": messages})

    assert request.messages == messages


# --- Completion (Section 7.4) ------------------------------------------------


def test_completion_matches_section_7_4():
    for dumped in _all_dumps(_completion()):
        assert dumped == _COMPLETION_EXAMPLE


def test_chat_completion_id_is_the_one_derivation():
    assert chat_completion_id(1842) == "chatcmpl-harness-1842"
    assert chat_completion_id(1).startswith(CHAT_COMPLETION_ID_PREFIX)


@pytest.mark.parametrize("value", ["tool_calls", "error", ""])
def test_completion_refuses_an_unknown_finish_reason(value):
    # The translator (STORY-009) maps anything else the upstream sends to "stop".
    with pytest.raises(ValidationError):
        Choice(message=AssistantMessage(content="x"), finish_reason=value)


# --- Chunks, models, errors (Sections 7.5-7.7) -------------------------------


@pytest.mark.parametrize("build, expected", _CHUNK_CASES)
def test_chunks_match_section_7_6(build, expected):
    for dumped in _all_dumps(build()):
        assert dumped == expected


def test_model_list_matches_section_7_7():
    models = ModelList(
        data=[
            ModelEntry(id="openai/gpt-4o", owned_by="openai"),
            ModelEntry(id="gpt-4", owned_by="harness"),
        ]
    )

    for dumped in _all_dumps(models):
        assert dumped == _MODELS_EXAMPLE


def test_error_matches_section_7_5():
    error = ErrorResponse(
        error=ErrorDetail(
            message=_ERROR_EXAMPLE["error"]["message"],
            type="permission_error",
            code="usage_limit_exceeded",
            harness=_ERROR_EXAMPLE["error"]["harness"],
        )
    )

    for dumped in _all_dumps(error):
        assert dumped == _ERROR_EXAMPLE


def test_error_without_harness_keeps_the_key_as_null():
    error = ErrorResponse(
        error=ErrorDetail(
            message="messages[0]: unknown role",
            type="invalid_request_error",
            param="messages[0]",
            code="invalid_messages",
        )
    )

    assert error.model_dump(mode="json") == {
        "error": {
            "message": "messages[0]: unknown role",
            "type": "invalid_request_error",
            "param": "messages[0]",
            "code": "invalid_messages",
            "harness": None,
        }
    }


@pytest.mark.parametrize("value", ["rate_limit_error", "not_found_error", ""])
def test_error_type_is_one_of_the_four(value):
    with pytest.raises(ValidationError):
        ErrorDetail(message="m", type=value, code="c")


# --- The OpenAI SDK's own types (AC 5) ---------------------------------------


def test_openai_sdk_validates_the_completion():
    openai = pytest.importorskip("openai")

    parsed = openai.types.chat.ChatCompletion.model_validate(
        json.loads(_completion().model_dump_json())
    )

    assert parsed.id == "chatcmpl-harness-1842"
    assert parsed.choices[0].finish_reason == "stop"
    assert parsed.choices[0].message.content == _CONTENT
    assert parsed.usage.total_tokens == 908
    assert parsed.model_extra["harness"]["audit_id"] == 1842


@pytest.mark.parametrize("build, expected", _CHUNK_CASES)
def test_openai_sdk_validates_each_chunk(build, expected):
    openai = pytest.importorskip("openai")

    parsed = openai.types.chat.ChatCompletionChunk.model_validate(
        json.loads(build().model_dump_json())
    )

    assert parsed.id == "chatcmpl-harness-1842"
    assert len(parsed.choices) == len(expected["choices"])
