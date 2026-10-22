"""Request translation for `/v1` (PRD-015 Sections 4 and 7.1).

Turns the wire request into pipeline arguments. Every refusal is a
`V1RequestError`, which the router maps to a 400 (STORY-009/010). Pure on
purpose, like `app/models/messages.py`: no I/O, no settings reads, no logging.
Parameter classification (STORY-006) lands here too.
"""

from typing import Any, FrozenSet, List, Mapping, Optional, Sequence, Tuple

from app.models.messages import Message, MessageNormalizationError, normalize_message

INVALID_MESSAGES = "invalid_messages"
# The `tools` parameter refusal (STORY-006) raises this same constant, so a
# client sees one code whether the tool use was in a parameter or a message.
TOOLS_NOT_SUPPORTED = "tools_not_supported"

IGNORED_MESSAGE_NAME = "messages[].name"


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
