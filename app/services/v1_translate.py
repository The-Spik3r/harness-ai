"""Request and result translation for `/v1` (PRD-015 Sections 4, 7.1-7.5).

Turns the wire request into pipeline arguments: the messages, the forwarded
generation parameters and the names of everything ignored, plus the
`X-Harness-Device` header. Turns a successful pipeline result into the
`chat.completion` the client reads, a blocked one into the `V1Error` the
router sends (Section 7.5), and a pipeline fault into the `V1Error` its retry
semantics call for (D7). Every refusal is a `V1RequestError`, which the
router maps to a 400 (STORY-009/010). Pure on purpose, like
`app/models/messages.py`: no I/O, no settings reads, no logging, no clock.

PRD-017 STORY-008: with `tools_enabled` the request may carry `tools`,
`tool_choice`, `parallel_tool_calls` and tool turns (Sections 4, 6.3, 10); the
router reads `V1_TOOLS_ENABLED` and `V1_TOOL_MODELS` per request and passes
them in, because this module reads no settings. The defaults are the flag-off
values, so PRD-015's behaviour is unchanged byte for byte (D10). STORY-011
builds the non-streamed release shape from the pipeline's `tool_outcome`.
"""

from dataclasses import dataclass
from typing import (
    Any,
    Callable,
    Dict,
    FrozenSet,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    Union,
)

from app.models.messages import (
    Message,
    MessageNormalizationError,
    conversation_shape_violation,
    normalize_message,
)
from app.models.schemas import (
    QueryBlockedContextLimitResponse,
    QueryBlockedDuplicateResponse,
    QueryBlockedForbiddenResponse,
    QueryBlockedSuspiciousResponse,
    QueryBlockedUsageLimitResponse,
    QuerySuccessResponse,
)
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
    chat_completion_id,
    chat_completion_ref_id,
)
# PRD-020 STORY-005: the pure submodules, not the package (`upstream/__init__`
# imports httpx and the registry), so this module stays pure.
from app.services.upstream.params import (
    GenerationParams,
    ToolParams,
    UnsupportedParameterError,
)
from app.services.upstream.types import UpstreamResult as OpenRouterResult

INVALID_MESSAGES = "invalid_messages"
INVALID_PARAMETER = "invalid_parameter"
UNSUPPORTED_PARAMETER = "unsupported_parameter"
# The `tools` parameter refusal raises this same constant, so a client sees
# one code whether the tool use was in a parameter or a message.
TOOLS_NOT_SUPPORTED = "tools_not_supported"
INVALID_HEADER = "invalid_header"
# A body that is not JSON or fails `ChatCompletionRequest` (router handler).
INVALID_REQUEST = "invalid_request"

# Section 7.5, one per verdict. `context_length_exceeded` is OpenAI's own
# spelling, so clients that already handle it (Aider) do.
DUPLICATE_REQUEST = "duplicate_request"
SUSPICIOUS_PATTERN = "suspicious_pattern"
CONTEXT_LENGTH_EXCEEDED = "context_length_exceeded"
REDACTION_LIMIT_EXCEEDED = "redaction_limit_exceeded"
MODEL_NOT_PERMITTED = "model_not_permitted"
BREAK_GLASS_NOT_PERMITTED = "break_glass_not_permitted"
PERMISSION_DENIED = "permission_denied"
USAGE_LIMIT_EXCEEDED = "usage_limit_exceeded"
# A missing or invalid bearer (router handler).
INVALID_API_KEY = "invalid_api_key"
# A `GET /v1/models/{id}` name not in MODEL_ALLOWLIST (router, Section 7.7).
MODEL_NOT_FOUND = "model_not_found"

# Section 7.5, one per pipeline fault (D7). The router names the fault.
UPSTREAM_UNAVAILABLE = "upstream_unavailable"
UPSTREAM_ERROR = "upstream_error"
INTERNAL_ERROR = "internal_error"
REDACTION_FAILED = "redaction_failed"
# PRD-018 D8, O4: a storage outage (the unit of work's `StorageUnavailableError`),
# as opposed to `internal_error`'s other storage faults. Fixed copy: driver
# text never reaches a client.
STORAGE_UNAVAILABLE = "storage_unavailable"
STORAGE_UNAVAILABLE_MESSAGE = "Storage is unavailable; the request was not sent to the model."
# PRD-018 D10, T5: step 8 runs after the upstream call, so this copy must not
# say "not sent to the model". Fixed: driver text never reaches a client.
AUDIT_UNAVAILABLE_MESSAGE = (
    "Storage is unavailable; the response could not be recorded, so it was not released."
)

