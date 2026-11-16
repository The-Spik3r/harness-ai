"""The one internal message shape (PRD-010 Section 6.2).

OpenAI message shapes -- `content` as a string, a list of parts, or `null` --
become a `Message(role, content: str)` here, and nothing past `normalize_*`
ever sees a part list or a `None`. Pure on purpose: no I/O, no settings, no
pydantic, no `app` import. The pipeline (STORY-004/007), chat history
(STORY-011) and PRD-011..014 build on this module; PRD-014 is the first ingress
that calls the normalizer. PRD-017 D5 adds the tool fields (`tool_calls` on an
assistant turn, `tool_call_id` on a tool turn) to the same shape.
"""

from dataclasses import dataclass
from typing import Any, Literal, Mapping, Optional, Sequence, get_args

# `tool` is valid on purpose, so PRD-017 (tool calling) does not have to widen
# the type. Tool turns now normalize (D5); the pipeline still refuses them at
# step 0 until STORY-005, as `dedup_key` already does.
Role = Literal["system", "user", "assistant", "tool"]

_ROLES = frozenset(get_args(Role))


@dataclass(frozen=True)
class ToolCallSpec:
    """One tool call on an assistant turn (PRD-017 Section 6.2, D5).

    Deliberately not `action_adapters.ToolCall`: this module imports nothing from
    `app`. A test keeps the field names aligned with it.
    """

    id: str
    name: str
    # The raw JSON string, exactly as the model emitted it; never parsed,
    # stripped or re-serialized (PRD-012's contract, PRD-017 D13).
    arguments: str


@dataclass(frozen=True)
class Message:
    """Satisfies PRD-009's `DedupTurn` structurally; no import in either direction.

    Deliberately unvalidated: `run_query` builds `Message("user", prompt)` for
    any prompt `/query` accepts. Validation lives at the edge, in the normalizer.
    The tool fields (PRD-017 D5) are unvalidated here too: per-message shape is
    the normalizer's job, cross-message shape (D6) is STORY-005's.
    """

    role: Role
    content: str
    tool_calls: tuple[ToolCallSpec, ...] = ()  # assistant only
    tool_call_id: Optional[str] = None  # tool only


class MessageNormalizationError(Exception):
    """A raw message is not a shape the pipeline can inspect.

    The message names a location (`messages[3]`, `content[1]`) and the rule
    that failed, never the offending value: content is untrusted, may hold PII,
    and would otherwise reach logs and a PRD-014 400 body verbatim.
    """


def _normalize_content(role: str, content: Any) -> str:
    if isinstance(content, str):
        return content
    if content is None:
        if role == "assistant":
            return ""
        raise MessageNormalizationError("null content is only allowed on assistant messages")
    if isinstance(content, list):
        texts = []
        for index, part in enumerate(content):
            if not isinstance(part, Mapping) or part.get("type") != "text":
                raise MessageNormalizationError(f"content[{index}] is not a text part")
            text = part.get("text")
            if not isinstance(text, str):
                raise MessageNormalizationError(f"content[{index}] text part has no string text")
            texts.append(text)
        # Parts are joined with a newline, not '': it keeps part boundaries
        # visible to pattern detection, so a part ending `ignore` and one
        # starting `previous` cannot fuse into one token (PRD-010 6.2).
        return "\n".join(texts)
    raise MessageNormalizationError("content must be a string, a list of text parts, or null")


def _normalize_tool_calls(calls: Any) -> tuple[ToolCallSpec, ...]:
    if not isinstance(calls, list):
        raise MessageNormalizationError("tool_calls must be a list")
    specs: list[ToolCallSpec] = []
    seen: set[str] = set()
    for index, call in enumerate(calls):
        where = f"tool_calls[{index}]"
        if not isinstance(call, Mapping):
            raise MessageNormalizationError(f"{where} is not an object")
        call_id = call.get("id")
        if not isinstance(call_id, str) or not call_id:
            raise MessageNormalizationError(f"{where}.id must be a non-empty string")
        if call.get("type") != "function":
            raise MessageNormalizationError(f'{where}.type must be "function"')
        function = call.get("function")
        if not isinstance(function, Mapping):
            raise MessageNormalizationError(f"{where}.function is not an object")
        name = function.get("name")
        if not isinstance(name, str) or not name:
            raise MessageNormalizationError(f"{where}.function.name must be a non-empty string")
        # `arguments` is carried as the exact input string: never parsed,
        # stripped or re-serialized (PRD-012's contract, PRD-017 D13). Empty and
        # non-JSON strings are accepted; only `action_adapters.map_tool_call`
        # parses it, for classification.
        arguments = function.get("arguments")
        if not isinstance(arguments, str):
            raise MessageNormalizationError(f"{where}.function.arguments must be a string")
        if call_id in seen:
            raise MessageNormalizationError(f"{where}.id repeats an earlier id in this turn")
        seen.add(call_id)
        specs.append(ToolCallSpec(call_id, name, arguments))
    return tuple(specs)


def normalize_message(raw: Mapping[str, Any]) -> Message:
    """Normalize one raw OpenAI-shaped message (PRD-010 6.2; tool fields PRD-017 D5).

    Per-message shape only; cross-message rules (D6) are STORY-005's. `tool_calls`
    is assistant-only and `tool_call_id` is tool-only (required there, non-empty).
    `tool_calls: null` on any role, and `tool_call_id: null` on a non-tool role,
    count as absent (orchestrator decision STORY-003: OpenAI SDK `model_dump()`
    echoes of text assistant messages carry `tool_calls: null`). `tool_call_id:
    null` on a `tool` turn is refused, since it is required there.
    """
    if not isinstance(raw, Mapping):
        raise MessageNormalizationError("message is not an object")
    role = raw.get("role")
    if not isinstance(role, str) or role not in _ROLES:
        raise MessageNormalizationError(
            "unknown role (expected one of: system, user, assistant, tool)"
        )
    # Tool shape before content: OpenAI's tool-call assistant turn is `content:
    # null` plus `tool_calls`, and a `tool` turn without an id must fail on the
    # id, not on whatever its content happens to be.
    # `tool_calls: null` is absent on any role (SDK `model_dump()` echoes of text
    # assistant turns carry it); a non-null value is assistant-only.
    raw_calls = raw.get("tool_calls")
    tool_calls: tuple[ToolCallSpec, ...] = ()
    if raw_calls is not None:
        if role != "assistant":
            raise MessageNormalizationError("tool_calls are only allowed on assistant messages")
        tool_calls = _normalize_tool_calls(raw_calls)
    tool_call_id: Optional[str] = None
    raw_id = raw.get("tool_call_id")
    if role == "tool":
        if not isinstance(raw_id, str) or not raw_id:
            raise MessageNormalizationError(
                "tool_call_id is required on tool messages and must be a non-empty string"
            )
        tool_call_id = raw_id
    elif raw_id is not None:
        raise MessageNormalizationError("tool_call_id is only allowed on tool messages")
    return Message(role, _normalize_content(role, raw.get("content")), tool_calls, tool_call_id)


def normalize_messages(raw: Sequence[Mapping[str, Any]]) -> list[Message]:
    # Structure across messages (non-empty, last turn is user) is the pipeline's
    # to check (STORY-007): PRD-014 may accept an assistant prefill later.
    if isinstance(raw, (str, bytes)) or not isinstance(raw, Sequence):
        raise MessageNormalizationError("messages must be a list")
    messages = []
    for index, item in enumerate(raw):
        try:
            messages.append(normalize_message(item))
        except MessageNormalizationError as exc:
            raise MessageNormalizationError(f"messages[{index}]: {exc}") from exc
    return messages
