"""PRD-015 STORY-009 `translate_result` and `translate_device`.

The success translation builds Section 7.4's `chat.completion` from the
pipeline's `QuerySuccessResponse` and the upstream result the router captured:
the finish reason (or "stop"), the split (0 when missing, total as reported)
and the `harness` object. The device header is stripped, at most 128 printable
characters, and its refusal never echoes the value. No app, no storage: every
test here runs under `-m "not db"`. The module's purity is pinned in
`tests/test_v1_translate_request.py::test_is_pure`, which covers both halves.
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import pytest

from app.models.schemas import QuerySuccessResponse
from app.models.v1_schemas import chat_completion_id
from app.services.openrouter_client import OpenRouterResult
from app.services.v1_translate import (
    INVALID_HEADER,
    MAX_DEVICE_LENGTH,
    V1RequestError,
    translate_device,
    translate_result,
)

_CREATED = 1792569600


def _success(**overrides):
    fields = {
        "response": "Hello from the model.",
        "audit_id": 1842,
        "model_used": "openai/gpt-4o",
        "tokens_used": 908,
    }
    fields.update(overrides)
    return QuerySuccessResponse(**fields)


def _upstream(**overrides):
    fields = {
        "response": "Hello from the model.",
        "model_used": "openai/gpt-4o",
        "tokens_used": 908,
        "input_tokens": 812,
        "output_tokens": 96,
        "finish_reason": "stop",
    }
    fields.update(overrides)
    return OpenRouterResult(**fields)


def _dump(result=None, upstream=None):
    return translate_result(result or _success(), upstream or _upstream(), _CREATED).model_dump(
        mode="json"
    )


# --- translate_result ----------------------------------------------------------


def test_builds_the_section_7_4_example():
    assert _dump() == {
        "id": "chatcmpl-harness-1842",
        "object": "chat.completion",
        "created": _CREATED,
        "model": "openai/gpt-4o",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "Hello from the model."},
                "logprobs": None,
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 812, "completion_tokens": 96, "total_tokens": 908},
        "harness": {"audit_id": 1842, "pii_redacted": False, "pii_entities_masked": []},
    }


@pytest.mark.parametrize("reason", ["stop", "length", "content_filter"])
def test_a_finish_reason_the_schema_carries_passes_through(reason):
    assert _dump(upstream=_upstream(finish_reason=reason))["choices"][0]["finish_reason"] == reason


@pytest.mark.parametrize("reason", [None, "error", "tool_calls", ""])
def test_any_other_finish_reason_is_stop(reason):
    assert _dump(upstream=_upstream(finish_reason=reason))["choices"][0]["finish_reason"] == "stop"


def test_a_missing_split_is_zero_with_the_reported_total():
    usage = _dump(upstream=_upstream(input_tokens=None, output_tokens=None))["usage"]

    assert usage == {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 908}


@pytest.mark.parametrize(
    "split, expected",
    [
        ({"input_tokens": None, "output_tokens": 96}, (0, 96)),
        ({"input_tokens": 812, "output_tokens": None}, (812, 0)),
        ({"input_tokens": 0, "output_tokens": 0}, (0, 0)),
    ],
)
def test_each_side_of_the_split_falls_back_alone(split, expected):
    usage = _dump(upstream=_upstream(**split))["usage"]

    assert (usage["prompt_tokens"], usage["completion_tokens"]) == expected
    assert usage["total_tokens"] == 908


def test_the_total_is_the_pipeline_result_s():
    usage = _dump(result=_success(tokens_used=1000))["usage"]

    assert usage["total_tokens"] == 1000


def test_harness_carries_the_pii_fields():
    harness = _dump(result=_success(pii_redacted=True, pii_entities_masked=["EMAIL_ADDRESS"]))[
        "harness"
    ]

    assert harness == {"audit_id": 1842, "pii_redacted": True, "pii_entities_masked": ["EMAIL_ADDRESS"]}


def test_id_and_model_come_from_the_pipeline_result():
    body = _dump(result=_success(audit_id=7, model_used="gpt-4"), upstream=_upstream(model_used="other"))

    assert body["id"] == chat_completion_id(7)
    assert body["model"] == "gpt-4"


# --- translate_device ----------------------------------------------------------


@pytest.mark.parametrize("raw", [None, "", "   ", "\t "])
def test_absent_or_blank_device_is_none(raw):
    assert translate_device(raw) is None


def test_device_is_stripped():
    assert translate_device(" laptop-01 ") == "laptop-01"


def test_device_at_the_limit_is_kept():
    value = "d" * MAX_DEVICE_LENGTH

    assert translate_device(value) == value
    # The limit applies after stripping.
    assert translate_device(f"  {value}  ") == value


def test_device_over_the_limit_is_invalid_header():
    with pytest.raises(V1RequestError) as caught:
        translate_device("d" * (MAX_DEVICE_LENGTH + 1))

    assert caught.value.code == INVALID_HEADER
    assert caught.value.param is None


@pytest.mark.parametrize("raw", ["dev\tice", "dev\x00ice", "dev\x7fice", "dev​ice", "dev\nice"])
def test_non_printable_device_is_invalid_header(raw):
    with pytest.raises(V1RequestError) as caught:
        translate_device(raw)

    assert caught.value.code == INVALID_HEADER


def test_device_refusal_never_echoes_the_value():
    canary = "SECRET-CANARY" * 20

    with pytest.raises(V1RequestError) as caught:
        translate_device(canary)

    assert "SECRET-CANARY" not in str(caught.value)
    assert "SECRET-CANARY" not in caught.value.message
    assert "X-Harness-Device" in caught.value.message