# The forbidden labels the pipeline writes (authz.authorize_model, step 2b).
_MODEL_PERMISSION_PREFIX = "query:model:"
_BREAK_GLASS_PERMISSION = "ingress:break_glass"

IGNORED_MESSAGE_NAME = "messages[].name"

DEVICE_HEADER = "X-Harness-Device"
MAX_DEVICE_LENGTH = 128

# The values `FinishReason` accepts from an upstream (v1_schemas). Anything else
# it reports, None included, is sent as "stop". "tool_calls" comes only from the
# release (PRD-017 DD-2), so an upstream `tool_calls` with nothing evaluated is
# still "stop".
_FINISH_REASONS = frozenset({"stop", "length", "content_filter"})

# PRD-015 Section 7.3 (D3): every key a client sends is in exactly one of three
# groups. Widening the upstream surface means changing PRD-010's allowlist,
# deliberately: test_forwarded_is_generation_params_plus_alias fails otherwise.
FORWARDED = frozenset({"temperature", "top_p", "max_tokens", "stop", "max_completion_tokens"})

# Accepted only as one of its listed defaults, compared by type and value so
# `n: true` is not `n: 1`. Absent is always accepted. Checked in this order.
REJECTED_UNLESS_DEFAULT: Mapping[str, Tuple[str, Tuple[Any, ...]]] = {
    "tools": (TOOLS_NOT_SUPPORTED, (None, [])),
    "functions": (TOOLS_NOT_SUPPORTED, (None, [])),
    "tool_choice": (TOOLS_NOT_SUPPORTED, (None, "none")),
    "function_call": (TOOLS_NOT_SUPPORTED, (None,)),
    "n": (UNSUPPORTED_PARAMETER, (None, 1)),
    "logprobs": (UNSUPPORTED_PARAMETER, (None, False)),
    "top_logprobs": (UNSUPPORTED_PARAMETER, (None,)),
    "response_format": (UNSUPPORTED_PARAMETER, (None, {"type": "text"})),
    "modalities": (UNSUPPORTED_PARAMETER, (None, ["text"])),
    "audio": (UNSUPPORTED_PARAMETER, (None,)),
}

# Read by translate_request itself, so neither forwarded nor ignored. Every
# other key is ignored and only its name recorded.
_STRUCTURAL = frozenset({"model", "messages", "stream", "stream_options"})

# PRD-017 Section 4, D11: the keys `V1_TOOLS_ENABLED` turns from rejected /
# ignored into tool params. REJECTED_UNLESS_DEFAULT above is the flag-off table
# (tests/e2e/_live.py mirrors it), so each key is in exactly one group per flag
# state: with the flag on, these three are tool params and `functions` /
# `function_call` stay rejected (D10). `parallel_tool_calls` is not declared on
# ChatCompletionRequest: with the flag off it stays an ignored unknown key.
TOOL_PARAMS = frozenset({"tools", "tool_choice", "parallel_tool_calls"})

_REJECTED_RULES = {
    TOOLS_NOT_SUPPORTED: "tool calling is not supported (PRD-017)",
    UNSUPPORTED_PARAMETER: "only the default value is supported on this endpoint",
}

# PRD-017 Section 10, flag on: `tool calling is not supported` would be false,
# so the two deprecated keys get their own text. Flag-off strings are untouched.
_LEGACY_TOOLS_RULE = "the deprecated function-calling API is not supported; use tools"
_FLAG_ON_REJECTED_RULES = {**_REJECTED_RULES, TOOLS_NOT_SUPPORTED: _LEGACY_TOOLS_RULE}
# PRD-017 D16: exactly this text, no location prefix.
_TOOL_MODEL_RULE = "model is not enabled for tool calling (V1_TOOL_MODELS)"

