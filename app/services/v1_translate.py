"""Request translation for `/v1` (PRD-015 Sections 4, 7.1 and 7.3).

Turns the wire request into pipeline arguments: the messages, the forwarded
generation parameters and the names of everything ignored. Every refusal is a
`V1RequestError`, which the router maps to a 400 (STORY-009/010). Pure on
purpose, like `app/models/messages.py`: no I/O, no settings reads, no logging.
"""

from dataclasses import dataclass
from typing import Any, Dict, FrozenSet, List, Mapping, Optional, Sequence, Tuple

from app.models.messages import Message, MessageNormalizationError, normalize_message
from app.models.v1_schemas import ChatCompletionRequest
from app.services.openrouter_client import GenerationParams, UnsupportedParameterError

INVALID_MESSAGES = "invalid_messages"
INVALID_PARAMETER = "invalid_parameter"
UNSUPPORTED_PARAMETER = "unsupported_parameter"
# The `tools` parameter refusal raises this same constant, so a client sees
# one code whether the tool use was in a parameter or a message.
TOOLS_NOT_SUPPORTED = "tools_not_supported"

IGNORED_MESSAGE_NAME = "messages[].name"

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

_REJECTED_RULES = {
    TOOLS_NOT_SUPPORTED: "tool calling is not supported (PRD-016)",
    UNSUPPORTED_PARAMETER: "only the default value is supported on this endpoint",
}

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
    called without `params=`, as for every other ingress.
    """

    messages: List[Message]
    params: Optional[GenerationParams]
    model: str
    stream: bool
    include_usage: bool
    ignored_params: Optional[str]


def translate_messages(raw: Sequence[Any]) -> Tuple[List[Message], FrozenSet[str]]:
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
            # Before the normalizer: it refuses `tool_calls` itself, which
            # would surface as `invalid_messages`, and it accepts `tool`.
            if "tool_calls" in item or "function_call" in item:
                raise V1RequestError(
                    TOOLS_NOT_SUPPORTED, f"{location}: tool calls are not supported (PRD-016)", location
                )
            if item.get("role") == "tool":
                raise V1RequestError(
                    TOOLS_NOT_SUPPORTED, f"{location}: tool turns are not supported (PRD-016)", location
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

    if messages[-1].role != "user":
        location = f"messages[{len(messages) - 1}]"
        raise V1RequestError(
            INVALID_MESSAGES, f"{location}: the last message must be a user turn", location
        )
    return messages, frozenset(ignored)


def _is_default(value: Any, defaults: Tuple[Any, ...]) -> bool:
    # Type first: `True == 1` and `False == 0` would otherwise pass for `n`.
    return any(type(value) is type(default) and value == default for default in defaults)


def _check_rejected(sent: FrozenSet[str], values: Mapping[str, Any]) -> None:
    for key, (code, defaults) in REJECTED_UNLESS_DEFAULT.items():
        if key in sent and not _is_default(values[key], defaults):
            raise V1RequestError(code, f"{key}: {_REJECTED_RULES[code]}", key)


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


def translate_request(body: ChatCompletionRequest) -> V1Call:
    """The parsed request as pipeline arguments (PRD-015 Sections 7.1, 7.3).

    Checks run in a fixed order and the first failure wins: the rejected keys
    in table order (so a tools client always sees `tools_not_supported`), the
    forwarded keys, `stream_options`, then `translate_messages`.

    A key counts as sent when it is present, even as `null`: a forwarded or
    rejected `null` is the default, an ignored one is still recorded, as
    `name` is in `translate_messages`. `ignored_params` holds names only,
    sorted and comma-joined, None when nothing was ignored. `include_usage`
    is honoured only on a streamed request.
    """
    sent = frozenset(body.model_fields_set)
    # Declared fields are attributes; extras live only in model_extra.
    values = {key: getattr(body, key) for key in type(body).model_fields}
    values.update(body.model_extra or {})

    _check_rejected(sent, values)
    params = _forwarded_params(sent, values)
    include_usage, stream_ignored = _stream_options(body.stream_options)
    messages, message_ignored = translate_messages(body.messages)

    top_level = sent - FORWARDED - REJECTED_UNLESS_DEFAULT.keys() - _STRUCTURAL
    ignored = top_level | stream_ignored | message_ignored
    return V1Call(
        messages=messages,
        params=params,
        model=body.model,
        stream=body.stream,
        include_usage=body.stream and include_usage,
        ignored_params=",".join(sorted(ignored)) or None,
    )
