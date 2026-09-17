"""The one internal message shape (PRD-010 Section 6.2).

OpenAI message shapes -- `content` as a string, a list of parts, or `null` --
become a `Message(role, content: str)` here, and nothing past `normalize_*`
ever sees a part list or a `None`. Pure on purpose: no I/O, no settings, no
pydantic, no `app` import. The pipeline (STORY-004/007), chat history
(STORY-011) and PRD-011..014 build on this module; PRD-014 is the first ingress
that calls the normalizer.
"""

from dataclasses import dataclass
from typing import Any, Literal, Mapping, Sequence, get_args

# `tool` is valid on purpose, so PRD-016 does not have to widen the type. The
# pipeline refuses it structurally (STORY-007), as `dedup_key` already does.
Role = Literal["system", "user", "assistant", "tool"]

_ROLES = frozenset(get_args(Role))


@dataclass(frozen=True)
class Message:
    """Satisfies PRD-009's `DedupTurn` structurally; no import in either direction.

    Deliberately unvalidated: `run_query` builds `Message("user", prompt)` for
    any prompt `/query` accepts. Validation lives at the edge, in the normalizer.
    """

    role: Role
    content: str


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


def normalize_message(raw: Mapping[str, Any]) -> Message:
    if not isinstance(raw, Mapping):
        raise MessageNormalizationError("message is not an object")
    role = raw.get("role")
    if not isinstance(role, str) or role not in _ROLES:
        raise MessageNormalizationError(
            "unknown role (expected one of: system, user, assistant, tool)"
        )
    # Before content: OpenAI's tool-call assistant turn is `content: null` plus
    # `tool_calls`, which would otherwise normalize silently to "".
    if "tool_calls" in raw:
        raise MessageNormalizationError("tool_calls are not supported (PRD-016)")
    return Message(role, _normalize_content(role, raw.get("content")))


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