# Check order, and the rule each 400 names. The rule is the translator's own
# text: GenerationParams' messages end with the value (`got ...`), and `stop`
# can hold user text (T6).
_FORWARDED_RULES: Dict[str, str] = {
    "temperature": "must be a number between 0.0 and 2.0",
    "top_p": "must be a number greater than 0.0 and at most 1.0",
    "max_tokens": "must be an integer >= 1",
    "stop": "must be a string or a list of at most 4 strings",
    "max_completion_tokens": "must be an integer >= 1",
}
_ALIASES = {"max_completion_tokens": "max_tokens"}


class V1RequestError(Exception):
    """A request this ingress refuses before the pipeline runs.

    No pipeline step runs, so no audit row is written (PRD-015 T9). `message`
    names a location and the rule that failed, never a value (T6): content is
    untrusted and would otherwise reach the 400 body verbatim. `param` is the
    OpenAI error object's `param`.
    """

    def __init__(self, code: str, message: str, param: Optional[str] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.param = param


@dataclass(frozen=True)
class V1Call:
    """What the router passes to `run_conversation` (PRD-015 Section 6.1).

    No `profile` or `ingress`: the call site names those, never the request
    (T4). `params` is None when nothing was forwarded, so `call_openrouter` is
    called without `params=`, as for every other ingress. `tools` is the same
    for the tool request (PRD-017 Section 4, D11): None when nothing was
    forwarded, which is always so with the flag off and with `tools` absent,
    `null` or `[]` (STORY-004 decision), so `call_openrouter` is called without
    `tools=`.
    """

    messages: List[Message]
    params: Optional[GenerationParams]
    model: str
    stream: bool
    include_usage: bool
    ignored_params: Optional[str]
    tools: Optional[ToolParams] = None


@dataclass(frozen=True)
class V1Error:
    """An error the router sends as `ErrorResponse` with `status_code` (Section 7.5).

    `harness` is the pipeline response's own fields, or None when there is no
    pipeline response. `message` names the rule and its details, never content
    (T6). `retryable` is True only for a fault the same request may get past
    (D7); every verdict is False, and the router sends `x-should-retry: false`
    for any error that is not retryable. `retry_after_seconds` is set only for
    `storage_unavailable` (PRD-018 D8); the router sends it as `Retry-After`.
    """

    status_code: int
    type: str
    code: str
    message: str
    harness: Optional[Dict[str, Any]] = None
    param: Optional[str] = None
    retryable: bool = False
    retry_after_seconds: Optional[int] = None


def translate_messages(
    raw: Sequence[Any], *, tools_enabled: bool = False
) -> Tuple[List[Message], FrozenSet[str]]:
    """The client's `messages` as pipeline `Message`s, plus the ignored names.

    Per message, in order: `tool_calls` / `function_call` and the `tool` role
    are `tools_not_supported`; a `name` is recorded as ignored; `developer`
    becomes `system`; then `normalize_message`, whose error is wrapped with its
    text kept. The loop is `normalize_messages`' own, plus the index for `param`.

    The edge checks (non-empty, no `tool` turn, last turn `user`) duplicate
    `query_pipeline._validate_conversation` on purpose: that one is a
    programming-error guard that writes no row (PRD-010 Section 6.1), this one
    is the client-facing 400, so `InvalidConversationError` stays unreachable
    from `/v1` (PRD-015 Section 4).

    With `tools_enabled` (PRD-017 STORY-008) assistant `tool_calls` and `tool`
    turns go to the normalizer, a non-null `function_call` is still
    `tools_not_supported` (D10; `null` counts as absent, as an SDK
    `model_dump()` echo carries it), and the cross-message rules are
    `conversation_shape_violation`'s, the same helper as step 0 (D6), so the
    two cannot drift. The flag-off strings above are kept for PRD-015.
    """
    if isinstance(raw, (str, bytes)) or not isinstance(raw, Sequence):
        raise V1RequestError(INVALID_MESSAGES, "messages must be a list", "messages")
    if not raw:
        raise V1RequestError(INVALID_MESSAGES, "messages must not be empty", "messages")

    messages = []
    ignored = set()
    for index, item in enumerate(raw):
        location = f"messages[{index}]"
        if isinstance(item, Mapping):
            if tools_enabled:
                if item.get("function_call") is not None:
                    raise V1RequestError(
                        TOOLS_NOT_SUPPORTED,
                        f"{location}: function_call is the deprecated function-calling API; "
                        "use tool_calls",
                        location,
                    )
            else:
                # Before the normalizer: it refuses `tool_calls` itself, which
                # would surface as `invalid_messages`, and it accepts `tool`.
                if "tool_calls" in item or "function_call" in item:
                    raise V1RequestError(
                        TOOLS_NOT_SUPPORTED,
                        f"{location}: tool calls are not supported (PRD-017)",
                        location,
                    )
                if item.get("role") == "tool":
                    raise V1RequestError(
                        TOOLS_NOT_SUPPORTED,
                        f"{location}: tool turns are not supported (PRD-017)",
                        location,
                    )
            if "name" in item:
                ignored.add(IGNORED_MESSAGE_NAME)
            # `developer` is a wire alias, not a pipeline role: `Role` is not
            # widened. A copy, so the caller's request is never changed.
            if item.get("role") == "developer":
                item = {**item, "role": "system"}
        try:
            messages.append(normalize_message(item))
        except MessageNormalizationError as exc:
            raise V1RequestError(INVALID_MESSAGES, f"{location}: {exc}", location) from exc

    if tools_enabled:
        violation = conversation_shape_violation(messages)
        if violation is not None:
            index, rule = violation
            location = f"messages[{index}]"
            raise V1RequestError(INVALID_MESSAGES, f"{location}: {rule}", location)
    elif messages[-1].role != "user":
        location = f"messages[{len(messages) - 1}]"
        raise V1RequestError(
            INVALID_MESSAGES, f"{location}: the last message must be a user turn", location
        )
    return messages, frozenset(ignored)


def _is_default(value: Any, defaults: Tuple[Any, ...]) -> bool:
    # Type first: `True == 1` and `False == 0` would otherwise pass for `n`.
    return any(type(value) is type(default) and value == default for default in defaults)


def _check_rejected(
    sent: FrozenSet[str],
    values: Mapping[str, Any],
    skip: FrozenSet[str] = frozenset(),
    rules: Mapping[str, str] = _REJECTED_RULES,
) -> None:
    for key, (code, defaults) in REJECTED_UNLESS_DEFAULT.items():
        if key in skip:
            continue
        if key in sent and not _is_default(values[key], defaults):
            raise V1RequestError(code, f"{key}: {rules[code]}", key)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


# GenerationParams compares before it checks types, so "hot" would be a
# TypeError and True or 1.5 would pass. `stop` it checks itself.
_FORWARDED_TYPES = {
    "temperature": _is_number,
    "top_p": _is_number,
    "max_tokens": _is_integer,
    "max_completion_tokens": _is_integer,
}


def _forwarded_params(sent: FrozenSet[str], values: Mapping[str, Any]) -> Optional[GenerationParams]:
    collected: Dict[str, Any] = {}
    for key, rule in _FORWARDED_RULES.items():
        value = values.get(key) if key in sent else None
        # An explicit null is absent: GenerationParams treats None as unset.
        if value is None:
            continue
        refusal = V1RequestError(INVALID_PARAMETER, f"{key}: {rule}", key)
        check = _FORWARDED_TYPES.get(key)
        if check is not None and not check(value):
            raise refusal
        canonical = _ALIASES.get(key, key)
        try:
            # One key at a time, so the error knows its `param`.
            GenerationParams.from_mapping({canonical: value})
        except UnsupportedParameterError:
            # `from None`: the cause's message carries the value (T6).
            raise refusal from None
        if canonical in collected and collected[canonical] != value:
            raise V1RequestError(
                INVALID_PARAMETER, f"{key}: must equal {canonical} when both are sent", key
            )
        collected[canonical] = value
    return GenerationParams.from_mapping(collected) if collected else None


def _refusal(param: str, rule: str) -> V1RequestError:
    # Location and rule only (T6): a tool's name, description and schema are
    # client text and never reach the 400 body.
    return V1RequestError(INVALID_PARAMETER, f"{param}: {rule}", param)


def _check_tools(value: Any) -> List[Mapping[str, Any]]:
    """`tools` shape (PRD-017 F3, Section 10), and the list itself, never a copy.

    Shape only: no name pattern, no duplicate rule, and `parameters` is not
    interpreted. Unknown keys are kept, so the list is forwarded as received.
    """
    if not isinstance(value, list):
        raise _refusal("tools", "must be a list of tool objects")
    for index, item in enumerate(value):
        where = f"tools[{index}]"
        if not isinstance(item, Mapping):
            raise _refusal(where, "must be an object")
        if item.get("type") != "function":
            raise _refusal(f"{where}.type", 'must be "function"')
        function = item.get("function")
        if not isinstance(function, Mapping):
            raise _refusal(f"{where}.function", "must be an object")
        name = function.get("name")
        if not isinstance(name, str) or not name:
            raise _refusal(f"{where}.function.name", "must be a non-empty string")
        description = function.get("description")
        if description is not None and not isinstance(description, str):
            raise _refusal(f"{where}.function.description", "must be a string")
        parameters = function.get("parameters")
        if parameters is not None and not isinstance(parameters, Mapping):
            raise _refusal(f"{where}.function.parameters", "must be an object")
        strict = function.get("strict")
        if strict is not None and not isinstance(strict, bool):
            raise _refusal(f"{where}.function.strict", "must be a boolean")
    return value


_TOOL_CHOICE_RULE = (
    'must be "none", "auto", "required" or {"type": "function", "function": {"name": ...}}'
)
_TOOL_CHOICE_STRINGS = frozenset({"none", "auto", "required"})


def _check_tool_choice(value: Any, tools: Optional[List[Mapping[str, Any]]]) -> None:
    """`tool_choice` shape; a named function must be one of `tools` (when any)."""
    if isinstance(value, str):
        if value in _TOOL_CHOICE_STRINGS:
            return
        raise _refusal("tool_choice", _TOOL_CHOICE_RULE)
    if not isinstance(value, Mapping) or value.get("type") != "function":
        raise _refusal("tool_choice", _TOOL_CHOICE_RULE)
    function = value.get("function")
    name = function.get("name") if isinstance(function, Mapping) else None
    if not isinstance(name, str) or not name:
        raise _refusal("tool_choice", _TOOL_CHOICE_RULE)
    if tools is not None and name not in {tool["function"]["name"] for tool in tools}:
        raise _refusal("tool_choice", "must name a function in tools")


def _tool_params(
    sent: FrozenSet[str], values: Mapping[str, Any]
) -> Tuple[Optional[ToolParams], FrozenSet[str]]:
    """The flag-on tool request as `ToolParams`, plus the names it ignored.

    Checked in order: `tools`, `tool_choice`, `parallel_tool_calls`. With no
    tools to forward (`tools` absent, `null` or `[]`, STORY-004 decision) the
    result is None and nothing tool-related is forwarded: `tool_choice` may be
    absent, `null` or `"none"` and any other valid value is refused, and
    `parallel_tool_calls` is recorded as ignored, as with the flag off, so
    the flag never makes a PRD-015 request fail (D11). With tools, the values
    are forwarded as sent and `null` is absent.
    """
    raw_tools = values.get("tools") if "tools" in sent else None
    tools = _check_tools(raw_tools) if raw_tools is not None else None
    if not tools:
        tools = None
    choice = values.get("tool_choice") if "tool_choice" in sent else None
    if choice is not None:
        _check_tool_choice(choice, tools)
    parallel = values.get("parallel_tool_calls") if "parallel_tool_calls" in sent else None
    if parallel is not None and not isinstance(parallel, bool):
        raise _refusal("parallel_tool_calls", "must be a boolean")
    if tools is None:
        if choice is not None and choice != "none":
            raise _refusal("tool_choice", "requires a non-empty tools list")
        ignored = frozenset({"parallel_tool_calls"}) if "parallel_tool_calls" in sent else frozenset()
        return None, ignored
    return ToolParams(tools=tools, tool_choice=choice, parallel_tool_calls=parallel), frozenset()


def _stream_options(value: Any) -> Tuple[bool, FrozenSet[str]]:
    """`include_usage`, plus `stream_options.<key>` for every other sub-key."""
    if value is None:
        return False, frozenset()
    if not isinstance(value, Mapping):
        raise V1RequestError(INVALID_PARAMETER, "stream_options: must be an object", "stream_options")
    include_usage = value.get("include_usage")
    if include_usage is not None and not isinstance(include_usage, bool):
        param = "stream_options.include_usage"
        raise V1RequestError(INVALID_PARAMETER, f"{param}: must be a boolean", param)
    ignored = frozenset(f"stream_options.{key}" for key in value if key != "include_usage")
    return include_usage is True, ignored


def translate_request(
    body: ChatCompletionRequest,
    *,
    tools_enabled: bool = False,
    tool_models: Sequence[str] = (),
) -> V1Call:
    """The parsed request as pipeline arguments (PRD-015 Sections 7.1, 7.3).

    Checks run in a fixed order and the first failure wins: the rejected keys
    in table order (so a tools client always sees `tools_not_supported`), the
    forwarded keys, `stream_options`, then `translate_messages`.

    A key counts as sent when it is present, even as `null`: a forwarded or
    rejected `null` is the default, an ignored one is still recorded, as
    `name` is in `translate_messages`. `ignored_params` holds names only,
    sorted and comma-joined, None when nothing was ignored. `include_usage`
    is honoured only on a streamed request.

    `tools_enabled` and `tool_models` are the router's per-request reads of
    `V1_TOOLS_ENABLED` and `V1_TOOL_MODELS` (PRD-017 Section 6.7), passed in
    because this module reads no settings; the defaults are the flag-off
    values. With the flag on the order is: the rejected keys except the tool
    params (`functions` / `function_call` stay refused, D10), then `tools`,
    `tool_choice`, `parallel_tool_calls`, then the model check, then the
    forwarded keys, `stream_options` and the messages. The model check (D16)
    runs when tools are forwarded and `tool_models` is non-empty: the list
    describes a model's capability, not a caller's permission, so it holds for
    every caller. Tool history alone is not a `tools` request and is not
    checked.
    """
    sent = frozenset(body.model_fields_set)
    # Declared fields are attributes; extras live only in model_extra.
    values = {key: getattr(body, key) for key in type(body).model_fields}
    values.update(body.model_extra or {})

    tools: Optional[ToolParams] = None
    tool_ignored: FrozenSet[str] = frozenset()
    if tools_enabled:
        _check_rejected(sent, values, skip=TOOL_PARAMS, rules=_FLAG_ON_REJECTED_RULES)
        tools, tool_ignored = _tool_params(sent, values)
        if tools is not None and tool_models and body.model not in tool_models:
            raise V1RequestError(TOOLS_NOT_SUPPORTED, _TOOL_MODEL_RULE, "tools")
    else:
        _check_rejected(sent, values)
    params = _forwarded_params(sent, values)
    include_usage, stream_ignored = _stream_options(body.stream_options)
    messages, message_ignored = translate_messages(body.messages, tools_enabled=tools_enabled)

    top_level = sent - FORWARDED - REJECTED_UNLESS_DEFAULT.keys() - _STRUCTURAL
    if tools_enabled:
        top_level = top_level - TOOL_PARAMS
    ignored = top_level | stream_ignored | message_ignored | tool_ignored
    return V1Call(
        messages=messages,
        params=params,
        model=body.model,
        stream=body.stream,
        include_usage=body.stream and include_usage,
        ignored_params=",".join(sorted(ignored)) or None,
        tools=tools,
    )


def translate_device(raw: Optional[str]) -> Optional[str]:
    """The `X-Harness-Device` header as the audit row's `device` (PRD-015 Section 7.2).

    Stripped, then at most `MAX_DEVICE_LENGTH` printable characters. Absent,
    or empty once stripped, is None: there is nothing to record. The body's
    `user` field is never the device (D1); the router reads only this header.
    The refusal names the header and the rule, never the value (T6).
    """
    if raw is None:
        return None
    value = raw.strip()
    if not value:
        return None
    if len(value) > MAX_DEVICE_LENGTH or not value.isprintable():
        raise V1RequestError(
            INVALID_HEADER,
            f"{DEVICE_HEADER}: must be at most {MAX_DEVICE_LENGTH} printable characters",
        )
    return value


def translate_result(
    result: QuerySuccessResponse, upstream: OpenRouterResult, created: int
) -> ChatCompletion:
    """A successful pipeline result as a `chat.completion` (PRD-015 Section 7.4).

    `QuerySuccessResponse` carries neither the finish reason nor the token
    split, and `/query`'s body must not move (STORY-001), so the router passes
    the upstream result its `call_openrouter` wrapper captured. `created` is a
    parameter so this function reads no clock.

    `finish_reason` is the upstream's when the schema can carry it, else
    "stop" (an omitted one included). A missing split is `0` on both sides
    with the reported total, so clients that compute cost from the keys keep
    working; the audit row keeps NULL, which stays the truth. `model` is the
    requested name, as `model_used` records it.

    PRD-017 Section 6.6, D2, D14, T1: the tool calls come from
    `result.tool_outcome` (step 7c's release), never from `upstream`. When
    calls were evaluated, `finish_reason` is the release's, `harness.actions`
    lists every decision in model order, `tool_calls` carries the released
    calls (`null` when every call was denied) and `content` is `null` when
    calls are released and there is no text or note. With no outcome the
    completion is PRD-015's, byte for byte (D10): neither new key is present.
    The stream renders this same message through `v1_sse.completion_events`
    (role chunk, one delta per released call, finish chunk), so both shapes
    follow one release.

    PRD-018 D14, O2: a journaled success (`audit_id is None`) is id
    `chatcmpl-harness-ref-<audit_ref>`, with `harness.audit_id: null` and
    `harness.audit_ref` set; `harness.audit_ref` is present on every success.
    """
    outcome = result.tool_outcome
    reported = upstream.finish_reason
    finish_reason = reported if reported in _FINISH_REASONS else "stop"
    message = AssistantMessage(content=result.response)  # no tool_calls kwarg: key absent
    actions = None
    if outcome is not None:
        release = outcome.release
        if release.finish_reason is not None:
            finish_reason = release.finish_reason
        # `arguments` is the model's string, passed through untouched (D13).
        released = [
            CompletionToolCall(
                id=call.id,
                function=ToolCallFunction(name=call.name, arguments=call.arguments),
            )
            for call in release.tool_calls
        ]
        content = None if released and not result.response else result.response
        # An explicit `None` keeps `tool_calls: null` (all denied, Section 10).
        message = AssistantMessage(content=content, tool_calls=released or None)
        actions = [
            HarnessAction(
                tool_call_id=d.tool_call_id,
                tool_name=d.tool_name,
                decision=d.decision,
                rule=d.rule,
                reason=d.reason,
            )
            for d in outcome.decisions
        ]
    prompt_tokens = 0 if upstream.input_tokens is None else upstream.input_tokens
    completion_tokens = 0 if upstream.output_tokens is None else upstream.output_tokens
    return ChatCompletion(
        id=(
            chat_completion_id(result.audit_id)
            if result.audit_id is not None
            else chat_completion_ref_id(result.audit_ref)
        ),
        created=created,
        model=result.model_used,
        choices=[Choice(message=message, finish_reason=finish_reason)],
        usage=Usage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=result.tokens_used,
        ),
        harness=HarnessCompletionInfo(
            audit_id=result.audit_id,
            audit_ref=result.audit_ref,
            pii_redacted=result.pii_redacted,
            pii_entities_masked=result.pii_entities_masked,
            actions=actions,
        ),
    )


