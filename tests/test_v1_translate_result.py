"""PRD-015 STORY-009 `translate_result` and `translate_device`; STORY-010
`translate_verdict`; STORY-011 `translate_fault`.

The success translation builds Section 7.4's `chat.completion` from the
pipeline's `QuerySuccessResponse` and the upstream result the router captured:
the finish reason (or "stop"), the split (0 when missing, total as reported)
and the `harness` object. The device header is stripped, at most 128 printable
characters, and its refusal never echoes the value. Each blocked pipeline
result maps to its Section 7.5 row, and every blocked member has one. Each
pipeline fault code maps to its 5xx row, and only the transient ones are
retryable (D7). No app, no storage: every
test here runs under `-m "not db"`. The module's purity is pinned in
`tests/test_v1_translate_request.py::test_is_pure`, which covers both halves.
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

from typing import get_args

import pytest

from app.models.schemas import (
    QueryBlockedContextLimitResponse,
    QueryBlockedDuplicateResponse,
    QueryBlockedForbiddenResponse,
    QueryBlockedSuspiciousResponse,
    QueryBlockedUsageLimitResponse,
    QuerySuccessResponse,
)
from app.models.v1_schemas import ErrorDetail, chat_completion_id
from app.services.openrouter_client import OpenRouterResult
from app.services.query_pipeline import QueryPipelineResult
from app.services.v1_translate import (
    _FAULTS,
    _VERDICTS,
    INTERNAL_ERROR,
    INVALID_HEADER,
    MAX_DEVICE_LENGTH,
    REDACTION_FAILED,
    STORAGE_UNAVAILABLE,
    STORAGE_UNAVAILABLE_MESSAGE,
    UPSTREAM_ERROR,
    UPSTREAM_UNAVAILABLE,
    QueryBlockedResponse,
    V1Error,
    V1RequestError,
    translate_device,
    translate_fault,
    translate_result,
    translate_verdict,
)

_CREATED = 1792569600
_AUDIT_REF = "0" * 32  # PRD-018 D14: required on every success


def _success(**overrides):
    fields = {
        "response": "Hello from the model.",
        "audit_id": 1842,
        "audit_ref": _AUDIT_REF,  # PRD-018 D14
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
        # PRD-018 D14: harness.audit_ref is on every success.
        "harness": {
            "audit_id": 1842,
            "audit_ref": _AUDIT_REF,
            "pii_redacted": False,
            "pii_entities_masked": [],
        },
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

    # PRD-018 D14: harness.audit_ref is on every success.
    assert harness == {
        "audit_id": 1842,
        "audit_ref": _AUDIT_REF,
        "pii_redacted": True,
        "pii_entities_masked": ["EMAIL_ADDRESS"],
    }


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


# --- translate_verdict (STORY-010) ---------------------------------------------
#
# Section 7.5's table, one case per verdict cell in the story's AC 1. Each case
# pins the whole V1Error, so a changed status, type, code or message is a
# diff here.

_RESETS_AT = "2026-10-22T00:00:00Z"

_VERDICT_CASES = [
    (
        QueryBlockedDuplicateResponse(
            reason="Duplicate query within 24 hours", first_query_at="2026-10-21T09:00:00Z"
        ),
        400, "invalid_request_error", "duplicate_request",
        "Duplicate query within 24 hours: first seen 2026-10-21T09:00:00Z",
    ),
    (
        QueryBlockedSuspiciousResponse(
            reason="Suspicious pattern detected", pattern="ignore previous instructions"
        ),
        400, "invalid_request_error", "suspicious_pattern",
        "Suspicious pattern detected: ignore previous instructions",
    ),
    (
        QueryBlockedContextLimitResponse(
            reason="Conversation exceeds context limit", limit="messages", maximum=100, actual=140
        ),
        400, "invalid_request_error", "context_length_exceeded",
        "Conversation exceeds context limit: messages 140 > 100",
    ),
    (
        QueryBlockedContextLimitResponse(
            reason="Conversation exceeds context limit", limit="characters", maximum=50, actual=51
        ),
        400, "invalid_request_error", "context_length_exceeded",
        "Conversation exceeds context limit: characters 51 > 50",
    ),
    (
        QueryBlockedContextLimitResponse(
            reason="Conversation exceeds redaction limit",
            limit="redaction_characters", maximum=200000, actual=200001,
        ),
        400, "invalid_request_error", "redaction_limit_exceeded",
        "Conversation exceeds redaction limit: redaction_characters 200001 > 200000",
    ),
    (
        QueryBlockedForbiddenResponse(
            reason="Missing required permission", required_permission="query:submit"
        ),
        403, "permission_error", "permission_denied",
        "Missing required permission: query:submit",
    ),
    (
        QueryBlockedForbiddenResponse(
            reason="Missing required permission", required_permission="query:byok"
        ),
        403, "permission_error", "permission_denied",
        "Missing required permission: query:byok",
    ),
    (
        QueryBlockedForbiddenResponse(
            reason="Model not permitted for this role",
            required_permission="query:model:openai/gpt-4o",
        ),
        403, "permission_error", "model_not_permitted",
        "Model not permitted for this role: query:model:openai/gpt-4o",
    ),
    (
        QueryBlockedForbiddenResponse(
            reason="Break-glass credential not permitted on this ingress",
            required_permission="ingress:break_glass",
        ),
        403, "permission_error", "break_glass_not_permitted",
        "Break-glass credential not permitted on this ingress: ingress:break_glass",
    ),
    (
        QueryBlockedUsageLimitResponse(
            reason="Usage limit reached", limit="requests", maximum=60, actual=61,
            resets_at="2026-10-21T09:01:00Z",
        ),
        403, "permission_error", "usage_limit_exceeded",
        "Usage limit reached: requests 61 of 60; resets at 2026-10-21T09:01:00Z",
    ),
    (
        QueryBlockedUsageLimitResponse(
            reason="Usage limit reached", limit="tokens", maximum=1000000, actual=1000412,
            resets_at=_RESETS_AT,
        ),
        403, "permission_error", "usage_limit_exceeded",
        f"Usage limit reached: tokens 1000412 of 1000000; resets at {_RESETS_AT}",
    ),
]


@pytest.mark.parametrize(
    "result, status_code, type_, code, message",
    _VERDICT_CASES,
    ids=[f"{type(case[0]).__name__}-{case[3]}-{i}" for i, case in enumerate(_VERDICT_CASES)],
)
def test_verdict_maps_to_the_section_7_5_row(result, status_code, type_, code, message):
    assert translate_verdict(result) == V1Error(
        status_code=status_code,
        type=type_,
        code=code,
        message=message,
        # Every field but the constant `status`.
        harness=result.model_dump(mode="json", exclude={"status"}),
        param=None,
    )


def test_harness_is_every_field_but_status():
    result = QueryBlockedUsageLimitResponse(
        reason="Usage limit reached", limit="tokens", maximum=1000000, actual=1000412,
        resets_at=_RESETS_AT,
    )

    assert translate_verdict(result).harness == {
        "reason": "Usage limit reached",
        "limit": "tokens",
        "maximum": 1000000,
        "actual": 1000412,
        "resets_at": _RESETS_AT,
    }


def test_every_blocked_member_has_a_verdict():
    # A future QueryPipelineResult member without a row fails here, not in
    # production as a TypeError.
    blocked = set(get_args(QueryPipelineResult)) - {QuerySuccessResponse}

    assert blocked == set(get_args(QueryBlockedResponse))
    assert blocked == set(_VERDICTS)


def test_no_verdict_is_retryable_by_status():
    # T7: the OpenAI SDKs retry 429 and every 5xx.
    statuses = {row[0] for row in _VERDICTS.values()}
    statuses |= {translate_verdict(case[0]).status_code for case in _VERDICT_CASES}

    assert statuses <= {400, 403}


def test_success_has_no_verdict():
    with pytest.raises(TypeError):
        translate_verdict(_success())


def test_every_verdict_type_fits_the_error_schema():
    for case in _VERDICT_CASES:
        error = translate_verdict(case[0])
        ErrorDetail(message=error.message, type=error.type, code=error.code, harness=error.harness)


def test_no_verdict_is_retryable():
    # D7: `retryable` is what keeps `x-should-retry: false` off a response.
    assert not any(translate_verdict(case[0]).retryable for case in _VERDICT_CASES)


# --- translate_fault (STORY-011) -----------------------------------------------
#
# Section 7.5's four fault rows. The message is passed through as received:
# the router hands over the exception's own text.

_FAULT_CASES = [
    (UPSTREAM_UNAVAILABLE, 502, True),
    (UPSTREAM_ERROR, 502, False),
    (INTERNAL_ERROR, 500, True),
    (REDACTION_FAILED, 500, False),
    # PRD-018 D8: a storage outage is a retryable 503.
    (STORAGE_UNAVAILABLE, 503, True),
]


@pytest.mark.parametrize(
    "code, status_code, retryable", _FAULT_CASES, ids=[case[0] for case in _FAULT_CASES]
)
def test_fault_maps_to_the_section_7_5_row(code, status_code, retryable):
    assert translate_fault(code, "OpenRouter request failed: probe") == V1Error(
        status_code=status_code,
        type="api_error",
        code=code,
        message="OpenRouter request failed: probe",
        harness=None,
        param=None,
        retryable=retryable,
    )


def test_unknown_fault_is_a_type_error():
    with pytest.raises(TypeError):
        translate_fault("duplicate_request", "probe")


def test_every_fault_is_a_5xx_and_only_transient_ones_retry():
    assert set(_FAULTS) == {case[0] for case in _FAULT_CASES}
    # PRD-018 D8: 503 joins the allowed statuses (storage outage).
    assert {row[0] for row in _FAULTS.values()} <= {500, 502, 503}
    assert {code for code, row in _FAULTS.items() if row[2]} == {
        UPSTREAM_UNAVAILABLE,
        INTERNAL_ERROR,
        STORAGE_UNAVAILABLE,  # PRD-018 D8: retryable
    }


def test_storage_unavailable_carries_retry_after_and_its_message():
    # PRD-018 D8: the router sends `retry_after_seconds` as `Retry-After`.
    error = translate_fault(
        STORAGE_UNAVAILABLE, STORAGE_UNAVAILABLE_MESSAGE, retry_after_seconds=7
    )
    assert error.retry_after_seconds == 7
    assert error.message == STORAGE_UNAVAILABLE_MESSAGE
    assert translate_fault(INTERNAL_ERROR, "x").retry_after_seconds is None


def test_every_fault_type_fits_the_error_schema():
    for code, _status, _retryable in _FAULT_CASES:
        error = translate_fault(code, "probe")
        ErrorDetail(message=error.message, type=error.type, code=error.code, harness=error.harness)


# --- PRD-017 STORY-011: the release on the completion --------------------------
#
# `translate_result` reads `result.tool_outcome` (step 7c) and never the upstream's
# own `tool_calls` (T1). Decisions are stand-ins with the five fields it reads;
# `apply_decisions` needs only `tool_call_id` and `decision`.

import json
import types

from app.models.messages import ToolCallSpec
from app.services import tool_release

_ARGS_1 = '{"path": "src/a.py",  "n": 1}'  # spacing kept: bytes the model wrote (D13)
_ARGS_2 = '{"command":"ls"}'
_READ = ToolCallSpec("call_1", "read", _ARGS_1)
_BASH = ToolCallSpec("call_2", "bash", _ARGS_2)
_NOTE = "[harness] tool call bash (call_2) was denied: no."


def _decision(call, decision, rule="r", reason="why"):
    return types.SimpleNamespace(
        tool_call_id=call.id, tool_name=call.name, decision=decision, rule=rule, reason=reason
    )


def _with_outcome(result, calls, decisions):
    result._tool_outcome = tool_release.ToolOutcome(
        tool_release.apply_decisions(calls, decisions), tuple(decisions)
    )
    return result


def _released_dump(response, calls, decisions, finish_reason="tool_calls"):
    result = _with_outcome(_success(response=response), calls, decisions)
    return translate_result(result, _upstream(finish_reason=finish_reason), _CREATED)


def test_two_released_calls_and_no_text():
    """AC1: content null, both calls, arguments the very same strings, finish tool_calls."""
    completion = _released_dump("", [_READ, _BASH], [_decision(_READ, "allow"), _decision(_BASH, "allow")])
    dumped = completion.model_dump(mode="json")
    choice = dumped["choices"][0]

    assert choice["message"] == {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {"id": "call_1", "type": "function", "function": {"name": "read", "arguments": _ARGS_1}},
            {"id": "call_2", "type": "function", "function": {"name": "bash", "arguments": _ARGS_2}},
        ],
    }
    assert choice["finish_reason"] == "tool_calls"
    sent = completion.choices[0].message.tool_calls
    assert sent[0].function.arguments is _READ.arguments
    assert sent[1].function.arguments is _BASH.arguments


def test_every_call_denied_is_the_notes_with_tool_calls_null():
    """AC2: tool_calls is null (key kept), content the note, finish stop even if the upstream said tool_calls."""
    dumped = _released_dump(_NOTE, [_BASH], [_decision(_BASH, "deny")]).model_dump(mode="json")
    choice = dumped["choices"][0]

    assert "tool_calls" in choice["message"] and choice["message"]["tool_calls"] is None
    assert choice["message"]["content"] == _NOTE
    assert choice["finish_reason"] == "stop"


def test_text_plus_released_calls_carries_both():
    dumped = _released_dump("Reading it.", [_READ], [_decision(_READ, "allow")]).model_dump(mode="json")
    choice = dumped["choices"][0]

    assert choice["message"]["content"] == "Reading it."
    assert [c["id"] for c in choice["message"]["tool_calls"]] == ["call_1"]
    assert choice["finish_reason"] == "tool_calls"


def test_mixed_release_keeps_the_note_and_the_allowed_call():
    dumped = _released_dump(
        _NOTE, [_READ, _BASH], [_decision(_READ, "allow"), _decision(_BASH, "deny")]
    ).model_dump(mode="json")
    choice = dumped["choices"][0]

    assert choice["message"]["content"] == _NOTE
    assert [c["id"] for c in choice["message"]["tool_calls"]] == ["call_1"]
    assert choice["finish_reason"] == "tool_calls"


def test_harness_actions_list_every_decision_in_model_order():
    """AC3: one entry per evaluated call, released or not (D14)."""
    third = ToolCallSpec("call_3", "write", "{}")
    decisions = [
        _decision(_READ, "allow", "a.rule", "ok"),
        _decision(_BASH, "flag", "f.rule", "watch"),
        _decision(third, "deny", "d.rule", "no"),
    ]

    dumped = _released_dump(_NOTE, [_READ, _BASH, third], decisions).model_dump(mode="json")

    assert dumped["harness"]["actions"] == [
        {"tool_call_id": "call_1", "tool_name": "read", "decision": "allow", "rule": "a.rule", "reason": "ok"},
        {"tool_call_id": "call_2", "tool_name": "bash", "decision": "flag", "rule": "f.rule", "reason": "watch"},
        {"tool_call_id": "call_3", "tool_name": "write", "decision": "deny", "rule": "d.rule", "reason": "no"},
    ]
    # allow and flag are released, the deny is not.
    assert [c["id"] for c in dumped["choices"][0]["message"]["tool_calls"]] == ["call_1", "call_2"]


def test_release_finish_reason_wins_over_the_upstream():
    released = _released_dump("", [_READ], [_decision(_READ, "allow")], finish_reason="length")
    denied = _released_dump(_NOTE, [_BASH], [_decision(_BASH, "deny")], finish_reason="length")

    assert released.choices[0].finish_reason == "tool_calls"
    assert denied.choices[0].finish_reason == "stop"


@pytest.mark.parametrize("response", ["Hello from the model.", ""], ids=["text", "empty"])
def test_without_an_outcome_the_body_is_prd_015s(response):
    """AC5 (DD-1): no call evaluated, so neither new key exists; an empty text stays ""."""
    dumped = _dump(result=_success(response=response))

    assert dumped["choices"][0]["message"] == {"role": "assistant", "content": response}
    assert set(dumped["harness"]) == {"audit_id", "audit_ref", "pii_redacted", "pii_entities_masked"}  # PRD-018 D14
    assert "tool_calls" not in json.dumps(dumped) and "actions" not in json.dumps(dumped)


def test_translate_result_never_reads_upstream_tool_calls():
    """T1: no `upstream.tool_calls` in the translator; calls come from the pipeline's outcome."""
    import ast
    import inspect
    import textwrap

    tree = ast.parse(textwrap.dedent(inspect.getsource(translate_result)))
    reads = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and node.attr == "tool_calls"
        and isinstance(node.value, ast.Name)
        and node.value.id == "upstream"
    ]

    assert reads == []


def test_completion_with_calls_parses_in_the_openai_sdk():
    openai = pytest.importorskip("openai")
    completion = _released_dump("", [_READ, _BASH], [_decision(_READ, "allow"), _decision(_BASH, "allow")])

    parsed = openai.types.chat.ChatCompletion.model_validate(json.loads(completion.model_dump_json()))

    assert parsed.choices[0].finish_reason == "tool_calls"
    assert [c.function.arguments for c in parsed.choices[0].message.tool_calls] == [_ARGS_1, _ARGS_2]


def test_a_journaled_success_has_a_null_audit_id_a_ref_and_a_ref_completion_id():
    # PRD-018 D14, O2: the id is `chatcmpl-harness-ref-<write_id>`, which a client
    # parsing the integer after `chatcmpl-harness-` cannot mistake for an audit id.
    ref = "ab" * 16
    body = _dump(result=_success(audit_id=None, audit_ref=ref))

    assert body["id"] == f"chatcmpl-harness-ref-{ref}"
    assert body["harness"]["audit_id"] is None and body["harness"]["audit_ref"] == ref
    assert "audit_id" in body["harness"]  # present as null, never dropped