# The blocked members of `QueryPipelineResult`, spelled out rather than taken
# from query_pipeline, whose import would bring storage into this pure module.
QueryBlockedResponse = Union[
    QueryBlockedDuplicateResponse,
    QueryBlockedSuspiciousResponse,
    QueryBlockedForbiddenResponse,
    QueryBlockedContextLimitResponse,
    QueryBlockedUsageLimitResponse,
]

# PRD-015 Section 7.5 (D2): (status, type, default code, details) per verdict.
# Content verdicts are 400, policy verdicts 403; never 429 or 5xx (T7). The
# details follow the reason after ": " and name only fields of the response:
# the matched pattern is the configured one, returned as on `/query` (T6).
# A blocked member without a row here is a TypeError in translate_verdict, and
# test_every_blocked_member_has_a_verdict fails.
_VERDICTS: Mapping[type, Tuple[int, str, str, Callable[[Any], str]]] = {
    QueryBlockedDuplicateResponse: (
        400, "invalid_request_error", DUPLICATE_REQUEST,
        lambda r: f"first seen {r.first_query_at}",
    ),
    QueryBlockedSuspiciousResponse: (
        400, "invalid_request_error", SUSPICIOUS_PATTERN,
        lambda r: r.pattern,
    ),
    QueryBlockedContextLimitResponse: (
        400, "invalid_request_error", CONTEXT_LENGTH_EXCEEDED,
        lambda r: f"{r.limit} {r.actual} > {r.maximum}",
    ),
    QueryBlockedForbiddenResponse: (
        403, "permission_error", PERMISSION_DENIED,
        lambda r: r.required_permission,
    ),
    QueryBlockedUsageLimitResponse: (
        403, "permission_error", USAGE_LIMIT_EXCEEDED,
        lambda r: f"{r.limit} {r.actual} of {r.maximum}; resets at {r.resets_at}",
    ),
}


def _verdict_code(result: QueryBlockedResponse, default: str) -> str:
    """The table's code, refined by the two fields Section 7.5 splits on."""
    if isinstance(result, QueryBlockedContextLimitResponse):
        if result.limit == "redaction_characters":
            return REDACTION_LIMIT_EXCEEDED
    elif isinstance(result, QueryBlockedForbiddenResponse):
        if result.required_permission.startswith(_MODEL_PERMISSION_PREFIX):
            return MODEL_NOT_PERMITTED
        if result.required_permission == _BREAK_GLASS_PERMISSION:
            return BREAK_GLASS_NOT_PERMITTED
    return default


def translate_verdict(result: QueryBlockedResponse) -> V1Error:
    """A blocked pipeline result as the error the client reads (PRD-015 Section 7.5).

    The pipeline has already written the row. `harness` is every field of the
    response except the constant `status`, so a field added to a response
    reaches the client without a change here. Raises TypeError for a type
    without a verdict, `QuerySuccessResponse` included: guessing a status
    would be worse than a 500.
    """
    try:
        status_code, type_, default_code, details = _VERDICTS[type(result)]
    except KeyError:
        raise TypeError(f"no /v1 verdict for {type(result).__name__}") from None
    return V1Error(
        status_code=status_code,
        type=type_,
        code=_verdict_code(result, default_code),
        message=f"{result.reason}: {details(result)}",
        harness=result.model_dump(mode="json", exclude={"status"}),
    )


# PRD-015 Section 7.5 (D7): (status, type, retryable) per pipeline fault. A
# transient upstream or storage fault is retryable; a deterministic one is not,
# so the same request is never sent again to fail the same way. Keyed by code,
# not exception type: three of the four exceptions live beside storage or the
# PII engines, whose import would end this module's purity. The router maps
# the exception to its code. PRD-018 D8: a storage *outage* is 503, retryable,
# with `Retry-After`; any other storage fault stays `internal_error` (500).
_FAULTS: Mapping[str, Tuple[int, str, bool]] = {
    UPSTREAM_UNAVAILABLE: (502, "api_error", True),
    UPSTREAM_ERROR: (502, "api_error", False),
    INTERNAL_ERROR: (500, "api_error", True),
    REDACTION_FAILED: (500, "api_error", False),
    STORAGE_UNAVAILABLE: (503, "api_error", True),
}


def translate_fault(
    code: str, message: str, retry_after_seconds: Optional[int] = None
) -> V1Error:
    """A pipeline fault as the error the client reads (PRD-015 Section 7.5, D7).

    The router names the code from the exception. `message` is the
    exception's own text, as `/query`'s `detail` is: for an upstream fault the
    client's `OpenRouterError` text, which names the HTTP failure and never the
    provider's body. `harness` is None: there is no pipeline response. Raises
    TypeError for a code without a row, as translate_verdict does.
    """
    try:
        status_code, type_, retryable = _FAULTS[code]
    except KeyError:
        raise TypeError(f"no /v1 fault for {code}") from None
    return V1Error(
        status_code=status_code,
        type=type_,
        code=code,
        message=message,
        retryable=retryable,
        retry_after_seconds=retry_after_seconds,
    )
